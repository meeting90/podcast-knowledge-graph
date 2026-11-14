"""Argument parsing for podcast-kg.

`--help` is the contract: every subcommand documents its inputs, outputs,
side effects and failure semantics there. Keep this file in sync with the
behaviour rather than describing commands in prose elsewhere.

Common contract for all subcommands:
  exit 0 success · 1 failure (bad input, unreadable file, missing dependency,
  failed install) · 130 interrupted.
"""

from __future__ import annotations

import argparse

from . import __version__
from .skill_install import TARGET_IDS

EXIT_CODES = """退出码
  0    成功
  1    失败（参数非法 / 文件不可读 / 依赖安装失败 / 校验不通过）
  130  被中断（Ctrl-C）

产物默认写入当前目录的 .outputs/（显式给出输出路径时以给出为准）。
每个子命令都有自己的 --help：podcast-kg <子命令> --help"""

FOOTER = "退出码 0 成功 / 1 失败 / 130 中断。产物默认写当前目录的 .outputs/。"


def build_parser() -> argparse.ArgumentParser:
    common = argparse.RawDescriptionHelpFormatter

    parser = argparse.ArgumentParser(
        prog="podcast-kg",
        description="播客/访谈知识卡工作流的命令行程序：转写、校验、渲染、入库，并把配套 skill 装进任意 agent。",
        epilog=EXIT_CODES,
        formatter_class=common,
    )
    parser.add_argument("--version", action="version", version=f"podcast-kg {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<子命令>")

    def add(name: str, summary: str, description: str, epilog: str) -> argparse.ArgumentParser:
        return sub.add_parser(
            name,
            help=summary,
            description=description,
            epilog=f"{epilog}\n\n{FOOTER}",
            formatter_class=common,
        )

    p = add(
        "models",
        "whisper 模型权重：查看 / 预取 / 校验",
        "模型不随 skill 内置（small 486MB、large-v3 3.1GB，PyPI 单文件上限 100MB）。"
        "这里负责把权重放到固定位置或校验已有目录；预取之后 transcribe 完全离线。",
        """动作
  list     每个已知模型的体积、状态（本地模型 / HF 缓存 / 未下载）、路径
  fetch    下载到 <dir>/<name>（默认 $PODCAST_KG_HOME/models）
  path     打印某个模型的可用本地路径；没有则退出码 1
  verify   校验目录完整性（config.json / model.bin / tokenizer.json / vocabulary）

常用
  podcast-kg models list
  podcast-kg models fetch --model small                       # 486 MB，之后完全离线
  podcast-kg models fetch --model small --dir /srv/models     # 内网共享盘 / U 盘
  podcast-kg models path --model small

输入
  --model   已知模型名（tiny/base/small/medium/large-v3/large-v3-turbo），可重复；fetch 支持 all
  --dir     模型根目录（默认 $PODCAST_KG_MODEL_DIR 或 $PODCAST_KG_HOME/models）

输出
  list / verify 人类可读表格；--json 输出结构化报告
  fetch 打印每个模型的目标路径与体积

失败语义
  未知模型名 / 校验不通过 → 退出码 1
  fetch 缺少 huggingface_hub 且自动安装失败 → 退出码 1
  离线环境下文件已存在时不需要联网""",
    )
    p.add_argument("action", choices=["list", "fetch", "path", "verify"], help="要做什么")
    p.add_argument("--model", action="append", help="已知模型名，可重复（默认 small；fetch 可用 all）")
    p.add_argument("--dir", help="模型根目录（默认 $PODCAST_KG_MODEL_DIR 或 $PODCAST_KG_HOME/models）")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.add_argument("--dry-run", action="store_true", help="fetch：只报告体积与目标路径，不下载")
    p.add_argument("--force", action="store_true", help="fetch：即使已存在也重新下载")
    p.set_defaults(func=None, name="models")

    p = add(
        "transcribe",
        "音频 → 带时间戳的转写稿",
        "用本地 faster-whisper 转写音频，输出段级时间戳。首次运行会下载 whisper 模型（数百 MB）并可能自动安装 faster-whisper。"
        "默认自动选运行配置：有可用 CUDA 用 large-v3-turbo/float16/beam 5，否则 small/int8/beam 1。",
        """输入
  <audio>        mp3 / wav / m4a 等；有 ffmpeg 时先转 16k 单声道，没有则用 PyAV 直接解码

模型来源（依次）
  1. --model 指向的目录 / 已在你给的 --model-dir 下
  2. $PODCAST_KG_HOME/models/<name>（`podcast-kg models fetch` 预取的位置）
  3. HuggingFace 缓存
  4. 都没有就下载（PODCAST_KG_OFFLINE=1 时改为报错，不会静默联网）

运行配置
  --device auto         有 ctranslate2 可用的 CUDA 设备则用 GPU，否则 CPU
  --compute-type auto   GPU→float16，CPU→int8
  --model auto          GPU→large-v3-turbo，CPU→small
  --beam auto           GPU→5，CPU→1
  CUDA 存在但 cuBLAS/cuDNN 缺失时自动回退 CPU/int8，不中断任务

输出
  <out> 或 .outputs/<audio>_transcript.json   [{"start": 12.3, "end": 15.8, "text": "…"}, …]
  同目录同名 .txt                             [mm:ss] text，按段一行
  --words 时额外 <audio>_words.json           [{"start": 12.34, "end": 12.6, "word": "…"}, …]

副作用
  .outputs/<audio>.16k.wav（有 ffmpeg 时会生成中间文件）
  模型缓存在 HF 缓存目录（GPU 的 large-v3-turbo 约 1.6 GB）

失败语义
  音频不可解码 / 无语音 → 退出码 1
  缺少 faster-whisper 且自动安装失败 → 退出码 1（提示手动安装命令）""",
    )
    p.add_argument("audio", help="音频文件；也可传已转好的 .wav")
    p.add_argument("out", nargs="?", help="输出 JSON 路径（默认 .outputs/<audio>_transcript.json）")
    p.add_argument(
        "--model",
        default=None,
        help="模型名（tiny/base/small/medium/large-v3/large-v3-turbo）、HF repo id，或本地模型目录（默认按设备自动选）",
    )
    p.add_argument(
        "--model-dir",
        metavar="DIR",
        help="模型根目录（默认 $PODCAST_KG_MODEL_DIR 或 $PODCAST_KG_HOME/models）；离线/内网时指到这里",
    )
    p.add_argument("--lang", default="zh", help="音频语言代码（默认 %(default)s）")
    p.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cuda", "cpu"],
        help="推理设备（默认 %(default)s）",
    )
    p.add_argument(
        "--compute-type",
        default=None,
        choices=["auto", "int8", "int8_float16", "float16", "float32"],
        help="量化精度（默认按设备自动选）",
    )
    p.add_argument("--beam", type=int, default=None, help="beam search 宽度（默认按设备自动选）")
    p.add_argument(
        "--words",
        action="store_true",
        help="额外输出词级时间戳 <audio>_words.json（DTW 对齐；弧/卡的时间戳靠它对齐到词边界）",
    )
    p.add_argument(
        "--carry-context",
        action="store_true",
        help="让每个语音段参考上文（默认关：开启后遇到重复段落可能进循环幻觉，实测 71s 重复音频 WER 10%%、耗时 4×）",
    )
    p.set_defaults(func=None, name="transcribe")

    p = add(
        "render",
        "知识卡 JSON → 单文件 HTML 观点页",
        "把知识卡渲染成单文件 HTML，与 heronai.top 详情页同一套 DOM 与样式："
        "顶栏 + 卡片头 + 主题导航 + 话题弧卡片 + 评论区位 + 浮层播放器；样式/字体全部内联，零外部依赖。",
        """输入
  <card>                   知识卡 JSON
  --seg DIR                可选，音频片段目录；mode=audio 时把片段内联进 HTML

输出
  <out> 或 .outputs/<card>.html    自包含 HTML（CSS/字体/音频均内联）

渲染单位
  卡里有 arcs（或 --arcs / 旁挂 <card>_arcs.json）→ 每个分组渲染 av-arc 话题弧卡片，
    展开后是「主持人开场原话 → 这一段讲了什么 → 金句 → 其余观点」，逐句 claim 降为证据
  没有 arcs → 退回逐句视图（om-row），与站点「全部观点」一致

多语言
  --i18n en=ep.en.json   输出单文件双语页：右上角切换，音频仍只有原始音源
  两份卡必须结构一致（content_id / id / 时间戳 / 分组），否则直接失败；
  先 `podcast-kg i18n check` 或 `i18n scaffold` 生成骨架

失败语义
  card 不可读或不是 JSON → 退出码 1
  claims 为空 → 仍生成页面，但页面显示空状态
  译文卡结构不一致 → 退出码 1（列出缺/多的 id 与漂移的时间戳）""",
    )
    p.add_argument("card", help="知识卡 JSON")
    p.add_argument("out", nargs="?", help="输出 HTML 路径（默认 .outputs/<card>.html）")
    p.add_argument("--seg", metavar="DIR", help="音频片段目录（mode=audio 时内联播放）")
    p.add_argument(
        "--mode",
        choices=["audio", "redirect"],
        default="audio",
        help="audio=自绘播放器+时间点跳转；redirect=纯文字+官方链接（默认 %(default)s）",
    )
    p.add_argument("--no-chrome", action="store_true", help="不输出 HERON 页面外壳（只要正文片段）")
    p.add_argument(
        "--arcs",
        metavar="JSON",
        help="话题弧 JSON（默认读卡内 arcs 字段，否则旁挂 <card>_arcs.json）；给了就按弧渲染",
    )
    p.add_argument(
        "--i18n",
        action="append",
        metavar="LANG=FILE",
        help="译文卡（可重复）：输出单文件双语页、右上角切换语言；如 --i18n en=ep.en.json",
    )
    p.add_argument(
        "--default-lang",
        metavar="LANG",
        help="默认显示语言（默认取 source.language 或 zh）",
    )
    p.set_defaults(func=None, name="render")

    p = add(
        "verify",
        "知识卡校验 / 跨卡归一 / 维度覆盖",
        "三种模式：默认做跨卡实体/人物归一报告；--build-registry 生成注册表草案；--coverage 检查六个共性维度的覆盖。"
        "只把知识卡 JSON 传进来（不要传 *_transcript.json / *_graph.json）。",
        """输入
  <cards>...                       一个或多个知识卡 JSON（默认模式）
  --build-registry OUT <cards>...  生成注册表草案到 OUT
  --coverage CARD [--transcript TXT]

输出
  报告直接打印到 stdout：
    A. id 冲突（同名不同 id）
    B. 跨卡共用实体（已对上）
    C. 全量 ID 清单
    --coverage 输出六个维度各有几条 + 可疑漏抽提示
    --build-registry 写入 JSON 文件（stdout 只打印条数）

失败语义
  JSON 不可读 → 抛出并退出码 1
  发现问题本身不算失败：报告输出后仍是退出码 0（由调用方判断）""",
    )
    p.add_argument("cards", nargs="*", help="知识卡 JSON（默认模式或配合 --build-registry）")
    p.add_argument("--build-registry", metavar="OUT", help="把注册表草案写到 OUT")
    p.add_argument("--coverage", metavar="CARD", help="检查 CARD 的六个共性维度覆盖")
    p.add_argument("--transcript", metavar="TXT", help="配合 --coverage：用转写稿做漏抽检测")
    p.set_defaults(func=None, name="verify")

    p = add(
        "i18n",
        "双语知识卡：结构对齐检查 / 生成译文骨架",
        "同一期节目出中英两份 JSON 时，结构必须完全一致（content_id / claim_id / arc_id / gid / person_id 与每个时间戳）。"
        "这里负责检查对齐、或生成只保留结构、文字留空的译文骨架。",
        """动作
  check     检查译文卡与母卡的结构是否对齐（硬错退出码 1）
  scaffold  生成 <base>.<lang>.json 骨架：id/时间戳/分组原样保留，文字字段留空

输入
  <base>            母卡 JSON
  [locales...]      check：一个或多个译文卡；留空则用 <base>.<lang>.json
  --lang            scaffold 目标语言（默认 en）
  --out             scaffold 输出路径（默认 <base>.<lang>.json）
  --force           scaffold 覆盖已存在的文件

输出
  check：每个译文卡的错误 / 未翻译警告；--json 输出结构化结果
  scaffold：打印写出的路径

失败语义
  结构不一致（缺/多 id、时间戳不同）→ 退出码 1
  scaffold 目标已存在且未加 --force → 退出码 1""",
    )
    p.add_argument("action", choices=["check", "scaffold"], help="要做什么")
    p.add_argument("base", help="母卡 JSON")
    p.add_argument("locales", nargs="*", help="check：译文卡（默认 <base>.<lang>.json）")
    p.add_argument("--lang", default="en", help="scaffold 目标语言（默认 %(default)s）")
    p.add_argument("--arcs", metavar="JSON", help="话题弧 JSON（母卡里没有 arcs 时旁挂，默认读 <base>_arcs.json）")
    p.add_argument("--out", help="scaffold 输出路径（默认 <base>.<lang>.json）")
    p.add_argument("--force", action="store_true", help="scaffold 覆盖已存在的文件")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.set_defaults(func=None, name="i18n")

    p = add(
        "ingest",
        "知识卡 JSON → 可溯源图谱快照",
        "把知识卡转成 entities / relationships / provenance 快照，每条 claim 带音频 URL 与秒级区间。"
        "纯标准库、离线可用；只按 id 去重，不做模糊实体消解（那会把不同实体并成一个）。",
        """输入
  <card>          知识卡 JSON

输出
  --out 或 .outputs/<card>_graph.json
    {"entities": [...], "relationships": [...], "provenance": [...], "metadata": {...}}
  stdout 打印节点数、边数、去重/拒绝的边数、溯源条数

规则
  实体只按 id 合并（不做“名字像就合并”的猜测）
  边：端点必须存在、不许自指、同一 (source,target,type) 只留一条；被拒的写入 metadata.rejected
  溯源：每条 claim 一条 {entity_id, source, clip, start_sec, end_sec, speaker}

失败语义
  知识卡缺少 content_id / source / claims → 退出码 1
  旧图谱快照或转写稿传进来 → 同上（提示换正确的文件）""",
    )
    p.add_argument("card", help="知识卡 JSON")
    p.add_argument("--out", help="输出图谱 JSON（默认 .outputs/<card>_graph.json）")
    p.set_defaults(func=None, name="ingest")

    p = add(
        "install-skill",
        "把配套 skill 装进任意 agent",
        "skill 本体是一份普通的 Agent Skills 目录（SKILL.md + sop/ + examples/），这里按目标 agent 的约定"
        "复制它，并在该 agent 的指令文件里维护一段带标记的说明块（指向 SKILL.md 与 podcast-kg --help）。"
        "重复执行幂等；--dry-run 先看要写哪些文件。",
        """目标（--target，可重复；默认 pi）
  pi        ~/.pi/agent/skills            .pi/skills            APPEND_SYSTEM.md
  claude    ~/.claude/skills              .claude/skills        CLAUDE.md
  codex     ~/.codex/skills               .codex/skills         AGENTS.md
  cursor    ~/.cursor/skills              .cursor/skills        AGENTS.md
  gemini    ~/.gemini/skills              .gemini/skills        GEMINI.md
  opencode  ~/.config/opencode/skills     .opencode/skills      AGENTS.md
  copilot   -（无用户级）                  .github/skills        .github/copilot-instructions.md
  agents    ~/.agents/skills              .agents/skills        AGENTS.md
  all       以上全部
  用 --list 查看实时表格

输入
  无（skill 内容随包分发，位于 site-packages/podcast_kg/skill/）

输出
  <skill-dir>/podcast-knowledge-graph/   SKILL.md + sop/ + examples/
  指令文件里 <!-- podcast-kg:start --> … <!-- podcast-kg:end --> 之间的块

副作用
  已存在同名 skill 时默认跳过（--force 覆盖）
  指令文件只动标记块，其他内容原样保留

失败语义
  未知 --target / 目标目录不可写 → 退出码 1
  某 scope 没有约定目录（如 copilot 用户级）→ 跳过并提示，不算失败""",
    )
    p.add_argument(
        "--target",
        action="append",
        choices=[*TARGET_IDS, "all"],
        help="目标 agent（可重复；默认 pi；all=全部）",
    )
    p.add_argument("--scope", choices=["user", "project"], default="user", help="user=用户级（默认）；project=当前项目")
    p.add_argument("--project", help="--scope project 的项目根目录（默认当前目录）")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录（默认 $PI_CODING_AGENT_DIR 或 ~/.pi/agent）")
    p.add_argument(
        "--skills-dir",
        metavar="DIR",
        help="任意 agent 的 skills 根目录（skill 装到 DIR/podcast-knowledge-graph；与 --target 互斥）",
    )
    p.add_argument(
        "--instructions",
        action="append",
        metavar="FILE",
        help="指针写进这些文件（可重复；默认用目标约定的文件）",
    )
    p.add_argument("--no-pointer", action="store_true", help="只装 skill 目录，不写任何指令文件")
    p.add_argument(
        "--verify",
        action="store_true",
        help="只做检查不安装：skill 文件、runtime.json 与 CLI 是否真的可用（不 ok 退出码 1）",
    )
    p.add_argument("--list", action="store_true", dest="list_targets", help="列出支持的目标与目录后退出")
    p.add_argument("--force", action="store_true", help="覆盖已存在的 skill 安装")
    p.add_argument("--dry-run", action="store_true", help="只报告将要做什么，不写文件")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.set_defaults(func=None, name="install-skill")

    p = add(
        "uninstall-skill",
        "移除已安装的 skill",
        "删除 skill 目录，并从目标 agent 的指令文件里移除 podcast-kg 标记块（其他内容保留）。目标解析与 install-skill 相同。",
        """输出
  每个目标打印 skill 目录与每个指令文件上的动作：removed / missing / no-block

失败语义
  目标不存在 → 视为成功（幂等），退出码 0""",
    )
    p.add_argument(
        "--target",
        action="append",
        choices=[*TARGET_IDS, "all"],
        help="目标 agent（可重复；默认 pi；all=全部）",
    )
    p.add_argument("--scope", choices=["user", "project"], default="user")
    p.add_argument("--project", help="--scope project 的项目根目录（默认当前目录）")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录")
    p.add_argument("--skills-dir", metavar="DIR", help="从任意 skills 根目录移除 skill")
    p.add_argument("--instructions", action="append", metavar="FILE", help="从这些文件移除标记块")
    p.add_argument("--dry-run", action="store_true", help="只报告将要做什么，不删文件")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.set_defaults(func=None, name="uninstall-skill")

    p = add(
        "bootstrap",
        "让 skill 的运行时可直接使用（装 CLI 到私有 venv）",
        "skill 只是文件；真正干活的是 `podcast-kg` CLI。本子命令转交给 skill 自带的 `bin/bootstrap.py`："
        "先找 PATH 上的 CLI，找不到就用 uv（可自带 Python 3.12）装 pin 住的版本到私有 venv，"
        "再写 PATH shim。幂等：已就绪时直接返回。",
        """参数（透传给 bin/bootstrap.py，以 `python3 bin/bootstrap.py --help` 为准）
  --check        只检查，不安装；未就绪退出码 1
  --plan         报告将要做什么，不动文件
  --json         机器可读报告（含 ready / cli / version / pinned / action / notes）
  --quiet        不打印过程信息
  --version SPEC 覆盖 pin 的版本（默认读 skill 目录下的 runtime.json）
  --extras LIST  all（默认）| none | 逗号分隔；离线只用 render/verify 时选 none
  --home DIR     覆盖运行时装在哪（默认 $PODCAST_KG_HOME）
  --python EXE   指定解释器 / 版本（默认 uv 管理的 3.12）
  --no-shim      只装 venv，不写 PATH shim

输出
  CLI 路径 + 版本 + 运行时目录；--json 时同样的信息

失败语义
  无 uv 且无 Python ≥3.10 → 退出码 1，并给出装 uv 的命令
  安装 / venv 创建失败 → 退出码 1，notes 带最后几行真实错误""",
    )
    p.add_argument("--check", action="store_true", help="只检查，不安装；未就绪退出码 1")
    p.add_argument("--plan", action="store_true", help="报告将要做什么，不动文件")
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.add_argument("--quiet", action="store_true", help="不打印过程信息")
    p.add_argument("--version", dest="pin_version", metavar="SPEC", help="覆盖 pin 的版本（如 0.1.0 / latest）")
    p.add_argument("--extras", metavar="LIST", help="all（默认）| none | 逗号分隔的 extras")
    p.add_argument("--home", metavar="DIR", help="覆盖运行时安装位置")
    p.add_argument("--python", metavar="EXE", help="指定 Python 解释器 / 版本")
    p.add_argument("--no-shim", action="store_true", help="只装 venv，不写 PATH shim")
    p.set_defaults(func=None, name="bootstrap")

    p = add(
        "setup",
        "安装 Pi skill（= install-skill --target pi）",
        "兼容旧命令：等价于 install-skill --target pi。要把 skill 装进 Claude Code / Codex / 其他 agent，用 install-skill。",
        """输入
  无（skill 内容随包分发）

输出
  user     <agent-dir>/skills/podcast-knowledge-graph/  与  <agent-dir>/APPEND_SYSTEM.md
  project  <project>/.pi/skills/podcast-knowledge-graph/ 与 <project>/.pi/APPEND_SYSTEM.md

失败语义
  目标目录不可写 → 退出码 1""",
    )
    p.add_argument("--scope", choices=["user", "project"], default="user")
    p.add_argument("--project", help="--scope project 的项目根目录（默认当前目录）")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录（默认 $PI_CODING_AGENT_DIR 或 ~/.pi/agent）")
    p.add_argument("--force", action="store_true", help="覆盖已存在的 skill 安装")
    p.add_argument("--dry-run", action="store_true", help="只报告将要做什么，不写文件")
    p.set_defaults(func=None, name="setup")

    p = add(
        "unsetup",
        "移除 Pi skill（= uninstall-skill --target pi）",
        "兼容旧命令：删除 Pi 的 skill 目录，并从 APPEND_SYSTEM.md 里移除 podcast-kg 标记块。",
        """输出
  打印每个动作：removed / missing / no-block

失败语义
  目标不存在 → 视为成功（幂等），退出码 0""",
    )
    p.add_argument("--scope", choices=["user", "project"], default="user")
    p.add_argument("--project", help="--scope project 的项目根目录（默认当前目录）")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录")
    p.add_argument("--dry-run", action="store_true", help="只报告将要做什么，不删文件")
    p.set_defaults(func=None, name="unsetup")

    p = add(
        "doctor",
        "检查解释器、依赖与 skill 安装状态",
        "打印运行环境：解释器路径、包目录、ffmpeg、可选依赖是否就绪、skill 装在哪个 scope。可用 --install 预先安装可选依赖。",
        """输出
  stdout 人类可读；--json 输出机器可读对象（含 skill_installed.user / .project）
  转写能力：ctranslate2 版本、可用 CUDA 设备数、PyAV 版本及与 faster-whisper 的兼容性

--install 取值
  transcribe  faster-whisper
  all         同上（ingest 已无额外依赖）

失败语义
  --install 失败 → 退出码 1；只做检查时几乎总是 0""",
    )
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录（用于检查 skill 安装位置）")
    p.add_argument("--install", choices=["transcribe", "all"], help="预先安装可选依赖到当前解释器")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"], help="doctor 检查时使用的设备策略（默认 %(default)s）")
    p.set_defaults(func=None, name="doctor")

    return parser
