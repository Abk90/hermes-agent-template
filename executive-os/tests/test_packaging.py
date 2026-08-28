from __future__ import annotations

import unittest
from pathlib import Path


class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[2]

    def test_managed_skills_are_in_docker_context(self) -> None:
        dockerignore = (self.repo / ".dockerignore").read_text(encoding="utf-8").splitlines()
        self.assertNotIn("skills/", dockerignore)
        self.assertNotIn("executive-os/skills/", dockerignore)
        for name in ("executive-dispatch", "odoo-approval-review", "omnifocus-executive"):
            self.assertTrue((self.repo / "executive-os" / "skills" / name / "SKILL.md").is_file())

    def test_dockerfile_copies_executive_os(self) -> None:
        dockerfile = (self.repo / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY executive-os/ /app/executive-os/", dockerfile)
        self.assertIn("COPY start-internal-intake.sh /app/start-internal-intake.sh", dockerfile)

    def test_internal_intake_artifacts_are_packaged(self) -> None:
        root = self.repo / "executive-os"
        self.assertTrue((root / "schemas" / "request-pack-v1.schema.json").is_file())
        self.assertTrue(
            (root / "portable-skills" / "bureau-ahmed-request" / "SKILL.md").is_file()
        )
        self.assertTrue((root / "profiles" / "internal-intake" / "SOUL.md").is_file())
        self.assertTrue((root / "scripts" / "install_portable_skill.py").is_file())

    def test_gitignore_does_not_hide_nested_skills(self) -> None:
        gitignore = (self.repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertNotIn("skills/", gitignore)
        self.assertIn("/skills/", gitignore)
