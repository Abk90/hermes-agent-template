from __future__ import annotations

from typing import Any

from .config import load_config
from .ledger import Ledger
from .models import RequestStatus
from .triage import classify


class ExecutiveOSService:
    def __init__(self, ledger: Ledger | None = None):
        self.config = load_config()
        self.ledger = ledger or Ledger()

    def triage_request(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        actor: str,
    ) -> dict[str, Any]:
        decision = classify(payload, config=self.config)
        record, created = self.ledger.create_or_get(
            payload=payload,
            decision=decision,
            idempotency_key=idempotency_key,
            actor=actor,
        )
        return {
            "created": created,
            "request_id": record["request_id"],
            "status": record["status"],
            "decision": decision.as_dict() if created else self.ledger.explain(record["request_id"])["request"]["decision"],
        }

    def list_queue(self, priorities: list[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        return self.ledger.list_queue(priorities, limit)

    def explain(self, request_id: str) -> dict[str, Any]:
        return self.ledger.explain(request_id)

    def transition(
        self,
        request_id: str,
        new_status: str,
        actor: str,
        justification: str,
        result: str = "DONE",
        error: str | None = None,
    ) -> dict[str, Any]:
        return self.ledger.transition(
            request_id,
            RequestStatus(new_status),
            actor=actor,
            justification=justification,
            result=result,
            error=error,
        )
