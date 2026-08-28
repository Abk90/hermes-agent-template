from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from executive_os.identity import DeviceIdentity, IdentityRegistry, token_sha256  # noqa: E402
from executive_os.intake import IntakePermissionError, InternalIntakeService  # noqa: E402
from executive_os.ledger import Ledger  # noqa: E402
from executive_os.odoo_context import ContextReceiptSigner, ContextVerificationError  # noqa: E402
from helpers import sample_pack, verified_sample_pack  # noqa: E402


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name) / "ledger.sqlite3")
        self.identity = DeviceIdentity(
            credential_id="cred-1",
            requester_id="employee-1",
            display_name="Employé Pilote",
            device_id="device-1",
            token_sha256=token_sha256("pilot-token"),
            telegram_user_id="123456",
            odoo_company_ids=("1",),
        )
        self.other = DeviceIdentity(
            credential_id="cred-2",
            requester_id="employee-2",
            display_name="Autre Employé",
            device_id="device-2",
            token_sha256=token_sha256("other-token"),
            telegram_user_id="654321",
            odoo_company_ids=("1",),
        )
        self.registry = IdentityRegistry([self.identity, self.other])
        self.signer = ContextReceiptSigner("test-signing-key-that-is-longer-than-32-bytes")
        self.service = InternalIntakeService(
            ledger=self.ledger,
            registry=self.registry,
            bot_username="BureauAhmedPilotBot",
            context_signer=self.signer,
        )

    def pack(self):
        return verified_sample_pack(self.signer, self.identity)

    def tearDown(self):
        self.temp.cleanup()

    def test_submit_indexes_exact_links_and_proposals_without_writes(self):
        result = self.service.submit_pack(
            self.pack(),
            identity=self.identity,
            idempotency_key="submission-1",
            source="api",
            source_message_id="pilot-1",
        )
        self.assertTrue(result["created"])
        self.assertTrue(result["preparation"]["ready"])
        self.assertEqual(0, result["writes_executed"])
        self.assertIn("https://t.me/BureauAhmedPilotBot?start=", result["telegram"]["deep_link"])
        explained = self.ledger.explain(result["request_id"])
        self.assertEqual(1, len(explained["operation_proposals"]))
        self.assertEqual("PROPOSED", explained["operation_proposals"][0]["status"])
        self.assertGreaterEqual(len(explained["links"]), 2)

    def test_idempotent_retry_does_not_duplicate(self):
        pack = self.pack()
        first = self.service.submit_pack(
            pack, identity=self.identity, idempotency_key="same", source="api", source_message_id="1"
        )
        second = self.service.submit_pack(
            pack, identity=self.identity, idempotency_key="same", source="api", source_message_id="1"
        )
        self.assertEqual(first["request_id"], second["request_id"])
        self.assertFalse(second["created"])
        explained = self.ledger.explain(first["request_id"])
        self.assertEqual(1, len(explained["operation_proposals"]))
        self.assertEqual(1, len(explained["revisions"]))

    def test_idempotency_conflict_is_rejected(self):
        self.service.submit_pack(
            self.pack(), identity=self.identity, idempotency_key="same", source="api", source_message_id="1"
        )
        changed = self.pack()
        changed["subject"] = "Contenu différent"
        with self.assertRaises(ValueError):
            self.service.submit_pack(
                changed, identity=self.identity, idempotency_key="same", source="api", source_message_id="1"
            )

    def test_other_employee_cannot_read_request(self):
        result = self.service.submit_pack(
            self.pack(), identity=self.identity, idempotency_key="private", source="api", source_message_id="1"
        )
        with self.assertRaises(IntakePermissionError):
            self.service.get_request(result["request_id"], identity=self.other)

    def test_telegram_binding_requires_exact_preverified_id(self):
        result = self.service.submit_pack(
            self.pack(), identity=self.identity, idempotency_key="bind", source="api", source_message_id="1"
        )
        token = result["telegram"]["deep_link"].split("start=", 1)[1]
        with self.assertRaises(IntakePermissionError):
            self.service.bind_telegram_start(
                start_token=token,
                telegram_user_id="not-allowlisted",
                chat_id="100",
            )
        bound = self.service.bind_telegram_start(
            start_token=token,
            telegram_user_id="123456",
            chat_id="100",
        )
        self.assertEqual(self.identity.requester_id, bound["requester_id"])
        self.assertEqual(0, bound["writes_executed"])

    def test_allowlisted_telegram_identity_can_bind_only_its_private_chat(self):
        with self.assertRaises(IntakePermissionError):
            self.service.bind_allowlisted_private_chat(
                telegram_user_id="not-allowlisted",
                chat_id="not-allowlisted",
            )
        with self.assertRaisesRegex(IntakePermissionError, "private chat"):
            self.service.bind_allowlisted_private_chat(
                telegram_user_id="123456",
                chat_id="-100999",
            )
        bound = self.service.bind_allowlisted_private_chat(
            telegram_user_id="123456",
            chat_id="123456",
        )
        self.assertEqual(self.identity.requester_id, bound["requester_id"])
        self.assertEqual("123456", bound["chat_id"])
        self.assertEqual(0, bound["writes_executed"])

        rebound = self.service.bind_allowlisted_private_chat(
            telegram_user_id="123456",
            chat_id="123456",
        )
        self.assertEqual(self.identity.requester_id, rebound["requester_id"])

    def test_revision_closes_preparation_gaps(self):
        incomplete = self.pack()
        incomplete["business_context"]["context_status"] = "unresolved"
        incomplete["business_context"]["primary_object"] = None
        incomplete["business_context"]["unresolved_reason"] = None
        submitted = self.service.submit_pack(
            incomplete, identity=self.identity, idempotency_key="revise", source="api", source_message_id="1"
        )
        self.assertFalse(submitted["preparation"]["ready"])
        revised = self.service.revise_pack(submitted["request_id"], self.pack(), identity=self.identity)
        self.assertTrue(revised["preparation"]["ready"])
        explained = self.ledger.explain(submitted["request_id"])
        self.assertEqual(2, len(explained["revisions"]))

    def test_unverified_or_tampered_odoo_reference_is_rejected(self):
        unsigned = sample_pack()
        with self.assertRaises(ContextVerificationError):
            self.service.submit_pack(
                unsigned,
                identity=self.identity,
                idempotency_key="unsigned",
                source="api",
                source_message_id="1",
            )
        tampered = self.pack()
        tampered["business_context"]["primary_object"]["record_id"] = "999"
        with self.assertRaises(ContextVerificationError):
            self.service.submit_pack(
                tampered,
                identity=self.identity,
                idempotency_key="tampered",
                source="api",
                source_message_id="2",
            )

    def test_revision_cannot_silently_mutate_an_existing_proposal(self):
        submitted = self.service.submit_pack(
            self.pack(),
            identity=self.identity,
            idempotency_key="immutable-proposal",
            source="api",
            source_message_id="1",
        )
        changed = self.pack()
        changed["proposed_operations"][0]["payload"]["summary"] = "Contenu changé"
        with self.assertRaisesRegex(ValueError, "use a new operation_id"):
            self.service.revise_pack(submitted["request_id"], changed, identity=self.identity)
        explained = self.ledger.explain(submitted["request_id"])
        self.assertEqual(1, len(explained["revisions"]))
        self.assertEqual(1, len(explained["operation_proposals"]))


if __name__ == "__main__":
    unittest.main()
