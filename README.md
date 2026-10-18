# podcast-knowledge-graph

把播客 / 长视频 / 深度访谈抽成**可溯源的知识卡**（JSON + Markdown），再渲染成可折叠思维导图，并注入知识图谱。

产出的每条观点（claim）都带**音频时间戳区间**，可以直接回链到原节目——这是这个项目和其他"AI 摘要"最大的区别。

```json
{
  "claim_id": "c17",
  "statement": "订阅制本质上是大厂用 API 利润率补贴用户",
  "speaker": "jin-jing",
  "timestamp": "27:24",
  "end": "28:17",
  "relations": [{ "type": "supports", "target": "c12", "note": "用成本结构佐证" }]
}
```

---

## 这个仓库包含什么

| 目录 | 内容 |
|---|---|
| `sop/SOP_v0.3.md` | **抽取规范**：schema 定义、实体命名规则、claim 关系类型、质检清单 |
| `scripts/transcribe.py` | faster-whisper 封装（16k 单声道、段级时间戳、中文 VAD） |
| `scripts/render_card.py` | 知识卡 JSON → HTML 思维导图（零第三方依赖） |
| `scripts/verify_cards.py` | 校验：id 冲突、悬空关系、人物混入实体表 |
| `scripts/ingest_graph.py` | 知识卡 JSON → Semantica 图谱（Neo4j/FalkorDB/AGE/Neptune） |
| `examples/` | 一张完整示例卡（JSON + Markdown） |

## 不包括什么

**发现层（L1）不在此仓库**：节目源清单、订阅偏好、平台解析 know-how、抓取优先级——这些是运营资产，不随工具开源。

你只需要自己提供：一个音频直链（或本地文件）+ 节目元数据。

---

## 工作流

```
音频 ──transcribe.py──▶ 带时间戳的转写稿
                            │
                            ▼
                  按 SOP 抽取（人工 或 agent）
                            │
                            ▼
                    知识卡 JSON  ◀── verify_cards.py 校验
                       │        │
          render_card.py       ingest_graph.py
                       │        │
                       ▼        ▼
                    HTML 思维导图   知识图谱（含 PROV-O 溯源）
```

## 快速开始

```bash
# 1. 转写（需要 ffmpeg + faster-whisper）
pip install faster-whisper
python scripts/transcribe.py input.mp3 --model small --lang zh

# 2. 按 SOP 抽取，产出 knowledge_card.json
#    参考 examples/knowledge_card.example.json 的结构
#    也可以让 agent 读 sop/SOP_v0.3.md 来执行

# 3. 校验
python scripts/verify_cards.py knowledge_card.json

# 4. 渲染成 HTML（无需任何依赖）
python -c "
import json, sys; sys.path.insert(0,'scripts')
import render_card as rc
card = json.load(open('knowledge_card.json', encoding='utf-8'))
open('out.html','w',encoding='utf-8').write(rc.render(card, None, mode='redirect'))
"

# 5. 入库（可选，需要 semantica）
pip install semantica
python scripts/ingest_graph.py knowledge_card.json
```

## 渲染模式

`render(card, seg_dir=None, mode=...)`：

| mode | 输出 |
|---|---|
| `audio` | 自绘播放器 + 时间点跳转 |
| `redirect` | 纯文字卡 + 官方链接（最保守，无版权风险） |

## Schema 要点

- `source.content_id` 全局唯一（`平台_日期_编号`）
- `claims[].timestamp` / `end` 必填，`end` 默认取下一条 claim 起点，上限 300 秒
- `relations[]` 11 种类型：`supports` / `extends` / `deepens` / `tension_with` / `responds_to` / `parallel` / `implies` / `precondition` / `part_of` / `echoes` / `exemplified_by`
- 实体用**纯 slug**（`pi` 而不是 `pi-agent`），人物与实体分开
- 完整规则见 [sop/SOP_v0.3.md](sop/SOP_v0.3.md)

## 依赖

| 脚本 | 依赖 |
|---|---|
| `transcribe.py` | `faster-whisper`、`ffmpeg` |
| `render_card.py` | **无**（纯标准库） |
| `verify_cards.py` | **无** |
| `ingest_graph.py` | `semantica` |

## License

[MIT](LICENSE)
