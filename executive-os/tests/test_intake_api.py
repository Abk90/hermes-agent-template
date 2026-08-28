from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from starlette.testclient import TestClient
except ImportError:  # pragma: no cover - Railway dependency
    TestClient = None

from executive_os.identity import DeviceIdentity, IdentityRegistry, token_sha256  # noqa: E402
from executive_os.intake_api import IntakeAPISettings, build_app  # noqa: E402
from executive_os.ledger import Ledger  # noqa: E402
from executive_os.odoo_context import ContextReceiptSigner, OdooContextResolver  # noqa: E402
from helpers import sample_pack, verified_sample_pack  # noqa: E402


class FakeOdooClient:
    async def search_records(self, **_kwargs):
        return {"records": [{"id": 4521, "name": "Tâche pilote", "company_id": [1, "Belkora"]}]}

    async def get_record(self, **kwargs):
        return {"id": kwargs["record_id"], "name": "Tâche pilote", "company_id": [1, "Belkora"]}


@unittest.skipIf(TestClient is None, "Starlette is installed by the Railway image")
class IntakeAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        ledger = Ledger(Path(self.temp.name) / "ledger.sqlite3")
        self.identity = DeviceIdentity(
            credential_id="cred-1",
            requester_id="employee-1",
            display_name="Employé Pilote",
            device_id="device-1",
            token_sha256=token_sha256("pilot-token"),
            telegram_user_id="123456",
            odoo_company_ids=("1",),
        )
        settings = IntakeAPISettings(
            enabled=True,
            bot_username="BureauAhmedPilotBot",
            start_token_ttl_minutes=30,
            context_signing_key="test-signing-key-that-is-longer-than-32-bytes",
        )
        self.signer = ContextReceiptSigner(settings.context_signing_key)
        resolver = OdooContextResolver(FakeOdooClient(), self.signer)
        self.client = TestClient(
            build_app(
                ledger=ledger,
                registry=IdentityRegistry([self.identity]),
                settings=settings,
                odoo_resolver=resolver,
            )
        )
        self.auth = {"Authorization": "Bearer pilot-token", "Idempotency-Key": "api-test-1"}

    def tearDown(self):
        self.temp.cleanup()

    def test_health_proves_writes_are_disabled(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertFalse(response.json()["writes_enabled"])

    def test_submit_requires_authentication_and_idempotency(self):
        self.assertEqual(401, self.client.post("/v1/requests", json=sample_pack()).status_code)
        no_idempotency = self.client.post(
            "/v1/requests",
            json=sample_pack(),
            headers={"Authorization": "Bearer pilot-token"},
        )
        self.assertEqual(400, no_idempotency.status_code)

    def test_api_to_telegram_continuation(self):
        submitted = self.client.post(
            "/v1/requests",
            json=verified_sample_pack(self.signer, self.identity),
            headers=self.auth,
        )
        self.assertEqual(201, submitted.status_code)
        payload = submitted.json()
        self.assertEqual(0, payload["writes_executed"])
        self.assertIn("start=", payload["telegram"]["deep_link"])
        token = payload["telegram"]["deep_link"].split("start=", 1)[1]
        bound = self.client.app.state.intake.bind_telegram_start(
            start_token=token,
            telegram_user_id="123456",
            chat_id="100",
        )
        self.assertEqual(payload["request_id"], bound["request_id"])
        self.client.app.state.intake.append_telegram_message(
            payload["request_id"],
            telegram_user_id="123456",
            chat_id="100",
            message_id="telegram-2",
            body="Voici la précision demandée.",
        )

        reread = self.client.get(
            f"/v1/requests/{payload['request_id']}",
            headers={"Authorization": "Bearer pilot-token"},
        )
        self.assertEqual(1, len(reread.json()["messages"]))

    def test_odoo_context_endpoints_are_read_only_and_return_signed_reference(self):
        search = self.client.post(
            "/v1/context/odoo/search",
            json={"model": "project.task", "query": "pilote"},
            headers={"Authorization": "Bearer pilot-token"},
        )
        self.assertEqual(200, search.status_code)
        self.assertEqual(0, search.json()["writes_executed"])
        receipt = search.json()["results"][0]["verification_receipt"]
        self.assertTrue(receipt.startswith("v1."))

        verified = self.client.post(
            "/v1/context/odoo/verify",
            json={"model": "project.task", "record_id": "4521"},
            headers={"Authorization": "Bearer pilot-token"},
        )
        self.assertEqual(200, verified.status_code)
        self.assertEqual("4521", verified.json()["id"])
        self.assertEqual(0, verified.json()["writes_executed"])


if __name__ == "__main__":
    unittest.main()
