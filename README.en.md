# podcast-knowledge-graph

[中文](README.md) | **English**

> **Live product: [heronai.top](https://heronai.top)** — HERON runs this exact pipeline as a product: a knowledge graph of spoken content where every claim links back to the second it was said.

An **agent-agnostic skill + Python CLI**. The same skill installs into Pi, Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot, or any agent that reads `AGENTS.md`, and turns podcasts / long videos / deep interviews into **source-linked knowledge cards** (JSON + Markdown), renders them as [HERON](https://heronai.top)-style claim pages (collapsible, timestamp links back to the audio), or writes them into a knowledge graph.

- **Agent Skills folder** (`skills/podcast-knowledge-graph/`): just `SKILL.md` + `sop/` + `examples/`, no agent-specific format — `podcast-kg install-skill` copies it into each agent's skills directory.
- **Python package** (`skills/podcast-knowledge-graph/lib/podcast_kg`): the CLI that does the work — transcribe, verify, render, graph snapshot, and install the skill.
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

The skill **ships its own CLI** (`skills/podcast-knowledge-graph/lib/podcast_kg`): once installed,
`render / verify / ingest / i18n / models / install-skill` work offline with the standard library.
Only `transcribe` needs a one-time install of `faster-whisper` (hundreds of MB) into a private venv.
**There is no separate `podcast-kg` package to publish or install.**

### Option A: install with `npx skills` from skills.sh (recommended, any agent)

The repo already uses the layout it expects (`skills/<name>/SKILL.md`):

```bash
npx skills add meeting90/podcast-knowledge-graph -l                    # list skills in the repo
npx skills add meeting90/podcast-knowledge-graph --agent claude-code -y     # Claude Code
npx skills add meeting90/podcast-knowledge-graph --agent '*'          # every agent
```

`--agent` takes a skills.sh id (`claude-code`, `codex`, `cursor`, `gemini-cli`, `opencode`, `pi`,
`github-copilot`, …); `--agent '*'` installs for all (`--all` adds `--skill '*'`); agents not in
that list use **`--agent universal`** (writes `.agents/skills/`, same as
`install-skill --target agents`).

`npx skills` only copies files and runs no install scripts, but the CLI is already inside the skill:

```bash
python3 <skills-dir>/podcast-knowledge-graph/bin/podcast-kg.py doctor
```

The first `transcribe` (or `models fetch`) installs `faster-whisper` into `$PODCAST_KG_HOME/venv`;
after that it works offline.

### Option B: install as a Pi extension (Pi only)

```bash
pi install git:github.com/meeting90/podcast-knowledge-graph
# current project only: pi install -l git:github.com/meeting90/podcast-knowledge-graph
```

Pi loads two resources:

| Resource | What it does |
| --- | --- |
| `.pi/extensions/podcast-kg.ts` | First session: prepares the venv, puts `podcast-kg` on PATH, appends the system prompt, registers `/podcast-kg` |
| `skills/podcast-knowledge-graph/` | The skill itself (including the vendored CLI in `lib/`) |

This repo is also a runnable Pi project:

```bash
cd podcast-knowledge-graph && pi        # asks for trust on first run (loads .pi/extensions)
```

### Option C: ZIP / manual install, or install into another agent

```bash
# unzip a release asset (or your local dist/*.zip) into an agent's skills directory
unzip podcast-knowledge-graph-<version>.zip -d ~/.claude/skills/
python3 ~/.claude/skills/podcast-knowledge-graph/bin/podcast-kg.py doctor

# once the skill runs, it can also install itself into other agents (and write the pointer block)
python3 <skills-dir>/podcast-knowledge-graph/bin/podcast-kg.py install-skill --target codex
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

For anything else: `install-skill --skills-dir DIR --instructions AGENTS.md`, or just unzip the ZIP.
The pointer text comes from `pointer.md`; Pi's own prompt block is `.pi/APPEND_SYSTEM.md` and is never reused.

> Pick one: both the Pi extension and `npx skills add --agent pi` provide the skill; installing twice
> creates a duplicate (Pi keeps the first and warns).

## Runtime: the CLI ships with the skill

| Install path | Where the CLI comes from | Transcribe runtime |
| --- | --- | --- |
| `npx skills` / ZIP / manual copy | `lib/podcast_kg` inside the skill, zero install | environment must provide `faster-whisper` |
| Pi extension | the extension prepares a private venv | installed on first session |
| `install-skill` from an existing CLI | that CLI, `lib/` synced to the same version | depends on that CLI |

```bash
python3 <skill>/bin/podcast-kg.py doctor          # bundled CLI, zero install
python3 <skill>/bin/podcast-kg.py render ep.json ep.html
python3 <skill>/bin/podcast-kg.py models fetch --model small
```

- **Vendored CLI**: `lib/podcast_kg` is the only copy of the package (pyproject packages from it),
  pinned by `runtime.json`. `render/verify/ingest/i18n/models` need **nothing** and work offline;
  `install-skill` copies its own package into the target skill's `lib/`.
- **Transcribe**: needs `faster-whisper` in the environment. The skill installs nothing; when it is
  missing the command says so. Provide a transcript, or use an environment that has the runtime
  (the Pi extension prepares one for Pi).
- **Weights**: managed separately (`models fetch`).
- **Scope**: no global venv, no shims, no pip/PyPI dependency — the CLI is just files in the skill.

### Why whisper weights are not bundled

`small` is 486 MB, `medium` 1.5 GB, `large-v3` 3.1 GB; marketplace ZIPs cap at 50 MB, git is the wrong place for binaries — and skill copies (`npx skills add`, plugin marketplaces) would drag every byte along. What is bundled is the ability to **use local weights**:

| Approach | Command | When |
| --- | --- | --- |
| Download on first use (default) | just `podcast-kg transcribe` | can reach huggingface.co |
| Prefetch once, stay offline | `podcast-kg models fetch --model small` | one download, then fully offline |
| Shared drive / USB / internal mirror | `podcast-kg models fetch --model small --dir /srv/models`, then `PODCAST_KG_MODEL_DIR=/srv/models` or `transcribe --model-dir /srv/models` | many machines, no internet |
| Prefetch weights (runtime already present) | `python3 <skill>/bin/podcast-kg.py models fetch --model small` | one download, then offline |

```bash
podcast-kg models list                    # size / state (local, HF cache, missing) / path
podcast-kg models fetch --model small     # → $PODCAST_KG_HOME/models/small
podcast-kg models verify                  # check config.json / model.bin / tokenizer.json / vocabulary
podcast-kg models path --model small      # usable local path (exit 1 when missing)
```

- Resolution order: `--model` directory → `<name>` under `--model-dir` / `PODCAST_KG_MODEL_DIR` → `$PODCAST_KG_HOME/models/<name>` → HF cache → download.
- With `PODCAST_KG_OFFLINE=1` (or `HF_HUB_OFFLINE=1`), missing weights **fail immediately** instead of silently waiting through a 130-second timeout.
- The folder produced by `models fetch` can be copied elsewhere (HF symlinks are materialised, `.cache` is removed). Ship it as a release asset or on a shared drive — not inside the wheel.

Launcher behaviour: [`skills/podcast-knowledge-graph/bin/README.md`](skills/podcast-knowledge-graph/bin/README.md).

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

### Dependencies: nothing to install as a Python package

| Subcommand | Dependency |
| --- | --- |
| `render` / `verify` / `install-skill` / `ingest` / `i18n` / `models` / `doctor` | **none** (stdlib, offline) |
| `transcribe` | `faster-whisper` must exist in the environment (this skill installs nothing) |

`npx skills` ships every line of code (`lib/podcast_kg`). **There is no `pip install` and no separate
Python package to publish.** `transcribe` is the only command that needs an external runtime: if
`faster-whisper` is missing it fails with a clear message (provide a transcript or use an environment
that has it) instead of installing packages behind your back. Pi users get the runtime from the
extension; other environments must provide it (conda, system packages, an existing venv).

> Since 0.1.0, `ingest` no longer depends on semantica. Its `merge_entities=True` merged by name
> similarity and got it wrong: it merged "Peking University" into "Beijing Normal University",
> `minsky` into `zuckerberg`, and two different claims (`c33` / `c43`) into one id — every bad merge
> looked perfectly valid. Its claimed PROV-O provenance lived only in process memory and was never
> written out. The current implementation dedupes by id only, validates edge endpoints and self-loops,
> and writes provenance into `*_graph.json` under `provenance[]`.

`ffmpeg` is optional: without it, transcription decodes the original audio through PyAV.

## Developing from source

```bash
git clone https://github.com/meeting90/podcast-knowledge-graph
cd podcast-knowledge-graph

pi                                       # load extension + skill as a project
pi -e .                                  # or load it as a Pi package

# run the bundled CLI directly (installs nothing)
PYTHONPATH=skills/podcast-knowledge-graph/lib python -m podcast_kg doctor

# tests
PYTHONPATH=skills/podcast-knowledge-graph/lib python -m unittest discover -s tests -v
```

## Packaging (Agensi / ZIP)

Agensi (and most skill marketplaces) accepts **one ZIP**: a single top folder with `SKILL.md` at its
root, scripts and references in subfolders. This repo ships a deterministic packager (same tree →
same SHA-256):

```bash
python scripts/package_skill.py           # → dist/podcast-knowledge-graph-<version>.zip
python scripts/package_skill.py --check   # validate only
python scripts/package_skill.py --json    # manifest / size / chars / sha256
```

The ZIP is the **complete skill including the CLI** (30 files, ~560 KB):

```
podcast-knowledge-graph/
├── SKILL.md / SKILL.en.md      triggers, steps, quality gates (zh/en)
├── sop/SOP.md / SOP.en.md      extraction spec (zh/en)
├── examples/                   one complete example card (JSON + Markdown)
├── bin/podcast-kg.py           launcher: runs the bundled CLI
├── lib/podcast_kg/             the CLI (only copy; includes HTML template/CSS)
├── pointer.md                  generic block installed into AGENTS.md / CLAUDE.md
└── runtime.json                version pin
```

It does **not** include whisper weights, caches or a virtualenv: `render/verify/ingest/i18n/models`
work offline straight away. `transcribe` needs `faster-whisper` in the environment (the skill installs
nothing). `lib/podcast_kg` is the only copy of the package (pyproject packages from it), so there is no
second source and no separately published PyPI package.

The packager enforces Agensi's rules: ≤50 MB, ≤1000 files, ≤6M characters; rejects exe/dll/so and
friends; strips `.git`, `__pycache__`, `.DS_Store`, `node_modules`, `site-packages` and virtualenvs.
It also prints the <20 KB review hint for scripts under `bin/` (advisory, not a hard limit).

### Publishing the ZIP through git

| Option | How | Verdict |
| --- | --- | --- |
| **GitHub Release asset (recommended)** | `git tag v0.1.0 && git push --tags`; `.github/workflows/skill-zip.yml` builds and uploads the zip | the binary never enters git history; each update is a new release asset |
| Commit the zip | put it in `dist/` (already git-ignored) | possible, but every doc change adds a binary commit |
| GitHub auto archive | `https://github.com/meeting90/podcast-knowledge-graph/archive/refs/tags/v0.1.0.zip` | contains the whole repo (Python source, tests), not a skill-only package |

Upload by hand:

```bash
gh release create v0.1.0 dist/podcast-knowledge-graph-<version>.zip --generate-notes
# or add the asset to an existing release:
gh release upload v0.1.0 dist/podcast-knowledge-graph-<version>.zip --clobber
```

On Agensi: upload the zip → set a price → 8-point automated security scan + AI intent review + human
review → live. Updates are a new version upload; buyers' agents fetch the current version on demand.

### Versioning and releases (merge → tag → release)

The version lives in three places (package metadata / `--version` / the skill's `runtime.json`).
One script keeps them in sync:

```bash
python scripts/bump_version.py --check        # also runs in CI
python scripts/bump_version.py patch          # 0.1.0 -> 0.1.1 (minor / major too)
python scripts/bump_version.py --set 0.2.0
```

Recommended flow:

1. Bump the version **inside the PR** (`bump_version.py …`) together with the change;
2. Merging to `main` runs `.github/workflows/release.yml`:
   - verifies the three files agree (fails otherwise);
   - if `v<version>` does not exist: tags it, creates a Release and attaches the skill ZIP
     (`--generate-notes` writes the changelog from merged PRs);
   - if it exists: no-op, so merges that do **not** bump the version never re-release;
3. Manual release:

```bash
git tag v0.2.0 && git push origin v0.2.0          # the skill-zip workflow creates the Release
# or directly (zip already in dist/):
gh release create v0.2.0 dist/podcast-knowledge-graph-<version>.zip --generate-notes
```

`gh` is just a CLI — it does not watch merges. Automation comes from Actions (`push: main`).
The only real rule: **bump the version in the PR**, otherwise there is no new tag to release.

**Release-notes grouping**: `.github/release.yml` splits changes into Features / Fixes / Documentation /
Maintenance / Other. When the PR title uses a Conventional Commits prefix (`feat:` / `fix:` / `docs:` /
`chore:` …, including `feat(api)!:`), `pr-label.yml` adds the matching label automatically; add the
`skip-changelog` label to hide a PR from the notes.

## Layout

```
podcast-knowledge-graph/
├── package.json                  # Pi package manifest: extension + skills
├── pyproject.toml                # Python package metadata (packages from the skill's lib/)
├── skills/podcast-knowledge-graph/   # Agent Skills folder (single source; mapped into the wheel)
│   ├── SKILL.md                  #   triggers, steps, quality gates (Chinese; English: SKILL.en.md)
│   ├── pointer.md                #   generic block installed into AGENTS.md / CLAUDE.md
│   ├── runtime.json              #   version pin
│   ├── bin/podcast-kg.py         #   launcher: runs the bundled CLI
│   ├── sop/SOP.md                #   extraction spec (English: SOP.en.md)
│   ├── examples/                 #   one complete example card (JSON + Markdown)
│   └── lib/podcast_kg/           #   the CLI itself (only copy of the Python package)
│       ├── cli.py                #     subcommand implementations
│       ├── args.py               #     argparse: each subcommand's --help (the contract)
│       ├── transcribe.py         #     faster-whisper wrapper (segments, VAD, --words)
│       ├── render_card.py        #     card JSON → HERON-compatible HTML
│       ├── i18n.py               #     bilingual cards: parity check, merge, scaffold
│       ├── models.py             #     whisper weights: resolution, prefetch, verify
│       ├── ingest_graph.py       #     source-linked graph snapshot (stdlib)
│       ├── skill_install.py      #     install into any agent
│       ├── runtime.py / deps.py  #     runtime pin / dependencies
│       └── assets/heron.css      #     site stylesheet (font subset inlined)
├── .pi/                          # Pi-only resources (other agents don't need them)
│   ├── APPEND_SYSTEM.md          #   prompt block appended to Pi's system prompt (Pi-only)
│   └── extensions/podcast-kg.ts  #   extension: env prep / PATH / prompt / skill / command
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
(`skills/podcast-knowledge-graph/lib/podcast_kg/assets/heron.css` is the site stylesheet, font subset inlined), so the exported
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
