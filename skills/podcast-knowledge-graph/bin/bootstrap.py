#!/usr/bin/env python3
"""podcast-kg runtime bootstrap — stdlib only, safe to run from the skill folder.

An installed skill is just files. This script is the one command that turns
those files into a working runtime: it finds an existing `podcast-kg`, or
installs the pinned version into a private venv and leaves a shim on PATH.

    python3 bin/bootstrap.py            # ensure (idempotent, fast when ready)
    python3 bin/bootstrap.py --check    # only report; exit 1 if not ready
    python3 bin/bootstrap.py --plan     # what would happen, touches nothing
    python3 bin/bootstrap.py --json     # machine-readable report

Exit codes: 0 ready / 1 not ready or install failed / 2 bad usage.

Install order: existing CLI on PATH → private venv via uv → private venv via
uv-managed Python → python -m venv + pip. Nothing is installed outside
$PODCAST_KG_HOME (default: XDG data dir / %LOCALAPPDATA%) except the shims.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# The pin is embedded so this script still works when it is copied alone to a
# temp file (marketplaces execute each script standalone, without the package
# around it). `runtime.json` overrides these when the skill folder is intact.
PIN_VERSION = "0.1.0"
PIN_EXTRAS = ["all"]
PIN_GIT = "git+https://github.com/meeting90/podcast-knowledge-graph"
DEFAULT_PIN = {
    "package": "podcast-kg",
    "version": PIN_VERSION,
    "extras": PIN_EXTRAS,
    "requires_python": ">=3.10",
    "install_from_git": PIN_GIT,
}
DEFAULT_PYTHON = "3.12"
IS_WIN = sys.platform == "win32"


# ── reporting ────────────────────────────────────────────────────────────────


def note(message: str, quiet: bool = False, stream=None) -> None:
    if not quiet:
        print(message, file=stream or sys.stderr, flush=True)


def tail(text: str, lines: int = 3) -> str:
    parts = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " … ".join(parts[-lines:])


# ── paths ────────────────────────────────────────────────────────────────────


def home_dir() -> Path:
    """Path.home() raises when HOME/USERPROFILE is unset (containers, CI)."""
    try:
        return Path.home()
    except RuntimeError:
        raw = os.environ.get("HOME") or os.environ.get("USERPROFILE") or os.getcwd()
        return Path(raw)


def runtime_home(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("PODCAST_KG_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or (home_dir() / "AppData" / "Local")
        return Path(base) / "podcast-kg"
    if sys.platform == "darwin":
        return home_dir() / "Library" / "Application Support" / "podcast-kg"
    base = os.environ.get("XDG_DATA_HOME") or (home_dir() / ".local" / "share")
    return Path(base) / "podcast-kg"


def venv_python(home: Path) -> Path:
    return home / "venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")


def venv_cli(home: Path) -> Path:
    return home / "venv" / ("Scripts/podcast-kg.exe" if IS_WIN else "bin/podcast-kg")


def shim_dir(home: Path) -> Path:
    return home / "bin"


def shim_candidates(home: Path) -> list[Path]:
    directory = shim_dir(home)
    return [directory / "podcast-kg.exe", directory / "podcast-kg.cmd", directory / "podcast-kg"]


# ── pin ──────────────────────────────────────────────────────────────────────


def load_pin(skill_root: Path) -> dict:
    pin = dict(DEFAULT_PIN)
    path = skill_root / "runtime.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            pin.update(data)
    except OSError:
        pass
    except ValueError:
        note(f"[bootstrap] {path} 不是合法 JSON，按默认 pin 处理")
    return pin


def pip_spec(pin: dict, extras_override: str | None = None) -> str:
    package = pin.get("package") or "podcast-kg"
    extras = resolve_extras(pin, extras_override)
    name = package + (f"[{','.join(extras)}]" if extras else "")
    version = str(pin.get("version") or "").strip()
    if not version or version in ("latest", "any", "*"):
        return name
    if version[0].isdigit():
        version = "==" + version
    return name + version


def resolve_extras(pin: dict, extras_override: str | None = None) -> list[str]:
    if extras_override is not None:
        return [] if extras_override in ("none", "base", "") else extras_override.split(",")
    extras = pin.get("extras") or []
    return list(extras) if isinstance(extras, list) else [str(extras)]


def local_project(skill_root: Path) -> Path | None:
    """A source checkout can be installed without PyPI (repo/dev installs)."""
    candidates = [skill_root.parent.parent, skill_root.parent, Path.cwd()]
    for candidate in candidates:
        pyproject = candidate / "pyproject.toml"
        try:
            text = pyproject.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if 'name = "podcast-kg"' in text and (candidate / "src" / "podcast_kg").is_dir():
            return candidate
    return None


# ── process helpers ──────────────────────────────────────────────────────────


def run(cmd: list[str], capture: bool = False) -> tuple[int, str]:
    env = None
    if IS_WIN and not os.environ.get("PATHEXT"):
        # uv resolves `git` through PATHEXT; a stripped environment (CI,
        # containers, some sandboxes) otherwise fails with "Git executable
        # not found" even though git is on PATH.
        env = dict(os.environ, PATHEXT=".COM;.EXE;.BAT;.CMD")
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            env=env,
        )
    except OSError as exc:
        return 127, str(exc)
    output = ""
    if capture and proc.stdout:
        output = proc.stdout.decode("utf-8", "replace")
    return proc.returncode, output


def cli_command(cli: Path, extra: list[str]) -> list[str]:
    # .cmd/.bat cannot be spawned directly by CreateProcess on older Pythons
    if IS_WIN and cli.suffix.lower() in (".cmd", ".bat"):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/c", str(cli), *extra]
    return [str(cli), *extra]


def cli_version(cli: Path) -> str | None:
    code, output = run(cli_command(cli, ["--version"]), capture=True)
    if code != 0:
        return None
    text = output.strip()
    for token in text.split():
        if token[:1].isdigit():
            return token
    return text or None


def find_cli(home: Path) -> Path | None:
    override = os.environ.get("PODCAST_KG_BIN")
    if override and Path(override).expanduser().is_file():
        return Path(override).expanduser()
    # our own venv shim first: it is the install this skill pinned
    for candidate in shim_candidates(home):
        if candidate.is_file() and cli_version(candidate):
            return candidate
    found = shutil.which("podcast-kg")
    return Path(found) if found else None


def find_executable(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    extra = [home_dir() / ".local" / "bin", home_dir() / ".cargo" / "bin"]
    for directory in extra:
        for candidate in (
            directory / name,
            directory / (name + ".exe"),
            directory / (name + ".cmd"),
        ):
            if candidate.is_file():
                return candidate
    return None


def find_python(hint: str | None = None) -> Path | None:
    names: list[str] = []
    if hint:
        names.append(hint)
    env_hint = os.environ.get("PODCAST_KG_PYTHON")
    if env_hint:
        names.append(env_hint)
    names += ["python", "python3"] if IS_WIN else ["python3", "python"]
    for name in names:
        path = Path(name) if os.sep in name or "/" in name else find_executable(name)
        if not path:
            continue
        code, output = run(
            [str(path), "-c", "import sys;print('%d.%d' % sys.version_info[:2])"], capture=True
        )
        if code != 0:
            continue
        try:
            major, minor = (int(part) for part in output.strip().split(".")[:2])
        except ValueError:
            continue
        if (major, minor) >= (3, 10):
            return path
    return None


# ── install ──────────────────────────────────────────────────────────────────


def candidate_specs(
    pin: dict, extras_override: str | None, local: Path | None
) -> list[tuple[str, str]]:
    """Where the package can come from, best first.

    local checkout → PyPI pin → git fallback. The git hop keeps a hand-copied
    skill usable before (or instead of) the package being published.
    """
    extras = resolve_extras(pin, extras_override)
    suffix = f"[{','.join(extras)}]" if extras else ""
    specs: list[tuple[str, str]] = []
    if local:
        specs.append(("local", f"{local}{suffix}"))
    specs.append(("pypi", pip_spec(pin, extras_override)))
    git = str(pin.get("install_from_git") or "").strip()
    if git:
        package = pin.get("package") or "podcast-kg"
        rev = str(pin.get("git_rev") or "").strip()
        url = f"{git}@{rev}" if rev else git
        specs.append(("git", f"{package}{suffix} @ {url}"))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for kind, spec in specs:
        if spec not in seen:
            seen.add(spec)
            unique.append((kind, spec))
    return unique


def install_with_uv(
    uv: Path,
    home: Path,
    candidates: list[tuple[str, str]],
    python_hint: str | None,
    quiet: bool,
) -> tuple[Path, str]:
    venv = home / "venv"
    python = venv_python(home)
    if not python.is_file():
        # `uv venv --python 3.12` downloads a managed interpreter when the host
        # has none, which is the only path that works on a bare machine.
        wanted = python_hint or DEFAULT_PYTHON
        note(f"[bootstrap] 创建 venv（uv，Python {wanted}）…", quiet)
        code, output = run(
            [str(uv), "venv", str(venv), "--python", wanted, "--seed", "--quiet", "--clear"],
            capture=True,
        )
        if code != 0:
            raise RuntimeError(f"uv venv 失败：{tail(output)}")
    errors: list[str] = []
    for kind, spec in candidates:
        note(f"[bootstrap] 安装 {spec} …", quiet)
        code, output = run(
            [str(uv), "pip", "install", "--python", str(python), "--quiet", spec],
            capture=True,
        )
        if code == 0:
            return python, spec
        errors.append(f"{kind}：{tail(output)}")
    raise RuntimeError("所有安装来源都失败：" + " | ".join(errors))


def install_with_pip(
    python: Path,
    home: Path,
    candidates: list[tuple[str, str]],
    quiet: bool,
) -> tuple[Path, str]:
    venv = home / "venv"
    venv_py = venv_python(home)
    if not venv_py.is_file():
        note("[bootstrap] 创建 venv（python -m venv）…", quiet)
        code, output = run([str(python), "-m", "venv", "--clear", str(venv)], capture=True)
        if code != 0:
            raise RuntimeError(f"python -m venv 失败：{tail(output)}")
    errors: list[str] = []
    for kind, spec in candidates:
        note(f"[bootstrap] 安装 {spec} …", quiet)
        code, output = run([str(venv_py), "-m", "pip", "install", "--quiet", spec], capture=True)
        if code == 0:
            return venv_py, spec
        errors.append(f"{kind}：{tail(output)}")
    raise RuntimeError("所有安装来源都失败：" + " | ".join(errors))


def write_shims(cli: Path, home: Path) -> list[Path]:
    directory = shim_dir(home)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    shim = directory / ("podcast-kg.cmd" if IS_WIN else "podcast-kg")
    if IS_WIN:
        shim.write_text(f'@echo off\r\n"{cli}" %*\r\n', encoding="utf-8", newline="")
    else:
        shim.write_text(
            '#!/bin/sh\n# Generated by podcast-kg bootstrap.\nexec "'
            + str(cli).replace('"', '\\"')
            + '" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        shim.chmod(0o755)
    written.append(shim)

    # ~/.local/bin is on PATH on most setups; write there too when it exists.
    if not IS_WIN:
        local_bin = home_dir() / ".local" / "bin"
        try:
            if local_bin.is_dir() and os.access(local_bin, os.W_OK):
                extra = local_bin / "podcast-kg"
                extra.write_text(
                    '#!/bin/sh\n# Generated by podcast-kg bootstrap.\nexec "'
                    + str(cli).replace('"', '\\"')
                    + '" "$@"\n',
                    encoding="utf-8",
                    newline="\n",
                )
                extra.chmod(0o755)
                written.append(extra)
        except OSError:
            pass
    return written


MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")
MODEL_VOCAB = ("vocabulary.txt", "vocabulary.json")


def model_ready(home: Path, name: str) -> bool:
    directory = home / "models" / name
    if not directory.is_dir():
        return False
    if not all((directory / item).is_file() for item in MODEL_FILES):
        return False
    return any((directory / item).is_file() for item in MODEL_VOCAB)


def fetch_models(cli: Path, home: Path, names: list[str]) -> tuple[int, str]:
    args = ["models", "fetch", "--dir", str(home / "models")]
    for name in names:
        args += ["--model", name]
    return run(cli_command(cli, args), capture=True)


def write_marker(home: Path, spec: str, python: Path, cli: Path) -> None:
    marker = home / "runtime.json"
    data = {
        "spec": spec,
        "cli": str(cli),
        "python": str(python),
        "python_version": sys.version.split()[0],
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    try:
        home.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        note(f"[bootstrap] 无法写入 {marker}：{exc}")


# ── main ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap",
        description="让 podcast-knowledge-graph skill 的运行时可用：找现有 CLI，或装到私有 venv 并留 shim。",
        epilog=(
            "退出码 0 就绪 / 1 未就绪或安装失败 / 2 参数非法。\n"
            "默认安装位置 $PODCAST_KG_HOME（Windows: %LOCALAPPDATA%\\podcast-kg，"
            "macOS: ~/Library/Application Support/podcast-kg，Linux: ~/.local/share/podcast-kg）。\n"
            "PIN 来自 skill 目录下的 runtime.json；--version/--extras 可临时覆盖。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check", action="store_true", help="只检查，不安装；未就绪退出码 1")
    parser.add_argument("--plan", action="store_true", help="报告将要做什么，不动文件")
    parser.add_argument("--json", action="store_true", dest="as_json", help="机器可读输出")
    parser.add_argument("--quiet", action="store_true", help="不打印过程信息")
    parser.add_argument("--version", dest="pin_version", metavar="SPEC", help="覆盖 pin 的版本（如 0.1.0 / latest）")
    parser.add_argument("--extras", metavar="LIST", help="all（默认）| none | 逗号分隔的 extras")
    parser.add_argument("--home", metavar="DIR", help="覆盖运行时装在哪（默认 $PODCAST_KG_HOME）")
    parser.add_argument("--python", metavar="EXE", help="指定 Python 解释器 / 版本（默认 uv 管理的 3.12）")
    parser.add_argument("--no-shim", action="store_true", help="只装 venv，不写 PATH shim")
    parser.add_argument(
        "--models",
        metavar="LIST",
        help="装完顺手预取 whisper 权重：small / small,base / all / none（默认 none；small 约 486 MB）",
    )
    parser.add_argument("--skill", metavar="DIR", help="skill 根目录（默认本脚本的上一级）")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    skill_root = (
        Path(args.skill).expanduser().resolve()
        if args.skill
        else Path(__file__).resolve().parent.parent
    )
    pin = load_pin(skill_root)
    if args.pin_version:
        pin["version"] = args.pin_version
    spec = pip_spec(pin, args.extras)
    local = local_project(skill_root)
    candidates = candidate_specs(pin, args.extras, local)
    home = runtime_home(args.home)

    found = find_cli(home)
    version = cli_version(found) if found else None
    uv = find_executable("uv")
    python = find_python(args.python)

    report = {
        "ready": bool(found and version),
        "cli": str(found) if found else None,
        "version": version,
        "pinned": spec,
        "source": str(local) if local else None,
        "candidates": [spec for _, spec in candidates],
        "install": None,
        "home": str(home),
        "venv": str(home / "venv"),
        "uv": str(uv) if uv else None,
        "python": str(python) if python else None,
        "action": "none",
        "shims": [],
        "models": {"dir": str(home / "models"), "requested": [], "action": "none"},
        "notes": [],
    }

    requested = []
    raw_models = (args.models or "none").strip()
    if raw_models and raw_models.lower() != "none":
        requested = [part.strip() for part in raw_models.split(",") if part.strip()]
    report["models"]["requested"] = requested

    def with_models(code: int, cli: Path | None) -> int:
        """Optionally pre-download weights, then report."""
        if cli is None or not requested or args.check or args.plan:
            return finish(code)
        pending = (
            requested
            if "all" in requested
            else [name for name in requested if not model_ready(home, name)]
        )
        if not pending:
            report["models"]["action"] = "present"
            return finish(code)
        note(f"[bootstrap] 预取模型 {', '.join(pending)} → {home / 'models'} …", args.quiet)
        status, output = fetch_models(cli, home, pending)
        if status != 0:
            report["models"]["action"] = "failed"
            report["notes"].append(f"模型预取失败：{tail(output)}")
            return finish(1)
        report["models"]["action"] = "fetched"
        report["models"]["ready"] = all(
            "all" in requested or model_ready(home, name) for name in requested
        )
        return finish(code)

    def finish(code: int) -> int:
        if args.as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif code == 0:
            print(f"podcast-kg 就绪  {report['cli']}  ({report['version']})")
            print(f"runtime      {report['home']}")
        else:
            print("podcast-kg 未就绪：运行 bin/bootstrap.py 安装（或看 --json 的 notes）")
        return code

    if report["ready"]:
        if not args.as_json:
            pinned = str(pin.get("version") or "")
            if pinned and pinned not in ("latest", "any", "*") and version != pinned:
                note(f"[bootstrap] 注意：现有 CLI 是 {version}，skill 期望 {pinned}（--version 可覆盖）", args.quiet)
        return with_models(0, found)

    if args.check or args.plan:
        if uv:
            report["action"] = "install-uv"
        elif python:
            report["action"] = "install-pip"
        else:
            report["action"] = "install-blocked"
            report["notes"].append(
                "没有 uv 也没有 Python ≥3.10：先装 uv（https://docs.astral.sh/uv/），"
                "它会连解释器一起准备好"
            )
        return finish(1 if args.check else 0)

    cli: Path | None = None
    try:
        home.mkdir(parents=True, exist_ok=True)
        if uv:
            python, used = install_with_uv(uv, home, candidates, args.python, args.quiet)
        elif python:
            python, used = install_with_pip(python, home, candidates, args.quiet)
        else:
            report["action"] = "install-blocked"
            report["notes"].append(
                "没有 uv 也没有 Python ≥3.10：先装 uv（https://docs.astral.sh/uv/）"
            )
            return finish(1)
        report["install"] = used

        candidate = venv_cli(home)
        if not candidate.is_file():
            report["notes"].append(f"安装完成但找不到 {candidate}")
            return finish(1)
        cli = candidate
        version = cli_version(cli)
        if not version:
            report["notes"].append(f"{cli} --version 执行失败")
            return finish(1)

        if not args.no_shim:
            report["shims"] = [str(path) for path in write_shims(cli, home)]
        write_marker(home, used, python, cli)
        report.update({"ready": True, "cli": str(cli), "version": version, "action": "installed"})
        if not shutil.which("podcast-kg"):
            report["notes"].append(
                f'{shim_dir(home)} 不在 PATH：export PATH="{shim_dir(home)}:$PATH"'
            )
        return with_models(0, cli)
    except RuntimeError as exc:
        report["notes"].append(str(exc))
        return finish(1)
    except OSError as exc:
        report["notes"].append(f"文件操作失败：{exc}")
        return finish(1)


if __name__ == "__main__":
    raise SystemExit(main())
