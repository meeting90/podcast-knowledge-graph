"""Runtime glue for the bundled skill.

The CLI ships inside the skill (`lib/podcast_kg`), so nothing is installed.
This module writes the `runtime.json` pin, reports whether the bundled CLI and
the optional transcribe runtime are available, and feeds `doctor`.
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


def pin_payload() -> dict:
    return {
        "package": "podcast-kg",
        "version": __version__,
        "requires_python": ">=3.10",
        "entry": "bin/podcast-kg.py",
        "note": "CLI 随 skill 分发（lib/），无需安装；transcribe 需要环境里已有 faster-whisper。",
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
    root = skill_dir()
    bundled = bool(root and (root / "lib" / "podcast_kg" / "cli.py").is_file())
    path_cli = shutil.which("podcast-kg")
    version = __version__ if bundled else (cli_version(path_cli) if path_cli else None)

    notes: list[str] = []
    if not has_module("faster_whisper"):
        notes.append(
            "转写依赖 faster-whisper 不在当前环境：skill 不安装任何东西；"
            "需要转写时请提供转写稿，或由环境预装运行时"
        )
    if not bundled and not path_cli:
        notes.append("skill 缺少 lib/podcast_kg（重装 skill 可修复）")

    return {
        "ready": bool(bundled or (path_cli and version)),
        "bundled": bundled,
        "on_path": bool(path_cli),
        "cli": str(root / "lib" / "podcast_kg") if bundled else path_cli,
        "version": version,
        "pinned": __version__,
        "skill_dir": str(root) if root else None,
        "runtime_home": str(home),
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
    print(
        "转写依赖    "
        + ("已安装" if report["transcribe_ready"] else "未安装（skill 不会安装；需要时请提供转写稿或预装）")
    )
    model = report.get("model") or {}
    if model:
        detail = model.get("status", "未下载")
        extra = "" if detail in ("本地模型", "HF 缓存") else "（podcast-kg models fetch --model {0}）".format(
            report.get("default_model", "small")
        )
        print(f"模型 {report.get('default_model', 'small')}      {detail}{extra}")
    print("图谱快照    纯标准库（ingest 无需额外依赖）")
    if report.get("notes") and not report["transcribe_ready"]:
        print("提示        转写需要 faster-whisper；本 skill 不安装，其他命令不受影响")
    for item in report["notes"]:
        print(f"⚠️  {item}")
