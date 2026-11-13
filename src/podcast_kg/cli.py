"""Command line interface for podcast-kg.

Subcommands:
  transcribe  audio -> timestamped transcript (.outputs/)
  render      knowledge card JSON -> single-file HTML
  verify      cross-card entity/person normalisation + coverage checks
  ingest      knowledge card JSON -> source-linked graph snapshot (stdlib)
  models      whisper weights: list / fetch / path / verify (not bundled)
  i18n        bilingual cards: parity check / translation scaffold
  setup       install the bundled Pi skill (alias: install-skill --target pi)
  unsetup     remove that installation
  install-skill    install the skill into any agent (pi / claude / codex / …)
  uninstall-skill  remove it again
  bootstrap   make the skill's runtime usable (private venv + PATH shim)
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
        words=getattr(args, "words", False),
        model_dir=getattr(args, "model_dir", None),
        carry_context=getattr(args, "carry_context", False),
    )
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    from .models import (
        DEFAULT_MODEL,
        KNOWN,
        fetch,
        models_root,
        resolve_source,
        status,
        status_list,
        verify_dir,
    )

    action = args.action
    names = list(args.model or [DEFAULT_MODEL])

    if action == "list":
        rows = status_list(args.dir)
        if args.json:
            print(
                json.dumps(
                    {"root": str(models_root(args.dir)), "models": rows},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        print(f"模型根目录  {models_root(args.dir)}")
        width = max(len(row["name"]) for row in rows)
        print(f"{'模型'.ljust(width)}  体积      状态        路径")
        for row in rows:
            size = f"{row['size_mb']} MB" if row["size_mb"] else "-"
            print(
                f"{row['name'].ljust(width)}  {size.ljust(8)}  "
                f"{_pad(row['status'], 10)}  {row['path']}"
            )
        return 0

    if action == "fetch":
        reports = fetch(
            names, root=args.dir, dry_run=args.dry_run, force=args.force
        )
        if args.json:
            print(json.dumps({"reports": reports}, ensure_ascii=False, indent=2))
            return 1 if any(r["action"] == "failed" for r in reports) else 0
        for report in reports:
            print(f"{report['name']}: {report['action']} → {report['path']} ({report['size_mb']} MB)")
        if args.dry_run:
            print("（--dry-run：未下载）")
        failed = [r for r in reports if r["action"] == "failed"]
        if failed:
            print(f"以下模型不完整：{', '.join(r['name'] for r in failed)}", file=sys.stderr)
            return 1
        return 0

    if action == "path":
        missing = []
        for name in names:
            info = status(name, args.dir)
            ready = info["status"] in ("本地模型", "HF 缓存")
            if args.json:
                print(json.dumps({"model": name, **info}, ensure_ascii=False, indent=2))
            elif ready:
                print(info["path"])
            else:
                missing.append(name)
                print(
                    f"{name} 未就绪（{info['status']}）：运行 "
                    f"podcast-kg models fetch --model {name}",
                    file=sys.stderr,
                )
        return 1 if missing else 0

    # verify: without --model, only check what is actually present (missing = fine)
    targets = names if args.model else [
        name for name in KNOWN if status(name, args.dir)["status"] != "未下载"
    ]
    results = []
    for name in targets:
        directory = Path(args.dir).expanduser() / name if args.dir else None
        if directory is not None:
            path = directory
        else:
            info = status(name)
            path = Path(info["path"])
        ok = path.is_dir() and not verify_dir(path)
        results.append(
            {
                "model": name,
                "path": str(path),
                "ok": ok,
                "missing": verify_dir(path) if path.is_dir() else ["目录不存在"],
            }
        )
    if not targets:
        if args.json:
            print(json.dumps({"results": []}, ensure_ascii=False, indent=2))
        else:
            print("没有已下载的模型（先 podcast-kg models fetch --model small）")
        return 0
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    else:
        for item in results:
            mark = "✓" if item["ok"] else "✗"
            detail = "完整" if item["ok"] else f"缺 {', '.join(item['missing'])}"
            print(f"{mark} {_pad(item['model'], 16)} {detail}  {item['path']}")
    return 0 if all(item["ok"] for item in results) else 1


def cmd_render(args: argparse.Namespace) -> int:
    from .i18n import check, load as load_card, merge, parse_locale_args
    from .outputs import ensure_parent, out_path, stem
    from .render_card import load_arcs, render

    card = json.load(open(args.card, encoding="utf-8"))
    if not isinstance(card, dict) or not card.get("claims"):
        raise SystemExit(
            f"{args.card} 不像一张知识卡（需要 JSON 对象且带 claims；"
            "转写稿 / 弧层文件请分别用 transcribe / --arcs 传入）"
        )
    arcs = load_arcs(card, args.arcs, args.card)

    locales = parse_locale_args(args.i18n)
    langs = None
    default_lang = args.default_lang
    if locales:
        locale_cards = {lang: load_card(path) for lang, path in locales.items()}
        base_lang = (card.get("source") or {}).get("language") or "zh"
        if base_lang in locale_cards:
            raise SystemExit(
                f"译文卡语言与母卡相同（{base_lang}）：母卡已声明 source.language={base_lang}，"
                "另一份请用不同语言代码（如 --i18n en=...）"
            )
        default_lang = default_lang or base_lang
        others = [lang for lang in locale_cards if lang != base_lang]
        langs = [default_lang, *[lang for lang in [base_lang, *others] if lang != default_lang]]
        if arcs and not card.get("arcs"):
            card = {**card, "arcs": arcs}
        problems: list[str] = []
        for lang, locale_card in locale_cards.items():
            result = check(card, locale_card, lang)
            problems += [f"[{lang}] {error}" for error in result["errors"]]
        if problems:
            sep = chr(10) + "  "
            raise SystemExit(
                "双语卡结构不一致（先跑 podcast-kg i18n check）：" + sep + sep.join(problems)
            )
        card = merge(card, locale_cards, base_lang)
        arcs = card.get("arcs") or arcs

    out = args.out or out_path(stem(args.card) + ".html")
    html = render(
        card,
        args.seg,
        mode=args.mode,
        chrome=not args.no_chrome,
        arcs=arcs,
        langs=langs,
        default_lang=default_lang,
    )
    ensure_parent(out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    relations = sum(len(c.get("relations", [])) for c in card.get("claims", []))
    unit = f"{len(arcs)} 段话题弧" if arcs else "逐句视图"
    languages = f" · {'/'.join(langs)} 可切换" if langs else ""
    print(f"内联片段: {html.count('\"b64\"')} 段")
    print(
        f"HTML: {out} ({len(card.get('claims', []))} claims, {relations} relations, "
        f"{unit}{languages})"
    )
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


def cmd_i18n(args: argparse.Namespace) -> int:
    from .i18n import check, load as load_card, locale_path, scaffold, write
    from .render_card import load_arcs

    base = load_card(args.base)
    arcs = load_arcs(base, args.arcs, args.base)
    if arcs and not base.get("arcs"):
        base = {**base, "arcs": arcs}
    if args.action == "check":
        paths = list(args.locales) or [str(locale_path(args.base, args.lang))]
        existing = [path for path in paths if Path(path).is_file()]
        if not existing:
            hint = chr(10) + "  先生成骨架：podcast-kg i18n scaffold <base> --lang en"
            raise SystemExit(f"找不到译文卡：{', '.join(paths)}" + hint)
        results = [check(base, load_card(path), path) for path in existing]
        if args.json:
            print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        else:
            for result in results:
                mark = "✓" if result["ok"] else "✗"
                print(f"{mark} {result['locale']}")
                for error in result["errors"]:
                    print(f"   错误  {error}")
                for warning in result["warnings"]:
                    print(f"   未翻译 {warning}")
        return 0 if all(result["ok"] for result in results) else 1

    target = Path(args.out) if args.out else locale_path(args.base, args.lang)
    if target.exists() and not args.force:
        raise SystemExit(f"{target} 已存在（--force 覆盖）")
    write(scaffold(base, args.lang), target)
    print(f"译文骨架: {target}（id / 时间戳 / 分组已保留，填文字字段）")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from .ingest_graph import ingest

    ingest(args.card, args.out)
    return 0


def cmd_install_skill(args: argparse.Namespace) -> int:
    from .skill_install import install, plan, pretty, target_table, verify

    if args.list_targets:
        print(target_table())
        return 0
    if args.skills_dir and args.target:
        raise SystemExit("--skills-dir 与 --target 不能同时用（自定义目录不需要目标 agent）")

    plan_kwargs = dict(
        targets=args.target,
        scope=args.scope,
        project=args.project,
        agent_dir=args.agent_dir,
        pointer=not args.no_pointer,
        skills_dir=args.skills_dir,
        instructions=args.instructions,
    )

    if args.verify:
        checks = verify(plan(**plan_kwargs))
        for item in checks:
            print(f"{'✓' if item['ok'] else '✗'} {_pad(item['label'], 18)} {item['detail']}")
        failed = [item for item in checks if not item["ok"]]
        if failed:
            print(
                "\n修复：`podcast-kg bootstrap`（装 CLI）；"
                "`podcast-kg install-skill --force`（补文件与 runtime.json）",
                file=sys.stderr,
            )
            return 1
        print("\n运行时与安装均就绪。")
        return 0

    result = install(force=args.force, dry_run=args.dry_run, **plan_kwargs)
    if args.json:
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0
    _print_results(result, pretty)
    if not _has_action(result, "skill"):
        return 0
    print()
    if args.dry_run:
        print("（--dry-run：未写入任何文件）")
    else:
        from . import __version__

        print(f"runtime pin  {__version__}（写进每个 skill 目录的 runtime.json）")
        print(
            "重开 agent 会话（Pi 用 /reload）后，skill `podcast-knowledge-graph` 即可被发现；"
            "不认 skill 格式的 agent 会从上面的指令文件找到它。"
        )
        print("运行时自检：`podcast-kg install-skill --verify`；缺 CLI 时：`podcast-kg bootstrap`")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    from .runtime import run_bootstrap

    argv: list[str] = []
    for flag, attribute in (
        ("--check", "check"),
        ("--plan", "plan"),
        ("--json", "json"),
        ("--quiet", "quiet"),
        ("--no-shim", "no_shim"),
    ):
        if getattr(args, attribute):
            argv.append(flag)
    for flag, attribute in (
        ("--version", "pin_version"),
        ("--extras", "extras"),
        ("--home", "home"),
        ("--python", "python"),
    ):
        value = getattr(args, attribute)
        if value:
            argv.extend([flag, value])
    return run_bootstrap(argv)


def cmd_uninstall_skill(args: argparse.Namespace) -> int:
    from .skill_install import pretty, uninstall

    if args.skills_dir and args.target:
        raise SystemExit("--skills-dir 与 --target 不能同时用")
    result = uninstall(
        targets=args.target,
        scope=args.scope,
        project=args.project,
        agent_dir=args.agent_dir,
        dry_run=args.dry_run,
        skills_dir=args.skills_dir,
        instructions=args.instructions,
    )
    if args.json:
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0
    _print_results(result, pretty, verb_map=_REMOVE_VERBS)
    return 0


_INSTALL_VERBS = {
    "installed": "已安装",
    "updated": "已更新",
    "would-install": "将安装",
    "would-update": "将更新",
    "exists": "已存在（跳过）",
    "skipped": "跳过",
}

_POINTER_VERBS = {
    "created": "已写入",
    "appended": "已追加",
    "updated": "已更新",
    "unchanged": "无变化",
    "removed": "已移除",
    "would-remove": "将移除",
    "missing": "不存在",
    "no-block": "无标记块",
}

_REMOVE_VERBS = {
    "removed": "已移除",
    "would-remove": "将移除",
    "missing": "不存在",
    "skipped": "跳过",
}


def _pad(text: str, width: int) -> str:
    """ljust that counts CJK glyphs as two columns (keeps check output aligned)."""
    import unicodedata

    cells = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(1, width - cells)


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _has_action(result: dict, key: str) -> bool:
    if key == "skill":
        return any(r["skill_action"] != "exists" for r in result["results"])
    return True


def _print_results(
    result: dict, pretty, verb_map: dict[str, str] | None = None
) -> None:
    verbs = verb_map or _INSTALL_VERBS
    dry_run = bool(result.get("dry_run"))

    def dry(verb: str) -> str:
        # dry-run must never claim something happened
        return verb.replace("已", "将") if dry_run else verb

    width = max((len(r["label"]) for r in result["results"]), default=0)
    for item in result["results"]:
        label = f"[{item['label']}]"
        skill_verb = dry(verbs.get(item["skill_action"], item["skill_action"]))
        skill_path = pretty(item["skill_dir"]) if item["skill_dir"] else item.get("reason", "-")
        print(f"{label.ljust(width + 2)} skill  {skill_verb.ljust(8)} {skill_path}")
        for pointer in item["pointers"]:
            pointer_verb = dry(_POINTER_VERBS.get(pointer["action"], pointer["action"]))
            print(f"{''.ljust(width + 2)} prompt {pointer_verb.ljust(8)} {pretty(pointer['file'])}")


def cmd_setup(args: argparse.Namespace) -> int:
    """Kept for compatibility: `install-skill --target pi`."""
    from .skill_install import installed, pretty

    args.target = ["pi"]
    args.skills_dir = None
    args.instructions = None
    args.no_pointer = False
    args.json = False
    args.list_targets = False
    args.verify = False
    code = cmd_install_skill(args)
    found = installed(["pi"], project=args.project, agent_dir=args.agent_dir)
    if found["pi"]["user"] and found["pi"]["project"]:
        print(
            f"注意     {pretty(Path(found['pi']['project']))} 与用户级都有一份；"
            "Pi 遇到同名 skill 会保留先发现的（用户级优先）并给出警告"
        )
    return code


def cmd_unsetup(args: argparse.Namespace) -> int:
    """Kept for compatibility: `uninstall-skill --target pi`."""
    from .skill_install import pretty, uninstall

    result = uninstall(
        targets=["pi"],
        scope=args.scope,
        project=args.project,
        agent_dir=args.agent_dir,
        dry_run=args.dry_run,
    )
    _print_results(result, pretty, verb_map=_REMOVE_VERBS)
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
    from .runtime import print_status, status as runtime_status
    from .skill_install import installed, pretty

    if args.install:
        targets = {"transcribe": [("faster_whisper", "faster-whisper>=1.0.0")]}
        for module, spec in targets[args.install]:
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
        "auto_install": not os.environ.get("PODCAST_KG_NO_AUTO_INSTALL"),
        "skill_installed": installed(project=os.getcwd(), agent_dir=args.agent_dir),
        "runtime": runtime_status(),
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

    skill_rows = [
        (target, scope, path)
        for target, scopes in info["skill_installed"].items()
        for scope, path in scopes.items()
        if path
    ]
    for target, scope, path in skill_rows:
        scope_label = "用户级" if scope == "user" else "项目级"
        print(f"skill       {target:8s} {scope_label}  {pretty(Path(path))}")
    if not skill_rows:
        print("skill       未安装到 agent  ← `podcast-kg install-skill --target <pi|claude|codex|…>`")
        if info["runtime"].get("skill_dir"):
            print(f"skill 源    {pretty(Path(info['runtime']['skill_dir']))}（随 CLI 分发，可直接安装）")

    print()
    print_status(info["runtime"])
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
    "i18n": cmd_i18n,
    "models": cmd_models,
    "install-skill": cmd_install_skill,
    "uninstall-skill": cmd_uninstall_skill,
    "bootstrap": cmd_bootstrap,
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
