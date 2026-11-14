"""The `bin/podcast-kg.py` launcher: delegate when installed, install on first use."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LAUNCHER = REPO / "skills" / "podcast-knowledge-graph" / "bin" / "podcast-kg.py"


def fake_cli(directory: Path) -> Path:
    if os.name == "nt":
        path = directory / "fake-podcast-kg.cmd"
        path.write_text("@echo off\r\necho FAKE %*\r\n", encoding="utf-8")
    else:
        path = directory / "fake-podcast-kg"
        path.write_text('#!/bin/sh\necho FAKE "$@"\n', encoding="utf-8")
        path.chmod(0o755)
    return path


class LauncherTest(unittest.TestCase):
    def run_launcher(self, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess:
        clean = {"PATH": "", "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        clean.update(env)
        return subprocess.run(
            [sys.executable, str(LAUNCHER), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=clean,
        )

    def test_delegates_to_explicit_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cli = fake_cli(Path(tmp))
            proc = self.run_launcher("doctor", "--json", env={"PODCAST_KG_BIN": str(cli)})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("FAKE doctor --json", proc.stdout)

    def test_help_does_not_install_anything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_launcher(
                "--help",
                env={"PODCAST_KG_HOME": str(home), "PODCAST_KG_BIN": ""},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            # the CLI ships with the skill, so help works without any install
            self.assertIn("usage: podcast-kg", proc.stdout)
            self.assertFalse((home / "venv").exists())


if __name__ == "__main__":
    unittest.main()
