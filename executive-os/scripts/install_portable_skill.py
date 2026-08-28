#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import tempfile
from pathlib import Path


SKILL_NAME = "bureau-ahmed-request"
ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "portable-skills" / SKILL_NAME


def same_tree(left: Path, right: Path) -> bool:
    comparison = filecmp.dircmp(left, right)
    if comparison.left_only or comparison.right_only or comparison.funny_files:
        return False
    if any(not filecmp.cmp(left / name, right / name, shallow=False) for name in comparison.common_files):
        return False
    return all(same_tree(left / name, right / name) for name in comparison.common_dirs)


def destinations(target: str, project_root: str | None) -> list[Path]:
    if target == "claude-user":
        return [Path.home() / ".claude" / "skills" / SKILL_NAME]
    if target == "kimi-user":
        kimi_home = Path(os.environ.get("KIMI_CODE_HOME", Path.home() / ".kimi-code")).expanduser()
        return [kimi_home / "skills" / SKILL_NAME]
    if not project_root:
        raise ValueError("--project-root is required for a project installation")
    root = Path(project_root).expanduser().resolve()
    return [
        root / ".claude" / "skills" / SKILL_NAME,
        root / ".agents" / "skills" / SKILL_NAME,
    ]


def install(destination: Path, *, replace: bool) -> str:
    if destination.exists():
        if same_tree(SOURCE, destination):
            return "unchanged"
        if not replace:
            raise FileExistsError(f"Refusing to overwrite modified skill: {destination}")
        backup = destination.with_name(f"{destination.name}.pre-install.bak")
        if backup.exists():
            raise FileExistsError(f"Backup already exists: {backup}")
        destination.rename(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{SKILL_NAME}-", dir=destination.parent))
    try:
        shutil.copytree(SOURCE, temporary / SKILL_NAME)
        (temporary / SKILL_NAME).rename(destination)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return "installed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the portable Bureau Ahmed Agent Skill")
    parser.add_argument("target", choices=["claude-user", "kimi-user", "project"])
    parser.add_argument("--project-root")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    results = {
        str(destination): install(destination, replace=args.replace)
        for destination in destinations(args.target, args.project_root)
    }
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
