"""Bilingual cards: parity checks, translation scaffold, switchable HTML."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "podcast-knowledge-graph" / "lib"))

from podcast_kg import i18n  # noqa: E402
from podcast_kg.render_card import render  # noqa: E402

CARD = {
    "content_id": "ep_bi",
    "source": {
        "title": "双语测试",
        "platform": "test",
        "audio_url": "https://example.invalid/a.mp3",
        "published_at": "2026-01-01",
        "language": "zh",
    },
    "people": [
        {"person_id": "host", "name": "主持人", "role": "host"},
        {"person_id": "guest", "name": "嘉宾", "role": "guest", "identity": "研究员"},
    ],
    "entities": [{"entity_id": "api", "name": "API", "type": "concept"}],
    "groups": [{"gid": "g1", "name": "① 产品", "ids": ["c01", "c02"]}],
    "claims": [
        {
            "claim_id": "c01",
            "statement": "订阅制是补贴",
            "speaker": "guest",
            "timestamp": "01:02",
            "end": "01:30",
            "type": "assertion",
            "evidence": "原话一",
            "relations": [{"type": "supports", "target": "c02", "note": "用成本佐证"}],
        },
        {
            "claim_id": "c02",
            "statement": "API 利润率很高",
            "speaker": "host",
            "timestamp": "01:30",
            "end": "02:00",
            "type": "definition",
            "relations": [],
        },
    ],
    "arcs": [
        {
            "arc_id": "a01",
            "title": "订阅与成本",
            "summary": "这一段讲订阅制的成本结构。",
            "start": "01:02",
            "end": "02:00",
            "duration_sec": 58,
            "open_question": "订阅为什么便宜？",
            "open_line": "我们先说订阅。",
            "points": [{"claim_id": "c01", "at": "01:02", "statement": "订阅是补贴"}],
            "beats": [{"at": "01:02", "gist": "主持人开场"}],
            "evidence": ["c01", "c02"],
        }
    ],
}


def english_card() -> dict:
    card = json.loads(json.dumps(CARD))
    card["source"]["title"] = "Bilingual test"
    card["groups"][0]["name"] = "① Product"
    card["people"][0]["role"] = "host"
    card["people"][1]["identity"] = "Researcher"
    card["claims"][0]["statement"] = "Subscriptions are subsidies"
    card["claims"][0]["evidence"] = "Quote one"
    card["claims"][0]["relations"][0]["note"] = "Backed by costs"
    card["claims"][1]["statement"] = "API margins are high"
    card["arcs"][0].update(
        {
            "title": "Subscriptions and cost",
            "summary": "How subscription pricing works.",
            "open_question": "Why is it cheap?",
            "open_line": "Let's start with subscriptions.",
            "points": [{"claim_id": "c01", "at": "01:02", "statement": "Subscriptions are subsidies"}],
            "beats": [{"at": "01:02", "gist": "Host opens"}],
        }
    )
    return card


class CheckTest(unittest.TestCase):
    def test_identical_structure_passes(self) -> None:
        result = i18n.check(CARD, english_card(), "en")
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["warnings"], [])

    def test_missing_and_extra_claims_are_errors(self) -> None:
        locale = english_card()
        locale["claims"].pop()
        result = i18n.check(CARD, locale, "en")
        self.assertFalse(result["ok"])
        self.assertTrue(any("缺少" in error for error in result["errors"]))

    def test_timestamp_drift_is_an_error(self) -> None:
        locale = english_card()
        locale["claims"][0]["timestamp"] = "01:03"
        result = i18n.check(CARD, locale, "en")
        self.assertFalse(result["ok"])
        self.assertTrue(any("timestamp" in error for error in result["errors"]))

    def test_arc_range_and_group_order_are_checked(self) -> None:
        locale = english_card()
        locale["arcs"][0]["start"] = "01:05"
        locale["groups"][0]["ids"] = ["c02", "c01"]
        result = i18n.check(CARD, locale, "en")
        self.assertFalse(result["ok"])
        self.assertTrue(any("a01.start" in error for error in result["errors"]))
        self.assertTrue(any("g1" in error for error in result["errors"]))

    def test_empty_translation_is_a_warning(self) -> None:
        locale = english_card()
        locale["claims"][0]["statement"] = ""
        result = i18n.check(CARD, locale, "en")
        self.assertTrue(result["ok"])
        self.assertTrue(any("c01.statement" in warning for warning in result["warnings"]))


class MergeTest(unittest.TestCase):
    def test_fields_become_language_maps(self) -> None:
        merged = i18n.merge(CARD, {"en": english_card()}, "zh")
        claim = merged["claims"][0]
        self.assertEqual(claim["statement"]["zh"], "订阅制是补贴")
        self.assertEqual(claim["statement"]["en"], "Subscriptions are subsidies")
        self.assertEqual(claim["relations"][0]["note"]["en"], "Backed by costs")
        self.assertEqual(merged["arcs"][0]["summary"]["en"], "How subscription pricing works.")
        self.assertEqual(merged["arcs"][0]["beats"][0]["gist"]["en"], "Host opens")
        self.assertEqual(merged["groups"][0]["name"]["en"], "① Product")
        self.assertEqual(merged["source"]["title"]["en"], "Bilingual test")
        # untouched structure
        self.assertEqual(merged["claims"][0]["timestamp"], "01:02")
        self.assertEqual(merged["arcs"][0]["evidence"], ["c01", "c02"])

    def test_empty_translation_falls_back(self) -> None:
        locale = english_card()
        locale["claims"][1]["statement"] = ""
        merged = i18n.merge(CARD, {"en": locale}, "zh")
        self.assertEqual(merged["claims"][1]["statement"], {"zh": "API 利润率很高"})


class ScaffoldTest(unittest.TestCase):
    def test_scaffold_keeps_structure_and_blanks_text(self) -> None:
        skeleton = i18n.scaffold(CARD, "en")
        self.assertEqual(skeleton["language"], "en")
        self.assertEqual(skeleton["content_id"], CARD["content_id"])
        self.assertEqual(
            [c["claim_id"] for c in skeleton["claims"]],
            [c["claim_id"] for c in CARD["claims"]],
        )
        self.assertEqual(skeleton["claims"][0]["timestamp"], "01:02")
        self.assertEqual(skeleton["claims"][0]["statement"], "")
        self.assertEqual(skeleton["arcs"][0]["title"], "")
        self.assertEqual(skeleton["arcs"][0]["start"], "01:02")
        self.assertEqual(skeleton["groups"][0]["ids"], ["c01", "c02"])
        # the base card must not be mutated
        self.assertEqual(CARD["claims"][0]["statement"], "订阅制是补贴")

    def test_locale_path_naming(self) -> None:
        path = i18n.locale_path("/tmp/ep.json", "en")
        self.assertEqual(path.name, "ep.en.json")


class RenderTest(unittest.TestCase):
    def test_bilingual_html_has_one_dom_and_a_switch(self) -> None:
        merged = i18n.merge(CARD, {"en": english_card()}, "zh")
        html = render(merged, langs=["zh", "en"], default_lang="zh", arcs=merged["arcs"])
        self.assertEqual(html.count("<audio"), 1)
        self.assertEqual(html.count('class="langsw"'), 1)
        self.assertIn('data-lang="en"', html)
        self.assertIn('data-en="Subscriptions are subsidies"', html)
        self.assertIn('data-zh="订阅制是补贴"', html)
        self.assertEqual(html.count('id="claim-c01"'), 1)
        self.assertEqual(html.count('id="arc-a01"'), 1)
        self.assertIn("applyLang", html)
        # bilingual attributes must pair up
        for attrs in re.findall(r'<span class="i18n" ([^>]*)>', html):
            self.assertIn("data-zh=", attrs)
            self.assertIn("data-en=", attrs)

    def test_single_language_html_stays_as_before(self) -> None:
        html = render(CARD, arcs=CARD["arcs"])
        self.assertNotIn('class="langsw"', html)
        self.assertNotIn("data-en=", html)
        self.assertIn('lang="zh-CN"', html)

    def test_english_only_render_uses_en_as_default(self) -> None:
        merged = i18n.merge(english_card(), {}, "en")
        html = render(merged, langs=["en"], default_lang="en", arcs=merged["arcs"])
        self.assertIn('lang="en"', html)
        self.assertIn("Subscriptions are subsidies", html)

    def test_english_default_keeps_chinese_switchable(self) -> None:
        merged = i18n.merge(CARD, {"en": english_card()}, "zh")
        html = render(merged, langs=["en", "zh"], default_lang="en", arcs=merged["arcs"])
        self.assertIn('lang="en"', html)
        self.assertIn('class="langsw"', html)
        self.assertIn('data-zh="订阅制是补贴"', html)
        self.assertIn("Subscriptions are subsidies", html)

    def test_translation_text_is_escaped(self) -> None:
        locale = english_card()
        locale["claims"][0]["statement"] = '<script>alert("x")</script>'
        merged = i18n.merge(CARD, {"en": locale}, "zh")
        html = render(merged, langs=["zh", "en"], default_lang="zh", arcs=merged["arcs"])
        # the payload lives inside <script> but is JSON-escaped (</ → <\/),
        # and the visible text is HTML-escaped
        self.assertIn("<\/script>", html)
        self.assertEqual(html.count("</script>"), 2)
        self.assertIn("&lt;script&gt;", html)

    def test_comment_payload_cannot_break_out(self) -> None:
        locale = english_card()
        locale["claims"][0]["statement"] = "a <!-- b </script>"
        merged = i18n.merge(CARD, {"en": locale}, "zh")
        html = render(merged, langs=["zh", "en"], default_lang="zh", arcs=merged["arcs"])
        self.assertNotIn("<!-- b", html)
        self.assertEqual(html.count("</script>"), 2)


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.base = self.root / "ep.json"
        self.base.write_text(json.dumps(CARD, ensure_ascii=False), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "podcast_kg", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={
                "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "skills" / "podcast-knowledge-graph" / "lib"),
                "PATH": "",
            },
        )

    def test_scaffold_then_check(self) -> None:
        made = self.run_cli("i18n", "scaffold", str(self.base), "--lang", "en")
        self.assertEqual(made.returncode, 0, made.stderr)
        locale = self.root / "ep.en.json"
        self.assertTrue(locale.is_file())

        checked = self.run_cli("i18n", "check", str(self.base), str(locale))
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("未翻译", checked.stdout)

        locale.write_text(json.dumps(english_card(), ensure_ascii=False), encoding="utf-8")
        clean = self.run_cli("i18n", "check", str(self.base), str(locale))
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertNotIn("未翻译", clean.stdout)

    def test_check_fails_on_structural_drift(self) -> None:
        locale = english_card()
        locale["claims"].pop()
        path = self.root / "ep.en.json"
        path.write_text(json.dumps(locale, ensure_ascii=False), encoding="utf-8")
        result = self.run_cli("i18n", "check", str(self.base), str(path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("缺少", result.stdout)

    def test_render_switches_languages(self) -> None:
        (self.root / "ep.en.json").write_text(
            json.dumps(english_card(), ensure_ascii=False), encoding="utf-8"
        )
        out = self.root / "ep.html"
        result = self.run_cli(
            "render",
            str(self.base),
            str(out),
            "--i18n",
            f"en={self.root / 'ep.en.json'}",
            "--default-lang",
            "zh",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        html = out.read_text(encoding="utf-8")
        self.assertIn('class="langsw"', html)
        self.assertIn("Subscriptions are subsidies", html)

    def test_render_rejects_broken_locale(self) -> None:
        broken = english_card()
        broken["claims"][0]["timestamp"] = "09:99"
        (self.root / "ep.en.json").write_text(
            json.dumps(broken, ensure_ascii=False), encoding="utf-8"
        )
        result = self.run_cli(
            "render",
            str(self.base),
            str(self.root / "ep.html"),
            "--i18n",
            f"en={self.root / 'ep.en.json'}",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("结构不一致", result.stderr)


if __name__ == "__main__":
    unittest.main()
