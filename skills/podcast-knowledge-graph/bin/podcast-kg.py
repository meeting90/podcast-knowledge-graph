#!/usr/bin/env python3
"""Stable entry point for the skill: `python3 bin/podcast-kg.py <args>`.

Why this exists: a skill is just files, and marketplaces deliver text files with
no install hook. So the agent gets exactly one command to remember. This
launcher finds an existing `podcast-kg`, and when there is none it runs the
bundled bootstrap once (private venv + PATH shim), then executes the CLI with
the same arguments.

    python3 bin/podcast-kg.py doctor
    python3 bin/podcast-kg.py transcribe ep42.mp3 --model small --lang zh

Exit codes are the CLI's own (0 success, 1 failure, 130 interrupted). If the
runtime cannot be installed, the bootstrap error is printed and its exit code
is returned.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_bootstrap():
    """Import the sibling bootstrap.py without depending on the package name."""
    spec = importlib.util.spec_from_file_location("_pk_bootstrap", HERE / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_pk_bootstrap"] = module  # dataclasses / introspection want this
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = list(sys.argv[1:] if argv is None else argv)
    bootstrap = load_bootstrap()
    home = bootstrap.runtime_home()
    cli = bootstrap.find_cli(home)

    if cli is None:
        if args and args[0] in ("-h", "--help", "--version"):
            print(
                "podcast-kg is not installed yet.\n"
                "Run any command through this launcher and it installs first, e.g.:\n"
                f"  python3 {Path(__file__).as_posix()} doctor",
                file=sys.stderr,
            )
            return 0
        print("[podcast-kg] runtime not found; installing it once …", file=sys.stderr, flush=True)
        code = bootstrap.main([])
        if code != 0:
            return code
        cli = bootstrap.find_cli(home)
        if cli is None:
            print("[podcast-kg] install reported success but no CLI was found", file=sys.stderr)
            return 1

    return subprocess.call(bootstrap.cli_command(Path(cli), args))


if __name__ == "__main__":
    raise SystemExit(main())
