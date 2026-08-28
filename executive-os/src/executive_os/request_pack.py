from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "request-pack-v1.schema.json"
ODOO_MODEL_PATTERN = re.compile(r"^[a-z][a-z0-9_.]+$")
SECRET_KEY_PATTERN = re.compile(
    r"(?:^|_)(?:api_?key|password|passwd|secret|token|credential|private_?key)(?:$|_)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    r"|\bsk-[A-Za-z0-9_-]{20,}\b"
    r"|\bgh[opsu]_[A-Za-z0-9]{20,}\b"
    r"|\b[0-9]{6,12}:[A-Za-z0-9_-]{20,}\b"
    r"|\bBearer\s+[A-Za-z0-9._~-]{20,}"
    r"|https?://[^/\s:@]+:[^/\s@]+@",
    re.IGNORECASE,
)


class RequestPackError(ValueError):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


@dataclass(frozen=True)
class PackAssessment:
    preparation_gaps: list[str]
    questions: list[str]


QUESTION_BY_GAP = {
    "business_context.primary_object": "Quel est l'objet métier exact (système, modèle et ID) ?",
    "business_context.unresolved_reason": "Pourquoi le rattachement exact n'a-t-il pas pu être résolu ?",
    "preparation.research": "Quelle recherche as-tu effectuée et quelles sources as-tu vérifiées ?",
    "preparation.research_reason": "Pourquoi aucune recherche n'était-elle utile ou possible ?",
    "preparation.options": "Quelles solutions as-tu comparées ?",
    "preparation.recommendation": "Quelle solution recommandes-tu et pourquoi ?",
    "preparation.work": "Qu'as-tu déjà réalisé dans ton périmètre, ou pourquoi aucune action n'était possible ?",
}


def load_schema(path: str | Path | None = None) -> dict[str, Any]:
    return json.loads(Path(path or DEFAULT_SCHEMA_PATH).read_text(encoding="utf-8"))


def _format_jsonschema_error(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    return f"{path or '$'}: {error.message}"


def _scan_secret_keys(value: Any, path: str = "$") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}"
            if SECRET_KEY_PATTERN.search(str(key)):
                issues.append(f"{nested_path}: secret-like fields are forbidden")
            issues.extend(_scan_secret_keys(nested, nested_path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            issues.extend(_scan_secret_keys(nested, f"{path}[{index}]"))
    elif isinstance(value, str) and SECRET_VALUE_PATTERN.search(value):
        issues.append(f"{path}: credential-like value is forbidden")
    return issues


def validate_message_body(body: str) -> str:
    clean = str(body or "").strip()
    if not clean:
        raise ValueError("message body is required")
    if len(clean) > 8000:
        raise ValueError("message body exceeds 8000 characters")
    if SECRET_VALUE_PATTERN.search(clean):
        raise ValueError("message body contains a credential-like value")
    return clean


def _validate_object_reference(reference: dict[str, Any], path: str) -> list[str]:
    issues: list[str] = []
    if reference.get("system") == "odoo":
        model = str(reference.get("model") or "")
        record_id = str(reference.get("record_id") or "")
        company_id = str(reference.get("company_id") or "")
        if not ODOO_MODEL_PATTERN.fullmatch(model):
            issues.append(f"{path}.model: exact Odoo model is required")
        if not record_id.isdigit() or int(record_id) <= 0:
            issues.append(f"{path}.record_id: positive numeric Odoo ID is required")
        if not company_id:
            issues.append(f"{path}.company_id: exact Odoo company ID is required")
    return issues


def validate_request_pack(pack: dict[str, Any], *, schema_path: str | Path | None = None) -> PackAssessment:
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency is baked into Railway image
        raise RuntimeError("Install jsonschema to validate Bureau Ahmed request packs") from exc

    if not isinstance(pack, dict):
        raise RequestPackError(["$: request pack must be a JSON object"])

    validator = Draft202012Validator(load_schema(schema_path))
    issues = [
        _format_jsonschema_error(error)
        for error in sorted(
            validator.iter_errors(pack),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    issues.extend(_scan_secret_keys(pack))
    if issues:
        raise RequestPackError(issues)

    context = pack["business_context"]
    primary = context.get("primary_object")
    if primary:
        issues.extend(_validate_object_reference(primary, "business_context.primary_object"))
    for index, reference in enumerate(context.get("related_objects", [])):
        issues.extend(_validate_object_reference(reference, f"business_context.related_objects[{index}]"))
    for index, operation in enumerate(pack.get("proposed_operations", [])):
        issues.extend(_validate_object_reference(operation["target"], f"proposed_operations[{index}].target"))
    if issues:
        raise RequestPackError(issues)

    gaps: list[str] = []
    status = context["context_status"]
    if status == "exact" and primary is None:
        gaps.append("business_context.primary_object")
    if status == "unresolved" and not context.get("unresolved_reason"):
        gaps.append("business_context.unresolved_reason")

    preparation = pack["preparation"]
    if preparation["research_performed"]:
        if not preparation.get("research_summary") or not preparation.get("sources"):
            gaps.append("preparation.research")
    elif not preparation.get("no_research_reason"):
        gaps.append("preparation.research_reason")

    if pack["decision_required"]:
        if not preparation.get("options"):
            gaps.append("preparation.options")
        recommendation = preparation["recommendation"]
        if not recommendation.get("summary") or not recommendation.get("rationale"):
            gaps.append("preparation.recommendation")

    if not preparation.get("work_completed") and not preparation.get("no_work_reason"):
        gaps.append("preparation.work")

    unique_gaps = list(dict.fromkeys(gaps))
    return PackAssessment(
        preparation_gaps=unique_gaps,
        questions=[QUESTION_BY_GAP[gap] for gap in unique_gaps if gap in QUESTION_BY_GAP],
    )


def normalize_request_pack(
    pack: dict[str, Any],
    *,
    requester_id: str,
    requester_name: str,
    source: str,
    source_message_id: str,
    assessment: PackAssessment,
) -> dict[str, Any]:
    impact = pack["impact"]
    preparation = pack["preparation"]
    context = pack["business_context"]
    recommendation = preparation["recommendation"].get("summary") or ""
    primary = context.get("primary_object")

    return {
        "source": source,
        "source_message_id": source_message_id,
        "requester_id": requester_id,
        "requester_name": requester_name,
        "subject": pack["subject"],
        "request_type": pack["request_type"],
        "decision_required": pack["decision_required"],
        "requested_decision": pack["requested_decision"],
        "recommendation": recommendation,
        "deadline_at": impact.get("deadline_at"),
        "consequence_2h": impact.get("consequence_2h"),
        "consequence_tomorrow": impact.get("consequence_tomorrow"),
        "consequence_level": impact["consequence_level"],
        "people_blocked": impact["people_blocked"],
        "amount_mad": impact.get("amount_mad"),
        "irreversible": impact["irreversible"],
        "human_safety_risk": impact["human_safety_risk"],
        "serious_legal_risk": impact["serious_legal_risk"],
        "major_client_crisis": impact["major_client_crisis"],
        "operation_blocked": impact["operation_blocked"],
        "urgency_claimed": bool(impact.get("deadline_at") or impact["operation_blocked"]),
        "requires_odoo_workflow": bool(
            (primary and primary.get("system") == "odoo")
            or any(item["target"].get("system") == "odoo" for item in pack["proposed_operations"])
        ),
        "odoo_reference": (
            f"{primary.get('model')}:{primary.get('record_id')}" if primary and primary.get("system") == "odoo" else ""
        ),
        "prepared_request": True,
        "preparation_gaps": assessment.preparation_gaps,
        "preparation_questions": assessment.questions,
        "business_context_status": context["context_status"],
        "research_summary": preparation.get("research_summary") or preparation.get("no_research_reason") or "",
        "solution_options": preparation.get("options", []),
        "work_completed_summary": preparation.get("work_completed") or preparation.get("no_work_reason") or "",
        "request_pack": pack,
    }


def object_references(pack: dict[str, Any]) -> list[dict[str, Any]]:
    context = pack["business_context"]
    references: list[dict[str, Any]] = []
    if context.get("primary_object"):
        references.append({"role": "primary", **context["primary_object"]})
    references.extend({"role": "related", **item} for item in context.get("related_objects", []))
    references.extend(
        {
            "role": "proposed_target",
            "operation_id": operation["operation_id"],
            **operation["target"],
        }
        for operation in pack.get("proposed_operations", [])
    )
    return references
