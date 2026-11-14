"""HERON · 知识卡 JSON → 单文件 HTML（与 heronai.top 详情页同一套 DOM 与样式）

版式来源
--------
样式直接从站点取（`assets/heron.css`，字体子集已内联），本文件只负责**按同样的
class 生成同样的结构**，所以本地导出的页面和 heronai.top/cards/<id> 看起来是同一版：

  顶栏 topbar → 卡片头 detail-hero（平台/日期、标题、人物、段数·观点数·原节目）
  → 工具条 om-bar（全部 / 我的推荐）→ 左侧 om-nav 主题导航 + 右侧话题弧 av-arc
  → 评论区 cm → 播放时浮出的 playerbar

两种阅读单位
------------
* 卡里有 `arcs`（HERON 把话题弧合回 `cards.card` 后就是这个形状）→ 每个分组下渲染
  `av-arc` 卡片：标题、摘要、听这段、证据条数；展开后是「主持人开场原话 → 这一段
  讲了什么（beats）→ 金句（points）→ 其余观点」，再往下才是逐句 claim。
* 卡里没有 `arcs` → 退回逐句视图（`om-row`），与 heron 的「全部观点」视图一致。

`podcast-kg render` 会自动旁挂 `<card>_arcs.json`（`build_arcs.py` 的产物），
也可以用 `--arcs PATH` 显式指定。
"""

from __future__ import annotations

import html
import json
import os
import re

REL_CN = {"supports": "支撑", "supported_by": "被支撑", "example_of": "例证", "exemplified_by": "例证于",
          "extends": "引申", "extended_by": "被引申", "deepens": "深化", "deepened_by": "被深化",
          "tension_with": "张力", "responds_to": "回应", "parallel": "并列", "implies": "推出",
          "precondition": "前提", "part_of": "属于", "echoes": "呼应", "echoed_by": "被呼应",
          "related": "关联", "contrast": "对比", "causes": "导致"}
REL_COLOR = {"supports": "#3b5bdb", "deepens": "#0b7285", "extends": "#2f9e44",
             "tension_with": "#c2255c", "responds_to": "#9c36b5", "parallel": "#e8590c",
             "implies": "#5f3dc4", "precondition": "#087f5b", "part_of": "#868e96",
             "echoes": "#1971c2", "exemplified_by": "#f08c00", "example_of": "#f08c00"}
# 与站点一致的分类色板（om-nav / om-dot 用）
GROUP_COLORS = ["#3b5bdb", "#0b7285", "#e8590c", "#2f9e44", "#9c36b5", "#c2255c", "#5f3dc4", "#087f5b"]

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = "https://heronai.top"

# ── 多语言 ───────────────────────────────────────────────────────────────────
# 渲染时用 `T()` 包住可翻译字段：字符串照旧输出；`{lang: text}` 输出成带
# `data-zh` / `data-en` 的 span，前端切语言只改 textContent，DOM 与 id 不变。
_LANGS: list[str] = ["zh"]
_DEFAULT = "zh"
LANG_LABEL = {"zh": "中文", "en": "EN"}

CHROME: dict[str, tuple[str, str]] = {
    "back": ("返回列表", "Back"),
    "submit": ("内容投稿", "Submit"),
    "theme": ("主题", "Theme"),
    "all": ("全部", "All"),
    "mine": ("我的推荐", "My picks"),
    "share": ("分享我的视图", "Share my view"),
    "export": ("导出 picks", "Export picks"),
    "export_title": ("把推荐导出成 JSON，回填到卡片", "Export picks as JSON"),
    "hint_arcs": ("共 {n} 段 · {m} 条观点（按话题弧分组）", "{n} segments · {m} claims, grouped by topic arcs"),
    "hint_claims": ("共 {m} 条观点，按主题分组", "{m} claims, grouped by theme"),
    "ungrouped": ("未入组 {n} 条", "{n} ungrouped"),
    "n_segments": ("{n} 段", "{n} segments"),
    "n_claims": ("{n} 条观点", "{n} claims"),
    "claims_count": ("{n} 观点", "{n} claims"),
    "original": ("原始节目 ↗", "Original episode ↗"),
    "mentioned": ("节目里提到的 {n} 人", "{n} people mentioned"),
    "nav": ("目录", "Contents"),
    "nav_count": ("目录 · {n} 段", "Contents · {n}"),
    "close": ("关闭", "Close"),
    "open_label": ("主持人开场原话", "Host's opening"),
    "beats_label": ("这一段讲了什么", "What this segment covers"),
    "points_label": ("金句 {n} 句", "{n} key quotes"),
    "rest_label": ("其余观点 {n} 条", "{n} more claims"),
    "evidence": ("语料", "Source line"),
    "listen": ("听这段", "Listen"),
    "auto_title": ("标题由算法截取，未经人工润色", "auto title"),
    "minutes": ("{n} 分钟", "{n} min"),
    "n_evidence": ("{n} 条证据", "{n} evidence"),
    "expand": ("展开这一段", "Expand"),
    "comments": ("评论", "Comments"),
    "comments_sub": ("看到某一集、某一段、某句话有想法，就在那里写下来。",
                     "Thoughts on an episode, a segment or a sentence? Write them there."),
    "comments_hint": ("本地导出的页面没有评论后端；想参与讨论请到 heronai.top 的这张卡。",
                      "This exported page has no comment backend; join the discussion on heronai.top."),
    "local_hint": ("本地导出的单文件页面：推荐存在你自己的浏览器里，不会上传；带推荐的链接可以直接分享给别人。",
                   "Single-file export: picks stay in your browser; shared links carry them along."),
    "player_pick": ("选一段开始听", "Pick a segment to start"),
    "player_redirect": ("点任一段的「听这段」复制定位提示", "Click “Listen” to copy a cue"),
    "empty": ("这张卡没有可展示的观点。", "No claims to show."),
    "lang_group": ("语言", "Language"),
    "filter": ("筛选", "Filter"),
    "all_claims": ("全部观点", "All claims"),
    "card_fallback": ("知识卡", "Knowledge card"),
    "description": ("{title} — HERON 知识卡：每个观点回溯到它被说出的那一秒。",
                    "{title} — HERON knowledge card: every claim links back to the second it was said."),
    "home": ("HERON 首页", "HERON home"),
    "pb_clip": ("片段 {a}–{b}", "clip {a}–{b}"),
    "pb_cont": ("继续播放", "continue"),
}


def C(key: str, **fmt) -> dict[str, str]:
    zh, en = CHROME[key]
    return {"zh": zh.format(**fmt) if fmt else zh, "en": en.format(**fmt) if fmt else en}


def set_langs(langs: list[str] | None, default: str | None = None) -> None:
    global _LANGS, _DEFAULT
    _LANGS = list(langs or ["zh"])
    _DEFAULT = default if default in _LANGS else _LANGS[0]


def _filled(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def TX(value) -> str:
    """取默认语言的纯文本（用于 JS 数据、属性）。"""
    if isinstance(value, dict):
        if _filled(value.get(_DEFAULT)):
            return value[_DEFAULT]
        for lang in _LANGS:
            if _filled(value.get(lang)):
                return value[lang]
        return ""
    return "" if value is None else str(value)


def T(value) -> str:
    """输出可翻译文本：纯字符串直接转义；多语言输出带 data-<lang> 的 span。"""
    if isinstance(value, dict):
        texts = {lang: value[lang] for lang in _LANGS if _filled(value.get(lang))}
        if not texts:
            return ""
        default = _DEFAULT if _DEFAULT in texts else next(iter(texts))
        attrs = " ".join(f'data-{lang}="{esc_attr(text)}"' for lang, text in texts.items())
        return f'<span class="i18n" {attrs}>{esc(texts[default])}</span>'
    return esc(value)


def T_ATTRS(value) -> str:
    """把多语言文本变成可挂在任意元素上的 `data-zh="…" data-en="…"`。"""
    if not isinstance(value, dict):
        return ""
    return " ".join(
        f'data-{lang}="{esc_attr(value[lang])}"'
        for lang in _LANGS
        if _filled(value.get(lang))
    )


def TA(value, attr: str = "title") -> str:
    """输出多语言属性：`title="当前语言" data-title-en="..."`。"""
    if not isinstance(value, dict):
        return f'{attr}="{esc_attr(value or "")}"'
    texts = {lang: value[lang] for lang in _LANGS if _filled(value.get(lang))}
    if not texts:
        return f'{attr}=""'
    default = _DEFAULT if _DEFAULT in texts else next(iter(texts))
    attrs = [f'{attr}="{esc_attr(texts[default])}"']
    attrs += [f'data-{attr}-{lang}="{esc_attr(text)}"' for lang, text in texts.items()]
    return " ".join(attrs)


# JS 侧文案：切换语言时 toast / 提示 / 播放条都要跟着变。
JS_I18N: dict[str, dict[str, str]] = {
    "zh": {
        "theme_dark": "切到深色", "theme_light": "切到浅色",
        "seg_all": "全部", "seg_mine": "我的推荐",
        "share": "分享我的视图", "export": "导出 picks",
        "mine_hint": "只看我推荐的，共 {n} 条",
        "mine_empty": "（还没推荐过，点 ★ 加入）",
        "n_segments": "{n} 段", "n_claims": "{n} 条观点",
        "play_title": "播放 {t} 这一段",
        "star_on": "已推荐 · 点击取消", "star_arc": "推荐这一段", "star_claim": "推荐这条观点",
        "expand": "展开这一段", "collapse": "收起",
        "player_pick": "选一段开始听",
        "no_audio": "这张卡没有可播放的音频地址，用「原始节目」去听",
        "autoplay": "浏览器拦了自动播放，点播放条 ▶ 即可",
        "finished": "这一段听完了",
        "share_done": "已复制：带推荐的链接",
        "export_done": "已导出 picks_{id}.json",
        "picks_view": "这是别人分享的推荐视图（{n} 条）",
        "locate": "定位：{where}　→ 到原平台拖到该处",
        "audio_err": "音频无法播放：{why}",
        "err_1": "加载被中断", "err_2": "网络错误", "err_3": "解码失败",
        "err_4": "格式不支持或地址不可达", "err_0": "未知错误",
        "pick_first": "先从上面选一段",
        "nav_more": "目录", "nav_close": "关闭",
    },
    "en": {
        "theme_dark": "Switch to dark", "theme_light": "Switch to light",
        "seg_all": "All", "seg_mine": "My picks",
        "share": "Share my view", "export": "Export picks",
        "mine_hint": "Only my picks · {n} total",
        "mine_empty": "(nothing yet — click ★ to add)",
        "n_segments": "{n} segments", "n_claims": "{n} claims",
        "play_title": "Play {t}",
        "star_on": "Recommended · click to remove", "star_arc": "Recommend this segment", "star_claim": "Recommend this claim",
        "expand": "Expand", "collapse": "Collapse",
        "player_pick": "Pick a segment to start",
        "no_audio": "This card has no playable audio; use “Original episode”",
        "autoplay": "Autoplay was blocked — press ▶ on the player bar",
        "finished": "Segment finished",
        "share_done": "Copied: link with your picks",
        "export_done": "Exported picks_{id}.json",
        "picks_view": "Shared picks view ({n} items)",
        "locate": "Cue: {where} → seek there on the source platform",
        "audio_err": "Audio failed: {why}",
        "err_1": "loading aborted", "err_2": "network error", "err_3": "decode failed",
        "err_4": "unsupported format or unreachable URL", "err_0": "unknown error",
        "pick_first": "Pick a segment above first",
        "nav_more": "Contents", "nav_close": "Close",
    },
}


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def esc_attr(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def js(obj) -> str:
    """嵌进 <script> 的 JSON：转义闭合标签，避免提前截断。"""
    text = json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")
    return text.replace("<!--", "<\\u0021--")


def strip_group_no(name):
    """「① 产品与工程」→「产品与工程」；多语言时逐语言处理。"""
    if isinstance(name, dict):
        return {lang: strip_group_no(text) for lang, text in name.items()}
    out = re.sub(r"^[\d①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]+[.\s、)）]?\s*", "", str(name or "")).strip()
    return out or str(name or "")


def to_sec(t) -> int:
    """`1:04:18.72` / `64:18` / `1:04:18` 都认；小数直接截断。"""
    q = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(t or ""))]
    if len(q) == 3:
        return int(q[0] * 3600 + q[1] * 60 + q[2])
    if len(q) == 2:
        return int(q[0] * 60 + q[1])
    return int(q[0]) if q else 0


def mmss(sec) -> str:
    sec = max(0, int(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def disp(stamp) -> str:
    """展示用时间戳：去掉词边界对齐带上的小数秒。"""
    text = str(stamp or "")
    return text.split(".")[0] if "." in text else text


def load_css() -> str:
    path = os.path.join(HERE, "assets", "heron.css")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# 站点上没有的部分：导出页专用的提示条与几处小修正。
LOCAL_CSS = """
.langsw{display:flex;align-items:center;border:1px solid currentColor;border-radius:99px;overflow:hidden;opacity:.85}
.langsw button{border:0;background:transparent;color:inherit;font:inherit;font-size:12px;
  padding:4px 10px;cursor:pointer;opacity:.7}
.langsw button[aria-pressed="true"]{background:var(--fg);color:var(--bg);opacity:1}
#toast{position:fixed;left:50%;bottom:92px;transform:translate(-50%,12px);z-index:60;
  background:var(--fg);color:var(--bg);border-radius:99px;padding:9px 18px;font-size:13px;
  max-width:min(560px,calc(100vw - 32px));text-align:center;pointer-events:none;
  opacity:0;transition:opacity .18s var(--ease-out),transform .18s var(--ease-out)}
#toast.show{opacity:1;transform:translate(-50%,0)}
/* 站点用 React 条件渲染：折叠时不输出正文。静态页把同一件事交给 CSS。 */
.av-arc-body{display:none}
.av-arc.open .av-arc-body{display:block}
.om-more{display:none}
.om-row.open .om-more{display:block}
.no-chrome .om-bar{display:none}
body.has-player .page{padding-bottom:150px}
@media(max-width:760px){nav.om-nav{position:sticky}}
"""


def load_segments(card: dict, seg_dir) -> tuple[dict, str]:
    """可选的内联音频片段：<seg_dir>/<claim_id>.mp3 → {claim_id: {b64, dur}}"""
    if not seg_dir or not os.path.isdir(seg_dir):
        return {}, card.get("source", {}).get("audio_url", "") or ""
    import base64

    out = {}
    for name in sorted(os.listdir(seg_dir)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in (".mp3", ".m4a", ".wav", ".opus", ".ogg"):
            continue
        with open(os.path.join(seg_dir, name), "rb") as fh:
            out[stem] = {"b64": base64.b64encode(fh.read()).decode(), "dur": 0}
    return out, ""


def build_groups(card: dict) -> list[tuple[str, str, list[str]]]:
    if card.get("groups"):
        return [(g["gid"], g["name"], list(g.get("ids", []))) for g in card["groups"]]
    return [("g1", "全部观点", [c["claim_id"] for c in card.get("claims", [])])]


def load_arcs(card: dict, explicit: str | None = None, card_path: str | None = None) -> list[dict]:
    """话题弧：卡的 `arcs` 字段 → `--arcs` 指定的文件 → 卡旁的 `<stem>_arcs.json`。

    HERON 那边是先把弧合回 `cards.card` 再存；本地跑时弧通常是 `build_arcs.py`
    写在兄弟文件里的，所以这里顺手旁挂一下，免得每次都要手动合。
    """
    if card.get("arcs"):
        return list(card["arcs"])
    candidates = []
    if explicit:
        candidates.append(explicit)
    if card_path:
        stem, _ = os.path.splitext(card_path)
        folder = os.path.dirname(card_path)
        candidates.append(stem + "_arcs.json")
        # build_arcs.py 默认把弧写到 <cards-dir>/arcs/
        candidates.append(os.path.join(folder, "arcs", os.path.basename(stem) + "_arcs.json"))
    for path in candidates:
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        arcs = data.get("arcs") if isinstance(data, dict) else data
        if arcs:
            return list(arcs)
    return []


def _people_split(card: dict):
    """host/guest 参与人 + mentioned（heron 把「提到的人」折叠在 details 里）。"""
    main, mentioned = [], []
    for p in card.get("people", []) or []:
        role = TX(p.get("role")).strip().lower()
        (main if role in ("host", "guest") else mentioned).append(p)
    if not main:  # 卡里没标角色时，别把所有人塞进折叠区
        main, mentioned = mentioned, []
    return main, mentioned


def _person_chip(p: dict) -> str:
    name = p.get("name") or p.get("person_id") or "?"
    return (
        '<span class="dh-person"><span class="dh-avatar" aria-hidden="true">'
        f'{esc(name[:1])}</span><span class="dh-pname">{esc(name)}</span>'
        + (f'<span class="dh-prole">{T(p.get("role"))}</span>' if p.get("role") else "")
        + "</span>"
    )


def _mentioned_chip(p: dict) -> str:
    name = p.get("name") or p.get("person_id") or "?"
    tip = p.get("identity") or p.get("org") or name
    if isinstance(tip, list):
        tip = "、".join(str(x) for x in tip)
    return (f'<span class="dh-person dh-person-muted" {TA(tip)}>'
            f'<span class="dh-pname">{esc(name)}</span></span>')


def _play_btn(kind: str, ident: str, label, stamp: str) -> str:
    label_html = f"<span>{T(label)}</span>" if label else ""
    return (
        f'<button type="button" class="om-playbtn" data-play="{esc_attr(kind)}:{esc_attr(ident)}" '
        f'data-stamp="{esc_attr(disp(stamp))}" title="">'
        '<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="none" '
        'aria-hidden="true"><path d="M8 5.14v13.72a1 1 0 0 0 1.53.85l10.29-6.86a1 1 0 0 0 '
        '0-1.7L9.53 4.29A1 1 0 0 0 8 5.14Z"></path></svg>'
        f'{label_html}<span class="num">{esc(disp(stamp))}</span></button>'
    )


def _star(kind: str, ident: str) -> str:
    return (
        f'<button type="button" class="om-star" data-star="{esc_attr(kind)}:{esc_attr(ident)}" title="">'
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M12 3.6l2.47 5 5.53.8-4 3.9.94 5.5L12 16.2l-4.94 2.6.94-5.5-4-3.9 '
        '5.53-.8 2.47-5Z"></path></svg></button>'
    )


def _chev(kind: str, ident: str, label: str) -> str:
    return (
        f'<button type="button" class="av-chev-btn" data-toggle="{esc_attr(kind)}:{esc_attr(ident)}" '
        f'aria-expanded="false">'
        '<span class="om-chev"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true"><path d="M9 5l7 7-7 7"></path></svg></span></button>'
    )


def claim_row(c: dict, speaker: str, rank=None, arc_id: str = "") -> str:
    """逐句观点行：与站点的 om-row / av-claim 同一结构。"""
    cid = c["claim_id"]
    stamp, end = disp(c.get("timestamp", "")), disp(c.get("end", ""))
    span = f"{stamp}–{end}" if (stamp and end) else (stamp or end)
    chips = "".join(
        f'<button type="button" class="om-relbtn" data-goto="{esc_attr(r.get("target") or "")}" '
        f'{TA(r.get("note") or "")}>'
        f'<i style="background:{REL_COLOR.get(r.get("type"), "#868e96")}"></i>'
        f'{esc(REL_CN.get(r.get("type"), r.get("type") or ""))} '
        f'<span class="num">{esc(r.get("target") or "")}</span></button>'
        for r in (c.get("relations") or [])
    )
    meta = " · ".join(x for x in (c.get("type"), c.get("confidence"), speaker) if x)
    meta_html = esc(meta) + (f' · {esc(span)}' if span else "")
    ev = c.get("evidence")
    ev_html = (f'<blockquote class="av-open-line"><span class="av-sub">{T(C("evidence"))}</span>{T(ev)}</blockquote>'
               if ev else "")
    return (
        f'<div class="om-row av-claim" id="claim-{esc_attr(cid)}" data-cid="{esc_attr(cid)}"'
        + (f' data-arc="{esc_attr(arc_id)}"' if arc_id else "")
        + '>'
        '<div class="om-row-h" data-toggle="claim:' + esc_attr(cid) + '" role="button" tabindex="0" '
        'aria-expanded="false">'
        + (f'<span class="ar-rank num">{rank}</span>' if rank else "")
        + f'<span class="om-title"><span class="om-cid num">{esc(cid)}</span>'
        f'{T(c.get("statement", ""))}</span>'
        + ("" if arc_id else _star("claim", cid))
        + (_play_btn("claim", cid, "", stamp) if stamp else "")
        + '<span class="om-chev"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true"><path d="M9 5l7 7-7 7"></path></svg></span>'
        "</div>"
        '<div class="om-more">'
        + (f'<div class="om-rels">{chips}</div>' if chips else "")
        + f'<div class="om-meta num">{meta_html}</div>{ev_html}'
        "</div></div>"
    )


def _arc_body(a: dict, claims: dict, people: dict) -> str:
    """展开后的弧内容：开场原话 → beats → 金句 → 其余观点。顺序与站点一致。"""
    out = ['<div class="av-arc-body">']
    if a.get("open_line"):
        out.append(f'<blockquote class="av-open-line"><span class="av-sub">{T(C("open_label"))}</span>'
                   f'{T(a["open_line"])}</blockquote>')

    beats = a.get("beats") or []
    if beats:
        out.append(f'<div class="av-beats"><div class="av-sub">{T(C("beats_label"))}</div>')
        for b in beats:
            out.append(f'<div class="av-beat"><span class="av-beat-at num">{esc(disp(b.get("at")))}</span>'
                       f'<span class="av-beat-gist">{T(b.get("gist", ""))}</span></div>')
        out.append("</div>")

    points = [p.get("claim_id") for p in (a.get("points") or []) if p.get("claim_id") in claims]
    evidence = [cid for cid in (a.get("evidence") or []) if cid in claims]
    rest = [cid for cid in evidence if cid not in set(points)]

    if points:
        out.append(f'<div class="av-points"><div class="av-sub">{T(C("points_label", n=len(points)))}</div>')
        for i, cid in enumerate(points, 1):
            c = claims[cid]
            out.append(claim_row(c, _name(people, c.get("speaker")), rank=i, arc_id=a["arc_id"]))
        out.append("</div>")
    if rest:
        out.append(f'<div class="av-points"><div class="av-sub">{T(C("rest_label", n=len(rest)))}</div>')
        for cid in rest:
            c = claims[cid]
            out.append(claim_row(c, _name(people, c.get("speaker")), arc_id=a["arc_id"]))
        out.append("</div>")
    out.append("</div>")
    return "".join(out)


def _name(people: dict, pid) -> str:
    return (people.get(pid) or {}).get("name") or (pid or "")


def arc_card(a: dict, claims: dict, people: dict) -> str:
    dur = a.get("duration_sec") or 0
    mins = TX(C("minutes", n=round(dur / 60))) if dur else ""
    n_ev = len([c for c in (a.get("evidence") or []) if c in claims])
    meta = " · ".join(x for x in (mins, TX(C("n_evidence", n=n_ev)) if n_ev else "") if x)
    auto = (a.get("title_source") == "auto")
    return (
        f'<article class="av-arc" id="arc-{esc_attr(a["arc_id"])}" data-arc="{esc_attr(a["arc_id"])}">'
        '<div class="av-arc-h" data-toggle="arc:' + esc_attr(a["arc_id"]) + '" role="button" '
        'tabindex="0" aria-expanded="false">'
        '<div class="av-arc-top"><span class="av-arc-id num">' + esc(a["arc_id"]) + "</span>"
        f'<h3 class="av-arc-title">{T(a.get("title", ""))}'
        + (f'<span class="av-auto" {TA(C("auto_title"))}>auto</span>' if auto else "")
        + "</h3></div>"
        + (f'<p class="av-arc-sum">{T(a["summary"])}</p>' if a.get("summary") else "")
        + '<div class="av-arc-actions">'
        + _play_btn("arc", a["arc_id"], C("listen"), a.get("start", ""))
        + (f'<span class="av-arc-meta num">{esc(meta)}</span>' if meta else "")
        + _star("arc", a["arc_id"])
        + _chev("arc", a["arc_id"], "")
        + "</div></div>"
        + _arc_body(a, claims, people)
        + "</article>"
    )


def _nav_items(items: list[tuple[str, str, int, str]]) -> tuple[str, str, str]:
    """返回 (strip 里的 a 标签, 更多按钮, sheet 内容)。"""
    links = "".join(
        f'<a href="#{esc_attr(sid)}"><i style="background:{color}"></i>{esc(name)}'
        f'<em class="num">{n}</em></a>'
        for sid, name, n, color in items
    )
    more = (
        '<button type="button" class="om-nav-more" id="navmore" aria-expanded="false" '
        f'aria-controls="navsheet">{T(C("nav"))} <span class="num">{len(items)}</span>'
        '<svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">'
        '<path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.6"></path></svg>'
        "</button>"
    )
    sheet = (
        '<div class="om-nav-sheet" id="navsheet" hidden><div class="om-nav-sheet-h">'
        f'<span>{T(C("nav_count", n=len(items)))}</span>'
        f'<button type="button" class="om-nav-sheet-x" id="navsheetx" {TA(C("close"), "aria-label")}>✕</button>'
        f"</div>{links}</div>"
    )
    return links, more, sheet


JS = r"""
const D = __DATA__;
const I18N = __I18N__;
const LANGS = __LANGS__;
const DEFAULT_LANG = __DEFAULT_LANG__;
const DOC_TITLES = __DOC_TITLES__;
const REDIRECT = __REDIRECT__;
let LANG = DEFAULT_LANG;
function t(key, vars) {
  const table = I18N[LANG] || I18N[DEFAULT_LANG] || {};
  let s = table[key];
  if (s === undefined) s = (I18N[DEFAULT_LANG] || {})[key];
  if (s === undefined) return key;
  if (vars) Object.keys(vars).forEach(k => { s = s.split('{' + k + '}').join(vars[k]); });
  return s;
}
function pick(v) {
  if (v && typeof v === 'object' && !Array.isArray(v))
    return v[LANG] || v[DEFAULT_LANG] || Object.values(v)[0] || '';
  return v == null ? '' : String(v);
}
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const fmt = (x) => { x = Math.max(0, Math.floor(x || 0)); const h = Math.floor(x / 3600),
  m = Math.floor(x % 3600 / 60), s = x % 60;
  return h ? h + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0')
           : m + ':' + String(s).padStart(2, '0'); };
const STORE = 'heron-picks:' + D.content_id;

/* ---------- 语言切换（单页双语，DOM 与 id 不变） ---------- */
function applyLang(lang, save) {
  LANG = LANGS.indexOf(lang) >= 0 ? lang : DEFAULT_LANG;
  document.documentElement.lang = LANG === 'zh' ? 'zh-CN' : LANG;
  document.documentElement.dataset.lang = LANG;
  $$('[data-' + LANG + ']').forEach(el => {
    el.textContent = el.getAttribute('data-' + LANG);
  });
  $$('[data-title-' + LANG + ']').forEach(el => {
    el.title = el.getAttribute('data-title-' + LANG);
  });
  $$('[data-aria-label-' + LANG + ']').forEach(el => {
    el.setAttribute('aria-label', el.getAttribute('data-aria-label-' + LANG));
  });
  $$('.langsw button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.lang === LANG)));
  $$('[data-play]').forEach(b => {
    if (b.dataset.stamp) b.title = t('play_title', { t: b.dataset.stamp });
  });
  $$('.av-chev-btn').forEach(b => {
    b.setAttribute('aria-label', t(b.getAttribute('aria-expanded') === 'true' ? 'collapse' : 'expand'));
  });
  if (DOC_TITLES[LANG]) document.title = DOC_TITLES[LANG];
  if (cur) $('#pb-stmt').textContent = pick(cur.statement);
  if (save !== false) { try { localStorage.setItem('heron-lang', LANG); } catch (e) {} }
  paintTheme();
  if (typeof paintPicks === 'function') paintPicks();
}

/* ---------- 主题（与站点同 key，切过去也认得） ---------- */
function paintTheme() {
  const cur = document.documentElement.dataset.theme;
  const dark = cur ? cur === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const b = $('#themebtn');
  if (b) b.title = dark ? t('theme_light') : t('theme_dark');
  if (b) b.dataset.dark = dark ? '1' : '';
}
function toggleTheme() {
  const root = document.documentElement, cur = root.dataset.theme;
  const dark = cur ? cur === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  root.dataset.theme = dark ? 'light' : 'dark';
  try { localStorage.setItem('heron-theme', root.dataset.theme); } catch (e) {}
  paintTheme();
}

/* ---------- 推荐（本地存储；站点那边是账号，这里是同一套按钮） ---------- */
let picks = [];
try { picks = JSON.parse(localStorage.getItem(STORE) || '[]') || []; } catch (e) { picks = []; }
function hasPick(kind, id) { return picks.some(p => p.kind === kind && p.id === id); }
function togglePick(kind, id) {
  const i = picks.findIndex(p => p.kind === kind && p.id === id);
  if (i >= 0) picks.splice(i, 1);
  else picks.push({ kind: kind, id: id, at: new Date().toISOString() });
  try { localStorage.setItem(STORE, JSON.stringify(picks)); } catch (e) {}
  paintPicks();
}
function unitStar(el) {
  /* 弧级 / 逐句行级各有一颗星；弧内的证据行不参与筛选。 */
  const b = el.matches('.av-arc') ? $('.av-arc-actions [data-star]', el)
                                  : $('.om-row-h [data-star]', el);
  return b ? b.dataset.star.split(':') : null;
}
function paintPicks() {
  const mine = document.body.classList.contains('mine-mode');
  $$('[data-star]').forEach(b => {
    const [k, id] = b.dataset.star.split(':');
    const on = hasPick(k, id);
    b.classList.toggle('on', on);
    b.title = on ? t('star_on') : (k === 'arc' ? t('star_arc') : t('star_claim'));
  });
  const mc = $('#minecount'); if (mc) mc.textContent = picks.length;
  ['#sharebtn', '#exportbtn'].forEach(sel => { const b = $(sel); if (b) b.hidden = picks.length === 0; });
  let total = 0;
  $$('.om-section').forEach(sec => {
    let visible = 0;
    $$('.av-arc, .om-row[data-cid]', sec).forEach(el => {
      if (el.parentElement.closest('.om-row')) return;   // 弧内的证据行
      const key = unitStar(el);
      const keep = !mine || (key ? hasPick(key[0], key[1]) : false);
      el.hidden = !keep;
      if (keep) visible++;
    });
    sec.hidden = visible === 0;
    total += visible;
    const small = $('.om-sh small', sec);
    if (small) {
      const unit = small.dataset.unit === 'arc' ? 'n_segments' : 'n_claims';
      small.textContent = t(unit, { n: mine ? visible : (+small.dataset.count || 0) });
    }
  });
  const hint = $('#omhint');
  if (hint) hint.textContent = mine
    ? t('mine_hint', { n: picks.length }) + (total === 0 ? t('mine_empty') : '')
    : (hint.getAttribute('data-' + LANG) || '');
}
function setMine(mine) {
  document.body.classList.toggle('mine-mode', mine);
  $$('.om-seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mine === String(mine))));
  paintPicks();
}
function shareView() {
  const url = location.href.split('#')[0] + '#picks=' + picks.map(p => p.id).join(',');
  const done = () => toast(t('share_done'));
  if (navigator.clipboard && navigator.clipboard.writeText)
    navigator.clipboard.writeText(url).then(done).catch(() => { location.hash = 'picks=' + picks.map(p => p.id).join(','); done(); });
  else { location.hash = 'picks=' + picks.map(p => p.id).join(','); done(); }
}
function exportPicks() {
  const rows = picks.map(p => {
    const a = D.arcs[p.id];
    return p.kind === 'arc' ? { arc_id: p.id, title: a ? pick(a.title) : '' } : { claim_id: p.id };
  });
  const body = JSON.stringify({ content_id: D.content_id, picks: rows }, null, 2);
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([body], { type: 'application/json' }));
  a.download = 'picks_' + D.content_id + '.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  toast(t('export_done', { id: D.content_id }));
}

/* ---------- 展开 / 折叠 ---------- */
function toggleBox(el, open) {
  const [kind, id] = el.dataset.toggle.split(':');
  const host = el.closest('.av-arc, .om-row');
  const state = open === undefined ? !host.classList.contains('open') : open;
  host.classList.toggle('open', state);
  el.setAttribute('aria-expanded', String(state));
  const chev = $('.om-chev', el); if (chev) chev.classList.toggle('open', state);
  if (el.classList.contains('av-chev-btn')) el.setAttribute('aria-label', t(state ? 'collapse' : 'expand'));
}
function flash(el) {
  if (!el) return;
  el.classList.remove('om-flash'); void el.offsetWidth; el.classList.add('om-flash');
  setTimeout(() => el.classList.remove('om-flash'), 1700);
}
function scrollTo(el) {
  if (!el) return;
  const bars = ['.topbar', '.om-bar'].map(s => $(s)).filter(Boolean)
    .map(x => x.getBoundingClientRect().bottom);
  const top = el.getBoundingClientRect().top + window.scrollY - Math.max(0, ...bars) - 12;
  window.scrollTo({ top: top, behavior: 'smooth' });
}
function gotoClaim(cid) {
  const el = $('#claim-' + cid); if (!el) return;
  const arc = el.closest('.av-arc');
  if (arc && !arc.classList.contains('open')) {
    const head = $('.av-arc-h', arc); if (head) toggleBox(head, true);
  }
  const head = $('.om-row-h', el); if (head) toggleBox(head, true);
  scrollTo(el); flash(el);
}

/* ---------- 音频 ---------- */
const au = $('#au');
const bar = $('#playerbar');
let cur = null, blobCache = {};
function segSrc(cid) {
  if (blobCache[cid]) return blobCache[cid];
  const s = D.segs[cid]; if (!s || !s.b64) return null;
  try {
    const bin = atob(s.b64), n = bin.length, buf = new Uint8Array(n);
    for (let i = 0; i < n; i++) buf[i] = bin.charCodeAt(i);
    blobCache[cid] = URL.createObjectURL(new Blob([buf], { type: 'audio/mpeg' }));
    return blobCache[cid];
  } catch (e) { return null; }
}
function play(kind, id) {
  const item = (kind === 'arc' ? D.arcs[id] : D.claims[id]) || {};
  const start = __TO_SEC__(item.start || item.timestamp || '0:00');
  const end = __TO_SEC__(item.end || '') || 0;
  const rawStatement = kind === 'arc' ? (item.title || id) : (item.statement || id);
  const statement = pick(rawStatement);
  if (REDIRECT || !au) { locate(kind, id, item); return; }
  $$('.av-arc.playing, .om-row.playing').forEach(x => x.classList.remove('playing'));
  const host = (kind === 'arc' ? $('#arc-' + id) : $('#claim-' + id));
  if (host) host.classList.add('playing');
  cur = { kind: kind, id: id, start: start, end: end > start ? end : 0, statement: rawStatement };
  bar.hidden = false; document.body.classList.add('has-player');
  $('#pb-stmt').textContent = statement;
  const seg = kind === 'claim' ? segSrc(id) : null;
  const src = seg || D.audio;
  if (!src) { toast(t('no_audio')); bar.hidden = true; return; }
  if (au.getAttribute('src') !== src) {
    au.src = src;
    au.addEventListener('loadedmetadata', () => {
      try { au.currentTime = seg ? 0 : start; } catch (e) {}
      const p = au.play(); if (p && p.catch) p.catch(() => toast(t('autoplay')));
    }, { once: true });
    au.load();
  } else {
    try { au.currentTime = seg ? 0 : start; } catch (e) {}
    const p = au.play(); if (p && p.catch) p.catch(() => toast(t('autoplay')));
  }
  sync();
}
function locate(kind, id, item) {
  const mins = Math.round(__TO_SEC__(item.timestamp || item.start || '0:00') / 60);
  const txt = (D.platform || '原平台') + (D.series ? '《' + D.series + '》' : '')
    + ' 约第 ' + mins + ' 分钟（' + (item.timestamp || item.start || '') + '）';
  const say = () => toast(t('locate', { where: txt }));
  if (navigator.clipboard && navigator.clipboard.writeText)
    navigator.clipboard.writeText(txt).then(say).catch(say);
  else say();
}
function sync() {
  if (!au) return;
  const total = au.duration || D.duration || 0;
  const now = au.currentTime || 0;
  $('#pb-fill').style.width = (total > 0 ? Math.min(100, now / total * 100) : 0) + '%';
  const clip = $('#pb-clip');
  if (cur && cur.end && total > 0) {
    clip.style.display = 'block';
    clip.style.left = (cur.start / total * 100) + '%';
    clip.style.width = Math.max(0.4, (cur.end - cur.start) / total * 100) + '%';
  } else { clip.style.display = 'none'; }
  $('#pb-time').textContent = fmt(now) + ' / ' + fmt(total)
    + (cur ? (cur.end ? ' · ' + t('pb_clip', { a: fmt(cur.start), b: fmt(cur.end) })
                       : ' · ' + t('pb_cont')) : '');
  $('#pb-toggle').innerHTML = (au.paused || au.ended)
    ? '<svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.14v13.72a1 1 0 0 0 1.53.85l10.29-6.86a1 1 0 0 0 0-1.7L9.53 4.29A1 1 0 0 0 8 5.14Z"/></svg>'
    : '<svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4h3.4v16H7zM13.6 4H17v16h-3.4z"/></svg>';
}
if (au) {
  au.addEventListener('timeupdate', () => {
    if (cur && cur.end && au.currentTime >= cur.end) {
      au.pause(); toast(t('finished'));
      const host = cur.kind === 'arc' ? $('#arc-' + cur.id) : $('#claim-' + cur.id);
      if (host) host.classList.remove('playing');
      cur.end = 0; cur.start = au.currentTime;
    }
    sync();
  });
  ['play', 'pause', 'ended', 'loadedmetadata'].forEach(ev => au.addEventListener(ev, sync));
  au.addEventListener('error', () => {
    const code = au.error ? au.error.code : 0;
    const why = t('err_' + code) === 'err_' + code ? t('err_0') : t('err_' + code);
    toast(t('audio_err', { why: why }));
  });
}

/* ---------- 目录（窄屏抽屉） ---------- */
function toggleSheet(open) {
  const sheet = $('#navsheet'), btn = $('#navmore'); if (!sheet) return;
  const state = open === undefined ? sheet.hidden : open;
  sheet.hidden = !state;
  if (btn) { btn.setAttribute('aria-expanded', String(state)); }
}

/* ---------- 提示 ---------- */
let toastTimer = null;
function toast(msg) {
  const t = $('#toast'); if (!t) return;
  t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2400);
}

/* ---------- 深链： #arc-a03 / #claim-c21 / #picks=a01,c05 ---------- */
function openHash() {
  const raw = decodeURIComponent((location.hash || '').replace(/^#/, '')).trim();
  if (!raw) return;
  if (raw.startsWith('picks=')) {
    const ids = raw.slice(6).split(',').map(s => s.trim()).filter(Boolean);
    picks = ids.map(id => ({ kind: D.arcs[id] ? 'arc' : 'claim', id: id }));
    try { localStorage.setItem(STORE, JSON.stringify(picks)); } catch (e) {}
    paintPicks(); setMine(true); toast(t('picks_view', { n: picks.length }));
    return;
  }
  const arc = D.arcs[raw] ? raw : (D.claims[raw] ? D.claims[raw].arc_id : null);
  if (D.claims[raw]) { gotoClaim(raw); return; }
  if (arc) {
    const el = $('#arc-' + arc); if (!el) return;
    const head = $('.av-arc-h', el); if (head) toggleBox(head, true);
    scrollTo(el); flash(el);
  }
}

/* ---------- 事件绑定 ---------- */
document.addEventListener('click', (ev) => {
  const star = ev.target.closest('[data-star]');
  if (star) {
    ev.stopPropagation();
    const [k, id] = star.dataset.star.split(':');
    togglePick(k, id); return;
  }
  const playBtn = ev.target.closest('[data-play]');
  if (playBtn) {
    ev.stopPropagation();
    const [k, id] = playBtn.dataset.play.split(':');
    play(k, id); return;
  }
  const rel = ev.target.closest('[data-goto]');
  if (rel) { ev.stopPropagation(); gotoClaim(rel.dataset.goto); return; }
  const tgl = ev.target.closest('[data-toggle]');
  if (tgl) { toggleBox(tgl); return; }
  const nav = ev.target.closest('#navmore'); if (nav) { toggleSheet(); return; }
  const navx = ev.target.closest('#navsheetx'); if (navx) { toggleSheet(false); return; }
  const navLink = ev.target.closest('#navsheet a'); if (navLink) toggleSheet(false);
  const langBtn = ev.target.closest('[data-lang]');
  if (langBtn) { applyLang(langBtn.dataset.lang); return; }
  const seg = ev.target.closest('.om-seg button');
  if (seg) { setMine(seg.dataset.mine === 'true'); return; }
});
document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Enter' && ev.key !== ' ') return;
  const tgl = ev.target.closest('[data-toggle]');
  if (tgl) { ev.preventDefault(); toggleBox(tgl); }
});
if ($('#themebtn')) $('#themebtn').addEventListener('click', toggleTheme);
if ($('#sharebtn')) $('#sharebtn').addEventListener('click', shareView);
if ($('#exportbtn')) $('#exportbtn').addEventListener('click', exportPicks);
if ($('#pb-toggle')) $('#pb-toggle').addEventListener('click', () => {
  if (!au || !au.src) { toast(t('pick_first')); return; }
  if (au.paused) { const p = au.play(); if (p && p.catch) p.catch(() => {}); } else au.pause();
});
if ($('#pb-track')) $('#pb-track').addEventListener('click', (ev) => {
  if (!au || !au.duration) return;
  const r = ev.currentTarget.getBoundingClientRect();
  try { au.currentTime = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * au.duration; } catch (e) {}
  sync();
});
window.addEventListener('hashchange', openHash);
let savedLang = null;
try { savedLang = localStorage.getItem('heron-lang'); } catch (e) {}
applyLang(savedLang || DEFAULT_LANG, false);
openHash();
"""


def render(
    card: dict,
    seg_dir=None,
    mode="audio",
    chrome=True,
    arcs=None,
    langs: list[str] | None = None,
    default_lang: str | None = None,
) -> str:
    """mode="audio"    自绘播放器（整集流播，或 `--seg` 目录的内联片段）
       mode="redirect" 纯导流：不内联音频、不发音频请求，点时间戳只复制定位提示
       arcs             话题弧列表；给了就按弧渲染，否则退回逐句视图
       langs/default_lang  多语言代码；不传就是单语（中文）"""
    set_langs(langs, default_lang)
    segs_map, full_url = load_segments(card, seg_dir)
    redirect = mode == "redirect"
    if redirect:
        segs_map, full_url = {}, ""

    src = card.get("source", {}) or {}
    claims_list = card.get("claims", []) or []
    claims = {c["claim_id"]: c for c in claims_list}
    people = {p["person_id"]: p for p in card.get("people", []) or []}
    title = src.get("title") or card.get("content_id") or C("card_fallback")
    title_text = TX(title)
    content_id = card.get("content_id") or src.get("content_id") or ""

    groups = build_groups(card)
    used = {cid for _, _, ids in groups for cid in ids if cid in claims}
    missing = [c["claim_id"] for c in claims_list if c["claim_id"] not in used]
    if missing:
        groups.append(("gx", C("ungrouped", n=len(missing)), missing))

    arc_list = [a for a in (arcs or []) if a.get("arc_id")]
    arc_by_id = {a["arc_id"]: a for a in arc_list}
    title_of_claim_arc = {}
    for a in arc_list:
        for cid in (a.get("evidence") or []):
            title_of_claim_arc[cid] = a["arc_id"]

    sections = []
    items: list[tuple[str, str, int, str]] = []   # (锚点, 组名, 段/条数, 颜色)
    placed_arcs: set[str] = set()
    for gi, (gid, gname, ids) in enumerate(groups):
        color = GROUP_COLORS[gi % len(GROUP_COLORS)]
        name = strip_group_no(gname)
        sid = f"s-arc-{gi}" if arc_list else f"s-{gid}"
        if arc_list:
            # 一个分组里的弧 = 该组 claim 所属的弧（保住顺序）。
            # 同一弧的 claim 可能横跨两个分组，但弧只能出现一次——先匹配到哪组就归哪组，
            # 否则同一段会在两个标题下重复出现。
            arc_ids = []
            for cid in ids:
                aid = title_of_claim_arc.get(cid)
                if aid and aid not in placed_arcs and aid not in arc_ids:
                    arc_ids.append(aid)
            if not arc_ids:
                continue
            placed_arcs.update(arc_ids)
            body = "".join(arc_card(arc_by_id[aid], claims, people) for aid in arc_ids)
            count, unit = len(arc_ids), "arc"
        else:
            ids_in = [cid for cid in ids if cid in claims]
            if not ids_in:
                continue
            body = "".join(claim_row(claims[cid], _name(people, claims[cid].get("speaker")))
                           for cid in ids_in)
            count, unit = len(ids_in), "claim"
        items.append((sid, name, count, color))
        label = C("n_segments" if unit == "arc" else "n_claims", n=count)
        sections.append(
            f'<section id="{esc_attr(sid)}" class="om-section" data-mine="1">'
            f'<div class="om-sh"><span class="om-dot" style="background:{color}"></span>'
            f'<h2>{T(name)}</h2>'
            f'<small data-count="{count}" data-unit="{unit}">{T(label)}</small></div>{body}</section>'
        )

    # ── 卡片头 ──
    kicker = (f'<span class="dh-platform">{esc(src.get("platform") or "PODCAST")}</span>'
              + (f'<time class="dh-date num">{esc(src.get("published_at"))}</time>'
                 if src.get("published_at") else ""))
    main_people, mentioned = _people_split(card)
    people_html = "".join(_person_chip(p) for p in main_people)
    mentioned_html = ""
    if mentioned:
        mentioned_html = (
            f'<details class="dh-mentioned"><summary>{T(C("mentioned", n=len(mentioned)))}</summary>'
            f'<div class="dh-people dh-people-sub">'
            + "".join(_mentioned_chip(p) for p in mentioned) + "</div></details>")

    n_units = len(arc_list) if arc_list else len(claims_list)
    stats = (
        f'<span>{T(C("n_segments" if arc_list else "n_claims", n=n_units))}</span>'
        f'<span>{T(C("claims_count", n=len(claims_list)))}</span>'
    )
    if src.get("url"):
        stats += (f'<a class="dh-link" href="{esc_attr(src["url"])}" target="_blank" '
                  f'rel="noopener noreferrer">{T(C("original"))}</a>')

    # ── 工具条 ──
    n_arcs_hint = (
        C("hint_arcs", n=len(arc_list), m=len(claims_list))
        if arc_list
        else C("hint_claims", m=len(claims_list))
    )
    bar_html = ""
    if chrome:
        bar_html = (
            '<div class="om-bar"><div class="om-bar-row">'
            f'<div class="om-seg" role="group" {TA(C("filter"), "aria-label")}>'
            f'<button type="button" data-mine="false" aria-pressed="true">{T(C("all"))}</button>'
            f'<button type="button" data-mine="true" aria-pressed="false">{T(C("mine"))} '
            '<span class="num" id="minecount">0</span></button></div>'
            f'<button type="button" class="om-share" id="sharebtn" hidden>{T(C("share"))}</button>'
            f'<button type="button" class="om-share" id="exportbtn" hidden {TA(C("export_title"))}>{T(C("export"))}</button>'
            f'<span class="om-hint" id="omhint" {T_ATTRS(n_arcs_hint)}>{esc(TX(n_arcs_hint))}</span>'
            "</div></div>")

    nav_strip, nav_more, nav_sheet = _nav_items(items)

    # ── 评论区（站点是登录后可用；本地页只留位置，避免版式缺一块） ──
    cm_html = (
        f'<section class="cm" id="comments"><div class="cm-chd"><h2>{T(C("comments"))}</h2></div>'
        f'<p class="cm-sub">{T(C("comments_sub"))}</p>'
        f'<div class="rec-login-hint">{T(C("comments_hint"))} '
        f'<a href="{SITE}/cards/{esc_attr(content_id)}" target="_blank" rel="noopener" '
        'style="color:var(--accent)">heronai.top</a></div></section>')

    # ── 播放条 ──
    if redirect:
        player = (
            '<div class="playerbar" id="playerbar" hidden>'
            '<button type="button" class="pb-toggle" id="pb-toggle" aria-label="播放/暂停">▶</button>'
            f'<div class="pb-info"><div class="pb-stmt" id="pb-stmt">{T(C("player_redirect"))}</div>'
            '<div class="pb-track" id="pb-track"><div class="pb-clip" id="pb-clip" style="display:none"></div>'
            '<div class="pb-fill" id="pb-fill"></div></div>'
            '<div class="pb-time" id="pb-time">0:00</div></div></div>'
            f'<a class="dh-link" href="{esc_attr(src.get("url", ""))}" target="_blank" rel="noopener" '
            'style="display:block;margin-top:24px">完整节目 ↗</a>')
    else:
        player = (
            '<div class="playerbar" id="playerbar" hidden>'
            '<button type="button" class="pb-toggle" id="pb-toggle" aria-label="播放/暂停">'
            '<svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
            '<path d="M8 5.14v13.72a1 1 0 0 0 1.53.85l10.29-6.86a1 1 0 0 0 0-1.7L9.53 4.29A1 1 0 0 0 8 5.14Z"/></svg>'
            "</button>"
            f'<div class="pb-info"><div class="pb-stmt" id="pb-stmt">{T(C("player_pick"))}</div>'
            '<div class="pb-track" id="pb-track"><div class="pb-clip" id="pb-clip" '
            'style="display:none"></div><div class="pb-fill" id="pb-fill"></div></div>'
            '<div class="pb-time" id="pb-time">0:00</div></div>'
            '<audio id="au" preload="metadata"></audio></div>')

    # ── JS 数据 ──
    claims_js = {
        cid: {
            "statement": c.get("statement", ""),
            "timestamp": c.get("timestamp", ""),
            "end": c.get("end", ""),
            "type": c.get("type", ""),
            "arc_id": title_of_claim_arc.get(cid, ""),
        }
        for cid, c in claims.items()
    }
    arcs_js = {a["arc_id"]: {"title": a.get("title", ""), "summary": a.get("summary", ""),
                             "start": a.get("start", ""), "end": a.get("end", "")}
               for a in arc_list}
    data = {
        "content_id": content_id,
        "arcs": arcs_js,
        "claims": claims_js,
        "segs": segs_map,
        "audio": full_url,
        "duration": int(src.get("duration_sec") or 0),
        "platform": src.get("platform", ""),
        "series": src.get("series", ""),
    }
    doc_titles = {}
    for code in _LANGS:
        text = title.get(code) if isinstance(title, dict) else title
        doc_titles[code] = f"{text or title_text or content_id} · HERON"
    scripts = (JS.replace("__DATA__", js(data))
                 .replace("__I18N__", js(JS_I18N))
                 .replace("__LANGS__", js(_LANGS))
                 .replace("__DEFAULT_LANG__", js(_DEFAULT))
                 .replace("__DOC_TITLES__", js(doc_titles))
                 .replace("__REDIRECT__", "true" if redirect else "false")
                 .replace("__TO_SEC__", "toSec"))
    scripts = ("function toSec(t){const q=String(t||'').match(/\\d+(?:\\.\\d+)?/g)||[];"
               "const n=q.map(Number);"
               "return n.length===3?Math.round(n[0]*3600+n[1]*60+n[2]):"
               "(n.length===2?Math.round(n[0]*60+n[1]):Math.round(n[0]||0))}\n") + scripts

    title_js = (f"<script>try{{var m=localStorage.getItem('heron-theme');"
                "if(m==='light'||m==='dark')document.documentElement.setAttribute('data-theme',m);"
                "var l=localStorage.getItem('heron-lang');"
                "if(l){document.documentElement.lang=(l==='zh'?'zh-CN':l);"
                "document.documentElement.dataset.lang=l}}"
                "catch(e){}</script>")
    body_cls = "" if chrome else "no-chrome"

    lang_switch = ""
    if len(_LANGS) > 1:
        buttons = "".join(
            f'<button type="button" data-lang="{esc_attr(code)}" '
            f'aria-pressed="{"true" if code == _DEFAULT else "false"}">'
            f"{esc(LANG_LABEL.get(code, code.upper()))}</button>"
            for code in _LANGS
        )
        lang_switch = (
            f'<div class="langsw" role="group" {TA(C("lang_group"), "aria-label")}>'
            f"{buttons}</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="{'zh-CN' if _DEFAULT == 'zh' else _DEFAULT}" data-lang="{esc_attr(_DEFAULT)}" class="VNkuCW_variable VxV-Ta_variable">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#101012" media="(prefers-color-scheme: dark)">
<title>{esc(doc_titles[_DEFAULT])}</title>
<meta name="description" content="{esc(TX(C("description", title=title_text)))}">
{title_js}
<style>{load_css()}{LOCAL_CSS}</style>
</head>
<body class="{body_cls}">
<header class="topbar">
  <h1 class="brand" role="button" tabindex="0" {TA(C("home"), "aria-label")}>{esc("HERON")}</h1>
  <div class="topbar-right">
    {lang_switch}
    <a class="topbar-submit" href="{SITE}/submit" target="_blank" rel="noopener noreferrer">{T(C("submit"))}</a>
    <button type="button" class="um-trigger" id="themebtn" aria-label="theme">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"></circle><path d="M12 2.6v2.2M12 19.2v2.2M2.6 12h2.2M19.2 12h2.2M5.4 5.4l1.6 1.6M17 17l1.6 1.6M18.6 5.4L17 7M7 17l-1.6 1.6"></path></svg>
      <span class="um-trigger-label">{T(C("theme"))}</span>
    </button>
  </div>
</header>
<main class="page">
  <a class="back" href="{SITE}">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5m0 0l6-6m-6 6l6 6"></path></svg>
    {T(C("back"))}
  </a>
  <article class="detail">
    <header class="detail-hero">
      <div class="dh-kicker">{kicker}</div>
      <h2 class="detail-title">{T(title)}</h2>
      {f'<div class="dh-people-wrap"><div class="dh-people">{people_html}</div>{mentioned_html}</div>' if people_html or mentioned_html else ''}
      <div class="dh-stats">{stats}</div>
    </header>
    <div class="rec-login-hint">{T(C("local_hint"))}</div>
    <div class="om">
      {bar_html}
      <div class="om-layout">
        <nav class="om-nav" {TA(C("nav"), "aria-label")}>
          <div class="om-nav-strip">{nav_strip}</div>
          {nav_more}
          {nav_sheet}
        </nav>
        <main>{''.join(sections) or f'<p class="om-empty">{T(C("empty"))}</p>'}</main>
      </div>
    </div>
    {cm_html}
  </article>
</main>
{player}
<div id="toast"></div>
<script>{scripts}</script>
</body>
</html>"""
