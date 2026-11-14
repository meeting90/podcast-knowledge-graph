#!/usr/bin/env python3
"""Build an Agensi-compatible ZIP of the skill (and check it before upload).

Agensi rules implemented here (see agensi.io/docs/packaging):

  * one ZIP, a single top folder, with `SKILL.md` inside;
  * the top `SKILL.md` must have a `name`, and every `SKILL.md` a `description`;
  * text/code only — executable file types are rejected;
  * <= 50 MB, <= 1000 files, and <= 6M characters delivered to the agent;
  * `.git`, `__pycache__`, `.DS_Store`, `node_modules`, `site-packages` and
    virtualenvs are stripped;
  * each script should stay under 20 KB (warning, not a hard limit).

The archive is deterministic: sorted entries with a fixed timestamp, so the
same tree always produces the same SHA-256. That makes it safe to attach to a
GitHub Release instead of committing the binary to git.

Usage
-----
    python scripts/package_skill.py                  # write dist/<name>-<ver>.zip
    python scripts/package_skill.py --check          # validate only, write nothing
    python scripts/package_skill.py --json           # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL_NAME = "podcast-knowledge-graph"
SKILL_DIR = REPO / "skills" / SKILL_NAME

EXECUTABLE_SUFFIXES = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".app", ".dmg", ".msi",
    ".deb", ".rpm", ".wasm", ".class", ".jar", ".war",
}
SKIP_DIRS = {
    "__pycache__", ".git", ".github", "node_modules", "site-packages",
    ".venv", "venv", ".idea", ".vscode", "__MACOSX",
}
SKIP_NAMES = {".DS_Store", "Thumbs.db", ".gitignore", ".gitattributes"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".zip", ".log", ".tmp"}

REQUIRED = (
    "SKILL.md",
    "runtime.json",
    "bin/bootstrap.py",
    "bin/podcast-kg.py",
    "lib/podcast_kg/cli.py",
    "sop/SOP.md",
    "examples/knowledge_card.example.json",
)
MAX_BYTES = 50 * 1024 * 1024
MAX_FILES = 1000
MAX_CHARS = 6_000_000
SCRIPT_BYTES_HINT = 20 * 1024
SCRIPT_SUFFIXES = {".py", ".sh", ".cmd", ".ps1"}


@dataclass
class Report:
    root: Path
    files: list[tuple[str, int]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    chars: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def size(self) -> int:
        return sum(size for _, size in self.files)


def collect(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def frontmatter(path: Path) -> dict[str, str]:
    """Minimal frontmatter reader — enough for name/description, no PyYAML dep."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fields: dict[str, str] = {}
    for line in text[3:end].splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip().strip("'\"")
    return fields


def yaml_scalar_errors(path: Path) -> list[str]:
    """Catch the YAML mistake strict parsers reject: an unquoted `: ` in a scalar.

    A description like `... cards. English: extract ...` silently becomes a nested
    mapping and marketplace installers skip the skill with a YAML parse error.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return []
    end = text.find(chr(10) + "---", 3)
    if end < 0:
        return []
    problems: list[str] = []
    for line in text[3:end].splitlines():
        if not line or line.startswith((" ", "	", "#")):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if not value or value[0] in "'\"[{|>":
            continue
        if ": " in value:
            problems.append(
                f"{path.name}: unquoted ': ' in `{match.group(1)}` breaks YAML — quote the value or use a block scalar"
            )
    return problems


def inspect(root: Path = SKILL_DIR) -> Report:
    report = Report(root=root)
    if not root.is_dir():
        report.errors.append(f"skill folder not found: {root}")
        return report

    paths = collect(root)
    for path in paths:
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        report.files.append((rel, size))

        if path.suffix.lower() in EXECUTABLE_SUFFIXES:
            report.errors.append(f"executable file type rejected by Agensi: {rel}")
        # The 20 KB guideline is about scripts the agent *executes*; library
        # modules are imported by the vendored CLI, so only bin/ entries matter.
        if (
            rel.startswith("bin/")
            and path.suffix.lower() in SCRIPT_SUFFIXES | {""}
            and size > SCRIPT_BYTES_HINT
        ):
            report.warnings.append(
                f"script over the 20 KB review guideline: {rel} ({size / 1024:.1f} KB)"
            )
        try:
            report.chars += len(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            report.warnings.append(f"non-text file (agents cannot read it): {rel}")

    names = {rel for rel, _ in report.files}
    for required in REQUIRED:
        if required not in names:
            report.errors.append(f"missing required file: {required}")

    if report.size > MAX_BYTES:
        report.errors.append(f"package is {report.size / 1e6:.1f} MB (limit 50 MB)")
    if len(report.files) > MAX_FILES:
        report.errors.append(f"{len(report.files)} files (limit 1000)")
    if report.chars > MAX_CHARS:
        report.errors.append(f"{report.chars} characters (limit 6M)")

    top = root / "SKILL.md"
    if top.is_file():
        meta = frontmatter(top)
        report.errors.extend(yaml_scalar_errors(top))
        if not meta.get("name"):
            report.errors.append("top-level SKILL.md is missing `name` in frontmatter")
        if not meta.get("description"):
            report.errors.append("top-level SKILL.md is missing `description` in frontmatter")

    for path in paths:
        if path.name == "SKILL.md":
            meta = frontmatter(path)
            report.errors.extend(yaml_scalar_errors(path))
            if not meta.get("description"):
                rel = path.relative_to(root).as_posix()
                report.errors.append(f"{rel} is missing `description` in frontmatter")

    return report


def build(out: Path, root: Path = SKILL_DIR) -> Report:
    report = inspect(root)
    if not report.ok:
        return report

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for rel, _ in report.files:
            data = (root / rel).read_bytes()
            info = zipfile.ZipInfo(f"{SKILL_NAME}/{rel}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return report


def payload(report: Report, archive: Path | None = None) -> dict:
    data = {
        "ok": report.ok,
        "root": str(report.root),
        "files": len(report.files),
        "bytes": report.size,
        "chars": report.chars,
        "errors": report.errors,
        "warnings": report.warnings,
    }
    if archive is not None and archive.is_file():
        data["archive"] = str(archive)
        data["sha256"] = sha256(archive.read_bytes()).hexdigest()
    return data


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        description="Build an Agensi-compatible ZIP of the podcast-knowledge-graph skill.",
    )
    parser.add_argument("--out", metavar="ZIP", help="output path (default dist/<name>-<version>.zip)")
    parser.add_argument("--check", action="store_true", help="validate only, write nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--quiet", action="store_true", help="only print errors")
    args = parser.parse_args(argv)

    runtime = json.loads((SKILL_DIR / "runtime.json").read_text(encoding="utf-8"))
    default_name = f"{SKILL_NAME}-{runtime.get('version', '0.0.0')}.zip"
    out = Path(args.out) if args.out else REPO / "dist" / default_name

    report = inspect(SKILL_DIR)
    if not report.ok or args.check:
        if args.json:
            print(json.dumps(payload(report), ensure_ascii=False, indent=2))
        else:
            for error in report.errors:
                print(f"error  {error}", file=sys.stderr)
            for warning in report.warnings:
                print(f"warn   {warning}", file=sys.stderr)
            if report.ok:
                print(f"OK {report.root} ({len(report.files)} files, {report.size / 1024:.0f} KB)")
        return 0 if report.ok else 1

    report = build(out)
    if not report.ok:
        for error in report.errors:
            print(f"error  {error}", file=sys.stderr)
        return 1

    data = payload(report, out)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    if not args.quiet:
        for rel, size in report.files:
            print(f"  {size:>7,}  {rel}")
        print()
        print(f"zip     {out}")
        print(f"files   {data['files']}  ·  {data['bytes'] / 1024:.0f} KB  ·  {data['chars']:,} chars")
        print(f"sha256  {data['sha256']}")
        for warning in report.warnings:
            print(f"warn    {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
