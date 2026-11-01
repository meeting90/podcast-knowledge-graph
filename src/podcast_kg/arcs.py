"""话题弧（topic arc）切分：把逐句 claim 重新聚成「主持人和嘉宾讲完一件事」的单元。

为什么需要这一层
----------------
逐句 claim（中位 45–57 秒）适合做溯源索引，不适合阅读：
相邻 claim 有 60–75% 之间的间隔 ≤2 秒，说明它们是同一段话被切开的。
读者点开一张卡，听到的是半句话，既不知道主持人问了什么，也不知道这个结论
是在什么前提下成立的。

切分依据（按可靠性排序）
------------------------
1. 静音停顿：真实的话题切换几乎总伴随数秒以上的停顿；
2. 主持人开口：主持人重新提问/转场，是天然的新话题起点；
3. 主题分组：已有 groups 的边界；
4. 时长约束：目标 3–10 分钟，低于下限合并、高于上限在最长的停顿处再切。

一个弧的内部结构是「提问 → 回应 → 追问 → 收束」，所以弧记录里必须保留
主持人开场问题（open_question）；这正是旧卡丢掉、而读者最缺的东西。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

TARGET_MIN = 180      # 弧下限：短于此并进相邻弧
TARGET_MAX = 600      # 弧上限：长于此在最长的停顿处切
# 卡本身就粗（中位 >80s）的期次，弧要跟着放大，否则一段只剩两条卡
COARSE_MIN = 300
COARSE_MAX = 780
COARSE_TRIGGER = 80
MIN_CLAIMS_PER_ARC = 2
PAUSE_STRONG = 20     # 强边界：>=20s 停顿基本就是话题切换
PAUSE_WEAK = 8        # 弱边界：>=8s 停顿可能是段落切换
PAD_OPEN = 10         # 起点前留一点上下文
PAD_CLOSE = 6         # 终点后留一点收尾

KEY_POINT_MAX = 4     # 一个弧最多保留几条「要点」
BEATS_MAX = 6         # 一个弧的回合数上限


def to_sec(stamp: str) -> int:
    parts = [int(p) for p in stamp.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def to_stamp(sec: int) -> str:
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@dataclass
class Claim:
    claim_id: str
    start: int
    end: int
    speaker: str
    statement: str
    type: str = ""
    group: str = ""
    relations: list = field(default_factory=list)


@dataclass
class Arc:
    claims: list[Claim]
    start: int
    end: int

    @property
    def duration(self) -> int:
        return self.end - self.start


def load_claims(card: dict) -> list[Claim]:
    group_of: dict[str, str] = {}
    for g in card.get("groups", []) or []:
        for cid in g.get("ids", []):
            group_of[cid] = g.get("name", "")
    claims = []
    for c in card.get("claims", []) or []:
        if not c.get("timestamp"):
            continue
        start = to_sec(c["timestamp"])
        end = to_sec(c.get("end") or c["timestamp"])
        claims.append(
            Claim(
                claim_id=c["claim_id"],
                start=start,
                end=max(end, start + 5),
                speaker=c.get("speaker", ""),
                statement=(c.get("statement") or "").strip(),
                type=c.get("type", ""),
                group=group_of.get(c["claim_id"], ""),
                relations=c.get("relations") or [],
            )
        )
    claims.sort(key=lambda c: (c.start, c.end))
    return claims


def _host_ids(card: dict) -> set[str]:
    return {p["person_id"] for p in card.get("people", []) or [] if p.get("role") == "host"}


def _candidate_boundaries(claims: list[Claim], host_ids: set[str]) -> dict[int, tuple[int, str]]:
    """returns {index_of_next_claim: (strength, reason)}; strength 2=强 1=弱"""
    out: dict[int, tuple[int, str]] = {}
    for i in range(1, len(claims)):
        prev, cur = claims[i - 1], claims[i]
        pause = max(0, cur.start - prev.end)
        group_changed = bool(prev.group and cur.group and prev.group != cur.group)
        if pause >= PAUSE_STRONG:
            out[i] = (3, f"停顿 {pause}s")
        elif group_changed:
            out[i] = (2, "主题分组切换")
        elif cur.speaker in host_ids and prev.speaker not in host_ids:
            out[i] = (2, "主持人重新提问")
        elif pause >= PAUSE_WEAK:
            out[i] = (1, f"停顿 {pause}s")
    return out


def _cut(claims: list[Claim], boundary: dict[int, tuple[int, str]]) -> list[list[Claim]]:
    blocks, cur = [], [claims[0]]
    for i in range(1, len(claims)):
        if i in boundary:
            blocks.append(cur)
            cur = [claims[i]]
        else:
            cur.append(claims[i])
    blocks.append(cur)
    return blocks


def _span(block: list[Claim]) -> int:
    return block[-1].end - block[0].start


def _merge_small(blocks: list[list[Claim]], minimum: int, keep_group_edges: bool = True) -> list[list[Claim]]:
    changed = True
    while changed and len(blocks) > 1:
        changed = False
        for i, b in enumerate(blocks):
            if _span(b) >= minimum:
                continue
            left = _span(blocks[i - 1] + b) if i > 0 else None
            right = _span(b + blocks[i + 1]) if i + 1 < len(blocks) else None
            if left is None and right is None:
                break
            pick_left = right is None or (left is not None and left <= right)
            neighbour = blocks[i - 1] if pick_left else blocks[i + 1]
            # 主题分组边界是强信号：只有小到 60s 以下才允许跨组并进来
            crosses_group = bool(b[0].group and neighbour[0].group and b[0].group != neighbour[0].group)
            if keep_group_edges and crosses_group and _span(b) >= 60:
                continue
            if pick_left:
                blocks[i - 1] = blocks[i - 1] + b
            else:
                blocks[i + 1] = b + blocks[i + 1]
            blocks.pop(i)
            changed = True
            break
    return blocks


def _split_large(block: list[Claim], maximum: int) -> list[list[Claim]]:
    if _span(block) <= maximum or len(block) < 3:
        return [block]
    # 在最长的内部停顿处切
    best_i, best_pause = None, -1
    for i in range(1, len(block)):
        pause = block[i].start - block[i - 1].end
        if pause > best_pause:
            best_i, best_pause = i, pause
    # 没有停顿就在时长中点附近切
    if best_pause < PAUSE_WEAK:
        half = block[0].start + _span(block) // 2
        best_i = min(range(1, len(block)), key=lambda i: abs(block[i].start - half))
    left, right = block[:best_i], block[best_i:]
    return _split_large(left, maximum) + _split_large(right, maximum)


def _absorb_tiny(blocks: list[list[Claim]], minimum_claims: int, max_span: int | None = None) -> list[list[Claim]]:
    """只剩一两条 claim 的弧并进相邻弧：读者点开只有 30 秒，等于又回到碎片。"""
    out = [list(b) for b in blocks]
    i = 0
    while i < len(out) and len(out) > 1:
        if len(out[i]) >= minimum_claims:
            i += 1
            continue
        left = _span(out[i - 1] + out[i]) if i > 0 else None
        right = _span(out[i] + out[i + 1]) if i + 1 < len(out) else None
        # 合并后会超长，就宁可留一条短弧，也不做出十几分钟的巨段
        if max_span is not None:
            if left is not None and left > max_span:
                left = None
            if right is not None and right > max_span:
                right = None
            if left is None and right is None:
                i += 1
                continue
        if right is not None and (left is None or right <= left):
            out[i + 1] = out[i] + out[i + 1]
            out.pop(i)
        else:
            out[i - 1] = out[i - 1] + out[i]
            out.pop(i)
            i = max(0, i - 1)
    return out


def _salience(claims: list[Claim], degree: dict[str, int]) -> list[Claim]:
    """挑代表点：被关系引用最多的优先，其次争议/判断/方法论，最后按时长。"""
    weight = {"争议观点": 3, "contrarian_view": 3, "判断预测": 2, "prediction": 2,
              "方法论": 2, "methodology": 2}
    ranked = sorted(
        claims,
        key=lambda c: (-degree.get(c.claim_id, 0), -weight.get(c.type, 0), -(c.end - c.start)),
    )
    return ranked[:KEY_POINT_MAX]


def _beats(block: list[Claim], minimum: int = 40) -> list[dict]:
    """把弧内部压成 3–5 个回合：不再逐句，而是「这一段在讲什么」。"""
    runs: list[list[Claim]] = []
    cur: list[Claim] = []
    for c in block:
        if cur and (c.speaker != cur[-1].speaker or c.start - cur[-1].end >= PAUSE_WEAK * 2):
            runs.append(cur)
            cur = [c]
        else:
            cur.append(c)
    if cur:
        runs.append(cur)
    # 合并过短的 run，直到 <= BEATS_MAX
    while len(runs) > BEATS_MAX:
        idx = min(range(len(runs) - 1), key=lambda i: len(runs[i]) + len(runs[i + 1]))
        runs[idx] = runs[idx] + runs[idx + 1]
        runs.pop(idx + 1)
    beats = []
    for run in runs:
        if not run:
            continue
        rep = max(run, key=lambda c: len(c.statement))
        beats.append({
            "at": to_stamp(run[0].start),
            "end": to_stamp(run[-1].end),
            "speaker": rep.speaker,
            "gist": rep.statement,
            "claims": [c.claim_id for c in run],
        })
    return beats


def _context(block: list[Claim], arc_index: dict[str, int], self_idx: int,
             arc_titles: list[str], card: dict) -> list[str]:
    """这个弧依赖的其他弧：来源是跨弧的 claim 关系。"""
    deps: dict[int, list[str]] = {}
    people = {p["person_id"]: p.get("name", p["person_id"]) for p in card.get("people", []) or []}
    for c in block:
        for r in c.relations:
            other = arc_index.get(r.get("target", ""))
            if other is None or other == self_idx:
                continue
            deps.setdefault(other, [])
            note = r.get("note") or ""
            deps[other].append(f"{people.get(c.speaker, c.speaker)}在 {to_stamp(c.start)} 的「{c.statement[:18]}…」{r.get('type')} 它{('（' + note + '）') if note else ''}")
    out = []
    for idx in sorted(deps):
        out.append({
            "arc_id": f"a{idx + 1:02d}",
            "title": arc_titles[idx] if idx < len(arc_titles) else "",
            "why": deps[idx][0],
        })
    return out


def _auto_title(block: list[Claim], degree: dict[str, int], group_count: dict[str, int]) -> str:
    """组名已经是好标题；同组多弧时再加一个限定词区分。"""
    group = block[0].group or ""
    short = group.split(" ", 1)[1] if group[:1] in "①②③④⑤⑥⑦⑧⑨⑩" and " " in group else group
    top = max(block, key=lambda c: (-degree.get(c.claim_id, 0), len(c.statement)))
    text = top.statement
    qualifier = ""
    for sep in ("：", "，", "；", "——"):
        if sep in text[:30]:
            head = text.split(sep)[0]
            if 4 <= len(head) <= 18:
                qualifier = head
                break
    if not qualifier:
        qualifier = text[:16]
    if short and group_count.get(group, 0) > 1:
        return f"{short}：{qualifier}"
    return short or qualifier


def build_arcs(card: dict) -> dict:
    claims = load_claims(card)
    if not claims:
        raise SystemExit("卡里没有带时间戳的 claims")

    host_ids = _host_ids(card)
    degree: dict[str, int] = {}
    for c in claims:
        for r in c.relations:
            degree[c.claim_id] = degree.get(c.claim_id, 0) + 1
            degree[r.get("target", "")] = degree.get(r.get("target", ""), 0) + 1

    median_claim = _median([c.end - c.start for c in claims])
    coarse = median_claim >= COARSE_TRIGGER
    min_sec = COARSE_MIN if coarse else TARGET_MIN
    max_sec = COARSE_MAX if coarse else TARGET_MAX

    boundary = _candidate_boundaries(claims, host_ids)
    blocks = _cut(claims, boundary)
    blocks = _merge_small(blocks, min_sec)
    split: list[list[Claim]] = []
    for b in blocks:
        split.extend(_split_large(b, max_sec))

    # 再合并一次：切完可能又出现过短弧
    split = _merge_small(split, min_sec // 2)
    split = _absorb_tiny(split, MIN_CLAIMS_PER_ARC, max_span=int(max_sec * 1.15))

    group_count: dict[str, int] = {}
    for b in split:
        if b[0].group:
            group_count[b[0].group] = group_count.get(b[0].group, 0) + 1

    titles = [_auto_title(b, degree, group_count) for b in split]
    arc_index = {c.claim_id: i for i, b in enumerate(split) for c in b}
    total = (card.get("source", {}) or {}).get("duration_sec")

    # 相邻弧之间的「分界点」取在停顿的中点；没有停顿就取上一段结束处，
    # 保证两段的播放区间永不重叠（否则连播时会听到重复的十来秒）。
    mids: list[int] = []
    for i in range(len(split) - 1):
        prev_end, next_start = split[i][-1].end, split[i + 1][0].start
        mids.append((prev_end + next_start) // 2 if next_start > prev_end else prev_end)

    arcs = []
    for i, block in enumerate(split):
        left_mid = mids[i - 1] if i > 0 else 0
        start = max(left_mid, block[0].start - PAD_OPEN, 0)
        right_mid = mids[i] if i < len(mids) else None
        end = block[-1].end + PAD_CLOSE if right_mid is None else min(block[-1].end + PAD_CLOSE, right_mid)
        if total:
            end = min(end, int(total))
        end = max(end, block[-1].end)
        group_names = []
        for c in block:
            if c.group and c.group not in group_names:
                group_names.append(c.group)
        openers = [c for c in block if c.speaker in host_ids]
        arcs.append({
            "arc_id": f"a{i + 1:02d}",
            "title": titles[i],
            "group": group_names[0] if group_names else "",
            "start": to_stamp(start),
            "end": to_stamp(end),
            "duration_sec": end - start,
            "speech_sec": block[-1].end - block[0].start,
            "open_question": openers[0].statement if openers and openers[0].start == block[0].start else "",
            "beats": _beats(block),
            "points": [
                {"claim_id": c.claim_id, "at": to_stamp(c.start), "end": to_stamp(c.end),
                 "statement": c.statement, "speaker": c.speaker}
                for c in sorted(_salience(block, degree), key=lambda c: c.start)
            ],
            "evidence": [c.claim_id for c in block],
            "context": _context(block, arc_index, i, titles, card),
        })

    # 弧之间的关系：把跨弧 claim 关系统计上来
    rel_counter: dict[tuple[str, str, str], int] = {}
    for c in claims:
        src_arc = f"a{arc_index[c.claim_id] + 1:02d}"
        for r in c.relations:
            tgt_arc = arc_index.get(r.get("target", ""))
            if tgt_arc is None:
                continue
            key = (src_arc, f"a{tgt_arc + 1:02d}", r.get("type", ""))
            if key[0] != key[1]:
                rel_counter[key] = rel_counter.get(key, 0) + 1
    for a in arcs:
        a["arc_relations"] = [
            {"target": t, "type": typ, "count": n}
            for (s, t, typ), n in sorted(rel_counter.items())
            if s == a["arc_id"]
        ]

    return {
        "content_id": card.get("content_id"),
        "source": card.get("source", {}),
        "people": card.get("people", []),
        "policy": {
            "unit": "话题弧：主持人开启一个话题到它自然结束",
            "target_sec": [min_sec, max_sec],
            "coarse_card": coarse,
            "boundaries": ["停顿>=20s（强）", "主题分组切换", "主持人重新提问", "停顿>=8s（弱）"],
            "padding_sec": [PAD_OPEN, PAD_CLOSE],
            "key_points_max": KEY_POINT_MAX,
            "note": "底层逐句 claim 保留为证据层，不单独呈现为阅读单元",
        },
        "stats": {
            "claims": len(claims),
            "arcs": len(arcs),
            "median_claim_sec": _median([c.end - c.start for c in claims]),
            "median_arc_sec": _median([a["duration_sec"] for a in arcs]),
        },
        "arcs": arcs,
        "claims": card.get("claims", []),
        "groups": card.get("groups", []),
    }


def _median(values: list[int]) -> int:
    if not values:
        return 0
    values = sorted(values)
    mid = len(values) // 2
    return int(values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2)


def build_file(path: str, transcript: str | None = None) -> dict:
    card = json.load(open(path, encoding="utf-8"))
    data = build_arcs(card)
    if transcript:
        add_open_lines(data, transcript)
    return data


def load_transcript(path: str) -> list[tuple[int, str]]:
    """读 [mm:ss] text 形式的转写稿。"""
    rows: list[tuple[int, str]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("[") or "]" not in line:
                continue
            stamp, text = line[1:].split("]", 1)
            try:
                rows.append((to_sec(stamp.strip()), text.strip()))
            except ValueError:
                continue
    return rows


def add_open_lines(data: dict, transcript_path: str, before: int = 0, after: int = 30) -> None:
    """给每个弧补上「开场原话」：弧起点前后那两句，就是主持人开启话题的话。

    whisper 不做说话人分离，所以这里如实标注为「转写原话」，不冒充说话人归属。
    """
    rows = load_transcript(transcript_path)
    if not rows:
        return
    for arc in data.get("arcs", []):
        s = to_sec(arc["start"])
        chunk = [t for (at, t) in rows if s - before <= at <= s + after]
        if chunk:
            arc["open_line"] = " ".join(chunk)[:260]
