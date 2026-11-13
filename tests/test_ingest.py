"""Graph snapshot tests: deterministic merging, edge validation, provenance.

Run with:  PYTHONPATH=src python -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from podcast_kg.ingest_graph import (  # noqa: E402
    build_graph,
    card_to_graph,
    claim_seconds,
    ingest,
)

CARD = {
    "content_id": "ep_2026",
    "source": {
        "title": "测试节目",
        "audio_url": "https://example.invalid/ep.mp3",
        "published_at": "2026-01-01",
    },
    "people": [
        {"person_id": "host", "name": "主持人", "role": "host"},
        {"person_id": "guest", "name": "嘉宾", "role": "guest"},
    ],
    "entities": [
        {"entity_id": "peking-university", "name": "北京大学", "type": "company"},
        {"entity_id": "beijing-normal-university", "name": "北京师范大学", "type": "company"},
    ],
    "claims": [
        {
            "claim_id": "c01",
            "statement": "甲观点",
            "speaker": "guest",
            "timestamp": "01:02",
            "end": "01:30",
            "type": "assertion",
            "relations": [
                {"type": "supports", "target": "c02", "note": "用乙佐证"},
                {"type": "responds_to", "target": "c01"},
            ],
        },
        {
            "claim_id": "c02",
            "statement": "乙观点",
            "speaker": "host",
            "timestamp": "1:04:18.72",
            "end": "1:04:40",
            "type": "definition",
            "relations": [{"type": "extends", "target": "c99"}],
        },
    ],
}


def card() -> dict:
    return copy.deepcopy(CARD)


class TimestampTest(unittest.TestCase):
    def test_mm_ss_and_h_mm_ss(self) -> None:
        self.assertEqual(claim_seconds("12:34"), 754)
        self.assertEqual(claim_seconds("01:02"), 62)
        self.assertEqual(claim_seconds("1:04:18.72"), 3858.72)

    def test_unparseable_is_none(self) -> None:
        for value in (None, "", "12", "abc", "12:3"):
            self.assertIsNone(claim_seconds(value), value)


class GraphTest(unittest.TestCase):
    def test_entities_are_not_fuzzy_merged(self) -> None:
        """Regression: semantica merged 北京大学 ← 北京师范大学 (and minsky ← zuckerberg)."""
        graph = build_graph(card())
        ids = {entity["id"] for entity in graph["entities"]}
        self.assertIn("peking-university", ids)
        self.assertIn("beijing-normal-university", ids)
        self.assertEqual(graph["metadata"]["duplicate_entities"], 0)
        self.assertFalse(graph["metadata"]["entity_resolution_applied"])

    def test_duplicate_ids_merge_fields_but_different_ids_do_not(self) -> None:
        data = card()
        data["people"].append(
            {"person_id": "guest", "name": "嘉宾", "role": "guest", "identity": "研究员"}
        )
        graph = build_graph(data)
        guest = [e for e in graph["entities"] if e["id"] == "guest"]
        self.assertEqual(len(guest), 1)
        self.assertEqual(guest[0]["identity"], "研究员")
        self.assertEqual(graph["metadata"]["duplicate_entities"], 1)

    def test_self_loops_and_dangling_targets_are_rejected(self) -> None:
        graph = build_graph(card())
        meta = graph["metadata"]
        reasons = sorted(item["reason"] for item in meta["rejected"])
        self.assertEqual(meta["rejected_relationships"], 2)
        self.assertTrue(any("self-loop" in reason for reason in reasons))
        self.assertTrue(any("c99" in reason for reason in reasons))
        for edge in graph["relationships"]:
            self.assertNotEqual(edge["source"], edge["target"])
        self.assertNotIn("c99", {edge["target"] for edge in graph["relationships"]})

    def test_duplicate_edges_are_collapsed(self) -> None:
        data = card()
        data["claims"][0]["relations"].append({"type": "supports", "target": "c02", "note": "重复"})
        graph = build_graph(data)
        keys = [(e["source"], e["target"], e["type"]) for e in graph["relationships"]]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(graph["metadata"]["duplicate_relationships"], 1)

    def test_relationship_endpoints_all_exist(self) -> None:
        graph = build_graph(card())
        ids = {entity["id"] for entity in graph["entities"]}
        for edge in graph["relationships"]:
            self.assertIn(edge["source"], ids)
            self.assertIn(edge["target"], ids)

    def test_claims_and_people_are_linked(self) -> None:
        graph = build_graph(card())
        edges = {(e["source"], e["target"], e["type"]) for e in graph["relationships"]}
        self.assertIn(("guest", "ep_2026", "GUESTED"), edges)
        self.assertIn(("host", "ep_2026", "HOSTED"), edges)
        self.assertIn(("c01", "ep_2026", "SAID_IN"), edges)
        self.assertIn(("guest", "c01", "SAID"), edges)
        self.assertIn(("c01", "c02", "SUPPORTS"), edges)

    def test_provenance_has_audio_and_seconds(self) -> None:
        graph = build_graph(card())
        records = {record["entity_id"]: record for record in graph["provenance"]}
        self.assertEqual(len(records), 2)
        first = records["c01"]
        self.assertEqual(first["source"], "https://example.invalid/ep.mp3")
        self.assertEqual(first["clip"], "01:02-01:30")
        self.assertEqual(first["start_sec"], 62)
        self.assertEqual(first["end_sec"], 90)
        self.assertEqual(first["speaker"], "guest")
        self.assertEqual(records["c02"]["start_sec"], 3858.72)
        self.assertEqual(graph["metadata"]["claims_without_timestamp"], 0)

    def test_metadata_keeps_legacy_keys(self) -> None:
        meta = build_graph(card())["metadata"]
        for key in ("num_entities", "num_relationships", "rejected_relationships"):
            self.assertIn(key, meta)
            self.assertIsInstance(meta[key], int)

    def test_missing_audio_url_still_builds(self) -> None:
        data = card()
        del data["source"]["audio_url"]
        graph = build_graph(data)
        self.assertIsNone(graph["provenance"][0]["source"])

    def test_card_to_graph_is_pure(self) -> None:
        data = card()
        graph = card_to_graph(data)
        self.assertNotIn("provenance", graph)
        self.assertEqual(data, CARD)


class IngestTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_card(self, data: dict | None = None) -> Path:
        path = self.root / "ep_2026.json"
        path.write_text(json.dumps(data if data is not None else card(), ensure_ascii=False), encoding="utf-8")
        return path

    def test_writes_snapshot_next_to_card(self) -> None:
        card_path = self.write_card()
        with contextlib.redirect_stdout(io.StringIO()):
            target = Path(ingest(str(card_path), str(self.root / "graph.json")))
        self.assertTrue(target.is_file())
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertIn("provenance", payload)
        self.assertEqual(payload["metadata"]["num_entities"], len(payload["entities"]))

    def test_missing_fields_exit_nonzero(self) -> None:
        broken = card()
        del broken["claims"]
        path = self.write_card(broken)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "podcast_kg",
                "ingest",
                str(path),
                "--out",
                str(self.root / "graph.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={"PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"), "PATH": ""},
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("claims", proc.stderr)

    def test_no_semantica_dependency(self) -> None:
        self.write_card()
        self.assertNotIn("semantica", sys.modules)
        with contextlib.redirect_stdout(io.StringIO()):
            ingest(str(self.root / "ep_2026.json"), str(self.root / "graph.json"))
        self.assertNotIn("semantica", sys.modules)


if __name__ == "__main__":
    unittest.main()
