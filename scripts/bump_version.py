#!/usr/bin/env python3
"""Keep the four version locations in sync.

The version lives in four places because four different consumers read it:

  1. pyproject.toml                 → what PyPI/pip sees
  2. skills/podcast-knowledge-graph/lib/podcast_kg/__init__.py → what `podcast-kg --version` prints
  3. skills/.../runtime.json        → what the skill pins when installing
  4. skills/.../bin/bootstrap.py    → the pin embedded for standalone scripts

Usage:
    python scripts/bump_version.py --check
    python scripts/bump_version.py patch        # 0.1.0 -> 0.1.1
    python scripts/bump_version.py minor        # 0.1.x -> 0.2.0
    python scripts/bump_version.py major        # 0.x.y -> 1.0.0
    python scripts/bump_version.py --set 1.0.0
    python scripts/bump_version.py patch --dry-run

The script only edits files; commit the change in the PR. The release workflow
tags `v<version>` after that PR merges.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = Path("skills") / "podcast-knowledge-graph"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def targets(root: Path) -> dict[str, Path]:
    return {
        "pyproject": root / "pyproject.toml",
        "package": root / "skills/podcast-knowledge-graph/lib" / "podcast_kg" / "__init__.py",
        "runtime": root / SKILL / "runtime.json",
        "bootstrap": root / SKILL / "bin" / "bootstrap.py",
    }


def read_current(root: Path) -> str:
    text = targets(root)["pyproject"].read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not match:
        raise SystemExit("pyproject.toml: cannot find [project] version")
    return match.group(1)


def found(root: Path) -> dict[str, str | None]:
    paths = targets(root)

    def grab(path: Path, pattern: str, group: int = 1) -> str | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        match = re.search(pattern, text, re.M)
        return match.group(group) if match else None

    return {
        "pyproject": grab(paths["pyproject"], r'^version\s*=\s*"([^"]+)"'),
        "package": grab(paths["package"], r'^__version__\s*=\s*"([^"]+)"'),
        "runtime": grab(paths["runtime"], r'"version"\s*:\s*"([^"]+)"'),
        "bootstrap": grab(paths["bootstrap"], r'^PIN_VERSION\s*=\s*"([^"]+)"'),
    }


def next_version(current: str, part: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def render(path: Path, version: str) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    if path.name == "pyproject.toml":
        updated = re.sub(r'^version\s*=\s*"[^"]+"', f'version = "{version}"', text, count=1, flags=re.M)
    elif path.name == "__init__.py":
        updated = re.sub(r'^__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', text, count=1, flags=re.M)
    elif path.name == "runtime.json":
        updated = re.sub(r'"version"\s*:\s*"[^"]+"', f'"version": "{version}"', text, count=1)
    else:
        updated = re.sub(r'^PIN_VERSION\s*=\s*"[^"]+"', f'PIN_VERSION = "{version}"', text, count=1, flags=re.M)
    return text, updated


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Sync the four version locations.")
    parser.add_argument("part", nargs="?", choices=["major", "minor", "patch"], help="bump this part")
    parser.add_argument("--set", metavar="X.Y.Z", help="set an explicit version")
    parser.add_argument("--check", action="store_true", help="verify the four files agree")
    parser.add_argument("--print", dest="show", action="store_true", help="print the current version and exit")
    parser.add_argument("--dry-run", action="store_true", help="print changes without writing")
    parser.add_argument("--root", metavar="DIR", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else REPO

    current = read_current(root)
    values = found(root)

    if args.show:
        print(current)
        return 0

    if args.check or (not args.part and not args.set):
        bad = {name: value for name, value in values.items() if value != current}
        if bad:
            print(f"version mismatch (pyproject={current}):", file=sys.stderr)
            for name, value in bad.items():
                print(f"  {name}: {value}", file=sys.stderr)
            print("fix with: python scripts/bump_version.py --set " + current, file=sys.stderr)
            return 1
        print(f"version OK: {current} (pyproject / package / runtime.json / bootstrap)")
        return 0

    if args.set:
        if not SEMVER.match(args.set):
            raise SystemExit(f"--set expects X.Y.Z, got {args.set!r}")
        target = args.set
    else:
        target = next_version(current, args.part)

    for path in targets(root).values():
        _, updated = render(path, target)
        if args.dry_run:
            print(f"would update  {path.relative_to(root)}")
        else:
            path.write_text(updated, encoding="utf-8", newline="\n")
            print(f"updated       {path.relative_to(root)}")
    print(f"\n{current} → {target}")
    if args.dry_run:
        print("(dry run: nothing written)")
    else:
        print("now: git diff, commit in the PR, merge → the release workflow tags v" + target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
