"""Transcribe token-pipeline tests that need no model download."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills" / "podcast-knowledge-graph" / "lib"))

from podcast_kg.transcribe import _collect  # noqa: E402


class FakeSegment:
    def __init__(self, text: str = "hello", start: float = 0.0, end: float = 1.0) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.words = []


class FakeModel:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return [FakeSegment()], object()


class CollectTest(unittest.TestCase):
    def run_collect(self, **kwargs):
        model = FakeModel()
        segments, vocab = _collect(model, "audio.wav", "zh", 1, 0.0, **kwargs)
        return model.kwargs, segments, vocab

    def test_context_carrying_is_off_by_default(self) -> None:
        kwargs, segments, _ = self.run_collect()
        self.assertFalse(kwargs["condition_on_previous_text"])
        self.assertTrue(kwargs["vad_filter"])
        self.assertEqual(len(segments), 1)
        self.assertEqual(segments[0]["text"], "hello")

    def test_carry_context_can_be_opted_in(self) -> None:
        kwargs, _, _ = self.run_collect(carry_context=True)
        self.assertTrue(kwargs["condition_on_previous_text"])

    def test_words_switch_enables_word_timestamps(self) -> None:
        kwargs, _, _ = self.run_collect(words=True)
        self.assertTrue(kwargs["word_timestamps"])


if __name__ == "__main__":
    unittest.main()
