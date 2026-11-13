# podcast-knowledge-graph

**中文** | [English](README.en.md)

> **在线版：[heronai.top](https://heronai.top)** —— HERON 把这条流水线的产物直接跑成了产品：口语内容的知识图谱，每个观点都能回溯到它被说出的那一秒。

一个 **agent 无关的 skill + Python CLI**：同一份 skill 可以装进 Pi、Claude Code、Codex、Cursor、Gemini CLI、OpenCode、Copilot，或任何读 `AGENTS.md` 的 agent，把播客 / 长视频 / 深度访谈抽成**可溯源的知识卡**（JSON + Markdown），渲染成 [HERON](https://heronai.top) 同款的观点页（可折叠、点时间戳回链原声），或写入知识图谱。

- **Agent Skills 目录**（`skills/podcast-knowledge-graph/`）：就是 `SKILL.md` + `sop/` + `examples/`，不依赖任何 agent 私有格式——`podcast-kg install-skill` 负责复制到各家的 skills 目录；
- **Python 包**（`src/podcast_kg`）：真正干活的 CLI——转写、校验、渲染、入库，以及安装 skill；
- **Pi extension**（`.pi/extensions/podcast-kg.ts`，可选）：薄桥接层，负责准备 Python 环境、把 `podcast-kg` 放进 PATH、追加 system prompt、注册 skill。只有 Pi 需要它。

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

### 方式 A：用 skills.sh 的 `npx skills` 安装（推荐，任意 agent）

仓库本来就是它要的结构（`skills/<name>/SKILL.md`），不用额外打包：

```bash
npx skills add meeting90/podcast-knowledge-graph -l                    # 先看仓库里有哪些 skill
npx skills add meeting90/podcast-knowledge-graph --agent claude-code -y     # 装到 Claude（默认符号链接）
npx skills add meeting90/podcast-knowledge-graph --agent '*'          # 所有 agent（含未安装的）
```

`--agent` 取 skills.sh 支持的 agent id（`claude-code`、`codex`、`cursor`、`gemini-cli`、`opencode`、`pi`、`github-copilot` …），
`--agent '*'` 装到所有 agent（`--all` 等价于 `--skill '*' --agent '*' -y`）；不在列表里的 agent 用 **`--agent universal`**（落到 `.agents/skills/`，
和本仓库 `install-skill --target agents` 是同一个位置）。`npx skills add … -l` 可以先看仓库里有哪些 skill。

`npx skills` 只把文件链接/复制进 agent 目录，**不会执行任何安装脚本**——Agent Skills 规范没有
postinstall 钩子，也不会帮你预装 CLI。但**用户不需要手动跑 uv/pip**：装完后第一条命令走 skill 自带的启动器，
它会先装运行时再执行（机器上只要有 `uv` 或 Python ≥3.10；两者都没有时它会打印装 uv 的命令）：

```bash
python3 <skills-dir>/podcast-knowledge-graph/bin/podcast-kg.py doctor
```

### 方式 B：作为 Pi extension 安装（只有 Pi 需要）

```bash
pi install git:github.com/meeting90/podcast-knowledge-graph
# 只给当前项目： pi install -l git:github.com/meeting90/podcast-knowledge-graph
```

Pi 会加载两个资源：


| 资源                                | 作用                                                                                                     |
| --------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `.pi/extensions/podcast-kg.ts`    | 首次会话时自动创建私有 venv 并装齐依赖（`podcast-kg[all]`），把 `podcast-kg` 放进 PATH，追加 system prompt，并注册 `/podcast-kg` 命令 |
| `skills/podcast-knowledge-graph/` | skill 本体：`SKILL.md`、`sop/SOP.md`、`examples/`                                                           |


依赖是**随扩展装好**的：第一次启动 Pi 时会一次性装到 `~/.pi/agent/cache/podcast-kg/venv`（含 `faster-whisper`），之后启动不再重复。检查：

```text
/podcast-kg doctor        # 或在 bash 里 podcast-kg doctor
```

本仓库自己也是可直接跑的 Pi 项目：

```bash
cd podcast-knowledge-graph && pi        # 首次会问是否信任（要加载 .pi/extensions）
```

### 方式 C：只装 CLI（想预装运行时 / 离线时）

> 走 `npx skills` 的话**可以跳过这一节**：skill 第一次被调用时会自己装运行时。
> 这里的 `install-skill` 与 npx 的区别是：它除了复制 skill，还会在该 agent 的指令文件里写一段指针块
> （`AGENTS.md` / `CLAUDE.md` / …），对不扫描 skills 目录的 agent 更稳。

`uv` / `pip` 并不认识本仓库：它们把 `podcast-kg` 当成 **PyPI 上的发行名**（等价写法 `podcast_kg`），
去默认索引 `https://pypi.org/simple` 查；`[all]` 是包元数据里的 **extra**（`Provides-Extra: all`），
不是另一个包。名字查不到就会报 `No solution found … no versions of podcast-kg[all]`。
`@ git+…` 或本地路径是 **direct reference**，绕过索引，包名只用来校验构建出来的项目名。
装好后 `uv tool list` 能看到，卸载用 `uv tool uninstall podcast-kg`。



```bash
# 现在（PyPI 尚未发布）：从 git 或本地源码装，direct reference 不需要索引
uv tool install "podcast-kg[all] @ git+https://github.com/meeting90/podcast-knowledge-graph"
# 在仓库根目录也可以：uv tool install ".[all]"

# PyPI 发布之后才能只写包名：
# uv tool install "podcast-kg[all]"   # 或 pipx / pip install "podcast-kg[all]"
podcast-kg doctor

podcast-kg install-skill --list                    # 支持哪些 agent、各自装到哪
podcast-kg install-skill --target pi               # ~/.pi/agent/skills
podcast-kg install-skill --target claude           # ~/.claude/skills
podcast-kg install-skill --target codex            # ~/.codex/skills + AGENTS.md
podcast-kg install-skill --target all --dry-run    # 先看要写哪些文件
```


| 目标         | 用户级 skills                   | 项目级 skills（`--scope project`） | 指针文件                              |
| ---------- | ---------------------------- | ----------------------------- | --------------------------------- |
| `pi`       | `~/.pi/agent/skills/`        | `.pi/skills/`                 | `APPEND_SYSTEM.md`（Pi 专用，`.pi/` 下） |
| `claude`   | `~/.claude/skills/`          | `.claude/skills/`             | `CLAUDE.md`                       |
| `codex`    | `~/.codex/skills/`           | `.codex/skills/`              | `AGENTS.md`                       |
| `cursor`   | `~/.cursor/skills/`          | `.cursor/skills/`             | `AGENTS.md`                       |
| `gemini`   | `~/.gemini/skills/`          | `.gemini/skills/`             | `GEMINI.md`                       |
| `opencode` | `~/.config/opencode/skills/` | `.opencode/skills/`           | `AGENTS.md`                       |
| `copilot`  | —（无用户级）                      | `.github/skills/`             | `.github/copilot-instructions.md` |
| `agents`   | `~/.agents/skills/`          | `.agents/skills/`             | `AGENTS.md`                       |


不在表里的 agent 用两参数通用形态：

```bash
podcast-kg install-skill --skills-dir .my-agent/skills --instructions AGENTS.md
podcast-kg install-skill --skills-dir .my-agent/skills --no-pointer   # 只要文件
```

指针块的文字来自 skill 里的 `pointer.md`（agent 无关）；Pi 自己的 system prompt 段在 `.pi/APPEND_SYSTEM.md`，两者互不复用。

每次安装都会在该 agent 的指令文件里维护一段 `<!-- podcast-kg:start --> … <!-- podcast-kg:end -->` 的块
（指向已安装的 `SKILL.md`、`runtime.json` 与 `bin/bootstrap.py`），不动文件里的其他内容；
`podcast-kg uninstall-skill --target <agent>` 只移除自己的那部分（运行时 venv 保留，
要一并清掉就 `rm -rf "$PODCAST_KG_HOME"`）。

> 三种方式选一：Pi extension 与 `npx skills add --agent pi` 都会提供 skill，重复安装会出现同名 skill（Pi 保留先发现的并告警）。
> 装完在 Pi 里 `/reload`，其他 agent 直接新开会话即可。

> `podcast-kg setup` / `unsetup` 保留为旧写法，等价于 `install-skill --target pi` / `uninstall-skill --target pi`。

## 运行时保证：装完为什么能直接用

skill 只是文件，真正干活的是 `podcast-kg` CLI。安装路径不同，运行时从哪来也不同：


| 安装方式                                              | 运行时由谁准备                                                    | 装完能不能用 |
| ------------------------------------------------- | ---------------------------------------------------------- | ------ |
| Pi extension                                      | extension 首次会话自动建私有 venv（含 `faster-whisper`） | 能      |
| `podcast-kg install-skill`                        | CLI 已在；`transcribe` / `ingest` 首次调用自动装依赖                   | 能      |
| 文件被拷进来（marketplace / `npx skills add` / 手工 clone） | 用 `bin/podcast-kg.py`：首次调用自动装运行时 | 第一条命令就装好 |


```bash
python3 skills/podcast-knowledge-graph/bin/bootstrap.py            # 幂等；已就绪就秒回
python3 skills/podcast-knowledge-graph/bin/bootstrap.py --check    # 未就绪退出码 1
python3 skills/podcast-knowledge-graph/bin/bootstrap.py --json     # ready / cli / version / pinned / notes
podcast-kg install-skill --target claude --verify                  # 装完自检：文件 / pin / CLI
```

- **装到哪**：`$PODCAST_KG_HOME`（Windows `%LOCALAPPDATA%\podcast-kg`，macOS `~/Library/Application Support/podcast-kg`，
Linux `${XDG_DATA_HOME:-~/.local/share}/podcast-kg`），只在私有 venv 里，不动系统 Python；
shim 写 `$PODCAST_KG_HOME/bin`（存在时也写 `~/.local/bin`）。
- **装什么版本**：skill 目录里的 `runtime.json` 记录安装它的 CLI 版本（`install-skill` 写入），
bootstrap 就装 `podcast-kg[all]==<该版本>`；来源依次是「本地源码 → PyPI → git」，
PyPI 还没发布这个版本时自动从 git 装（需已装 git），所以 skill 被单独拷走也能自举。
- **没有 Python 也能起来**：优先用 `uv`，缺解释器时 `uv venv --python 3.12` 会自动下载；
连 uv 都没有则提示先装 uv（`curl -LsSf https://astral.sh/uv/install.sh | sh`）。
- **体积与网络**：`[all]` 首次安装要联网（faster-whisper + ctranslate2，数百 MB），
whisper 模型在首次 `transcribe` 时下载；只要 `render` / `verify` 就加 `--extras none`（纯标准库，离线可用）。
- **失败不失联**：bootstrap 退出码 0/1，`--json` 的 `notes` 带真实错误尾部；
两类环境变量 `PODCAST_KG_HOME`（安装位置）、`PODCAST_KG_BIN`（指定现成可执行文件）。

### 模型权重（whisper）为什么不内置

`small` 486 MB、`medium` 1.5 GB、`large-v3` 3.1 GB；PyPI 单文件上限 100 MB，git 仓库不适合放二进制，
skill 被 `npx skills add` / 插件市场复制时还会被整包搬走。所以内置的是**「认得本地权重」的能力**：

| 做法 | 命令 | 适用 |
| --- | --- | --- |
| 首次自动下载（默认） | 直接 `podcast-kg transcribe` | 能连 huggingface.co |
| 预取到私有目录，之后完全离线 | `podcast-kg models fetch --model small` | 一次联网换永久离线 |
| 共享盘 / U 盘 / 内网镜像 | `podcast-kg models fetch --model small --dir /srv/models`，再 `PODCAST_KG_MODEL_DIR=/srv/models` 或 `transcribe --model-dir /srv/models` | 多机复用、无外网 |
| 装运行时顺便装模型 | `podcast-kg bootstrap --models small` | 一条命令一步到位 |

```bash
podcast-kg models list                    # 体积 / 状态（本地模型、HF 缓存、未下载）/ 路径
podcast-kg models fetch --model small     # → $PODCAST_KG_HOME/models/small
podcast-kg models verify                  # 校验 config.json / model.bin / tokenizer.json / vocabulary
podcast-kg models path --model small      # 可用的本地路径（没有则退出码 1）
```

- 解析顺序：`--model` 指向的目录 → `--model-dir` / `PODCAST_KG_MODEL_DIR` 下的 `<name>` →
  `$PODCAST_KG_HOME/models/<name>` → HF 缓存 → 下载。
- `PODCAST_KG_OFFLINE=1`（或 `HF_HUB_OFFLINE=1`）时缺权重**直接报错**，不会静默联网等 130 秒超时。
- `models fetch` 产出的目录可直接拷贝分发（HF 的符号链接会落成真实文件，`.cache` 会被清掉）；
  随包分发请走发布物/共享盘，别塞进 wheel。

完整的 bootstrap 行为（解析顺序、探测逻辑、Windows 商店 python 别名）见
[`skills/podcast-knowledge-graph/bin/README.md`](skills/podcast-knowledge-graph/bin/README.md)。

## 使用

装好后直接说"把这段播客整理成知识卡"，或显式调用 skill：

```text
/skill:podcast-knowledge-graph 把这期播客整理成知识卡，音频 ./ep42.mp3
```

`/skill:` 是 Pi / Claude Code 的写法；其他 agent 直接说同一句话，或让它读已安装的 `SKILL.md`。

skill 会按 `sop/SOP.md` 走完 转写 → 抽取 → 校验 → 产出。也可以手动用 CLI：

```bash
podcast-kg --help                      # 选子命令
podcast-kg transcribe --help           # 再查参数 / 输入输出 / 失败语义
```

```bash
podcast-kg doctor                      # 环境自检（解释器 / ffmpeg / 可选依赖 / skill / runtime / 模型）
podcast-kg bootstrap --check           # 运行时是否真的可用（未就绪退出码 1）
podcast-kg models fetch --model small  # 预取权重，之后完全离线（不预取则首次 transcribe 下载）
podcast-kg transcribe ep42.mp3 --model small --lang zh
podcast-kg transcribe ep42.mp3 --words     # 额外出词级时间戳（弧的起止点要对齐到词边界时用）
podcast-kg verify .outputs/ep42.json   # 可一次传多张卡做跨卡归一
podcast-kg render .outputs/ep42.json   # → .outputs/ep42.html
podcast-kg i18n scaffold .outputs/ep42.json --lang en     # 双语：译文骨架
podcast-kg i18n check .outputs/ep42.json .outputs/ep42.en.json
podcast-kg render .outputs/ep42.json .outputs/ep42.html   --i18n en=.outputs/ep42.en.json --default-lang zh        # 一份 HTML，右上角切换
podcast-kg ingest .outputs/ep42.json   # → .outputs/ep42_graph.json
```

所有产物默认写到**当前目录**的 `.outputs/`。**`--help` 是权威说明**（参数、输入输出、退出码），下面的例子只是常见用法。

> **引擎**：默认 faster-whisper。实测（[完整对比](docs/asr-engines.md)）：
> Parakeet TDT 0.6B v3 英文很快很准但**不支持中文**；SenseVoice 中文 CPU 跑到 40–48×、带标点，
> 但会把 `Claude Code` 听成 `cloud code`；Zipformer CTC small（61 MB）纯中文 0% CER，
> 但英文术语全部 `<unk>`。中文技术播客（中英混说 + 专名）仍是 whisper 最稳。
> 同一份数据还暴露了 whisper 的重复循环幻觉，现已默认关闭 `condition_on_previous_text`
> （要旧行为加 `--carry-context`）。

### 可选依赖

| 子命令                                      | 依赖               | 说明       |
| ---------------------------------------- | ---------------- | -------- |
| `render` / `verify` / `install-skill` / `ingest` / `doctor` | **无**（纯标准库） | 离线可用 |
| `transcribe`                             | `faster-whisper` | 首次调用自动安装 |

> `ingest` 从 0.1.0 起不再依赖 semantica。它的 `merge_entities=True` 会按名字相似度误合并：
> 实测把「北京大学」并进「北京师范大学」（`minsky` 并进 `zuckerberg`，两条不同 claim `c33`/`c43` 并成一个 id），
> 每条脏数据都长得完全合法；而它宣称的 PROV-O 溯源只存在进程内存里、从未落盘。
> 现在的实现（`src/podcast_kg/ingest_graph.py`）只按 id 去重，边做端点/自指校验，
> 溯源直接写进 `*_graph.json` 的 `provenance[]`。


自动安装会按当前解释器的安装方式选择 `pip` 或 `uv pip install --python <python>`（`uv tool` 的 venv 没有 pip）。想自己控制：

```bash
podcast-kg doctor --install all         # 提前装
export PODCAST_KG_NO_AUTO_INSTALL=1     # 禁用自动安装
uv tool install --with "faster-whisper" podcast-kg      # 转写依赖一起装
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

uv build                                 # wheel 会把 skills/ 映射成 podcast_kg/skill
PYTHONPATH=src python -m unittest discover -s tests -v   # skill 安装器测试
```

## 打包与发布 skill（Agensi / ZIP）

Agensi（以及大多数技能市场）只收**一个 ZIP**：解压后一个顶层目录，`SKILL.md` 在目录根部，
脚本与参考资料放子目录。本仓库自带打包器，输出**确定性** zip（同一棵树 → 同一个 SHA-256）：

```bash
python scripts/package_skill.py           # → dist/podcast-knowledge-graph-0.1.0.zip
python scripts/package_skill.py --check   # 只校验，不写文件
python scripts/package_skill.py --json    # 文件清单 / 体积 / 字符数 / sha256
```

ZIP 里**只有 skill 本体**（14 个文件、约 155 KB、12.6 万字符）：

```
podcast-knowledge-graph/
├── SKILL.md / SKILL.en.md      触发条件、执行步骤、质量闸门（中/英）
├── sop/SOP.md / SOP.en.md      抽取规范（中/英）
├── examples/                   完整示例卡（JSON + Markdown）
├── bin/bootstrap.py            运行时自举（纯标准库；版本 pin 已内置）
├── bin/bootstrap / .cmd        可选启动器
├── bin/README.md / .en.md      自举行为说明
├── pointer.md                  写进 AGENTS.md / CLAUDE.md 的通用说明块
└── runtime.json                版本 pin（bootstrap 优先读它）
```

**不含** CLI 源码、whisper 权重、缓存或虚拟环境：买家第一次用时由 `bin/bootstrap.py`
把 `podcast-kg` 装进私有 venv（PyPI 优先，未发布则回退 git）。脚本可以单文件拷走运行——
版本 pin 已写进 `bootstrap.py` 常量，`runtime.json` 只作覆盖。

打包器已按 Agensi 规则检查：≤50 MB、≤1000 文件、≤600 万字符；拒绝 exe/dll/so 等可执行文件；
自动剔除 `.git`、`__pycache__`、`.DS_Store`、`node_modules`、`site-packages`、venv。
唯一提示：`bin/bootstrap.py` 22.9 KB，略超其「脚本 <20 KB 便于人工审阅」的建议值（非硬限制）。

### 用 git 发布 ZIP

| 方式 | 做法 | 评价 |
| --- | --- | --- |
| **GitHub Release 资产（推荐）** | `git tag v0.1.0 && git push --tags`；`.github/workflows/skill-zip.yml` 会自动打包并上传 zip | zip 不进 git 历史，Agensi 每次更新只需换版本资产 |
| 直接提交 zip | 放进 `dist/`（已在 `.gitignore`） | 可以，但每次改文档都会多一个二进制 commit，历史会膨胀 |
| GitHub 自动归档 | `https://github.com/meeting90/podcast-knowledge-graph/archive/refs/tags/v0.1.0.zip` | 含整个仓库（Python 源码、测试），不是 skill-only 包，不适合直接交市场 |

手动上传到 Release：

```bash
gh release create v0.1.0 dist/podcast-knowledge-graph-0.1.0.zip --generate-notes
# 或先建 release，再补资产：
gh release upload v0.1.0 dist/podcast-knowledge-graph-0.1.0.zip --clobber
```

Agensi 侧流程：上传 zip → 填定价 → 8 项自动安全扫描 + AI 意图审查 + 人工复核 → 上线；
后续更新重新上传新版本 zip 即可，买家无需重新下载（按需从 MCP 拉取）。

### 版本管理与发布（merge 即 tag + release）

版本写在 4 处（PyPI 元数据 / `--version` / skill 的 `runtime.json` / bootstrap 内置 pin），用脚本同步：

```bash
python scripts/bump_version.py --check        # CI 每次都会跑
python scripts/bump_version.py patch          # 0.1.0 -> 0.1.1（minor / major 同理）
python scripts/bump_version.py --set 0.2.0
```

发布流程（推荐）：

1. 在 PR 里跑 `bump_version.py …`，连同代码一起提交；
2. merge 到 `main` → `.github/workflows/release.yml` 自动执行：
   - 校验 4 处版本一致（不一致直接失败）；
   - 若 `v<version>` 不存在：打 tag、建 Release、附上 skill zip，`--generate-notes` 自动汇总变动的 PR；
   - 已存在：no-op，所以**没升版本号的 merge 不会重复发版**；
3. 手动补发版：

```bash
git tag v0.2.0 && git push origin v0.2.0          # skill-zip 工作流建 Release
# 或直接（zip 已在 dist/）：
gh release create v0.2.0 dist/podcast-knowledge-graph-0.2.0.zip --generate-notes
```

`gh` 本身只是个 CLI，不会“监听 merge”；自动打 tag 靠的是 Actions（`push: main`）。
真实约束只有一条：**版本号必须在 PR 里升好**，merge 后才有新 tag 可发。

**Release notes 分组**：`.github/release.yml` 把变更分成 Features / Fixes / Documentation / Maintenance / Other；
PR 标题用 Conventional Commits 前缀（`feat:` / `fix:` / `docs:` / `chore:` …，支持 `feat(api)!:`）时，
`pr-label.yml` 会自动打对应标签；不想出现在 notes 里就给 PR 加 `skip-changelog` 标签。

### 为什么发 PyPI（不发会怎样）

`podcast-kg` 不是本仓库私有的名字，它是 **PyPI 上的发行名**。不发，所有“按名字装”的路径都会断：

| 不发 PyPI | 影响 |
| --- | --- |
| `uv tool install "podcast-kg[all]"` / `pip install` / `pipx` / `uvx` | 全部 `No solution found`，文档只能写 git / 本地路径 |
| skill 的 `bin/bootstrap.py` | 每次都先查 PyPI（404）再回退 git：要求机器有 `git` 且能连 GitHub；CI/容器常常只有 pip，国内网络 GitHub 也不稳（PyPI 有镜像） |
| 版本锁定与审计 | 不能 `podcast-kg==0.1.0`、不能 `pip download` 做离线 wheelhouse、依赖扫描/SBOM 认的是 PyPI |
| Marketplace 审核 | “运行时从 PyPI 装”比“从 git 装”更容易解释与复核 |

**不发的代价不是“装不上”**：skill 文件、`render/verify/ingest/i18n` 这些纯标准库命令、以及 git/本地安装都照常；
代价集中在**普通用户第一次装 CLI** 和**无 git / 弱网环境**。

### 发布步骤（一次配置，之后随 tag 自动）

1. 首次：PyPI → *Publishing* → *Add a pending publisher*：
   project `podcast-kg`、owner `meeting90`、repository `podcast-knowledge-graph`、workflow `pypi.yml`。
   仓库里已备好 OIDC 工作流（`.github/workflows/pypi.yml`），**不需要 API token**。
2. 触发：`gh workflow run pypi.yml -f tag=v0.1.0`；或发布 GitHub Release 时自动触发。
3. 想本地手动发（需要 token）：`uv build && uv publish`（或 `twine upload dist/*`）。
4. 验证：`pip index versions podcast-kg`、`uv tool install "podcast-kg[all]"`。

版本号在 4 处（`pyproject.toml`、`__init__.py`、`runtime.json`、`bootstrap.py` 的 `PIN_VERSION`），
用 `python scripts/bump_version.py patch|minor|major` 同步；`pypi.yml` 会先校验 tag 与版本一致。

> PyPI 版本不可覆盖：发错了只能 yank 再发下一个版本。先在 TestPyPI 或 `uv build` + `twine check` 过一遍（当前两者均通过）。

## 目录结构

```
podcast-knowledge-graph/
├── package.json                  # Pi 包清单：extension + skills
├── pyproject.toml                # Python 包 podcast-kg：依赖、CLI 入口
├── skills/podcast-knowledge-graph/   # Agent Skills 目录（唯一来源，打包时映射进 wheel）
│   ├── SKILL.md                  #   触发条件、执行步骤、质量闸门（中文；英文见 SKILL.en.md）
│   ├── pointer.md                #   装到各家 AGENTS.md / CLAUDE.md 的通用说明块
│   ├── runtime.json              #   运行时 pin：bootstrap 要装的 podcast-kg 版本
│   ├── bin/bootstrap.py          #   纯标准库自愈脚本：私有 venv + PATH shim
│   ├── sop/SOP.md                #   抽取规范：schema、命名规则、关系类型、质检清单（英文见 SOP.en.md）
│   └── examples/                 #   一张完整示例卡（JSON + Markdown）
├── .pi/                          # Pi 专有资源（其他 agent 不需要）
│   ├── APPEND_SYSTEM.md          #   追加进 Pi system prompt 的说明（Pi 专用）
│   └── extensions/podcast-kg.ts  #   extension：环境准备 / PATH / prompt / skill / 命令
└── src/podcast_kg/               # Python 实现
    ├── cli.py                    #   子命令实现
    ├── args.py                   #   argparse 定义：每个子命令的 --help（权威说明）
    ├── skill_install.py          #   把 skill 装进任意 agent（skills 目录 + 指令文件标记块）
    ├── runtime.py                #   运行时 pin / bootstrap 转交 / 环境自检
    ├── deps.py                   #   可选依赖按需安装（pip / uv tool 兼容）
    ├── outputs.py                #   .outputs/ 约定
    ├── transcribe.py             #   faster-whisper 封装（段级时间戳、VAD、--words 词级对齐）
    ├── models.py                 #   whisper 权重：已知模型表、本地/HF 解析、预取与校验
    ├── i18n.py                   #   双语卡：结构对齐检查、字段合并、译文骨架
    ├── render_card.py            #   知识卡 JSON → HERON 同款 HTML（DOM 与站点对齐）
    ├── render_arcs.py            #   话题弧校验页（点一次连播一整段）
    ├── assets/heron.css          #   站点样式（字体子集已内联，随包装配）
    ├── verify_cards.py           #   跨卡实体 / 人物归一校验
    └── ingest_graph.py           #   知识卡 JSON → 可溯源图谱快照（纯标准库）
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
                       HTML 观点页   图谱快照（entities / relationships / provenance）
```

产物的成品形态可以直接看 [**heronai.top**](https://heronai.top)：那套页面就是 `podcast-kg render` 的目标版式。

## 渲染模式

`podcast-kg render <card.json> [out.html] [--arcs arcs.json] [--mode audio|redirect] [--i18n LANG=FILE]`


| mode       | 输出                            |
| ---------- | ----------------------------- |
| `audio`    | 自绘浮层播放器 + 时间点跳转，播到 `end` 自动暂停 |
| `redirect` | 纯导流：不内联音频、不发音频请求，点时间戳只复制定位提示  |


页面与 [heronai.top](https://heronai.top) 的详情页**同一套 DOM 与样式**（`src/podcast_kg/assets/heron.css`
即站点样式，字体子集内联），所以本地导出的单文件 HTML 跟线上看起来是同一版：

- **阅读单位是话题弧**：卡里有 `arcs`（或旁挂 `<card>_arcs.json`、或 `--arcs` 指定）时，
每个分组下是 `av-arc` 卡片（标题 / 摘要 / 听这段 / 证据条数）；展开后依次是
「主持人开场原话 → 这一段讲了什么 → 金句 → 其余观点」，逐句 claim 降为证据层。
没有 `arcs` 就退回逐句视图（`om-row`）。
- **推荐**：卡片和逐句行上的 ★ 存在你自己的浏览器里（localStorage）；「我的推荐」只看自己推荐的；
「分享我的视图」复制一条带 `#picks=…` 的链接，对方打开就是同一份推荐视图；
「导出 picks」下载 `picks_<id>.json` 回填卡片。
- **多语言（中英）**：`--i18n en=ep42.en.json` 把译文并进同一份 DOM，顶栏出现「中文 / EN」；
  切换只改文字（正文、按钮、提示、目录、时间条），DOM / id / 深链 / 播放器只有一份。
  两份卡必须结构一致（id、时间戳、分组逐字相同），`podcast-kg i18n check` 会卡住漂移；
  `i18n scaffold` 生成只含结构、文字留空的译文骨架。
- **音频不变**：双语页面始终播原始音源，没有配音、没有第二套时间轴。
- **深链**：`#arc-a03` 展开一段，`#c21` 展开它所在的弧和这条观点。
- **评论区**只留版式位；要真讨论就去线上那张卡。

本地页是**自包含单文件**（CSS + 字体子集 + 可选音频片段全部内联），断网、发微信都能直接打开。

## Schema 要点

- `source.content_id` 全局唯一（`平台_日期_编号`）
- `claims[].timestamp` / `end` 必填，`end` 默认取下一条 claim 起点，上限 300 秒
- `relations[]` 11 种类型：`supports` / `extends` / `deepens` / `tension_with` / `responds_to` / `parallel` / `implies` / `precondition` / `part_of` / `echoes` / `exemplified_by`
- `groups[].ids` 必须覆盖全部 claim，不重不漏
- 实体用**纯 slug**（`pi` 而不是 `pi-agent`），人物与实体分开
- 完整规则见 skill 里的 `sop/SOP.md`

## License

[MIT](LICENSE)



&nbsp;