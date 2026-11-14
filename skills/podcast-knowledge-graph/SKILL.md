---
name: podcast-knowledge-graph
description: '把播客/长视频/访谈抽成带时间戳溯源的知识卡（JSON，含话题弧），渲染为带中英切换的 HERON 同款 HTML 观点页，或写入可溯源图谱快照。当用户提供音频、转写稿或节目链接，要求"结构化笔记 / 观点地图 / 观点关系 / 可溯源摘要"时使用。English: extract podcasts/interviews into timestamped, source-linked knowledge cards with topic arcs; render a HERON-style HTML page with a zh/en switch; or write a source-linked graph snapshot.'
license: MIT
compatibility: 需要 Python 3.10+ 与 `podcast-kg` CLI（pip / uv tool / pipx 安装）；ffmpeg 可选
metadata:
  repo: https://github.com/meeting90/podcast-knowledge-graph
summary: 把播客/访谈抽成带时间戳溯源的知识卡（话题弧 + 逐句证据），默认中英双语、一份可切换语言的 HTML 观点页；音频不变。
tags: [podcast, transcription, knowledge-graph, whisper, bilingual, timestamps]
use_cases: [播客结构化笔记, 观点地图, 可溯源摘要, 中英双语知识卡]
docs_url: https://github.com/meeting90/podcast-knowledge-graph
---

# Podcast → Knowledge Card

> 中文 | [English](SKILL.en.md)

## 何时使用

-   用户给一段播客/访谈音频或转写稿，想要**结构化**的笔记（不是流水账摘要）
-   需要"每条观点能回到原文某一秒"的溯源能力
-   需要跨集的观点关系（支持/反驳/延伸/呼应）
-   要把内容沉淀成可查询的图谱

**不适用**：纯新闻摘要、单轮问答、不需要溯源的场合。

## 怎么用（以 --help 为准）

通过 bash 调用 `podcast-kg`。**先 `podcast-kg --help` 选子命令，再 `podcast-kg <子命令> --help` 看参数、输入输出和失败语义**；本文件不重复 CLI 细节，两者冲突时以 `--help` 为准。

-   本文件里的 `sop/`、`examples/` 相对于**本文件所在目录**；动手前先读一遍 [sop/SOP.md](sop/SOP.md)
-   触发方式随 agent 而定：Pi / Claude Code 里是 `/skill:podcast-knowledge-graph`；
    其他 agent 直接说“按 podcast-knowledge-graph 的 SOP 把这期播客整理成知识卡”，或在会话里让 agent 读本文件
-   每次任务开始先跑一次 `podcast-kg doctor`；命令不存在时见下面的「安装与自愈」

## 安装与自愈

skill 本体是一份普通的 **Agent Skills** 目录（`SKILL.md` + `sop/` + `examples/` + `bin/`），不绑定任何 agent。
装到别处时，会在该 agent 的指令文件里留一段带标记、指向本文件的块（可重复执行，`--force` 升级）：

```bash
podcast-kg install-skill --list                     # 支持哪些 agent、各自装到哪
podcast-kg install-skill --target claude            # 用户级：~/.claude/skills/podcast-knowledge-graph/
podcast-kg install-skill --target codex --scope project
podcast-kg install-skill --target all --dry-run     # 先看要写哪些文件
podcast-kg install-skill --skills-dir DIR --instructions AGENTS.md   # 不认识的 agent
podcast-kg install-skill --target claude --verify   # 装完自检：文件 / pin / CLI 是否真的可用
```

**CLI 随 skill 分发**（`lib/podcast_kg`），所以装上就能用；只有 `transcribe` 需要的
`faster-whisper` / `av` 第一次运行时才装进私有 venv：

| 情况 | 运行时从哪来 |
| --- | --- |
| 文件被拷进来（marketplace / `npx skills add` / 手工解压） | 直接可用；首次 `transcribe` 自动装依赖 |
| Pi extension 安装 | 首次会话自动准备好 venv 与依赖 |
| 用 `podcast-kg install-skill` 装 | 用现有 CLI，并把 `lib/` 同步成同一版本 |

自愈命令（幂等；已就绪时秒回，不联网）：

```bash
python3 <skill目录>/bin/podcast-kg.py doctor     # 首选入口：内置 CLI，缺依赖时会自动装
python3 <skill目录>/bin/bootstrap.py             # 显式安装转写依赖（venv + PATH shim）
python3 <skill目录>/bin/bootstrap.py --check     # 只检查，未就绪退出码 1
python3 <skill目录>/bin/bootstrap.py --json      # ready / cli / version / pinned / action / notes
python3 <skill目录>/bin/bootstrap.py --plan      # 报告会做什么，不动文件
python3 <skill目录>/bin/bootstrap.py --extras none   # 只装 render/verify（离线可用，不拉 whisper）
python3 <skill目录>/bin/bootstrap.py --models small # 装依赖 + 预取权重（486 MB）
```

Windows 用 `<skill目录>\bin\bootstrap.cmd`；POSIX 也可以直接 `<skill目录>/bin/bootstrap`。
    技能市场会把脚本**单独**拷到临时目录执行，所以以 `bootstrap.py` 为准（版本 pin 已内置，不依赖同目录文件）；两个启动器只是本地便利入口。

- 装到哪：`$PODCAST_KG_HOME`（Windows `%LOCALAPPDATA%\podcast-kg`，macOS `~/Library/Application Support/podcast-kg`，Linux `~/.local/share/podcast-kg`），只在私有 venv 里，不动系统 Python；shim 写到 `$PODCAST_KG_HOME/bin`（以及存在时的 `~/.local/bin`）。
- 装什么：内置 CLI 的版本由 `runtime.json` 的 `version` 固定；bootstrap 只安装 `deps`
  （`faster-whisper` + `av<19`），不再安装 `podcast-kg` 包，也不依赖 PyPI。
- 没有 Python 也能起来：有 `uv` 时用 uv 托管的 Python 3.12 建 venv；连 uv 都没有就先装 uv（`curl -LsSf https://astral.sh/uv/install.sh | sh`）。
- 转写依赖（faster-whisper + ctranslate2）首次安装要联网、几百 MB；`render`/`verify`/`ingest`/`i18n` 无需依赖、完全离线。

`podcast-kg bootstrap [--check|--plan|--json]` 是同一实现的 CLI 入口；
`podcast-kg setup` / `unsetup` 是 `--target pi` 的旧写法。

## 输入

| 必需 | 说明 |
| --- | --- |
| 音频直链或本地文件 | 用于转写；没有则至少要有转写稿 |
| 节目元数据 | 标题、嘉宾、发布日期、URL |
| （可选）shownotes | 帮助识别专名和段落 |

## 输出

所有产物写到**当前工作目录**下的 `.outputs/`（CLI 未显式指定输出路径时的默认行为，具体见各子命令 `--help`）：

```
.outputs/
├── <audio>_transcript.json / .txt     转写稿
├── <content_id>.json / .md            母语知识卡（抽取结果）
├── <content_id>.<lang>.json           译文卡（默认 en；结构一致，只换文字）
├── <content_id>_arcs.json             话题弧层（阅读主视图）
├── <content_id>.html                  单文件页：多语言时右上角切换
├── <content_id>_arcs.html             话题弧页（点一次连播一整段）
├── <content_id>_graph.json            图谱快照
└── registry/                          entities / people / concepts
```

**默认交付双语**：`<id>.json`（中文）+ `<id>.en.json`（英文）+ **一份** `<id>.html`。
音频始终是原始音源——不配音、不换源；切换语言只换文字（含按钮/提示/目录/播放条）。

### 每期两个阅读层（别只交逐句卡）

| 层 | 单位 | 量级 | 谁看 |
| --- | --- | --- | --- |
| **话题弧 `arcs`** | 主持人开启话题 → 嘉宾讲完 → 收束 | 8–18 段/期，每段 3–10 分钟 | **读者的默认真实入口** |
| 逐句 `claims` | 一句一条主张 | 30–113 条/期，中位 45–105 秒 | 溯源、引用、图谱 |

只交逐句卡＝读者每次只听到半句话。实测 60–75% 的相邻 claim 间隔 ≤2 秒，
它们本来就是同一段话被切开的；而且抽取时极易把**主持人开启话题的那个问题**丢掉，
而那正是读者最缺的上下文。

知识卡核心结构：

```yaml
source: { content_id, platform, title, url, audio_url, published_at }
people: [{ person_id, name, role, identity }]        # role: host/guest/mentioned
entities: [{ entity_id, name, type }]                # 纯 slug，不带类型后缀
claims:
  - claim_id: c01
    statement: "一句话观点（不是描述，是主张）"
    speaker: person_id
    timestamp: "12:34"          # 起点
    end: "13:10"                # 终点，上限 300 秒
    type: assertion|prediction|definition|...
    relations:                  # 与其他 claim 的关系
      - { type: supports, target: c05, note: "为什么" }
groups: [{ gid, name, ids }]    # 观点页一级分组，覆盖全部 claim
arcs:                          # 阅读主视图：一期 8–18 段
  - arc_id: a01
    title: "从物理到脑科学：一条二十年的弯路"
    summary: "这一段在讲什么（2–3 句，给读者一个听下去的理由）"
    start: "01:14"             # 播放区间（含前后留白）
    end: "10:08"
    duration_sec: 534
    speech_sec: 500            # 纯发言时长
    open_question: "…"         # 主持人开启话题的问句（有就填）
    open_line: "…"             # 该话题被开启时的转写原话（不分说话人）
    points: [{ claim_id, at, statement }]   # 2–4 条要点，按时间排序
    beats:  [{ at, gist, claims }]          # 3–6 个回合
    evidence: [c01, c02, …]                 # 这一段覆盖的全部 claim（折叠展示）
    context: [{ arc_id, why }]              # 要听懂它，前面哪段已铺垫
extensions: { concepts: [...], corrections: [...] }


```

完整 schema 与字段约束见 [sop/SOP.md](sop/SOP.md)（英文：[sop/SOP.en.md](sop/SOP.en.md)）；弧的字段形状见 [examples/arcs.example.json](examples/arcs.example.json)。

## 执行步骤

下面只说每步**要做什么**和**验收标准**；命令怎么写一律现场用 `--help` 确认。

1.  **运行时自检（每次，最先做）**  
    首选入口是 skill 自带的启动器（CLI 已内置，不需要任何安装）：

    ```bash
    python3 <skill目录>/bin/podcast-kg.py doctor
    ```

    如果 `podcast-kg` 恰好在 PATH 上，也可以直接用。`doctor` 显示转写依赖未安装是正常的：
    第一次 `transcribe` / `models fetch` 会把 `faster-whisper` + `av` 装进 `$PODCAST_KG_HOME/venv`
    （数百 MB，需联网），之后离线可用。要显式体检/预装：`<skill目录>/bin/bootstrap.py [--check|--json]`。
    启动器都失败时，把命令和输出原样报给用户，不要凭猜测继续。
    
2.  **转写**  
    用 `transcribe` 子命令（参数见 `podcast-kg transcribe --help`）。得到段级时间戳的 JSON + `[mm:ss]` 全文，后续引用只认这份时间轴。长音频先切片，单片建议 ≤ 40 分钟。
    
    **模型不随 skill 分发**（small 486 MB）：首次转写会下载到 HF 缓存。离线 / 内网机器先
    `podcast-kg models fetch --model small`，或用 `--model-dir DIR` / `PODCAST_KG_MODEL_DIR` 指向已下载目录；
    `podcast-kg models list` 看体积与状态，`PODCAST_KG_OFFLINE=1` 时缺权重会直接报错而不是静默联网。
    
    要切话题弧就加 `--words`：额外出 `<audio>_words.json`（词级时间戳）。**弧的起止点必须对齐到词边界**，
    否则回放开场就少半个词/多一个词（段级时间戳只有 0.1s 粒度，切点常常落在词中间）。
    
3.  **专名校正**  
    先通读转写稿，建立 `transcript_corrections` 表（whisper 对人名/产品名系统性出错）。**引用原话一律用校正后写法。**
    
4.  **按 SOP 抽取**
    
    -   claim 判定：是"主张"不是"描述"；一句话能独立成立
    -   时间戳：起点取说话开始，终点默认取下一条 claim 起点，最长 300 秒
    -   关系：只在确有语义关系时连边，禁止自指与悬空
    -   实体：纯 slug；通用概念不进 `entities`，放 `extensions.concepts`
5.  **分话题弧（关键一步）**

    以「主持人开启话题 → 嘉宾讲完 → 收束」为单位把 claim 聚成弧，参数见
    `podcast-kg arcs --help`（当前版本可能还没这个子命令，那就用本仓库的
    `build_arcs.py`，它默认读 `.outputs/` 并写到 `.outputs/arcs/`）。
    硬规则写在 [sop/SOP.md](sop/SOP.md) 的 §2.7，
    最容易走偏的两条是：

    -   **边界只认停顿与主持人开口**，不按句子数切、不按分组机械切
    -   **不跨主题分组合并**：跨组只在 <60 秒时才允许

    弧定好之后补 `title` / `summary`（自动标题只能兜底，读者看的就是这两行）。

    有 `--words` 产出的词级时间戳时，`build_arcs.py` 会自动把每段起止点挪到最近的词边界，
    并写成带小数秒的 `1:04:18.72`（整秒会把词切开）。没有词级文件时退回整秒。

    四类自动信号都失效时（典型：主持人夹在一段话中间说「节目最后我想问一个点」，
    两边既没停顿也没换分组），在精修稿里人工指定切点，
    格式 `"<content_id>": {"_breaks": [{"before": "c69", "at": "1:04:18"}]}`。
    人工切点优先级最高：任何合并都不会跨过它，且 `at` 两侧都不重叠；
    切完任一侧不足 60 秒会直接忽略并提示。
6.  **校验**  
    `verify` 子命令有默认报告、`--build-registry`、`--coverage` 三种模式，用 `podcast-kg verify --help` 确认。**输出有问题不等于命令失败**：退出码 0 也要自己读报告。

    弧还要单独体检：`evidence` 是否覆盖全部 claim、相邻弧的播放区间是否重叠、
    有没有 <60 秒的碎段。
7.  **产出**

    -   落盘：知识卡写成 `.outputs/<content_id>.json` 与 `.outputs/<content_id>.md`
    -   话题弧：`<content_id>_arcs.json`（给产品端）+ `<content_id>_arcs.html`（本地验收）
    -   双语：`podcast-kg i18n scaffold` 生成译文骨架 → 填文字 → `i18n check` → `render --i18n`（见第 8 步）
    -   HTML：`render` 子命令；页面与 [heronai.top](https://heronai.top) 详情页同一套 DOM/样式，
        卡里有 `arcs`（或旁挂 `<card>_arcs.json`、或 `--arcs`）时**按话题弧渲染**，否则退回逐句视图
    -   图谱：`ingest` 子命令（纯标准库、离线；只按 id 去重，不做模糊实体消解）

8.  **中英双语（默认交付）**

    **音频不变**：原音源、原时间轴，只翻文字。

    ```bash
    # 生成骨架：id / 时间戳 / 分组 / 关系原样保留，文字留空
    podcast-kg i18n scaffold .outputs/<id>.json --lang en

    # 只填这些字段：source.title/series、groups[].name、people[].role/identity、
    # claims[].statement/evidence/relations[].note、
    # arcs[].title/summary/open_question/open_line/points[].statement/beats[].gist
    # 专名保留原文（Claude Code / Orca / ADE / harness），不要硬翻

    podcast-kg i18n check .outputs/<id>.json .outputs/<id>.en.json   # 硬错 -> 退出码 1
    podcast-kg render .outputs/<id>.json .outputs/<id>.html       --i18n en=.outputs/<id>.en.json --default-lang zh
    ```

    规则与字段表见 [sop/SOP.md](sop/SOP.md) §7。**不要**为两种语言各出一份 HTML。

## 质量闸门（必须过）

-   \[ \] 每条 claim 的 `timestamp`/`end` 能在音频里对上
-   \[ \] `groups[].ids` 覆盖全部 claim，不重不漏
-   \[ \] `relations[].target` 全部存在，无自指
-   \[ \] 说话者已用对话轮转校验（whisper 不做说话人分离）
-   \[ \] 抽查 3 条 claim 回听音频，确认没断章取义

双语层：

-   [ ] `i18n check` 0 错误；每条 claim 的 `timestamp`/`end` 两种语言逐字一致
-   [ ] 抽查 3 条：译文没有丢限定词（可能/约/据称），专名保留原文
-   [ ] 弧 `title`/`summary` 两种语言都能独立读通，不是字对字直译
-   [ ] 只出一份 HTML；切到 EN 后按钮/提示/目录/播放条全英文，深链 `#claim-c21` 仍能定位
-   [ ] 播放器只播原始音频（没有译文配音、没有换源）

话题弧层（只交 claim 不算完成）：

-   \[ \] `arcs[].evidence` 合起来覆盖全部 claim，一个不漏
-   \[ \] 弧的 `start`/`end` 落在词边界上（有 `--words` 时自动对齐）；相邻弧的播放区间不重叠
-   \[ \] 没有 <60 秒的碎段；弧长中位落在 3–10 分钟
-   \[ \] 每段能回答“主持人问了什么” —— 有 `open_question` 或 `open_line`
-   \[ \] 抽查 3 段（最早 / 中位 / 最长）连续听完，确认这一段自己能立住
-   \[ \] `title` / `summary` 已人工写过，不是自动截取的半句话

## 常见错误

| 错误 | 后果 | 纠正 |
| --- | --- | --- |
| 把描述当观点 | 卡片变成流水账 | 只收"主张句" |
| 时间戳取整段 | 回链失效 | 精确到秒，终点按语义边界 |
| 实体带类型后缀 | 跨卡无法合并 | `pi` 而非 `pi-agent` |
| 关系为凑数而连 | 图谱噪声 | 宁可少连 |
| 忽略说话者校验 | 观点张冠李戴 | 看上下文转场语 |
| 拿逐句 claim 当阅读单位 | 读者每次只听到半句话，要连点好几次才凑出语境 | 交 `arcs`，claim 降为证据层 |
| 没确认 `podcast-kg` 可用就开始抽取 | 干到一半才在 `transcribe` 报 command not found | 先 `doctor`，失败就跑 `bin/bootstrap.py`，再 `doctor` |
| 只录嘉宾主张、丢掉主持人的提问 | 话题为什么开始、在回答什么，全丢了 | 主持人的问句进 `open_question`/`open_line` |
| 按句子数或分组机械切弧 | 切在话题中间，听众被腰斩 | 边界只认停顿与主持人开口 |
| 译稿改了 id / 时间戳 / 分组 | 双语切换错位、深链失效 | 只翻文字；`i18n check` 卡住结构漂移 |
| 为两种语言各出一份 HTML | 两份会各自漂移，分享链接分叉 | 一份 HTML + `--i18n`，右上角切换 |
| 给英文重新配音 / 换音频 | 观众听到的不是本人 | 音频只保留原始音源 |
| 主持人中途转场却照旧并成一段（「最后我想问一个点」） | 时代级话题被塞在上一段末尾，读者点开听到一半才反应过来 | 精修稿 `_breaks` 人工指定切点 |
| 弧内要点堆十几条、还带关系 | 换了个姿势的流水账 | 每弧 2–4 条要点，关系只连弧与弧 |
| 弧区间直接首尾相接不留白 | 每段开头都缺半句、结尾被砍 | 前留 10s、后留 6s，再按中点切开 |
