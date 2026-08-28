from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from executive_os.identity import IdentityError, IdentityRegistry, token_sha256  # noqa: E402


class IdentityTests(unittest.TestCase):
    def test_token_authentication_injects_server_identity(self):
        registry = IdentityRegistry.from_json(
            json.dumps(
                {
                    "credentials": [
                        {
                            "credential_id": "cred-1",
                            "requester_id": "employee-1",
                            "display_name": "Employé Pilote",
                            "device_id": "device-1",
                            "token_sha256": token_sha256("correct-token"),
                            "telegram_user_id": "123456",
                            "odoo_company_ids": [1],
                        }
                    ]
                }
            )
        )
        self.assertEqual("employee-1", registry.authenticate("correct-token").requester_id)
        self.assertIsNone(registry.authenticate("wrong-token"))
        self.assertEqual("employee-1", registry.by_telegram_user_id("123456").requester_id)
        self.assertEqual(("1",), registry.authenticate("correct-token").odoo_company_ids)

    def test_same_telegram_id_cannot_belong_to_two_people(self):
        raw = {
            "credentials": [
                {
                    "credential_id": "a",
                    "requester_id": "employee-a",
                    "display_name": "A",
                    "device_id": "device-a",
                    "token_sha256": token_sha256("token-a"),
                    "telegram_user_id": "999",
                },
                {
                    "credential_id": "b",
                    "requester_id": "employee-b",
                    "display_name": "B",
                    "device_id": "device-b",
                    "token_sha256": token_sha256("token-b"),
                    "telegram_user_id": "999",
                },
            ]
        }
        with self.assertRaises(IdentityError):
            IdentityRegistry.from_json(json.dumps(raw))

    def test_same_person_can_have_multiple_devices_with_one_consistent_telegram_identity(self):
        rows = []
        for suffix in ("a", "b"):
            rows.append(
                {
                    "credential_id": f"cred-{suffix}",
                    "requester_id": "employee-1",
                    "display_name": "Employé Pilote",
                    "device_id": f"device-{suffix}",
                    "token_sha256": token_sha256(f"token-{suffix}"),
                    "telegram_user_id": "123456",
                    "odoo_company_ids": [1],
                }
            )
        registry = IdentityRegistry.from_json(json.dumps({"credentials": rows}))
        self.assertEqual("employee-1", registry.by_telegram_user_id("123456").requester_id)


if __name__ == "__main__":
    unittest.main()
