"""Whisper 权重管理：不随包内置，但可以一键预取 / 离线指路。

为什么不把模型塞进 skill 或 wheel：

  * 体积：small 486 MB、large-v3 3.1 GB；PyPI 单文件上限 100 MB，git 仓库也不适合
    放二进制大文件，skill 被 npx / 插件市场复制时更会被整包搬走。
  * 版本：权重由 CTranslate2 转换、独立演进，和 CLI 版本解耦更稳；换了模型不必发版。
  * 许可：权重是 MIT，但内置再分发仍需自己承担镜像/校验/更新成本。

所以内置的是「让 transcribe 认得本地权重」的能力：

  1. 预取到 `$PODCAST_KG_HOME/models/<name>` → 之后完全离线（默认就在这里）
  2. `--model-dir` / `PODCAST_KG_MODEL_DIR` 指向任意已下载目录（共享盘、U 盘、内网镜像）
  3. 都不指定时走 HuggingFace 缓存，零配置
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# repo / 体积与 faster-whisper 的 _MODELS 对齐（2026-11 实测 HF API 的总字节数）。
KNOWN: dict[str, dict] = {
    "tiny": {"repo": "Systran/faster-whisper-tiny", "size_mb": 78},
    "base": {"repo": "Systran/faster-whisper-base", "size_mb": 148},
    "small": {"repo": "Systran/faster-whisper-small", "size_mb": 486},
    "medium": {"repo": "Systran/faster-whisper-medium", "size_mb": 1531},
    "large-v3": {"repo": "Systran/faster-whisper-large-v3", "size_mb": 3091},
    "large-v3-turbo": {
        "repo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "size_mb": 1622,
    },
}
DEFAULT_MODEL = "small"
REQUIRED = ("config.json", "model.bin", "tokenizer.json")
VOCAB = ("vocabulary.txt", "vocabulary.json")
PATTERNS = ["*.json", "*.bin", "*.txt"]


def models_root(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("PODCAST_KG_MODEL_DIR")
    if env:
        return Path(env).expanduser().resolve()
    from .runtime import runtime_home

    return runtime_home() / "models"


def model_dir(name: str, root: str | None = None) -> Path:
    return models_root(root) / name


def verify_dir(path: str | Path) -> list[str]:
    """Which required files are missing; empty list means usable."""
    directory = Path(path)
    missing = [name for name in REQUIRED if not (directory / name).is_file()]
    if not any((directory / name).is_file() for name in VOCAB):
        missing.append("vocabulary.txt|vocabulary.json")
    return missing


# ── HuggingFace cache ────────────────────────────────────────────────────────


def hf_cache_roots() -> list[str]:
    """Where huggingface_hub keeps snapshots, in its own precedence order."""
    env = os.environ
    roots: list[str] = []
    for key in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if env.get(key):
            roots.append(env[key])
    if env.get("HF_HOME"):
        roots.append(os.path.join(env["HF_HOME"], "hub"))
    roots.append(os.path.join("~", ".cache", "huggingface", "hub"))
    return [os.path.expanduser(root) for root in roots]


def hf_snapshot(model: str) -> str | None:
    """Path of a complete cached snapshot, or None.

    Answered without importing faster_whisper / huggingface_hub: those imports
    freeze their offline switch, so the check has to happen before them.
    """
    if os.path.isdir(model):
        return model if not verify_dir(model) else None
    if "/" in model:
        wanted = ["models--" + model.replace("/", "--")]
    else:
        wanted = []
    suffix = f"--faster-whisper-{model.rsplit('/', 1)[-1]}"
    for root in hf_cache_roots():
        try:
            entries = os.listdir(root)
        except OSError:
            continue
        for entry in entries:
            if not entry.startswith("models--"):
                continue
            if not (entry in wanted or entry.endswith(suffix)):
                continue
            snapshots = os.path.join(root, entry, "snapshots")
            try:
                revisions = os.listdir(snapshots)
            except OSError:
                continue
            for revision in revisions:
                candidate = os.path.join(snapshots, revision)
                if os.path.isfile(os.path.join(candidate, "model.bin")):
                    return candidate
    return None


def is_cached(model: str) -> bool:
    return hf_snapshot(model) is not None


# ── resolution ───────────────────────────────────────────────────────────────


def resolve_source(model: str, model_dir_override: str | None = None) -> tuple[str, str]:
    """Return (what to hand to WhisperModel, human explanation)."""
    path = Path(model).expanduser()
    if path.is_dir():
        missing = verify_dir(path)
        if missing:
            raise SystemExit(
                f"{path} 不像一个完整的 whisper 模型目录（缺 {', '.join(missing)}）。\n"
                "  用 `podcast-kg models fetch --model <name>` 重新下载，或指向正确的目录。"
            )
        return str(path), f"本地模型目录（--model 传入）：{path}"

    root = models_root(model_dir_override)
    local = root / model
    if local.is_dir():
        missing = verify_dir(local)
        if missing:
            raise SystemExit(
                f"{local} 不完整（缺 {', '.join(missing)}）。\n"
                f"  重跑：podcast-kg models fetch --model {model}"
            )
        return str(local), f"本地模型目录（{root}）"

    snapshot = hf_snapshot(model)
    if snapshot:
        return model, f"HF 缓存（{snapshot}）"
    return model, "本地无缓存，走 Hub 下载"


def offline_requested() -> bool:
    for key in ("PODCAST_KG_OFFLINE", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        if os.environ.get(key) not in (None, "", "0", "false"):
            return True
    return False


def offline_hint(model: str) -> str:
    return (
        f"离线模式（PODCAST_KG_OFFLINE / HF_HUB_OFFLINE=1）但没有 {model} 的本地权重。\n"
        f"  预取一次：podcast-kg models fetch --model {model}\n"
        "  或把已下载的目录用 --model-dir / PODCAST_KG_MODEL_DIR 指过来"
    )


# ── status / fetch ───────────────────────────────────────────────────────────


def status(name: str, root: str | None = None) -> dict:
    local = model_dir(name, root)
    if local.is_dir():
        missing = verify_dir(local)
        state = "本地不完整" if missing else "本地模型"
        return {
            "name": name,
            "size_mb": KNOWN.get(name, {}).get("size_mb"),
            "status": state,
            "path": str(local),
            "missing": missing,
        }
    snapshot = hf_snapshot(name)
    if snapshot:
        return {
            "name": name,
            "size_mb": KNOWN.get(name, {}).get("size_mb"),
            "status": "HF 缓存",
            "path": snapshot,
            "missing": [],
        }
    return {
        "name": name,
        "size_mb": KNOWN.get(name, {}).get("size_mb"),
        "status": "未下载",
        "path": str(local),
        "missing": [],
    }


def status_list(root: str | None = None) -> list[dict]:
    return [status(name, root) for name in KNOWN]


def _materialize(directory: Path) -> None:
    """Replace symlinks with real files so the folder can be copied/shipped."""
    for path in directory.rglob("*"):
        try:
            if path.is_symlink():
                target = path.resolve()
                path.unlink()
                shutil.copy2(target, path)
        except OSError:
            continue


def fetch(
    names: list[str],
    root: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    quiet: bool = False,
) -> list[dict]:
    """Download models into `<root>/<name>` and return one report per model."""
    if "all" in names:
        names = list(KNOWN)
    unknown = [name for name in names if name not in KNOWN]
    if unknown:
        raise SystemExit(
            f"未知模型：{', '.join(unknown)}；可选：{', '.join(KNOWN)}"
            "（要装任意 HF 仓库，直接把 repo id 传给 transcribe --model）"
        )

    destination_root = models_root(root)
    reports: list[dict] = []
    planned = 0.0
    download = []

    for name in names:
        destination = destination_root / name
        already = destination.is_dir() and not verify_dir(destination)
        report = {
            "name": name,
            "path": str(destination),
            "size_mb": KNOWN[name]["size_mb"],
            "repo": KNOWN[name]["repo"],
        }
        if already and not force:
            report["action"] = "already-present"
            reports.append(report)
            continue
        report["action"] = "would-fetch" if dry_run else "fetched"
        planned += KNOWN[name]["size_mb"]
        download.append((name, destination, report))
        reports.append(report)

    if dry_run or not download:
        return reports

    from .deps import ensure

    ensure("huggingface_hub", "huggingface-hub>=0.19")
    from huggingface_hub import snapshot_download

    for name, destination, report in download:
        if not quiet:
            print(
                f"[podcast-kg] 下载 {name}（约 {KNOWN[name]['size_mb']} MB）→ {destination}",
                flush=True,
            )
        snapshot_download(
            repo_id=KNOWN[name]["repo"],
            local_dir=str(destination),
            allow_patterns=PATTERNS,
        )
        _materialize(destination)
        shutil.rmtree(destination / ".cache", ignore_errors=True)
        missing = verify_dir(destination)
        if missing:
            report["action"] = "failed"
            report["missing"] = missing
        else:
            report.setdefault("missing", [])
    return reports
