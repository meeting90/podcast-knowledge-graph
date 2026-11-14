"""Install the bundled skill into any agent's skill directory.

The skill is a plain **Agent Skills** folder — `SKILL.md` plus `sop/` and
`examples/` — so the same bytes work in every agent that reads the format.
Only two things are agent-specific:

  * where skills are discovered (`<dir>/<skill>/SKILL.md`);
  * where to leave a pointer for agents that do not discover skills natively
    (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `APPEND_SYSTEM.md`, …).

`TARGETS` is that registry. Anything not in it can still be served with
`install(..., skills_dir="…", instructions=["…"])`.

Every write is idempotent, newline-normalised to LF, and scoped to a marked
block: `<!-- podcast-kg:start -->` … `<!-- podcast-kg:end -->`.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Sequence

SKILL_NAME = "podcast-knowledge-graph"
BLOCK_START = "<!-- podcast-kg:start -->"
BLOCK_END = "<!-- podcast-kg:end -->"


@dataclass(frozen=True)
class Target:
    """One agent: where it looks for skills and where its instructions live."""

    id: str
    label: str
    user_skills: str | None
    project_skills: str | None
    user_instructions: tuple[str, ...] = ()
    project_instructions: tuple[str, ...] = ()
    note: str = ""


# Templates: {home} ~ user home, {project} project root, {agent_dir} Pi agent dir.
TARGETS: tuple[Target, ...] = (
    Target(
        "pi",
        "Pi",
        "{agent_dir}/skills",
        "{project}/.pi/skills",
        ("{agent_dir}/APPEND_SYSTEM.md",),
        ("{project}/.pi/APPEND_SYSTEM.md",),
        "skills + APPEND_SYSTEM.md",
    ),
    Target(
        "claude",
        "Claude Code",
        "{home}/.claude/skills",
        "{project}/.claude/skills",
        ("{home}/.claude/CLAUDE.md",),
        ("{project}/CLAUDE.md",),
        "skills + CLAUDE.md",
    ),
    Target(
        "codex",
        "OpenAI Codex",
        "{home}/.codex/skills",
        "{project}/.codex/skills",
        ("{home}/.codex/AGENTS.md",),
        ("{project}/AGENTS.md",),
        "skills + AGENTS.md",
    ),
    Target(
        "cursor",
        "Cursor",
        "{home}/.cursor/skills",
        "{project}/.cursor/skills",
        ("{home}/.cursor/AGENTS.md",),
        ("{project}/AGENTS.md",),
        "skills + AGENTS.md",
    ),
    Target(
        "gemini",
        "Gemini CLI",
        "{home}/.gemini/skills",
        "{project}/.gemini/skills",
        ("{home}/.gemini/GEMINI.md",),
        ("{project}/GEMINI.md",),
        "skills + GEMINI.md",
    ),
    Target(
        "opencode",
        "OpenCode",
        "{home}/.config/opencode/skills",
        "{project}/.opencode/skills",
        ("{home}/.config/opencode/AGENTS.md",),
        ("{project}/AGENTS.md",),
        "skills + AGENTS.md",
    ),
    Target(
        "copilot",
        "GitHub Copilot",
        None,
        "{project}/.github/skills",
        (),
        ("{project}/.github/copilot-instructions.md",),
        "project skills + copilot-instructions.md",
    ),
    Target(
        "agents",
        "AGENTS.md 通用",
        "{home}/.agents/skills",
        "{project}/.agents/skills",
        ("{home}/AGENTS.md",),
        ("{project}/AGENTS.md",),
        "skills + AGENTS.md（任何读 AGENTS.md 的 agent）",
    ),
)

TARGET_IDS = tuple(t.id for t in TARGETS)


class SkillInstallError(RuntimeError):
    """Raised for unknown targets / unusable paths; the CLI turns it into exit 1."""


def get_target(target_id: str) -> Target:
    for target in TARGETS:
        if target.id == target_id:
            return target
    raise SkillInstallError(
        f"未知目标 {target_id!r}；可选：{', '.join(TARGET_IDS)}，"
        "或用 --skills-dir DIR 指定任意目录"
    )


def expand_targets(names: Sequence[str] | None) -> list[Target]:
    """`None` → pi（保持旧行为）；`all` → 全部目标；支持同名去重。"""
    wanted = list(names or ["pi"])
    if "all" in wanted:
        return list(TARGETS)
    seen: list[Target] = []
    for name in wanted:
        target = get_target(name)
        if target not in seen:
            seen.append(target)
    return seen


def default_agent_dir() -> Path:
    raw = os.environ.get("PI_CODING_AGENT_DIR") or (Path.home() / ".pi" / "agent")
    return Path(raw).expanduser().resolve()


def _format(template: str, project: Path, agent_dir: Path) -> Path:
    raw = (
        template.replace("{home}", str(Path.home()))
        .replace("{project}", str(project))
        .replace("{agent_dir}", str(agent_dir))
    )
    return Path(raw).expanduser()


def resolve_target(
    target: Target,
    scope: str = "user",
    project: str | None = None,
    agent_dir: str | None = None,
) -> tuple[Path | None, list[Path]]:
    """Return (skill_dir, instruction files) for one target/scope combination."""
    if scope not in ("user", "project"):
        raise SkillInstallError(f"未知 scope: {scope!r}（可选 user / project）")
    project_path = Path(project or os.getcwd()).expanduser().resolve()
    agent_path = Path(agent_dir).expanduser().resolve() if agent_dir else default_agent_dir()

    skills_template = target.user_skills if scope == "user" else target.project_skills
    skill_dir = (
        _format(skills_template, project_path, agent_path) / SKILL_NAME
        if skills_template
        else None
    )
    instructions_template = (
        target.user_instructions if scope == "user" else target.project_instructions
    )
    instructions = [
        _format(template, project_path, agent_path) for template in instructions_template
    ]
    return skill_dir, instructions


def pretty(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home())).replace(os.sep, "/")
    except ValueError:
        return path.as_posix()


def _skill_resource():
    """Packaged copy first; editable installs fall back to the source tree."""
    packaged = resources.files("podcast_kg").joinpath("skill")
    if packaged.is_dir():
        return packaged
    here = Path(__file__).resolve()
    fallback = here.parent.parent.parent / "skills" / SKILL_NAME
    if fallback.is_dir():
        return fallback
    # vendored: <skill>/lib/podcast_kg/skill_install.py -> <skill>
    vendored = here.parent.parent.parent
    if (vendored / "SKILL.md").is_file() and (vendored / "lib" / "podcast_kg").is_dir():
        return vendored
    return packaged


def _require_skill():
    source = _skill_resource()
    if not source.is_dir():
        raise SkillInstallError(
            "找不到随包分发的 skill 目录（podcast_kg/skill 或仓库的 skills/）；重装 podcast-kg 可修复"
        )
    return source


def _pointer_doc() -> str:
    """The agent-neutral prompt block; Pi's own prompt lives in `.pi/APPEND_SYSTEM.md`."""
    packaged = resources.files("podcast_kg").joinpath("skill", "pointer.md")
    if packaged.is_file():
        raw = packaged.read_text(encoding="utf-8")
    else:
        raw = (
            Path(__file__).resolve().parent.parent.parent
            / "skills"
            / SKILL_NAME
            / "pointer.md"
        ).read_text(encoding="utf-8")
    lines = [
        line
        for line in raw.replace("\r\n", "\n").split("\n")
        if line.strip() not in {BLOCK_START, BLOCK_END}
    ]
    return "\n".join(lines).strip()


def pointer_block(skill_dir: Path) -> str:
    """The marked block: generic CLI reminder + where this skill lives."""
    body = _pointer_doc()
    location = f"技能包：`{skill_dir.as_posix()}`（处理播客 / 长视频 / 访谈前先读其中的 `SKILL.md`）。"
    bootstrap = skill_dir / "bin" / "bootstrap.py"
    runtime = (
        f"运行时：`python3 {bootstrap.as_posix()}`（幂等；只在 `podcast-kg` 不可用时执行，"
        "装到私有 venv 并留 PATH shim）。"
    )
    return "\n\n".join(part for part in (body, location, runtime) if part)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read().replace("\r\n", "\n")


def _write_text(path: Path, text: str) -> None:
    """Write with LF newlines regardless of platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _upsert_block(path: Path, content: str, dry_run: bool = False) -> str:
    block = f"{BLOCK_START}\n{content}\n{BLOCK_END}"
    existing = _read_text(path)

    if BLOCK_START in existing and BLOCK_END in existing:
        start = existing.index(BLOCK_START)
        end = existing.index(BLOCK_END) + len(BLOCK_END)
        updated = existing[:start] + block + existing[end:]
        action = "updated"
    elif existing.strip():
        separator = "" if existing.endswith("\n") else "\n"
        updated = f"{existing}{separator}{block}\n"
        action = "appended"
    else:
        updated = f"{block}\n"
        action = "created"

    if updated == existing:
        return "unchanged"
    if not dry_run:
        _write_text(path, updated)
    return action


def _remove_block(path: Path, dry_run: bool = False) -> str:
    if not path.exists():
        return "missing"
    existing = _read_text(path)
    if BLOCK_START not in existing or BLOCK_END not in existing:
        return "no-block"
    start = existing.index(BLOCK_START)
    end = existing.index(BLOCK_END) + len(BLOCK_END)
    updated = (existing[:start] + existing[end:]).strip("\n")
    if not dry_run:
        if updated:
            _write_text(path, updated + "\n")
        else:
            path.unlink()
    return "removed"


def _copy_tree(src, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        # never ship bytecode that happened to be lying around in a checkout
        if entry.name == "__pycache__" or entry.suffix == ".pyc":
            continue
        target = dest / entry.name
        if entry.is_dir():
            _copy_tree(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


def _sync_lib(skill_dir: Path) -> None:
    """Refresh the vendored CLI inside an installed skill from this package.

    The skill must run without a separately published wheel, so `lib/` is part
    of every install; it has to match the CLI that installed it.
    """
    source = Path(__file__).resolve().parent
    dest = skill_dir / "lib" / "podcast_kg"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        if path.is_dir() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(source)
        if rel.parts[0] == "skill":
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def _install_skill(skill_dir: Path, force: bool, dry_run: bool) -> str:
    if skill_dir.exists():
        if not force:
            return "exists"
        if not dry_run:
            shutil.rmtree(skill_dir)
            _copy_tree(_skill_resource(), skill_dir)
        return "would-update" if dry_run else "updated"
    if not dry_run:
        _copy_tree(_skill_resource(), skill_dir)
    return "would-install" if dry_run else "installed"


def _custom_plan(
    skills_dir: str,
    instructions: Sequence[str],
) -> dict:
    skill_dir = Path(skills_dir).expanduser().resolve() / SKILL_NAME
    files = [Path(path).expanduser().resolve() for path in instructions]
    return {
        "target": "custom",
        "label": "自定义",
        "note": "--skills-dir",
        "skill_dir": skill_dir,
        "instructions": files,
    }


def plan(
    targets: Sequence[str] | None = None,
    scope: str = "user",
    project: str | None = None,
    agent_dir: str | None = None,
    pointer: bool = True,
    skills_dir: str | None = None,
    instructions: Sequence[str] | None = None,
) -> list[dict]:
    """Resolve what `install` would touch, without touching it."""
    if scope not in ("user", "project"):
        raise SkillInstallError(f"未知 scope: {scope!r}（可选 user / project）")
    if skills_dir:
        return [_custom_plan(skills_dir, instructions or ())]

    project_path = Path(project or os.getcwd()).expanduser().resolve()
    entries: list[dict] = []
    skipped: list[dict] = []
    seen_dirs: set[Path] = set()

    for target in expand_targets(targets):
        skill_dir, default_instructions = resolve_target(
            target, scope, project_path, agent_dir
        )
        if skill_dir is None:
            skipped.append(
                {
                    "target": target.id,
                    "label": target.label,
                    "skill_dir": None,
                    "skill_action": "skipped",
                    "reason": f"{target.label} 没有约定 {scope} scope 的 skill 目录",
                    "instructions": [],
                }
            )
            continue
        if skill_dir in seen_dirs:
            continue
        seen_dirs.add(skill_dir)
        files = (
            [Path(path).expanduser().resolve() for path in instructions]
            if instructions
            else default_instructions
        )
        entries.append(
            {
                "target": target.id,
                "label": target.label,
                "note": target.note,
                "skill_dir": skill_dir,
                "instructions": files if pointer else [],
            }
        )
    return entries + skipped


def install(
    targets: Sequence[str] | None = None,
    scope: str = "user",
    project: str | None = None,
    agent_dir: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    pointer: bool = True,
    skills_dir: str | None = None,
    instructions: Sequence[str] | None = None,
) -> dict:
    """Copy the skill into every planned location and upsert its pointer block."""
    _require_skill()
    entries = plan(
        targets=targets,
        scope=scope,
        project=project,
        agent_dir=agent_dir,
        pointer=pointer,
        skills_dir=skills_dir,
        instructions=instructions,
    )
    results: list[dict] = []
    for entry in entries:
        skill_dir = entry["skill_dir"]
        if skill_dir is None:
            results.append(
                {
                    "target": entry["target"],
                    "label": entry["label"],
                    "skill_dir": None,
                    "skill_action": "skipped",
                    "reason": entry.get("reason", ""),
                    "pointers": [],
                }
            )
            continue
        skill_action = _install_skill(skill_dir, force=force, dry_run=dry_run)
        pin = None
        if not dry_run:
            from .runtime import write_pin

            pin = write_pin(skill_dir, force=True)
            if skill_action in ("installed", "updated"):
                _sync_lib(skill_dir)
        pointers = []
        if entry["instructions"]:
            block = pointer_block(skill_dir)
            for path in entry["instructions"]:
                pointers.append(
                    {"file": path, "action": _upsert_block(path, block, dry_run=dry_run)}
                )
        results.append(
            {
                "target": entry["target"],
                "label": entry["label"],
                "skill_dir": skill_dir,
                "skill_action": skill_action,
                "pointers": pointers,
                "pin": pin,
            }
        )
    return {"scope": scope, "dry_run": dry_run, "results": results}


def uninstall(
    targets: Sequence[str] | None = None,
    scope: str = "user",
    project: str | None = None,
    agent_dir: str | None = None,
    dry_run: bool = False,
    skills_dir: str | None = None,
    instructions: Sequence[str] | None = None,
) -> dict:
    """Remove the skill directory and the marked pointer block, keeping other text."""
    entries = plan(
        targets=targets,
        scope=scope,
        project=project,
        agent_dir=agent_dir,
        pointer=True,
        skills_dir=skills_dir,
        instructions=instructions,
    )
    results: list[dict] = []
    for entry in entries:
        skill_dir = entry["skill_dir"]
        if skill_dir is None:
            continue
        action = "missing"
        if skill_dir.exists():
            if not dry_run:
                shutil.rmtree(skill_dir)
            action = "would-remove" if dry_run else "removed"
        pointers = [
            {"file": path, "action": _remove_block(path, dry_run=dry_run)}
            for path in entry["instructions"]
        ]
        results.append(
            {
                "target": entry["target"],
                "label": entry["label"],
                "skill_dir": skill_dir,
                "skill_action": action,
                "pointers": pointers,
            }
        )
    return {"scope": scope, "dry_run": dry_run, "results": results}


def installed(
    targets: Sequence[str] | None = None,
    project: str | None = None,
    agent_dir: str | None = None,
) -> dict[str, dict[str, str | None]]:
    """Where this skill is currently installed, per target and scope."""
    found: dict[str, dict[str, str | None]] = {}
    for target in expand_targets(targets or ["all"]):
        entry: dict[str, str | None] = {}
        for scope in ("user", "project"):
            skill_dir, _ = resolve_target(target, scope, project, agent_dir)
            entry[scope] = (
                str(skill_dir)
                if skill_dir is not None and (skill_dir / "SKILL.md").is_file()
                else None
            )
        found[target.id] = entry
    return found


def verify(entries: Sequence[dict]) -> list[dict]:
    """Post-install checks: files, pin, pointer block, and a runnable CLI.

    Returns one `{ok, label, detail}` per check. Callers decide the exit code;
    an empty entry list still checks the runtime (that is the part users get
    wrong when the skill was copied by hand).
    """
    from . import __version__
    from .runtime import PIN_FILE, status

    checks: list[dict] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        checks.append({"ok": bool(ok), "label": label, "detail": detail})

    seen: set[Path] = set()
    for entry in entries:
        skill_dir = entry.get("skill_dir")
        if skill_dir is None:
            continue
        skill_dir = Path(skill_dir)
        if skill_dir in seen:
            continue
        seen.add(skill_dir)

        check((skill_dir / "SKILL.md").is_file(), "SKILL.md", str(skill_dir))
        check((skill_dir / "bin" / "bootstrap.py").is_file(), "bin/bootstrap.py", str(skill_dir))

        pin_path = skill_dir / PIN_FILE
        try:
            pinned = json.loads(pin_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pinned = None
        if not isinstance(pinned, dict):
            check(False, "runtime.json", f"缺失或不可读：{pin_path}")
        else:
            check(
                pinned.get("version") == __version__,
                "runtime.json",
                f"pin {pinned.get('version') or '—'} / 当前 CLI {__version__}",
            )

        for path in entry.get("instructions") or []:
            text = _read_text(Path(path))
            check(
                BLOCK_START in text and BLOCK_END in text,
                "指令文件标记块",
                str(path),
            )

    report = status()
    check(report["ready"], "CLI 可执行", report["cli"] or "podcast-kg 不在 PATH")
    check(
        True,
        "转写依赖",
        "faster-whisper 已安装"
        if report["transcribe_ready"]
        else "首次 transcribe 自动安装（需联网，数百 MB）",
    )
    check(
        True,
        "图谱快照",
        "ingest 纯标准库，无需额外依赖",
    )
    model = report.get("model") or {}
    check(
        True,
        "模型权重",
        f"{report.get('default_model', 'small')}：{model.get('status', '未下载')}"
        if model.get("status") in ("本地模型", "HF 缓存")
        else f"{report.get('default_model', 'small')} 未下载（首次 transcribe 下载，或 podcast-kg models fetch）",
    )
    return checks


def target_table() -> str:
    """Human-readable registry for `install-skill --list`."""
    home = Path.home().as_posix()
    agent_dir = default_agent_dir().as_posix()
    cwd = Path.cwd().as_posix()

    def shorten(path: Path | None) -> str:
        if path is None:
            return "-"
        text = path.as_posix()
        for prefix, label in ((home, "~"), (agent_dir, "$PI_AGENT_DIR"), (cwd, ".")):
            if text == prefix:
                return label
            if text.startswith(prefix + "/"):
                return label + text[len(prefix) :]
        return text

    rows = [("目标", "agent", "用户级 skills", "项目级 skills", "指针文件")]
    for target in TARGETS:
        user_dir, user_files = resolve_target(target, "user", cwd, agent_dir)
        project_dir, project_files = resolve_target(target, "project", cwd, agent_dir)
        rows.append(
            (
                target.id,
                target.label,
                shorten(user_dir),
                shorten(project_dir),
                ", ".join(f.name for f in project_files) or "-",
            )
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        for row in rows
    )
