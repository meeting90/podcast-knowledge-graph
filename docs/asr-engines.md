# ASR 引擎对比：whisper / Parakeet / SenseVoice / Zipformer

> **English summary (full details below are in Chinese)**
>
> Tested on an i5-13400F / RTX 4060 / 32 GB Windows box with the same audio (synthetic Chinese,
> code-switched zh/en, English with accents + noise, a real 60 s Chinese podcast clip).
>
> | Engine | Pure Chinese CER | zh/en mixed CER | English WER | RTF (warm) | Weight size |
> | --- | --- | --- | --- | --- | --- |
> | whisper large-v3-turbo (GPU) | **0.0%** | **3.0%** | **0.0%** | 17–27× | 1.6 GB |
> | whisper small (CPU) | 1.2–2.4% | 16.7% | 0.0% | 4–5× | 486 MB |
> | SenseVoice int8 (CPU) | 1.2% | 4.5% | 1.9% | **40–48×** | 239 MB |
> | Zipformer CTC small (CPU) | **0.0%** | 40.9% (`<unk>` on English) | — | **46–74×** | 61 MB |
> | Parakeet TDT 0.6B v3 (CPU) | **unusable** (no Chinese) | — | 0.0–3.7% | 15–18× | 670 MB |
>
> **Decision**: keep faster-whisper as the default — it is the only engine that survives
> Chinese tech podcasts (code-switching plus proper nouns). SenseVoice is a valid speed option for
> pure Mandarin; Zipformer CTC small is the best value for pure Chinese but cannot handle English
> terms. The same benchmark also exposed whisper's repetition-loop hallucination, now fixed by
> defaulting `condition_on_previous_text` to off.

> **结论**
>
> 1. **默认仍是 faster-whisper**。中文技术播客（中英混说 + 专名）只有 whisper 全面扛得住：
>    纯中文 0% CER、中英混 3.0% CER、英文 0% WER。
> 2. **Parakeet TDT 0.6B v3 用不了中文**（25 种语言里没有 zh），英文很强，仅适合非中文节目。
> 3. **SenseVoice 是中文场景的速度选项**：CPU 40–48×、带标点与 ITN、token 时间戳、239 MB；
>    代价是中英混说时会把 `Claude Code` 听成 `cloud code`、`Codex` 听成 `codeex`。
> 4. **Zipformer CTC small（61 MB）纯中文 0% CER、45–74×**，是本次性价比最高的中文模型；
>    但它把英文术语全部输出成 `<unk>`，不能单独用于技术播客。
> 5. 同一份数据还抓到 whisper 的重复循环幻觉，已修：默认关闭 `condition_on_previous_text`
>    （71 s 重复音频 10.2% WER / 11.0 s → 0.0% / 2.8 s，正常音频输出逐字不变）。

## 测试环境

| 项 | 值 |
| --- | --- |
| CPU / 内存 / GPU | i5-13400F / 32 GB / RTX 4060 (Windows 11) |
| faster-whisper | 1.2.1（ctranslate2 4.8.4，PyAV 18.1.0） |
| whisper 模型 | `small` int8 CPU（本项目 CPU 默认）、`large-v3-turbo` float16 CUDA（GPU 默认） |
| Parakeet | onnx-asr 0.12.0 + onnxruntime 1.31.1，`nemo-parakeet-tdt-0.6b-v3` **int8**（670 MB） |
| SenseVoice | sherpa-onnx 2.0.1，`sense-voice-zh-en-ja-ko-yue-int8-2024-07-17`（239 MB，8 线程 CPU） |
| Zipformer | sherpa-onnx 2.0.1，`zipformer-zh-en-2023-11-22` int8（encoder 69 MB + decoder 5 MB + joiner 1 MB） |
| Zipformer CTC | sherpa-onnx 2.0.1，`zipformer-ctc-small-zh-int8-2025-07-16`（61 MB，8 线程 CPU） |
| 计时 | 每个样本跑 2 次，取预热后的第 2 次；RTF = 音频秒数 ÷ 推理秒数 |

样本（参考文本已知，WER/CER 可精确计算）：

- 英文同一段 54 词文本：en-US / en-IN / en-GB / en-AU（edge-tts 合成）＋ 10 dB / 0 dB 加噪 ＋ 4 倍重复（71 s）
- 中文 18 s 合成语音；**中英混说** 12 s（`Agent / Claude Code / Codex / API / harness`）
- 真实中文播客 60 s（`clip60.wav`）

合成语音是干净音源，绝对错误率偏低；表格用于**同条件横向对比**，不代表真实播客的绝对错误率。

## 一、英文 / 欧洲语言：Parakeet 很强，但与本项目无关

### 英文结果（WER / 热身后 RTF）

| 样本 | whisper small（CPU int8） | whisper turbo（CUDA fp16） | Parakeet v3（int8 CPU） |
| --- | --- | --- | --- |
| en-US 17.8 s | 0.0% / 3.9× | 0.0% / 17.0× | 0.0% / **17.5×** |
| en-IN 24.2 s | 0.0% / 8.4× | 0.0% / 29.4× | 0.0% / 16.6× |
| en-GB 20.4 s | 0.0% / 7.0× | 0.0% / 25.7× | 0.0% / 16.5× |
| en-AU 18.1 s | 0.0% / 6.2× | 0.0% / 22.9× | 0.0% / 14.5× |
| 白噪 10 dB | 0.0% / 6.1× | 0.0% / 23.3× | 0.0% / 17.7× |
| 白噪 0 dB | 1.9% / 5.9× | 7.4% / 23.2× | 3.7% / 18.3× |
| 重复 71 s | 0.0% / 6.7× | **10.2%** / 6.2× | 0.0% / **15.0×** |

- 干净英文三家都能做满分；Parakeet 在 **CPU** 上就打平 whisper-turbo 在 4060 上的速度。
- 71 s 重复音频上 whisper-turbo 掉进循环幻觉，Parakeet 一次过（15×，0% WER）。
- 0 dB 那行只有一条合成样本，不具统计意义。

### Parakeet 的中文：直接出局

| 样本 | whisper small (CPU) | whisper turbo (CUDA) | Parakeet int8 (CPU) |
| --- | --- | --- | --- |
| 合成中文 18 s | CER 2.4% | **CER 0.0%** | **CER 100%**（0 token，空串） |
| 真实播客 60 s | — | 26.6×，语义连贯 | 空串；开 VAD 后 21 段欧洲语言乱码 |

Parakeet v3 的 25 种语言里没有中文。开 VAD 强行解码真实中文会得到：

```
You too scientific fashion the show. Csőchhan Tácsü, Talti Süsama. Nimme ją mentöite. …
```

**看起来像文本**——接进抽取流程会静默产出一整卡错误观点。

## 二、中文候选：SenseVoice / Zipformer

### 结果（CER / WER，热身后 RTF）

| 样本 | whisper small | whisper turbo | SenseVoice int8 | Zipformer zh-en | Zipformer CTC small |
| --- | --- | --- | --- | --- | --- |
| 纯中文 18 s | 1.2–2.4% / 4–5× | **0.0%** / 20.8× | 1.2% / 47.8× | **0.0%** / 27.3× | **0.0%** / 68.8× |
| 中英混 12 s | 16.7% / 4.5× | **3.0%** / 16.7× | 4.5% / 47.3× | 6.1% / 46.5× | **40.9%** / 74.4× |
| 英文 17.8 s | 0.0% / — | **0.0%** / 22.6× | 1.9% / 40.2× | 11.1% / 42.2× | — |
| 真实中文 60 s | — | 基准 / 26.6× | 1.4%* / 40.2× | 3.2%* / 39.5× | 1.4%* / 45.8× |

\* 60 s 真实音频没有人工标注，以 whisper-turbo 的输出为伪参考（`CER*`），只用于横向排序。

### 定性差异（中英混说，同一句）

参考：`今天我们聊 Agent，Claude Code 和 Codex 到底差在哪，API 成本又该怎么算。`

| 引擎 | 输出 |
| --- | --- |
| whisper turbo | `今天我们聊 Agent、Cloud Code 和 Codex 到底差在哪 API 成本又该怎么算` |
| whisper small | `今天我們聊 agent, cloud code和 codex到底差在哪, API成本又該怎麼算?`（**漂到繁体**） |
| SenseVoice | `今天我们聊agentcloud code和codeex到底差在哪？API成本又该怎么算？` |
| Zipformer zh-en | `今天我们聊AGENT CLOUD CODE 和KODAX 到底差在哪A P I 成本又该怎么算` |
| Zipformer CTC small | `今天我们聊<unk> <unk> <unk> 和<unk> 到底差在哪<unk> 成本又该怎么算` |

真实 60 s 中文上，各家的错法也不同：

| 引擎 | 典型错误 |
| --- | --- |
| whisper turbo | 无（"长篇地谈"也正确） |
| SenseVoice | 多一个"那么"；"长篇地谈"正确；标点最全 |
| Zipformer zh-en | 不禁/不仅、置身/之身、算力/算理、有史/优势、"长篇地毯" |
| Zipformer CTC small | "长篇地这家公司"（漏"谈"）、"那我我知道"（重复） |

### 成本 / 许可 / 能力

| | SenseVoice | Zipformer zh-en | Zipformer CTC small |
| --- | --- | --- | --- |
| 运行时 | sherpa-onnx（onnxruntime） | 同 | 同 |
| 体积 | 239 MB | ~75 MB（int8 三件套） | 61 MB |
| 加载 | 1.2–1.7 s | 1.0–1.2 s | 4.0 s |
| 标点 / ITN | **有**（含数字规范化） | 无 | 无 |
| 时间戳 | token 级（91 token / 83 字） | token 级 | token 级 |
| 长音频 | 30 s 窗口，需自己切（本文 20 s 切片） | 60 s 一次过 | 60 s 一次过 |
| 语言 | zh / yue / en / ja / ko（+50 语种训练） | zh + en | zh（英文 `<unk>`） |
| 许可 | FunASR 模型协议（允许使用/修改/再分发，**需署名**；自定义条款，非 OSI） | Apache-2.0（icefall） | Apache-2.0（icefall） |

### 结论

1. **SenseVoice 不能替代 whisper，但可以当"快速草稿"**：纯中文 1.2% CER 已接近 whisper-turbo，
   速度快 2 倍（CPU vs GPU）、带标点和 token 时间戳、体积 1/7。中英混说的英文术语是硬伤。
2. **Zipformer CTC small 是本次的惊喜**：61 MB、45–74×、纯中文 0% CER；但英文全 `<unk>`，
   只能用于纯中文内容。它适合当"实时字幕 / 段落切分 / 交叉校验"的轻量引擎。
3. **Zipformer zh-en 不如 CTC small**：同为 zipformer，312 MB 的旧双语模型在真实音频上 3.2%，
   比 61 MB 的新中文 CTC 还差，且同样读不准英文专名。
4. 中文技术播客的正确组合仍是 **whisper-turbo 做主转写**；如果将来要压成本，可考虑
   "CTC small 出草稿 + 时间轴，whisper 只复核专名与低置信段"的两段式，但复杂度明显上升，暂不实现。

## 三、整体建议

1. **默认引擎保持 faster-whisper**。唯一在中英混说 + 专名 + 长音频上都不掉链子的选项。
2. **可选后端**（尚未实现，接口设计如下）：
   - `transcribe --engine whisper|sensevoice|zipformer-ctc`，`--engine auto` 按语言路由；
   - 模型走现有 `podcast-kg models`：新增 `models fetch --engine sensevoice`（239 MB）等；
   - 依赖放 optional extra（`podcast-kg[local-asr]` → `sherpa-onnx`），默认不装；
   - token 时间戳 → 按停顿/标点切段 → 复用现有 `_transcript.json` 结构。
3. **不建议**把 Parakeet 接进中文流水线；也不建议为 SenseVoice 放弃 whisper 的专名准确率。
4. 若目标是"实时字幕"而不是"事后转写"，Zipformer（streaming 版）比以上所有离线方案都更合适，
   值得单独测一轮。

## 四、复现

```bash
# 合成样本（英文 / 中文 / 中英混说）
uvx edge-tts -v zh-CN-YunxiNeural --write-media zh.mp3 -t "<中文稿>"
uvx edge-tts -v en-US-AndrewNeural --write-media en.mp3 -t "<英文稿>"
# 转成 16 kHz 单声道 WAV（ffmpeg 或 PyAV）

# whisper
python scripts/bench_asr.py --engine whisper --model large-v3-turbo \
    --device cuda --compute-type float16 --beam 5 --lang zh --runs 2 \
    --ref-file ref_zh.txt zh.wav zhmix.wav real-zh.wav

# Parakeet（独立 venv，避免和 ctranslate2 抢依赖）
uv venv /tmp/pv3 && uv pip install --python /tmp/pv3/Scripts/python.exe "onnx-asr[cpu,hub]"
/tmp/pv3/Scripts/python.exe scripts/bench_asr.py --engine parakeet \
    --runs 2 --ref-file ref_en.txt en.wav

# SenseVoice / Zipformer（sherpa-onnx）
uv venv /tmp/sc && uv pip install --python /tmp/sc/Scripts/python.exe sherpa-onnx
BASE=https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models
curl -LO "$BASE/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2"
curl -LO "$BASE/sherpa-onnx-zipformer-zh-en-2023-11-22.tar.bz2"
curl -LO "$BASE/sherpa-onnx-zipformer-ctc-small-zh-int8-2025-07-16.tar.bz2"
tar xjf sherpa-onnx-*.tar.bz2

/tmp/sc/Scripts/python.exe scripts/bench_asr.py --engine sensevoice \
    --model-dir sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17 \
    --threads 8 --chunk 20 --ref-file ref_zh.txt zh.wav zhmix.wav real-zh.wav
/tmp/sc/Scripts/python.exe scripts/bench_asr.py --engine zipformer-ctc \
    --model-dir sherpa-onnx-zipformer-ctc-small-zh-int8-2025-07-16 \
    --threads 8 --ref-file ref_zh.txt zh.wav zhmix.wav real-zh.wav
```

原始样本与完整 JSONL 结果未入库（合成音频 + 一次性数据）；`scripts/bench_asr.py` 可随时重跑同样的对比。
