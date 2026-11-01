---
name: podcast-knowledge-graph
description: 把播客/长视频/访谈抽成带时间戳溯源的知识卡（JSON），并渲染为 HERON 同款 HTML 观点页或写入知识图谱。当用户提供音频、转写稿或节目链接，要求"结构化笔记 / 观点地图 / 观点关系 / 可溯源摘要"时使用。
license: MIT
compatibility: 需要 Python 3.10+ 与 `podcast-kg` CLI（pip / uv tool / pipx 安装）；ffmpeg 可选
metadata:
  repo: https://github.com/meeting90/podcast-knowledge-graph
---

# Podcast → Knowledge Card

## 何时使用

-   用户给一段播客/访谈音频或转写稿，想要**结构化**的笔记（不是流水账摘要）
-   需要"每条观点能回到原文某一秒"的溯源能力
-   需要跨集的观点关系（支持/反驳/延伸/呼应）
-   要把内容沉淀成可查询的图谱

**不适用**：纯新闻摘要、单轮问答、不需要溯源的场合。

## 怎么用（以 --help 为准）

通过 bash 调用 `podcast-kg`。**先 `podcast-kg --help` 选子命令，再 `podcast-kg <子命令> --help` 看参数、输入输出和失败语义**；本文件不重复 CLI 细节，两者冲突时以 `--help` 为准。

- 本 skill 由 `podcast-kg setup` 安装；它依赖的 CLI 是同一个包提供的
- 显式触发：`/skill:podcast-knowledge-graph 把这期播客整理成知识卡`
- 本文件里的 `sop/`、`examples/` 相对于**本文件所在目录**
- 升级后重跑 `podcast-kg setup --force`，再在 Pi 里 `/reload`

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
├── <content_id>.json / .md            知识卡（抽取结果）
├── <content_id>.html                  观点页
├── <content_id>_graph.json            图谱快照
└── registry/                          entities / people / concepts
```

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
extensions: { concepts: [...], corrections: [...] }


```

完整 schema 与字段约束见 [sop/SOP.md](sop/SOP.md)。

## 执行步骤

下面只说每步**要做什么**和**验收标准**；命令怎么写一律现场用 `--help` 确认。

1.  **环境自检（首次）**  
    `podcast-kg doctor`。缺可选依赖时，下一次调用对应子命令会自动装；想提前装看 `doctor --help`。
    
2.  **转写**  
    用 `transcribe` 子命令（参数见 `podcast-kg transcribe --help`）。得到段级时间戳的 JSON + `[mm:ss]` 全文，后续引用只认这份时间轴。长音频先切片，单片建议 ≤ 40 分钟。
    
3.  **专名校正**  
    先通读转写稿，建立 `transcript_corrections` 表（whisper 对人名/产品名系统性出错）。**引用原话一律用校正后写法。**
    
4.  **按 SOP 抽取**
    
    -   claim 判定：是"主张"不是"描述"；一句话能独立成立
    -   时间戳：起点取说话开始，终点默认取下一条 claim 起点，最长 300 秒
    -   关系：只在确有语义关系时连边，禁止自指与悬空
    -   实体：纯 slug；通用概念不进 `entities`，放 `extensions.concepts`
5.  **校验**  
    `verify` 子命令有默认报告、`--build-registry`、`--coverage` 三种模式，用 `podcast-kg verify --help` 确认。**输出有问题不等于命令失败**：退出码 0 也要自己读报告。
    
6.  **产出**
    
    -   落盘：知识卡写成 `.outputs/<content_id>.json` 与 `.outputs/<content_id>.md`
    -   HTML：`render` 子命令；页面里「✎ 编辑推荐」→ 增删推荐 / 写理由 → 「⤓ 生成编辑后的页面」直接导出带推荐的新 HTML
    -   图谱：`ingest` 子命令（首次自动装 semantica）

## 质量闸门（必须过）

-   \[ \] 每条 claim 的 `timestamp`/`end` 能在音频里对上
-   \[ \] `groups[].ids` 覆盖全部 claim，不重不漏
-   \[ \] `relations[].target` 全部存在，无自指
-   \[ \] 说话者已用对话轮转校验（whisper 不做说话人分离）
-   \[ \] 抽查 3 条 claim 回听音频，确认没断章取义

## 常见错误

| 错误 | 后果 | 纠正 |
| --- | --- | --- |
| 把描述当观点 | 卡片变成流水账 | 只收"主张句" |
| 时间戳取整段 | 回链失效 | 精确到秒，终点按语义边界 |
| 实体带类型后缀 | 跨卡无法合并 | `pi` 而非 `pi-agent` |
| 关系为凑数而连 | 图谱噪声 | 宁可少连 |
| 忽略说话者校验 | 观点张冠李戴 | 看上下文转场语 |