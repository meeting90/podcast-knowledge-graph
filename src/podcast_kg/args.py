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
        description="播客/访谈知识卡工作流的命令行程序：转写、校验、渲染、入库，并安装配套 Pi skill。",
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
        "transcribe",
        "音频 → 带时间戳的转写稿",
        "用本地 faster-whisper 转写音频，输出段级时间戳。首次运行会下载 whisper 模型（数百 MB）并可能自动安装 faster-whisper。",
        """输入
  <audio>        mp3 / wav / m4a 等；有 ffmpeg 时先转 16k 单声道，没有则用 PyAV 直接解码

输出
  <out> 或 .outputs/<audio>_transcript.json   [{"start": 12.3, "end": 15.8, "text": "…"}, …]
  同目录同名 .txt                             [mm:ss] text，按段一行

副作用
  .outputs/<audio>.16k.wav（有 ffmpeg 时会生成中间文件）

失败语义
  音频不可解码 / 无语音 → 退出码 1
  缺少 faster-whisper 且自动安装失败 → 退出码 1（提示手动安装命令）""",
    )
    p.add_argument("audio", help="音频文件；也可传已转好的 .wav")
    p.add_argument("out", nargs="?", help="输出 JSON 路径（默认 .outputs/<audio>_transcript.json）")
    p.add_argument("--model", default="small", help="whisper 模型大小（tiny/base/small/medium/large-v3；默认 %(default)s）")
    p.add_argument("--lang", default="zh", help="音频语言代码（默认 %(default)s）")
    p.set_defaults(func=None, name="transcribe")

    p = add(
        "render",
        "知识卡 JSON → 单文件 HTML 观点页",
        "把知识卡渲染成单文件 HTML（HERON 同款版式：刊头 + 主题导航 + 观点行 + 底部播放条），零外部依赖。",
        """输入
  <card>                   知识卡 JSON
  --seg DIR                可选，音频片段目录；mode=audio 时把片段内联进 HTML

输出
  <out> 或 .outputs/<card>.html    自包含 HTML（CSS/JS/音频均内联）

失败语义
  card 不可读或不是 JSON → 退出码 1
  claims 为空 → 仍生成页面，但页面显示空状态""",
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
        "ingest",
        "知识卡 JSON → Semantica 图谱快照",
        "把知识卡转成 Semantica 图谱并登记 PROV-O 溯源（每条 claim 的音频 URL + 秒级区间）。"
        "首次运行可能自动安装 semantica。",
        """输入
  <card>          知识卡 JSON

输出
  --out 或 .outputs/<card>_graph.json    {"entities": [...], "relationships": [...], …}
  stdout 打印节点数、边数、被拒关系数、溯源登记条数

失败语义
  缺少 semantica 且自动安装失败 → 退出码 1（提示手动安装命令）
  知识卡缺少必需字段（content_id / source.audio_url / claims）→ 退出码 1""",
    )
    p.add_argument("card", help="知识卡 JSON")
    p.add_argument("--out", help="输出图谱 JSON（默认 .outputs/<card>_graph.json）")
    p.set_defaults(func=None, name="ingest")

    p = add(
        "setup",
        "把随包分发的 Pi skill 装进 Pi",
        "把包内自带的 skill 复制到 Pi 的 skills 目录，并往对应的 APPEND_SYSTEM.md 追加一段带标记的 CLI 说明。"
        "重复执行是幂等的；有内容变化时只更新标记块，不动文件里的其他内容。",
        """输入
  无（skill 内容随包分发，位于 site-packages/podcast_kg/skill/）

输出
  user     scope: <agent-dir>/skills/podcast-knowledge-graph/  与  <agent-dir>/APPEND_SYSTEM.md
  project  scope: <project>/.pi/skills/podcast-knowledge-graph/ 与  <project>/.pi/APPEND_SYSTEM.md
  <agent-dir> = $PI_CODING_AGENT_DIR 或 ~/.pi/agent

副作用
  已存在同名 skill 时默认跳过（--force 覆盖）
  APPEND_SYSTEM.md 里只增删 <!-- podcast-kg:start --> 与 <!-- podcast-kg:end --> 之间的块

失败语义
  目标目录不可写 → 退出码 1
  另一 scope 已有同名 skill → 只提示，不失败（Pi 保留先发现的）""",
    )
    p.add_argument(
        "--scope",
        choices=["user", "project"],
        default="user",
        help="user=<agent-dir>/skills（默认）；project=<project>/.pi/skills",
    )
    p.add_argument("--project", help="--scope project 的项目根目录（默认当前目录）")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录（默认 $PI_CODING_AGENT_DIR 或 ~/.pi/agent）")
    p.add_argument("--force", action="store_true", help="覆盖已存在的 skill 安装")
    p.add_argument("--dry-run", action="store_true", help="只报告将要做什么，不写文件")
    p.set_defaults(func=None, name="setup")

    p = add(
        "unsetup",
        "移除已安装的 Pi skill",
        "删除 skill 目录，并从 APPEND_SYSTEM.md 里移除 podcast-kg 的标记块（文件里其他内容保留）。",
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

--install 取值
  transcribe  faster-whisper
  graph       semantica
  all         两者

失败语义
  --install 失败 → 退出码 1；只做检查时几乎总是 0""",
    )
    p.add_argument("--json", action="store_true", help="机器可读输出")
    p.add_argument("--agent-dir", help="覆盖 Pi agent 目录（用于检查 skill 安装位置）")
    p.add_argument(
        "--install",
        choices=["transcribe", "graph", "all"],
        help="预先安装可选依赖到当前解释器",
    )
    p.set_defaults(func=None, name="doctor")

    return parser
