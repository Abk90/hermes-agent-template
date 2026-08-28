from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from .bootstrap import _atomic_text, _canonical_digest, install_managed_skill


INTAKE_MCP_TOOLS = (
    "bind_allowlisted_private_chat",
    "search_odoo_context",
    "verify_odoo_context",
    "bind_telegram_start",
    "submit_telegram_request",
    "append_intake_message",
    "get_intake_request",
    "list_my_intake_requests",
)


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def managed_intake_entry() -> dict[str, Any]:
    return {
        "command": "/usr/local/bin/python",
        "args": ["-m", "executive_os.intake_mcp_server"],
        "env": {
            "PYTHONPATH": "/app/executive-os/src",
            "EXECUTIVE_OS_CONFIG": "/app/executive-os/config/executive-os.toml",
            "EXECUTIVE_OS_DB": "/data/.hermes/executive-os/ledger.sqlite3",
            "HOME": "/data",
            "HERMES_HOME": "/data/.hermes",
            "LANG": "C.UTF-8",
        },
        "enabled": True,
        "timeout": 60,
        "connect_timeout": 20,
        "idle_timeout_seconds": 600,
        "supports_parallel_tool_calls": False,
        "tools": {
            "include": list(INTAKE_MCP_TOOLS),
            "resources": False,
            "prompts": False,
        },
    }


def _render_managed_config(existing: dict[str, Any]) -> dict[str, Any]:
    rendered = dict(existing)
    servers = dict(rendered.get("mcp_servers") or {})
    servers["internal-intake"] = managed_intake_entry()
    rendered["mcp_servers"] = servers
    rendered["toolsets"] = ["mcp-internal-intake"]
    terminal = dict(rendered.get("terminal") or {})
    terminal["home_mode"] = "profile"
    rendered["terminal"] = terminal
    browser = dict(rendered.get("browser") or {})
    browser["backend"] = "off"
    rendered["browser"] = browser
    return rendered


def bootstrap_intake(app_root: Path, hermes_home: Path) -> dict[str, Any]:
    private_root = hermes_home / "executive-os"
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_root, 0o700)
    state_path = private_root / "intake-bootstrap-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    skill_result = install_managed_skill(
        app_root / "skills" / "internal-request-triage",
        hermes_home / "skills" / "internal-request-triage",
    )
    soul_source = app_root / "profiles" / "internal-intake" / "SOUL.md"
    soul_target = hermes_home / "SOUL.md"
    soul_digest = hashlib.sha256(soul_source.read_bytes()).hexdigest()
    previous_soul_digest = state.get("soul_digest")
    soul_result = "installed"
    if soul_target.exists() and previous_soul_digest:
        current_digest = hashlib.sha256(soul_target.read_bytes()).hexdigest()
        if current_digest != previous_soul_digest:
            soul_result = "preserved-local-change"
    elif soul_target.exists() and not previous_soul_digest:
        soul_result = "preserved-unmanaged"
    if soul_result == "installed":
        _atomic_text(soul_target, soul_source.read_text(encoding="utf-8"), 0o600)
        state["soul_digest"] = soul_digest

    config_path = hermes_home / "config.yaml"
    parsed = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if parsed is not None and not isinstance(parsed, dict):
        raise ValueError("Hermes config.yaml root must be a mapping")
    current = parsed or {}
    previous_config_digest = state.get("config_digest")
    if previous_config_digest and _canonical_digest(current) != previous_config_digest:
        config_result = "preserved-local-change"
    elif not previous_config_digest and current.get("mcp_servers", {}).get("internal-intake"):
        config_result = "preserved-unmanaged"
    else:
        managed = _render_managed_config(current)
        if config_path.exists():
            backup = config_path.with_name("config.yaml.pre-internal-intake.bak")
            if not backup.exists():
                shutil.copy2(config_path, backup)
                os.chmod(backup, 0o600)
        _atomic_text(config_path, yaml.safe_dump(managed, allow_unicode=True, sort_keys=False), 0o600)
        state["config_digest"] = _canonical_digest(managed)
        config_result = "installed"

    _atomic_text(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n", 0o600)
    return {"mcp": config_result, "skill": skill_result, "soul": soul_result}


def main() -> int:
    if not _enabled(os.environ.get("INTERNAL_INTAKE_ENABLED")):
        print("Internal intake bootstrap disabled")
        return 0
    app_root = Path(os.environ.get("EXECUTIVE_OS_ROOT", "/app/executive-os"))
    hermes_home = Path(os.environ.get("HERMES_HOME", "/data/.hermes"))
    result = bootstrap_intake(app_root, hermes_home)
    print(json.dumps(result, sort_keys=True))
    if any(result[key] != "installed" for key in ("mcp", "skill", "soul")):
        print("Internal intake managed files were not installed cleanly", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
