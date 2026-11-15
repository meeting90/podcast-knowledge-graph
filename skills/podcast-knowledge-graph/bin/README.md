# bin/

中文 | [English](README.en.md)

| 文件 | 作用 |
| --- | --- |
| `podcast-kg.py` | **唯一入口**：用内置 CLI（`../lib/podcast_kg`）执行命令 |
| `README.md` / `README.en.md` | 本说明 |

```bash
python3 podcast-kg.py doctor          # 零安装，CLI 就在 lib/
python3 podcast-kg.py render ep.json ep.html
python3 podcast-kg.py transcribe ep.mp3   # 需要环境里已有 faster-whisper
```

- `render` / `verify` / `ingest` / `i18n` / `models` / `doctor`：纯标准库，离线可用。
- `transcribe`：需要环境里的 `faster-whisper`；**skill 不安装任何东西**，缺了会明确报错。
  Pi 用户由 extension 准备私有 venv；其他环境请自备（conda / 系统包 / 已有 venv）。
- 没有 venv、没有 shim、没有 pip/PyPI 依赖。`PODCAST_KG_BIN` 可指向现成的 `podcast-kg` 覆盖内置 CLI。
