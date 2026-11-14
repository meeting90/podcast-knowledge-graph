#!/usr/bin/env python3
"""把知识卡聚成「话题弧」层，产出 <id>_arcs.json + <id>_arcs.html。

数据不跟代码一起入库：卡与精修稿都放在 `.outputs/`（被 .gitignore 忽略），
脚本本身只描述「怎么算」。换一批卡就换 --cards-dir。

用法：
  python build_arcs.py                       # 默认读 .outputs，写到 .outputs/arcs
  python build_arcs.py --cards-dir D:/x/cards --out-dir D:/x/arcs

输入
  --cards-dir   知识卡目录（*.json，只认带 content_id 且有 claims 的）
  --curated     精修稿：{content_id: {arc_id: {title, summary, open_question, open_line}}}
                另可写 `_breaks: [{before: c69, at: "1:04:18"}]` 人工指定话题边界：
                停顿/分组/主持人轮转全都失效时用（例：主持人中途说「最后我问一个点」）
  --out-dir     产物目录（默认 <cards-dir>/arcs）

输出
  <out-dir>/<id>_arcs.json    弧层（给产品端：merge 回原卡后导入）
  <out-dir>/<id>_arcs.html    本地验收页（点一次连播一整段）
  <out-dir>/index.html        多期对照表
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills/podcast-knowledge-graph/lib"))
from podcast_kg.arcs import build_file  # noqa: E402
from podcast_kg.render_arcs import render  # noqa: E402

# 有转写稿的期次可以补「开场原话」（弧起点处那句话就是主持人开启话题的话）。
# 文件名按 content_id 对应，转写稿同样放在 .outputs/ 下，不入库。
TRANSCRIPT_DIR = ".outputs"

# 精修稿里能直接覆盖到弧本身的人工字段（不只影响 HTML，JSON 也要带上）
CURATED_FIELDS = ("title", "summary", "open_question", "open_line")


def _load_words(path: str) -> list[dict]:
    """词级时间戳：弧的起止点靠它对齐到词边界（没有这个文件就跳过对齐）。"""
    from podcast_kg.arcs import load_words

    words = load_words(path)
    print(f"  词级对齐：{len(words)} 个词（{os.path.basename(path)}）")
    return words


def apply_curated(data: dict, cur: dict) -> None:
    """把人工标题 / 摘要 / 开场问句写进弧本身，JSON 与 HTML 用同一份文字。"""
    for arc in data.get("arcs", []):
        entry = cur.get(arc.get("arc_id")) or {}
        for key in CURATED_FIELDS:
            if entry.get(key):
                arc[key] = entry[key]


def is_card(path: str) -> bool:
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and bool(data.get("content_id")) and bool(data.get("claims"))


def _mapped(content_id: str, kind: str) -> str | None:
    """按映射表找某类产物（transcript / words），也接受 `<content_id>_<kind>` 直推。

    映射表长这样（放在 .outputs/transcripts.json，随数据走、不入库）：
      {"xiaoyuzhoufm_20260328_296": "lijia_transcript.txt"}                # 老写法
      {"xiaoyuzhoufm_...": {"transcript": "x_transcript.txt", "words": "x_words.json"}}
    """
    fallbacks = {"transcript": ("_transcript.txt",), "words": ("_words.json",)}[kind]
    for base in (TRANSCRIPT_DIR, ".outputs"):
        mapping_path = os.path.join(base, "transcripts.json")
        if os.path.isfile(mapping_path):
            mapping = json.load(open(mapping_path, encoding="utf-8"))
            entry = mapping.get(content_id)
            names = []
            if isinstance(entry, dict):
                if entry.get(kind):
                    names.append(entry[kind])
            elif isinstance(entry, str) and kind == "transcript":
                # 老写法只有转写稿；词级文件靠同名替换推
                names.append(entry)
                for suffix in fallbacks:
                    if entry.endswith("_transcript.txt"):
                        names.append(entry.replace("_transcript.txt", suffix))
            elif isinstance(entry, str):
                for suffix in fallbacks:
                    if entry.endswith("_transcript.txt"):
                        names.append(entry.replace("_transcript.txt", suffix))
            for name in names:
                candidate = os.path.join(base, name)
                if os.path.isfile(candidate):
                    return candidate
        for suffix in fallbacks:
            direct = os.path.join(base, f"{content_id}{suffix}")
            if os.path.isfile(direct):
                return direct
    return None


def transcript_for(content_id: str) -> str | None:
    return _mapped(content_id, "transcript")


def words_for(content_id: str) -> str | None:
    """词级时间戳（`transcribe --words` 产出）：弧的时间戳靠它对齐到词边界。"""
    return _mapped(content_id, "words")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cards-dir", default=".outputs", help="知识卡目录（默认 %(default)s）")
    p.add_argument("--out-dir", default=None, help="产物目录（默认 <cards-dir>/arcs）")
    p.add_argument("--curated", default=None, help="精修稿 JSON（默认 <cards-dir>/arcs_curated.json）")
    args = p.parse_args()

    out_dir = args.out_dir or os.path.join(args.cards_dir, "arcs")
    curated_path = args.curated or os.path.join(args.cards_dir, "arcs_curated.json")
    curated = json.load(open(curated_path, encoding="utf-8")) if os.path.isfile(curated_path) else {}
    os.makedirs(out_dir, exist_ok=True)

    cards = [f for f in sorted(glob.glob(os.path.join(args.cards_dir, "*.json"))) if is_card(f)]
    if not cards:
        print(f"没有在 {args.cards_dir} 找到知识卡（需含 content_id 与 claims）", file=sys.stderr)
        return 1

    rows = []
    for path in cards:
        card = json.load(open(path, encoding="utf-8"))
        cid = card["content_id"]
        cur = curated.get(cid, {})
        words_path = words_for(cid)
        words = _load_words(words_path) if words_path else None
        data = build_file(path, transcript_for(cid), breaks=cur.get("_breaks"), words=words)
        apply_curated(data, cur)

        json.dump(
            data,
            open(os.path.join(out_dir, f"{cid}_arcs.json"), "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=2,
        )
        with open(os.path.join(out_dir, f"{cid}_arcs.html"), "w", encoding="utf-8") as fh:
            fh.write(render(data, curated=cur, source_label="话题弧版"))

        s = data["stats"]
        dur_min = (card["source"].get("duration_sec") or 1) / 60
        rows.append({
            "cid": cid,
            "title": card["source"]["title"][:34],
            "claims": s["claims"],
            "arcs": s["arcs"],
            "mc": s["median_claim_sec"],
            "ma": s["median_arc_sec"],
            "curated": len(cur),
            "density": s["claims"] / dur_min,
        })

    print(f"{'content_id':32s} {'claims':>6s} {'arcs':>5s} {'卡中位':>7s} {'弧中位':>8s} {'精修':>4s}  密度")
    for r in rows:
        print(f"{r['cid']:32s} {r['claims']:6d} {r['arcs']:5d} {r['mc']:6d}s "
              f"{r['ma'] // 60:5d}分{r['ma'] % 60:02d}s {r['curated']:5d}  {r['density']:.1f} 卡/10分钟")

    write_index(rows, out_dir)
    print("\n输出目录:", out_dir)
    return 0


def write_index(rows: list[dict], out_dir: str) -> None:
    head = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>话题弧 · 多期对照</title><style>",
        'body{margin:0;background:#f7f4ee;color:#1c1a17;font:16px/1.7 -apple-system,"Segoe UI","Noto Sans SC",sans-serif}',
        ".wrap{max-width:940px;margin:0 auto;padding:56px 20px 80px}",
        "h1{font-size:30px;margin:0 0 8px}p.lead{color:#6f6860;margin:0 0 32px}",
        "table{width:100%;border-collapse:collapse;background:#fffdf9;border:1px solid #e0d9cd;border-radius:12px;overflow:hidden}",
        "th,td{padding:12px 14px;text-align:left;border-bottom:1px solid #e0d9cd;font-size:14px}",
        "th{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#8a4b2a;background:#f4efe6}",
        "tr:last-child td{border-bottom:0}td.n{font-variant-numeric:tabular-nums}",
        "a{color:#8a4b2a;font-weight:600;text-decoration:none}a:hover{text-decoration:underline}",
        ".bad{color:#b03a2e}.good{color:#1f5d4c;font-weight:700}",
        "</style></head><body><div class=\"wrap\">",
        "<h1>话题弧 · 多期对照</h1>",
        '<p class="lead">逐句卡适合溯源，不适合阅读：相邻卡有 60–75% 间隔 ≤2 秒，本来就是同一段话被切开的。'
        "聚成话题弧之后，点一次就连播一整段（主持人开启话题 → 嘉宾讲完 → 自然收束）。</p>",
        "<table><tr><th>节目</th><th>逐句卡</th><th>卡中位</th><th>话题弧</th><th>弧中位</th>"
        "<th>覆盖密度</th><th>标题</th></tr>",
    ]
    for r in rows:
        head.append(
            f'<tr><td><a href="{r["cid"]}_arcs.html">{r["title"]}</a><br>'
            f'<span style="color:#9a9186;font-size:12px">{r["cid"]}</span></td>'
            f'<td class="n bad">{r["claims"]}</td><td class="n">{r["mc"]}s</td>'
            f'<td class="n good">{r["arcs"]}</td>'
            f'<td class="n">{r["ma"] // 60}分{r["ma"] % 60:02d}秒</td>'
            f'<td class="n">{r["density"]:.1f} 卡/10分钟</td>'
            f'<td class="n">{"✓ 人工" if r["curated"] else "自动"}</td></tr>'
        )
    head.append("</table></div></body></html>")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(head))


if __name__ == "__main__":
    raise SystemExit(main())
