from __future__ import annotations

import tempfile
import unittest
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
        first = self.bootstrap(self.app, self.home)
        second = self.bootstrap(self.app, self.home)
        self.assertEqual(first, {"mcp": "installed", "skill": "installed", "soul": "installed"})
        self.assertEqual(second, first)
        config = yaml.safe_load((self.home / "config.yaml").read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
