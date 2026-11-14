## 播客知识卡能力

通过 bash 调用 `podcast-kg` 命令。先执行 `podcast-kg --help` 选择子命令，再执行 `podcast-kg <子命令> --help` 查看参数、输入输出及失败语义。这些是命令行程序。

**运行时自检（每次任务先做）**：`podcast-kg doctor`。命令不存在时用 skill 自带的启动器
`python3 <skill目录>/bin/podcast-kg.py <子命令>`：CLI 已随 skill 分发，直接可用；
只有首次 `transcribe` / `models fetch` 会把 `faster-whisper` 装进私有 venv。要显式体检/预装再用 `bin/bootstrap.py`。
两条都失败才向用户报告，并附上命令输出。

抽取规范与质量闸门：`podcast-kg` 装的 skill `podcast-knowledge-graph`。

每期必须同时产出两层：`arcs`（话题弧，8–18 段、每段 3–10 分钟，读者的真实入口）与
`claims`（逐句观点，仅作溯源证据）。只交逐句卡＝读者每次只听到半句话。

默认交付中英双语：`<content_id>.json` + `<content_id>.en.json` + **一份**可切换语言的 HTML
（`podcast-kg i18n scaffold` → 填文字 → `i18n check` → `render --i18n`）。音频不变。

**English**: run `podcast-kg doctor` first; if the command is missing, run the skill's
`bin/podcast-kg.py <args>` — the CLI ships with the skill; only the first transcribe installs
dependencies into a private venv. `bin/bootstrap.py` is the explicit dependency installer. Deliver two cards (`<content_id>.json` + `<content_id>.en.json`) and **one**
switchable HTML (`podcast-kg i18n scaffold` → fill text → `i18n check` → `render --i18n`). Audio stays
the original source. Full instructions: `SKILL.md` (English: `SKILL.en.md`).
