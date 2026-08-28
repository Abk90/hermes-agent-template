from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from .identity import DeviceIdentity, IdentityRegistry
from .ledger import Ledger
from .odoo_context import (
    ContextReceiptSigner,
    OdooContextResolver,
    verify_pack_odoo_receipts,
)
from .request_pack import (
    normalize_request_pack,
    object_references,
    validate_message_body,
    validate_request_pack,
)
from .service import ExecutiveOSService
from .triage import classify


class IntakePermissionError(PermissionError):
    pass


class InternalIntakeService:
    def __init__(
        self,
        *,
        ledger: Ledger | None = None,
        registry: IdentityRegistry | None = None,
        bot_username: str | None = None,
        start_token_ttl_minutes: int = 30,
        context_signer: ContextReceiptSigner | None = None,
        odoo_resolver: OdooContextResolver | None = None,
    ):
        self.ledger = ledger or Ledger()
        self.registry = registry or IdentityRegistry([])
        self.executive = ExecutiveOSService(self.ledger)
        self.bot_username = str(bot_username or "").strip().lstrip("@") or None
        self.start_token_ttl_minutes = max(5, min(int(start_token_ttl_minutes), 1440))
        self.context_signer = context_signer
        self.odoo_resolver = odoo_resolver

    def _assert_owner(self, request_id: str, requester_id: str) -> dict[str, Any]:
        record = self.ledger.get_request(request_id)
        if not record:
            raise KeyError(request_id)
        if record["requester_id"] != requester_id:
            raise IntakePermissionError("Request does not belong to this collaborator")
        return record

    def _telegram_continuation(self, request_id: str, identity: DeviceIdentity, *, issue: bool) -> dict[str, Any]:
        binding = self.ledger.get_telegram_binding(identity.requester_id)
        if binding:
            return {
                "paired": True,
                "request_id": request_id,
                "telegram_user_id_verified": True,
                "deep_link": None,
            }
        if not issue or not self.bot_username or not identity.telegram_user_id:
            return {
                "paired": False,
                "request_id": request_id,
                "telegram_user_id_verified": bool(identity.telegram_user_id),
                "deep_link": None,
            }
        expires = datetime.now(timezone.utc) + timedelta(minutes=self.start_token_ttl_minutes)
        raw_token = self.ledger.issue_telegram_start_token(
            request_id,
            requester_id=identity.requester_id,
            expected_telegram_user_id=identity.telegram_user_id,
            expires_at=expires.isoformat(),
        )
        return {
            "paired": False,
            "request_id": request_id,
            "telegram_user_id_verified": True,
            "deep_link": f"https://t.me/{self.bot_username}?start={raw_token}",
            "expires_at": expires.isoformat(),
        }

    def submit_pack(
        self,
        pack: dict[str, Any],
        *,
        identity: DeviceIdentity,
        idempotency_key: str,
        source: str,
        source_message_id: str,
    ) -> dict[str, Any]:
        assessment = validate_request_pack(pack)
        scoped_key = f"{source}:{identity.requester_id}:{idempotency_key}"
        existing = self.ledger.get_request_by_idempotency_key(scoped_key)
        if existing:
            existing_pack = json.loads(existing["payload_json"]).get("request_pack")
            if json.dumps(existing_pack, sort_keys=True, ensure_ascii=False) != json.dumps(
                pack, sort_keys=True, ensure_ascii=False
            ):
                raise ValueError("Idempotency key was already used with a different request pack")
            verified_odoo_objects = len(
                {
                    (
                        str(reference.get("model")),
                        str(reference.get("record_id")),
                        str(reference.get("company_id")),
                    )
                    for reference in self.declared_references(pack)
                    if reference.get("system") == "odoo"
                }
            )
        else:
            verified_odoo_objects = verify_pack_odoo_receipts(
                pack,
                identity=identity,
                signer=self.context_signer,
            )
        payload = normalize_request_pack(
            pack,
            requester_id=identity.requester_id,
            requester_name=identity.display_name,
            source=source,
            source_message_id=source_message_id,
            assessment=assessment,
        )
        result = self.executive.triage_request(
            payload,
            idempotency_key=scoped_key,
            actor=f"device:{identity.device_id}",
        )
        if not result["created"]:
            existing = self.ledger.explain(result["request_id"])["request"]["payload"].get("request_pack")
            if json.dumps(existing, sort_keys=True, ensure_ascii=False) != json.dumps(
                pack, sort_keys=True, ensure_ascii=False
            ):
                raise ValueError("Idempotency key was already used with a different request pack")
        if result["created"]:
            decision = classify(payload, config=self.executive.config)
            indexed = self.ledger.record_request_pack(
                result["request_id"],
                pack=pack,
                decision=decision,
                actor=f"device:{identity.device_id}",
            )
        else:
            indexed = {"links_added": 0, "proposals_added": 0}
        return {
            **result,
            "preparation": {
                "ready": not assessment.preparation_gaps,
                "gaps": assessment.preparation_gaps,
                "questions": assessment.questions,
            },
            "indexed": indexed,
            "writes_executed": 0,
            "verified_odoo_objects": verified_odoo_objects,
            "telegram": self._telegram_continuation(
                result["request_id"], identity, issue=bool(result["created"])
            ),
        }

    def revise_pack(
        self,
        request_id: str,
        pack: dict[str, Any],
        *,
        identity: DeviceIdentity,
    ) -> dict[str, Any]:
        current = self._assert_owner(request_id, identity.requester_id)
        assessment = validate_request_pack(pack)
        verified_odoo_objects = verify_pack_odoo_receipts(
            pack,
            identity=identity,
            signer=self.context_signer,
        )
        self.ledger.assert_operation_proposals_compatible(
            request_id,
            pack.get("proposed_operations", []),
        )
        payload = normalize_request_pack(
            pack,
            requester_id=identity.requester_id,
            requester_name=identity.display_name,
            source=current["source"],
            source_message_id=current.get("source_message_id") or pack["submission_id"],
            assessment=assessment,
        )
        decision = classify(payload, config=self.executive.config)
        self.ledger.revise_request(
            request_id,
            payload=payload,
            pack=pack,
            decision=decision,
            actor=f"device:{identity.device_id}",
        )
        indexed = self.ledger.record_request_pack(
            request_id,
            pack=pack,
            decision=decision,
            actor=f"device:{identity.device_id}",
        )
        return {
            "request_id": request_id,
            "status": "QUALIFYING" if assessment.preparation_gaps or decision.missing_fields else "READY",
            "decision": decision.as_dict(),
            "preparation": {
                "ready": not assessment.preparation_gaps,
                "gaps": assessment.preparation_gaps,
                "questions": assessment.questions,
            },
            "indexed": indexed,
            "writes_executed": 0,
            "verified_odoo_objects": verified_odoo_objects,
        }

    async def search_odoo_context(
        self,
        *,
        identity: DeviceIdentity,
        model: str,
        query: str,
        limit: int = 8,
    ) -> dict[str, Any]:
        if self.odoo_resolver is None:
            raise ValueError("Private Odoo context reader is not configured")
        results = await self.odoo_resolver.search(
            identity=identity,
            model=model,
            query=query,
            limit=limit,
        )
        return {"results": results, "count": len(results), "writes_executed": 0}

    async def verify_odoo_context(
        self,
        *,
        identity: DeviceIdentity,
        model: str,
        record_id: str,
    ) -> dict[str, Any]:
        if self.odoo_resolver is None:
            raise ValueError("Private Odoo context reader is not configured")
        return await self.odoo_resolver.verify(
            identity=identity,
            model=model,
            record_id=record_id,
        )

    def _paired_telegram_identity(self, telegram_user_id: str, chat_id: str) -> DeviceIdentity:
        identity = self.registry.by_telegram_user_id(telegram_user_id)
        if not identity:
            raise IntakePermissionError("Telegram identity is not on the verified allowlist")
        binding = self.ledger.get_telegram_binding(identity.requester_id)
        if not binding or str(binding["telegram_user_id"]) != str(telegram_user_id):
            raise IntakePermissionError("Telegram identity has not completed exact pairing")
        if str(binding["chat_id"]) != str(chat_id):
            raise IntakePermissionError("Telegram chat does not match the verified private chat")
        return identity

    async def search_telegram_odoo_context(
        self,
        *,
        telegram_user_id: str,
        chat_id: str,
        model: str,
        query: str,
        limit: int = 8,
    ) -> dict[str, Any]:
        identity = self._paired_telegram_identity(telegram_user_id, chat_id)
        return await self.search_odoo_context(
            identity=identity,
            model=model,
            query=query,
            limit=limit,
        )

    async def verify_telegram_odoo_context(
        self,
        *,
        telegram_user_id: str,
        chat_id: str,
        model: str,
        record_id: str,
    ) -> dict[str, Any]:
        identity = self._paired_telegram_identity(telegram_user_id, chat_id)
        return await self.verify_odoo_context(
            identity=identity,
            model=model,
            record_id=record_id,
        )

    def get_request(self, request_id: str, *, identity: DeviceIdentity) -> dict[str, Any]:
        self._assert_owner(request_id, identity.requester_id)
        return self.ledger.explain(request_id)

    def append_api_message(
        self,
        request_id: str,
        *,
        identity: DeviceIdentity,
        message_id: str,
        body: str,
    ) -> dict[str, Any]:
        self._assert_owner(request_id, identity.requester_id)
        clean_body = validate_message_body(body)
        created = self.ledger.append_message(
            request_id,
            source="api",
            source_message_id=f"{identity.requester_id}:{message_id}",
            actor=f"device:{identity.device_id}",
            body=clean_body,
        )
        return {"request_id": request_id, "created": created, "writes_executed": 0}

    def bind_telegram_start(
        self,
        *,
        start_token: str,
        telegram_user_id: str,
        chat_id: str,
    ) -> dict[str, Any]:
        identity = self.registry.by_telegram_user_id(telegram_user_id)
        if not identity:
            raise IntakePermissionError("Telegram identity is not on the verified allowlist")
        result = self.ledger.consume_telegram_start_token(
            start_token,
            telegram_user_id=str(telegram_user_id),
            chat_id=str(chat_id),
            actor=f"telegram:{telegram_user_id}",
        )
        if result["requester_id"] != identity.requester_id:
            raise IntakePermissionError("Telegram identity does not match request owner")
        return {**result, "writes_executed": 0}

    def submit_telegram_pack(
        self,
        pack: dict[str, Any],
        *,
        telegram_user_id: str,
        chat_id: str,
        message_id: str,
    ) -> dict[str, Any]:
        identity = self.registry.by_telegram_user_id(telegram_user_id)
        if not identity:
            raise IntakePermissionError("Telegram identity is not on the verified allowlist")
        binding = self.ledger.get_telegram_binding(identity.requester_id)
        if not binding or str(binding["telegram_user_id"]) != str(telegram_user_id):
            raise IntakePermissionError("Telegram identity has not completed exact pairing")
        return self.submit_pack(
            pack,
            identity=identity,
            idempotency_key=f"{chat_id}:{message_id}",
            source="telegram",
            source_message_id=str(message_id),
        )

    def append_telegram_message(
        self,
        request_id: str,
        *,
        telegram_user_id: str,
        chat_id: str,
        message_id: str,
        body: str,
    ) -> dict[str, Any]:
        identity = self.registry.by_telegram_user_id(telegram_user_id)
        if not identity:
            raise IntakePermissionError("Telegram identity is not on the verified allowlist")
        self._assert_owner(request_id, identity.requester_id)
        binding = self.ledger.get_telegram_binding(identity.requester_id)
        if not binding or str(binding["telegram_user_id"]) != str(telegram_user_id):
            raise IntakePermissionError("Telegram identity has not completed exact pairing")
        if str(binding["chat_id"]) != str(chat_id):
            raise IntakePermissionError("Telegram chat does not match the verified private chat")
        clean_body = validate_message_body(body)
        created = self.ledger.append_message(
            request_id,
            source="telegram",
            source_message_id=f"{chat_id}:{message_id}",
            actor=f"telegram:{telegram_user_id}",
            body=clean_body,
        )
        return {"request_id": request_id, "created": created, "writes_executed": 0}

    def get_telegram_request(self, request_id: str, *, telegram_user_id: str) -> dict[str, Any]:
        identity = self.registry.by_telegram_user_id(telegram_user_id)
        if not identity:
            raise IntakePermissionError("Telegram identity is not on the verified allowlist")
        self._assert_owner(request_id, identity.requester_id)
        binding = self.ledger.get_telegram_binding(identity.requester_id)
        if not binding or str(binding["telegram_user_id"]) != str(telegram_user_id):
            raise IntakePermissionError("Telegram identity has not completed exact pairing")
        return self.ledger.explain(request_id)

    def list_telegram_requests(self, *, telegram_user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        identity = self.registry.by_telegram_user_id(telegram_user_id)
        if not identity:
            raise IntakePermissionError("Telegram identity is not on the verified allowlist")
        binding = self.ledger.get_telegram_binding(identity.requester_id)
        if not binding or str(binding["telegram_user_id"]) != str(telegram_user_id):
            raise IntakePermissionError("Telegram identity has not completed exact pairing")
        return self.ledger.list_requests_for_requester(identity.requester_id, limit)

    @staticmethod
    def declared_references(pack: dict[str, Any]) -> list[dict[str, Any]]:
        return object_references(pack)
