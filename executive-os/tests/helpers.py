from __future__ import annotations

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "portable-skills" / "bureau-ahmed-request" / "examples" / "request-pack.sample.json"


def sample_pack():
    return copy.deepcopy(json.loads(SAMPLE.read_text(encoding="utf-8")))


def verified_sample_pack(signer, identity):
    pack = sample_pack()
    context = pack["business_context"]
    references = []
    if context.get("primary_object"):
        references.append(context["primary_object"])
    references.extend(context.get("related_objects", []))
    references.extend(operation["target"] for operation in pack.get("proposed_operations", []))
    for reference in references:
        if reference.get("system") != "odoo":
            continue
        reference["verification_receipt"] = signer.issue(
            identity=identity,
            model=reference["model"],
            record_id=reference["record_id"],
            company_id=reference["company_id"],
            label=reference["label"],
        )
    return pack
