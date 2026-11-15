#!/usr/bin/env python3
"""Stable entry point for the skill: `python3 bin/podcast-kg.py <args>`.

The CLI ships inside the skill (`lib/podcast_kg`), so it needs no installation.
Commands that only use the standard library (render/verify/ingest/i18n/models/
doctor) always work. `transcribe` additionally needs `faster-whisper` in the
environment; if it is missing this launcher reports it and installs nothing.

Exit codes are the CLI's own (0 success, 1 failure, 130 interrupted).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
LIB = SKILL / "lib"
IS_WIN = sys.platform == "win32"
NL = chr(10)


def runtime_home() -> Path:
    override = os.environ.get("PODCAST_KG_HOME")
    if override:
        return Path(override).expanduser().resolve()
    try:
        home = Path.home()
    except RuntimeError:  # HOME / USERPROFILE unset (containers, CI)
        home = Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.getcwd())
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or (home / "AppData" / "Local")
        return Path(base) / "podcast-kg"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "podcast-kg"
    base = os.environ.get("XDG_DATA_HOME") or (home / ".local" / "share")
    return Path(base) / "podcast-kg"


def venv_python(home: Path) -> Path:
    return home / "venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")


def cli_command(cli: Path, args: list[str]) -> list[str]:
    if IS_WIN and cli.suffix.lower() in (".cmd", ".bat"):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(cli), *args]
    return [str(cli), *args]


def has_module(python: Path, module: str) -> bool:
    code = subprocess.call(
        [str(python), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return code == 0


def required_module(args: list[str]) -> str | None:
    """Only these commands need anything beyond the standard library."""
    if not args:
        return None
    if args[0] == "transcribe":
        return "faster_whisper"
    if args[0] == "models" and len(args) > 1 and args[1] == "fetch":
        return "huggingface_hub"
    return None


def run_vendored(python: Path, args: list[str]) -> int:
    env = dict(os.environ)
    previous = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(LIB) + (os.pathsep + previous if previous else "")
    env["PODCAST_KG_VENDORED"] = "1"
    return subprocess.call([str(python), "-m", "podcast_kg", *args], env=env)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = list(sys.argv[1:] if argv is None else argv)

    # An explicit binary always wins (tests, CI, users with a custom install).
    explicit = os.environ.get("PODCAST_KG_BIN")
    if explicit and Path(explicit).is_file():
        return subprocess.call(cli_command(Path(explicit), args))

    home = runtime_home()

    if not (LIB / "podcast_kg" / "cli.py").is_file():
        print(
            "This skill is incomplete: lib/podcast_kg is missing." + NL
            + "Reinstall the skill (npx skills / unzip the release asset).",
            file=sys.stderr,
        )
        return 1

    python = venv_python(home)
    if not python.is_file():
        python = Path(sys.executable)
    module = required_module(args)
    if module and not has_module(python, module):
        print(
            f"{args[0]} needs {module}, which is not available in this environment." + NL
            + "This skill installs nothing: provide a transcript, or use an environment that" + NL
            + "already has faster-whisper. Everything else (render/verify/ingest/i18n/models)" + NL
            + "works without it.",
            file=sys.stderr,
        )
        return 1
    return run_vendored(python, args)


if __name__ == "__main__":
    raise SystemExit(main())
