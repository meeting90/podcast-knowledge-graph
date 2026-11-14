# Structured Content Extraction SOP

> 中文版：[SOP.md](SOP.md)

> All tooling goes through the `podcast-kg` CLI; this document only defines **content standards**. Command arguments are always governed by `podcast-kg <subcommand> --help`.

---

## 1. Inputs

1. **Audio/video**: a direct URL is preferred, used for timestamp back-links and QA;
2. **Transcript**: local whisper, with segment timestamps;
3. **Episode metadata**: title, shownotes, guest bios, chapter outline (if any).

Without a transcript, run `podcast-kg transcribe` first (see `--help`).

---

## 2. Schema

### 2.1 Core fields

```yaml
# ── metadata ──
source:
  content_id: string          # globally unique: platform_date_number (e.g. transistor_20260917_319)
  platform: enum              # transistor.fm / xiaoyuzhoufm / youtube / mp.weixin ...
  title: string
  url: string                 # original page / audio page
  audio_url: string?          # direct URL, the basis for timestamp back-links
  duration_sec: int?
  published_at: date
  series: string?
  episode_no: string?

groups:                       # required; top-level topic groups on the claim page
  - gid: g1
    name: "① Product & Engineering"
    ids: [c01, c02, ...]      # must cover every claim_id exactly once

arcs:                         # required; the primary reading view (see §2.7)
  - arc_id: a01               # a01…, unique within the card
    title: "From physics to neuroscience: a twenty-year detour"
    summary: "What this segment is about (2–3 sentences)"
    start: "01:14"             # playback range (with lead-in/lead-out)
    end: "10:08"
    duration_sec: 534
    speech_sec: 500           # speaking time only
    open_question: "…"        # the host's opening question (required when present)
    open_line: "…"            # transcript line where the topic starts
    points:                   # 2–4, time-ordered
      - { claim_id: c01, at: "02:43", end: "03:22", statement: "…", speaker: "…" }
    beats:                    # 3–6 turns
      - { at: "02:43", end: "03:30", speaker: "noah-shinn", gist: "…", claims: [c01] }
    evidence: [c01, c02, c03] # every claim this segment covers (collapsed)
    context: [{ arc_id: a03, why: "…" }]  # which earlier arc sets this one up
    arc_relations: [{ target: a05, type: supports, count: 2 }]

# ── people ──
people:
  - person_id: string         # global slug (see §2.6)
    name: string
    aliases: string[]         # aliases / English name / nickname
    role: enum                # host / guest / mentioned (required)
    identity: string
    org: string[]
    links: url[]
    first_appeared_in: content_id

# ── entities ──
entities:
  - entity_id: string         # global slug (see §2.4)
    type: enum                # company / product / book / paper
    name: string
    aliases: string[]         # Chinese name / former name / alternate name
    url: string?
    context: string           # role in this piece of content

# ── claims ──
claims:
  - claim_id: string          # c001... (unique within the card)
    speaker: person_id        # must exist in people
    timestamp: "mm:ss"
    end: "mm:ss"
    type: enum                # methodology / prediction / fact / lesson / contested
    statement: string         # ≤ 50 Chinese chars (≤ 25 English words)
    evidence: string?
    confidence: enum          # stated directly / inferred from paraphrase / consensus in dialogue
    relations: [{type, target, note}]
    tags: string[]

# ── open area ──
extensions:
  concepts:                   # generic concepts / methods / frameworks; not entities
    - {name: "Agent Harness", note: "umbrella term for a class of tools", ref_claims: [c02]}
  ...                         # other business attributes (see §2.2)

transcript_corrections:       # proper-noun corrections (see §4.4)
```

### 2.2 Open extension fields

Core fields are fixed; business attributes are open, but every new attribute must be registered.

| Attribute | Type | Purpose |
|---|---|---|
| `concepts` | list[{name, note, ref_claims}] | generic concepts / frameworks |
| `contrarian_views` | list[{claim_ref, why_contrarian}] | against-consensus views |
| `costs` / `opportunities` / `action_items` | list | as needed |

**Attribute registry** (maintained): when an attribute first appears, record `name / type / first content_id / description`.

### 2.3 Claim relations

`relations` is required (may be an empty array, but must be explicit). Eleven legal relation types, all with forward semantics:

| Type | Meaning | Type | Meaning |
|---|---|---|---|
| supports | supports | responds_to | responds to |
| exemplified_by | exemplified by | parallel | parallel |
| extends | extends | implies | implies |
| deepens | deepens | precondition | precondition |
| tension_with | in tension with | part_of | part of |
| echoes | echoes | | |

**Three hard constraints**: no self-loops; no dangling targets (every target must exist); no redundant reverse edges.

### 2.4 Entity ID rules

Violating any rule is reported by `podcast-kg verify` (it only reports — it does not exit non-zero, so read the report).

1. **Format**: lowercase, `a-z0-9-` only, hyphen-separated. No CJK, spaces, underscores or uppercase.
2. **No type affixes**:
   - ❌ `pi-agent` / `book-zhineng` / `jeff-dean-papers`
   - ✅ `pi` / `intelligence-book` / `jeff-dean`
3. **One id, one entity**: never concatenate two different objects.
   - ❌ `openclaw-opencode` (while the name is OpenCode)
   - ✅ split into `openclaw` + `opencode`
4. **Pick the most recognisable name**: prefer the official English company/product name; for Chinese-only official names use pinyin + category.
   - ✅ `doubao`, `kimi`, `openai`, `claude-code`
   - Chinese names go into `aliases`
5. **Versions/models do not enter ids**: when `gpt-4` and `gpt-4o` are the same family, use `gpt-4` and put the model in `context`; only split when they are genuinely separate products.
6. **Same object, same id across cards**: check `.outputs/registry/entities.json` first; reuse on hit.

### 2.5 Entities vs concepts

| Test | Goes to | Examples |
|---|---|---|
| A **specific object you can point at**: company, product, book, paper | `entities` | OpenAI, Orca, Codex, *Intelligence*, Quoc Le |
| **Generic category / method / framework / metaphor** | `extensions.concepts` | Agent Harness, cask theory, Drucker's three revolutions, the loom analogy |
| **Entity + category mixed together** | Split | `Netscape/browser` → entity `netscape` + concept `browser` |

Rule of thumb: **"can you point at one concrete thing and say 'that one'?"** Yes → entity; no → concept.

### 2.6 People vs entities

- `people` holds only **people who appear in the episode** (speaking or explicitly introduced). `role` is required, one of `host` / `guest` / `mentioned`.
- Person names **must not** appear in `entities`. If someone is *being discussed* rather than present (e.g. a CEO's strategy), they still go in `people` with `role: mentioned`.
- `person_id` follows the slug rules in §2.4: `given-family` pinyin (`liang-wenfeng`), no role suffix.
- The same person may have different roles on different cards (guest on A, mentioned on B) and keeps the same `person_id`.

### 2.7 Topic arcs `arcs` (the reading unit, required)

**Why this layer exists**: claim rows are an index, not a reading unit. In practice 60–75% of adjacent claims are ≤2 s apart — they were one passage split up — and claim extraction naturally keeps only "positions", filtering out **the question that opened the topic**. The reader ends up with neither opening nor context and has to click several times to build any.

**Definition**: one arc = the host opens a topic → the guest develops it → the topic closes. Inside an arc you should see "question → answer → follow-up → wrap-up", not a flat list of claims.

| Field | Required | Constraint |
|---|---|---|
| `arc_id` | ✓ | starting at `a01`, unique within the card |
| `title` | ✓ | a judgement or a question, not half a sentence; auto titles are a fallback only |
| `summary` | ✓ | 2–3 sentences explaining why this segment is worth hearing in full |
| `start` / `end` | ✓ | playback range; **adjacent arcs must not overlap**; use `h:mm:ss` beyond 60 min; with word timestamps include fractional seconds (`1:04:18.72`) so cuts land on word boundaries |
| `duration_sec` | ✓ | `end - start`; record `speech_sec` separately for speaking time |
| `open_question` | when present | the host's question in their own words (when speakers can be distinguished) |
| `open_line` | recommended | transcript line at the arc start; whisper does no diarisation, so do not assert attribution |
| `points` | ✓ | **2–4**, time-ordered; choose by citation count + type weight |
| `beats` | ✓ | 3–6 turns, one sentence each; do not copy claims verbatim |
| `evidence` | ✓ | every claim_id the arc covers; **across all arcs this must cover 100% of claims** |
| `context` | optional | cross-arc dependency: which earlier arc sets this up |
| `arc_relations` | optional | arc-to-arc relations; **do not link sentences inside an arc** |

**Hard boundary rules** (ordered by reliability; only these four count):

1. **Pause ≥ 20 s** (strong boundary) — real topic changes almost always come with several seconds of silence;
2. **Topic group change** (`groups` boundary);
3. **Host asks again** (guest → host turn change);
4. **Pause ≥ 8 s** (weak boundary).

**Manual cuts (fallback)**: when the host transitions mid-passage ("one last question before we wrap"), with neither a pause nor a group change on either side, all four signals fail and you must set the cut in the curated file:

```json
{ "<content_id>": { "_breaks": [{ "before": "c69", "at": "1:04:18" }] } }
```

`at` is optional and defaults to the midpoint between the two claims. Semantics: claims before the cut belong to the previous arc, after it to the next; `at` is the previous arc's `end` and the next arc's `start` (no extra padding, no overlap). If either side ends up under 60 s the cut is ignored. No automatic merge ever crosses a manual cut.

Duration constraints: target **3–10 minutes**; below the floor merge into a neighbour, above the ceiling split at the longest pause. If the card itself is coarse (median claim > 80 s), raise the floor to 5 minutes and the ceiling to 13 minutes — otherwise a segment holds only two claims.

Forbidden:

- Splitting by sentence count or fixed claim count;
- Blindly merging across topic groups (cross-group only when under 60 s);
- Fewer than 2 claims in an arc (unless the card is extremely sparse);
- No padding at arc edges — 10 s lead-in and 6 s lead-out, then split at the midpoint to avoid overlap;
- Cuts landing mid-word — a `0.3 s` offset is enough to lose half a word at the start. Use `transcribe --words` word timestamps and snap cuts to the nearer end of the word (a word is either fully in one arc or fully in the next).

---

## 3. Extraction flow (eight steps)

```
S0 Load registries — read .outputs/registry/entities.json and .outputs/registry/people.json
                     (start empty if absent; ids extracted here are stored in S7)

S1 Metadata        — fill the source block mechanically, without interpreting content
S2 People          — distinguish host/guest/mentioned; cross-check guest identity; enforce speaker checks (§4)
S3 Entities        — reuse from the registry; mark unmatched ones new:true; decide entity vs concept (§2.5)
S4 Claims          — extract claim by claim; always with timestamp+end+speaker+relations
S4.5 Topic arcs    — group into arcs per §2.7; write title/summary; check full evidence coverage and non-overlap
S5 Extensions      — put specific dimensions in extensions; concepts in extensions.concepts; register new attributes
S6 QA back-links   — spot-check 3 claims (earliest / median / end) + 3 arcs (earliest / median / longest) against audio
S7 Cross-card      — a) run `podcast-kg verify` over all cards
                     b) resolve A: id conflicts / B: suspected duplicates / C: new entities
                     c) after human confirmation write back to the registry, then update ids in each card
                     d) re-run until zero conflicts
```

S7 is the only horizontal pass: the first six steps are single-card and cannot see cross-card id drift, so it must be its own step.

---

## 4. Mandatory verification

### 4.1 Speaker verification (S2 / S4)

whisper does no diarisation, so speaker labels must be cross-checked:

1. **Turn-taking**: host/guest should alternate; pronoun stance ("our product" vs "your product") is a strong signal;
2. **Transition cues**: "right," "exactly" usually come from the listener; questions usually from the host; self-corrections/examples from the speaker;
3. If the two conflict or cannot be resolved, mark `confidence: inferred from paraphrase` and listen again;
4. When the host restates a guest's claim, keep the guest as speaker and add a note.

**Long uninterrupted passages by one person are the easiest to mislabel — check them specifically.**

### 4.2 S6 QA back-links

Before finalising a card, spot-check 3 claims (earliest / median / one that triggered the end cap): verify statement semantics, speaker attribution and the end boundary at a topic change. Fix and record in the QA report.

Then the **arc check** (this layer is the easiest to get looking right while being unlistenable):

| Check | Criterion | If it fails |
|---|---|---|
| Full coverage | deduped `arcs[].evidence` == all claim_ids | recover the missing claims or add an arc |
| No overlap | adjacent `end ≤ next start` | split at the midpoint of the pause |
| No crumbs | no arc `< 60 s`; median 3–10 min | merge into a neighbour |
| Has context | every arc has `open_question` or `open_line` | listen to the 15 s before the arc start |
| Stands alone | spot-check 3 arcs (earliest / median / longest) end-to-end, audio only | boundaries are wrong; re-cut |

### 4.3 S7 cross-card verification

```bash
# pass cards only (no *_transcript.json / *_graph.json)
podcast-kg verify .outputs/<id1>.json .outputs/<id2>.json
podcast-kg verify --build-registry .outputs/registry/entities.json .outputs/<id1>.json .outputs/<id2>.json
```

(Other switches: `podcast-kg verify --help`.)

Three report classes:

| Class | Meaning | Action |
|---|---|---|
| **A. id conflict** | the same name used different ids across cards | must fix: unify to the registry id |
| **B. suspected duplicate** | very similar names, different ids | confirm whether it is the same object; merge ids |
| **C. new entity** | id not in the registry | confirm and add to the registry |

Built-in automatic checks:

- ids match `^[a-z0-9][a-z0-9-]*$`
- ids contain type affixes (`-agent`, `book-`, `-papers`, …)
- the same id has inconsistent names (possible concatenation)
- person names leaked into entities
- `groups` covers all claims (none missing, none duplicated)

### 4.4 Transcript proper-noun corrections

whisper is error-prone on names and products (clock→Claude, 虎精→Orca, 曾敏→曾鸣, Hardness→Harness). Maintain `transcript_corrections`: `{raw, corrected, where, note}`. Always quote corrected spellings; reuse the table for the next episode in the same series.

---

## 5. Timestamp back-linking

Two interval layers — arcs and claims — over one audio file:

- **claim back-link** (fine): click a sentence and jump there; used for quotes and graph provenance;
- **arc back-link** (coarse): click once to **play the whole segment continuously**, pausing at `end` — this is the reader's default interaction.

Arc range rules:

1. `start` = first claim's start − 10 s, but not earlier than the midpoint of the previous arc;
2. `end` = last claim's end + 6 s, but not later than the midpoint of the next arc;
3. **adjacent arc ranges never overlap**, otherwise continuous playback repeats ten-odd seconds;
4. beyond 60 minutes use `h:mm:ss`, never `66:21` (front ends that split on `:` get it wrong);
5. ad blocks and trailers are not arcs; record them in `extensions.ad_blocks`.

- `timestamp~end` is the back-link interval: clicking jumps to the start, playback pauses at `end`;
- **end rules**:
  1. default = next claim's `timestamp`;
  2. cap `end - timestamp ≤ 300 s`; beyond that cut at a topic pause;
  3. long cases/stories: set `end` manually at a transcript **silence boundary** (segment gap > 2 s);
  4. the last claim's `end` ≤ total audio duration;
  5. `end` never precedes `timestamp`; adjacent intervals never overlap.
- If shownotes have chapters, align to chapters first, then refine within the segment;
- Graph layer: `timestamp/end` is written as provenance into `provenance[]` in `*_graph.json` (audio URI + second-level range).

---

## 6. Outputs

Everything goes under `.outputs/` in the **current working directory** (explicit paths win):

```
.outputs/
├── <audio>_transcript.json / .txt
├── <content_id>.json / .md          base-language card (with arcs)
├── <content_id>.<lang>.json         translated card (same structure, text only; see §7)
├── <content_id>_arcs.json           topic-arc layer (for the product side)
├── <content_id>.html                single page; language switch in the top bar when multilingual
├── <content_id>_arcs.html           arc page (local QA: one click plays a whole segment)
├── <content_id>_graph.json
└── registry/
```

> Bilingual is a first-class output: `<content_id>.json` (Chinese) + `<content_id>.en.json` (English) + **one** `<content_id>.html`.
> The page switches language; the audio is always the original source.

Curated arc titles/ledes are a **human asset**; keep them in a separate `<content_id>_curated.json` (`content_id → arc_id → {title, summary}`),
because cuts are recomputable but good titles are not. It must travel with the card, otherwise only auto titles survive.

### 6.1 Files per piece of content

1. `.outputs/<content_id>.md` — human-readable (metadata table, people, entities, claims grouped by `groups`, corrections, QA notes);
2. `.outputs/<content_id>.json` — the complete base-language schema (single source of truth);
3. `.outputs/<content_id>.<lang>.json` — translated card, structurally identical (§7); without it `--i18n` has no input.

### 6.2 Global files

| File | Purpose |
|---|---|
| `.outputs/registry/entities.json` | entity source of truth: id / name / aliases / type / cards |
| `.outputs/registry/people.json` | people source of truth, including role history |
| `.outputs/registry/concepts.json` | concept vocabulary, used in S3 to separate entities from concepts |

### 6.3 Rendering

`podcast-kg render` — see `podcast-kg render --help`; writes `.outputs/<card>.html` by default.

The page shares the **same DOM and styles** as [heronai.top](https://heronai.top) detail pages (`assets/heron.css` is the site stylesheet, font subset inlined):
top bar → card header (platform/date, title, people, segment/claim counts, original episode) → toolbar → left topic nav + right topic arcs → comments → floating player.

* **The reading unit is the topic arc**: with `arcs` in the card (or `--arcs`, or a sibling `<card>_arcs.json`), each group renders `av-arc` cards; expanding shows "host's opening line → beats → key quotes → remaining claims"; without `arcs` it falls back to claim rows.
* **Picks**: ★ is stored in browser localStorage; "My picks" filters, "Share my view" copies a `#picks=…` link, "Export picks" downloads `picks_<id>.json`.
* **Multilingual**: `--i18n en=<id>.en.json` merges the translation into the same DOM and adds a "中文 / EN" switch; DOM, ids, deep links and the player stay single, only text changes (including buttons, hints, contents, time bar).
* After updating site styles, re-run `python scripts/refresh_heron_css.py` (see `skills/podcast-knowledge-graph/lib/podcast_kg/assets/README.md`).

---

## 7. Bilingual output (zh/en)

**Audio unchanged**: no dubbing, no second source, no re-cut timeline; only text changes.

### 7.1 Hard rules

1. The base card declares its language in `source.language` (defaults to `zh`); both cards share the same `content_id`, all `claim_id` / `arc_id` / `gid` / `person_id` / `entity_id`, and the order of `groups[].ids`;
2. Every claim's `timestamp` / `end` / `speaker` is identical; every arc's `start` / `end` / `duration_sec` is identical;
3. Translate text fields only (see 7.2); structural fields (ids, timestamps, relation targets, colours/order) are copied verbatim;
4. Write the translation to its own file `<content_id>.<lang>.json`; **do not** edit the base card;
5. Produce **one** HTML, merged with `--i18n`, with a top-bar switch; never two HTML files.

### 7.2 Translatable fields (nothing else)

| Layer | Fields |
| --- | --- |
| Card | `source.title`, `source.series`, `groups[].name` |
| People | `people[].role`, `people[].identity` (`name` is a proper noun, keep as-is) |
| Claims | `claims[].statement`, `claims[].evidence`, `claims[].relations[].note` |
| Arcs | `arcs[].title`, `arcs[].summary`, `arcs[].open_question`, `arcs[].open_line`, `arcs[].points[].statement`, `arcs[].beats[].gist` |

### 7.3 Flow

```bash
# 1) skeleton: ids / timestamps / groups preserved, text blank
podcast-kg i18n scaffold .outputs/<id>.json --lang en

# 2) fill the fields listed in 7.2
#    - keep proper nouns: Claude Code / Orca / ADE / harness; add a gloss on first use if helpful
#    - translate quotes (open_line / evidence) for meaning; do not pretend they are verbatim
#    - statement stays ≤50 Chinese chars (≤25 English words)

# 3) structural parity: hard errors exit 1; "untranslated" is a warning
podcast-kg i18n check .outputs/<id>.json .outputs/<id>.en.json

# 4) one bilingual page (audio unchanged, switch in the top bar)
podcast-kg render .outputs/<id>.json .outputs/<id>.html \
  --i18n en=.outputs/<id>.en.json --default-lang zh
```

### 7.4 Bilingual quality gates

- [ ] `i18n check` reports 0 errors; remaining warnings are only deliberate untranslated proper nouns/quotes
- [ ] Spot-check 3 claims: identical `timestamp` in both languages, same meaning, no lost hedges ("may / about / reportedly")
- [ ] Arc `title` / `summary` read naturally in both languages, not word-for-word
- [ ] Switching to EN in the HTML translates buttons, hints, time bar, contents; `#claim-c21` still lands
- [ ] Audio only plays the original source (no dubbed track)

---

## 8. Quality red lines

1. A claim must have speaker, timestamp and end;
2. Relations must not be self-loops or dangling;
3. `groups` must cover every claim;
4. `entity_id` / `person_id` must follow the slug rules in §2.4;
5. Person names must not appear in entities; generic concepts must not appear in entities;
6. Never invent timestamps; `end` must not exceed the audio duration;
7. A statement over 50 Chinese chars counts as unextracted — rewrite it;
8. `arcs[].evidence` together must cover every claim; orphan claims are forbidden;
9. Adjacent arc playback ranges must not overlap, and no arc may be under 60 s;
10. An arc `title` must not be the first N characters of a statement (write a human sentence instead);
11. `open_line` is a transcript line: do not rewrite it, and do not assert speaker attribution.
