"""HERON · outputs.py — 统一的输出目录约定

所有 CLI 命令的产物都写到**当前工作目录**下的 `.outputs/`：

    .outputs/
    ├── <audio>_transcript.json / .txt    转写稿
    ├── <content_id>.json / .md           知识卡（由 agent 写入）
    ├── <content_id>.html                 渲染出的观点页
    ├── <content_id>_graph.json           图谱快照
    ├── <content_id>.<lang>.json          译文卡（结构一致，只换文字）
    └── registry/                         实体 / 人物 / 概念注册表

显式传入输出路径时以传入路径为准。
"""
import os

OUTPUT_DIR = ".outputs"


def ensure(subdir=""):
    """创建输出目录（可带子目录），返回路径。"""
    d = os.path.join(OUTPUT_DIR, subdir) if subdir else OUTPUT_DIR
    os.makedirs(d, exist_ok=True)
    return d


def out_path(filename, subdir=""):
    """输出文件的默认路径：.outputs/[subdir/]filename"""
    return os.path.join(ensure(subdir), filename)


def stem(path):
    """取文件名主干（不含扩展名）。"""
    return os.path.splitext(os.path.basename(path))[0]


def ensure_parent(path):
    """确保显式输出路径的父目录存在。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path
