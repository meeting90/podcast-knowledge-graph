## 播客知识卡能力

通过 bash 调用 `podcast-kg` 命令。先执行 `podcast-kg --help` 选择子命令，再执行 `podcast-kg <子命令> --help` 查看参数、输入输出及失败语义。这些是命令行程序。

**运行时自检（每次任务先做）**：`podcast-kg doctor`。命令不存在时用 skill 自带的启动器
`python3 <skill目录>/bin/podcast-kg.py <子命令>`：首次调用会自动装运行时（私有 venv + PATH shim），
然后把参数交给 CLI，之后等价于 `podcast-kg`。要显式安装/体检再用 `bin/bootstrap.py`。
两条都失败才向用户报告，并附上命令输出。

抽取规范与质量闸门：`podcast-kg` 装的 skill `podcast-knowledge-graph`。

每期必须同时产出两层：`arcs`（话题弧，8–18 段、每段 3–10 分钟，读者的真实入口）与
`claims`（逐句观点，仅作溯源证据）。只交逐句卡＝读者每次只听到半句话。

默认交付中英双语：`<content_id>.json` + `<content_id>.en.json` + **一份**可切换语言的 HTML
（`podcast-kg i18n scaffold` → 填文字 → `i18n check` → `render --i18n`）。音频不变。

**English**: run `podcast-kg doctor` first; if the command is missing, run the skill's
`bin/podcast-kg.py <args>` — it installs the runtime on first use (private venv) and then delegates.
`bin/bootstrap.py` is the explicit installer. Deliver two cards (`<content_id>.json` + `<content_id>.en.json`) and **one**
switchable HTML (`podcast-kg i18n scaffold` → fill text → `i18n check` → `render --i18n`). Audio stays
the original source. Full instructions: `SKILL.md` (English: `SKILL.en.md`).
