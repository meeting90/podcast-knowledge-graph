<!-- podcast-kg:start -->
## 播客知识卡能力（Pi）

通过 bash 调用 `podcast-kg` 命令。先执行 `podcast-kg --help` 选择子命令，再执行 `podcast-kg <子命令> --help` 查看参数、输入输出及失败语义。这些是命令行程序。

Pi 侧环境由扩展准备好了：`podcast-kg` 已在 PATH；`/podcast-kg doctor` 等价于 `podcast-kg doctor`。
命令不存在或报错时，先跑随 skill 分发的 `bin/bootstrap.py`，再重试 `podcast-kg doctor`；
两条都失败才向用户报告，并附上命令输出。

抽取规范与质量闸门：`podcast-kg` 装的 skill `podcast-knowledge-graph`（`skills/podcast-knowledge-graph/SKILL.md`）。

每期必须同时产出两层：`arcs`（话题弧，8–18 段、每段 3–10 分钟，读者的真实入口）与
`claims`（逐句观点，仅作溯源证据）。只交逐句卡＝读者每次只听到半句话。

默认交付中英双语：`<content_id>.json` + `<content_id>.en.json` + **一份**可切换语言的 HTML
（`podcast-kg i18n scaffold` → 填文字 → `i18n check` → `render --i18n`）。音频不变。
<!-- podcast-kg:end -->
