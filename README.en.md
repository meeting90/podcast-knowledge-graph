# podcast-knowledge-graph

[中文](README.md) | **English**

> **Live product: [heronai.top](https://heronai.top)** — HERON runs this exact pipeline as a product: a knowledge graph of spoken content where every claim links back to the second it was said.

An **agent-agnostic skill + Python CLI**. The same skill installs into Pi, Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot, or any agent that reads `AGENTS.md`, and turns podcasts / long videos / deep interviews into **source-linked knowledge cards** (JSON + Markdown), renders them as [HERON](https://heronai.top)-style claim pages (collapsible, timestamp links back to the audio), or writes them into a knowledge graph.

- **Agent Skills folder** (`skills/podcast-knowledge-graph/`): just `SKILL.md` + `sop/` + `examples/`, no agent-specific format — `podcast-kg install-skill` copies it into each agent's skills directory.
- **Python package** (`src/podcast_kg`): the CLI that does the work — transcribe, verify, render, graph snapshot, and install the skill.
- **Pi extension** (`.pi/extensions/podcast-kg.ts`, optional): a thin bridge that prepares the Python env, puts `podcast-kg` on PATH, appends a system prompt and registers the skill. Only Pi needs it.

Every claim carries an **audio timestamp range**, so it can link straight back to the episode — that is the difference between this and a generic "AI summary".

```json
{
  "claim_id": "c17",
  "statement": "Subscriptions are really big vendors subsidising users with API margin",
  "speaker": "jin-jing",
  "timestamp": "27:24",
  "end": "28:17",
  "relations": [{ "type": "supports", "target": "c12", "note": "Backed by the cost structure" }]
}
```

## When to use

- You have podcast / interview audio, a transcript or an episode link and want **structured** notes, not a running summary
- You need "every claim can go back to the exact second" provenance
- You need cross-episode relations: supports / challenges / extends / echoes
- You want the content to accumulate into a queryable graph

## Install

### Option A: install with `npx skills` from skills.sh (recommended, any agent)

The repo already uses the layout it expects (`skills/<name>/SKILL.md`), so no extra packaging:

```bash
npx skills add meeting90/podcast-knowledge-graph -l                    # list skills in the repo
npx skills add meeting90/podcast-knowledge-graph --agent claude-code -y     # install for Claude (symlinks by default)
npx skills add meeting90/podcast-knowledge-graph --agent '*'          # every agent (installed or not)
```

`--agent` takes a skills.sh agent id (`claude-code`, `codex`, `cursor`, `gemini-cli`, `opencode`,
`pi`, `github-copilot`, …); `--agent '*'` installs for every agent (`--all` is shorthand for `--skill '*' --agent '*' -y`). For agents that
are not in that list use **`--agent universal`** (writes to `.agents/skills/`, the same location as
`install-skill --target agents`). `npx skills add … -l` lists the skills in a repo first.

`npx skills` only links/copies files into agent directories — it **never runs install scripts**
(Agent Skills has no postinstall hook) and does not preinstall the CLI. But **users never run uv/pip
by hand**: the first command after install goes through the bundled launcher, which installs the
runtime and then executes (it needs `uv` or Python ≥3.10 on the machine; if neither exists it prints
the uv install command):

```bash
python3 <skills-dir>/podcast-knowledge-graph/bin/podcast-kg.py doctor
```

### Option B: install as a Pi extension (Pi only)

```bash
pi install git:github.com/meeting90/podcast-knowledge-graph
# current project only: pi install -l git:github.com/meeting90/podcast-knowledge-graph
```

Pi loads two resources:

| Resource | What it does |
| --- | --- |
| `.pi/extensions/podcast-kg.ts` | On first session: creates a private venv, installs `podcast-kg[all]`, puts `podcast-kg` on PATH, appends the system prompt, registers `/podcast-kg` |
| `skills/podcast-knowledge-graph/` | The skill itself: `SKILL.md`, `sop/SOP.md`, `examples/` |

Dependencies are **installed by the extension**: the first Pi session fills `~/.pi/agent/cache/podcast-kg/venv` (including `faster-whisper`) once. Check it:

```text
/podcast-kg doctor        # or: podcast-kg doctor in bash
```

This repo is also a runnable Pi project:

```bash
cd podcast-knowledge-graph && pi        # asks for trust on first run (loads .pi/extensions)
```

### Option C: install the CLI (preinstall the runtime / go offline)

> If you install through `npx skills`, **you can skip this section**: the skill installs its runtime
> on first use. The difference here is that `install-skill` also writes a pointer block into the
> agent's instruction file (`AGENTS.md` / `CLAUDE.md` / …), which is more reliable for agents that do
> not scan skill directories.

`uv` / `pip` do not know this repository: they treat `podcast-kg` as a **distribution name on PyPI**
(equivalent to `podcast_kg`) and query the default index `https://pypi.org/simple`; `[all]` is an
**extra** declared in the package metadata (`Provides-Extra: all`), not a separate package. If the
name is not found you get `No solution found … no versions of podcast-kg[all]`.
`@ git+…` or a local path is a **direct reference**: it bypasses the index, and the name is only
checked against the built project. `uv tool list` shows it; `uv tool uninstall podcast-kg` removes it.



```bash
# Until the package is on PyPI, install from git or a local checkout (a direct reference):
uv tool install "podcast-kg[all] @ git+https://github.com/meeting90/podcast-knowledge-graph"
# From the repo root: uv tool install ".[all]"

# Only after publishing to PyPI does the plain name work:
# uv tool install "podcast-kg[all]"   # or pipx / pip install "podcast-kg[all]"
podcast-kg doctor

podcast-kg install-skill --list                    # which agents, and where they go
podcast-kg install-skill --target pi               # ~/.pi/agent/skills
podcast-kg install-skill --target claude           # ~/.claude/skills
podcast-kg install-skill --target codex            # ~/.codex/skills + AGENTS.md
podcast-kg install-skill --target all --dry-run    # see what would be written first
```

| Target | User-level skills | Project-level skills (`--scope project`) | Pointer file |
| --- | --- | --- | --- |
| `pi` | `~/.pi/agent/skills/` | `.pi/skills/` | `APPEND_SYSTEM.md` (Pi-only, under `.pi/`) |
| `claude` | `~/.claude/skills/` | `.claude/skills/` | `CLAUDE.md` |
| `codex` | `~/.codex/skills/` | `.codex/skills/` | `AGENTS.md` |
| `cursor` | `~/.cursor/skills/` | `.cursor/skills/` | `AGENTS.md` |
| `gemini` | `~/.gemini/skills/` | `.gemini/skills/` | `GEMINI.md` |
| `opencode` | `~/.config/opencode/skills/` | `.opencode/skills/` | `AGENTS.md` |
| `copilot` | — (no user level) | `.github/skills/` | `.github/copilot-instructions.md` |
| `agents` | `~/.agents/skills/` | `.agents/skills/` | `AGENTS.md` |

For anything not in the table, use the two-argument form:

```bash
podcast-kg install-skill --skills-dir .my-agent/skills --instructions AGENTS.md
podcast-kg install-skill --skills-dir .my-agent/skills --no-pointer   # files only
```

The pointer text comes from `pointer.md` inside the skill (agent-neutral); Pi's own prompt block lives in `.pi/APPEND_SYSTEM.md` and is never reused.

Each install maintains one `<!-- podcast-kg:start --> … <!-- podcast-kg:end -->` block in that agent's instruction file (pointing at the installed `SKILL.md`, `runtime.json` and `bin/bootstrap.py`) and never touches anything else. `podcast-kg uninstall-skill --target <agent>` removes only its own part (the runtime venv stays; `rm -rf "$PODCAST_KG_HOME"` removes that too).

> Pick one: both the Pi extension and `npx skills add --agent pi` provide the skill; installing twice creates a duplicate (Pi keeps the first and warns).
> After installing, `/reload` in Pi or just start a new session elsewhere.

> `podcast-kg setup` / `unsetup` are kept as legacy aliases for `install-skill --target pi` / `uninstall-skill --target pi`.

## Runtime guarantee: why it works right after installing

The skill is only files; the work is done by the `podcast-kg` CLI. Where the runtime comes from depends on how you installed:

| Install path | Who prepares the runtime | Usable right away? |
| --- | --- | --- |
| Pi extension | First session creates a private venv (with `faster-whisper`) | Yes |
| `podcast-kg install-skill` | CLI already present; `transcribe` / `ingest` install their deps on first use | Yes |
| Files copied in (marketplace / `npx skills add` / manual clone) | Use `bin/podcast-kg.py`: it installs on first use | Yes, the first command does it |

```bash
python3 skills/podcast-knowledge-graph/bin/bootstrap.py            # idempotent; instant when ready
python3 skills/podcast-knowledge-graph/bin/bootstrap.py --check    # exit 1 if not ready
python3 skills/podcast-knowledge-graph/bin/bootstrap.py --json     # ready / cli / version / pinned / notes
podcast-kg install-skill --target claude --verify                  # post-install check: files / pin / CLI
```

- **Where**: `$PODCAST_KG_HOME` (Windows `%LOCALAPPDATA%\podcast-kg`, macOS `~/Library/Application Support/podcast-kg`, Linux `${XDG_DATA_HOME:-~/.local/share}/podcast-kg`), always inside a private venv — system Python is untouched. Shims go to `$PODCAST_KG_HOME/bin` (and `~/.local/bin` when it exists).
- **Which version**: `runtime.json` in the skill folder records the CLI version that installed it (`install-skill` writes it), and bootstrap installs `podcast-kg[all]==<that version>`. Sources, in order: local checkout → PyPI → git. If PyPI doesn't have that version yet, it falls back to git (git required) — so a hand-copied skill can still bootstrap itself.
- **Works without Python**: prefers `uv`; `uv venv --python 3.12` downloads an interpreter when the host has none. If neither uv nor Python is available it prints the uv install command.
- **Size and network**: `[all]` needs network once (faster-whisper + ctranslate2, hundreds of MB); whisper weights download on the first `transcribe`. Use `--extras none` if you only need `render` / `verify` (pure stdlib, offline).
- **Fails loudly**: bootstrap exits 0/1 and `--json` puts the real error tail in `notes`. Env vars: `PODCAST_KG_HOME` (install location), `PODCAST_KG_BIN` (use an existing executable).

### Why whisper weights are not bundled

`small` is 486 MB, `medium` 1.5 GB, `large-v3` 3.1 GB; PyPI caps files at 100 MB and git is the wrong place for binaries — and skill copies (`npx skills add`, plugin marketplaces) would drag every byte along. What is bundled is the ability to **use local weights**:

| Approach | Command | When |
| --- | --- | --- |
| Download on first use (default) | just `podcast-kg transcribe` | can reach huggingface.co |
| Prefetch once, stay offline | `podcast-kg models fetch --model small` | one download, then fully offline |
| Shared drive / USB / internal mirror | `podcast-kg models fetch --model small --dir /srv/models`, then `PODCAST_KG_MODEL_DIR=/srv/models` or `transcribe --model-dir /srv/models` | many machines, no internet |
| Install runtime and weights together | `podcast-kg bootstrap --models small` | one command |

```bash
podcast-kg models list                    # size / state (local, HF cache, missing) / path
podcast-kg models fetch --model small     # → $PODCAST_KG_HOME/models/small
podcast-kg models verify                  # check config.json / model.bin / tokenizer.json / vocabulary
podcast-kg models path --model small      # usable local path (exit 1 when missing)
```

- Resolution order: `--model` directory → `<name>` under `--model-dir` / `PODCAST_KG_MODEL_DIR` → `$PODCAST_KG_HOME/models/<name>` → HF cache → download.
- With `PODCAST_KG_OFFLINE=1` (or `HF_HUB_OFFLINE=1`), missing weights **fail immediately** instead of silently waiting through a 130-second timeout.
- The folder produced by `models fetch` can be copied elsewhere (HF symlinks are materialised, `.cache` is removed). Ship it as a release asset or on a shared drive — not inside the wheel.

Full bootstrap behaviour (resolution order, probing, Windows Store python aliases) lives in
[`skills/podcast-knowledge-graph/bin/README.md`](skills/podcast-knowledge-graph/bin/README.md).

## Usage

Just say "turn this podcast into a knowledge card", or invoke the skill explicitly:

```text
/skill:podcast-knowledge-graph turn this episode into a knowledge card, audio ./ep42.mp3
```

`/skill:` is the Pi / Claude Code syntax; other agents accept the same sentence, or read the installed `SKILL.md`.

The skill follows `sop/SOP.md`: transcribe → extract → verify → output. You can also drive the CLI by hand:

```bash
podcast-kg --help                      # pick a subcommand
podcast-kg transcribe --help           # then read its inputs/outputs/failure modes
```

```bash
podcast-kg doctor                      # environment check (python / ffmpeg / deps / skill / runtime / models)
podcast-kg bootstrap --check           # is the runtime actually usable (exit 1 if not)
podcast-kg models fetch --model small  # prefetch weights for offline use
podcast-kg transcribe ep42.mp3 --model small --lang zh
podcast-kg transcribe ep42.mp3 --words     # also emit word-level timestamps (for arc boundaries)
podcast-kg verify .outputs/ep42.json   # pass several cards to normalise across episodes
podcast-kg render .outputs/ep42.json   # → .outputs/ep42.html
podcast-kg i18n scaffold .outputs/ep42.json --lang en     # bilingual: translation skeleton
podcast-kg i18n check .outputs/ep42.json .outputs/ep42.en.json
podcast-kg render .outputs/ep42.json .outputs/ep42.html \
  --i18n en=.outputs/ep42.en.json --default-lang zh        # one HTML, language switch
podcast-kg ingest .outputs/ep42.json   # → .outputs/ep42_graph.json
```

Everything is written to `.outputs/` in the **current directory**. **`--help` is the contract** (arguments, outputs, exit codes); the examples above are just common usage.

> **Engine**: faster-whisper by default. Benchmarked in [docs/asr-engines.md](docs/asr-engines.md):
> Parakeet TDT 0.6B v3 is fast and accurate for English but **has no Chinese**; SenseVoice reaches
> 40–48× on CPU with punctuation but hears `Claude Code` as `cloud code`; Zipformer CTC small (61 MB)
> gets 0% CER on pure Mandarin yet emits `<unk>` for every English term. For Chinese tech podcasts
> (code-switching plus proper nouns) whisper remains the safest.
> The same data exposed whisper's repetition loop, now fixed by defaulting
> `condition_on_previous_text` to off (`--carry-context` restores the old behaviour).

### Optional dependencies

| Subcommand | Dependency | Notes |
| --- | --- | --- |
| `render` / `verify` / `install-skill` / `ingest` / `doctor` | **none** (stdlib only) | works offline |
| `transcribe` | `faster-whisper` | installed on first use |

> Since 0.1.0, `ingest` no longer depends on semantica. Its `merge_entities=True` merged by name
> similarity and got it wrong: it merged "Peking University" into "Beijing Normal University",
> `minsky` into `zuckerberg`, and two different claims (`c33` / `c43`) into one id — every bad merge
> looked perfectly valid. Its claimed PROV-O provenance lived only in process memory and was never
> written out. The current implementation (`src/podcast_kg/ingest_graph.py`) only dedupes by id,
> validates edge endpoints and self-loops, and writes provenance into `*_graph.json` under `provenance[]`.

Auto-install uses `pip` or `uv pip install --python <python>` depending on how the interpreter is managed (`uv tool` venvs have no pip). To control it yourself:

```bash
podcast-kg doctor --install all         # install ahead of time
export PODCAST_KG_NO_AUTO_INSTALL=1     # disable auto-install
uv tool install --with "faster-whisper" podcast-kg      # include transcribe deps
```

`ffmpeg` is optional: without it, transcription decodes the original audio through PyAV.

## Developing from source

```bash
git clone https://github.com/meeting90/podcast-knowledge-graph
cd podcast-knowledge-graph
uv venv && uv pip install -e ".[all]"

pi                                       # load extension + skill as a project
pi -e .                                  # or load it as a Pi package

# Option B install logic (does not touch your real Pi config)
podcast-kg setup --agent-dir /tmp/pk-agent --dry-run
podcast-kg setup --agent-dir /tmp/pk-agent

uv build                                 # the wheel maps skills/ to podcast_kg/skill
PYTHONPATH=src python -m unittest discover -s tests -v   # installer tests
```

## Packaging and publishing (Agensi / ZIP)

Agensi (and most skill marketplaces) accepts **one ZIP**: a single top folder with
`SKILL.md` at its root, scripts and references in subfolders. This repo ships a
deterministic packager (same tree → same SHA-256):

```bash
python scripts/package_skill.py           # → dist/podcast-knowledge-graph-0.1.0.zip
python scripts/package_skill.py --check   # validate only
python scripts/package_skill.py --json    # manifest / size / chars / sha256
```

The ZIP contains **the skill only** (14 files, ~155 KB, 126k characters):

```
podcast-knowledge-graph/
├── SKILL.md / SKILL.en.md      triggers, steps, quality gates (zh/en)
├── sop/SOP.md / SOP.en.md      extraction spec (zh/en)
├── examples/                   one complete example card (JSON + Markdown)
├── bin/bootstrap.py            runtime bootstrap (stdlib; version pin embedded)
├── bin/bootstrap / .cmd        optional launchers
├── bin/README.md / .en.md      bootstrap behaviour
├── pointer.md                  generic block installed into AGENTS.md / CLAUDE.md
└── runtime.json                version pin (bootstrap prefers it)
```

It does **not** include the CLI source, whisper weights, caches or a virtualenv:
on first use the buyer's agent runs `bin/bootstrap.py`, which installs `podcast-kg`
into a private venv (PyPI first, git fallback until a release is on PyPI). The script
also works when copied alone to a temp file — the version pin is embedded in
`bootstrap.py`, with `runtime.json` as an override.

The packager enforces Agensi's rules: ≤50 MB, ≤1000 files, ≤6M characters; rejects
exe/dll/so and friends; strips `.git`, `__pycache__`, `.DS_Store`, `node_modules`,
`site-packages` and virtualenvs. One advisory: `bin/bootstrap.py` is 22.9 KB, slightly
over their "keep scripts under 20 KB for review" guideline (not a hard limit).

### Publishing the ZIP through git

| Option | How | Verdict |
| --- | --- | --- |
| **GitHub Release asset (recommended)** | `git tag v0.1.0 && git push --tags`; `.github/workflows/skill-zip.yml` builds and uploads the zip | the binary never enters git history; each update is just a new release asset |
| Commit the zip | put it in `dist/` (already git-ignored) | possible, but every doc change adds a binary commit and bloats history |
| GitHub auto archive | `https://github.com/meeting90/podcast-knowledge-graph/archive/refs/tags/v0.1.0.zip` | contains the whole repo (Python source, tests), not a skill-only package — not suitable for the marketplace |

Upload by hand instead:

```bash
gh release create v0.1.0 dist/podcast-knowledge-graph-0.1.0.zip --generate-notes
# or add the asset to an existing release:
gh release upload v0.1.0 dist/podcast-knowledge-graph-0.1.0.zip --clobber
```

On Agensi: upload the zip → set a price → 8-point automated security scan + AI intent
review + human review → live. Updates are a new version upload; buyers' agents fetch the
current version on demand.

### Versioning and releases (merge → tag → release)

The version lives in four places (PyPI metadata / `--version` / the skill's `runtime.json` / the
pin embedded in bootstrap). One script keeps them in sync:

```bash
python scripts/bump_version.py --check        # also runs in CI
python scripts/bump_version.py patch          # 0.1.0 -> 0.1.1 (minor / major too)
python scripts/bump_version.py --set 0.2.0
```

Recommended flow:

1. Bump the version **inside the PR** (`bump_version.py …`) together with the change;
2. Merging to `main` runs `.github/workflows/release.yml`:
   - verifies the four files agree (fails otherwise);
   - if `v<version>` does not exist: tags it, creates a Release and attaches the skill ZIP
     (`--generate-notes` writes the changelog from merged PRs);
   - if it exists: no-op, so merges that do **not** bump the version never re-release;
3. Manual release:

```bash
git tag v0.2.0 && git push origin v0.2.0          # the skill-zip workflow creates the Release
# or directly (zip already in dist/):
gh release create v0.2.0 dist/podcast-knowledge-graph-0.2.0.zip --generate-notes
```

`gh` is just a CLI — it does not watch merges. Automation comes from Actions (`push: main`).
The only real rule: **bump the version in the PR**, otherwise there is no new tag to release.

**Release-notes grouping**: `.github/release.yml` splits changes into Features / Fixes / Documentation /
Maintenance / Other. When the PR title uses a Conventional Commits prefix (`feat:` / `fix:` / `docs:` /
`chore:` …, including `feat(api)!:`), `pr-label.yml` adds the matching label automatically; add the
`skip-changelog` label to hide a PR from the notes.

### Publishing to PyPI (makes `uv tool install "podcast-kg[all]"` work)

```bash
uv build                 # dist/*.whl + *.tar.gz
uv publish               # or: twine upload dist/*
```

When bumping a version, update four places: `version` in `pyproject.toml`, `__version__` in
`src/podcast_kg/__init__.py`, `skills/podcast-knowledge-graph/runtime.json`, and `PIN_VERSION`
in `bin/bootstrap.py` (`tests/test_package.py` asserts the last three match).

## Layout

```
podcast-knowledge-graph/
├── package.json                  # Pi package manifest: extension + skills
├── pyproject.toml                # Python package podcast-kg: deps, CLI entry point
├── skills/podcast-knowledge-graph/pointer.md   # generic block written into AGENTS.md / CLAUDE.md
├── skills/podcast-knowledge-graph/   # Agent Skills folder (single source; mapped into the wheel)
│   ├── SKILL.md                  #   triggers, steps, quality gates (Chinese; English: SKILL.en.md)
│   ├── pointer.md                #   generic block installed into AGENTS.md / CLAUDE.md
│   ├── runtime.json              #   runtime pin: which podcast-kg version bootstrap installs
│   ├── bin/bootstrap.py          #   stdlib-only self-heal: private venv + PATH shim
│   ├── sop/SOP.md                #   extraction spec: schema, naming, relations, QA checklist (English: SOP.en.md)
│   └── examples/                 #   one complete example card (JSON + Markdown)
├── .pi/                          # Pi-only resources (other agents don't need them)
│   ├── APPEND_SYSTEM.md          #   prompt block appended to Pi's system prompt (Pi-only)
│   └── extensions/podcast-kg.ts  #   extension: env prep / PATH / prompt / skill / command
└── src/podcast_kg/               # Python implementation
    ├── cli.py                    #   subcommand implementations
    ├── args.py                   #   argparse: each subcommand's --help (the contract)
    ├── skill_install.py          #   install the skill into any agent (skills dir + pointer block)
    ├── runtime.py                #   runtime pin / bootstrap delegation / env check
    ├── deps.py                   #   install optional deps on demand (pip / uv tool compatible)
    ├── outputs.py                #   the .outputs/ convention
    ├── transcribe.py             #   faster-whisper wrapper (segments, VAD, --words alignment)
    ├── models.py                 #   whisper weights: table, local/HF resolution, prefetch, verify
    ├── i18n.py                   #   bilingual cards: parity check, merge, translation scaffold
    ├── render_card.py            #   card JSON → HERON-compatible HTML (same DOM as the site)
    ├── render_arcs.py            #   arc verification page (one click plays a whole segment)
    ├── assets/heron.css          #   site stylesheet (font subset inlined, shipped with the package)
    ├── verify_cards.py           #   cross-card entity / person normalisation checks
    └── ingest_graph.py           #   card JSON → source-linked graph snapshot (stdlib)
```

## Workflow

```
audio ──podcast-kg transcribe──▶ transcript with timestamps
                                    │
                                    ▼
                          extract per the SOP (human or agent)
                                    │
                                    ▼
                          knowledge card JSON ◀── podcast-kg verify
                              │       │
                 podcast-kg render    podcast-kg ingest
                              │       │
                              ▼       ▼
                       HTML claim page   graph snapshot (entities / relationships / provenance)
```

See [**heronai.top**](https://heronai.top) for the finished shape: those pages are what `podcast-kg render` targets.

## Render modes

`podcast-kg render <card.json> [out.html] [--arcs arcs.json] [--mode audio|redirect] [--i18n LANG=FILE]`

| mode | Output |
| --- | --- |
| `audio` | Custom overlay player with timestamp jumps; pauses at `end` |
| `redirect` | Link-out only: no audio inlined, no audio requests; clicking a timestamp copies a cue |

The page shares the **same DOM and stylesheet** as [heronai.top](https://heronai.top) detail pages
(`src/podcast_kg/assets/heron.css` is the site stylesheet, font subset inlined), so the exported
single file looks exactly like the live one:

- **The reading unit is the topic arc**: when the card has `arcs` (or a sibling `<card>_arcs.json`, or `--arcs`),
  each group renders `av-arc` cards (title / summary / listen / evidence count). Expanding one shows
  "host's opening line → what this segment covers → key quotes → remaining claims", with per-sentence
  claims demoted to evidence. Without `arcs` it falls back to the claim-row view (`om-row`).
- **Picks**: ★ on cards and rows lives in your own browser (localStorage); "My picks" filters to them;
  "Share my view" copies a `#picks=…` link; "Export picks" downloads `picks_<id>.json` for the card.
- **Bilingual (zh/en)**: `--i18n en=ep42.en.json` merges the translation into the same DOM and adds a
  "中文 / EN" switch in the top bar. Switching changes text only (body, buttons, hints, contents, time bar);
  DOM, ids, deep links and the player stay single. Both cards must be structurally identical
  (ids, timestamps, groups) — `podcast-kg i18n check` blocks drift, and `i18n scaffold` writes a
  structure-only skeleton to translate.
- **Audio never changes**: the bilingual page always plays the original audio; no dubbing, no second timeline.
- **Deep links**: `#arc-a03` opens an arc, `#c21` opens the arc that contains the claim plus the claim.
- **Comments** is a layout placeholder; real discussion happens on the live card.

The exported page is a **self-contained single file** (CSS + font subset + optional audio clips inlined), so it opens offline or from a chat app.

## Schema highlights

- `source.content_id` is globally unique (`platform_date_number`)
- `claims[].timestamp` / `end` are required; `end` defaults to the next claim's start, capped at 300 s
- `relations[]` has 11 types: `supports` / `extends` / `deepens` / `tension_with` / `responds_to` / `parallel` / `implies` / `precondition` / `part_of` / `echoes` / `exemplified_by`
- `groups[].ids` must cover every claim exactly once
- Entities use **plain slugs** (`pi`, not `pi-agent`); people and entities are separate
- Full rules: `sop/SOP.md` (English: `sop/SOP.en.md`) in the skill

## License

[MIT](LICENSE)
