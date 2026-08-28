from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml


MANAGED_SKILLS = (
    "executive-dispatch",
    "odoo-approval-review",
    "omnifocus-executive",
)
MCP_TOOLS = (
    "triage_request",
    "list_executive_queue",
    "why_request",
    "transition_request",
    "connector_status",
)
MARKER_NAME = ".belkora-executive-os.sha256"


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_text(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def install_managed_skill(source: Path, destination: Path) -> str:
    source_file = source / "SKILL.md"
    destination_file = destination / "SKILL.md"
    marker = destination / MARKER_NAME
    source_digest = _digest(source_file)

    if destination_file.exists():
        if not marker.exists():
            return "preserved-unmanaged"
        installed_digest = marker.read_text(encoding="utf-8").strip()
        if _digest(destination_file) != installed_digest:
            return "preserved-local-change"

    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    _atomic_text(destination_file, source_file.read_text(encoding="utf-8"), 0o600)
    _atomic_text(marker, source_digest + "\n", 0o600)
    return "installed"


def managed_mcp_entry() -> dict[str, Any]:
    return {
        "command": "/usr/local/bin/python",
        "args": ["-m", "executive_os.mcp_server"],
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
            "include": list(MCP_TOOLS),
            "resources": False,
            "prompts": False,
        },
    }


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def install_mcp_config(config_path: Path, state_path: Path) -> str:
    loaded: dict[str, Any] = {}
    if config_path.exists():
        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if parsed is not None and not isinstance(parsed, dict):
            raise ValueError("Hermes config.yaml root must be a mapping")
        loaded = parsed or {}

    servers = loaded.get("mcp_servers")
    if servers is None:
        servers = {}
        loaded["mcp_servers"] = servers
    if not isinstance(servers, dict):
        raise ValueError("Hermes mcp_servers must be a mapping")

    state: dict[str, Any] = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    existing = servers.get("executive_os")
    previous_digest = state.get("mcp_entry_digest")
    if existing is not None:
        if not previous_digest:
            return "preserved-unmanaged"
        if _canonical_digest(existing) != previous_digest:
            return "preserved-local-change"

    entry = managed_mcp_entry()
    servers["executive_os"] = entry

    if config_path.exists():
        backup = config_path.with_name("config.yaml.pre-executive-os.bak")
        if not backup.exists():
            shutil.copy2(config_path, backup)
            os.chmod(backup, 0o600)

    rendered = yaml.safe_dump(loaded, allow_unicode=True, sort_keys=False)
    _atomic_text(config_path, rendered, 0o600)
    state["mcp_entry_digest"] = _canonical_digest(entry)
    _atomic_text(state_path, json.dumps(state, indent=2, sort_keys=True) + "\n", 0o600)
    return "installed"


def bootstrap(app_root: Path, hermes_home: Path) -> dict[str, Any]:
    private_root = hermes_home / "executive-os"
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_root, 0o700)

    skill_results: dict[str, str] = {}
    for name in MANAGED_SKILLS:
        skill_results[name] = install_managed_skill(
            app_root / "skills" / name,
            hermes_home / "skills" / name,
        )

    config_result = install_mcp_config(
        hermes_home / "config.yaml",
        private_root / "bootstrap-state.json",
    )
    return {"mcp": config_result, "skills": skill_results}


def main() -> int:
    if not _enabled(os.environ.get("EXECUTIVE_OS_ENABLED")):
        print("Executive OS bootstrap disabled")
        return 0

    app_root = Path(os.environ.get("EXECUTIVE_OS_ROOT", "/app/executive-os"))
    hermes_home = Path(os.environ.get("HERMES_HOME", "/data/.hermes"))
    result = bootstrap(app_root, hermes_home)
    print(json.dumps(result, sort_keys=True))

    if result["mcp"] != "installed":
        print(
            "Executive OS MCP entry was preserved because it is unmanaged or locally modified",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
