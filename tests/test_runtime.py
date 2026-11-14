"""Runtime-guarantee tests: the pin, the bootstrap, and post-install checks.

Run with:  PYTHONPATH=src python -m unittest discover -s tests -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from podcast_kg import __version__  # noqa: E402
from podcast_kg import runtime  # noqa: E402
from podcast_kg import skill_install as si  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO / "skills" / si.SKILL_NAME / "bin" / "bootstrap.py"


def clean_env(**extra: str) -> dict:
    keep = ("SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.update(extra)
    return env


def load_bootstrap():
    """Import the standalone script as a module (it must stay stdlib-only)."""
    spec = importlib.util.spec_from_file_location("pk_bootstrap", BOOTSTRAP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class BootstrapSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bootstrap = load_bootstrap()

    def test_pinned_spec_uses_version_and_extras(self) -> None:
        pin = {"package": "podcast-kg", "version": "1.2.3", "extras": ["all"]}
        self.assertEqual(self.bootstrap.pip_spec(pin), "podcast-kg[all]==1.2.3")
        self.assertEqual(self.bootstrap.pip_spec(pin, "none"), "podcast-kg==1.2.3")
        self.assertEqual(
            self.bootstrap.pip_spec(pin, "transcribe"), "podcast-kg[transcribe]==1.2.3"
        )

    def test_latest_means_no_version_constraint(self) -> None:
        pin = {"package": "podcast-kg", "version": "latest", "extras": []}
        self.assertEqual(self.bootstrap.pip_spec(pin), "podcast-kg")

    def test_sources_are_ordered_local_pypi_git(self) -> None:
        pin = {
            "package": "podcast-kg",
            "version": "1.0.0",
            "extras": ["all"],
            "install_from_git": "git+https://example.invalid/pk",
        }
        kinds = [kind for kind, _ in self.bootstrap.candidate_specs(pin, None, Path("/repo"))]
        self.assertEqual(kinds, ["local", "pypi", "git"])
        specs = [spec for _, spec in self.bootstrap.candidate_specs(pin, None, None)]
        self.assertEqual(specs[0], "podcast-kg[all]==1.0.0")
        self.assertIn(" @ git+https://example.invalid/pk", specs[1])

    def test_git_rev_pins_the_fallback(self) -> None:
        pin = {
            "package": "podcast-kg",
            "version": "1.0.0",
            "extras": [],
            "install_from_git": "git+https://example.invalid/pk",
            "git_rev": "v1.0.0",
        }
        specs = [spec for _, spec in self.bootstrap.candidate_specs(pin, "none", None)]
        self.assertEqual(specs[-1], "podcast-kg @ git+https://example.invalid/pk@v1.0.0")

    def test_local_project_is_none_outside_a_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill = Path(tmp) / "podcast-knowledge-graph"
            skill.mkdir()
            with mock.patch.object(Path, "cwd", return_value=Path(tmp)):
                self.assertIsNone(self.bootstrap.local_project(skill))

    def test_local_project_found_in_the_repo(self) -> None:
        root = BOOTSTRAP.parent.parent
        self.assertEqual(self.bootstrap.local_project(root), REPO)


class PinTest(unittest.TestCase):
    def test_repo_pin_matches_this_cli(self) -> None:
        pin = json.loads(
            (REPO / "skills" / si.SKILL_NAME / "runtime.json").read_text(encoding="utf-8")
        )
        self.assertEqual(pin["package"], "podcast-kg")
        self.assertEqual(pin["version"], __version__)
        self.assertIn("all", pin["extras"])
        self.assertEqual(pin["bootstrap"], "bin/bootstrap.py")

    def test_write_pin_refreshes_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pin_file = root / "runtime.json"
            pin_file.write_text('{"version": "0.0.1"}', encoding="utf-8")

            runtime.write_pin(root, force=False)
            self.assertEqual(
                json.loads(pin_file.read_text(encoding="utf-8"))["version"], __version__
            )

    def test_installed_skill_carries_pin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            result = si.install(
                targets=["claude"], scope="project", project=str(project)
            )
            skill_dir = Path(result["results"][0]["skill_dir"])
            pin = json.loads((skill_dir / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(pin["version"], __version__)
            self.assertTrue((skill_dir / "bin" / "bootstrap.py").is_file())


class BootstrapTest(unittest.TestCase):
    def run_bootstrap(self, *args: str, home: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(BOOTSTRAP), *args, "--home", str(home)],
            capture_output=True,
            text=True,
            timeout=120,
            env=clean_env(
                PODCAST_KG_HOME=str(home),
                PATH=str(home / "empty-bin"),
            ),
        )

    def test_plan_is_read_only_and_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_bootstrap("--plan", "--json", home=home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ready"])
            self.assertIn(
                report["action"],
                {"install-deps", "install-uv", "install-pip", "install-blocked"},
            )
            self.assertTrue(report["vendored"])
            self.assertTrue(report["deps"])
            self.assertIn("podcast-kg", report["pinned"])
            self.assertFalse(home.exists(), "plan must not create anything")

    def test_plan_reports_requested_models_without_downloading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_bootstrap("--plan", "--json", "--models", "small", home=home)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertEqual(report["models"]["requested"], ["small"])
            self.assertEqual(report["models"]["action"], "none")
            self.assertFalse((home / "models").exists())

    def test_check_fails_when_nothing_is_installed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            proc = self.run_bootstrap("--check", "--json", home=home)
            self.assertEqual(proc.returncode, 1)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ready"])
            self.assertTrue(report["notes"] or report["action"])

    def test_check_uses_pinned_shim_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            shim_dir = home / "bin"
            shim_dir.mkdir(parents=True)
            # A shim pointing at a "CLI" that answers --version.
            fake = Path(tmp) / "fake-cli"
            if os.name == "nt":
                fake = fake.with_suffix(".py")
                fake.write_text("import sys;print('podcast-kg 0.1.0')\n", encoding="utf-8")
                shim = shim_dir / "podcast-kg.cmd"
                shim.write_text(f'@echo off\r\n"{sys.executable}" "{fake}" %*\r\n', encoding="utf-8")
            else:
                fake.write_text(
                    "#!/bin/sh\necho 'podcast-kg 0.1.0'\n", encoding="utf-8"
                )
                fake.chmod(0o755)
                shim = shim_dir / "podcast-kg"
                shim.write_text(f'#!/bin/sh\nexec "{fake}" "$@"\n', encoding="utf-8")
                shim.chmod(0o755)

            proc = self.run_bootstrap("--check", "--json", home=home)
            report = json.loads(proc.stdout)
            self.assertTrue(report["ready"], proc.stdout + proc.stderr)
            self.assertEqual(Path(report["cli"]).resolve(), shim.resolve())


class StatusTest(unittest.TestCase):
    def test_status_reports_model_defaults(self) -> None:
        report = runtime.status()
        self.assertIn("default_model", report)
        self.assertIn("models_dir", report)
        self.assertIn(report["model"]["status"], {"本地模型", "HF 缓存", "未下载", "本地不完整"})


class VerifyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.result = si.install(targets=["agents"], scope="project", project=str(self.project))
        self.entries = si.plan(targets=["agents"], scope="project", project=str(self.project))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_verify_passes_when_runtime_ready(self) -> None:
        report = {
            "ready": True,
            "cli": "/usr/bin/podcast-kg",
            "version": __version__,
            "pinned": __version__,
            "skill_dir": None,
            "bootstrap": None,
            "runtime_home": "/tmp",
            "venv_cli": None,
            "transcribe_ready": True,
            "ingest_ready": False,
            "notes": [],
        }
        with mock.patch.object(runtime, "status", return_value=report):
            checks = si.verify(self.entries)
        self.assertTrue(all(item["ok"] for item in checks), checks)

    def test_verify_fails_when_cli_missing(self) -> None:
        report = {
            "ready": False,
            "cli": None,
            "version": None,
            "pinned": __version__,
            "skill_dir": None,
            "bootstrap": None,
            "runtime_home": "/tmp",
            "venv_cli": None,
            "transcribe_ready": False,
            "ingest_ready": False,
            "notes": [],
        }
        with mock.patch.object(runtime, "status", return_value=report):
            checks = si.verify(self.entries)
        failed = [item for item in checks if not item["ok"]]
        self.assertEqual([item["label"] for item in failed], ["CLI 可执行"])

    def test_verify_catches_missing_pointer_block(self) -> None:
        report = {
            "ready": True,
            "cli": "/usr/bin/podcast-kg",
            "version": __version__,
            "pinned": __version__,
            "skill_dir": None,
            "bootstrap": None,
            "runtime_home": "/tmp",
            "venv_cli": None,
            "transcribe_ready": True,
            "ingest_ready": True,
            "notes": [],
        }
        (self.project / "AGENTS.md").write_text("other text\n", encoding="utf-8")
        with mock.patch.object(runtime, "status", return_value=report):
            checks = si.verify(self.entries)
        self.assertIn("指令文件标记块", [item["label"] for item in checks if not item["ok"]])


if __name__ == "__main__":
    unittest.main()
