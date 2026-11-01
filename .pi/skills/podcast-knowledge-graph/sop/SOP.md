# 内容结构化抽取 SOP

> 工具统一走 `podcast-kg` CLI；本文件只规定**内容标准**，命令参数一律以 `podcast-kg <子命令> --help` 为准。

---

## 一、输入

1. **音频/视频**：有直链优先，用于时间点回链与质检；
2. **转写稿**：本地 whisper，带 segment 时间戳；
3. **节目元数据**：标题、shownotes、嘉宾介绍、章节大纲（如有）。

没有转写稿时先跑 `podcast-kg transcribe`（参数见 `--help`）。

---

## 二、Schema

### 2.1 核心字段

```yaml
# ── 元数据层 ──
source:
  content_id: string          # 全局唯一：平台_日期_编号（如 transistor_20260917_319）
  platform: enum              # transistor.fm / xiaoyuzhoufm / youtube / mp.weixin ...
  title: string
  url: string                 # 原文/原音频页面
  audio_url: string?          # 直链，时间点回链的基础
  duration_sec: int?
  published_at: date
  series: string?
  episode_no: string?

groups:                       # 必填，观点页的一级主题分组
  - gid: g1
    name: "① 产品与工程"
    ids: [c01, c02, ...]      # 必须覆盖全部 claim_id，不重不漏

# ── 人物层 ──
people:
  - person_id: string         # 全局 slug（见 §2.6）
    name: string
    aliases: string[]         # 别名/英文名/昵称
    role: enum                # host / guest / mentioned（必填）
    identity: string
    org: string[]
    links: url[]
    first_appeared_in: content_id

# ── 实体层 ──
entities:
  - entity_id: string         # 全局 slug（见 §2.4）
    type: enum                # company / product / book / paper
    name: string
    aliases: string[]         # 中文名/旧名/别称
    url: string?
    context: string           # 在本条内容中的角色

# ── 观点层 ──
claims:
  - claim_id: string          # c001...（同卡内唯一）
    speaker: person_id        # 必须存在于 people
    timestamp: "mm:ss"
    end: "mm:ss"
    type: enum                # 方法论 / 判断预测 / 事实数据 / 经验教训 / 争议观点
    statement: string         # ≤50 字
    evidence: string?
    confidence: enum          # 作者原话直接表达 / 转述推断 / 对话中多人共识
    relations: [{type, target, note}]
    tags: string[]

# ── 动态区 ──
extensions:
  concepts:                   # 通用概念/方法论/框架，不放 entities
    - {name: "Agent Harness", note: "作为一类工具的统称", ref_claims: [c02]}
  ...                         # 其他业务属性（见 §2.2）

transcript_corrections:       # 专名纠正表（见 §4.4）
```

### 2.2 动态扩展字段

核心字段固定，业务属性开放，新属性必须登记。

| 属性名 | 类型 | 说明 |
|---|---|---|
| `concepts` | list[{name, note, ref_claims}] | 通用概念/框架 |
| `contrarian_views` | list[{claim_ref, why_contrarian}] | 反共识观点 |
| `costs` / `opportunities` / `action_items` | list | 按需 |

**属性登记表**（必维护）：新属性第一次出现时登记 `属性名 / 类型 / 首现 content_id / 说明`。

### 2.3 claim 关系字段

`relations` 必填（可为空数组但必须显式写出）。11 种合法关系类型，统一正向语义：

| 关系类型 | 语义 | 关系类型 | 语义 |
|---|---|---|---|
| supports | 支撑 | responds_to | 回应 |
| exemplified_by | 被例证 | parallel | 并列 |
| extends | 引申 | implies | 推出 |
| deepens | 深化 | precondition | 前提 |
| tension_with | 张力 | part_of | 属于 |
| echoes | 呼应 | | |

**三条硬约束**：禁止自指；禁止悬空（target 必须存在）；禁止冗余反向边。

### 2.4 实体 ID 命名硬规则

违反任一条，`podcast-kg verify` 会报出来（它只报告，不会非零退出，报告要自己读）。

1. **格式**：全小写，仅 `a-z0-9-`，连字符分隔。禁止中文、空格、下划线、大写。
2. **禁止前后缀**：不得带类型标记。
   - ❌ `pi-agent` / `book-zhineng` / `jeff-dean-papers`
   - ✅ `pi` / `intelligence-book` / `jeff-dean`
3. **一 id 一实体**：不得把两个不同对象拼成一个 id。
   - ❌ `openclaw-opencode`（name 却是 OpenCode）
   - ✅ 拆成 `openclaw` + `opencode`
4. **取「最通用可识别名」**：优先公司/产品官方英文名；官方名为中文则用拼音+品类。
   - ✅ `doubao`（豆包）、`kimi`、`openai`、`claude-code`
   - 中文名一律写入 `aliases`
5. **版本/型号不入 id**：`gpt-4` 与 `gpt-4o` 归为 `gpt-4` 系列时，型号写入 `context`；确为独立产品才单列。
6. **同一对象跨卡必须同 id**：抽取前先查 `.outputs/registry/entities.json`，命中即复用。

### 2.5 实体 / 概念分界

| 判定 | 归入 | 例 |
|---|---|---|
| 可指认的**具体对象**：公司、产品、书、论文 | `entities` | OpenAI、Orca、Codex、《智能》、Quoc Le |
| **通用类目/方法论/框架/隐喻** | `extensions.concepts` | Agent Harness、木桶理论、德鲁克三革命、织布机类比 |
| **实体 + 类目混写** | 拆分 | `Netscape/浏览器` → entity `netscape` + concept `browser` |

判定口诀：**「能不能指着一个具体的东西说『就是它』」**。能→实体；不能→概念。

### 2.6 人物 / 实体边界

- `people` 只放**节目中出场的人**（发言或明确被介绍），`role` 三选一必填：`host` / `guest` / `mentioned`。
- 人名**禁止**出现在 `entities`。若某人是"被讨论的对象"而非"在场者"（如讨论某公司 CEO 的战略），仍进 `people`，`role: mentioned`。
- `person_id` 按 §2.4 的 slug 规则：`名-姓` 拼音（`liang-wenfeng`），不带角色后缀。
- 同一人在不同卡角色不同（A 卡 guest、B 卡 mentioned），仍是同一个 `person_id`。

---

## 三、抽取流程（七步）

```
S0 装载注册表 —— 读取 .outputs/registry/entities.json 与 .outputs/registry/people.json
                （不存在则以空表启动，本次抽出的 id 在 S7 入库）

S1 元数据填充 —— source 区机械填入，不理解内容
S2 人物识别   —— 区分 host/guest/mentioned；guest 身份交叉验证；说话者强制校验（§四）
S3 实体收集   —— 查注册表复用；未命中的暂标 new:true；同时判别「实体 vs 概念」（§2.5）
S4 观点抽取   —— 逐段抽 claim，必带 timestamp+end+speaker+relations
S5 动态属性   —— 特有维度归 extensions；概念归 extensions.concepts；登记属性表
S6 质检回链   —— 抽查 3 条 claim 对音频原文核验（最早/中位/end 边界）
S7 跨卡归一   —— a) 运行 `podcast-kg verify` 扫全部卡
                b) 处理 A 类 id 冲突 / B 类疑似同一 / C 类新实体
                c) 人工确认后回写 registry，再回填各卡 id
                d) 重跑校验至零冲突
```

S7 只做「横向比对」：前六步都是单卡视角，看不到跨卡的 id 漂移，必须独立成步兜住。

---

## 四、强制校验

### 4.1 说话者校验（S2 / S4）

whisper 无说话人分离，speaker 标注必须交叉验证：

1. **上下文轮转**：host/guest 应交替；代词立场（"我们的产品" vs "你的产品"）是强信号；
2. **转场语交叉验证**："对，"、"没错" 多为接话方；提问句多为 host；自我纠正/举例多为发言方；
3. 两项冲突或无法确认 → 标 `confidence: 转述推断` 并回听；
4. host 复述 guest 观点时不改 speaker，加 note 说明。

**单人连续长段发言最容易误判，需特别检查。**

### 4.2 S6 质检回链

每卡定稿前抽查 3 条（最早 / 中位 / end 上限触发的一条）：核对 statement 语义、speaker 归属、end 边界话题切换。不合格即修并记入校验报告。

### 4.3 S7 跨卡校验

```bash
# 只传知识卡本身（不要带 *_transcript.json / *_graph.json）
podcast-kg verify .outputs/<id1>.json .outputs/<id2>.json
podcast-kg verify --build-registry .outputs/registry/entities.json .outputs/<id1>.json .outputs/<id2>.json
```

（其余开关见 `podcast-kg verify --help`。）

输出三类报告：

| 类别 | 含义 | 处理 |
|---|---|---|
| **A. id 冲突** | 同一名称在不同卡用了不同 id | 必改：统一为注册表中的 id |
| **B. 疑似同一** | 名称高度相似但 id 不同 | 人工确认是否真同一对象，合并 id |
| **C. 新实体** | 注册表中不存在的 id | 人工确认后写入注册表 |

脚本内置的自动检查：

- id 是否匹配 `^[a-z0-9][a-z0-9-]*$`
- id 是否含类型前后缀（`-agent`、`book-`、`-papers` 等）
- 同一 id 是否出现 name 不一致（拼实体嫌疑）
- 人名是否误入 entities
- `groups` 是否覆盖全部 claims（不漏不重）

### 4.4 转写专名校正表

whisper 对人名/产品名易错（clock→Claude、虎精→Orca、曾敏→曾鸣、Hardness→Harness）。建立 `transcript_corrections`：`{raw, corrected, where, note}`。引用原话一律用校正后写法；同系列下一期复用该表。

---

## 五、时间点回链机制

- `timestamp~end` 为回链区间，点击跳原音频起始点，播到 end 自动暂停；
- **end 规则**：
  1. 默认 = 下一条 claim 的 `timestamp`；
  2. 上限 `end - timestamp ≤ 300 秒`，超限在话题停顿处截断；
  3. 长案例/故事按转写**静音边界**（segment 间隔 > 2s）手动定 end；
  4. 最后一条 end ≤ 音频总时长；
  5. end 不得早于 timestamp，相邻区间不得重叠。
- shownotes 有章节先对齐章节再段内细定位；
- 图谱层：`timestamp/end` 作为 provenance 挂到音频 URI（Semantica PROV 适配）。

---

## 六、输出物

所有产物写到**当前工作目录**下的 `.outputs/`（显式传路径时以传入路径为准）：

```
.outputs/
├── <audio>_transcript.json / .txt
├── <content_id>.json / .md
├── <content_id>.html
├── <content_id>_graph.json
└── registry/
```

### 6.1 每条内容两个文件

1. `.outputs/<content_id>.md` —— 人类阅读版（元数据表、人物卡、实体表、按 groups 分组的 claims、专名纠正表、质检记录）；
2. `.outputs/<content_id>.json` —— 机器可读完整 schema。

### 6.2 三类全局文件

| 文件 | 作用 |
|---|---|
| `.outputs/registry/entities.json` | 实体唯一真源：id / name / aliases / type / cards |
| `.outputs/registry/people.json` | 人物唯一真源，含 role 记录 |
| `.outputs/registry/concepts.json` | 概念词表，用于 S3 判别实体 vs 概念 |

### 6.3 渲染

`podcast-kg render` —— 参数见 `podcast-kg render --help`；默认写 `.outputs/<card>.html`。HERON 同款版式：刊头 + 左侧主题导航 + 行式观点列表 + 底部播放条；移动端适配，点时间戳回链原声。

页面内可直接调推荐：右上「✎ 编辑推荐」→ 行尾 ☆ 增删、填推荐理由 → 「⤓ 生成编辑后的页面」导出 `<content_id>_picks.html`（浏览器下载目录）；或「⧉ 复制 JSON」把 `picks` 回填 `.outputs/<content_id>.json`，下次渲染自动带上。

---

## 七、质量红线

1. claim 不得无 speaker、无 timestamp、无 end；
2. relations 不得自指或悬空；
3. `groups` 必须覆盖全部 claim；
4. `entity_id` / `person_id` 必须符合 §2.4 slug 规则；
5. 人名不得出现在 entities；通用概念不得出现在 entities；
6. 不得编造时间戳，end 不得超出音频时长；
7. statement 超过 50 字视为未提炼，须重写。
