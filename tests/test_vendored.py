"""The CLI ships inside the skill: lib/ sync, launcher, dependency guard."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / "skills" / "podcast-knowledge-graph"
LAUNCHER = SKILL / "bin" / "podcast-kg.py"
sys.path.insert(0, str(REPO / "src"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


KEEP_ENV = ("SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA")


def clean_env(**extra: str) -> dict:
    env = {key: os.environ[key] for key in KEEP_ENV if key in os.environ}
    env.update({"PATH": ""})
    env.update(extra)
    return env


class SyncTest(unittest.TestCase):
    def test_vendored_copy_matches_source(self) -> None:
        module = load("sync_skill_lib", REPO / "scripts" / "sync_skill_lib.py")
        problems = module.diff()
        self.assertEqual(problems, [], "run: python scripts/sync_skill_lib.py")

    def test_required_modules_exist(self) -> None:
        for name in ("cli.py", "__main__.py", "i18n.py", "models.py", "render_card.py"):
            self.assertTrue((SKILL / "lib" / "podcast_kg" / name).is_file(), name)
        self.assertTrue((SKILL / "lib" / "podcast_kg" / "assets" / "heron.css").is_file())


class LauncherTest(unittest.TestCase):
    def run_launcher(self, *args: str, home: Path) -> subprocess.CompletedProcess:
        env = clean_env(PODCAST_KG_HOME=str(home))
        return subprocess.run(
            [sys.executable, str(LAUNCHER), *args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, env=env,
        )

    def test_runs_vendored_cli_without_installing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_launcher("--version", home=home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("podcast-kg 0.1.", proc.stdout)
            self.assertFalse((home / "venv").exists())

    def test_doctor_works_without_deps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_launcher("doctor", home=home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("图谱快照", proc.stdout)


class DepsGuardTest(unittest.TestCase):
    def test_vendored_mode_refuses_to_pollute_system_python(self) -> None:
        from podcast_kg import deps

        with mock.patch.dict(os.environ, {"PODCAST_KG_VENDORED": "1"}):
            with self.assertRaises(SystemExit) as caught:
                deps.ensure("module_that_does_not_exist_xyz")
        self.assertIn("内置", str(caught.exception))
        self.assertIn("bin/podcast-kg.py", str(caught.exception))


class PackageTest(unittest.TestCase):
    def test_zip_contains_a_runnable_vendored_cli(self) -> None:
        module = load("package_skill", REPO / "scripts" / "package_skill.py")
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "skill.zip"
            report = module.build(archive)
            self.assertTrue(report.ok, report.errors)
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)
            launcher = Path(tmp) / "podcast-knowledge-graph" / "bin" / "podcast-kg.py"
            self.assertTrue(launcher.is_file())
            env = clean_env(PODCAST_KG_HOME=str(Path(tmp) / "home"))
            proc = subprocess.run(
                [sys.executable, str(launcher), "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120, env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("podcast-kg 0.1.", proc.stdout)


if __name__ == "__main__":
    unittest.main()
