from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from executive_os.request_pack import (  # noqa: E402
    RequestPackError,
    validate_message_body,
    validate_request_pack,
)
from helpers import sample_pack  # noqa: E402


class RequestPackTests(unittest.TestCase):
    def test_complete_sample_is_ready(self):
        assessment = validate_request_pack(sample_pack())
        self.assertEqual([], assessment.preparation_gaps)

    def test_missing_research_becomes_a_preparation_gap(self):
        pack = sample_pack()
        pack["preparation"]["research_performed"] = True
        pack["preparation"]["research_summary"] = None
        pack["preparation"]["sources"] = []
        assessment = validate_request_pack(pack)
        self.assertIn("preparation.research", assessment.preparation_gaps)

    def test_unresolved_context_is_allowed_but_must_explain_why(self):
        pack = sample_pack()
        pack["business_context"]["context_status"] = "unresolved"
        pack["business_context"]["primary_object"] = None
        pack["business_context"]["unresolved_reason"] = None
        assessment = validate_request_pack(pack)
        self.assertIn("business_context.unresolved_reason", assessment.preparation_gaps)

    def test_fuzzy_odoo_reference_is_rejected(self):
        pack = sample_pack()
        pack["business_context"]["primary_object"]["record_id"] = "tache-probable"
        with self.assertRaises(RequestPackError) as raised:
            validate_request_pack(pack)
        self.assertTrue(any("numeric Odoo ID" in issue for issue in raised.exception.issues))

    def test_secret_like_operation_payload_is_rejected(self):
        pack = sample_pack()
        pack["proposed_operations"][0]["payload"]["api_key"] = "must-not-enter-ledger"
        with self.assertRaises(RequestPackError) as raised:
            validate_request_pack(pack)
        self.assertTrue(any("secret-like" in issue for issue in raised.exception.issues))

    def test_non_proposal_business_action_is_rejected(self):
        pack = sample_pack()
        pack["proposed_operations"][0]["action"] = "approve_payment"
        with self.assertRaises(RequestPackError):
            validate_request_pack(pack)

    def test_credential_like_value_is_rejected_in_pack_or_followup(self):
        pack = sample_pack()
        pack["free_text_context"] = "Bearer abcdefghijklmnopqrstuvwxyz123456"
        with self.assertRaises(RequestPackError):
            validate_request_pack(pack)
        with self.assertRaises(ValueError):
            validate_message_body("sk-abcdefghijklmnopqrstuvwxyz123456")


if __name__ == "__main__":
    unittest.main()
