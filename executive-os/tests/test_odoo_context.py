from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from executive_os.identity import DeviceIdentity, token_sha256  # noqa: E402
from executive_os.odoo_context import (  # noqa: E402
    ContextReceiptSigner,
    ContextVerificationError,
    OdooContextError,
    OdooContextResolver,
    private_mcp_url,
)


class FakeOdooClient:
    def __init__(self):
        self.search_call = None
        self.get_call = None

    async def search_records(self, **kwargs):
        self.search_call = kwargs
        return {
            "records": [
                {
                    "id": 42,
                    "name": "Projet exact",
                    "company_id": [1, "Belkora"],
                    "write_date": "2026-08-28 10:00:00",
                    "active": True,
                    "private_field": "must-not-leak",
                },
                {"id": 77, "name": "Autre société", "company_id": [2, "Other"]},
            ]
        }

    async def get_record(self, **kwargs):
        self.get_call = kwargs
        return {
            "id": kwargs["record_id"],
            "name": "Tâche exacte",
            "company_id": [1, "Belkora"],
            "project_id": [42, "Projet exact"],
            "stage_id": [3, "En cours"],
        }


class OdooContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
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
            odoo_company_ids=("2",),
        )
        self.signer = ContextReceiptSigner("test-signing-key-that-is-longer-than-32-bytes")
        self.client = FakeOdooClient()
        self.resolver = OdooContextResolver(self.client, self.signer)

    async def test_search_is_model_field_company_and_limit_restricted(self):
        results = await self.resolver.search(
            identity=self.identity,
            model="project.project",
            query="exact",
            limit=99,
        )
        self.assertEqual(1, len(results))
        self.assertNotIn("private_field", results[0])
        self.assertEqual(10, self.client.search_call["limit"])
        self.assertEqual(
            [["company_id", "in", [1]], ["name", "ilike", "exact"]],
            self.client.search_call["domain"],
        )
        self.assertEqual(0, results[0]["writes_executed"])

    async def test_exact_record_receipt_is_bound_to_identity_and_claims(self):
        result = await self.resolver.verify(
            identity=self.identity,
            model="project.task",
            record_id="123",
        )
        reference = {
            "model": result["model"],
            "record_id": result["id"],
            "company_id": result["company_id"],
            "label": result["label"],
            "verification_receipt": result["verification_receipt"],
        }
        payload = self.signer.verify_reference(reference, identity=self.identity)
        self.assertEqual("123", payload["record_id"])
        with self.assertRaises(ContextVerificationError):
            self.signer.verify_reference(reference, identity=self.other)
        reference["label"] = "Nom modifié"
        with self.assertRaises(ContextVerificationError):
            self.signer.verify_reference(reference, identity=self.identity)

    async def test_unsearchable_model_and_public_mcp_url_are_refused(self):
        with self.assertRaises(OdooContextError):
            await self.resolver.search(
                identity=self.identity,
                model="res.partner",
                query="Ahmed",
            )
        with self.assertRaises(OdooContextError):
            private_mcp_url("https://public.example.com/mcp")
        self.assertEqual(
            "http://odoo-mcp.railway.internal:8000/mcp",
            private_mcp_url("http://odoo-mcp.railway.internal:8000/mcp"),
        )


if __name__ == "__main__":
    unittest.main()
