"""Whisper model resolution: local dirs, prefetch, offline behaviour.

Run with:  PYTHONPATH=src python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from podcast_kg import models  # noqa: E402


def make_model(root: Path, name: str, complete: bool = True) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    for item in ("config.json", "model.bin", "tokenizer.json"):
        (directory / item).write_text("x", encoding="utf-8")
    if complete:
        (directory / "vocabulary.txt").write_text("x", encoding="utf-8")
    return directory


class TableTest(unittest.TestCase):
    def test_size_table_is_ordered_and_sane(self) -> None:
        self.assertEqual(models.DEFAULT_MODEL, "small")
        sizes = [models.KNOWN[name]["size_mb"] for name in ("tiny", "base", "small")]
        self.assertEqual(sizes, sorted(sizes))
        self.assertEqual(sizes, [78, 148, 486])

    def test_every_entry_has_a_repo(self) -> None:
        for name, info in models.KNOWN.items():
            self.assertTrue(info["repo"].startswith(("Systran/", "mobiuslabsgmbh/")), name)


class VerifyTest(unittest.TestCase):
    def test_complete_directory_has_no_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(models.verify_dir(make_model(Path(tmp), "small")), [])

    def test_missing_files_are_named(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_model(Path(tmp), "small", complete=False)
            (directory / "model.bin").unlink()
            missing = models.verify_dir(directory)
            self.assertIn("model.bin", missing)
            self.assertTrue(any("vocabulary" in item for item in missing))


class ResolveTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_explicit_path_wins(self) -> None:
        directory = make_model(self.root, "tiny")
        source, note = models.resolve_source(str(directory))
        self.assertEqual(Path(source), directory)
        self.assertIn("本地模型目录", note)

    def test_incomplete_path_is_an_error(self) -> None:
        directory = make_model(self.root, "tiny", complete=False)
        (directory / "model.bin").unlink()
        with self.assertRaises(SystemExit) as caught:
            models.resolve_source(str(directory))
        message = str(caught.exception)
        self.assertIn("model.bin", message)
        self.assertIn("models fetch", message)

    def test_model_dir_env_is_used(self) -> None:
        directory = make_model(self.root, "small")
        with mock.patch.dict(os.environ, {"PODCAST_KG_MODEL_DIR": str(self.root)}):
            source, note = models.resolve_source("small")
        self.assertEqual(Path(source), directory)
        self.assertIn("本地模型目录", note)

    def test_explicit_model_dir_beats_env(self) -> None:
        explicit = self.root / "explicit"
        make_model(explicit, "small")
        with mock.patch.dict(os.environ, {"PODCAST_KG_MODEL_DIR": str(self.root / "env")}):
            source, _ = models.resolve_source("small", str(explicit))
        self.assertEqual(Path(source), explicit / "small")

    def test_unknown_model_falls_through_to_hub(self) -> None:
        with mock.patch.dict(os.environ, {"PODCAST_KG_MODEL_DIR": str(self.root)}):
            source, note = models.resolve_source("definitely-not-cached-model")
        self.assertEqual(source, "definitely-not-cached-model")
        self.assertIn("Hub", note)


class StatusTest(unittest.TestCase):
    def test_local_model_is_reported_with_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_model(Path(tmp), "small")
            info = models.status("small", tmp)
            self.assertEqual(info["status"], "本地模型")
            self.assertEqual(Path(info["path"]), directory)
            self.assertEqual(info["size_mb"], 486)

    def test_incomplete_local_dir_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = make_model(Path(tmp), "small", complete=False)
            (directory / "model.bin").unlink()
            info = models.status("small", tmp)
            self.assertEqual(info["status"], "本地不完整")
            self.assertTrue(info["missing"])

    def test_list_covers_every_known_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rows = models.status_list(tmp)
        self.assertEqual([row["name"] for row in rows], list(models.KNOWN))


class FetchTest(unittest.TestCase):
    def test_dry_run_downloads_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reports = models.fetch(["small"], root=tmp, dry_run=True)
            self.assertEqual(reports[0]["action"], "would-fetch")
            self.assertFalse((Path(tmp) / "small").exists())

    def test_all_expands_to_every_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reports = models.fetch(["all"], root=tmp, dry_run=True)
        self.assertEqual(len(reports), len(models.KNOWN))

    def test_present_model_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            make_model(Path(tmp), "small")
            reports = models.fetch(["small"], root=tmp)
        self.assertEqual(reports[0]["action"], "already-present")

    def test_unknown_model_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as caught:
                models.fetch(["nope"], root=tmp)
        self.assertIn("未知模型", str(caught.exception))


class LoadModelOfflineTest(unittest.TestCase):
    def test_offline_without_weights_fails_with_instructions(self) -> None:
        from podcast_kg.transcribe import load_model

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                {
                    "PODCAST_KG_OFFLINE": "1",
                    "PODCAST_KG_MODEL_DIR": tmp,
                },
            ), mock.patch.object(models, "hf_snapshot", return_value=None):
                with self.assertRaises(SystemExit) as caught:
                    load_model("small", "cpu", "int8")
        message = str(caught.exception)
        self.assertIn("models fetch --model small", message)
        self.assertIn("--model-dir", message)


class OfflineTest(unittest.TestCase):
    def test_offline_flag_variants(self) -> None:
        for value in ("1", "true", "yes"):
            with mock.patch.dict(os.environ, {"PODCAST_KG_OFFLINE": value}):
                self.assertTrue(models.offline_requested(), value)
        with mock.patch.dict(os.environ, {"PODCAST_KG_OFFLINE": "0"}):
            self.assertFalse(models.offline_requested())

    def test_hint_names_the_fetch_command(self) -> None:
        hint = models.offline_hint("small")
        self.assertIn("models fetch --model small", hint)
        self.assertIn("--model-dir", hint)


if __name__ == "__main__":
    unittest.main()
