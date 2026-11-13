"""Tests for the agent-agnostic skill installer.

Run with:  PYTHONPATH=src python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from podcast_kg import skill_install as si  # noqa: E402


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.agent_dir = self.root / "pi-agent"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def install(self, **kwargs):
        params = dict(
            targets=["pi"],
            scope="project",
            project=str(self.project),
            agent_dir=str(self.agent_dir),
        )
        params.update(kwargs)
        return si.install(**params)

    def test_installs_skill_folder_per_target(self) -> None:
        result = self.install(targets=["claude", "codex"])
        dirs = {r["target"]: r["skill_dir"] for r in result["results"]}
        self.assertEqual(
            dirs["claude"], self.project / ".claude" / "skills" / si.SKILL_NAME
        )
        self.assertEqual(
            dirs["codex"], self.project / ".codex" / "skills" / si.SKILL_NAME
        )
        for path in dirs.values():
            self.assertTrue((path / "SKILL.md").is_file())
            self.assertTrue((path / "sop" / "SOP.md").is_file())

    def test_install_skips_python_bytecode(self) -> None:
        source = self.root / "src-skill"
        (source / "__pycache__").mkdir(parents=True)
        (source / "SKILL.md").write_text("# s", encoding="utf-8")
        (source / "bin").mkdir()
        (source / "bin" / "bootstrap.py").write_text("print(1)", encoding="utf-8")
        (source / "bin" / "__pycache__").mkdir()
        (source / "bin" / "__pycache__" / "bootstrap.cpython-312.pyc").write_bytes(b"x")
        (source / "bin" / "stray.pyc").write_bytes(b"x")

        dest = self.root / "out"
        si._copy_tree(source, dest)
        names = {p.name for p in dest.rglob("*")}
        self.assertNotIn("__pycache__", names)
        self.assertNotIn("stray.pyc", names)
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertTrue((dest / "bin" / "bootstrap.py").is_file())

    def test_pointer_block_is_idempotent_and_keeps_existing_text(self) -> None:
        agents_md = self.project / "AGENTS.md"
        agents_md.write_text("# 原有内容\n", encoding="utf-8")

        self.install(targets=["agents"])
        first = agents_md.read_text(encoding="utf-8")
        self.assertIn("# 原有内容", first)
        self.assertIn(si.BLOCK_START, first)
        self.assertIn("SKILL.md", first)

        second = self.install(targets=["agents"])
        self.assertEqual(second["results"][0]["skill_action"], "exists")
        self.assertEqual(second["results"][0]["pointers"][0]["action"], "unchanged")
        self.assertEqual(agents_md.read_text(encoding="utf-8"), first)

    def test_force_updates_skill_folder(self) -> None:
        self.install(targets=["claude"])
        stale = self.project / ".claude" / "skills" / si.SKILL_NAME / "stale.txt"
        stale.write_text("old", encoding="utf-8")

        result = self.install(targets=["claude"], force=True)
        self.assertEqual(result["results"][0]["skill_action"], "updated")
        self.assertFalse(stale.exists())
        self.assertTrue(
            (
                self.project
                / ".claude"
                / "skills"
                / si.SKILL_NAME
                / "SKILL.md"
            ).is_file()
        )

    def test_dry_run_writes_nothing(self) -> None:
        result = self.install(targets=["claude"], dry_run=True)
        self.assertEqual(result["results"][0]["skill_action"], "would-install")
        self.assertFalse((self.project / ".claude").exists())
        self.assertFalse((self.project / "CLAUDE.md").exists())

    def test_uninstall_removes_only_its_own_marked_block(self) -> None:
        agents_md = self.project / "AGENTS.md"
        agents_md.write_text("# 原有内容\n", encoding="utf-8")
        self.install(targets=["agents"])

        result = si.uninstall(
            targets=["agents"], scope="project", project=str(self.project)
        )
        self.assertEqual(result["results"][0]["skill_action"], "removed")
        self.assertFalse(
            (self.project / ".agents" / "skills" / si.SKILL_NAME).exists()
        )
        self.assertTrue(agents_md.read_text(encoding="utf-8").startswith("# 原有内容"))
        self.assertNotIn(si.BLOCK_START, agents_md.read_text(encoding="utf-8"))

    def test_user_scope_uses_home_templates(self) -> None:
        result = self.install(targets=["pi"], scope="user", dry_run=True)
        skill_dir = result["results"][0]["skill_dir"]
        self.assertEqual(skill_dir, self.agent_dir / "skills" / si.SKILL_NAME)
        pointer = result["results"][0]["pointers"][0]["file"]
        self.assertEqual(pointer, self.agent_dir / "APPEND_SYSTEM.md")

    def test_custom_skills_dir_and_instructions(self) -> None:
        skills_dir = self.root / "my-agent" / "skills"
        instructions = self.root / "my-agent" / "AGENTS.md"
        result = si.install(
            skills_dir=str(skills_dir),
            instructions=[str(instructions)],
            scope="project",
            project=str(self.project),
        )
        entry = result["results"][0]
        self.assertEqual(entry["skill_dir"], skills_dir / si.SKILL_NAME)
        self.assertTrue((skills_dir / si.SKILL_NAME / "SKILL.md").is_file())
        self.assertIn(si.BLOCK_START, instructions.read_text(encoding="utf-8"))

    def test_no_pointer_skips_instruction_files(self) -> None:
        result = self.install(targets=["claude"], pointer=False)
        self.assertEqual(result["results"][0]["pointers"], [])
        self.assertFalse((self.project / "CLAUDE.md").exists())

    def test_unknown_target_is_reported(self) -> None:
        with self.assertRaises(si.SkillInstallError):
            si.expand_targets(["nope"])

    def test_copilot_has_no_user_scope_but_project_works(self) -> None:
        result = self.install(targets=["copilot"], scope="user")
        self.assertEqual(result["results"][0]["skill_action"], "skipped")

        result = self.install(targets=["copilot"], scope="project")
        self.assertEqual(result["results"][0]["skill_action"], "installed")
        self.assertTrue(
            (
                self.project
                / ".github"
                / "skills"
                / si.SKILL_NAME
                / "SKILL.md"
            ).is_file()
        )

    def test_installed_reports_targets(self) -> None:
        self.install(targets=["claude"])
        found = si.installed(["claude", "codex"], project=str(self.project))
        self.assertIsNotNone(found["claude"]["project"])
        self.assertIsNone(found["codex"]["project"])

    @unittest.skipIf(os.name == "nt", "POSIX-only path rendering")
    def test_table_renders_without_error(self) -> None:
        self.assertIn("claude", si.target_table())


if __name__ == "__main__":
    unittest.main()
