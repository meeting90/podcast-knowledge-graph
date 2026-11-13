"""Version sync: the four locations must move together."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "bump_version.py"
FILES = [
    "pyproject.toml",
    "src/podcast_kg/__init__.py",
    "skills/podcast-knowledge-graph/runtime.json",
    "skills/podcast-knowledge-graph/bin/bootstrap.py",
]


class VersionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        for rel in FILES:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, target)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--root", str(self.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def values(self) -> dict:
        import re

        texts = {rel: (self.root / rel).read_text(encoding="utf-8") for rel in FILES}
        return {
            "pyproject": re.search(r'^version\s*=\s*"([^"]+)"', texts["pyproject.toml"], re.M).group(1),
            "package": re.search(r'^__version__\s*=\s*"([^"]+)"', texts["src/podcast_kg/__init__.py"], re.M).group(1),
            "runtime": json.loads(texts["skills/podcast-knowledge-graph/runtime.json"])["version"],
            "bootstrap": re.search(
                r'^PIN_VERSION\s*=\s*"([^"]+)"',
                texts["skills/podcast-knowledge-graph/bin/bootstrap.py"],
                re.M,
            ).group(1),
        }

    def test_repository_is_consistent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_set_updates_all_four(self) -> None:
        result = self.run_cli("--set", "1.2.3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.values().values()), {"1.2.3"})
        self.assertEqual(self.run_cli("--check").returncode, 0)
        report = json.loads((self.root / "skills/podcast-knowledge-graph/runtime.json").read_text(encoding="utf-8"))
        self.assertEqual(report["version"], "1.2.3")

    def test_part_bumps(self) -> None:
        current = self.values()["pyproject"]
        major, minor, patch = current.split(".")
        for part, expected in (
            ("patch", f"{major}.{minor}.{int(patch) + 1}"),
            ("minor", f"{major}.{int(minor) + 1}.0"),
            ("major", f"{int(major) + 1}.0.0"),
        ):
            self.run_cli("--set", current)
            self.assertEqual(self.run_cli(part).returncode, 0)
            self.assertEqual(set(self.values().values()), {expected}, part)

    def test_print_current_version(self) -> None:
        out = self.run_cli("--print")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.strip(), self.values()["pyproject"])

    def test_dry_run_writes_nothing(self) -> None:
        before = self.values()
        self.assertEqual(self.run_cli("--set", "2.0.0", "--dry-run").returncode, 0)
        self.assertEqual(self.values(), before)

    def test_check_detects_drift(self) -> None:
        path = self.root / "skills/podcast-knowledge-graph/runtime.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = "9.9.9"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = self.run_cli("--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("runtime", result.stderr)


if __name__ == "__main__":
    unittest.main()
