"""Audio transcription via faster-whisper (local, offline).

Outputs `.outputs/<audio>_transcript.json` (segment list with timestamps) and a
human-readable `.outputs/<audio>_transcript.txt`.

Runtime selection (all overridable from the CLI):

  auto-detect CUDA  -> large-v3-turbo / float16 / beam 5
  no usable CUDA    -> small / int8 / beam 1

CUDA detection alone is not enough: ctranslate2 needs cuBLAS + cuDNN DLLs, so a
failed CUDA init falls back to CPU instead of killing the run.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

from .deps import ensure
from .models import is_cached, offline_hint, offline_requested, resolve_source
from .outputs import ensure_parent, out_path, stem

CUDA_MODEL = "large-v3-turbo"
CPU_MODEL = "small"
# faster-whisper decodes through PyAV, which dropped `metadata_errors` in av 19
# while faster_whisper.audio still passes it -> hard crash on every audio file.
# pyproject pins `av<19`; this is the friendly message if someone unpins it.
MIN_AV = 19


def cuda_device_count() -> int:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001 - probing must never be fatal
        return 0


def resolve_runtime(
    model: str | None,
    device: str | None,
    compute_type: str | None,
    beam: int | None,
) -> tuple[str, str, str, int]:
    """Fill in the blanks: explicit CLI flags win, `auto` picks by hardware."""
    if device in (None, "auto"):
        want_cuda = cuda_device_count() > 0
    else:
        want_cuda = device == "cuda"
    device = "cuda" if want_cuda else "cpu"
    model = model or (CUDA_MODEL if device == "cuda" else CPU_MODEL)
    compute_type = compute_type or ("float16" if device == "cuda" else "int8")
    if beam is None:
        beam = 5 if device == "cuda" else 1
    return model, device, compute_type, beam


def enable_cuda_dlls() -> list[str]:
    """Windows: make pip-installed cuBLAS/cuDNN wheels visible to ctranslate2.

    `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` drop their DLLs under
    site-packages/nvidia/<lib>/bin, which is not on PATH, so ctranslate2 dies
    with "Library cublas64_12.dll is not found or cannot be loaded".
    """
    if sys.platform != "win32":
        return []
    try:
        spec = importlib.util.find_spec("nvidia")
    except (ImportError, ValueError):
        return []
    if not spec or not spec.submodule_search_locations:
        return []
    dirs: list[str] = []
    for root in spec.submodule_search_locations:
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc", "cufft"):
            candidate = os.path.join(root, sub, "bin")
            if os.path.isdir(candidate):
                dirs.append(candidate)
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except (AttributeError, OSError):
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    return dirs


def check_pyav() -> None:
    """Fail early, with a fix, instead of an opaque `open() got an unexpected ...`."""
    try:
        import av
    except ImportError:
        return
    major = int(str(av.__version__).split(".")[0] or 0)
    if major >= MIN_AV:
        print(
            f"[podcast-kg] 警告：PyAV {av.__version__} 与 faster-whisper 不兼容"
            "（av 19 移除了 av.open(metadata_errors=…)）。修复：\n"
            f'  {sys.executable} -m pip install "av<19"',
            file=sys.stderr,
            flush=True,
        )


def to_wav16k(src: str) -> str:
    """Convert to 16 kHz mono WAV for whisper.

    faster-whisper can decode most containers through PyAV (same libav that
    ffmpeg wraps), so when ffmpeg is unavailable the original file is used
    directly instead of failing.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(
            "[podcast-kg] 未找到 ffmpeg，直接用 PyAV 解码原音频（质量无实质差别）",
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


def skip_hub_when_cached(model: str) -> str:
    """Keep huggingface_hub off the network when the weights are local.

    Left alone, every run pays a metadata round-trip to the Hub: on a machine
    that cannot reach it, that is a 130-second retry backoff *per invocation*
    before the cached snapshot is used. A 154-minute episode then takes 20
    minutes instead of 16, and four parallel chunks spend 8 minutes of wall
    clock doing nothing.
    """
    if os.environ.get("HF_HUB_OFFLINE") == "1":
        return "沿用外部 HF_HUB_OFFLINE=1"
    if is_cached(model):
        os.environ["HF_HUB_OFFLINE"] = "1"
        where = "本地模型目录" if os.path.isdir(model) else "本地缓存"
        return f"用{where}，跳过 Hub 联网检查（HF_HUB_OFFLINE=1）"
    # 真没缓存：下载前先问一句能不能连上，别让元数据请求挂两分钟。
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "5")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
    return ("本地无缓存，走 Hub 下载（需能连 huggingface.co；离线机器请设 HF_ENDPOINT 镜像，"
            "或用 --model 指向本地模型目录）")


def load_model(
    model_size: str,
    device: str,
    compute_type: str,
    model_dir: str | None = None,
):
    """Load the model, degrading to CPU/int8 when CUDA is present but unusable."""
    source, note = resolve_source(model_size, model_dir)
    print(f"模型来源 {note}", file=sys.stderr, flush=True)
    if offline_requested() and not is_cached(source):
        raise SystemExit(offline_hint(model_size))
    # Must run before `import faster_whisper`: that import freezes HF_HUB_OFFLINE.
    print(f"缓存检查 {skip_hub_when_cached(source)}", file=sys.stderr, flush=True)
    from faster_whisper import WhisperModel

    if device == "cuda":
        enable_cuda_dlls()
    try:
        return WhisperModel(source, device=device, compute_type=compute_type), device, compute_type
    except Exception as exc:  # noqa: BLE001 - RuntimeError from ctranslate2 when cuDNN is missing
        if device != "cuda":
            raise
        print(
            f"[podcast-kg] CUDA 初始化失败（{exc}），回退 CPU/int8；"
            "装好 cuBLAS + cuDNN 9 后可用 --device cuda",
            file=sys.stderr,
            flush=True,
        )
        return WhisperModel(source, device="cpu", compute_type="int8"), "cpu", "int8"


def _collect(
    model,
    audio: str,
    language: str,
    beam_size: int,
    started: float,
    words: bool = False,
    carry_context: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Consume the segment generator, reporting progress every 30s.

    `words=True` 时额外返回词级时间戳（DTW 对齐）：弧/卡的时间戳只有对齐到
    词的起止点，才不会出现“开头少一个词 / 多一个词”。
    """
    segments, _info = model.transcribe(
        audio,
        language=language,
        vad_filter=True,
        beam_size=beam_size,
        word_timestamps=words,
        # Default off: carrying context makes long audio with repeated passages
        # (intros, ads, re-caps) fall into a repetition loop. Measured on a
        # 71 s clip that repeats one paragraph: 10.2% WER and 11.0 s with the
        # context on, 0.0% WER and 2.8 s with it off. Short clips are byte-identical.
        condition_on_previous_text=carry_context,
    )
    out: list[dict] = []
    vocab: list[dict] = []
    last_report = started
    for seg in segments:
        text = seg.text.strip()
        if text:
            out.append({"start": round(seg.start, 1), "end": round(seg.end, 1), "text": text})
        for w in (seg.words or []):
            word = (w.word or "").strip()
            if word:
                vocab.append({"start": round(w.start, 2), "end": round(w.end, 2), "word": word})
        now = time.time()
        if now - last_report >= 30:
            last_report = now
            done = out[-1]["end"] if out else 0
            print(
                f"  进度 {done:.0f}s / 已出 {len(out)} 段 / 用时 {now - started:.0f}s",
                file=sys.stderr,
                flush=True,
            )
    return out, vocab


def transcribe(
    audio: str,
    model_size: str | None = None,
    language: str = "zh",
    device: str | None = None,
    compute_type: str | None = None,
    beam_size: int | None = None,
    words: bool = False,
    model_dir: str | None = None,
    carry_context: bool = False,
) -> tuple[list[dict], list[dict]]:
    ensure("faster_whisper", "faster-whisper>=1.0.0")
    check_pyav()

    model_size, device, compute_type, beam_size = resolve_runtime(
        model_size, device, compute_type, beam_size
    )
    print(
        f"运行配置 {device}/{compute_type} · {model_size} · beam {beam_size}",
        file=sys.stderr,
        flush=True,
    )

    t0 = time.time()
    model, device, compute_type = load_model(model_size, device, compute_type, model_dir)
    print(f"模型加载 {time.time() - t0:.0f}s", flush=True)

    try:
        out, vocab = _collect(model, audio, language, beam_size, t0, words, carry_context)
    except Exception as exc:  # noqa: BLE001 - ctranslate2 loads cuBLAS lazily, on first encode
        if device != "cuda":
            raise
        # CUDA 上下文能建、但第一次真实推理才报缺 DLL。别让整期内容报废：降级重跑。
        fallback_model = CPU_MODEL if model_size == CUDA_MODEL else model_size
        print(
            f"[podcast-kg] CUDA 推理失败（{exc}），回退 CPU/int8·{fallback_model} 重跑。\n"
            "  想要 GPU：pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 后重试 --device cuda",
            file=sys.stderr,
            flush=True,
        )
        t0 = time.time()
        model, device, compute_type = load_model(
            fallback_model, "cpu", "int8", model_dir
        )
        model_size = fallback_model
        print(f"模型加载 {time.time() - t0:.0f}s", flush=True)
        out, vocab = _collect(model, audio, language, beam_size, t0, words, carry_context)

    if not out:
        raise SystemExit("没有识别到语音，请检查音频文件。")
    print(
        f"转写完成: {len(out)} 段 / {out[-1]['end']}s / 耗时 {time.time() - t0:.0f}s "
        f"（{device}/{compute_type} · {model_size}）"
    )
    if vocab:
        print(f"词级时间戳: {len(vocab)} 个词", flush=True)
    return out, vocab


def transcribe_file(
    src: str,
    out: str | None = None,
    model_size: str | None = None,
    language: str = "zh",
    device: str | None = None,
    compute_type: str | None = None,
    beam_size: int | None = None,
    words: bool = False,
    model_dir: str | None = None,
    carry_context: bool = False,
) -> tuple[str, str]:
    wav = src if src.lower().endswith(".wav") else to_wav16k(src)
    segs, vocab = transcribe(
        wav,
        model_size=model_size,
        language=language,
        device=device,
        compute_type=compute_type,
        beam_size=beam_size,
        words=words,
        model_dir=model_dir,
        carry_context=carry_context,
    )
    target = ensure_parent(out) if out else out_path(stem(src) + "_transcript.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(segs, fh, ensure_ascii=False, indent=1)
    txt = os.path.splitext(target)[0] + ".txt"
    with open(txt, "w", encoding="utf-8") as fh:
        for s in segs:
            m, sec = divmod(int(s["start"]), 60)
            fh.write(f"[{m:02d}:{sec:02d}] {s['text']}\n")
    if vocab:
        wpath = os.path.splitext(target)[0].replace("_transcript", "") + "_words.json"
        with open(wpath, "w", encoding="utf-8") as fh:
            json.dump(vocab, fh, ensure_ascii=False, indent=0)
        print("词级时间戳:", wpath)
    print("产物:", target, "和", txt)
    return target, txt
