from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from executive_os.ledger import Ledger  # noqa: E402
from executive_os.models import Priority, RequestStatus, Route, TriageDecision  # noqa: E402


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tempdir.name) / "ledger.sqlite3")
        self.payload = {
            "source": "telegram",
            "source_message_id": "42",
            "requester_id": "user-1",
            "subject": "Decision test",
        }
        self.decision = TriageDecision(
            priority=Priority.P2,
            route=Route.EXECUTIVE_QUEUE,
            confidence="high",
            justification=["Test"],
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_idempotency_returns_same_request_without_duplicate_event(self):
        first, created_first = self.ledger.create_or_get(
            payload=self.payload,
            decision=self.decision,
            idempotency_key="telegram:42",
            actor="tester",
        )
        second, created_second = self.ledger.create_or_get(
            payload=self.payload,
            decision=self.decision,
            idempotency_key="telegram:42",
            actor="tester",
        )
        self.assertTrue(created_first)
        self.assertFalse(created_second)
        self.assertEqual(first["request_id"], second["request_id"])
        explained = self.ledger.explain(first["request_id"])
        self.assertEqual(len(explained["events"]), 1)

    def test_status_transition_is_audited(self):
        record, _ = self.ledger.create_or_get(
            payload=self.payload,
            decision=self.decision,
            idempotency_key="telegram:43",
            actor="tester",
        )
        updated = self.ledger.transition(
            record["request_id"],
            RequestStatus.PENDING,
            actor="ahmed",
            justification="Decision en cours",
        )
        self.assertEqual(updated["status"], "PENDING")
        self.assertEqual(len(self.ledger.explain(record["request_id"])["events"]), 2)

    def test_invalid_transition_is_refused(self):
        record, _ = self.ledger.create_or_get(
            payload=self.payload,
            decision=self.decision,
            idempotency_key="telegram:44",
            actor="tester",
        )
        with self.assertRaises(ValueError):
            self.ledger.transition(
                record["request_id"],
                RequestStatus.RETRYING,
                actor="tester",
                justification="Invalid",
            )

    def test_events_are_append_only_at_database_level(self):
        record, _ = self.ledger.create_or_get(
            payload=self.payload,
            decision=self.decision,
            idempotency_key="telegram:45",
            actor="tester",
        )
        with self.ledger.connect() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE events SET result = 'CHANGED' WHERE request_id = ?",
                    (record["request_id"],),
                )

    def test_failed_connector_does_not_erase_last_success(self):
        first = self.ledger.record_connector_state("odoo", "OK", success=True, cursor="a")
        second = self.ledger.record_connector_state(
            "odoo", "FAILED", success=False, error="timeout"
        )
        self.assertEqual(first["last_success_at"], second["last_success_at"])
        self.assertEqual(second["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
