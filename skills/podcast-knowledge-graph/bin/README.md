# runtime bootstrap

中文 | [English](README.en.md)

`SKILL.md` 只是说明书；真正干活的是 **skill 自带的 CLI**（`../lib/podcast_kg`）。
这个目录负责两件事：给 agent 一个稳定入口，以及把 `transcribe` 需要的依赖装进私有 venv。
脚本只用标准库，不依赖任何已发布的 `podcast-kg` 包。

```bash
python3 podcast-kg.py doctor       # 首选入口：直接跑内置 CLI；缺依赖时自动装
python3 podcast-kg.py transcribe ep.mp3   # 第一次会先把 faster-whisper 装进 venv

python3 bootstrap.py               # 只装依赖（幂等）：venv + shim
python3 bootstrap.py --check       # 依赖/venv 是否就绪；未就绪退出码 1
python3 bootstrap.py --plan        # 会做什么，不动文件
python3 bootstrap.py --json        # ready / vendored / deps / deps_ready / cli / action / notes
python3 bootstrap.py --models small  # 装依赖 + 预取 whisper 权重
```

Windows：`bootstrap.cmd`；POSIX：`./bootstrap`（探测解释器后转交 `bootstrap.py`，
跳过 Windows 商店那种一跑就退出 49 的 `python` 别名）。

## 行为

| 顺序 | 条件 | 动作 |
| --- | --- | --- |
| 1 | `$PODCAST_KG_BIN` 可执行 | 直接用（显式覆盖） |
| 2 | `lib/podcast_kg` 存在 + 当前解释器已有依赖 | 直接跑内置 CLI |
| 3 | `lib/podcast_kg` 存在 + `$PODCAST_KG_HOME/venv` 已有依赖 | 用 venv 的 Python 跑内置 CLI |
| 4 | 内置 CLI + 缺依赖（`transcribe` / `models fetch`） | `uv venv --python 3.12` + 安装 `deps`；然后重跑 |
| 5 | 没有 `lib/`（旧安装） | 找 PATH/venv 里的 CLI；都没有则装 `podcast-kg` 包（PyPI → git） |
| 6 | 连 Python/uv 都没有 | 退出 1，打印装 uv 的命令 |

安装目标：`$PODCAST_KG_HOME`（默认 Windows `%LOCALAPPDATA%\podcast-kg`，
macOS `~/Library/Application Support/podcast-kg`，Linux `${XDG_DATA_HOME:-~/.local/share}/podcast-kg`）。
只写私有 venv 与 `bin/` shim（存在时也写 `~/.local/bin`），不碰系统 Python。

`runtime.json` 提供两样东西：

| 字段 | 用途 |
| --- | --- |
| `version` | 内置 CLI 的版本（`install-skill` 写入；`lib/` 与它同步） |
| `deps` | 需要装进 venv 的依赖，默认 `faster-whisper>=1.0.0` + `av>=11,<19` |

## 模型权重

权重不进 skill（small 486 MB、large-v3 3.1 GB），`--models` 只是转交内置 CLI：

```bash
python3 bootstrap.py --models small      # → <home>/models/small，之后 transcribe 完全离线
```

`--check` / `--plan` 只报告不下载；下载失败会把 CLI 的真实错误尾部写进 `notes` 并以 1 退出。
离线部署把 `<home>/models` 整个目录拷到别的机器，配 `PODCAST_KG_MODEL_DIR` 即可。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 就绪（不管本来就有的、内置的，还是刚装好的） |
| 1 | 未就绪 / 安装失败（`notes` 里带真实错误尾部） |
| 2 | 参数非法 |

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `PODCAST_KG_HOME` | 运行时安装位置（venv / shim / models） |
| `PODCAST_KG_BIN` | 指定一个现成的 `podcast-kg` 可执行文件 |
| `PODCAST_KG_PYTHON` | 指定解释器（launcher 与 venv 都用它） |
| `PODCAST_KG_VENDORED` | 内置 CLI 标记；此时禁止往系统 Python 装包（由启动器设置） |
