# runtime bootstrap

[中文](README.md) | **English**

`SKILL.md` is the manual; the `podcast-kg` CLI does the work. This folder turns "files on disk"
into "a usable runtime". The script is stdlib-only and does not depend on `podcast-kg` itself.

Day to day there is one entry point: `python3 podcast-kg.py <args>` (installs on first use,
then delegates). `bootstrap.py` below is the explicit install/inspect entry point.

```bash
python3 bootstrap.py            # idempotent: returns when ready, otherwise private venv + PATH shim
python3 bootstrap.py --check    # check only; exit 1 when not ready
python3 bootstrap.py --plan     # report what would happen, touch nothing
python3 bootstrap.py --json     # ready / cli / version / pinned / install / models / action / notes
```

Windows: `bootstrap.cmd`; POSIX: `./bootstrap` (both probe the interpreter and delegate to
`bootstrap.py`, skipping the Windows Store `python` alias that exits 49).

## Behaviour

| Order | Condition | Action |
| --- | --- | --- |
| 1 | `$PODCAST_KG_BIN` executable | use it |
| 2 | shim in `$PODCAST_KG_HOME/bin` | use it (treated as broken if `--version` fails) |
| 3 | `podcast-kg` on PATH | use it |
| 4 | `uv` available | `uv venv --python 3.12` (downloads an interpreter if needed) + `uv pip install <pin>` |
| 5 | Python ≥3.10 available | `python -m venv` + `pip install <pin>` |
| 6 | neither | exit 1 with the uv install command |

Install target: `$PODCAST_KG_HOME` (defaults: Windows `%LOCALAPPDATA%\podcast-kg`,
macOS `~/Library/Application Support/podcast-kg`, Linux `${XDG_DATA_HOME:-~/.local/share}/podcast-kg`).
Only the private venv and `bin/` are written (plus `~/.local/bin` when it exists); system Python is untouched.

The version comes from `runtime.json` in the skill root (`install-skill` writes it from the current CLI),
defaulting to `podcast-kg[all]==<version>`. Sources are tried in order; the next one runs only if the previous fails:

| Order | Source | When |
| --- | --- | --- |
| 1 | local checkout (`pyproject.toml` next to the skill) | repo / dev environment, no package download |
| 2 | PyPI: `podcast-kg[all]==<version>` | package is published |
| 3 | git: `podcast-kg[all] @ git+<install_from_git>` | fallback before the version is on PyPI (needs git) |

Options:

- `--extras none`: CLI only (stdlib; `render` / `verify` / `install-skill` / `ingest` work offline)
- `--models LIST`: prefetch whisper weights after install (`small` / `small,base` / `all` / `none`, default none) → `<home>/models`
- `--version latest`: no version pin (PyPI candidate unpinned; git is HEAD anyway)
- On Windows, if `PATHEXT` is missing (CI / minimal containers) the script adds it — otherwise uv cannot find `git`

## Model weights

Weights are not shipped in the skill (`small` 486 MB, `large-v3` 3.1 GB); `--models` simply delegates to the installed CLI:

```bash
python3 bootstrap.py --models small      # → <home>/models/small; transcribe is fully offline afterwards
```

`--check` / `--plan` only report and never download; a failed download puts the CLI's real error tail
into `notes` and exits 1. For offline deployment, copy the whole `<home>/models` directory to another
machine and point `PODCAST_KG_MODEL_DIR` at it.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | ready (whether it already was or was just installed) |
| 1 | not ready / install failed (`notes` carries the real error tail) |
| 2 | bad arguments |

## Environment variables

| Variable | Purpose |
| --- | --- |
| `PODCAST_KG_HOME` | runtime install location |
| `PODCAST_KG_BIN` | use an existing `podcast-kg` executable |
| `PODCAST_KG_PYTHON` | interpreter to use (launcher and venv) |
