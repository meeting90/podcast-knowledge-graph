---
name: podcast-knowledge-graph
description: Extract podcasts, long videos and interviews into timestamped, source-linked knowledge cards (JSON), including topic arcs; render a HERON-style HTML claim page with a built-in zh/en switch, or write a source-linked graph snapshot. Use when the user provides audio, a transcript or an episode link and asks for "structured notes / claim map / claim relations / source-linked summary".
license: MIT
compatibility: requires Python 3.10+ and the `podcast-kg` CLI (pip / uv tool / pipx); ffmpeg optional
metadata:
  repo: https://github.com/meeting90/podcast-knowledge-graph
  language: en
summary: Turn podcasts and interviews into timestamped, source-linked knowledge cards (topic arcs + claim evidence), delivered as zh/en JSON plus one switchable HTML page. Audio never changes.
tags: [podcast, transcription, knowledge-graph, whisper, bilingual, timestamps]
use_cases: [structured podcast notes, claim map, source-linked summary, bilingual knowledge cards]
docs_url: https://github.com/meeting90/podcast-knowledge-graph
---

# Podcast → Knowledge Card

> 中文版：[SKILL.md](SKILL.md)

## When to use

- The user gives podcast / interview audio or a transcript and wants **structured** notes, not a running summary
- You need "every claim can go back to the exact second" provenance
- You need cross-episode relations: supports / challenges / extends / echoes
- You want the content to accumulate into a queryable graph

**Not for**: plain news summaries, single-turn Q&A, anything that does not need provenance.

## How to run it (the `--help` output is the contract)

Call `podcast-kg` through bash. **First `podcast-kg --help` to pick a subcommand, then `podcast-kg <subcommand> --help` for arguments, outputs and failure semantics**; this file does not repeat CLI details and `--help` wins on conflicts.

- `sop/` and `examples/` are relative to **this file's directory**; read [sop/SOP.md](sop/SOP.md) (English: [sop/SOP.en.md](sop/SOP.en.md)) before starting
- How the skill is triggered depends on the agent: Pi / Claude Code use `/skill:podcast-knowledge-graph`; elsewhere ask the agent to read this file or say "follow the podcast-knowledge-graph SOP"
- Run `podcast-kg doctor` at the start of every task; if the command is missing see "Install and self-heal" below

## Install and self-heal

The skill is a plain **Agent Skills** folder (`SKILL.md` + `sop/` + `examples/` + `bin/`) and is not tied to any agent. Installing it elsewhere leaves a marked block in that agent's instruction file pointing at this file (idempotent; `--force` upgrades):

```bash
podcast-kg install-skill --list                     # supported agents and where each goes
podcast-kg install-skill --target claude            # user level: ~/.claude/skills/podcast-knowledge-graph/
podcast-kg install-skill --target codex --scope project
podcast-kg install-skill --target all --dry-run     # see which files would be written
podcast-kg install-skill --skills-dir DIR --instructions AGENTS.md   # any other agent
podcast-kg install-skill --target claude --verify   # post-install check: files / pin / CLI
```

**The CLI ships with the skill** (`lib/podcast_kg`), so it works as soon as the files land. Only
`faster-whisper` / `av` (needed by `transcribe`) are installed later, on first use, into a private venv:

| Case | Where the runtime comes from |
| --- | --- |
| Files copied in (marketplace / `npx skills add` / manual unzip) | works immediately; first `transcribe` installs deps |
| Installed by the Pi extension | first session prepares the venv and deps |
| Installed via `podcast-kg install-skill` | uses the existing CLI and syncs `lib/` to the same version |

Self-heal commands (idempotent; instant and offline when already ready):

```bash
python3 <skill-dir>/bin/podcast-kg.py doctor     # preferred entry: bundled CLI, installs deps if needed
python3 <skill-dir>/bin/bootstrap.py             # explicit dependency install (venv + PATH shim)
python3 <skill-dir>/bin/bootstrap.py --check     # check only; exit 1 if not ready
python3 <skill-dir>/bin/bootstrap.py --json      # ready / cli / version / pinned / action / notes
python3 <skill-dir>/bin/bootstrap.py --plan      # report what would happen
python3 <skill-dir>/bin/bootstrap.py --extras none   # CLI only (render/verify/ingest, offline)
python3 <skill-dir>/bin/bootstrap.py --models small # deps + prefetch weights (486 MB)
```

On Windows use `<skill-dir>\bin\bootstrap.cmd`; on POSIX `<skill-dir>/bin/bootstrap` also works.
    Marketplaces execute scripts **standalone** from a temp file, so `bootstrap.py` is the contract (the version pin is embedded; it does not read sibling files); the two launchers are local conveniences.

- **Where**: `$PODCAST_KG_HOME` (Windows `%LOCALAPPDATA%\podcast-kg`, macOS `~/Library/Application Support/podcast-kg`, Linux `~/.local/share/podcast-kg`), always a private venv; system Python is untouched. Shims go to `$PODCAST_KG_HOME/bin` (and `~/.local/bin` when present).
- **What gets installed**: the vendored CLI version is pinned by `version` in `runtime.json`; bootstrap
  installs only `deps` (`faster-whisper` + `av<19`). It no longer installs a `podcast-kg` package and
  does not need PyPI.
- **Works without Python**: uses `uv`; `uv venv --python 3.12` downloads an interpreter when the host has none. Without uv it prints the install command.
- **Size and network**: the transcribe deps (faster-whisper + ctranslate2) need network once and hundreds of MB; `render`/`verify`/`ingest`/`i18n` need nothing and work offline.

`podcast-kg bootstrap [--check|--plan|--json]` is the same implementation exposed by the CLI; `podcast-kg setup` / `unsetup` are legacy aliases for `--target pi`.

## Inputs

| Required | Notes |
| --- | --- |
| Audio URL or local file | For transcription; otherwise a transcript is the minimum |
| Episode metadata | Title, guests, publish date, URL |
| (Optional) shownotes | Helps with proper nouns and segment boundaries |

## Outputs

Everything goes to `.outputs/` in the **current working directory** (unless a subcommand is given an explicit path; see each `--help`):

```
.outputs/
├── <audio>_transcript.json / .txt     transcript
├── <content_id>.json / .md            base-language card (extraction result)
├── <content_id>.<lang>.json           translated card (default en; same structure, text only)
├── <content_id>_arcs.json             topic-arc layer (primary reading view)
├── <content_id>.html                  single-file page with a zh/en switch
├── <content_id>_arcs.html             arc verification page (click once to play a segment)
├── <content_id>_graph.json            graph snapshot
└── registry/                          entities / people / concepts
```

**Bilingual is the default delivery**: `<id>.json` (Chinese) + `<id>.en.json` (English) + **one** `<id>.html`.
Audio never changes — no dubbing, no second source; switching language only swaps text (including buttons, hints, contents, player bar).

### Two reading layers per episode (do not ship claim rows only)

| Layer | Unit | Size | Reader |
| --- | --- | --- | --- |
| **Topic arcs `arcs`** | host opens a topic → guest develops it → it closes | 8–18 per episode, 3–10 min each | **the reader's real entry point** |
| Sentence-level `claims` | one claim per sentence | 30–113 per episode, median 45–105 s | provenance, quotes, graph |

Shipping only claim rows means the reader hears half a sentence every time. In practice 60–75% of adjacent claims are ≤2 s apart — they were one passage that got split — and extraction systematically drops **the host's opening question**, which is exactly the context readers lack.

Core card shape:

```yaml
source: { content_id, platform, title, url, audio_url, published_at }
people: [{ person_id, name, role, identity }]        # role: host/guest/mentioned
entities: [{ entity_id, name, type }]                # plain slug, no type suffix
claims:
  - claim_id: c01
    statement: "one-sentence claim (a position, not a description)"
    speaker: person_id
    timestamp: "12:34"          # start
    end: "13:10"                # end, max 300 s
    type: assertion|prediction|definition|...
    relations:                  # relations to other claims
      - { type: supports, target: c05, note: "why" }
groups: [{ gid, name, ids }]    # top-level page groups; must cover every claim
arcs:                           # primary reading view: 8–18 per episode
  - arc_id: a01
    title: "From physics to neuroscience: a twenty-year detour"
    summary: "What this segment is about (2–3 sentences, give the reader a reason to listen)"
    start: "01:14"             # playback range (with lead-in/lead-out)
    end: "10:08"
    duration_sec: 534
    speech_sec: 500            # speaking time only
    open_question: "…"         # the host's question that opens the topic (when available)
    open_line: "…"             # transcript line where the topic starts (speaker-agnostic)
    points: [{ claim_id, at, statement }]   # 2–4 key points, time-ordered
    beats:  [{ at, gist, claims }]          # 3–6 turns
    evidence: [c01, c02, …]                 # every claim this arc covers (collapsed)
    context: [{ arc_id, why }]              # what earlier arc sets this one up
extensions: { concepts: [...], corrections: [...] }
```

Full schema and field constraints: [sop/SOP.md](sop/SOP.md) (English: [sop/SOP.en.md](sop/SOP.en.md)); arc field examples: [examples/arcs.example.json](examples/arcs.example.json).

## Steps

Each step states **what to do** and **how to know it is done**; always confirm command syntax with `--help` on the spot.

1.  **Runtime check (every time, first)**
    Use the bundled launcher — the CLI is inside the skill, so nothing needs installing:

    ```bash
    python3 <skill-dir>/bin/podcast-kg.py doctor
    ```

    If `podcast-kg` happens to be on PATH, that works too. `doctor` reporting the transcribe deps
    as missing is normal: the first `transcribe` / `models fetch` installs `faster-whisper` + `av`
    into `$PODCAST_KG_HOME/venv` (hundreds of MB, needs network), then works offline. To inspect or
    preinstall explicitly: `<skill-dir>/bin/bootstrap.py [--check|--json]`. If the launcher fails,
    report the exact command and output — do not guess.

2.  **Transcribe**
    Use the `transcribe` subcommand (`podcast-kg transcribe --help`). You get segment-level timestamps (JSON) plus a `[mm:ss]` transcript; all later references use that timeline. Slice long audio first, ideally ≤40 minutes per piece.

    **Weights are not shipped with the skill** (`small` is 486 MB): the first run downloads them into the HF cache. For offline / intranet machines, first `podcast-kg models fetch --model small`, or point `--model-dir DIR` / `PODCAST_KG_MODEL_DIR` at a downloaded directory; `podcast-kg models list` shows size and state, and with `PODCAST_KG_OFFLINE=1` missing weights fail fast instead of going online.

    Add `--words` when you need topic arcs: it also writes `<audio>_words.json` (word-level timestamps). **Arc boundaries must land on word boundaries**, otherwise the opening loses or gains half a word (segment timestamps only have 0.1 s granularity, so cut points often land mid-word).

3.  **Fix proper nouns**
    Read the transcript first and build a `transcript_corrections` table (whisper is systematically wrong on names and product names). **Always quote corrected spellings.**

4.  **Extract per the SOP**
    - Claim test: a position, not a description; must stand on its own
    - Timestamps: start at speech onset; end defaults to the next claim's start, max 300 s
    - Relations: only when a real semantic relation exists; no self-loops, no dangling targets
    - Entities: plain slugs; generic concepts go to `extensions.concepts`, not `entities`

5.  **Group into topic arcs (the key step)**
    Group claims into arcs using "host opens a topic → guest develops it → it closes"; parameters are in `podcast-kg arcs --help` (if that subcommand is missing, use `build_arcs.py` in this repo — it reads `.outputs/` and writes `.outputs/arcs/`). The hard rules are in [sop/SOP.md](sop/SOP.md) §2.7 (English: [sop/SOP.en.md](sop/SOP.en.md)); the two easiest ways to go wrong are:
    - **Boundaries only come from pauses and the host taking the floor** — never from sentence counts or group edges
    - **Never merge across topic groups**: cross-group merges are allowed only when shorter than 60 s

    After the arcs are set, write `title` / `summary` (auto titles are a fallback; these two lines are what readers see).

    With `--words` output, `build_arcs.py` snaps each arc's start/end to the nearest word boundary and writes fractional seconds (`1:04:18.72`); whole seconds would cut words. Without word timestamps it falls back to whole seconds.

    When all four automatic signals fail (typically the host interjects mid-passage with "one last question"), set the cut manually in the curated file: `"<content_id>": {"_breaks": [{"before": "c69", "at": "1:04:18"}]}`. Manual cuts win over everything: no merge crosses them, and the two sides do not overlap; a side under 60 s is ignored with a warning.

6.  **Verify**
    `verify` has three modes — default report, `--build-registry`, `--coverage`; confirm with `podcast-kg verify --help`. **Problems in the report are not a failed command**: exit code 0 still requires reading the report.

    Check arcs separately: does `evidence` cover every claim, do adjacent playback ranges overlap, are there any segments under 60 s?

7.  **Produce outputs**
    - Cards: `.outputs/<content_id>.json` and `.outputs/<content_id>.md`
    - Arcs: `<content_id>_arcs.json` (for the product side) + `<content_id>_arcs.html` (local QA)
    - Bilingual: `podcast-kg i18n scaffold` → fill text → `i18n check` → `render --i18n` (step 8)
    - HTML: the `render` subcommand; the page shares the DOM/styles of [heronai.top](https://heronai.top) detail pages. With `arcs` in the card (or a sibling `<card>_arcs.json`, or `--arcs`) it **renders by topic arc**, otherwise it falls back to the claim-row view
    - Graph: the `ingest` subcommand (stdlib, offline; dedupes by id only, no fuzzy entity resolution)

8.  **Bilingual zh/en (default delivery)**

    **Audio unchanged**: original source, original timeline, text only.

    ```bash
    # skeleton: ids / timestamps / groups / relations preserved, text blank
    podcast-kg i18n scaffold .outputs/<id>.json --lang en

    # fill only these fields: source.title/series, groups[].name, people[].role/identity,
    # claims[].statement/evidence/relations[].note,
    # arcs[].title/summary/open_question/open_line/points[].statement/beats[].gist
    # keep proper nouns as-is (Claude Code / Orca / ADE / harness) — do not force-translate

    podcast-kg i18n check .outputs/<id>.json .outputs/<id>.en.json   # hard errors -> exit 1
    podcast-kg render .outputs/<id>.json .outputs/<id>.html \
      --i18n en=.outputs/<id>.en.json --default-lang zh
    ```

    Rules and the field table: [sop/SOP.en.md](sop/SOP.en.md) §7. **Do not** produce one HTML per language.

## Quality gates (mandatory)

- [ ] Every claim's `timestamp`/`end` maps to the audio
- [ ] `groups[].ids` covers every claim exactly once
- [ ] Every `relations[].target` exists; no self-loops
- [ ] Speaker labels cross-checked against turn-taking (whisper does no diarisation)
- [ ] Spot-check 3 claims against the audio; no quote is taken out of context

Bilingual layer:

- [ ] `i18n check` reports 0 errors; `timestamp`/`end` are identical across languages
- [ ] Spot-check 3 claims: no lost hedges ("may / about / reportedly"), proper nouns preserved
- [ ] Arc `title`/`summary` read naturally in both languages, not word-for-word translations
- [ ] Only one HTML; switching to EN translates buttons/hints/contents/player bar, and `#claim-c21` still lands
- [ ] The player only plays the original audio (no dubbed track, no second source)

Topic-arc layer (claim rows alone are not "done"):

- [ ] `arcs[].evidence` together cover every claim, none missing
- [ ] Arc `start`/`end` land on word boundaries (automatic with `--words`); adjacent ranges do not overlap
- [ ] No arc under 60 s; median arc length is 3–10 minutes
- [ ] Every arc answers "what did the host ask?" — has `open_question` or `open_line`
- [ ] Spot-check 3 arcs (earliest / median / longest) end-to-end; each stands on its own
- [ ] `title` / `summary` were written by a human, not an auto-truncated half sentence

## Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating a description as a claim | The card becomes a running log | Only take positions |
| Timestamping the whole segment | Back-links are useless | Precise to the second; end on a semantic boundary |
| Type suffix on entity ids | Cannot merge across cards | `pi`, not `pi-agent` |
| Inventing relations to look dense | Graph noise | Better fewer edges |
| Skipping speaker verification | Claims attributed to the wrong person | Read the surrounding turn-taking |
| Using claim rows as the reading unit | The reader hears half a sentence and must click several times | Ship `arcs`; claims become evidence |
| Starting extraction before `podcast-kg` works | `command not found` halfway through `transcribe` | Run `doctor`; on failure run `bin/bootstrap.py`, then `doctor` |
| Only recording guest claims, dropping the host's questions | Why the topic started, and what it answers, is lost | Put the host's question in `open_question`/`open_line` |
| Splitting arcs by sentence count or group edges | Cut mid-topic; the listener is cut in half | Boundaries only from pauses and the host |
| Translation changed ids / timestamps / groups | Language switch misaligns; deep links break | Translate text only; `i18n check` blocks drift |
| One HTML per language | The two drift apart; shared links fork | One HTML + `--i18n`, top-bar switch |
| Dubbing the English version / swapping audio | Listeners hear someone else | Keep the original audio only |
| Host transitions mid-passage yet the arc continues | A topic is buried at the end of the previous arc; readers only notice halfway in | Set a manual `_breaks` cut in the curated file |
| Ten-plus points per arc, with relations | A running log in a different shape | 2–4 points per arc; relations only connect arcs |
| Arc ranges butt-joined with no padding | Every segment starts half a sentence late and ends clipped | 10 s lead-in, 6 s lead-out, then split at the midpoint |
