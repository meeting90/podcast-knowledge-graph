"""Audio transcription via faster-whisper (local, offline).

Outputs `.outputs/<audio>_transcript.json` (segment list with timestamps) and a
human-readable `.outputs/<audio>_transcript.txt`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

from .deps import ensure
from .outputs import ensure_parent, out_path, stem


def to_wav16k(src: str) -> str:
    """Convert to 16 kHz mono WAV for whisper.

    faster-whisper can decode most containers through PyAV, so when ffmpeg is
    unavailable the original file is used directly instead of failing.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(
            "[podcast-kg] 未找到 ffmpeg，直接用 PyAV 解码原音频（质量可能略差）",
            file=sys.stderr,
            flush=True,
        )
        return src
    dst = out_path(stem(src) + ".16k.wav")
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000", dst],
        check=True,
    )
    return dst


def transcribe(audio: str, model_size: str = "small", language: str = "zh") -> list[dict]:
    ensure("faster_whisper", "faster-whisper>=1.0.0")
    from faster_whisper import WhisperModel

    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"模型加载 {time.time() - t0:.0f}s", flush=True)
    segments, _info = model.transcribe(audio, language=language, vad_filter=True, beam_size=1)
    out = [
        {"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()}
        for s in segments
    ]
    if not out:
        raise SystemExit("没有识别到语音，请检查音频文件。")
    print(f"转写完成: {len(out)} 段 / {out[-1]['end']}s / 耗时 {time.time() - t0:.0f}s")
    return out


def transcribe_file(
    src: str,
    out: str | None = None,
    model_size: str = "small",
    language: str = "zh",
) -> tuple[str, str]:
    wav = src if src.lower().endswith(".wav") else to_wav16k(src)
    segs = transcribe(wav, model_size=model_size, language=language)
    target = ensure_parent(out) if out else out_path(stem(src) + "_transcript.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(segs, fh, ensure_ascii=False, indent=1)
    txt = os.path.splitext(target)[0] + ".txt"
    with open(txt, "w", encoding="utf-8") as fh:
        for s in segs:
            m, sec = divmod(int(s["start"]), 60)
            fh.write(f"[{m:02d}:{sec:02d}] {s['text']}\n")
    print("产物:", target, "和", txt)
    return target, txt
