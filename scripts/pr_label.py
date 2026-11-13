#!/usr/bin/env python3
"""Map a PR title (Conventional Commits prefix) to a release-notes label.

    feat: ...            -> feature
    feat(api)!: ...      -> feature
    fix: ...             -> bug
    docs: ...            -> documentation
    chore/refactor/ci/…  -> chore
    anything else        -> (empty, stays in "Other changes")

Used by .github/workflows/pr-label.yml; keep the labels in sync with
.github/release.yml.
"""

from __future__ import annotations

import re
import sys

RULES = (
    (re.compile(r"^(?:feat|feature)(?:\([^)]*\))?!?:"), "feature"),
    (re.compile(r"^fix(?:\([^)]*\))?!?:"), "bug"),
    (re.compile(r"^docs?(?:\([^)]*\))?:"), "documentation"),
    (re.compile(r"^(?:chore|refactor|test|tests|ci|build|perf)(?:\([^)]*\))?!?:"), "chore"),
)


def label_for(title: str) -> str:
    text = (title or "").strip()
    for pattern, label in RULES:
        if pattern.match(text):
            return label
    return ""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    print(label_for(args[0] if args else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
