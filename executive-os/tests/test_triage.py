from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from executive_os.models import Priority, Route  # noqa: E402
from executive_os.triage import classify  # noqa: E402


NOW = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)


def base_request(**updates):
    payload = {
        "source": "telegram",
        "source_message_id": "msg-1",
        "requester_id": "user-1",
        "subject": "Valider le fournisseur X",
        "requested_decision": "APPROUVER ou REFUSER",
        "recommendation": "Approuver",
        "decision_required": True,
        "consequence_level": "material",
    }
    payload.update(updates)
    return payload


class TriageTests(unittest.TestCase):
    def test_vague_urgent_supplier_is_clarified(self):
        decision = classify(
            base_request(
                urgency_claimed=True,
                request_type="supplier",
                recommendation="",
            ),
            now=NOW,
        )
        self.assertEqual(decision.priority, Priority.P2)
        self.assertEqual(decision.route, Route.CLARIFY)
        self.assertEqual(
            set(decision.missing_fields),
            {"deadline_at", "consequence_2h", "consequence_tomorrow", "amount_mad", "recommendation"},
        )
        self.assertTrue(any("urgent" in reason.lower() for reason in decision.justification))

    def test_human_safety_is_p0_and_keeps_direct_path(self):
        decision = classify(base_request(human_safety_risk=True), now=NOW)
        self.assertEqual(decision.priority, Priority.P0)
        self.assertEqual(decision.route, Route.EXECUTIVE_QUEUE)
        self.assertTrue(decision.direct_human_path)

    def test_irreversible_imminent_major_is_p0(self):
        decision = classify(
            base_request(
                irreversible=True,
                consequence_level="major",
                deadline_at=(NOW + timedelta(minutes=60)).isoformat(),
            ),
            now=NOW,
        )
        self.assertEqual(decision.priority, Priority.P0)

    def test_blocked_operation_today_is_p1(self):
        decision = classify(
            base_request(
                operation_blocked=True,
                people_blocked=4,
                deadline_at=(NOW + timedelta(hours=3)).isoformat(),
            ),
            now=NOW,
        )
        self.assertEqual(decision.priority, Priority.P1)

    def test_normal_decision_is_p2(self):
        decision = classify(base_request(), now=NOW)
        self.assertEqual(decision.priority, Priority.P2)
        self.assertEqual(decision.route, Route.EXECUTIVE_QUEUE)

    def test_information_is_archived(self):
        decision = classify(
            base_request(information_only=True, decision_required=False, requested_decision="FYI"),
            now=NOW,
        )
        self.assertEqual(decision.priority, Priority.P3)
        self.assertEqual(decision.route, Route.ARCHIVE)

    def test_idea_is_backlogged(self):
        decision = classify(
            base_request(idea_or_opportunity=True, decision_required=False, requested_decision="Aucune"),
            now=NOW,
        )
        self.assertEqual(decision.priority, Priority.P4)
        self.assertEqual(decision.route, Route.BACKLOG)

    def test_known_procedure_can_answer_without_ahmed(self):
        decision = classify(
            base_request(procedure_known=True, can_answer_safely=True),
            now=NOW,
        )
        self.assertEqual(decision.route, Route.ANSWER)

    def test_official_workflow_routes_to_odoo(self):
        decision = classify(
            base_request(requires_odoo_workflow=True, odoo_reference="PO-123"),
            now=NOW,
        )
        self.assertEqual(decision.route, Route.ODOO)

    def test_odoo_approval_is_not_duplicated_in_omnifocus(self):
        decision = classify(
            base_request(
                requires_odoo_workflow=True,
                odoo_reference="PO-123",
                ahmed_personal_action=False,
            ),
            now=NOW,
        )
        self.assertEqual(decision.route, Route.ODOO)

    def test_real_personal_action_routes_to_omnifocus(self):
        decision = classify(
            base_request(ahmed_personal_action=True, requested_decision="Appeler Naima"),
            now=NOW,
        )
        self.assertEqual(decision.route, Route.OMNIFOCUS)

    def test_other_owner_routes_to_delegation(self):
        decision = classify(
            base_request(
                responsible_owner="direction-achats",
                decision_required=False,
                requested_decision="Aucune",
            ),
            now=NOW,
        )
        self.assertEqual(decision.route, Route.DELEGATE)


if __name__ == "__main__":
    unittest.main()
