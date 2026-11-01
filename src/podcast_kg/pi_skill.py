"""Install the bundled Pi skill into a Pi skills directory.

`podcast-kg setup` copies the skill shipped inside this package into

  user scope     <agent-dir>/skills/podcast-knowledge-graph/
  project scope  <project>/.pi/skills/podcast-knowledge-graph/

and upserts a marked block in the matching `APPEND_SYSTEM.md`, which Pi loads
natively. No JavaScript extension is involved: the CLI is the extension.

Implementation note: block read/write normalises to LF so repeated `setup`
runs are idempotent on Windows.
"""

from __future__ import annotations

import os
import shutil
from importlib import resources
from pathlib import Path

SKILL_NAME = "podcast-knowledge-graph"
BLOCK_START = "<!-- podcast-kg:start -->"
BLOCK_END = "<!-- podcast-kg:end -->"


def agent_dir(override: str | None = None) -> Path:
    raw = override or os.environ.get("PI_CODING_AGENT_DIR") or (Path.home() / ".pi" / "agent")
    return Path(raw).expanduser().resolve()


def resolve_paths(
    scope: str = "user",
    project: str | None = None,
    agent_dir_override: str | None = None,
) -> tuple[Path, Path]:
    """Return (skill_dir, append_system_file) for the requested scope."""
    if scope == "project":
        root = Path(project or os.getcwd()).expanduser().resolve()
        pi_dir = root / ".pi"
    elif scope == "user":
        pi_dir = agent_dir(agent_dir_override)
    else:
        raise ValueError(f"unknown scope: {scope} (expected user|project)")
    return pi_dir / "skills" / SKILL_NAME, pi_dir / "APPEND_SYSTEM.md"


def pretty(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home())).replace(os.sep, "/")
    except ValueError:
        return path.as_posix()


def _skill_resource():
    return resources.files("podcast_kg").joinpath("skill")


def _append_doc() -> str:
    raw = resources.files("podcast_kg").joinpath("APPEND_SYSTEM.md").read_text(encoding="utf-8")
    lines = [
        line
        for line in raw.replace("\r\n", "\n").split("\n")
        if line.strip() not in {BLOCK_START, BLOCK_END}
    ]
    return "\n".join(lines).strip()


def _copy_tree(src, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dest / entry.name
        if entry.is_dir():
            _copy_tree(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


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
        sep = "\n" if existing.endswith("\n") else "\n\n"
        updated = f"{existing}{sep}{block}\n"
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


def install(
    scope: str = "user",
    project: str | None = None,
    agent_dir_override: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, str]:
    skill_dir, append_file = resolve_paths(scope, project, agent_dir_override)

    if skill_dir.exists():
        if not force:
            skill_action = "exists"
        else:
            if not dry_run:
                shutil.rmtree(skill_dir)
                _copy_tree(_skill_resource(), skill_dir)
            skill_action = "updated" if not dry_run else "would-update"
    else:
        if not dry_run:
            _copy_tree(_skill_resource(), skill_dir)
        skill_action = "installed" if not dry_run else "would-install"

    prompt_action = _upsert_block(append_file, _append_doc(), dry_run=dry_run)
    return {
        "scope": scope,
        "skill_dir": str(skill_dir),
        "skill_action": skill_action,
        "append_file": str(append_file),
        "prompt_action": prompt_action,
        "other_scope": other_scope_copy(scope, project, agent_dir_override),
    }


def uninstall(
    scope: str = "user",
    project: str | None = None,
    agent_dir_override: str | None = None,
    dry_run: bool = False,
) -> dict[str, str]:
    skill_dir, append_file = resolve_paths(scope, project, agent_dir_override)

    skill_action = "missing"
    if skill_dir.exists():
        if not dry_run:
            shutil.rmtree(skill_dir)
        skill_action = "removed" if not dry_run else "would-remove"

    prompt_action = _remove_block(append_file, dry_run=dry_run)
    return {
        "scope": scope,
        "skill_dir": str(skill_dir),
        "skill_action": skill_action,
        "append_file": str(append_file),
        "prompt_action": prompt_action,
    }


def installed(agent_dir_override: str | None = None) -> dict[str, str | None]:
    """Where the skill is currently installed (user and current project)."""
    user_dir, _ = resolve_paths("user", agent_dir_override=agent_dir_override)
    project_dir, _ = resolve_paths("project")
    return {
        "user": str(user_dir) if (user_dir / "SKILL.md").is_file() else None,
        "project": str(project_dir) if (project_dir / "SKILL.md").is_file() else None,
    }


def other_scope_copy(
    scope: str,
    project: str | None = None,
    agent_dir_override: str | None = None,
) -> str | None:
    """Path of an existing install in the *other* scope, if any.

    Pi keeps the first discovered skill on a name collision (user scope wins and
    logs a warning), so a duplicate install is harmless but worth mentioning.
    """
    if scope == "project":
        path, _ = resolve_paths("user", agent_dir_override=agent_dir_override)
    else:
        path, _ = resolve_paths("project", project)
    return str(path) if (path / "SKILL.md").is_file() else None
