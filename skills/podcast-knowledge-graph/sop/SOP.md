# 内容结构化抽取 SOP

> 中文 | [English](SOP.en.md)

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

arcs:                         # 必填，阅读主视图（见 §2.7）
  - arc_id: a01               # a01…，同卡内唯一
    title: "从物理到脑科学：一条二十年的弯路"
    summary: "这一段在讲什么（2–3 句）"
    start: "01:14"             # 播放区间（含前后留白）
    end: "10:08"
    duration_sec: 534
    speech_sec: 500           # 纯发言时长
    open_question: "…"        # 主持人开启话题的问句（有则必填）
    open_line: "…"            # 该话题被开启时的转写原话
    points:                   # 2–4 条，按时间排序
      - { claim_id: c01, at: "02:43", end: "03:22", statement: "…", speaker: "…" }
    beats:                    # 3–6 个回合
      - { at: "02:43", end: "03:30", speaker: "noah-shinn", gist: "…", claims: [c01] }
    evidence: [c01, c02, c03] # 这一段覆盖的全部 claim（折叠展示）
    context: [{ arc_id: a03, why: "…" }]  # 要听懂它，前面哪段已铺垫
    arc_relations: [{ target: a05, type: supports, count: 2 }]

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

### 2.7 话题弧 `arcs`（阅读单位，必填）

**为什么必须有这一层**：逐句 claim 是索引，不是阅读单位。实测 60–75% 的相邻 claim
间隔 ≤2 秒，它们本来是同一段话被切开的；而抽 claim 又天然只留“主张”，把**主持人
开启话题的那个问题**过滤掉了——读者于是既没开头也没语境，只能连点好几次才滋出上下文。

**定义**：一条弧 = 主持人开启一个话题 → 嘉宾展开 → 该话题自然收束。
弧内应该是“提问 → 回应 → 追问 → 收束”，而不是平铺的观点列表。

| 字段 | 必需 | 约束 |
|---|---|---|
| `arc_id` | ✓ | `a01` 起递推，同卡唯一 |
| `title` | ✓ | 一个判断或一问，不要半句话；自动标题只能兜底 |
| `summary` | ✓ | 2–3 句，告诉读者“为什么值得完整听这一段” |
| `start` / `end` | ✓ | 播放区间；**相邻弧不得重叠**；>60 分钟用 `h:mm:ss`；有词级时间戳时带小数秒（`1:04:18.72`），保证切在词边界上 |
| `duration_sec` | ✓ | `end - start`；`speech_sec` 另记纯发言时长 |
| `open_question` | 有则必填 | 主持人的问句原话（能分出说话人时） |
| `open_line` | 建议 | 弧起点处的转写原话；whisper 不做说话人分离，不得冒充归属 |
| `points` | ✓ | **2–4 条**，按时间排序；代表点按被引用度 + 类型权重挑 |
| `beats` | ✓ | 3–6 个回合，每回合一句话，不逐句搬 |
| `evidence` | ✓ | 该弧覆盖的全部 claim_id；**全弧合起来必须 100% 覆盖 claims** |
| `context` | 可选 | 跨弧依赖：要听懂这段，前面哪段已铺垫 |
| `arc_relations` | 可选 | 弧与弧之间的关系；**弧内部不再连句子** |

**切分硬规则**（按可靠性排序，只认这四类边界）：

1. **停顿 ≥ 20s**（强边界）——真实话题切换几乎都伴随数秒以上沉默；
2. **主题分组切换**（`groups` 边界）；
3. **主持人重新提问**（guest → host 的发言轮转）；
4. **停顿 ≥ 8s**（弱边界）。

**人工切点（兜底）**：主持人夹在一段话中间转场（“节目最后我想问一个点”），
两侧既没停顿也没换分组时，四类信号全部失效，必须在精修稿里指定：

```json
{ "<content_id>": { "_breaks": [{ "before": "c69", "at": "1:04:18" }] } }
```

`at` 可选，缺省取两侧 claim 的中点。语义：切点之前的 claim 归上一段、之后的归下一段；
`at` 就是上一段的 `end`、下一段的 `start`（不再叠 PAD，不重叠）；
切完任一侧不足 60 秒则忽略。任何自动合并都不会跨过人工切点。

时长约束：目标 **3–10 分钟**；低于下限并进邻段，高于上限在最长停顿处再切。
卡本身很粗（claim 中位 >80s）时，下限提到 5 分钟、上限提到 13 分钟，否则一段只剩两条卡。

禁止事项：

- 不按句子数切、不按固定条数切；
- 不跨主题分组盲目合并（跨组只在 <60s 时才允许）；
- 一个弧里少于 2 条 claim（除非卡本身极稀）；
- 弧首尾不留白——起点前留 10s、终点后留 6s，再按中点切开以免重叠；
- 切点落在词中间——`0.3s` 的偏移就够让开场少半个词。用 `transcribe --words` 的词级时间戳对齐，
  切点落在词内部时挪到该词较近的一端（词要么整条留下、要么整条留给下一段）。

---

## 三、抽取流程（八步）

```
S0 装载注册表 —— 读取 .outputs/registry/entities.json 与 .outputs/registry/people.json
                （不存在则以空表启动，本次抽出的 id 在 S7 入库）

S1 元数据填充 —— source 区机械填入，不理解内容
S2 人物识别   —— 区分 host/guest/mentioned；guest 身份交叉验证；说话者强制校验（§四）
S3 实体收集   —— 查注册表复用；未命中的暂标 new:true；同时判别「实体 vs 概念」（§2.5）
S4 观点抽取   —— 逐段抽 claim，必带 timestamp+end+speaker+relations
S4.5 分话题弧 —— 按 §2.7 聚成 arcs；补 title/summary；校验 evidence 全覆盖、区间不重叠
S5 动态属性   —— 特有维度归 extensions；概念归 extensions.concepts；登记属性表
S6 质检回链   —— 抽查 3 条 claim（最早/中位/end）+ 3 段弧（最早/中位/最长）对音频核验
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

再加**弧体检**（这层最容易看起来对、实际不能听）：

| 检查 | 判据 | 不过怎么办 |
|---|---|---|
| 全覆盖 | `arcs[].evidence` 去重后 == 全部 claim_id | 找回漏掉的 claim 或补弧 |
| 不重叠 | 相邻弧 `end ≤ 下一弧 start` | 在停顿中点切开 |
| 不碎 | 无 `< 60s` 的弧，中位落在 3–10 分钟 | 并进邻段 |
| 有上下文 | 每弧有 `open_question` 或 `open_line` | 回听弧起点前 15 秒 |
| 能立住 | 抽查 3 段（最早/中位/最长）连续听完，不看文字也能听懂 | 边界没切对，重切 |

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

弧层与 claim 层两套区间，同一份音频：

- **claim 回链**（细）：点一句话跳过去，给引用与图谱溯源用；
- **arc 回链**（粗）：点一下**连续播完整段**，播到 `end` 自动停——这是读者的默认交互。

弧区间规则：

1. `start` = 首条 claim 起点 − 10s，但不能早于上一弧的中点；
2. `end` = 末条 claim 终点 + 6s，但不能晚于下一弧的中点；
3. **相邻弧区间永不重叠**，否则连播会听到重复的十几秒；
4. 超过 60 分钟的节目用 `h:mm:ss`，不要写成 `66:21`（前端自己切 `:` 会算错）；
5. 广告段、预告片不进弧，记入 `extensions.ad_blocks`。


- `timestamp~end` 为回链区间，点击跳原音频起始点，播到 end 自动暂停；
- **end 规则**：
  1. 默认 = 下一条 claim 的 `timestamp`；
  2. 上限 `end - timestamp ≤ 300 秒`，超限在话题停顿处截断；
  3. 长案例/故事按转写**静音边界**（segment 间隔 > 2s）手动定 end；
  4. 最后一条 end ≤ 音频总时长；
  5. end 不得早于 timestamp，相邻区间不得重叠。
- shownotes 有章节先对齐章节再段内细定位；
- 图谱层：`timestamp/end` 作为 provenance 写进 `*_graph.json` 的 `provenance[]`（音频 URI + 秒级区间）。

---

## 六、输出物

所有产物写到**当前工作目录**下的 `.outputs/`（显式传路径时以传入路径为准）：

```
.outputs/
├── <audio>_transcript.json / .txt
├── <content_id>.json / .md          母语知识卡（含 arcs）
├── <content_id>.<lang>.json         译文卡（结构一致，只换文字；见 §7）
├── <content_id>_arcs.json           话题弧层（给产品端）
├── <content_id>.html                单文件页：多语言时右上角切换
├── <content_id>_arcs.html           话题弧页（本地验收：点一次连播一整段）
├── <content_id>_graph.json
└── registry/
```

> 双语是一等输出：`<content_id>.json`（中文）+ `<content_id>.en.json`（英文）+ **一份** `<content_id>.html`。
> 网页里切语言，音频始终是原始音源。

弧的精修标题/导语是**人工资产**，单独存一份 `<content_id> 或全局>_curated.json`（`content_id → arc_id → {title, summary}`），
因为切分可重算、好标题不可重算。回传时它必须跟着卡一起走，否则产品端只剩自动标题。

### 6.1 每条内容的文件

1. `.outputs/<content_id>.md` —— 人类阅读版（元数据表、人物卡、实体表、按 groups 分组的 claims、专名纠正表、质检记录）；
2. `.outputs/<content_id>.json` —— 母语完整 schema（唯一真源）；
3. `.outputs/<content_id>.<lang>.json` —— 译文卡，结构逐字对齐（§7），缺了它 `--i18n` 无可用输入。

### 6.2 三类全局文件

| 文件 | 作用 |
|---|---|
| `.outputs/registry/entities.json` | 实体唯一真源：id / name / aliases / type / cards |
| `.outputs/registry/people.json` | 人物唯一真源，含 role 记录 |
| `.outputs/registry/concepts.json` | 概念词表，用于 S3 判别实体 vs 概念 |

### 6.3 渲染

`podcast-kg render` —— 参数见 `podcast-kg render --help`；默认写 `.outputs/<card>.html`。

页面与 [heronai.top](https://heronai.top) 详情页是**同一套 DOM 与样式**（`assets/heron.css` 就是站点样式，字体子集内联）：
顶栏 → 卡片头（平台/日期、标题、人物、段数·观点数·原节目）→ 工具条 → 左侧主题导航 + 右侧话题弧 → 评论区 → 播浮层。

* **阅读单位是话题弧**：卡里有 `arcs`（或用 `--arcs`、或旁挂 `<card>_arcs.json`）时，每组下渲染 `av-arc` 卡片，
  展开后是「主持人开场原话 → beats → 金句 → 其余观点」；没有 `arcs` 就退回逐句视图。
* **推荐**：★ 存在浏览器 localStorage；「我的推荐」过滤、「分享我的视图」复制 `#picks=…` 链接、
  「导出 picks」下载 `picks_<id>.json` 回填卡片。
* **多语言**：`--i18n en=<id>.en.json` 把译文并入同一份 DOM，顶栏出现「中文 / EN」切换；
  DOM、id、深链、播放器只有一份，切换只改文字（含按钮、提示、目录、时间条）。
* 站点样式更新后重跑 `python scripts/refresh_heron_css.py`（见 `src/podcast_kg/assets/README.md`）。

---

## 七、双语输出（中英）

**音频不变**：不配音、不换源、不重切时间轴；变的只有文字。

### 7.1 硬规则

1. 母卡用 `source.language` 声明语言（缺省按 `zh`）；两份卡共享同一个 `content_id`、
   全部 `claim_id` / `arc_id` / `gid` / `person_id` / `entity_id`，`groups[].ids` 顺序也一致；
2. 每条 claim 的 `timestamp` / `end` / `speaker` 逐字一致；每条弧的 `start` / `end` / `duration_sec` 一致；
3. 只翻译文字字段（见 7.2），结构字段（ids、时间戳、关系目标、颜色/排序）一律照抄；
4. 译文写成独立文件 `<content_id>.<lang>.json`，**不要**改母卡；
5. 只出一份 HTML，用 `--i18n` 合并，右上角切语言；不要生成两个 HTML。

### 7.2 可翻译字段（其余不要动）

| 层 | 字段 |
| --- | --- |
| 卡 | `source.title`、`source.series`、`groups[].name` |
| 人物 | `people[].role`、`people[].identity`（`name` 是专名，保留原文） |
| 观点 | `claims[].statement`、`claims[].evidence`、`claims[].relations[].note` |
| 话题弧 | `arcs[].title`、`arcs[].summary`、`arcs[].open_question`、`arcs[].open_line`、`arcs[].points[].statement`、`arcs[].beats[].gist` |

### 7.3 流程

```bash
# 1) 生成译文骨架：id / 时间戳 / 分组原样保留，文字留空
podcast-kg i18n scaffold .outputs/<id>.json --lang en

# 2) 逐条填 <id>.en.json 里的字段（只填 7.2 列出的）
#    - 专名保留：Claude Code / Orca / ADE / harness 不硬翻，首次出现可加中文括注
#    - 引语（open_line / evidence）译意，不要冒充逐字引文
#    - statement 仍要 ≤50 字（英文 ≤ 25 words）

# 3) 结构对齐体检：硬错退出码 1；「未翻译」是警告
podcast-kg i18n check .outputs/<id>.json .outputs/<id>.en.json

# 4) 出单文件双语页（音频不变，右上角切换）
podcast-kg render .outputs/<id>.json .outputs/<id>.html   --i18n en=.outputs/<id>.en.json --default-lang zh
```

### 7.4 双语质量闸门

- [ ] `i18n check` 0 错误；警告只剩「专名/引语有意保留」的项
- [ ] 抽查 3 条 claim：中英 `timestamp` 相同，语义一致、没有漏译限定词（“可能/约/据称”）
- [ ] 弧的 `title` / `summary` 两种语言都能独立读通，不是逐字直译
- [ ] HTML 里切到 EN 后：按钮、提示、时间条、目录全部英文，且深链 `#claim-c21` 仍能定位
- [ ] 音频只播原始音源（不出现译文配音）

---

## 八、质量红线

1. claim 不得无 speaker、无 timestamp、无 end；
2. relations 不得自指或悬空；
3. `groups` 必须覆盖全部 claim；
4. `entity_id` / `person_id` 必须符合 §2.4 slug 规则；
5. 人名不得出现在 entities；通用概念不得出现在 entities；
6. 不得编造时间戳，end 不得超出音频时长；
7. statement 超过 50 字视为未提炼，须重写；
8. `arcs[].evidence` 合起来必须覆盖全部 claim，禁止孤儿 claim；
9. 相邻弧播放区间不得重叠，也不得出现 <60 秒的碎弧；
10. 弧的 `title` 不得是 statement 的前 N 个字（宁可写一句人话）；
11. `open_line` 是转写原话，不得改写、不得冒充说话人归属。
