"""Runtime status, pin, and post-install checks (everything is bundled)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
LIB = REPO / "skills" / "podcast-knowledge-graph" / "lib"
sys.path.insert(0, str(LIB))

from podcast_kg import __version__  # noqa: E402
from podcast_kg import runtime  # noqa: E402
from podcast_kg import skill_install as si  # noqa: E402


class PinTest(unittest.TestCase):
    def test_repo_pin_matches_this_cli(self) -> None:
        pin = json.loads(
            (REPO / "skills" / si.SKILL_NAME / "runtime.json").read_text(encoding="utf-8")
        )
        self.assertEqual(pin["package"], "podcast-kg")
        self.assertEqual(pin["version"], __version__)
        self.assertEqual(pin["entry"], "bin/podcast-kg.py")

    def test_write_pin_refreshes_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runtime.json").write_text('{"version": "0.0.1"}', encoding="utf-8")
            runtime.write_pin(root, force=False)
            self.assertEqual(
                json.loads((root / "runtime.json").read_text(encoding="utf-8"))["version"],
                __version__,
            )

    def test_installed_skill_carries_pin_and_lib(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            result = si.install(targets=["claude"], scope="project", project=str(project))
            skill_dir = Path(result["results"][0]["skill_dir"])
            pin = json.loads((skill_dir / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(pin["version"], __version__)
            self.assertTrue((skill_dir / "lib" / "podcast_kg" / "cli.py").is_file())
            self.assertTrue((skill_dir / "bin" / "podcast-kg.py").is_file())


class StatusTest(unittest.TestCase):
    def test_status_reports_bundled_cli_and_models(self) -> None:
        report = runtime.status()
        self.assertTrue(report["bundled"])
        self.assertTrue(report["ready"])
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

    def _report(self, ready: bool = True) -> dict:
        return {
            "ready": ready,
            "bundled": True,
            "on_path": ready,
            "cli": "/skill/lib/podcast_kg" if ready else None,
            "version": __version__ if ready else None,
            "pinned": __version__,
            "skill_dir": None,
            "runtime_home": "/tmp",
            "transcribe_ready": True,
            "ingest_ready": True,
            "default_model": "small",
            "models_dir": "/tmp/models",
            "model": {"status": "未下载"},
            "notes": [],
        }

    def test_verify_passes_when_runtime_ready(self) -> None:
        with mock.patch.object(runtime, "status", return_value=self._report()):
            checks = si.verify(self.entries)
        self.assertTrue(all(item["ok"] for item in checks), checks)

    def test_verify_fails_when_cli_missing(self) -> None:
        with mock.patch.object(runtime, "status", return_value=self._report(ready=False)):
            checks = si.verify(self.entries)
        failed = [item for item in checks if not item["ok"]]
        self.assertIn("CLI 可执行", [item["label"] for item in failed])

    def test_verify_catches_missing_pointer_block(self) -> None:
        (self.project / "AGENTS.md").write_text("other text\n", encoding="utf-8")
        with mock.patch.object(runtime, "status", return_value=self._report()):
            checks = si.verify(self.entries)
        self.assertIn("指令文件标记块", [item["label"] for item in checks if not item["ok"]])


if __name__ == "__main__":
    unittest.main()
