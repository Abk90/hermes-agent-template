from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - local environment without optional runtime dependency
    yaml = None


@unittest.skipIf(yaml is None, "PyYAML is installed by the Railway image")
class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        from executive_os.bootstrap import bootstrap

        self.bootstrap = bootstrap
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.home = self.root / "home"
        for name in ("executive-dispatch", "odoo-approval-review", "omnifocus-executive"):
            path = self.app / "skills" / name
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        self.home.mkdir()
        (self.home / "config.yaml").write_text(
            "model:\n  provider: openai-codex\nmcp_servers:\n  odoo:\n    url: http://odoo\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_bootstrap_preserves_config_and_is_idempotent(self) -> None:
        first = self.bootstrap(self.app, self.home)
        second = self.bootstrap(self.app, self.home)
        config = yaml.safe_load((self.home / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual("installed", first["mcp"])
        self.assertEqual("installed", second["mcp"])
        self.assertEqual("openai-codex", config["model"]["provider"])
        self.assertEqual("http://odoo", config["mcp_servers"]["odoo"]["url"])
        self.assertEqual(
            [
                "triage_request",
                "list_executive_queue",
                "why_request",
                "transition_request",
                "connector_status",
            ],
            config["mcp_servers"]["executive_os"]["tools"]["include"],
        )
        self.assertTrue((self.home / "config.yaml.pre-executive-os.bak").exists())

    def test_user_modified_skill_is_preserved(self) -> None:
        self.bootstrap(self.app, self.home)
        target = self.home / "skills" / "executive-dispatch" / "SKILL.md"
        target.write_text("# local change\n", encoding="utf-8")
        result = self.bootstrap(self.app, self.home)
        self.assertEqual("preserved-local-change", result["skills"]["executive-dispatch"])
        self.assertEqual("# local change\n", target.read_text(encoding="utf-8"))

    def test_user_modified_mcp_entry_is_preserved(self) -> None:
        self.bootstrap(self.app, self.home)
        config_path = self.home / "config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["mcp_servers"]["executive_os"]["timeout"] = 999
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        result = self.bootstrap(self.app, self.home)
        reread = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual("preserved-local-change", result["mcp"])
        self.assertEqual(999, reread["mcp_servers"]["executive_os"]["timeout"])

    def test_unmanaged_existing_entry_is_preserved(self) -> None:
        config_path = self.home / "config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        config["mcp_servers"]["executive_os"] = {"command": "custom"}
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        result = self.bootstrap(self.app, self.home)
        reread = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.assertEqual("preserved-unmanaged", result["mcp"])
        self.assertEqual("custom", reread["mcp_servers"]["executive_os"]["command"])
        state = self.home / "executive-os" / "bootstrap-state.json"
        self.assertFalse(state.exists())
