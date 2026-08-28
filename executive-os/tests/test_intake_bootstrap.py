from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - Railway dependency
    yaml = None


@unittest.skipIf(yaml is None, "PyYAML is installed by the Railway image")
class IntakeBootstrapTests(unittest.TestCase):
    def setUp(self):
        from executive_os.intake_bootstrap import bootstrap_intake

        self.bootstrap = bootstrap_intake
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.home = self.root / "home"
        (self.app / "skills" / "internal-request-triage").mkdir(parents=True)
        (self.app / "skills" / "internal-request-triage" / "SKILL.md").write_text(
            "# intake\n", encoding="utf-8"
        )
        (self.app / "profiles" / "internal-intake").mkdir(parents=True)
        (self.app / "profiles" / "internal-intake" / "SOUL.md").write_text(
            "# Bureau Ahmed\n", encoding="utf-8"
        )
        self.home.mkdir()
        (self.home / "config.yaml").write_text("model:\n  provider: test\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_bootstrap_installs_only_intake_toolset(self):
        configured = {
            "INTERNAL_INTAKE_INFERENCE_PROVIDER": "deepseek",
            "INTERNAL_INTAKE_INFERENCE_MODEL": "deepseek-v4-pro",
            "TELEGRAM_ALLOWED_USERS": "123456,654321",
            "INTERNAL_INTAKE_TELEGRAM_ADMIN_USERS": "123456",
        }
        with patch.dict("os.environ", configured, clear=False):
            first = self.bootstrap(self.app, self.home)
            second = self.bootstrap(self.app, self.home)
        self.assertEqual(first, {"mcp": "installed", "skill": "installed", "soul": "installed"})
        self.assertEqual(second, first)
        config = yaml.safe_load((self.home / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual("deepseek", config["model"]["provider"])
        self.assertEqual("deepseek-v4-pro", config["model"]["default"])
        telegram_extra = config["gateway"]["platforms"]["telegram"]["extra"]
        self.assertEqual(["123456", "654321"], telegram_extra["allow_from"])
        self.assertEqual(["123456"], telegram_extra["allow_admin_from"])
        self.assertEqual(["start"], telegram_extra["user_allowed_commands"])
        self.assertEqual([], telegram_extra["group_allow_from"])
        self.assertEqual([], telegram_extra["group_user_allowed_commands"])
        self.assertEqual(["mcp-internal-intake"], config["toolsets"])
        self.assertEqual("off", config["browser"]["backend"])
        self.assertEqual(
            [
                "bind_allowlisted_private_chat",
                "search_odoo_context",
                "verify_odoo_context",
                "bind_telegram_start",
                "submit_telegram_request",
                "append_intake_message",
                "get_intake_request",
                "list_my_intake_requests",
            ],
            config["mcp_servers"]["internal-intake"]["tools"]["include"],
        )

    def test_dedicated_service_can_adopt_seeded_unmanaged_soul_with_backup(self):
        soul = self.home / "SOUL.md"
        soul.write_text("# Seeded upstream soul\n", encoding="utf-8")
        configured = {
            "INTERNAL_INTAKE_ADOPT_UNMANAGED_SOUL": "true",
            "TELEGRAM_ALLOWED_USERS": "123456",
            "INTERNAL_INTAKE_TELEGRAM_ADMIN_USERS": "123456",
        }
        with patch.dict("os.environ", configured, clear=False):
            result = self.bootstrap(self.app, self.home)
        self.assertEqual("installed", result["soul"])
        self.assertEqual("# Bureau Ahmed\n", soul.read_text(encoding="utf-8"))
        self.assertEqual(
            "# Seeded upstream soul\n",
            (self.home / "SOUL.md.pre-internal-intake.bak").read_text(encoding="utf-8"),
        )

    def test_explicit_reconcile_updates_managed_config_and_preserves_other_keys(self):
        initial = {
            "INTERNAL_INTAKE_INFERENCE_PROVIDER": "deepseek",
            "INTERNAL_INTAKE_INFERENCE_MODEL": "deepseek-v4-pro",
            "TELEGRAM_ALLOWED_USERS": "123456",
            "INTERNAL_INTAKE_TELEGRAM_ADMIN_USERS": "123456",
        }
        with patch.dict("os.environ", initial, clear=False):
            first = self.bootstrap(self.app, self.home)
        self.assertEqual("installed", first["mcp"])

        config_path = self.home / "config.yaml"
        changed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        changed["display"] = {"theme": "dark"}
        config_path.write_text(
            yaml.safe_dump(changed, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        migrated = {
            "INTERNAL_INTAKE_INFERENCE_PROVIDER": "anthropic",
            "INTERNAL_INTAKE_INFERENCE_MODEL": "claude-sonnet-4-6",
            "INTERNAL_INTAKE_RECONCILE_MANAGED_CONFIG": "true",
            "TELEGRAM_ALLOWED_USERS": "123456",
            "INTERNAL_INTAKE_TELEGRAM_ADMIN_USERS": "123456",
        }
        with patch.dict("os.environ", migrated, clear=False):
            result = self.bootstrap(self.app, self.home)

        self.assertEqual("installed", result["mcp"])
        rendered = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual("anthropic", rendered["model"]["provider"])
        self.assertEqual("claude-sonnet-4-6", rendered["model"]["default"])
        self.assertEqual({"theme": "dark"}, rendered["display"])
        self.assertTrue(
            (self.home / "config.yaml.pre-internal-intake-reconcile.bak").exists()
        )


if __name__ == "__main__":
    unittest.main()
