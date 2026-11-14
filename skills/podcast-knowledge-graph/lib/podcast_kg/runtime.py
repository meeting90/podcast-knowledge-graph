"""Runtime glue for the bundled skill.

Skill files alone cannot transcribe anything: `podcast-kg` and its optional
dependencies must exist. So every install carries

  * `runtime.json` — the exact version this skill was installed with, and
  * `bin/bootstrap.py` — a stdlib-only installer that turns "files on disk"
    into "working CLI" (private venv + PATH shim), idempotently.

This module writes that pin, exposes the bootstrap to `podcast-kg bootstrap`,
and reports the runtime state for `doctor` / `install-skill --verify`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__

SKILL_NAME = "podcast-knowledge-graph"
PIN_FILE = "runtime.json"
BOOTSTRAP = Path("bin") / "bootstrap.py"
IS_WIN = sys.platform == "win32"


def skill_dir() -> Path | None:
    """The bundled skill folder, whether installed from a wheel or a checkout."""
    packaged = Path(__file__).resolve().parent / "skill"
    if (packaged / "SKILL.md").is_file():
        return packaged
    fallback = Path(__file__).resolve().parent.parent.parent / "skills" / SKILL_NAME
    if (fallback / "SKILL.md").is_file():
        return fallback
    # vendored: <skill>/lib/podcast_kg/runtime.py -> <skill>
    vendored = Path(__file__).resolve().parent.parent.parent
    if (vendored / "SKILL.md").is_file() and (vendored / "lib" / "podcast_kg").is_dir():
        return vendored
    return None


def bootstrap_script(root: Path | None = None) -> Path:
    root = root or skill_dir()
    if root is None:
        raise RuntimeError("找不到随包分发的 skill 目录（重装 podcast-kg 可修复）")
    script = Path(root) / BOOTSTRAP
    if not script.is_file():
        raise RuntimeError(f"找不到 {script}（skill 包不完整，重装 podcast-kg 可修复）")
    return script


def pin_payload() -> dict:
    return {
        "package": "podcast-kg",
        "version": __version__,
        "extras": ["all"],
        "deps": ["faster-whisper>=1.0.0", "av>=11,<19"],
        "requires_python": ">=3.10",
        "entry": "podcast-kg",
        "bootstrap": BOOTSTRAP.as_posix(),
        "install_from_git": "git+https://github.com/meeting90/podcast-knowledge-graph",
        "git_rev": "",
        "note": "CLI 随 skill 分发（lib/）。bin/bootstrap.py 只把转写依赖装进私有 venv。",
    }


def write_pin(root: Path, force: bool = True) -> Path | None:
    """Write `runtime.json` so the skill always names the CLI that can run it."""
    target = Path(root) / PIN_FILE
    if not force:
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = None
        if isinstance(current, dict) and current.get("version") == __version__:
            return None
    try:
        target.write_text(
            json.dumps(pin_payload(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        print(f"[podcast-kg] 无法写入 {target}：{exc}", file=sys.stderr)
        return None
    return target


def run_bootstrap(argv: list[str]) -> int:
    """Delegate to the skill's own bootstrap (one implementation, no drift)."""
    from_subprocess = [sys.executable, str(bootstrap_script()), *argv]
    try:
        return subprocess.call(from_subprocess)
    except OSError as exc:
        print(f"podcast-kg: 无法执行 bootstrap：{exc}", file=sys.stderr)
        return 1


def runtime_home(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("PODCAST_KG_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "podcast-kg"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "podcast-kg"
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / "podcast-kg"


def cli_version(cli: str | Path | None) -> str | None:
    if not cli:
        return None
    try:
        proc = subprocess.run(
            [str(cli), "--version"], capture_output=True, timeout=30, text=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    for token in proc.stdout.split():
        if token[:1].isdigit():
            return token
    return None


def status() -> dict:
    """What `doctor` / `--verify` report about the runtime side of the skill."""
    from .deps import has_module
    from .models import DEFAULT_MODEL, models_root, status as model_status

    home = runtime_home()
    venv_cli = home / "venv" / ("Scripts/podcast-kg.exe" if IS_WIN else "bin/podcast-kg")
    path_cli = shutil.which("podcast-kg")
    found = str(venv_cli) if venv_cli.is_file() else path_cli
    version = cli_version(found) if found else None
    root = skill_dir()
    script = root / BOOTSTRAP if root else None

    notes: list[str] = []
    if not found:
        notes.append(
            "podcast-kg 不在 PATH：运行 bin/bootstrap.py（或 pip/pipx/uv tool 安装）"
        )
    elif not path_cli:
        notes.append(
            f"私有 venv 里已有 CLI，但不在 PATH：{home / 'bin'}（重跑 bootstrap 会写 shim）"
        )
    elif version and version != __version__:
        notes.append(f"PATH 上是 {version}，skill 期望 {__version__}（--help 为准则可忽略）")
    if script is None or not script.is_file():
        notes.append("skill 目录缺少 bin/bootstrap.py（重装 skill 可修复）")

    return {
        "ready": bool(found and version),
        "on_path": bool(path_cli),
        "cli": found,
        "version": version,
        "pinned": __version__,
        "skill_dir": str(root) if root else None,
        "bootstrap": str(script) if script else None,
        "runtime_home": str(home),
        "venv_cli": str(venv_cli) if venv_cli.is_file() else None,
        "transcribe_ready": has_module("faster_whisper"),
        "ingest_ready": True,
        "default_model": DEFAULT_MODEL,
        "models_dir": str(models_root()),
        "model": model_status(DEFAULT_MODEL),
        "notes": notes,
    }


def print_status(report: dict) -> None:
    print(f"runtime     {'就绪' if report['ready'] else '未就绪'}  {report['cli'] or '-'}")
    if report["cli"] and report["version"]:
        print(f"版本        {report['version']}（skill pin {report['pinned']}）")
    print(f"转写依赖    {'已安装' if report['transcribe_ready'] else '未安装（首次 transcribe 自动装）'}")
    model = report.get("model") or {}
    if model:
        detail = model.get("status", "未下载")
        extra = "" if detail in ("本地模型", "HF 缓存") else "（podcast-kg models fetch --model {0}）".format(
            report.get("default_model", "small")
        )
        print(f"模型 {report.get('default_model', 'small')}      {detail}{extra}")
    print("图谱快照    纯标准库（ingest 无需额外依赖）")
    if report["bootstrap"]:
        print(f"自愈命令    python3 {report['bootstrap']}")
    for item in report["notes"]:
        print(f"⚠️  {item}")
