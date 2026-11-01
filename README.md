# podcast-knowledge-graph

一个 **Pi extension + Python 扩展包**：装一次，Pi 里就能把播客 / 长视频 / 深度访谈抽成**可溯源的知识卡**（JSON + Markdown），渲染成 HERON 同款的观点页（可折叠、点时间戳回链原声），或写入知识图谱。

- **Pi extension**（`.pi/extensions/podcast-kg.ts`）：薄桥接层，负责准备 Python 环境、把 `podcast-kg` 放进 PATH、追加 system prompt、注册 skill；
- **Python 包**（`src/podcast_kg`）：真正干活的 CLI——转写、校验、渲染、入库。

每条观点（claim）都带**音频时间戳区间**，可以直接回链到原节目——这是它和普通"AI 摘要"最大的区别。

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

## 何时使用

- 给一段播客 / 访谈的音频、转写稿或节目链接，想要**结构化**笔记，而不是流水账摘要
- 需要"每条观点都能回到原文某一秒"的溯源能力
- 需要跨集的观点关系：支持 / 反驳 / 延伸 / 呼应
- 想把内容沉淀成可查询的知识图谱

## 安装

### 方式 A：作为 Pi extension 安装（推荐）

```bash
pi install git:github.com/meeting90/podcast-knowledge-graph
# 只给当前项目： pi install -l git:github.com/meeting90/podcast-knowledge-graph
```

Pi 会加载两个资源：

| 资源 | 作用 |
| --- | --- |
| `.pi/extensions/podcast-kg.ts` | 首次会话时自动创建私有 venv 并装齐依赖（`podcast-kg[all]`），把 `podcast-kg` 放进 PATH，追加 system prompt，并注册 `/podcast-kg` 命令 |
| `.pi/skills/podcast-knowledge-graph/` | skill 本体：`SKILL.md`、`sop/SOP.md`、`examples/` |

依赖是**随扩展装好**的：第一次启动 Pi 时会一次性装到 `~/.pi/agent/cache/podcast-kg/venv`（含 `faster-whisper` + `semantica`），之后启动不再重复。检查：

```text
/podcast-kg doctor        # 或在 bash 里 podcast-kg doctor
```

本仓库自己也是可直接跑的 Pi 项目：

```bash
cd podcast-knowledge-graph && pi        # 首次会问是否信任（要加载 .pi/extensions）
```

### 方式 B：只装 CLI（无 Pi extension）

```bash
uv tool install "podcast-kg[all]"     # 或 pipx / pip install "podcast-kg[all]"
podcast-kg setup                      # 装 skill + APPEND_SYSTEM 块（默认用户级）
podcast-kg doctor
```

| 位置 | 内容 |
| --- | --- |
| `~/.pi/agent/skills/podcast-knowledge-graph/` | skill 本体 |
| `~/.pi/agent/APPEND_SYSTEM.md` | 追加一段带标记的说明（不动已有内容，可被 `unsetup` 干净移除） |

项目级安装：`podcast-kg setup --scope project` → `.pi/skills/...` + `.pi/APPEND_SYSTEM.md`；`podcast-kg unsetup --scope project` 移除。

> 两种方式二选一：extension 已经提供 skill 与 prompt 片段，再跑 `podcast-kg setup` 会出现同名 skill（Pi 保留先发现的并告警）。
> 装完在 Pi 里 `/reload` 或重启即可。

## 使用

装好后直接说"把这段播客整理成知识卡"，或显式调用 skill：

```text
/skill:podcast-knowledge-graph 把这期播客整理成知识卡，音频 ./ep42.mp3
```

skill 会按 `sop/SOP.md` 走完 转写 → 抽取 → 校验 → 产出。也可以手动用 CLI：

```bash
podcast-kg --help                      # 选子命令
podcast-kg transcribe --help           # 再查参数 / 输入输出 / 失败语义
```

```bash
podcast-kg doctor                      # 环境自检（解释器 / ffmpeg / 可选依赖 / skill 状态）
podcast-kg transcribe ep42.mp3 --model small --lang zh
podcast-kg verify .outputs/ep42.json   # 可一次传多张卡做跨卡归一
podcast-kg render .outputs/ep42.json   # → .outputs/ep42.html
podcast-kg ingest .outputs/ep42.json   # → .outputs/ep42_graph.json
```

所有产物默认写到**当前目录**的 `.outputs/`。**`--help` 是权威说明**（参数、输入输出、退出码），下面的例子只是常见用法。

### 可选依赖

| 子命令 | 依赖 | 说明 |
| --- | --- | --- |
| `render` / `verify` / `setup` / `doctor` | **无**（纯标准库） | 离线可用 |
| `transcribe` | `faster-whisper` | 首次调用自动安装 |
| `ingest` | `semantica` | 首次调用自动安装 |

自动安装会按当前解释器的安装方式选择 `pip` 或 `uv pip install --python <python>`（`uv tool` 的 venv 没有 pip）。想自己控制：

```bash
podcast-kg doctor --install all         # 提前装
export PODCAST_KG_NO_AUTO_INSTALL=1     # 禁用自动安装
uv tool install --with "faster-whisper" --with "semantica" podcast-kg   # 一次装齐
```

`ffmpeg` 可选：没有时转写直接用 PyAV 解码原音频。

## 从源码开发

```bash
git clone https://github.com/meeting90/podcast-knowledge-graph
cd podcast-knowledge-graph
uv venv && uv pip install -e ".[all]"

pi                                       # 以项目形态加载 extension + skill
pi -e .                                 # 或把它当成 Pi 包加载

# 方式 B 的安装逻辑（不会碰你的真实 Pi 配置）
podcast-kg setup --agent-dir /tmp/pk-agent --dry-run
podcast-kg setup --agent-dir /tmp/pk-agent

uv build                                 # wheel 会把 .pi/skills 映射成 podcast_kg/skill
```

## 目录结构

```
podcast-knowledge-graph/
├── package.json                  # Pi 包清单：extension + skill
├── pyproject.toml                # Python 包 podcast-kg：依赖、CLI 入口
├── APPEND_SYSTEM.md              # 追加进 Pi system prompt 的说明（唯一来源）
├── .pi/                          # Pi 侧资源（唯一来源，打包时映射进 wheel）
│   ├── extensions/podcast-kg.ts  #   extension：环境准备 / PATH / prompt / skill / 命令
│   └── skills/podcast-knowledge-graph/
│       ├── SKILL.md              #   触发条件、执行步骤、质量闸门
│       ├── sop/SOP.md            #   抽取规范：schema、命名规则、关系类型、质检清单
│       └── examples/             #   一张完整示例卡（JSON + Markdown）
└── src/podcast_kg/               # Python 实现
    ├── cli.py                    #   子命令实现
    ├── args.py                   #   argparse 定义：每个子命令的 --help（权威说明）
    ├── pi_skill.py               #   方式 B：把 skill + APPEND_SYSTEM 块装进 Pi
    ├── deps.py                   #   可选依赖按需安装（pip / uv tool 兼容）
    ├── outputs.py                #   .outputs/ 约定
    ├── transcribe.py             #   faster-whisper 封装（段级时间戳、VAD）
    ├── render_card.py            #   知识卡 JSON → HERON 同款 HTML（纯标准库）
    ├── verify_cards.py           #   跨卡实体 / 人物归一校验
    └── ingest_graph.py           #   知识卡 JSON → Semantica 图谱
```

## 工作流

```
音频 ──podcast-kg transcribe──▶ 带时间戳的转写稿
                                    │
                                    ▼
                          按 SOP 抽取（人工 或 agent）
                                    │
                                    ▼
                          知识卡 JSON ◀── podcast-kg verify
                              │       │
                 podcast-kg render    podcast-kg ingest
                              │       │
                              ▼       ▼
                       HTML 观点页   知识图谱（含 PROV-O 溯源）
```

## 渲染模式

`podcast-kg render <card.json> [out.html] [--mode audio|redirect]`：

| mode | 输出 |
| --- | --- |
| `redirect` | 纯文字卡 + 官方链接（最保守） |
| `audio` | 自绘播放器 + 时间点跳转，播到 `end` 自动暂停 |

页面右上角「✎ 编辑推荐」进入编辑态：点行尾 ☆ 增删推荐、填推荐理由，面板里可以：

- **⤓ 生成编辑后的页面**：把当前推荐写进 HTML，另存为 `<content_id>_picks.html`，直接发给别人打开就是编辑后的样子
- **⧉ 复制 JSON / 下载 .json**：把 `picks` 回填到卡片 JSON，下次渲染自动带上

## Schema 要点

- `source.content_id` 全局唯一（`平台_日期_编号`）
- `claims[].timestamp` / `end` 必填，`end` 默认取下一条 claim 起点，上限 300 秒
- `relations[]` 11 种类型：`supports` / `extends` / `deepens` / `tension_with` / `responds_to` / `parallel` / `implies` / `precondition` / `part_of` / `echoes` / `exemplified_by`
- `groups[].ids` 必须覆盖全部 claim，不重不漏
- 实体用**纯 slug**（`pi` 而不是 `pi-agent`），人物与实体分开
- 完整规则见 skill 里的 `sop/SOP.md`

## License

[MIT](LICENSE)
