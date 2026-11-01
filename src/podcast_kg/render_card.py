#!/usr/bin/env python3
"""HERON · 知识卡 JSON → 单文件 HTML（与 heron 站点同款版式）

版式（对齐 heron 详情页）:
  毛玻璃顶栏 → 刊头（平台/日期/标题/嘉宾/统计）
  → 工具条（全部 / 我的推荐 / 编辑推荐）
  → 左侧 sticky 主题导航 + 右侧观点行列表（展开看关系与语料）
  → 底部悬浮播放条（点时间戳回链原声）

交互:
  - 点行 = 展开/收起；点行内播放钮/星标不冒泡
  - 点时间戳 = 播放该 claim 区间，播到 end 自动暂停
  - ★ 编辑推荐 → 复制 JSON，回填 card["picks"]
"""
import json
import os
import re

from .outputs import ensure_parent, out_path, stem

REL_CN = {"supports": "支撑", "supported_by": "被支撑", "example_of": "例证", "exemplified_by": "例证于",
          "extends": "引申", "extended_by": "被引申", "deepens": "深化", "deepened_by": "被深化",
          "tension_with": "张力", "responds_to": "回应", "parallel": "并列", "implies": "推出",
          "precondition": "前提", "part_of": "属于", "echoes": "呼应", "echoed_by": "被呼应",
          "related": "关联", "contrast": "对比", "followed_by": "递进", "aligns_with": "呼应"}

REL_COLOR = {"supports": "#3b5bdb", "deepens": "#0b7285", "extends": "#2f9e44",
             "echoes": "#9c36b5", "responds_to": "#e8590c", "tension_with": "#c92a2a",
             "implies": "#5f3dc4", "part_of": "#868e96", "precondition": "#f08c00",
             "parallel": "#adb5bd", "exemplified_by": "#0c8599", "contrast": "#c2255c"}

GROUP_COLORS = ["#3b5bdb", "#0b7285", "#e8590c", "#2f9e44", "#9c36b5", "#c2255c", "#5f3dc4", "#087f5b"]


# ---------------------------------------------------------------- helpers

def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def esc_attr(s):
    return esc(s).replace('"', "&quot;")


def jss(v):
    """把值转成可嵌入单引号 JS 字符串 / 双引号属性的安全文本。"""
    return (str(v if v is not None else "")
            .replace("\\", "\\\\").replace("'", "\\'")
            .replace('"', "&quot;").replace("\n", " ").replace("\r", " "))


def js(obj):
    """嵌入 <script> 的 JSON：转义闭合标签，避免提前截断。"""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def strip_group_no(name):
    """「① 产品与工程」→「产品与工程」"""
    out = re.sub(r"^[\d①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]+[.\s、)）]?\s*", "", str(name or "")).strip()
    return out or str(name or "")


def to_sec(t):
    if not t:
        return 0
    q = [int(x) for x in re.findall(r"\d+", str(t))]
    if len(q) == 3:
        return q[0] * 3600 + q[1] * 60 + q[2]
    if len(q) == 2:
        return q[0] * 60 + q[1]
    return q[0] if q else 0


def mmss(sec):
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def build_groups(card):
    if card.get("groups"):
        return [(g["gid"], g["name"], list(g.get("ids", []))) for g in card["groups"]]
    claims = card["claims"]
    n = len(claims)
    parts = 4 if n >= 20 else 3
    size = -(-n // parts)
    out = []
    for i in range(parts):
        chunk = claims[i * size:(i + 1) * size]
        if not chunk:
            continue
        out.append((f"g{i+1}", f"{i+1} · {chunk[0]['timestamp']} 起", [c["claim_id"] for c in chunk]))
    return out


def load_segments(card, seg_dir):
    """读取 seg_dir 下的 {cid}.mp3，转 base64，返回 {cid:{b64,dur,start,end}}。
    约定：文件名前缀为 claim_id，例如 1_c21.mp3 / c21.mp3 均可。"""
    segs = {}
    audio_url = card["source"].get("audio_url", "")
    if not seg_dir:
        return segs, audio_url
    import base64
    import glob
    import os
    meta = {c["claim_id"]: (c.get("timestamp", ""), c.get("end", "")) for c in card["claims"]}
    for f in sorted(glob.glob(os.path.join(seg_dir, "*.mp3"))):
        cid = os.path.splitext(os.path.basename(f))[0].split("_")[-1]
        if cid not in meta:
            continue
        with open(f, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        st, en = meta[cid]
        segs[cid] = {"b64": b64, "start": st, "end": en,
                     "dur": max(0, to_sec(en) - to_sec(st))}
    return segs, audio_url


# ---------------------------------------------------------------- blocks

def claim_row(c, speaker, rank=None, cid_attr=True, pick=False):
    cid = c["claim_id"]
    t = esc(c.get("timestamp", ""))
    e = esc(c.get("end", ""))
    rid = f' id="claim-{esc_attr(cid)}"' if cid_attr else ""
    rank_html = f'<span class="om-rank num">{rank}</span>' if rank else ""

    chips = []
    for r in c.get("relations", []) or []:
        rtype = r.get("type", "")
        chips.append(
            f'<button type="button" class="om-relbtn" '
            f'onclick="event.stopPropagation();gotoClaim(\'{jss(r.get("target", ""))}\')" '
            f'title="{esc_attr(r.get("note", ""))}">'
            f'<i style="background:{REL_COLOR.get(rtype, "#868e96")}"></i>'
            f'{esc(REL_CN.get(rtype, rtype))} <span class="num">{esc(r.get("target", ""))}</span></button>')
    rels_html = f'<div class="om-rels">{"".join(chips)}</div>' if chips else ""

    meta_bits = [x for x in (c.get("type"), c.get("confidence"), speaker) if x]
    meta_html = " · ".join(esc(x) for x in meta_bits)
    if t:
        meta_html = (meta_html + " · " if meta_html else "") + f'<span class="num">{t}–{e}</span>'

    ev = c.get("evidence")
    ev_html = f'<div class="om-ev"><b>语料</b>{esc(ev)}</div>' if ev else ""

    play_cls = "om-playbtn"
    play_html = (
        f'<button type="button" class="{play_cls}" title="播放 {t}–{e}" '
        f'onclick="playClaim(event,\'{jss(cid)}\',\'{jss(t)}\',\'{jss(e)}\')">'
        f'<svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">'
        f'<path d="M3 1.6v8.8l7-4.4z" fill="currentColor"/></svg>'
        f'<span class="num">{t}</span></button>')

    pick_cls = " is-pick" if pick else ""
    return (
        f'<div class="om-row{pick_cls}"{rid} data-cid="{esc_attr(cid)}">'
        f'<div class="om-row-h" role="button" tabindex="0" aria-expanded="false" '
        f'onclick="toggleRow(this)" onkeydown="rowKey(event,this)">'
        f'{rank_html}'
        f'<span class="om-title"><span class="om-cid num">{esc(cid)}</span>{esc(c.get("statement", ""))}</span>'
        f'<button type="button" class="om-star" title="加入/移出推荐" '
        f'onclick="togglePick(event,\'{jss(cid)}\')">☆</button>'
        f'{play_html}'
        f'<span class="om-chev">'
        f'<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
        f'<path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg></span>'
        f'</div>'
        f'<div class="om-more">{rels_html}<div class="om-meta num">{meta_html}</div>{ev_html}'
        f'<div class="om-note" hidden></div></div>'
        f'</div>'
    )


# ---------------------------------------------------------------- template

CSS = r"""
:root{
  color-scheme:light dark;
  --bg:#fafafa; --bg-sunken:#f4f4f5; --surface:#ffffff;
  --fg:#18181b; --fg-muted:#52525b; --fg-faint:#a1a1aa;
  --line:rgba(24,24,27,.08); --line-strong:rgba(24,24,27,.16); --hover:rgba(24,24,27,.045);
  --accent:#b45309; --accent-soft:rgba(180,83,9,.09); --accent-line:rgba(180,83,9,.32);
  --play:#0f766e; --play-soft:rgba(15,118,110,.1);
  --ok:#15803d; --error:#b91c1c;
  --font-display:Outfit,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  --font-body:Outfit,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  --font-mono:"JetBrains Mono",ui-monospace,"SF Mono",Consolas,monospace;
  --ease-out:cubic-bezier(.16,1,.3,1);
  --ease-spring:cubic-bezier(.34,1.4,.44,1);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --bg:#101012; --bg-sunken:#0a0a0b; --surface:#1a1a1d;
    --fg:#e4e4e7; --fg-muted:#a1a1aa; --fg-faint:#52525b;
    --line:rgba(228,228,231,.09); --line-strong:rgba(228,228,231,.2); --hover:rgba(228,228,231,.06);
    --accent:#d97706; --accent-soft:rgba(217,119,6,.13); --accent-line:rgba(217,119,6,.4);
    --play:#2dd4bf; --play-soft:rgba(45,212,191,.12);
  }
}
:root[data-theme="dark"]{
  --bg:#101012; --bg-sunken:#0a0a0b; --surface:#1a1a1d;
  --fg:#e4e4e7; --fg-muted:#a1a1aa; --fg-faint:#52525b;
  --line:rgba(228,228,231,.09); --line-strong:rgba(228,228,231,.2); --hover:rgba(228,228,231,.06);
  --accent:#d97706; --accent-soft:rgba(217,119,6,.13); --accent-line:rgba(217,119,6,.4);
  --play:#2dd4bf; --play-soft:rgba(45,212,191,.12);
  color-scheme:dark;
}
:root[data-theme="light"]{color-scheme:light}

*{box-sizing:border-box}
body{margin:0;font:15px/1.65 var(--font-body);background:var(--bg);color:var(--fg);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.num{font-family:var(--font-mono);font-feature-settings:"zero" on}
a{color:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
::selection{background:var(--accent-soft)}

/* ── 顶栏 ── */
.topbar{position:sticky;top:0;z-index:20;display:flex;gap:12px;align-items:center;
  padding:12px 24px;background:color-mix(in srgb,var(--bg) 78%,transparent);
  backdrop-filter:blur(14px) saturate(1.4);-webkit-backdrop-filter:blur(14px) saturate(1.4);
  border-bottom:1px solid var(--line);box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}
.brand{margin:0;font-family:var(--font-display);font-size:17px;font-weight:650;
  letter-spacing:-.02em;white-space:nowrap;flex:none}
.brand::after{content:"";display:inline-block;width:6px;height:6px;margin-left:9px;
  border-radius:50%;background:var(--accent);vertical-align:2px;opacity:.85}
.tb-spacer{flex:1}
.tb-link{font-size:13px;color:var(--accent);text-decoration:none;
  border-bottom:1px solid var(--accent-line);white-space:nowrap}
.tb-link:hover{border-bottom-width:2px}
.theme-btn{all:unset;cursor:pointer;width:32px;height:32px;display:inline-flex;
  align-items:center;justify-content:center;border-radius:50%;color:var(--fg-muted);
  border:1px solid var(--line);font-size:14px}
.theme-btn:hover{background:var(--hover);color:var(--fg)}

/* ── 页面骨架 ── */
.page{max-width:880px;margin:0 auto;padding:40px 24px 120px}
body.has-player .page{padding-bottom:170px}

/* ── 刊头 ── */
.detail-hero{animation:rise-in .5s var(--ease-out) both}
@keyframes rise-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.dh-kicker{display:flex;align-items:baseline;gap:10px;margin-bottom:10px}
.dh-platform{font-family:var(--font-mono);font-size:11px;font-weight:600;letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent)}
.dh-date{font-family:var(--font-mono);font-size:11.5px;color:var(--fg-faint)}
.detail-title{margin:0 0 14px;font-family:var(--font-display);
  font-size:clamp(24px,4.5vw,34px);font-weight:700;letter-spacing:-.03em;line-height:1.18;
  text-wrap:balance}
.dh-people{display:flex;flex-wrap:wrap;gap:14px;margin-bottom:16px}
.dh-person{display:inline-flex;align-items:center;gap:8px}
.dh-avatar{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;
  border-radius:50%;background:var(--bg-sunken);border:1px solid var(--line-strong);
  font-family:var(--font-display);font-size:13px;font-weight:650;color:var(--fg-muted)}
.dh-pname{font-size:14px;font-weight:600}
.dh-prole{font-family:var(--font-mono);font-size:10.5px;color:var(--fg-faint)}
.dh-stats{display:flex;flex-wrap:wrap;gap:4px 18px;align-items:baseline;
  font-size:12.5px;color:var(--fg-muted)}
.dh-stats b{font-family:var(--font-mono);font-size:14px;font-weight:600;color:var(--fg);
  margin-right:2px}
.dh-link{color:var(--accent);text-decoration:none;border-bottom:1px solid var(--accent-line);
  font-size:12.5px}
.dh-link:hover{border-bottom-width:2px}

/* ── 全局按钮 ── */
button{padding:7px 16px;border:1px solid var(--line-strong);border-radius:10px;
  background:transparent;color:inherit;font:inherit;font-weight:500;cursor:pointer;
  transition:background .2s var(--ease-out),border-color .2s var(--ease-out),
    transform .12s var(--ease-spring)}
button:hover:not(:disabled){background:var(--hover);
  border-color:color-mix(in srgb,var(--fg) 28%,transparent)}
button:active:not(:disabled){transform:translateY(1px) scale(.98)}

/* ── 观点地图 ── */
.om{margin-top:8px}
.om-bar{position:sticky;top:48px;z-index:5;background:var(--bg);
  padding:12px 0 14px;border-bottom:1px solid var(--line)}
.om-bar-row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.om-seg{display:inline-flex;background:var(--surface);border:1px solid var(--line);
  border-radius:9px;padding:3px}
.om-seg button{all:unset;cursor:pointer;padding:4px 14px;border-radius:6px;
  font-size:14px;color:var(--fg-muted)}
.om-seg button[aria-pressed="true"]{background:var(--accent);color:#fff}
.om-edit{all:unset;cursor:pointer;display:inline-flex;gap:7px;align-items:center;
  padding:4px 13px;border:1px solid var(--accent);color:var(--accent);border-radius:9px;
  font-size:14px}
.om-edit:hover{background:var(--accent-soft)}
.om-hint{font-size:13px;color:var(--fg-muted);margin-left:auto}

.om-layout{display:grid;grid-template-columns:168px 1fr;gap:40px;padding:28px 0 80px}
.om-layout>main{min-width:0}
.om-nav{position:sticky;top:100px;align-self:start;display:flex;flex-direction:column;
  gap:2px;font-size:15px}
.om-nav a{display:flex;align-items:center;gap:9px;padding:6px 10px;border-radius:8px;
  color:var(--fg-muted);text-decoration:none}
.om-nav a:hover{background:var(--surface);color:var(--fg)}
.om-nav i{width:9px;height:9px;border-radius:50%;flex:none}
.om-nav em{margin-left:auto;font-style:normal;font-size:13px;font-variant-numeric:tabular-nums;
  font-family:var(--font-mono)}

.om-section{margin-bottom:48px;scroll-margin-top:120px}
.om-section.hide{display:none}
.om-sh{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
.om-sh h2{margin:0;font-size:19px;font-weight:700}
.om-sh small{color:var(--fg-muted);font-size:14px}
.om-dot{width:11px;height:11px;border-radius:50%;align-self:center;flex:none}
.om-empty{color:var(--fg-muted);padding:40px 0}

.om-row{border-bottom:1px solid var(--line);animation:rise-in .45s var(--ease-out) both}
.om-row-pick{animation:none}
.om-row.hide{display:none}
.om-row-h{box-sizing:border-box;display:flex;gap:16px;align-items:flex-start;width:100%;
  padding:15px 0;cursor:pointer}
.om-row.open>.om-row-h{padding-bottom:10px}
.om-playbtn{all:unset;cursor:pointer;flex:none;display:inline-flex;align-items:center;
  justify-content:center;gap:5px;height:28px;min-width:76px;padding:0 10px;border-radius:99px;
  background:var(--accent-soft);color:var(--accent);font-size:13px;font-weight:500;
  font-variant-numeric:tabular-nums;transition:background .15s,color .15s}
.om-playbtn .num{font-size:12px}
.om-playbtn:hover,.om-row.playing .om-playbtn{background:var(--accent);color:#fff}
.om-title{flex:1;min-width:0;font-size:17px;line-height:1.55;text-wrap:pretty}
.om-cid{color:var(--fg-faint);font-size:12px;margin-right:8px;font-variant-numeric:tabular-nums}
.om-star{all:unset;cursor:pointer;flex:none;display:inline-flex;align-items:center;gap:4px;
  padding:2px 9px;border-radius:99px;font-size:13px;color:var(--fg-muted);
  border:1px solid var(--line);font-variant-numeric:tabular-nums;line-height:1.5}
.om-star.on{background:var(--accent-soft);border-color:transparent;color:var(--accent);font-weight:700}
body.no-chrome .om-star{display:none}
.om-chev{flex:none;width:14px;height:14px;margin-top:6px;color:var(--fg-muted);
  transition:transform .2s}
.om-row.open .om-chev{transform:rotate(90deg)}
.om-row.playing>.om-row-h{box-shadow:inset 3px 0 0 var(--accent);padding-left:14px}
.om-row.om-flash>.om-row-h{animation:om-flash 1.6s var(--ease-out)}
@keyframes om-flash{0%{background:var(--accent-soft)}100%{background:transparent}}

.om-more{display:none;padding:0 0 20px}
.om-row.open .om-more{display:block}
.om-rels{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
.om-relbtn{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:6px;
  padding:2px 10px;border:1px solid var(--line);border-radius:99px;background:var(--surface);
  font-size:12.5px;color:var(--fg-muted);transition:border-color .15s,color .15s}
.om-relbtn:hover{border-color:var(--accent);color:var(--accent)}
.om-relbtn i{width:8px;height:8px;border-radius:50%;flex:none}
.om-relbtn .num{font-size:11.5px;color:var(--fg-faint)}
.om-meta{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--fg-muted);margin-bottom:16px}
.om-ev{font-size:13.5px;line-height:1.7;color:var(--fg-muted);
  border-left:2px solid var(--line-strong);padding:2px 0 2px 12px;margin:0 0 14px}
.om-ev b{display:block;font-family:var(--font-mono);font-size:10.5px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--fg-faint);margin-bottom:2px;font-weight:600}
.om-note{font-size:13px;color:var(--accent);margin:0}
.om-note[hidden]{display:none}
.preason{display:none;width:100%;margin-top:6px;padding:6px 10px;font:inherit;font-size:13px;
  color:var(--fg);background:var(--surface);border:1px solid var(--accent-line);border-radius:8px}
body.editing .preason{display:block}
body.editing .om-note{display:none}
.om-rank{flex:none;width:34px;font-size:28px;line-height:1;font-weight:700;color:var(--accent);
  padding-top:2px}

.om-seg button:focus-visible,.om-edit:focus-visible,.om-playbtn:focus-visible,
.om-star:focus-visible,.om-relbtn:focus-visible,.om-row-h:focus-visible{
  outline:2px solid var(--accent);outline-offset:2px}

/* ── 播放条 ── */
.playerbar{position:fixed;bottom:14px;left:50%;transform:translateX(-50%);
  width:min(680px,calc(100vw - 28px));z-index:40;display:none;align-items:center;gap:14px;
  padding:12px 18px;background:color-mix(in srgb,var(--surface) 88%,transparent);
  backdrop-filter:blur(16px) saturate(1.5);-webkit-backdrop-filter:blur(16px) saturate(1.5);
  border:1px solid var(--line-strong);border-radius:18px;
  box-shadow:0 24px 48px -16px rgba(24,24,27,.35),inset 0 1px 0 rgba(255,255,255,.08)}
.playerbar.show{display:flex;animation:player-in .45s var(--ease-spring) both}
@keyframes player-in{from{opacity:0;transform:translateX(-50%) translateY(24px)}
  to{opacity:1;transform:translateX(-50%) translateY(0)}}
.pb-toggle{flex:0 0 auto;width:42px;height:42px;display:inline-flex;align-items:center;
  justify-content:center;border-radius:50%;border:1px solid var(--line-strong);
  background:var(--fg);color:var(--bg);cursor:pointer;padding:0;transition:transform .15s var(--ease-spring)}
.pb-toggle:hover:not(:disabled){background:var(--fg);border-color:var(--fg)}
.pb-toggle:active{transform:scale(.9)}
.pb-info{flex:1;min-width:0}
.pb-stmt{font-family:var(--font-display);font-size:13px;font-weight:600;letter-spacing:-.01em;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:6px}
.pb-track{height:5px;border-radius:3px;background:var(--bg-sunken);cursor:pointer;
  position:relative;overflow:hidden}
.pb-clip{position:absolute;top:0;height:100%;background:color-mix(in srgb,var(--accent) 30%,transparent);
  pointer-events:none;display:none}
.pb-fill{height:100%;border-radius:3px;background:var(--play);transition:width .2s linear}
.pb-time{font-family:var(--font-mono);font-size:10.5px;color:var(--fg-faint);margin-top:5px}

/* ── 导出面板 ── */
#exportpanel{position:fixed;left:50%;transform:translateX(-50%);bottom:88px;
  width:min(680px,calc(100vw - 28px));z-index:45;display:none;
  background:var(--surface);border:1px solid var(--line-strong);border-radius:16px;
  padding:14px 16px;box-shadow:0 24px 48px -16px rgba(24,24,27,.35)}
#exportpanel.show{display:block}
.ep-hd{display:flex;gap:8px;align-items:baseline;font-size:12.5px;color:var(--fg-muted);
  margin-bottom:8px}
.ep-hd b{color:var(--accent)}
#exptext{width:100%;height:110px;resize:vertical;font-family:var(--font-mono);font-size:11.5px;
  color:var(--fg);background:var(--bg-sunken);border:1px solid var(--line);border-radius:10px;
  padding:8px 10px}
.ep-btns{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
.ep-btns button{font-size:12.5px;padding:5px 13px}
.ep-btns .primary{background:var(--accent);border-color:var(--accent);color:#fff}
.ep-btns .primary:hover{background:var(--accent);filter:brightness(1.06);color:#fff}

/* ── 导流条（redirect 模式） ── */
#origbar{position:fixed;left:0;right:0;bottom:0;z-index:40;background:var(--surface);
  border-top:1px solid var(--line);padding:10px 16px calc(10px + env(safe-area-inset-bottom,0px));
  font-size:13px;box-shadow:0 -8px 24px -12px rgba(0,0,0,.25)}
body.redirect .page{padding-bottom:130px}
.orig-link{display:flex;align-items:center;gap:9px;text-decoration:none;color:var(--fg)}
.orig-ico{width:22px;height:22px;border-radius:50%;background:var(--accent);color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:12px;flex:none}
.orig-txt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.orig-go{color:var(--accent);font-weight:600;flex:none}
.orig-hint{margin-top:7px;color:var(--fg-faint);font-size:12px;line-height:1.55;transition:color .2s}
.orig-hint.flash{color:var(--accent);font-weight:500}

#toast{position:fixed;left:50%;top:68px;transform:translateX(-50%);z-index:60;
  background:var(--fg);color:var(--bg);padding:8px 16px;border-radius:10px;font-size:12.5px;
  opacity:0;transition:.25s;pointer-events:none}
#toast.show{opacity:1}

/* ── 响应式 ── */
@media (max-width:760px){
  .topbar{padding:11px 16px}
  .page{padding:26px 16px 96px}
  .om-layout{display:block;padding-top:8px}
  .om-bar{top:44px;padding:10px 0 12px}
  .om-bar-row{justify-content:flex-start}
  .om-hint{margin-left:0;flex-basis:100%;font-size:12px;order:3}
  .om-seg button{padding:4px 12px;font-size:13px}
  .om-edit{padding:4px 10px;font-size:13px}
  .om-nav{position:sticky;top:90px;z-index:4;flex-direction:row;flex-wrap:wrap;gap:5px;
    padding:8px 2px;margin:0 0 10px;background:var(--bg);border-bottom:1px solid var(--line)}
  .om-nav a{white-space:nowrap;border:1px solid var(--line);padding:3px 10px;border-radius:99px;
    background:var(--surface);flex:none;font-size:12.5px}
  .om-nav em{display:none}
  .om-rank{width:22px;font-size:18px}
  .om-section{margin-bottom:32px;scroll-margin-top:190px}
  .om-sh h2{font-size:17px}
  .om-sh small{font-size:12.5px}
  .om-title{font-size:15.5px;flex-basis:calc(100% - 100px)}
  .om-row-h{flex-wrap:wrap;gap:6px 12px}
  .om-star{padding:4px 10px}
  .om-chev{margin-top:4px}
  .om-relbtn{font-size:12px;padding:2px 8px}
  .detail-title{font-size:clamp(22px,6vw,28px)}
  .playerbar{left:0;right:0;bottom:0;transform:none;width:100%;border-radius:0;
    border-left:0;border-right:0;border-bottom:0;
    padding:10px 14px calc(10px + env(safe-area-inset-bottom,0px));gap:10px}
  #exportpanel{bottom:0;width:100%;border-radius:16px 16px 0 0}
}
@media (max-width:420px){
  .om-title{font-size:15px}
  .om-cid{font-size:10.5px}
}
@media (pointer:coarse){
  *{-webkit-tap-highlight-color:transparent}
  .om-relbtn:active,.om-playbtn:active{opacity:.7}
}
@media (prefers-reduced-motion:reduce){
  .om *,.playerbar{transition:none!important;animation:none!important}
}
"""

JS = r"""
const REL_CN=__REL_CN__, REL_COLORS=__COLORS__;
const SEGS=__SEGS__, FULL_URL=__AUDIO__, FULL_DUR=__FULL_DUR__, ORIG_URL=__ORIG_URL__;
const REDIRECT=__REDIRECT__, CLAIMS=__CLAIMS__, CONTENT_ID=__CONTENT_ID__;
const SERIES=__SERIES__, EPNO=__EPNO__, PLATFORM=__PLATFORM__;
let picks=__PICKS__.slice();
let editing=false;

/* ---------- 基础 ---------- */
function escHtml(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
  .replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function toSec(t){const p=String(t||'').match(/\d+/g)||[];const q=p.map(Number);
  return q.length===3?q[0]*3600+q[1]*60+q[2]:(q.length===2?q[0]*60+q[1]:(q[0]||0))}
function fmt(x){x=Math.max(0,Math.floor(x||0));const h=Math.floor(x/3600),m=Math.floor(x%3600/60),
  s=x%60;return h?h+':'+String(m).padStart(2,'0')+':'+String(s).padStart(2,'0')
  :m+':'+String(s).padStart(2,'0')}
function toast(msg){const t=document.getElementById('toast');if(!t)return;
  t.textContent=msg;t.classList.add('show');clearTimeout(t._tm);
  t._tm=setTimeout(()=>t.classList.remove('show'),2000)}

/* ---------- 主题 ---------- */
try{const th=localStorage.getItem('heron-theme');
  if(th==='light'||th==='dark')document.documentElement.dataset.theme=th}catch(e){}
function toggleTheme(){
  const root=document.documentElement;
  const cur=root.dataset.theme;
  const sys=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';
  const next=cur?(cur==='dark'?'light':'dark'):(sys==='dark'?'light':'dark');
  root.dataset.theme=next;
  try{localStorage.setItem('heron-theme',next)}catch(e){}
  const b=document.getElementById('themebtn');if(b)b.textContent=next==='dark'?'☾':'☀';
}
(function(){
  const b=document.getElementById('themebtn');if(!b)return;
  const cur=document.documentElement.dataset.theme;
  const dark=cur?cur==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
  b.textContent=dark?'☾':'☀';
})();

/* ---------- 行展开 ---------- */
function toggleRow(head){
  const row=head.closest('.om-row');if(!row)return;
  const open=!row.classList.contains('open');
  row.classList.toggle('open',open);
  head.setAttribute('aria-expanded',open?'true':'false');
}
function rowKey(ev,head){
  if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();toggleRow(head)}
}
function gotoClaim(cid){
  const el=document.getElementById('claim-'+cid);if(!el)return;
  el.classList.add('open');
  const head=el.querySelector('.om-row-h');if(head)head.setAttribute('aria-expanded','true');
  const sticky=['topbar','om-bar'].map(c=>document.querySelector('.'+c))
    .filter(Boolean).map(x=>x.getBoundingClientRect().bottom);
  const top=el.getBoundingClientRect().top+window.scrollY-Math.max(0,...sticky)-8;
  window.scrollTo({top,behavior:'smooth'});
  el.classList.remove('om-flash');void el.offsetWidth;el.classList.add('om-flash');
  setTimeout(()=>el.classList.remove('om-flash'),1700);
}

/* ---------- 推荐 ---------- */
function pickOf(cid){return picks.find(p=>p.claim_id===cid)}
function pickRow(p,i){
  const c=CLAIMS[p.claim_id]||{};
  const t=p.timestamp||c.timestamp||'',e=p.end||c.end||'';
  const chips=(c.rels||[]).map(r=>'<button type="button" class="om-relbtn" '
    +'onclick="event.stopPropagation();gotoClaim(\''+r.target+'\')">'
    +'<i style="background:'+(REL_COLORS[r.type]||'#868e96')+'"></i>'
    +(REL_CN[r.type]||r.type)+' <span class="num">'+escHtml(r.target)+'</span></button>').join('');
  const meta=[c.type,c.confidence,c.speakerName].filter(Boolean).map(escHtml).join(' · ')
    +((t)?((c.type||c.confidence||c.speakerName?' · ':'')+'<span class="num">'
      +escHtml(t)+'–'+escHtml(e)+'</span>'):'');
  const ev=c.evidence?('<div class="om-ev"><b>语料</b>'+escHtml(c.evidence)+'</div>'):'';
  return '<div class="om-row om-row-pick" data-cid="'+escHtml(p.claim_id)+'">'
    +'<div class="om-row-h" role="button" tabindex="0" aria-expanded="false" '
    +'onclick="toggleRow(this)" onkeydown="rowKey(event,this)">'
    +'<span class="om-rank num">'+(i+1)+'</span>'
    +'<span class="om-title"><span class="om-cid num">'+escHtml(p.claim_id)+'</span>'
    +escHtml(p.label||c.statement||p.claim_id)+'</span>'
    +'<button type="button" class="om-star on" title="移出推荐" '
    +'onclick="togglePick(event,\''+p.claim_id+'\')">★</button>'
    +'<button type="button" class="om-playbtn" '
    +'onclick="playClaim(event,\''+p.claim_id+'\',\''+escHtml(t)+'\',\''+escHtml(e)+'\')">'
    +'<svg viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">'
    +'<path d="M3 1.6v8.8l7-4.4z" fill="currentColor"/></svg>'
    +'<span class="num">'+escHtml(t)+'</span></button>'
    +'<span class="om-chev"><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">'
    +'<path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" '
    +'stroke-linecap="round" stroke-linejoin="round"/></svg></span></div>'
    +'<div class="om-more">'+(chips?'<div class="om-rels">'+chips+'</div>':'')
    +'<div class="om-meta num">'+meta+'</div>'+ev
    +'<div class="om-note"'+(p.note?'':' hidden')+'>'+(p.note?'推荐理由：'+escHtml(p.note):'')+'</div>'
    +'<input class="preason" placeholder="写推荐理由（可选）" value="'+escHtml(p.note||'')+'" '
    +'onclick="event.stopPropagation()" oninput="setReason('+i+',this.value)"></div></div>';
}
function buildJson(){
  return JSON.stringify({content_id:CONTENT_ID,picks:picks.map(p=>({
    claim_id:p.claim_id,label:p.label||'',note:p.note||'',
    timestamp:p.timestamp||'',end:p.end||''}))},null,2);
}
function renderPicks(){
  const list=document.getElementById('pickslist');
  if(list)list.innerHTML=picks.map(pickRow).join('');
  const sec=document.getElementById('s-top');
  if(sec)sec.classList.toggle('hide',picks.length===0);
  const nav=document.getElementById('nav-top');
  if(nav){nav.style.display=picks.length?'':'none';
    const em=nav.querySelector('em');if(em)em.textContent=picks.length}
  const cnt=document.getElementById('pickscount');
  if(cnt)cnt.textContent=picks.length+' 条 · 点击直接播放';
  const mc=document.getElementById('minecount');
  if(mc)mc.textContent=picks.length;
  document.querySelectorAll('.om-row[data-cid]').forEach(r=>{
    r.classList.toggle('is-pick',!!pickOf(r.dataset.cid));
    if(!r.classList.contains('om-row-pick')){
      const s=r.querySelector('.om-star');
      const on=!!pickOf(r.dataset.cid);
      if(s){s.classList.toggle('on',on);s.textContent=on?'★':'☆'}
    }
  });
  const ta=document.getElementById('exptext');
  if(ta)ta.value=buildJson();
  applyFilter();
}
function togglePick(ev,cid){
  if(ev)ev.stopPropagation();
  if(!editing){toast('先点「✎ 编辑推荐」再加入推荐');return}
  const i=picks.findIndex(p=>p.claim_id===cid);
  if(i>=0){picks.splice(i,1)}
  else{
    const c=CLAIMS[cid]||{};
    picks.push({claim_id:cid,label:c.statement||cid,note:'',
      timestamp:c.timestamp||'',end:c.end||''});
  }
  renderPicks();
}
function setReason(i,v){
  if(!picks[i])return;
  picks[i].note=v;
  const ta=document.getElementById('exptext');
  if(ta)ta.value=buildJson();
}
function toggleEdit(){
  editing=!editing;
  document.body.classList.toggle('editing',editing);
  const b=document.getElementById('editbtn');
  if(b)b.textContent=editing?'✓ 完成编辑':'✎ 编辑推荐';
  const p=document.getElementById('exportpanel');
  if(p)p.classList.toggle('show',editing);
  if(editing){toast('点 ☆ 加入推荐；填推荐理由后复制 JSON')}
}
function copyExport(){
  const ta=document.getElementById('exptext'),txt=buildJson();
  if(ta){ta.value=txt;ta.focus();ta.select()}
  const ok=()=>toast('已复制 '+picks.length+' 条推荐');
  const fail=()=>toast('已全选，请按 Ctrl/⌘+C 手动复制');
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(ok).catch(fail);
  }else{
    let done=false;try{done=document.execCommand('copy')}catch(e){}
    done?ok():fail();
  }
}
function downloadExport(){
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([buildJson()],{type:'application/json'}));
  a.download='picks_'+CONTENT_ID+'.json';a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),4000);
}
/* 把当前推荐写进页面，另存一份可独立打开的 HTML */
function buildPageHtml(){
  const doc=document.documentElement.cloneNode(true);
  doc.removeAttribute('data-theme');
  doc.querySelectorAll('.om-row.open').forEach(r=>r.classList.remove('open'));
  doc.querySelectorAll('.om-row-h').forEach(h=>h.setAttribute('aria-expanded','false'));
  doc.querySelectorAll('.om-row.playing,.om-row.om-flash').forEach(r=>
    r.classList.remove('playing','om-flash'));
  const pb=doc.querySelector('#playerbar');if(pb)pb.classList.remove('show');
  doc.querySelectorAll('#pb-fill').forEach(e=>e.style.width='0');
  const clip=doc.querySelector('#pb-clip');
  if(clip){clip.style.display='none';clip.style.left='';clip.style.width=''}
  const stmt=doc.querySelector('#pb-stmt');
  if(stmt)stmt.textContent='点上方任一观点的时间戳开始';
  const ptime=doc.querySelector('#pb-time');if(ptime)ptime.textContent='0:00';
  const ptg=doc.querySelector('#pb-toggle');if(ptg)ptg.textContent='▶';
  const body=doc.querySelector('body');
  if(body)body.classList.remove('has-player','editing','mine-mode');
  const panel=doc.querySelector('#exportpanel');if(panel)panel.classList.remove('show');
  const editBtn=doc.querySelector('#editbtn');if(editBtn)editBtn.textContent='✎ 编辑推荐';
  const ta=doc.querySelector('#exptext');if(ta)ta.textContent='';
  const pickList=doc.querySelector('#pickslist');if(pickList)pickList.innerHTML='';
  doc.querySelectorAll('.om-seg button').forEach(b=>
    b.setAttribute('aria-pressed',String(b.dataset.mine==='false')));
  doc.querySelectorAll('.om-section.hide').forEach(s=>s.classList.remove('hide'));
  const toastEl=doc.querySelector('#toast');
  if(toastEl){toastEl.textContent='';toastEl.classList.remove('show')}
  const target=[...doc.querySelectorAll('script')].find(s=>
    s.textContent.indexOf('let picks=')>=0);
  if(target){
    const txt=target.textContent;
    const a=txt.indexOf('let picks='),b=txt.indexOf('.slice();',a);
    if(a>=0&&b>a){
      const arr=JSON.stringify(picks).replace(/<\//g,'<\\/');
      target.textContent=txt.slice(0,a)+'let picks='+arr+'.slice();'
        +txt.slice(b+'.slice();'.length);
    }
  }
  return '<!DOCTYPE html>\n'+doc.outerHTML;
}
function exportPage(){
  const html=buildPageHtml();
  const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));
  a.download=(CONTENT_ID||'card')+'_picks.html';a.click();
  setTimeout(()=>URL.revokeObjectURL(a.href),5000);
  toast('已生成 '+a.download+'：推荐已写进页面');
}

/* ---------- 筛选：全部 / 我的推荐 ---------- */
function setFilter(mine){
  document.body.classList.toggle('mine-mode',mine);
  document.querySelectorAll('.om-seg button').forEach(b=>
    b.setAttribute('aria-pressed',String(b.dataset.mine===String(mine))));
  applyFilter();
}
function applyFilter(){
  const mine=document.body.classList.contains('mine-mode');
  document.querySelectorAll('.om-section').forEach(sec=>{
    if(sec.id==='s-top'){sec.classList.toggle('hide',mine||picks.length===0);return}
    const rows=[...sec.querySelectorAll('.om-row')];
    const visible=rows.filter(r=>!mine||r.classList.contains('is-pick'));
    sec.classList.toggle('hide',visible.length===0);
    const small=sec.querySelector('.om-sh small');
    if(small)small.textContent=visible.length+' 条';
  });
}

/* ---------- 音频 ---------- */
const au=document.getElementById('au');
const pb=document.getElementById('playerbar');
const pbStmt=document.getElementById('pb-stmt');
const pbFill=document.getElementById('pb-fill');
const pbClip=document.getElementById('pb-clip');
const pbTime=document.getElementById('pb-time');
const pbToggle=document.getElementById('pb-toggle');
const pbTrack=document.getElementById('pb-track');
let blobURLs={},curCid=null,curEnd=null,pendingSeek=null;

function segSrc(cid){
  if(blobURLs[cid])return blobURLs[cid];
  const s=SEGS[cid];if(!s||!s.b64)return null;
  try{
    const bin=atob(s.b64),n=bin.length,buf=new Uint8Array(n);
    for(let i=0;i<n;i++)buf[i]=bin.charCodeAt(i);
    blobURLs[cid]=URL.createObjectURL(new Blob([buf],{type:'audio/mpeg'}));
    return blobURLs[cid];
  }catch(e){return null}
}
function markPlaying(cid){
  document.querySelectorAll('.om-row.playing').forEach(r=>r.classList.remove('playing'));
  if(!cid)return;
  document.querySelectorAll('.om-row[data-cid="'+cid+'"]').forEach(r=>r.classList.add('playing'));
}
function locate(t){
  const mins=Math.round(toSec(t)/60);
  const txt=(PLATFORM||'原平台')+(SERIES?'《'+SERIES+'》':'')+(EPNO?' EP.'+EPNO:'')
    +' 约第 '+mins+' 分钟（'+t+'）';
  const hint=document.getElementById('orig-hint');
  const show=(ok)=>{
    if(!hint)return;
    hint.innerHTML=(ok?'✅ 已复制：':'📍 ')+escHtml(txt)
      +'　<a href="'+escHtml(ORIG_URL)+'" target="_blank" rel="noopener" '
      +'style="color:var(--accent)">打开原节目 →</a>';
    hint.classList.add('flash');
    clearTimeout(hint._tm);hint._tm=setTimeout(()=>hint.classList.remove('flash'),2400);
  };
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(()=>show(true)).catch(()=>show(false));
  }else{show(false)}
}
function playClaim(ev,cid,t,e){
  if(ev)ev.stopPropagation();
  if(REDIRECT){locate(t);return}
  if(!au)return;
  markPlaying(cid);curCid=cid;
  const c=CLAIMS[cid]||{};
  if(pbStmt)pbStmt.textContent=cid+' · '+(c.statement||'');
  if(pb&&!pb.classList.contains('show')){
    pb.classList.add('show');document.body.classList.add('has-player');
  }
  const seg=segSrc(cid);
  if(seg){
    curEnd=null;au.src=seg;
    if(pbClip)pbClip.style.display='none';
    const p=au.play();
    if(p&&p.catch)p.catch(()=>toast('播放被浏览器拦截，点播放条 ▶ 重试'));
    return;
  }
  if(!FULL_URL){
    if(pb)pb.classList.remove('show');
    document.body.classList.remove('has-player');
    toast('这条观点没有可播放音频，请到原平台收听');
    return;
  }
  const start=toSec(t),end=e?toSec(e):0;
  curEnd=end>start?end:null;
  if(pbClip&&FULL_DUR>0){
    pbClip.style.display='block';
    pbClip.style.left=(start/FULL_DUR*100)+'%';
    pbClip.style.width=(Math.max(0,(curEnd||start+1)-start)/FULL_DUR*100)+'%';
  }
  if(au.getAttribute('src')!==FULL_URL){
    au.src=FULL_URL;au.load();pendingSeek=start;
    au.addEventListener('loadedmetadata',function(){
      if(pendingSeek!==null){try{au.currentTime=pendingSeek}catch(err){}pendingSeek=null}
      const p=au.play();if(p&&p.catch)p.catch(()=>{});
    },{once:true});
    if(pbTime)pbTime.textContent=fmt(start)+' / '+fmt(FULL_DUR);
    return;
  }
  try{au.currentTime=start}catch(err){}
  const p=au.play();if(p&&p.catch)p.catch(()=>toast('播放被拦截，点播放条 ▶ 重试'));
}
function syncBar(){
  if(!au)return;
  const d=au.duration||(SEGS[curCid]?SEGS[curCid].dur:0)||FULL_DUR||0;
  const t=au.currentTime||0;
  if(pbFill)pbFill.style.width=(d>0?Math.min(100,t/d*100):0)+'%';
  if(pbTime)pbTime.textContent=fmt(t)+' / '+fmt(d);
  if(pbToggle)pbToggle.textContent=(au.paused||au.ended)?'▶':'❚❚';
}
if(au){
  au.addEventListener('timeupdate',()=>{
    if(curEnd!==null&&au.currentTime>=curEnd){au.pause();curEnd=null;toast('片段结束')}
    syncBar();
  });
  au.addEventListener('play',syncBar);
  au.addEventListener('pause',syncBar);
  au.addEventListener('ended',syncBar);
  au.addEventListener('loadedmetadata',syncBar);
  au.addEventListener('error',()=>{
    const c=au.error?au.error.code:0;
    const m={1:'加载被中断',2:'网络错误',3:'解码失败',4:'格式不支持或地址不可达'}[c]||'未知错误';
    toast('音频无法播放：'+m);
  });
  au.addEventListener('stalled',()=>{if(au.readyState<2)toast('缓冲中…')});
}
if(pbToggle)pbToggle.addEventListener('click',()=>{
  if(!au||!au.src)return;
  if(au.paused){const p=au.play();if(p&&p.catch)p.catch(()=>toast('播放被拦截，请再点一次'))}
  else au.pause();
});
if(pbTrack)pbTrack.addEventListener('click',ev=>{
  if(!au||!au.duration)return;
  const r=pbTrack.getBoundingClientRect();
  au.currentTime=Math.max(0,Math.min(1,(ev.clientX-r.left)/r.width))*au.duration;
  syncBar();
});

/* ---------- 启动（脚本在 body 末尾，元素已就绪） ---------- */
renderPicks();
"""


def render(card: dict, seg_dir=None, mode="audio", chrome=True) -> str:
    """mode="audio"    内联片段 / 整集流播，页面自带播放条
       mode="redirect" 纯导流：不内联音频、不请求 CDN，点时间戳只复制定位提示
       chrome=False    去掉推荐编辑与工具条（分享给读者看的干净版）"""
    segs_map, full_url = load_segments(card, seg_dir)
    redirect = mode == "redirect"
    if redirect:
        segs_map, full_url = {}, ""

    src = card["source"]
    claims = card["claims"]
    people = {p["person_id"]: p for p in card.get("people", [])}
    title = src.get("title") or card.get("content_id") or "知识卡"

    groups = build_groups(card)
    rendered = set()
    used = {cid for _, _, ids in groups for cid in ids if cid in {c["claim_id"] for c in claims}}
    missing = [c["claim_id"] for c in claims if c["claim_id"] not in used]
    if missing:
        groups.append(("gx", f"未入组 {len(missing)} 条", missing))

    # ── 导航 + 各主题 section ──
    nav_items = []
    sections = []
    total_rels = 0
    for gi, (gid, gname, ids) in enumerate(groups):
        color = GROUP_COLORS[gi % len(GROUP_COLORS)]
        rows = []
        for cid in ids:
            c = next((x for x in claims if x["claim_id"] == cid), None)
            if not c or cid in rendered:
                continue
            rendered.add(cid)
            speaker = people.get(c.get("speaker"), {}).get("name", c.get("speaker", ""))
            total_rels += len(c.get("relations", []) or [])
            rows.append(claim_row(c, speaker, cid_attr=True))
        if not rows:
            continue
        sid = f"s-{gid}"
        nav_items.append(
            f'<a href="#{esc_attr(sid)}" data-nav="{esc_attr(gid)}">'
            f'<i style="background:{color}"></i>{esc(strip_group_no(gname))}'
            f'<em class="num">{len(rows)}</em></a>')
        sections.append(
            f'<section id="{esc_attr(sid)}" class="om-section" data-gid="{esc_attr(gid)}">'
            f'<div class="om-sh"><span class="om-dot" style="background:{color}"></span>'
            f'<h2>{esc(strip_group_no(gname))}</h2><small>{len(rows)} 条</small></div>'
            f'{"".join(rows)}</section>')

    # ── 刊头 ──
    kicker = (f'<span class="dh-platform">{esc(src.get("platform") or "PODCAST")}</span>'
              + (f'<time class="dh-date num">{esc(src.get("published_at"))}</time>'
                 if src.get("published_at") else ""))

    ppl = "".join(
        f'<span class="dh-person"><span class="dh-avatar" aria-hidden="true">{esc((p.get("name") or "?")[:1])}</span>'
        f'<span class="dh-pname">{esc(p.get("name", ""))}</span>'
        + (f'<span class="dh-prole">{esc(p.get("role"))}</span>' if p.get("role") else "")
        + '</span>'
        for p in card.get("people", [])[:6])

    stats = (f'<span><b class="num">{len(claims)}</b> 条观点</span>'
             f'<span><b class="num">{len(sections)}</b> 个主题</span>'
             f'<span><b class="num">{total_rels}</b> 条关系</span>')
    if src.get("url"):
        stats += (f'<a class="dh-link" href="{esc_attr(src["url"])}" target="_blank" '
                  f'rel="noopener noreferrer">原节目 ↗</a>')
    if src.get("duration_sec"):
        stats += f'<span class="num">{mmss(src["duration_sec"])}</span>'

    # ── 工具条 ──
    bar = ""
    if chrome:
        bar = (
            '<div class="om-bar"><div class="om-bar-row">'
            '<div class="om-seg" role="group" aria-label="筛选">'
            '<button type="button" data-mine="false" aria-pressed="true" '
            'onclick="setFilter(false)">全部</button>'
            '<button type="button" data-mine="true" aria-pressed="false" '
            'onclick="setFilter(true)">我的推荐 <span id="minecount" class="num">0</span></button>'
            '</div>'
            '<button type="button" class="om-edit" id="editbtn" '
            'onclick="toggleEdit()">✎ 编辑推荐</button>'
            '<span class="om-hint">点行展开关系与语料 · 点时间戳回链原声</span>'
            '</div></div>')

    nav_top = (
        f'<a href="#s-top" id="nav-top" style="display:none">'
        f'<i style="background:var(--accent)"></i>我的推荐<em class="num">0</em></a>'
        if chrome else "")

    top_section = (
        '<section id="s-top" class="om-section hide">'
        '<div class="om-sh"><span class="om-dot" style="background:var(--accent)"></span>'
        '<h2>我的推荐</h2><small id="pickscount">0 条</small></div>'
        '<div id="pickslist"></div></section>'
        if chrome else "")

    # ── 播放条 / 导流条 ──
    if redirect:
        player = (
            '<div id="origbar">'
            f'<a class="orig-link" href="{esc_attr(src.get("url", ""))}" target="_blank" rel="noopener">'
            '<span class="orig-ico">◉</span>'
            f'<span class="orig-txt"><b>{esc(src.get("platform") or "原平台")}</b>'
            + (f'　{esc(src.get("series", ""))}' if src.get("series") else "")
            + (f' EP.{esc(src.get("episode_no", ""))}' if src.get("episode_no") else "")
            + (f'　·　全程 {mmss(src["duration_sec"])}' if src.get("duration_sec") else "")
            + '</span><span class="orig-go">去听原声 →</span></a>'
            '<div class="orig-hint" id="orig-hint">点任一条的时间戳：自动复制「第 X 分钟」定位提示，'
            '回到原平台拖到该处即可。</div></div>')
    else:
        player = (
            '<div class="playerbar" id="playerbar">'
            '<button type="button" class="pb-toggle num" id="pb-toggle" aria-label="播放/暂停">▶</button>'
            '<div class="pb-info">'
            '<div class="pb-stmt" id="pb-stmt">点上方任一观点的时间戳开始</div>'
            '<div class="pb-track" id="pb-track"><div class="pb-clip" id="pb-clip"></div>'
            '<div class="pb-fill" id="pb-fill"></div></div>'
            '<div class="pb-time" id="pb-time">0:00</div></div>'
            '<audio id="au" preload="metadata"></audio></div>')

    export_panel = ""
    if chrome:
        export_panel = (
            '<div id="exportpanel">'
            '<div class="ep-hd">推荐改完后：生成新页面直接带走，或复制 JSON 回填卡片</div>'
            '<textarea id="exptext" readonly onclick="this.select()"></textarea>'
            '<div class="ep-btns">'
            '<button type="button" class="primary" onclick="exportPage()">⤓ 生成编辑后的页面</button>'
            '<button type="button" onclick="copyExport()">⧉ 复制 JSON</button>'
            '<button type="button" onclick="downloadExport()">下载 .json</button>'
            '<button type="button" onclick="toggleEdit()">完成</button>'
            '</div></div>')

    # ── JS 数据 ──
    claims_js = {}
    for c in claims:
        claims_js[c["claim_id"]] = {
            "statement": c.get("statement", ""),
            "timestamp": c.get("timestamp", ""),
            "end": c.get("end", ""),
            "type": c.get("type", ""),
            "confidence": c.get("confidence", ""),
            "evidence": c.get("evidence", ""),
            "speakerName": people.get(c.get("speaker"), {}).get("name", c.get("speaker", "")),
            "rels": [{"type": r.get("type", ""), "target": r.get("target", ""),
                      "note": r.get("note", "")} for r in (c.get("relations") or [])],
        }
    used_types = sorted({r.get("type") for c in claims for r in (c.get("relations") or [])
                         if r.get("type")})

    body_cls = " ".join(x for x in ([] if chrome else ["no-chrome"]) + (["redirect"] if redirect else []))
    scripts = (JS.replace("__REL_CN__", js({t: REL_CN.get(t, t) for t in used_types}))
                 .replace("__COLORS__", js({t: REL_COLOR.get(t, "#868e96") for t in used_types}))
                 .replace("__SEGS__", js(segs_map))
                 .replace("__AUDIO__", js(full_url))
                 .replace("__FULL_DUR__", str(int(src.get("duration_sec") or 0)))
                 .replace("__ORIG_URL__", js(src.get("url", "")))
                 .replace("__REDIRECT__", "true" if redirect else "false")
                 .replace("__CLAIMS__", js(claims_js))
                 .replace("__CONTENT_ID__", js(card.get("content_id") or src.get("content_id", "")))
                 .replace("__SERIES__", js(src.get("series", "")))
                 .replace("__EPNO__", js(src.get("episode_no", "")))
                 .replace("__PLATFORM__", js(src.get("platform", "")))
                 .replace("__PICKS__", js(card.get("picks") or [])))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#101012" media="(prefers-color-scheme: dark)">
<title>{esc(title)} · HERON</title>
<script>try{{var t=localStorage.getItem('heron-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>{CSS}</style>
</head>
<body class="{body_cls}">
<header class="topbar">
  <h1 class="brand">HERON</h1>
  <span class="tb-spacer"></span>
  <button type="button" class="theme-btn" id="themebtn" onclick="toggleTheme()" aria-label="切换主题">☀</button>
</header>
<main class="page">
  <article class="detail">
    <header class="detail-hero">
      <div class="dh-kicker">{kicker}</div>
      <h2 class="detail-title">{esc(title)}</h2>
      {f'<div class="dh-people">{ppl}</div>' if ppl else ''}
      <div class="dh-stats">{stats}</div>
    </header>
    <div class="om">
      {bar}
      <div class="om-layout">
        <nav class="om-nav" aria-label="主题导航">{nav_top}{''.join(nav_items)}</nav>
        <main>{top_section}{''.join(sections) or '<p class="om-empty">这张卡没有可展示的观点。</p>'}</main>
      </div>
    </div>
  </article>
</main>
{player}
{export_panel}
<div id="toast"></div>
<script>{scripts}</script>
</body>
</html>"""

