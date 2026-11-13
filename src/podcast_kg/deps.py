"""Optional runtime dependency handling.

The base install stays dependency-free so `render` / `verify` / `setup` work
offline. Heavy command-specific packages are installed on first use into the
interpreter that is already running the CLI:

  * managed by pip      -> `python -m pip install <spec>`
  * managed by uv tool  -> `uv pip install --python <python> <spec>`
                         (uv tool venvs ship without pip)
  * neither available   -> a message naming the exact install command

Set PODCAST_KG_NO_AUTO_INSTALL=1 to disable and install manually.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys

_HINT = {
    "faster_whisper": "faster-whisper>=1.0.0",
}


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _run(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd).returncode == 0
    except OSError:
        return False


def _install(spec: str) -> bool:
    if has_module("pip"):
        if _run([sys.executable, "-m", "pip", "install", spec]):
            return True

    for name in ("uv", "pipx"):
        exe = shutil.which(name)
        if not exe:
            continue
        if name == "uv":
            if _run([exe, "pip", "install", "--python", sys.executable, spec]):
                return True
        else:  # pipx inject <venv-name> <spec> is only meaningful for pipx venvs
            if _run([exe, "inject", "--force", os.path.basename(os.path.dirname(sys.executable)), spec]):
                return True

    return False


def manual_hint(spec: str) -> str:
    uv = shutil.which("uv")
    if uv:
        return f'{uv} pip install --python "{sys.executable}" "{spec}"'
    return f'"{sys.executable}" -m pip install "{spec}"'


def ensure(module: str, spec: str | None = None) -> None:
    """Import-time guard: install `spec` if `module` is missing."""
    if has_module(module):
        return

    spec = spec or _HINT.get(module, module)

    if os.environ.get("PODCAST_KG_NO_AUTO_INSTALL"):
        raise SystemExit(f"缺少依赖 {spec}。请运行：{manual_hint(spec)}")

    print(f"[podcast-kg] 缺少 {module}，正在安装 {spec} …", file=sys.stderr, flush=True)
    if _install(spec) and has_module(module):
        print(f"[podcast-kg] 已安装 {spec}", file=sys.stderr, flush=True)
        return

    raise SystemExit(
        "\n".join(
            [
                f"安装 {spec} 失败。手动安装方式（任选其一）：",
                f"  1) {manual_hint(spec)}",
                f'  2) uv tool install --reinstall --with "{spec}" podcast-kg',
            ]
        )
    )
