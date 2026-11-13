# runtime bootstrap

中文 | [English](README.en.md)

`SKILL.md` 只是说明书；真正干活的是 `podcast-kg` CLI。这个目录负责把「文件」变成「可用的运行时」，
整个脚本只用标准库，不依赖 `podcast-kg` 本身。

日常只需要一个入口：`python3 podcast-kg.py <子命令>`（缺运行时先自动安装，再执行）。
下面的 `bootstrap.py` 是显式安装/体检入口。

```bash
python3 bootstrap.py            # 幂等：已就绪直接返回，否则装到私有 venv 并写 PATH shim
python3 bootstrap.py --check    # 只检查；未就绪退出码 1
python3 bootstrap.py --plan     # 会做什么，不动文件
python3 bootstrap.py --json     # ready / cli / version / pinned / install / models / action / notes
```

Windows：`bootstrap.cmd`；POSIX：`./bootstrap`（都只是探测解释器后转交给 `bootstrap.py`，
跳过 Windows 商店那种一跑就退出 49 的 `python` 别名）。

## 行为

| 顺序 | 条件 | 动作 |
| --- | --- | --- |
| 1 | `$PODCAST_KG_BIN` 可执行 | 直接用 |
| 2 | `$PODCAST_KG_HOME/bin` 里的 shim | 直接用（`--version` 不通过则视为失效） |
| 3 | PATH 上的 `podcast-kg` | 直接用 |
| 4 | 有 `uv` | `uv venv --python 3.12`（缺解释器会自动下载）+ `uv pip install <pin>` |
| 5 | 有 Python ≥3.10 | `python -m venv` + `pip install <pin>` |
| 6 | 都没有 | 退出 1，打印装 uv 的命令 |

安装目标：`$PODCAST_KG_HOME`（默认 Windows `%LOCALAPPDATA%\podcast-kg`，
macOS `~/Library/Application Support/podcast-kg`，Linux `${XDG_DATA_HOME:-~/.local/share}/podcast-kg`）。
只写私有 venv 与 `bin/`（存在时也写 `~/.local/bin`），不碰系统 Python。

版本来自 skill 根目录的 `runtime.json`（`install-skill` 按当前 CLI 写入），默认 `podcast-kg[all]==<version>`。
安装来源按顺序尝试，前一个失败才试下一个：

| 顺序 | 来源 | 何时生效 |
| --- | --- | --- |
| 1 | 本地源码（`pyproject.toml` 与 skill 同级） | 仓库 / 开发环境，不联网装包 |
| 2 | PyPI：`podcast-kg[all]==<version>` | 包已发布 |
| 3 | git：`podcast-kg[all] @ git+<install_from_git>` | PyPI 还没这个版本时的兜底（需已装 git） |

选项：

- `--extras none`：只装 CLI 本体（纯标准库，`render` / `verify` / `install-skill` / `ingest` 可用，离线可用）
- `--models LIST`：装完预取 whisper 权重（`small` / `small,base` / `all` / `none`，默认 none）→ `<home>/models`
- `--version latest`：不锁版本（PyPI 候选不锁；git 候选本来就是 HEAD）
- Windows 下若环境里缺 `PATHEXT`（CI / 精简容器），脚本会自动补上，否则 uv 找不到 `git`

## 模型权重

权重不进 skill（small 486 MB、large-v3 3.1 GB），`--models` 只是转交已装好的 CLI：

```bash
python3 bootstrap.py --models small      # → <home>/models/small，之后 transcribe 完全离线
```

`--check` / `--plan` 只报告不下载；下载失败会把 CLI 的真实错误尾部写进 `notes` 并以 1 退出。
离线部署把 `<home>/models` 整个目录拷到别的机器，配 `PODCAST_KG_MODEL_DIR` 即可。

## 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 就绪（不管是本来就有的还是刚装的） |
| 1 | 未就绪 / 安装失败（`notes` 里带真实错误尾部） |
| 2 | 参数非法 |

## 环境变量

| 变量 | 作用 |
| --- | --- |
| `PODCAST_KG_HOME` | 运行时安装位置 |
| `PODCAST_KG_BIN` | 指定一个现成的 `podcast-kg` 可执行文件 |
| `PODCAST_KG_PYTHON` | 指定解释器（launcher 与 venv 都用它） |
