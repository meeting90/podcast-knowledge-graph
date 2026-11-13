#!/usr/bin/env python3
"""知识卡 JSON → 可溯源图谱快照（纯标准库，不联网）。

历史：早期版本用 semantica 的 GraphBuilder(merge_entities=True) + ProvenanceManager。
两个问题：

1. 它的实体消解按名字相似度合并，实测会把「北京大学」并进「北京师范大学」、
   「Marvin Minsky」并进「Zuckerberg」、把两条不同 claim（c33/c43）并成一个 id ——
   每条脏数据都会污染整张图，而且看起来完全合法，没法事后发现。
2. ProvenanceManager 只写进程内对象，`register_provenance()` 的返回值被丢弃，
   所谓 PROV-O 溯源从来没落盘。

所以这里自己做完，只做**确定性**的事：
   • 只按 id 去重，绝不猜测「这两个名字像不像同一个东西」
   • 校验每条边：端点必须存在、不许自指、同一 (source,target,type) 只留一条
   • 溯源写进文件（claim ← 音频 + 秒级区间），而不是打在 stdout 上
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import __version__
from .outputs import ensure_parent, out_path, stem

_TS = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)$")


def claim_seconds(timestamp: str | None) -> float | None:
    """`mm:ss` / `h:mm:ss` / `h:mm:ss.ff` → 秒（float；小数秒要保留）"""
    if not timestamp:
        return None
    match = _TS.match(str(timestamp).strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)


def card_to_graph(card: dict) -> dict:
    """Deterministic entity/relationship extraction (no external merging)."""
    entities: list[dict] = []
    relationships: list[dict] = []
    content_id = card["content_id"]
    audio = (card.get("source") or {}).get("audio_url")

    entities.append(
        {
            "id": content_id,
            "name": (card["source"].get("title") or content_id)[:40],
            "type": "Content",
            "audio_url": audio,
            "published_at": card["source"].get("published_at"),
        }
    )

    for person in card.get("people", []):
        entities.append(
            {
                "id": person["person_id"],
                "name": person["name"],
                "type": "Person",
                "role": person.get("role"),
                "identity": person.get("identity"),
            }
        )
        relationships.append(
            {
                "source": person["person_id"],
                "target": content_id,
                "type": "HOSTED" if person.get("role") == "host" else "GUESTED",
            }
        )

    for item in card.get("entities", []):
        entities.append(
            {
                "id": item["entity_id"],
                "name": item["name"],
                "type": str(item.get("type") or "").upper(),
            }
        )
        relationships.append(
            {"source": item["entity_id"], "target": content_id, "type": "MENTIONED_IN"}
        )

    for claim in card.get("claims", []):
        start = claim.get("timestamp")
        end = claim.get("end") or start
        entities.append(
            {
                "id": claim["claim_id"],
                "name": (claim.get("statement") or "")[:60],
                "type": "Claim",
                "timestamp": start,
                "end": end,
                "claim_type": claim.get("type"),
            }
        )
        relationships.append(
            {
                "source": claim["claim_id"],
                "target": content_id,
                "type": "SAID_IN",
                "audio_url": audio,
                "start": start,
                "end": end,
            }
        )
        relationships.append(
            {"source": claim.get("speaker"), "target": claim["claim_id"], "type": "SAID"}
        )
        for relation in claim.get("relations", []) or []:
            relationships.append(
                {
                    "source": claim["claim_id"],
                    "target": relation["target"],
                    "type": str(relation["type"]).upper(),
                    "note": relation.get("note"),
                }
            )
    return {"entities": entities, "relationships": relationships}


def provenance_records(card: dict) -> list[dict]:
    """One record per claim: what was said, where to hear it, from whom.

    This is the part the old semantica path claimed to do but never wrote out.
    """
    content_id = card["content_id"]
    audio = (card.get("source") or {}).get("audio_url")
    records: list[dict] = []
    for claim in card.get("claims", []):
        start = claim.get("timestamp")
        end = claim.get("end") or start
        records.append(
            {
                "entity_id": claim["claim_id"],
                "activity": "SAID_IN",
                "episode": content_id,
                "speaker": claim.get("speaker"),
                "source": audio,
                "clip": f"{start}-{end}",
                "start_sec": claim_seconds(start),
                "end_sec": claim_seconds(end),
            }
        )
    return records


def _merge_entity(target: dict, incoming: dict) -> None:
    for key, value in incoming.items():
        current = target.get(key)
        if current in (None, "", [], {}):
            target[key] = value
        elif isinstance(current, list) and isinstance(value, list):
            for item in value:
                if item not in current:
                    current.append(item)


def build_graph(card: dict) -> dict:
    """Dedupe by id, validate edges, attach provenance and counts."""
    raw = card_to_graph(card)

    entities: list[dict] = []
    by_id: dict[str, dict] = {}
    duplicates = 0
    for entity in raw["entities"]:
        entity_id = entity.get("id")
        if not entity_id:
            continue
        if entity_id in by_id:
            _merge_entity(by_id[entity_id], entity)
            duplicates += 1
            continue
        by_id[entity_id] = entity
        entities.append(entity)

    relationships: list[dict] = []
    seen_edges: set[tuple] = set()
    rejected: list[dict] = []
    deduped = 0

    def reject(edge: dict, reason: str) -> None:
        rejected.append(
            {"source": edge.get("source"), "target": edge.get("target"), "type": edge.get("type"), "reason": reason}
        )

    for edge in raw["relationships"]:
        source, target, kind = edge.get("source"), edge.get("target"), edge.get("type")
        if not source or not target or not kind:
            reject(edge, "missing endpoint or type")
            continue
        if source == target:
            reject(edge, "self-loop")
            continue
        if source not in by_id:
            reject(edge, f"unknown source {source}")
            continue
        if target not in by_id:
            reject(edge, f"unknown target {target}")
            continue
        key = (source, target, kind)
        if key in seen_edges:
            deduped += 1
            continue
        seen_edges.add(key)
        relationships.append(edge)

    provenance = provenance_records(card)
    missing_provenance = sum(1 for record in provenance if record["start_sec"] is None)

    return {
        "entities": entities,
        "relationships": relationships,
        "provenance": provenance,
        "metadata": {
            "generator": f"podcast-kg {__version__}",
            "num_entities": len(entities),
            "num_relationships": len(relationships),
            # kept for readers of older snapshots
            "rejected_relationships": len(rejected),
            "duplicate_entities": duplicates,
            "duplicate_relationships": deduped,
            "num_provenance": len(provenance),
            "claims_without_timestamp": missing_provenance,
            "entity_resolution_applied": False,
            "rejected": rejected,
        },
    }


def _require(card: Any, fields: tuple[str, ...]) -> None:
    if not isinstance(card, dict):
        raise SystemExit("知识卡必须是 JSON 对象")
    missing = [field for field in fields if not card.get(field)]
    if missing:
        raise SystemExit(
            "知识卡缺少必需字段："
            + ", ".join(missing)
            + "（需要 content_id / source / claims；转写稿或旧图谱快照不要传进来）"
        )


def ingest(card_path: str, out: str | None = None) -> str:
    """Build a source-linked graph snapshot (stdlib only, offline)."""
    with open(card_path, encoding="utf-8") as handle:
        card = json.load(handle)
    _require(card, ("content_id", "source", "claims"))
    if not isinstance(card["claims"], list):
        raise SystemExit("claims 必须是数组")

    graph = build_graph(card)
    meta = graph["metadata"]
    print(
        f"图构建: {meta['num_entities']} 节点, {meta['num_relationships']} 边, "
        f"去重 {meta['duplicate_entities']} 实体 / {meta['duplicate_relationships']} 边, "
        f"拒绝 {meta['rejected_relationships']} 条"
    )
    print(f"溯源: {meta['num_provenance']} 条 claim（音频 + 秒级区间已写入文件）")

    target = ensure_parent(out) if out else out_path(stem(card_path) + "_graph.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(graph, handle, ensure_ascii=False, indent=1)
    print("图快照:", target)
    return target
