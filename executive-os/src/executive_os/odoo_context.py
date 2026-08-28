from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

from .identity import DeviceIdentity
from .request_pack import validate_message_body


SEARCHABLE_MODELS = {"project.project", "project.task"}
READABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "project.project": ("id", "name", "company_id", "write_date", "active"),
    "project.task": ("id", "name", "project_id", "company_id", "write_date", "stage_id", "active"),
    "documents.document": (
        "id",
        "name",
        "res_model",
        "res_id",
        "company_id",
        "write_date",
        "owner_id",
    ),
    "approval.request": (
        "id",
        "name",
        "company_id",
        "request_owner_id",
        "request_status",
        "write_date",
    ),
}


class OdooContextError(ValueError):
    pass


class ContextVerificationError(ValueError):
    pass


class OdooToolClient(Protocol):
    async def search_records(
        self,
        *,
        model: str,
        domain: list[Any],
        fields: list[str],
        limit: int,
    ) -> Any: ...

    async def get_record(self, *, model: str, record_id: int, fields: list[str]) -> Any: ...


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class ContextReceiptSigner:
    def __init__(self, signing_key: str, *, ttl_minutes: int = 60):
        if len(signing_key.encode("utf-8")) < 32:
            raise ContextVerificationError("Context signing key must contain at least 32 bytes")
        self._key = signing_key.encode("utf-8")
        self.ttl_minutes = max(5, min(int(ttl_minutes), 1440))

    def issue(
        self,
        *,
        identity: DeviceIdentity,
        model: str,
        record_id: str,
        company_id: str,
        label: str,
        now: datetime | None = None,
    ) -> str:
        issued = now or datetime.now(timezone.utc)
        payload = {
            "requester_id": identity.requester_id,
            "model": model,
            "record_id": str(record_id),
            "company_id": str(company_id),
            "label": label,
            "verified_at": issued.isoformat(),
            "expires_at": (issued + timedelta(minutes=self.ttl_minutes)).isoformat(),
        }
        encoded = _b64encode(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        signature = hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"v1.{encoded}.{_b64encode(signature)}"

    def verify_reference(
        self,
        reference: dict[str, Any],
        *,
        identity: DeviceIdentity,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        receipt = str(reference.get("verification_receipt") or "")
        try:
            version, encoded, supplied_signature = receipt.split(".", 2)
            if version != "v1":
                raise ValueError
            expected_signature = _b64encode(
                hmac.new(self._key, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(expected_signature, supplied_signature):
                raise ValueError
            payload = json.loads(_b64decode(encoded))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ContextVerificationError("Odoo reference is missing a valid server verification receipt") from exc

        claims = {
            "requester_id": identity.requester_id,
            "model": str(reference.get("model") or ""),
            "record_id": str(reference.get("record_id") or ""),
            "company_id": str(reference.get("company_id") or ""),
            "label": str(reference.get("label") or ""),
        }
        for key, expected in claims.items():
            supplied = str(payload.get(key) or "").encode("utf-8")
            if not hmac.compare_digest(supplied, expected.encode("utf-8")):
                raise ContextVerificationError(f"Odoo verification receipt does not match {key}")
        current = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(str(payload["expires_at"]))
        except (KeyError, ValueError) as exc:
            raise ContextVerificationError("Odoo verification receipt has an invalid expiry") from exc
        if expires.tzinfo is None or expires < current:
            raise ContextVerificationError("Odoo verification receipt has expired")
        if claims["company_id"] not in identity.odoo_company_ids:
            raise ContextVerificationError("Odoo company is outside this collaborator's verified scope")
        return payload


def private_mcp_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OdooContextError("ODOO_MCP_URL must be an HTTP(S) URL")
    hostname = parsed.hostname.lower()
    private = hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(
        (".railway.internal", ".internal")
    )
    if not private:
        try:
            private = ipaddress.ip_address(hostname).is_private
        except ValueError:
            private = False
    if not private:
        raise OdooContextError("ODOO_MCP_URL must use a private network endpoint")
    return url


class StreamableHttpOdooClient:
    def __init__(self, url: str, *, timeout_seconds: float = 20):
        self.url = private_mcp_url(url)
        self.timeout_seconds = max(1, min(float(timeout_seconds), 60))

    @staticmethod
    def _payload(result: Any) -> Any:
        if getattr(result, "isError", False):
            raise OdooContextError("Private Odoo reader returned an error")
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured.get("result", structured) if isinstance(structured, dict) else structured
        for item in getattr(result, "content", []):
            text = getattr(item, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue
                return parsed.get("result", parsed) if isinstance(parsed, dict) else parsed
        raise OdooContextError("Private Odoo reader returned no structured record data")

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:  # pragma: no cover - bundled by the Railway Hermes image
            raise RuntimeError("The MCP client dependency is required for Odoo context reads") from exc
        try:
            async with streamable_http_client(self.url) as (reader, writer, _session_id):
                async with ClientSession(reader, writer, read_timeout_seconds=self.timeout_seconds) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        name,
                        arguments,
                        read_timeout_seconds=self.timeout_seconds,
                    )
        except OdooContextError:
            raise
        except Exception as exc:
            raise OdooContextError("Private Odoo context reader is unavailable") from exc
        return self._payload(result)

    async def search_records(
        self,
        *,
        model: str,
        domain: list[Any],
        fields: list[str],
        limit: int,
    ) -> Any:
        return await self._call(
            "search_records",
            {"model": model, "domain": domain, "fields": fields, "limit": limit},
        )

    async def get_record(self, *, model: str, record_id: int, fields: list[str]) -> Any:
        return await self._call(
            "get_record",
            {"model": model, "record_id": record_id, "fields": fields},
        )


@dataclass(frozen=True)
class OdooContextResolver:
    client: OdooToolClient
    signer: ContextReceiptSigner

    @staticmethod
    def _company_id(value: Any) -> str | None:
        if isinstance(value, (list, tuple)) and value:
            return str(value[0])
        if isinstance(value, dict):
            return str(value.get("id")) if value.get("id") is not None else None
        if value not in (None, False, ""):
            return str(value)
        return None

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            if isinstance(payload.get("record"), dict):
                return [payload["record"]]
            for key in ("records", "data", "items"):
                if isinstance(payload.get(key), list):
                    return [row for row in payload[key] if isinstance(row, dict)]
            if "id" in payload:
                return [payload]
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    @staticmethod
    def _identity_scope(identity: DeviceIdentity) -> list[int]:
        if not identity.odoo_company_ids:
            raise OdooContextError("No verified Odoo company scope is configured for this collaborator")
        return [int(value) for value in identity.odoo_company_ids]

    @staticmethod
    def _fields(model: str) -> list[str]:
        if model not in READABLE_FIELDS:
            raise OdooContextError("This Odoo model is not exposed by the internal intake policy")
        return list(READABLE_FIELDS[model])

    def _sanitize(self, model: str, row: dict[str, Any], identity: DeviceIdentity) -> dict[str, Any]:
        company_id = self._company_id(row.get("company_id"))
        if company_id not in identity.odoo_company_ids:
            raise OdooContextError("Odoo record is outside this collaborator's verified company scope")
        safe = {field: row.get(field) for field in READABLE_FIELDS[model] if field in row}
        safe["id"] = str(row.get("id"))
        safe["company_id"] = company_id
        safe["model"] = model
        safe["label"] = str(row.get("name") or row.get("display_name") or "").strip()
        if not safe["id"].isdigit() or not safe["label"]:
            raise OdooContextError("Odoo record lacks an exact ID or readable label")
        safe["verification_receipt"] = self.signer.issue(
            identity=identity,
            model=model,
            record_id=safe["id"],
            company_id=company_id,
            label=safe["label"],
        )
        safe["writes_executed"] = 0
        return safe

    async def search(self, *, identity: DeviceIdentity, model: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
        if model not in SEARCHABLE_MODELS:
            raise OdooContextError("Only projects and tasks can be searched by name")
        clean_query = validate_message_body(query)
        if len(clean_query) < 3:
            raise OdooContextError("Odoo context search requires at least 3 characters")
        if len(clean_query) > 200:
            raise OdooContextError("Odoo context search is limited to 200 characters")
        company_ids = self._identity_scope(identity)
        bounded_limit = min(max(int(limit), 1), 10)
        payload = await self.client.search_records(
            model=model,
            domain=[["company_id", "in", company_ids], ["name", "ilike", clean_query]],
            fields=self._fields(model),
            limit=bounded_limit,
        )
        results: list[dict[str, Any]] = []
        for row in self._rows(payload):
            try:
                results.append(self._sanitize(model, row, identity))
            except OdooContextError:
                continue
        return results

    async def verify(
        self,
        *,
        identity: DeviceIdentity,
        model: str,
        record_id: str | int,
    ) -> dict[str, Any]:
        self._identity_scope(identity)
        clean_id = str(record_id)
        if not clean_id.isdigit() or int(clean_id) <= 0:
            raise OdooContextError("A positive numeric Odoo record ID is required")
        payload = await self.client.get_record(
            model=model,
            record_id=int(clean_id),
            fields=self._fields(model),
        )
        rows = self._rows(payload)
        if len(rows) != 1 or str(rows[0].get("id")) != clean_id:
            raise OdooContextError("Odoo did not return exactly the requested record")
        return self._sanitize(model, rows[0], identity)


def verify_pack_odoo_receipts(
    pack: dict[str, Any],
    *,
    identity: DeviceIdentity,
    signer: ContextReceiptSigner | None,
) -> int:
    references: list[dict[str, Any]] = []
    context = pack["business_context"]
    if context.get("primary_object"):
        references.append(context["primary_object"])
    references.extend(context.get("related_objects", []))
    references.extend(operation["target"] for operation in pack.get("proposed_operations", []))
    odoo_references = [reference for reference in references if reference.get("system") == "odoo"]
    if odoo_references and signer is None:
        raise ContextVerificationError("Server-side Odoo context verification is not configured")
    seen: set[tuple[str, str, str, str]] = set()
    for reference in odoo_references:
        assert signer is not None
        signer.verify_reference(reference, identity=identity)
        seen.add(
            (
                str(reference.get("model")),
                str(reference.get("record_id")),
                str(reference.get("company_id")),
                str(reference.get("label")),
            )
        )
    return len(seen)
