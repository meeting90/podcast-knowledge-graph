# runtime bootstrap

[中文](README.md) | **English**

`SKILL.md` is the manual; the work is done by the **CLI bundled with the skill** (`../lib/podcast_kg`).
This folder provides one stable entry point and installs the dependencies `transcribe` needs into a
private venv. Everything here is stdlib-only and does not depend on a published `podcast-kg` package.

```bash
python3 podcast-kg.py doctor       # preferred entry: runs the bundled CLI; installs deps if needed
python3 podcast-kg.py transcribe ep.mp3   # first call installs faster-whisper into the venv

python3 bootstrap.py               # deps only (idempotent): venv + shims
python3 bootstrap.py --check       # deps/venv ready? exit 1 when not
python3 bootstrap.py --plan        # report only, touch nothing
python3 bootstrap.py --json        # ready / vendored / deps / deps_ready / cli / action / notes
python3 bootstrap.py --models small  # install deps + prefetch whisper weights
```

Windows: `bootstrap.cmd`; POSIX: `./bootstrap` (probes the interpreter, delegates to `bootstrap.py`,
skipping the Windows Store `python` alias that exits 49).

## Behaviour

| Order | Condition | Action |
| --- | --- | --- |
| 1 | `$PODCAST_KG_BIN` executable | use it (explicit override) |
| 2 | `lib/podcast_kg` present and the current interpreter has the deps | run the bundled CLI |
| 3 | `lib/podcast_kg` present and `$PODCAST_KG_HOME/venv` has the deps | run the bundled CLI with that venv's Python |
| 4 | bundled CLI, deps missing (`transcribe` / `models fetch`) | `uv venv --python 3.12` + install `deps`, then retry |
| 5 | no `lib/` (older install) | use a CLI on PATH / in the venv; otherwise install the `podcast-kg` package (PyPI → git) |
| 6 | no Python and no uv | exit 1 with the uv install command |

Install target: `$PODCAST_KG_HOME` (defaults: Windows `%LOCALAPPDATA%\podcast-kg`,
macOS `~/Library/Application Support/podcast-kg`, Linux `${XDG_DATA_HOME:-~/.local/share}/podcast-kg`).
Only the private venv and `bin/` shims are written (plus `~/.local/bin` when present); system Python
is untouched.

`runtime.json` carries two things:

| Field | Purpose |
| --- | --- |
| `version` | version of the bundled CLI (written by `install-skill`; `lib/` is kept in sync) |
| `deps` | dependencies to install into the venv, default `faster-whisper>=1.0.0` + `av>=11,<19` |

## Model weights

Weights are not shipped in the skill (`small` 486 MB, `large-v3` 3.1 GB); `--models` just delegates
to the bundled CLI:

```bash
python3 bootstrap.py --models small      # → <home>/models/small; transcribe is fully offline afterwards
```

`--check` / `--plan` only report. A failed download puts the CLI's real error tail into `notes` and
exits 1. For offline deployment, copy the whole `<home>/models` directory and point
`PODCAST_KG_MODEL_DIR` at it.

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | ready (existing, bundled, or just installed) |
| 1 | not ready / install failed (`notes` has the real error tail) |
| 2 | bad arguments |

## Environment variables

| Variable | Purpose |
| --- | --- |
| `PODCAST_KG_HOME` | runtime location (venv / shims / models) |
| `PODCAST_KG_BIN` | use an existing `podcast-kg` executable |
| `PODCAST_KG_PYTHON` | interpreter to use (launcher and venv) |
| `PODCAST_KG_VENDORED` | set by the launcher; forbids installing into system Python |
