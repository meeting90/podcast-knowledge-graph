# 内容结构化抽取 SOP（v0.3）

> 适用对象：播客 / 长视频 / 深度访谈的知识抽取，产出「知识卡」（JSON + Markdown），可直接渲染为可折叠思维导图并注入知识图谱。
> v0.3 核心变更：**引入全局实体注册表，把「实体归一」从各卡各自为政升级为跨卡共享的一等公民。**

---

## 变更记录

### v0.2 → v0.3（基于 3 张卡实测暴露的问题）

三张实测卡（对话319 / ep153曾鸣 / MCtalk李超，共 41 个 id）跨卡校验结果：**id 冲突 0 个、真实共用 4 个**（codex、claude-code、manus、doubao）。冲突为零是运气而非机制——因为恰好都是常见英文名直译。同时暴露 5 类系统性问题：

| # | 问题 | 实测案例 | v0.3 对策 |
|---|---|---|---|
| ① | **id 命名无统一风格** | `pi-agent`（带类型后缀）、`book-zhineng`（拼音+类型前缀）、`jeff-dean-papers`（人名+类型） | §2.4 命名硬规则：纯 slug，禁前后缀 |
| ② | **两个实体被拼成一个 id** | `openclaw-opencode`，name 却是 "OpenCode" | §2.4 规则 3 + §四 校验脚本拦截 |
| ③ | **通用概念被当成实体** | `Agent Harness`、`德鲁克三革命框架`、`Jeff Dean / Quoc Le 论文路径` | §2.5 实体/概念分界；概念移入 `extensions.concepts` |
| ④ | **混合表述** | `Netscape/浏览器`（实体 + 类目混写） | §2.5 规则：拆成 `netscape` + concept `browser` |
| ⑤ | **人名混入实体表** | `jin-jing` 出现在 entities | §2.6 人物/实体边界；校验脚本自动检测 |

同时新增 **S7 跨卡归一环节** 与 **`verify_cards.py` 后置校验**，把「抽取各自独立」改为「抽取前查表、抽取后回写」。

---

## 一、抽取对象与输入

（沿用 v0.2）

输入三件套：

1. **音频/视频**（有直链则优先，用于时间点回链与质检）；
2. **转写稿**（本地 whisper，带 segment 时间戳）；
3. **节目元数据**：标题、shownotes、嘉宾介绍、章节大纲（如有）。

> 发现层独立于本 SOP：Apple Podcasts ID → RSS `feedUrl` → 时长初筛 → 下载。工具见 `heron/scripts/fetch_feed.py`。

---

## 二、Schema 设计

### 2.1 固定核心字段

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

groups:                       # 【v0.3 必填】思维导图的一级主题分组
  - gid: g1
    name: "① 产品与工程"
    ids: [c01, c02, ...]      # 必须覆盖全部 claim_id，不重不漏

# ── 人物层 ──
people:
  - person_id: string         # 全局 slug（见 §2.6）
    name: string
    aliases: string[]         # 【v0.3】别名/英文名/昵称
    role: enum                # host / guest / mentioned（必填）
    identity: string
    org: string[]
    links: url[]
    first_appeared_in: content_id

# ── 实体层 ──
entities:
  - entity_id: string         # 全局 slug（见 §2.4）
    type: enum                # company / product / book / paper / person(非发言人)
    name: string
    aliases: string[]         # 【v0.3】中文名/旧名/别称
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
  concepts:                   # 【v0.3 新增】通用概念/方法论/框架，不放 entities
    - {name: "Agent Harness", note: "作为一类工具的统称", ref_claims: [c02]}
  ...                         # 其他业务属性（见 §2.2）

transcript_corrections:       # 专名纠正表（沿用 v0.2）
```

### 2.2 动态扩展字段

原则不变：核心字段固定，业务属性开放，新属性必须登记。

| 属性名 | 类型 | 说明 |
|---|---|---|
| `concepts` | list[{name, note, ref_claims}] | **v0.3 新增**，通用概念/框架 |
| `contrarian_views` | list[{claim_ref, why_contrarian}] | 反共识观点 |
| `costs` / `opportunities` / `action_items` | list | 按需 |

**属性登记表**（必维护）：新属性第一次出现时登记 `属性名 / 类型 / 首现 content_id / 说明`。

### 2.3 claim 关系字段

`relations` 必填（可为空数组但必须显式写出）。**11 种合法关系类型**，统一正向语义：

| 关系类型 | 语义 | 关系类型 | 语义 |
|---|---|---|---|
| supports | 支撑 | responds_to | 回应 |
| exemplified_by | 被例证 | parallel | 并列 |
| extends | 引申 | implies | 推出 |
| deepens | 深化 | precondition | 前提 |
| tension_with | 张力 | part_of | 属于 |
| echoes | 呼应 | | |

**三条硬约束**：禁止自指；禁止悬空（target 必须存在）；禁止冗余反向边。

### 2.4 实体 ID 命名硬规则【v0.3 新增】

> 这是 v0.3 最重要的约束。违反任一条，`verify_cards.py` 直接报错。

1. **格式**：全小写，仅 `a-z0-9-`，连字符分隔。**禁止**中文、空格、下划线、大写。
2. **禁止前后缀**：不得带类型标记。
   - ❌ `pi-agent` / `book-zhineng` / `jeff-dean-papers`
   - ✅ `pi` / `intelligence-book` / `jeff-dean`
3. **一 id 一实体**：不得把两个不同对象拼成一个 id。
   - ❌ `openclaw-opencode`（name 却是 OpenCode）
   - ✅ 拆成 `openclaw` + `opencode`
4. **命名取「最通用可识别名」**：优先公司/产品官方英文名；官方名为中文则用拼音+品类。
   - ✅ `doubao`（豆包）、`kimi`、`openai`、`claude-code`
   - 中文名一律写入 `aliases`
5. **版本/型号不入 id**：`gpt-4` 与 `gpt-4o` 归为 `gpt-4` 系列时，型号写入 `context`；确为独立产品才单列。
6. **同一对象跨卡必须同 id**：抽取前先查 `heron/registry/entities.json`，命中即复用。

### 2.5 实体 / 概念分界【v0.3 新增】

| 判定 | 归入 | 例 |
|---|---|---|
| 可指认的**具体对象**：公司、产品、书、论文、非发言人个人 | `entities` | OpenAI、Orca、Codex、《智能》、Quoc Le |
| **通用类目/方法论/框架/隐喻** | `extensions.concepts` | Agent Harness、木桶理论、德鲁克三革命、织布机类比 |
| **实体 + 类目混写** | 拆分 | `Netscape/浏览器` → entity `netscape` + concept `browser` |

判定口诀：**「能不能指着一个具体的东西说『就是它』」**。能→实体；不能→概念。

### 2.6 人物 / 实体边界【v0.3 新增】

- `people` 只放**节目中出场的人**（发言或明确被介绍），`role` 三选一必填：`host` / `guest` / `mentioned`。
- 人名**禁止**出现在 `entities`。若某人是"被讨论的对象"而非"在场者"（如讨论某公司 CEO 的战略），仍进 `people`，`role: mentioned`。
- `person_id` 沿用 §2.4 的 slug 规则：`名-姓` 拼音（`liang-wenfeng`），不带角色后缀。
- 同一人在不同卡角色不同（A 卡 guest、B 卡 mentioned），**仍是同一个 `person_id`**。

---

## 三、抽取流程（七步）【v0.3 由六步扩为七步】

```
S0 装载注册表 —— 读取 heron/registry/entities.json 与 registry/people.json
                （不存在则以空表启动，本次抽出的 id 将在 S7 入库）

S1 元数据填充 —— source 区机械填入，不理解内容
S2 人物识别   —— 区分 host/guest/mentioned；guest 身份交叉验证；说话者强制校验（§四）
S3 实体收集   —— 查注册表复用；未命中的暂标 new:true；同时判别「实体 vs 概念」（§2.5）
S4 观点抽取   —— 逐段抽 claim，必带 timestamp+end+speaker+relations
S5 动态属性   —— 特有维度归 extensions；概念归 extensions.concepts；登记属性表
S6 质检回链   —— 抽查 3 条 claim 对音频原文核验（最早/中位/end 边界）
S7 跨卡归一   —— 【v0.3 新增，必做】
                 a) 运行 verify_cards.py 扫全部卡
                 b) 处理 A 类 id 冲突 / B 类疑似同一 / C 类新实体
                 c) 人工确认后回写 registry，再回填各卡 id
                 d) 重跑校验至零冲突
```

**S7 为什么必须独立成步**：前六步都以"单卡视角"运行，天然看不到跨卡的 id 漂移。三卡实测已证明，即使抽取质量不错，id 层面仍会出现 `pi-agent` 这类不规范命名——必须有一个只做"横向比对"的环节兜住。

---

## 四、强制校验细则

### 4.1 说话者校验（S2/S4）

whisper 无说话人分离，speaker 标注必须交叉验证：

1. **上下文轮转**：host/guest 应交替；代词立场（"我们的产品" vs "你的产品"）是强信号；
2. **转场语交叉验证**："对，"、"没错" 多为接话方；提问句多为 host；自我纠正/举例多为发言方；
3. 两项冲突或无法确认 → 标 `confidence: 转述推断` 并回听；
4. host 复述 guest 观点时不改 speaker，加 note 说明。

> 实测教训（v0.2 沿用）：对话319 的 c17 曾被误标为嘉宾，实际是主持人发言（"我经常跟人说…"），靠上下文轮转 + 转场语才纠正。**单人连续长段发言最容易误判，需特别检查。**

### 4.2 S6 质检回链

每卡定稿前抽查 3 条（最早 / 中位 / end 上限触发的一条）：核对 statement 语义、speaker 归属、end 边界话题切换。不合格即修并记入校验报告。

### 4.3 S7 跨卡校验【v0.3 新增】

`python heron/scripts/verify_cards.py card1.json card2.json ...` 输出三类报告：

| 类别 | 含义 | 处理 |
|---|---|---|
| **A. id 冲突** | 同一名称在不同卡用了不同 id | 必改：统一为注册表中的 id |
| **B. 跨卡共用** | 已正确对上的实体 | 人工确认是否真同一对象 |
| **C. 新实体** | 注册表中不存在的 id | 人工确认后写入注册表 |

附加自动检查（脚本内置，v0.3.1 落地）：
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

### 6.1 每条内容两个文件

1. `<content_id>.md` —— 人类阅读版（元数据表、人物卡、实体表、按 groups 分组的 claims、专名纠正表、质检记录）；
2. `<content_id>.json` —— 机器可读完整 schema。

### 6.2 三类全局文件【v0.3 新增】

| 文件 | 作用 |
|---|---|
| `heron/registry/entities.json` | 实体唯一真源：id / name / aliases / type / cards |
| `heron/registry/people.json` | 人物唯一真源，含 role 历史 |
| `heron/registry/concepts.json` | 概念词表，用于 S3 判别实体 vs 概念 |

### 6.3 渲染

`render_card.py <card.json> <out.html>` —— 纵向可折叠思维导图，移动端适配，点击跳音频。

---

## 七、质量红线

1. claim 不得无 speaker、无 timestamp、无 end；
2. relations 不得自指或悬空；
3. `groups` 必须覆盖全部 claim（v0.3 新增）；
4. `entity_id` / `person_id` 必须符合 §2.4 slug 规则（v0.3 新增）；
5. 人名不得出现在 entities；通用概念不得出现在 entities（v0.3 新增）；
6. 不得编造时间戳，end 不得超出音频时长；
7. statement 超过 50 字视为未提炼，须重写。

---

## 八、试运行样例记录

| 卡 | claims | 关系 | 主题组 | 备注 |
|---|---|---|---|---|
| 对话319（津晶/Orca） | 33 | 44 | 5 | v0.2 首个样例 |
| ep153（曾鸣/产业史观） | 33 | 23 | 6 | 首次全流程自动化 |
| MCtalk（李超/AI落地） | 30 | 15 | 6 | 首次暴露跨卡实体问题 |

**v0.3 待办**：按 §2.4 重命名三卡实体 id，建立注册表，重跑 S7 至零冲突。
