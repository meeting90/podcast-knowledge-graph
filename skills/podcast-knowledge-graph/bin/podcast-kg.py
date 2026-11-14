#!/usr/bin/env python3
"""Stable entry point for the skill: `python3 bin/podcast-kg.py <args>`.

The CLI ships inside the skill (`lib/podcast_kg`), so most commands need no
installation at all. Only commands that need heavy deps (transcribe, models
fetch) trigger a one-time install of those deps into a private venv; the
vendored CLI is then run with that venv's Python.

Exit codes are the CLI's own (0 success, 1 failure, 130 interrupted).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
LIB = SKILL / "lib"
IS_WIN = sys.platform == "win32"


def load_bootstrap():
    """Import the sibling bootstrap.py without depending on the package name."""
    spec = importlib.util.spec_from_file_location("_pk_bootstrap", HERE / "bootstrap.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_pk_bootstrap"] = module  # dataclasses / introspection want this
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def has_module(python: Path, module: str) -> bool:
    code = subprocess.call(
        [str(python), "-c", f"import {module}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return code == 0


def required_module(args: list[str]) -> str | None:
    """Only these commands pull heavy dependencies."""
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
    bootstrap = load_bootstrap()
    home = bootstrap.runtime_home()

    # An explicit binary always wins (tests, CI, users with a custom install).
    explicit = os.environ.get("PODCAST_KG_BIN")
    if explicit and Path(explicit).is_file():
        return subprocess.call(bootstrap.cli_command(Path(explicit), args))

    vendored = (LIB / "podcast_kg" / "cli.py").is_file()
    if vendored:
        python = bootstrap.venv_python(home)
        if not python.is_file():
            python = Path(sys.executable)
        module = required_module(args)
        if module and not has_module(python, module):
            if os.environ.get("PODCAST_KG_NO_AUTO_INSTALL"):
                print(
                    f"缺少依赖 {module}，且 PODCAST_KG_NO_AUTO_INSTALL 已设置。\n"
                    f"手动安装：python3 {HERE / 'bootstrap.py'}",
                    file=sys.stderr,
                )
                return 1
            print(
                f"[podcast-kg] {args[0]} 需要额外依赖，正在一次性安装到私有 venv …",
                file=sys.stderr,
                flush=True,
            )
            code = bootstrap.main([])
            if code != 0:
                return code
            python = bootstrap.venv_python(home)
            if not has_module(python, module):
                print(f"[podcast-kg] 依赖安装后仍无法导入 {module}", file=sys.stderr)
                return 1
        return run_vendored(python, args)

    # Older installs without lib/: find a real CLI or install the package.
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
