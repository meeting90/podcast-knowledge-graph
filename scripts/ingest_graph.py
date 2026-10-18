#!/usr/bin/env python3
"""HERON · ingest_graph.py — 知识卡 JSON → Semantica 图谱适配器

用法: python ingest_graph.py <knowledge_card.json> [--out graph.json]
已验证: semantica 0.7.0, 43节点/119边, 中文无损 (pilot 2026-10-17)
"""
import json, sys

def card_to_graph(card: dict) -> dict:
    entities, relationships = [], []
    cid = card["content_id"]
    audio = card["source"]["audio_url"]

    entities.append({"id": cid, "name": card["source"]["title"][:40],
                     "type": "Content", "audio_url": audio,
                     "published_at": card["source"]["published_at"]})

    for p in card.get("people", []):
        entities.append({"id": p["person_id"], "name": p["name"], "type": "Person",
                         "role": p["role"], "identity": p["identity"]})
        relationships.append({"source": p["person_id"], "target": cid,
                              "type": "HOSTED" if p["role"] == "host" else "GUESTED"})

    for e in card.get("entities", []):
        entities.append({"id": e["entity_id"], "name": e["name"], "type": e["type"].upper()})
        relationships.append({"source": e["entity_id"], "target": cid, "type": "MENTIONED_IN"})

    for c in card.get("claims", []):
        entities.append({"id": c["claim_id"], "name": c["statement"][:60], "type": "Claim",
                         "timestamp": c["timestamp"], "end": c["end"], "claim_type": c["type"]})
        relationships.append({"source": c["claim_id"], "target": cid, "type": "SAID_IN",
                              "audio_url": audio, "start": c["timestamp"], "end": c["end"]})
        relationships.append({"source": c["speaker"], "target": c["claim_id"], "type": "SAID"})
        for r in c.get("relations", []):
            relationships.append({"source": c["claim_id"], "target": r["target"],
                                  "type": r["type"].upper(), "note": r["note"]})
    return {"entities": entities, "relationships": relationships}


def register_provenance(card: dict):
    """每个 claim 的出处登记为 PROV-O 溯源（音频URL + 秒级区间在 metadata）"""
    from semantica.provenance import ProvenanceManager
    pm = ProvenanceManager()
    audio = card["source"]["audio_url"]
    def sec(ts):
        p = ts.split(":"); return int(p[0]) * 60 + int(p[1])
    for c in card.get("claims", []):
        pm.track_entity(entity_id=c["claim_id"], source=audio,
                        metadata={"clip": f'{c["timestamp"]}-{c["end"]}',
                                  "start_sec": sec(c["timestamp"]), "end_sec": sec(c["end"]),
                                  "episode": card["content_id"], "speaker": c["speaker"]})
    return pm


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    card = json.load(open(sys.argv[1]))
    data = card_to_graph(card)
    from semantica.kg import GraphBuilder
    res = GraphBuilder(merge_entities=True).build(data)
    print(f"图构建: {len(res['entities'])} 节点, {len(res['relationships'])} 边, "
          f"拒绝关系 {res['metadata'].get('rejected_relationships')}")
    pm = register_provenance(card)
    print(f"溯源登记: {len(pm.get_all_sources())} 个来源")
    out = sys.argv[3] if len(sys.argv) > 3 else sys.argv[1].replace(".json", "_graph.json")
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print("图快照:", out)


if __name__ == "__main__":
    main()
