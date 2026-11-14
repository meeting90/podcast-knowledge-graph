#!/usr/bin/env python3
"""Copy the Python package into the skill so the skill ships its own CLI.

The skill must work without publishing `podcast-kg` to PyPI: `bin/podcast-kg.py`
runs `lib/podcast_kg` directly. This script keeps that copy identical to
`src/podcast_kg`; a test fails when they drift.

    python scripts/sync_skill_lib.py          # copy (and prune stale files)
    python scripts/sync_skill_lib.py --check  # verify only, exit 1 on drift
"""

from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "podcast_kg"
DEST = REPO / "skills" / "podcast-knowledge-graph" / "lib" / "podcast_kg"
SKIP_DIRS = {"__pycache__", "skill"}


def wanted(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix == ".pyc" or path.name == ".DS_Store":
            continue
        files.append(path)
    return files


def rel(path: Path, root: Path) -> Path:
    return path.relative_to(root)


def diff() -> list[str]:
    problems: list[str] = []
    src_files = {rel(p, SRC) for p in wanted(SRC)}
    dest_files = {rel(p, DEST) for p in wanted(DEST)} if DEST.is_dir() else set()
    for missing in sorted(src_files - dest_files):
        problems.append(f"missing in skill: {missing.as_posix()}")
    for extra in sorted(dest_files - src_files):
        problems.append(f"stale in skill: {extra.as_posix()}")
    for name in sorted(src_files & dest_files):
        if not filecmp.cmp(SRC / name, DEST / name, shallow=False):
            problems.append(f"differs: {name.as_posix()}")
    return problems


def sync() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    src_files = wanted(SRC)
    keep = {rel(p, SRC) for p in src_files}
    for path in wanted(DEST):
        if rel(path, DEST) not in keep:
            path.unlink()
    copied = 0
    for path in src_files:
        target = DEST / rel(path, SRC)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or not filecmp.cmp(path, target, shallow=False):
            shutil.copy2(path, target)
            copied += 1
    # drop empty dirs left by pruning
    for directory in sorted((p for p in DEST.rglob("*") if p.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync src/podcast_kg into the skill's lib/.")
    parser.add_argument("--check", action="store_true", help="verify only; exit 1 on drift")
    args = parser.parse_args(argv)

    if args.check:
        problems = diff()
        if problems:
            for problem in problems:
                print(f"drift  {problem}", file=sys.stderr)
            print("run: python scripts/sync_skill_lib.py", file=sys.stderr)
            return 1
        print(f"lib OK: {len(wanted(SRC))} files match src/podcast_kg")
        return 0

    copied = sync()
    print(f"synced {copied} file(s) into {DEST.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
