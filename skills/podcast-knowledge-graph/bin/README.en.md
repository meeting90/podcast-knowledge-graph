# bin/

[中文](README.md) | **English**

| File | Purpose |
| --- | --- |
| `podcast-kg.py` | **the only entry point**: runs commands with the bundled CLI (`../lib/podcast_kg`) |
| `README.md` / `README.en.md` | this note |

```bash
python3 podcast-kg.py doctor          # zero install; the CLI is in lib/
python3 podcast-kg.py render ep.json ep.html
python3 podcast-kg.py transcribe ep.mp3   # needs faster-whisper in the environment
```

- `render` / `verify` / `ingest` / `i18n` / `models` / `doctor`: stdlib only, offline.
- `transcribe`: needs `faster-whisper` in the environment; **the skill installs nothing** and reports it
  when missing. Pi users get a private venv from the extension; other environments must provide it
  (conda, system packages, an existing venv).
- No venv, no shims, no pip/PyPI dependency. `PODCAST_KG_BIN` points at an existing `podcast-kg` to
  override the bundled CLI.
