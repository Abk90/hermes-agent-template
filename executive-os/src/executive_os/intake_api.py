from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .identity import IdentityRegistry
from .intake import IntakePermissionError, InternalIntakeService
from .ledger import Ledger
from .odoo_context import (
    ContextReceiptSigner,
    ContextVerificationError,
    OdooContextError,
    OdooContextResolver,
    StreamableHttpOdooClient,
)
from .request_pack import RequestPackError


MAX_BODY_BYTES = 65_536


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class IntakeAPISettings:
    enabled: bool
    bot_username: str | None
    start_token_ttl_minutes: int
    context_signing_key: str | None = None
    context_receipt_ttl_minutes: int = 60

    @classmethod
    def from_env(cls) -> "IntakeAPISettings":
        return cls(
            enabled=_enabled(os.environ.get("INTERNAL_INTAKE_API_ENABLED")),
            bot_username=os.environ.get("INTERNAL_INTAKE_TELEGRAM_BOT_USERNAME"),
            start_token_ttl_minutes=int(os.environ.get("INTERNAL_INTAKE_START_TOKEN_TTL_MINUTES", "30")),
            context_signing_key=os.environ.get("INTERNAL_INTAKE_CONTEXT_SIGNING_KEY"),
            context_receipt_ttl_minutes=int(
                os.environ.get("INTERNAL_INTAKE_CONTEXT_RECEIPT_TTL_MINUTES", "60")
            ),
        )


def _json_response(payload: dict[str, Any] | list[Any], status_code: int = 200):
    from starlette.responses import JSONResponse

    return JSONResponse(payload, status_code=status_code)


async def _read_json(request: Any) -> dict[str, Any]:
    declared = request.headers.get("content-length")
    if declared and int(declared) > MAX_BODY_BYTES:
        raise ValueError("Request body is too large")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValueError("Request body is too large")
    try:
        parsed = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def _bearer_token(request: Any) -> str | None:
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    return authorization[len(prefix) :].strip() if authorization.startswith(prefix) else None


def build_app(
    *,
    ledger: Ledger | None = None,
    registry: IdentityRegistry | None = None,
    settings: IntakeAPISettings | None = None,
    context_signer: ContextReceiptSigner | None = None,
    odoo_resolver: OdooContextResolver | None = None,
):
    from starlette.applications import Starlette
    from starlette.routing import Route

    configured = settings or IntakeAPISettings.from_env()
    identity_registry = registry or IdentityRegistry.from_json(
        os.environ.get("INTERNAL_INTAKE_DEVICE_CREDENTIALS_JSON")
    )
    signer = context_signer
    if signer is None and configured.context_signing_key:
        signer = ContextReceiptSigner(
            configured.context_signing_key,
            ttl_minutes=configured.context_receipt_ttl_minutes,
        )
    resolver = odoo_resolver
    odoo_mcp_url = os.environ.get("ODOO_MCP_URL", "").strip()
    if resolver is None and signer is not None and odoo_mcp_url:
        resolver = OdooContextResolver(StreamableHttpOdooClient(odoo_mcp_url), signer)
    intake = InternalIntakeService(
        ledger=ledger,
        registry=identity_registry,
        bot_username=configured.bot_username,
        start_token_ttl_minutes=configured.start_token_ttl_minutes,
        context_signer=signer,
        odoo_resolver=resolver,
    )

    def require_identity(request: Any):
        token = _bearer_token(request)
        identity = identity_registry.authenticate(token or "")
        if not identity:
            raise IntakePermissionError("Invalid or inactive device credential")
        return identity

    async def health(_request: Any):
        return _json_response(
            {
                "status": "ok",
                "mode": "observe",
                "api_enabled": configured.enabled,
                "active_device_credentials": identity_registry.active_count,
                "telegram_bot_configured": bool(configured.bot_username),
                "odoo_context_reader_configured": resolver is not None,
                "writes_enabled": False,
            }
        )

    async def submit_request(request: Any):
        if not configured.enabled:
            return _json_response({"error": "internal intake API is disabled"}, 503)
        try:
            identity = require_identity(request)
            idempotency_key = request.headers.get("idempotency-key", "").strip()
            if not idempotency_key:
                return _json_response({"error": "Idempotency-Key header is required"}, 400)
            pack = await _read_json(request)
            result = intake.submit_pack(
                pack,
                identity=identity,
                idempotency_key=idempotency_key,
                source="api",
                source_message_id=pack.get("submission_id") or idempotency_key,
            )
            return _json_response(result, 201 if result["created"] else 200)
        except RequestPackError as exc:
            return _json_response({"error": "invalid_request_pack", "issues": exc.issues}, 422)
        except ContextVerificationError as exc:
            return _json_response({"error": "unverified_odoo_context", "issues": [str(exc)]}, 422)
        except IntakePermissionError as exc:
            return _json_response({"error": str(exc)}, 401)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, 400)

    async def get_request(request: Any):
        if not configured.enabled:
            return _json_response({"error": "internal intake API is disabled"}, 503)
        try:
            identity = require_identity(request)
            return _json_response(intake.get_request(request.path_params["request_id"], identity=identity))
        except IntakePermissionError as exc:
            return _json_response({"error": str(exc)}, 403)
        except KeyError:
            return _json_response({"error": "request not found"}, 404)

    async def revise_request(request: Any):
        if not configured.enabled:
            return _json_response({"error": "internal intake API is disabled"}, 503)
        try:
            identity = require_identity(request)
            pack = await _read_json(request)
            result = intake.revise_pack(request.path_params["request_id"], pack, identity=identity)
            return _json_response(result)
        except RequestPackError as exc:
            return _json_response({"error": "invalid_request_pack", "issues": exc.issues}, 422)
        except ContextVerificationError as exc:
            return _json_response({"error": "unverified_odoo_context", "issues": [str(exc)]}, 422)
        except IntakePermissionError as exc:
            return _json_response({"error": str(exc)}, 403)
        except KeyError:
            return _json_response({"error": "request not found"}, 404)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, 400)

    async def append_message(request: Any):
        if not configured.enabled:
            return _json_response({"error": "internal intake API is disabled"}, 503)
        try:
            identity = require_identity(request)
            payload = await _read_json(request)
            message_id = str(payload.get("message_id") or "").strip()
            body = str(payload.get("body") or "").strip()
            if not message_id or not body:
                return _json_response({"error": "message_id and body are required"}, 400)
            return _json_response(
                intake.append_api_message(
                    request.path_params["request_id"],
                    identity=identity,
                    message_id=message_id,
                    body=body,
                ),
                201,
            )
        except IntakePermissionError as exc:
            return _json_response({"error": str(exc)}, 403)
        except KeyError:
            return _json_response({"error": "request not found"}, 404)
        except ValueError as exc:
            return _json_response({"error": str(exc)}, 400)

    async def odoo_search(request: Any):
        if not configured.enabled:
            return _json_response({"error": "internal intake API is disabled"}, 503)
        try:
            identity = require_identity(request)
            payload = await _read_json(request)
            result = await intake.search_odoo_context(
                identity=identity,
                model=str(payload.get("model") or ""),
                query=str(payload.get("query") or ""),
                limit=int(payload.get("limit", 8)),
            )
            return _json_response(result)
        except IntakePermissionError as exc:
            return _json_response({"error": str(exc)}, 401)
        except (OdooContextError, TypeError, ValueError) as exc:
            return _json_response({"error": str(exc)}, 400)

    async def odoo_verify(request: Any):
        if not configured.enabled:
            return _json_response({"error": "internal intake API is disabled"}, 503)
        try:
            identity = require_identity(request)
            payload = await _read_json(request)
            result = await intake.verify_odoo_context(
                identity=identity,
                model=str(payload.get("model") or ""),
                record_id=str(payload.get("record_id") or ""),
            )
            return _json_response(result)
        except IntakePermissionError as exc:
            return _json_response({"error": str(exc)}, 401)
        except (OdooContextError, ValueError) as exc:
            return _json_response({"error": str(exc)}, 400)

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/v1/requests", submit_request, methods=["POST"]),
        Route("/v1/requests/{request_id:str}", get_request, methods=["GET"]),
        Route("/v1/requests/{request_id:str}", revise_request, methods=["PUT"]),
        Route("/v1/requests/{request_id:str}/messages", append_message, methods=["POST"]),
        Route("/v1/context/odoo/search", odoo_search, methods=["POST"]),
        Route("/v1/context/odoo/verify", odoo_verify, methods=["POST"]),
    ]
    app = Starlette(debug=False, routes=routes)
    app.state.intake = intake
    app.state.identity_registry = identity_registry
    app.state.settings = configured
    return app


def create_app():
    return build_app()
