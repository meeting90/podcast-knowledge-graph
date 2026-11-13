#!/usr/bin/env python3
"""Same-audio ASR benchmark: faster-whisper vs Parakeet TDT 0.6B v3 (ONNX).

Two engines live in different dependency trees, so the script loads only the
one you ask for:

    faster-whisper      pip install "podcast-kg[transcribe]"
    onnx-asr + weights  pip install "onnx-asr[cpu,hub]"
                        (model downloads on first run, ~670 MB int8)
    sherpa-onnx         pip install sherpa-onnx   (SenseVoice / Zipformer, ONNX)
                        model dirs from
                        https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models

Examples
--------
    python scripts/bench_asr.py --engine whisper --model small --device cpu \
        --compute-type int8 --runs 2 ep.mp3.wav

    python scripts/bench_asr.py --engine parakeet --model nemo-parakeet-tdt-0.6b-v3 \
        ep.mp3.wav --ref-file reference.txt

Each run prints one JSON line; `--ref` / `--ref-file` adds WER (space-delimited
languages) or CER (CJK, decided by whether the reference has spaces).
"""

from __future__ import annotations

import argparse
import array
import json
import re
import sys
import time
import unicodedata
import wave
from pathlib import Path

ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


# ── scoring ─────────────────────────────────────────────────────────────────


def _number_word(token: str) -> str:
    if not token.isdigit() or len(token) > 2:
        return token
    value = int(token)
    if value < 20:
        return ONES[value]
    if value % 10 == 0:
        return TENS[value // 10]
    return f"{TENS[value // 10]} {ONES[value % 10]}"


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[^\w\s]|_", " ", text)
    out: list[str] = []
    for token in text.split():
        out.extend(_number_word(token).split())
    return out


ZH_DIGITS = str.maketrans(
    {"零": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
)


def chars(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower().translate(ZH_DIGITS)
    return list(re.sub(r"[\W_]+", "", text))


def distance(a: list[str], b: list[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(reference: str, hypothesis: str) -> dict:
    if " " in reference.strip():
        ref, hyp = words(reference), words(hypothesis)
        return {"unit": "WER", "value": round(distance(ref, hyp) / max(1, len(ref)), 4)}
    ref, hyp = chars(reference), chars(hypothesis)
    return {"unit": "CER", "value": round(distance(ref, hyp) / max(1, len(ref)), 4)}


def duration(path: str) -> float:
    with wave.open(path) as handle:
        return handle.getnframes() / handle.getframerate()


# ── engines ─────────────────────────────────────────────────────────────────


def load_whisper(args):
    from faster_whisper import WhisperModel

    if args.device == "cuda":
        try:
            from podcast_kg.transcribe import enable_cuda_dlls

            enable_cuda_dlls()
        except Exception:  # noqa: BLE001 - benchmark keeps going without it
            pass
    return WhisperModel(args.model, device=args.device, compute_type=args.compute_type)


def run_whisper(args, wav: str, model) -> dict:
    started = time.time()
    segments, info = model.transcribe(
        wav,
        language=args.lang,
        beam_size=args.beam,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=args.carry_context,
    )
    parts, n_words = [], 0
    for segment in segments:
        parts.append(segment.text.strip())
        n_words += len(segment.words or [])
    elapsed = time.time() - started
    return {
        "audio_s": round(duration(wav), 2),
        "infer_s": round(elapsed, 2),
        "rtf": round(duration(wav) / elapsed, 1) if elapsed else None,
        "lang": getattr(info, "language", None),
        "words": n_words,
        "text": " ".join(parts),
    }


def load_parakeet(args):
    import onnx_asr

    model = onnx_asr.load_model(args.model, quantization=args.quantization)
    return model.with_timestamps()


def run_parakeet(args, wav: str, model) -> dict:
    started = time.time()
    result = model.recognize(wav)
    elapsed = time.time() - started
    return {
        "audio_s": round(duration(wav), 2),
        "infer_s": round(elapsed, 2),
        "rtf": round(duration(wav) / elapsed, 1) if elapsed else None,
        "tokens": len(result.tokens),
        "text": result.text,
    }


SHERPA_ENGINES = ("sensevoice", "zipformer", "zipformer-ctc")


def load_sherpa(args):
    import sherpa_onnx

    root = Path(args.model_dir).expanduser()
    threads = args.threads
    if args.engine == "sensevoice":
        return sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(root / "model.int8.onnx"),
            tokens=str(root / "tokens.txt"),
            num_threads=threads,
            use_itn=True,
            language=args.lang or "auto",
        )
    if args.engine == "zipformer":
        prefix = next(
            p.name[: -len(".int8.onnx")]
            for p in root.glob("encoder-*.int8.onnx")
        )
        return sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(root / f"{prefix}.int8.onnx"),
            decoder=str(root / f"{prefix.replace('encoder-', 'decoder-', 1)}.onnx"),
            joiner=str(root / f"{prefix.replace('encoder', 'joiner')}.int8.onnx"),
            tokens=str(root / "tokens.txt"),
            num_threads=threads,
            decoding_method="greedy_search",
        )
    return sherpa_onnx.OfflineRecognizer.from_zipformer_ctc(
        model=str(root / "model.int8.onnx"),
        tokens=str(root / "tokens.txt"),
        num_threads=threads,
    )


def read_samples(path: str) -> tuple[list[float], int]:
    with wave.open(path) as handle:
        rate = handle.getframerate()
        raw = array.array("h", handle.readframes(handle.getnframes()))
    return [value / 32768.0 for value in raw], rate


def run_sherpa(args, wav: str, model) -> dict:
    samples, rate = read_samples(wav)
    started = time.time()
    if args.chunk > 0:
        step = int(args.chunk * rate)
        parts = []
        for start in range(0, len(samples), step):
            stream = model.create_stream()
            stream.accept_waveform(rate, samples[start : start + step])
            model.decode_stream(stream)
            parts.append(stream.result.text)
        text = "".join(parts)
        tokens = 0
    else:
        stream = model.create_stream()
        stream.accept_waveform(rate, samples)
        model.decode_stream(stream)
        text = stream.result.text
        tokens = len(getattr(stream.result, "tokens", []) or [])
    elapsed = time.time() - started
    return {
        "audio_s": round(len(samples) / rate, 2),
        "infer_s": round(elapsed, 2),
        "rtf": round((len(samples) / rate) / elapsed, 1) if elapsed else None,
        "tokens": tokens,
        "text": text,
    }


# ── main ────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare faster-whisper and Parakeet TDT v3 on the same audio.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Examples")[0],
    )
    parser.add_argument("wavs", nargs="+", help="16 kHz mono WAV files")
    parser.add_argument(
        "--engine",
        choices=["whisper", "parakeet", *SHERPA_ENGINES],
        required=True,
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--quantization", default="int8", help="parakeet: onnx quantization")
    parser.add_argument("--beam", type=int, default=5)
    parser.add_argument("--lang", default=None)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--carry-context", action="store_true", help="whisper: condition_on_previous_text")
    parser.add_argument("--model-dir", help="sherpa engines: unpacked model directory")
    parser.add_argument("--threads", type=int, default=8, help="sherpa engines: CPU threads")
    parser.add_argument(
        "--chunk",
        type=float,
        default=0.0,
        help="sherpa engines: split audio into N-second windows (SenseVoice needs <=30s)",
    )
    parser.add_argument("--ref", help="reference transcript for WER/CER")
    parser.add_argument("--ref-file", help="file containing the reference transcript")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    if args.device == "auto":
        args.device = "cuda" if args.engine == "whisper" else "cpu"
    ref = args.ref
    if args.ref_file:
        ref = Path(args.ref_file).read_text(encoding="utf-8").strip()

    if args.engine == "whisper":
        args.model = args.model or "small"
        load, run = load_whisper, run_whisper
        hint = 'pip install "podcast-kg[transcribe]"'
    elif args.engine == "parakeet":
        args.model = args.model or "nemo-parakeet-tdt-0.6b-v3"
        load, run = load_parakeet, run_parakeet
        hint = 'pip install "onnx-asr[cpu,hub]"'
    else:
        if not args.model_dir:
            print(f"--engine {args.engine} 需要 --model-dir（解压后的 sherpa-onnx 模型目录）", file=sys.stderr)
            return 2
        load, run = load_sherpa, run_sherpa
        hint = "pip install sherpa-onnx"

    try:
        load_started = time.time()
        model = load(args)
    except ImportError as exc:
        print(f"缺少 {args.engine} 依赖（{exc}）：{hint}", file=sys.stderr)
        return 1
    print(json.dumps({"event": "loaded", "load_s": round(time.time() - load_started, 2)}), flush=True)

    best: list[dict] = []
    for wav in args.wavs:
        last = None
        for run_index in range(args.runs):
            try:
                row = run(args, wav, model)
            except Exception as exc:  # noqa: BLE001 - benchmark reports, never crashes
                print(json.dumps({"wav": wav, "error": repr(exc)}, ensure_ascii=False), flush=True)
                last = None
                break
            row.update({"wav": wav, "run": run_index})
            if ref:
                row.update(score(ref, row.get("text") or ""))
            print(json.dumps(row, ensure_ascii=False), flush=True)
            last = row
        if last:
            best.append(last)

    if ref and best:
        print("\n| clip | audio | infer | RTF | score |", file=sys.stderr)
        for row in best:
            print(
                f"| {Path(row['wav']).name} | {row['audio_s']}s | {row['infer_s']}s | "
                f"{row['rtf']}× | {row.get('unit', '')} {row.get('value', 0) * 100:.1f}% |",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
