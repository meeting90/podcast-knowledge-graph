"""Skill packaging: Agensi rules, deterministic ZIP, standalone bootstrap pin."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from podcast_kg import __version__  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module          # dataclasses need the module registered
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


package = load("package_skill", REPO / "scripts" / "package_skill.py")
bootstrap = load("skill_bootstrap", REPO / "skills" / "podcast-knowledge-graph" / "bin" / "bootstrap.py")


class PinTest(unittest.TestCase):
    def test_embedded_pin_matches_package_and_runtime(self) -> None:
        self.assertEqual(bootstrap.PIN_VERSION, __version__)
        runtime = json.loads(
            (REPO / "skills" / "podcast-knowledge-graph" / "runtime.json").read_text(encoding="utf-8")
        )
        self.assertEqual(runtime["version"], __version__)
        self.assertEqual(runtime.get("install_from_git"), bootstrap.PIN_GIT)

    def test_standalone_pin_needs_no_runtime_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pin = bootstrap.load_pin(Path(tmp))  # no runtime.json here
        self.assertEqual(pin["version"], bootstrap.PIN_VERSION)
        self.assertEqual(bootstrap.pip_spec(pin), f"podcast-kg[all]=={bootstrap.PIN_VERSION}")


class InspectTest(unittest.TestCase):
    def test_repository_skill_passes_agensi_checks(self) -> None:
        report = package.inspect()
        self.assertTrue(report.ok, report.errors)
        names = {name for name, _ in report.files}
        for required in package.REQUIRED:
            self.assertIn(required, names)
        self.assertLess(report.size, package.MAX_BYTES)
        self.assertLess(len(report.files), package.MAX_FILES)
        self.assertLess(report.chars, package.MAX_CHARS)

    def test_collect_skips_caches_and_os_junk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\n", encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "x.pyc").write_bytes(b"x")
            (root / ".DS_Store").write_bytes(b"x")
            (root / "notes.md").write_text("ok", encoding="utf-8")
            files = [p.relative_to(root).as_posix() for p in package.collect(root)]
        self.assertEqual(sorted(files), ["SKILL.md", "notes.md"])

    def test_unquoted_colon_in_frontmatter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content = "---" + chr(10) + "name: x" + chr(10) + "description: a: b" + chr(10) + "---" + chr(10)
            (root / "SKILL.md").write_text(content, encoding="utf-8")
            report = package.inspect(root)
        self.assertFalse(report.ok)
        self.assertTrue(any("YAML" in error for error in report.errors))

    def test_frontmatter_requires_name_and_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("---\ndescription: y\n---\n", encoding="utf-8")
            report = package.inspect(root)
        self.assertFalse(report.ok)
        self.assertTrue(any("name" in error for error in report.errors))


class BuildTest(unittest.TestCase):
    def test_zip_layout_and_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.zip"
            second = Path(tmp) / "b.zip"
            report = package.build(first)
            self.assertTrue(report.ok, report.errors)
            package.build(second)

            self.assertEqual(first.read_bytes(), second.read_bytes(), "zip must be deterministic")
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
            self.assertTrue(all(name.startswith("podcast-knowledge-graph/") for name in names))
            self.assertIn("podcast-knowledge-graph/SKILL.md", names)
            self.assertIn("podcast-knowledge-graph/bin/bootstrap.py", names)
            self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
            self.assertFalse(
                any(Path(name).suffix.lower() in package.EXECUTABLE_SUFFIXES for name in names)
            )

    def test_build_refuses_invalid_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SKILL.md").write_text("# no frontmatter", encoding="utf-8")
            out = Path(tmp) / "x.zip"
            report = package.build(out, root=root)
        self.assertFalse(report.ok)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
