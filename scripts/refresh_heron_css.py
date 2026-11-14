#!/usr/bin/env python3
"""刷新 `skills/podcast-knowledge-graph/lib/podcast_kg/assets/heron.css`：把 heronai.top 的站点样式取下来，字体子集内联。

为什么要有这个脚本
------------------
`render_card.py` 的 DOM 是照着站点逐类写的，样式也必须来自同一份文件，否则
「本地导出的页面」和线上就会慢慢漂开。样式是站点的构建产物（带 hash 的文件名），
所以不能手抄，只能按需重新拉一次。

用法
  python scripts/refresh_heron_css.py                      # 拉最新
  python scripts/refresh_heron_css.py --base https://heronai.top
  python scripts/refresh_heron_css.py --card xiaoyuzhoufm_20261029_6ae1e359

做的事
  1. 取一张详情页，从 <link rel=stylesheet> 里找到站点 CSS 的 URL；
  2. 把 CSS 里引用的 woff2 字体子集下载下来，转成 data URI 内联
     （只保留 latin / latin-ext；西里尔、希腊、越南语子集丢掉）；
  3. 写回 assets/heron.css。

产物是派生的，可以随时重跑；重跑后记得把样例卡重渲染一遍对比。
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import urllib.request
from urllib.parse import urljoin

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "skills/podcast-knowledge-graph/lib", "podcast_kg", "assets", "heron.css")


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "podcast-kg/refresh-css"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def find_css_url(base: str, card: str, html: str) -> str:
    m = re.search(r'<link rel="stylesheet" href="([^"]+\.css)"', html)
    if not m:
        raise SystemExit("详情页里没找到 stylesheet 链接")
    href = m.group(1)
    return href if href.startswith("http") else base.rstrip("/") + href


def inline_fonts(css: str, css_url: str) -> tuple[str, list[str]]:
    """把 @font-face 的 woff2 换成 data URI；其他语种子集整块丢掉。

    中文正文走系统中文字体，这几套西文字体真正起作用的是拉丁字母和数字，
    所以只留 latin（`U+??`）与 latin-ext（`U+100-2BA…`）两个子集。
    """
    kept: list[str] = []

    def rewrite(m: re.Match) -> str:
        block = m.group(0)
        url = re.search(r"url\(([^)]+)\)", block)
        if not url:
            return block
        path = url.group(1)
        if path.startswith("data:"):
            return block
        rng = re.search(r"unicode-range:([^}]+)", block)
        if rng and "U+??" not in rng.group(1) and not rng.group(1).startswith("U+100-2BA"):
            return ""
        data = base64.b64encode(get(urljoin(css_url, path))).decode()
        kept.append(os.path.basename(path))
        return block.replace(path, f"data:font/woff2;base64,{data}")

    return re.sub(r"@font-face\{[^}]*\}", rewrite, css), kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://heronai.top")
    ap.add_argument("--card", default="xiaoyuzhoufm_20261029_6ae1e359")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    html = get(f"{base}/cards/{args.card}").decode("utf-8", "replace")
    css_url = find_css_url(base, args.card, html)
    print("CSS:", css_url)
    css = get(css_url).decode("utf-8")

    css, fonts = inline_fonts(css, css_url)
    print("字体子集:", ", ".join(fonts) or "（无）")

    header = (
        "/* HERON 站点样式（自 https://heronai.top 取，内联字体子集后随包装配）\n"
        "   生成方式见 skills/podcast-knowledge-graph/lib/podcast_kg/assets/README.md；请勿手改。 */\n"
    )
    out = os.path.normpath(TARGET)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(header + css)
    print(f"写入 {out}（{os.path.getsize(out) // 1024} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
