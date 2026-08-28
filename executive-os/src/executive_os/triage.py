from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .config import AppConfig, load_config
from .models import Priority, Route, TriageDecision


CONSEQUENCE_RANK = {
    "none": 0,
    "minor": 1,
    "material": 2,
    "major": 3,
    "critical": 4,
}

QUESTION_BY_FIELD = {
    "requester_id": "Qui formule exactement cette demande ?",
    "subject": "Quel est le sujet precis ?",
    "requested_decision": "Quelle decision exacte attends-tu d'Ahmed ?",
    "deadline_at": "Avant quelle date et quelle heure la decision est-elle necessaire ?",
    "consequence_2h": "Que se passe-t-il concretement si Ahmed repond dans deux heures ?",
    "consequence_tomorrow": "Et s'il repond demain ?",
    "amount_mad": "Quel est le montant en DH ?",
    "odoo_reference": "Quelle est la reference Odoo correspondante ?",
    "recommendation": "Quelle solution recommandes-tu ?",
}


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _parse_deadline(value: Any, timezone_name: str) -> datetime | None:
    if not _present(value):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc)


def missing_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("requester_id", "subject", "requested_decision"):
        if not _present(payload.get(field)):
            missing.append(field)

    urgency_claimed = bool(payload.get("urgency_claimed"))
    payment_like = str(payload.get("request_type", "")).lower() in {
        "payment",
        "supplier",
        "purchase",
    }
    if urgency_claimed:
        for field in ("deadline_at", "consequence_2h", "consequence_tomorrow"):
            if not _present(payload.get(field)):
                missing.append(field)
    if payment_like and not _present(payload.get("amount_mad")):
        missing.append("amount_mad")
    if payload.get("requires_odoo_workflow") and not _present(payload.get("odoo_reference")):
        missing.append("odoo_reference")
    if payload.get("decision_required", True) and not _present(payload.get("recommendation")):
        missing.append("recommendation")
    return missing


def _choose_route(payload: dict[str, Any], priority: Priority, missing: list[str]) -> Route:
    if missing and priority != Priority.P0:
        return Route.CLARIFY
    if payload.get("procedure_known") and payload.get("can_answer_safely"):
        return Route.ANSWER
    if _present(payload.get("responsible_owner")) and not payload.get("decision_required", True):
        return Route.DELEGATE
    if payload.get("requires_odoo_workflow"):
        return Route.ODOO
    if payload.get("ahmed_personal_action"):
        return Route.OMNIFOCUS
    if priority in {Priority.P0, Priority.P1, Priority.P2} or payload.get("decision_required", True):
        return Route.EXECUTIVE_QUEUE
    if priority == Priority.P3:
        return Route.ARCHIVE
    return Route.BACKLOG


def classify(
    payload: dict[str, Any],
    *,
    config: AppConfig | None = None,
    now: datetime | None = None,
) -> TriageDecision:
    cfg = config or load_config()
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    deadline = _parse_deadline(payload.get("deadline_at"), cfg.triage.timezone)
    minutes_to_deadline = None
    if deadline:
        minutes_to_deadline = (deadline - now_utc).total_seconds() / 60

    consequence = CONSEQUENCE_RANK.get(str(payload.get("consequence_level", "none")).lower(), 0)
    amount = float(payload.get("amount_mad") or 0)
    people_blocked = int(payload.get("people_blocked") or 0)
    irreversible = bool(payload.get("irreversible"))
    safety = bool(payload.get("human_safety_risk"))
    serious_legal = bool(payload.get("serious_legal_risk"))
    major_client_crisis = bool(payload.get("major_client_crisis"))
    direct_emergency = bool(payload.get("direct_emergency_requested"))
    reasons: list[str] = []

    imminent = minutes_to_deadline is not None and minutes_to_deadline <= cfg.triage.p0_window_minutes
    today = minutes_to_deadline is not None and minutes_to_deadline <= cfg.triage.p1_window_hours * 60

    if safety or serious_legal:
        priority = Priority.P0
        reasons.append("Danger humain ou risque legal serieux signale.")
    elif irreversible and imminent and consequence >= CONSEQUENCE_RANK["major"]:
        priority = Priority.P0
        reasons.append("Decision irreversible imminente avec consequence majeure.")
    elif major_client_crisis and imminent:
        priority = Priority.P0
        reasons.append("Crise client majeure a echeance immediate.")
    elif today and (
        consequence >= CONSEQUENCE_RANK["major"]
        or people_blocked > 0
        or amount >= cfg.triage.significant_amount_mad
        or payload.get("operation_blocked")
    ):
        priority = Priority.P1
        reasons.append("Consequence materielle aujourd'hui, personnes ou operation bloquees.")
    elif payload.get("information_only"):
        priority = Priority.P3
        reasons.append("Information sans decision ni action immediate.")
    elif payload.get("idea_or_opportunity"):
        priority = Priority.P4
        reasons.append("Idee ou opportunite sans action actuelle.")
    else:
        priority = Priority.P2
        reasons.append("Decision normale sans preuve d'interruption immediate.")

    if payload.get("urgency_claimed") and priority not in {Priority.P0, Priority.P1}:
        reasons.append("Le mot urgent n'a pas suffi sans consequence et echeance probantes.")
    if amount >= cfg.triage.large_amount_mad:
        reasons.append("Montant financier eleve : jugement explicite d'Ahmed requis.")

    missing = missing_fields(payload)
    route = _choose_route(payload, priority, missing)
    confidence = "high" if not missing else ("medium" if priority == Priority.P0 else "low")
    questions = [QUESTION_BY_FIELD[field] for field in missing if field in QUESTION_BY_FIELD]
    return TriageDecision(
        priority=priority,
        route=route,
        confidence=confidence,
        justification=reasons,
        missing_fields=missing,
        questions=questions,
        direct_human_path=direct_emergency or priority == Priority.P0,
    )
