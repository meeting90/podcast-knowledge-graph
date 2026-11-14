"""PR title -> release-notes label mapping."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load():
    spec = importlib.util.spec_from_file_location("pr_label", REPO / "scripts" / "pr_label.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_label"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class LabelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.label = load().label_for

    def test_conventional_prefixes(self) -> None:
        cases = {
            "feat: add bilingual cards": "feature",
            "feature(ui): add toggle": "feature",
            "feat(api)!: drop v0": "feature",
            "fix: crash on empty claims": "bug",
            "fix(render): escape text": "bug",
            "docs: explain the launcher": "documentation",
            "doc: typo": "documentation",
            "chore: bump deps": "chore",
            "refactor(core): split module": "chore",
            "ci: add release job": "chore",
            "test: cover launcher": "chore",
            "perf: cache registry": "chore",
        }
        for title, expected in cases.items():
            self.assertEqual(self.label(title), expected, title)

    def test_unknown_titles_stay_uncategorized(self) -> None:
        for title in ("Update README", "featuring a new thing", "FIX: shout", ""):
            self.assertEqual(self.label(title), "", title)


if __name__ == "__main__":
    unittest.main()
