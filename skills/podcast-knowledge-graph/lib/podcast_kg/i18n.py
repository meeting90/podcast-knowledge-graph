"""中英双语知识卡：结构对齐、字段合并、翻译脚手架。

双语的前提是**结构完全一致**：同一张卡的中文版和英文版必须共享
`content_id`、全部 `claim_id` / `arc_id` / `gid` / `person_id`，以及每一条的
时间戳。只有文字字段允许不同——否则时间点回链、弧的证据覆盖、深链
`#claim-c21` 全会错位。

本模块负责三件事：

  * `merge(base, locales)`   把多语言文字字段合并成 `{lang: text}` 供渲染器输出
                             `<span data-zh data-en>`；
  * `check(base, locale)`    结构对齐体检（id 集合、时间戳、弧区间），硬错会列出明细；
  * `scaffold(base, lang)`   生成一份只有结构、文字留空的译文骨架，交给 agent 填。
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Iterable

# 允许翻译的字段（其余字段视为结构，必须逐字一致）
CLAIM_TEXT = ("statement", "evidence")
ARC_TEXT = ("title", "summary", "open_question", "open_line")
PEOPLE_TEXT = ("role", "identity")
SOURCE_TEXT = ("title", "series")


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _ids(card: dict, key: str, id_key: str) -> list[str]:
    return [item[id_key] for item in (card.get(key) or []) if item.get(id_key)]


# ── 结构对齐 ─────────────────────────────────────────────────────────────────


def check(base: dict, locale: dict, locale_name: str = "locale") -> dict:
    """Return {"errors": [...], "warnings": [...]} for one locale card."""
    errors: list[str] = []
    warnings: list[str] = []

    if base.get("content_id") != locale.get("content_id"):
        errors.append(
            f"content_id 不一致：{base.get('content_id')!r} ≠ {locale.get('content_id')!r}"
        )

    def compare_ids(kind: str, key: str, id_key: str) -> None:
        left = set(_ids(base, key, id_key))
        right = set(_ids(locale, key, id_key))
        if left - right:
            errors.append(f"{kind} 缺少：{', '.join(sorted(left - right))}")
        if right - left:
            errors.append(f"{kind} 多出：{', '.join(sorted(right - left))}")

    compare_ids("claim_id", "claims", "claim_id")
    compare_ids("arc_id", "arcs", "arc_id")
    compare_ids("gid", "groups", "gid")
    compare_ids("person_id", "people", "person_id")
    compare_ids("entity_id", "entities", "entity_id")

    base_claims = {c["claim_id"]: c for c in base.get("claims") or [] if c.get("claim_id")}
    loc_claims = {c["claim_id"]: c for c in locale.get("claims") or [] if c.get("claim_id")}
    for cid in sorted(set(base_claims) & set(loc_claims)):
        for field in ("timestamp", "end", "speaker"):
            if base_claims[cid].get(field) != loc_claims[cid].get(field):
                errors.append(
                    f"{cid}.{field} 必须一致："
                    f"{base_claims[cid].get(field)!r} ≠ {loc_claims[cid].get(field)!r}"
                )
        if not _nonempty(loc_claims[cid].get("statement")):
            warnings.append(f"{cid}.statement 未翻译")

    base_arcs = {a["arc_id"]: a for a in base.get("arcs") or [] if a.get("arc_id")}
    loc_arcs = {a["arc_id"]: a for a in locale.get("arcs") or [] if a.get("arc_id")}
    for aid in sorted(set(base_arcs) & set(loc_arcs)):
        for field in ("start", "end", "duration_sec"):
            if base_arcs[aid].get(field) != loc_arcs[aid].get(field):
                errors.append(
                    f"{aid}.{field} 必须一致："
                    f"{base_arcs[aid].get(field)!r} ≠ {loc_arcs[aid].get(field)!r}"
                )
        if not _nonempty(loc_arcs[aid].get("summary")):
            warnings.append(f"{aid}.summary 未翻译")

    for gid, group in ((g["gid"], g) for g in base.get("groups") or [] if g.get("gid")):
        match = next(
            (g for g in locale.get("groups") or [] if g.get("gid") == gid), None
        )
        if match and list(group.get("ids") or []) != list(match.get("ids") or []):
            errors.append(f"分组 {gid} 的 ids 顺序/内容不一致（必须逐一对应）")

    if not (locale.get("source") or {}).get("title"):
        warnings.append("source.title 未翻译")

    return {
        "locale": locale_name,
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }


# ── 合并 ─────────────────────────────────────────────────────────────────────


def _text_map(values: dict[str, object]) -> dict[str, str]:
    return {lang: str(value).strip() for lang, value in values.items() if _nonempty(value)}


def merge(base: dict, locales: dict[str, dict], default: str | None = None) -> dict:
    """Return a card whose translatable text fields are `{lang: text}` maps.

    Structure is taken from `base`; text comes from every card that has it.
    Missing translations simply fall back at render time.
    """
    langs = [default or "zh", *[code for code in locales if code != (default or "zh")]]
    cards = {langs[0]: base, **locales}
    merged = copy.deepcopy(base)

    # source
    source = merged.setdefault("source", {})
    for field in SOURCE_TEXT:
        texts = _text_map({lang: (cards[lang].get("source") or {}).get(field) for lang in langs})
        if texts:
            source[field] = texts

    # groups
    for group in merged.get("groups") or []:
        gid = group.get("gid")
        for lang in langs[1:]:
            match = next(
                (g for g in locales[lang].get("groups") or [] if g.get("gid") == gid), {}
            )
            if _nonempty(match.get("name")):
                group.setdefault("name", {})
                if isinstance(group["name"], str):
                    group["name"] = {langs[0]: group["name"]}
                group["name"][lang] = match["name"]

    # people (names are proper nouns and stay untouched)
    for person in merged.get("people") or []:
        pid = person.get("person_id")
        for field in PEOPLE_TEXT:
            values = {langs[0]: person.get(field)}
            for lang in langs[1:]:
                match = next(
                    (p for p in locales[lang].get("people") or [] if p.get("person_id") == pid),
                    {},
                )
                values[lang] = match.get(field)
            texts = _text_map(values)
            if len(texts) > 1 or (texts and langs[0] not in texts):
                person[field] = texts

    # claims
    for claim in merged.get("claims") or []:
        cid = claim.get("claim_id")
        for field in CLAIM_TEXT:
            values = {langs[0]: claim.get(field)}
            for lang in langs[1:]:
                match = next(
                    (c for c in locales[lang].get("claims") or [] if c.get("claim_id") == cid),
                    {},
                )
                values[lang] = match.get(field)
            texts = _text_map(values)
            if texts:
                claim[field] = texts
        for index, relation in enumerate(claim.get("relations") or []):
            values = {langs[0]: relation.get("note")}
            for lang in langs[1:]:
                match_claim = next(
                    (c for c in locales[lang].get("claims") or [] if c.get("claim_id") == cid),
                    {},
                )
                match_rel = (match_claim.get("relations") or [])
                values[lang] = (
                    match_rel[index].get("note") if index < len(match_rel) else None
                )
            texts = _text_map(values)
            if texts:
                relation["note"] = texts

    # arcs
    for arc in merged.get("arcs") or []:
        aid = arc.get("arc_id")
        for field in ARC_TEXT:
            values = {langs[0]: arc.get(field)}
            for lang in langs[1:]:
                match = next(
                    (a for a in locales[lang].get("arcs") or [] if a.get("arc_id") == aid), {}
                )
                values[lang] = match.get(field)
            texts = _text_map(values)
            if texts:
                arc[field] = texts
        for point in arc.get("points") or []:
            cid = point.get("claim_id")
            values = {langs[0]: point.get("statement")}
            for lang in langs[1:]:
                match_arc = next(
                    (a for a in locales[lang].get("arcs") or [] if a.get("arc_id") == aid), {}
                )
                match_point = next(
                    (p for p in match_arc.get("points") or [] if p.get("claim_id") == cid),
                    {},
                )
                values[lang] = match_point.get("statement")
            texts = _text_map(values)
            if texts:
                point["statement"] = texts
        beats = arc.get("beats") or []
        for index, beat in enumerate(beats):
            values = {langs[0]: beat.get("gist")}
            for lang in langs[1:]:
                match_arc = next(
                    (a for a in locales[lang].get("arcs") or [] if a.get("arc_id") == aid), {}
                )
                match_beats = match_arc.get("beats") or []
                values[lang] = (
                    match_beats[index].get("gist") if index < len(match_beats) else None
                )
            texts = _text_map(values)
            if texts:
                beat["gist"] = texts

    return merged


# ── 脚手架 ───────────────────────────────────────────────────────────────────


def _blank_claims(card: dict) -> None:
    for claim in card.get("claims") or []:
        for field in CLAIM_TEXT:
            if field in claim:
                claim[field] = ""
        for relation in claim.get("relations") or []:
            if "note" in relation:
                relation["note"] = ""


def scaffold(base: dict, lang: str) -> dict:
    """A structurally identical card with every translatable string blanked."""
    card = copy.deepcopy(base)
    card["language"] = lang
    card["translation_of"] = base.get("content_id")
    if isinstance(card.get("source"), dict):
        for field in SOURCE_TEXT:
            if field in card["source"]:
                card["source"][field] = base["source"].get(field, "")
    for group in card.get("groups") or []:
        if "name" in group:
            group["name"] = ""
    for person in card.get("people") or []:
        for field in PEOPLE_TEXT:
            if field in person:
                person[field] = ""
    _blank_claims(card)
    for arc in card.get("arcs") or []:
        for field in ARC_TEXT:
            if field in arc:
                arc[field] = ""
        for point in arc.get("points") or []:
            if "statement" in point:
                point["statement"] = ""
        for beat in arc.get("beats") or []:
            if "gist" in beat:
                beat["gist"] = ""
    return card


def locale_path(base_path: str | Path, lang: str) -> Path:
    path = Path(base_path)
    return path.with_name(f"{path.stem}.{lang}{path.suffix}")


def load(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        card = json.load(handle)
    if not isinstance(card, dict):
        raise SystemExit(f"{path} 不是知识卡 JSON 对象")
    return card


def write(card: dict, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return target


def parse_locale_args(values: Iterable[str] | None) -> dict[str, str]:
    """`--i18n en=path.json` → {"en": "path.json"}"""
    out: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            raise SystemExit(f"--i18n 需要 LANG=FILE 形式，收到 {raw!r}")
        lang, path = raw.split("=", 1)
        lang = lang.strip()
        path = path.strip()
        if not lang or not os.path.isfile(path):
            raise SystemExit(f"--i18n {raw!r} 指向的文件不存在")
        out[lang] = path
    return out
