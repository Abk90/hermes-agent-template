from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class Route(StrEnum):
    CLARIFY = "clarify"
    ANSWER = "answer"
    DELEGATE = "delegate"
    ODOO = "odoo"
    OMNIFOCUS = "omnifocus"
    EXECUTIVE_QUEUE = "executive_queue"
    ARCHIVE = "archive"
    BACKLOG = "backlog"


class RequestStatus(StrEnum):
    NEW = "NEW"
    QUALIFYING = "QUALIFYING"
    READY = "READY"
    PENDING = "PENDING"
    RETRYING = "RETRYING"
    DONE = "DONE"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class TriageDecision:
    priority: Priority
    route: Route
    confidence: str
    justification: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    direct_human_path: bool = False

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["priority"] = self.priority.value
        result["route"] = self.route.value
        return result
