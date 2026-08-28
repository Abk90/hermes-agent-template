#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {
    "schema_version",
    "submission_id",
    "subject",
    "request_type",
    "decision_required",
    "requested_decision",
    "business_context",
    "impact",
    "preparation",
    "evidence",
    "proposed_operations",
    "sensitivity",
}


def load_pack(path: str) -> dict[str, Any]:
    parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("Le request pack doit être un objet JSON.")
    return parsed


def basic_validate(pack: dict[str, Any]) -> list[str]:
    issues = [f"Champ manquant : {name}" for name in sorted(REQUIRED_TOP_LEVEL - pack.keys())]
    if pack.get("schema_version") != "1.0":
        issues.append("schema_version doit valoir 1.0")
    context = pack.get("business_context")
    if isinstance(context, dict) and context.get("context_status") == "exact":
        primary = context.get("primary_object")
        if not isinstance(primary, dict):
            issues.append("Un contexte exact exige primary_object")
        elif primary.get("system") == "odoo":
            if not str(primary.get("record_id") or "").isdigit():
                issues.append("Un objet Odoo exact exige un record_id numérique")
            if not primary.get("model") or not primary.get("company_id"):
                issues.append("Un objet Odoo exact exige model et company_id")
    references = []
    if isinstance(context, dict):
        if isinstance(context.get("primary_object"), dict):
            references.append(context["primary_object"])
        references.extend(item for item in context.get("related_objects", []) if isinstance(item, dict))
    references.extend(
        operation["target"]
        for operation in pack.get("proposed_operations", [])
        if isinstance(operation, dict) and isinstance(operation.get("target"), dict)
    )
    for index, reference in enumerate(references):
        if reference.get("system") == "odoo" and not str(
            reference.get("verification_receipt") or ""
        ).startswith("v1."):
            issues.append(f"La référence Odoo {index + 1} exige le reçu retourné par odoo-verify")
    return issues


def request_json(method: str, path: str, *, body: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Any:
    api_url = os.environ.get("BUREAU_AHMED_API_URL", "").rstrip("/")
    token = os.environ.get("BUREAU_AHMED_DEVICE_TOKEN", "")
    if not api_url:
        raise RuntimeError("BUREAU_AHMED_API_URL n'est pas configurée.")
    if not token:
        raise RuntimeError("BUREAU_AHMED_DEVICE_TOKEN n'est pas configuré.")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    request = urllib.request.Request(f"{api_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bureau Ahmed a refusé la requête (HTTP {exc.code}) : {payload[:2000]}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="submit_request.py")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("pack")
    submit = sub.add_parser("submit")
    submit.add_argument("pack")
    submit.add_argument("--idempotency-key")
    status = sub.add_parser("status")
    status.add_argument("request_id")
    revise = sub.add_parser("revise")
    revise.add_argument("request_id")
    revise.add_argument("pack")
    message = sub.add_parser("message")
    message.add_argument("request_id")
    message.add_argument("body")
    odoo_search = sub.add_parser("odoo-search")
    odoo_search.add_argument("model", choices=["project.project", "project.task"])
    odoo_search.add_argument("query")
    odoo_search.add_argument("--limit", type=int, default=8)
    odoo_verify = sub.add_parser("odoo-verify")
    odoo_verify.add_argument(
        "model",
        choices=["project.project", "project.task", "documents.document", "approval.request"],
    )
    odoo_verify.add_argument("record_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in {"validate", "submit", "revise"}:
        pack = load_pack(args.pack)
        issues = basic_validate(pack)
        if issues:
            print(json.dumps({"valid": False, "issues": issues}, ensure_ascii=False, indent=2))
            return 2
        if args.command == "validate":
            print(json.dumps({"valid": True, "note": "Validation serveur complète lors de la soumission."}, ensure_ascii=False))
            return 0
        if args.command == "submit":
            result = request_json(
                "POST",
                "/v1/requests",
                body=pack,
                idempotency_key=args.idempotency_key or str(pack["submission_id"]),
            )
        else:
            result = request_json("PUT", f"/v1/requests/{args.request_id}", body=pack)
    elif args.command == "status":
        result = request_json("GET", f"/v1/requests/{args.request_id}")
    elif args.command == "message":
        result = request_json(
            "POST",
            f"/v1/requests/{args.request_id}/messages",
            body={"message_id": str(uuid.uuid4()), "body": args.body},
        )
    elif args.command == "odoo-search":
        result = request_json(
            "POST",
            "/v1/context/odoo/search",
            body={"model": args.model, "query": args.query, "limit": args.limit},
        )
    else:
        result = request_json(
            "POST",
            "/v1/context/odoo/verify",
            body={"model": args.model, "record_id": args.record_id},
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
