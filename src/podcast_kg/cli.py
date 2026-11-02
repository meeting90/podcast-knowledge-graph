"""Command line interface for podcast-kg.

Subcommands:
  transcribe  audio -> timestamped transcript (.outputs/)
  render      knowledge card JSON -> single-file HTML
  verify      cross-card entity/person normalisation + coverage checks
  ingest      knowledge card JSON -> Semantica graph snapshot
  setup       install the bundled Pi skill (+ APPEND_SYSTEM.md block)
  unsetup     remove that installation
  doctor      environment check / optional dependency install
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__


def cmd_transcribe(args: argparse.Namespace) -> int:
    from .transcribe import transcribe_file

    transcribe_file(
        args.audio,
        args.out,
        model_size=args.model,
        language=args.lang,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam,
    )
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from .outputs import ensure_parent, out_path, stem
    from .render_card import render

    card = json.load(open(args.card, encoding="utf-8"))
    out = args.out or out_path(stem(args.card) + ".html")
    html = render(card, args.seg, mode=args.mode, chrome=not args.no_chrome)
    ensure_parent(out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    relations = sum(len(c.get("relations", [])) for c in card.get("claims", []))
    print(f"内联片段: {html.count('\"b64\"')} 段")
    print(f"HTML: {out} ({len(card.get('claims', []))} claims, {relations} relations)")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .verify_cards import coverage, verify, write_registry

    if args.build_registry:
        if not args.cards:
            raise SystemExit("--build-registry 需要至少一个知识卡 JSON")
        write_registry(args.build_registry, args.cards)
    elif args.coverage:
        coverage(args.coverage, args.transcript)
    else:
        if not args.cards:
            raise SystemExit("请提供至少一个知识卡 JSON（或使用 --build-registry/--coverage）")
        verify(args.cards)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest_graph import ingest

    ingest(args.card, args.out)
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    from .pi_skill import install, pretty

    result = install(
        scope=args.scope,
        project=args.project,
        agent_dir_override=args.agent_dir,
        force=args.force,
        dry_run=args.dry_run,
    )
    skill_dir = Path(result["skill_dir"])
    append_file = Path(result["append_file"])

    verb = {
        "installed": "已安装",
        "updated": "已更新",
        "would-install": "将安装",
        "would-update": "将更新",
        "exists": "已存在（跳过）",
    }[result["skill_action"]]
    print(f"skill  {verb}  {pretty(skill_dir)}")
    if result["skill_action"] == "exists":
        print("       加 --force 覆盖已存在的安装")

    prompt_verb = {
        "created": "已写入",
        "appended": "已追加",
        "updated": "已更新",
        "unchanged": "无变化",
    }[result["prompt_action"]]
    if args.dry_run and result["prompt_action"] != "unchanged":
        prompt_verb = "将" + prompt_verb[1:]
    print(f"prompt {prompt_verb}  {pretty(append_file)}")

    if result.get("other_scope"):
        print(
            f"注意     {pretty(Path(result['other_scope']))} 也已有一份；"
            "Pi 遇到同名 skill 会保留先发现的（用户级优先）并给出警告"
        )

    if args.dry_run:
        print("（--dry-run：未写入任何文件）")
    else:
        print("在 Pi 里执行 /reload 或重启后即可 /skill:podcast-knowledge-graph")
    return 0


def cmd_unsetup(args: argparse.Namespace) -> int:
    from .pi_skill import pretty, uninstall

    result = uninstall(
        scope=args.scope,
        project=args.project,
        agent_dir_override=args.agent_dir,
        dry_run=args.dry_run,
    )
    print(f"skill  {result['skill_action']}  {pretty(Path(result['skill_dir']))}")
    print(f"prompt {result['prompt_action']}  {pretty(Path(result['append_file']))}")
    return 0


def transcribe_caps(device: str = "auto") -> dict:
    """Environment facts for `doctor`: what `transcribe` would actually do here."""
    from .transcribe import MIN_AV, resolve_runtime

    caps: dict = {}
    try:
        import ctranslate2

        caps["ctranslate2"] = ctranslate2.__version__
        caps["cuda_devices"] = ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001 - probing only
        caps["ctranslate2"] = None
        caps["cuda_devices"] = 0

    try:
        import av

        version = str(av.__version__)
        caps["pyav"] = version
        caps["pyav_compatible"] = int(version.split(".")[0] or 0) < MIN_AV
    except Exception:  # noqa: BLE001
        caps["pyav"] = None
        caps["pyav_compatible"] = True

    model, dev, compute, beam = resolve_runtime(None, device, None, None)
    caps["transcribe"] = {"model": model, "device": dev, "compute_type": compute, "beam": beam}
    return caps


def cmd_doctor(args: argparse.Namespace) -> int:
    from .deps import ensure, has_module
    from .pi_skill import installed, pretty

    if args.install:
        targets = {
            "transcribe": [("faster_whisper", "faster-whisper>=1.0.0")],
            "graph": [("semantica", "semantica>=0.7.0")],
        }
        wanted = (
            targets["transcribe"] + targets["graph"]
            if args.install == "all"
            else targets[args.install]
        )
        for module, spec in wanted:
            ensure(module, spec)

    info = {
        "podcast_kg": __version__,
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "package_dir": str(Path(__file__).resolve().parent),
        "cwd": os.getcwd(),
        "outputs_dir": os.path.abspath(".outputs"),
        "ffmpeg": shutil.which("ffmpeg"),
        "faster_whisper": has_module("faster_whisper"),
        "semantica": has_module("semantica"),
        "auto_install": not os.environ.get("PODCAST_KG_NO_AUTO_INSTALL"),
        "skill_installed": installed(agent_dir_override=args.agent_dir),
    }
    info.update(transcribe_caps(args.device))
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    print(f"podcast-kg  {info['podcast_kg']}")
    print(f"python      {info['python']}  ({info['python_executable']})")
    print(f"包目录      {info['package_dir']}")
    print(f"ffmpeg      {info['ffmpeg'] or '未找到（用 PyAV 直接解码，ffmpeg 只影响解码路径，不影响识别质量）'}")
    print(f"faster-whisper  {'已安装' if info['faster_whisper'] else '未安装（首次 transcribe 自动安装）'}")
    print(f"semantica   {'已安装' if info['semantica'] else '未安装（首次 ingest 自动安装）'}")
    print(f"输出目录    {info['outputs_dir']}")

    if info["faster_whisper"]:
        cuda = info.get("cuda_devices", 0)
        print(
            "转写运行配置 {device}/{compute_type} · {model} · beam {beam}".format(**info["transcribe"])
        )
        print(
            f"ctranslate2 {info.get('ctranslate2') or '未安装'}  CUDA 设备 {cuda}"
            + ("" if cuda else "  ← 无可用 CUDA，将用 CPU（慢一个量级）")
        )
        print(f"PyAV        {info.get('pyav') or '未安装'}")
        if not info.get("pyav_compatible", True):
            print(
                "⚠️ PyAV 与 faster-whisper 不兼容（av 19 移除了 av.open(metadata_errors=…)），"
                '转写会直接报错。修复：pip install "av<19"'
            )

    user_skill = info["skill_installed"]["user"]
    project_skill = info["skill_installed"]["project"]
    if user_skill:
        print(f"Pi skill    用户级  {pretty(Path(user_skill))}")
    if project_skill:
        print(f"Pi skill    项目级  {pretty(Path(project_skill))}")
    if not user_skill and not project_skill:
        print("Pi skill    未安装  ← 运行 `podcast-kg setup` 安装")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Delegates to .args so `--help` text lives next to the arg definitions."""
    from .args import build_parser as _build

    return _build()


COMMANDS = {
    "transcribe": cmd_transcribe,
    "render": cmd_render,
    "verify": cmd_verify,
    "ingest": cmd_ingest,
    "setup": cmd_setup,
    "unsetup": cmd_unsetup,
    "doctor": cmd_doctor,
}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    command = getattr(args, "name", args.command)
    handler = COMMANDS[command]
    try:
        return handler(args) or 0
    except KeyboardInterrupt:
        return 130
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"podcast-kg: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
