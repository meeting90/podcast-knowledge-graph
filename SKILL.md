---
name: podcast-knowledge-graph
description: 把播客/长视频/访谈抽成带时间戳溯源的知识卡（JSON），并渲染为 HTML 思维导图或写入知识图谱。当用户提供音频、转写稿或节目链接，要求"结构化笔记 / 思维导图 / 观点关系 / 可溯源摘要"时使用。
---

# Podcast → Knowledge Card

## 何时使用

- 用户给一段播客/访谈音频或转写稿，想要**结构化**的笔记（不是流水账摘要）
- 需要"每条观点能回到原文某一秒"的溯源能力
- 需要跨集的观点关系（支持/反驳/延伸/呼应）
- 要把内容沉淀成可查询的图谱

**不适用**：纯新闻摘要、单轮问答、不需要溯源的场合。

## 输入

| 必需 | 说明 |
|---|---|
| 音频直链或本地文件 | 用于转写；没有则至少要有转写稿 |
| 节目元数据 | 标题、嘉宾、发布日期、URL |
| （可选）shownotes | 帮助识别专名和段落 |

## 输出

一份 `knowledge_card.json`，核心结构：

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
groups: [{ gid, name, ids }]    # 思维导图一级分组，覆盖全部 claim
extensions: { concepts: [...], corrections: [...] }
```

完整 schema 与字段约束见 [sop/SOP_v0.3.md](../sop/SOP_v0.3.md)。

## 执行步骤

1. **转写**
   `python scripts/transcribe.py audio.mp3 --model small --lang zh`
   产出带 segment 时间戳的 JSON + txt。长音频先按 40 分钟切片（见脚本注释）。

2. **专名校正**
   先通读转写稿，建立 `transcript_corrections` 表（whisper 对人名/产品名系统性出错）。**引用原话一律用校正后写法。**

3. **按 SOP 抽取**
   - claim 判定：是"主张"不是"描述"；一句话能独立成立
   - 时间戳：起点取说话开始，终点默认取下一条 claim 起点，最长 300 秒
   - 关系：只在确有语义关系时连边，禁止自指与悬空
   - 实体：纯 slug；通用概念不进 `entities`，放 `extensions.concepts`

4. **校验**
   `python scripts/verify_cards.py card.json`
   检查 id 冲突、悬空 target、人物是否混入实体表。

5. **产出**
   - HTML：`render_card.py` 的 `render(card, None, mode='redirect')`
   - 图谱：`ingest_graph.py card.json`（需 semantica）

## 质量闸门（必须过）

- [ ] 每条 claim 的 `timestamp`/`end` 能在音频里对上
- [ ] `groups[].ids` 覆盖全部 claim，不重不漏
- [ ] `relations[].target` 全部存在，无自指
- [ ] 说话者已用对话轮转校验（whisper 不做说话人分离）
- [ ] 抽查 3 条 claim 回听音频，确认没断章取义

## 常见错误

| 错误 | 后果 | 纠正 |
|---|---|---|
| 把描述当观点 | 卡片变成流水账 | 只收"主张句" |
| 时间戳取整段 | 回链失效 | 精确到秒，终点按语义边界 |
| 实体带类型后缀 | 跨卡无法合并 | `pi` 而非 `pi-agent` |
| 关系为凑数而连 | 图谱噪声 | 宁可少连 |
| 忽略说话者校验 | 观点张冠李戴 | 看上下文转场语 |
