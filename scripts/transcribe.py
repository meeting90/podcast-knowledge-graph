#!/usr/bin/env python3
"""HERON · transcribe.py — 音频转写封装（faster-whisper，本地离线）

用法: python transcribe.py <audio.(mp3|wav)> [out_transcript.json]
前置: pip install faster-whisper；模型经 HF 镜像下载（已验证）
"""
import json, sys, time, subprocess, os

def to_wav16k(src: str) -> str:
    """ffmpeg 转 16k 单声道（whisper 最优输入）"""
    dst = os.path.splitext(src)[0] + ".wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-i", src, "-ac", "1", "-ar", "16000", dst], check=True)
    return dst

def transcribe(wav: str, model_size="small", language="zh"):
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"模型加载 {time.time()-t0:.0f}s", flush=True)
    segments, info = model.transcribe(wav, language=language, vad_filter=True, beam_size=1)
    out = [{"start": round(s.start, 1), "end": round(s.end, 1), "text": s.text.strip()}
           for s in segments]
    print(f"转写完成: {len(out)} 段 / {out[-1]['end']}s / 耗时 {time.time()-t0:.0f}s")
    return out

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    wav = src if src.endswith(".wav") else to_wav16k(src)
    segs = transcribe(wav)
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "_transcript.json"
    json.dump(segs, open(out, "w"), ensure_ascii=False)
    # 同时产出带时间戳的人读全文
    txt = out.replace(".json", ".txt")
    with open(txt, "w") as f:
        for s in segs:
            m, sec = divmod(int(s["start"]), 60)
            f.write(f"[{m:02d}:{sec:02d}] {s['text']}\n")
    print("产物:", out, "和", txt)

if __name__ == "__main__":
    main()
