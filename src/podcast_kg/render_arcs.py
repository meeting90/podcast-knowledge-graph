"""把「话题弧」渲染成单文件 HTML：一次点击听完整段讨论。

与 render_card.py 的差别
------------------------
旧页面把每条 claim 当成一个可点击单位（点一下跳 30 秒），读者永远在听半句话。
新页面只有一种播放单位：**一个弧**。点「完整听这一段」从弧起点连播到弧终点
自动暂停，中途不做任何切割；想要细节再点段内要点，那只是可选的下钻。
"""

from __future__ import annotations

import html
import json


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def mmss(sec: int) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def to_sec(stamp: str) -> int:
    parts = [int(p) for p in str(stamp).split(":") if p != ""]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return parts[0] if parts else 0


CSS = """
:root{
  --paper:#f7f4ee; --ink:#1c1a17; --muted:#6f6860; --line:#e0d9cd;
  --accent:#8a4b2a; --accent-soft:#f0e3d8; --card:#fffdf9; --play:#1f5d4c;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;}
a{color:inherit}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 140px}

/* 刊头 */
header.head{padding:56px 0 28px;border-bottom:1px solid var(--line)}
.kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700}
h1.title{font-size:clamp(24px,3.4vw,38px);line-height:1.28;margin:14px 0 16px;font-weight:800;letter-spacing:-.01em}
.meta{color:var(--muted);font-size:14px;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center}
.meta .num{font-variant-numeric:tabular-nums}
/* 对比条 */
.compare{display:flex;flex-wrap:wrap;gap:12px;margin:26px 0 4px}
.compare div{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;font-size:13px;color:var(--muted)}
.compare b{color:var(--ink);font-size:17px;font-variant-numeric:tabular-nums;margin-right:4px}
.compare .arrow{align-self:center;color:var(--accent);font-weight:700}

/* 布局 */
.cols{display:grid;grid-template-columns:236px minmax(0,1fr);gap:40px;align-items:start}
@media(max-width:900px){.cols{grid-template-columns:1fr;gap:16px}
  nav.toc{position:static!important;max-height:none!important;display:none}
  nav.toc.open{display:block}}

/* 侧栏 */
nav.toc{position:sticky;top:18px;max-height:calc(100vh - 40px);overflow:auto;padding:18px 0;
  border-right:1px solid var(--line);padding-right:14px}
nav.toc .h{font-size:11px;letter-spacing:.14em;color:var(--muted);text-transform:uppercase;margin-bottom:10px}
nav.toc a{display:block;text-decoration:none;padding:7px 8px;border-radius:7px;font-size:13.5px;
  color:var(--muted);line-height:1.45;border-left:2px solid transparent}
nav.toc a:hover{background:#efe9df;color:var(--ink)}
nav.toc a.on{background:var(--accent-soft);color:var(--accent);border-left-color:var(--accent);font-weight:600}
nav.toc a .t{font-variant-numeric:tabular-nums;font-size:11.5px;color:#9a9186;display:block}

/* 弧卡片 */
.arc{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px 28px;margin:26px 0;
  scroll-margin-top:20px}
.arc.playing{border-color:var(--play);box-shadow:0 0 0 3px rgba(31,93,76,.12)}
.arc-top{display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
.idx{font-size:13px;font-weight:800;color:var(--accent);font-variant-numeric:tabular-nums;
  background:var(--accent-soft);border-radius:6px;padding:2px 7px}
.arc h2{font-size:clamp(19px,2.2vw,25px);margin:0;line-height:1.35;font-weight:750;flex:1 1 auto;min-width:240px}
.arc-meta{color:var(--muted);font-size:12.5px;margin:8px 0 0;display:flex;gap:14px;flex-wrap:wrap;
  font-variant-numeric:tabular-nums}
.summary{margin:16px 0 0;color:#3b352e}
blockquote.open{margin:18px 0 0;padding:12px 16px;background:#f4efe6;border-left:3px solid var(--accent);
  border-radius:0 8px 8px 0;color:#4a443c;font-size:14.5px;line-height:1.7}
blockquote.open .lbl{display:block;font-size:11px;letter-spacing:.1em;color:var(--accent);
  text-transform:uppercase;margin-bottom:6px;font-weight:700}

/* 播放按钮 */
.play{display:inline-flex;align-items:center;gap:9px;background:var(--play);color:#fff;border:0;
  border-radius:999px;padding:11px 20px;font-size:14px;font-weight:650;cursor:pointer;margin-top:18px;
  font-variant-numeric:tabular-nums}
.play:hover{filter:brightness(1.08)}
.play.alt{background:#fff;color:var(--play);border:1.5px solid var(--play)}
.play .dur{opacity:.75;font-weight:500;font-size:12.5px}

/* 要点 */
h3.sec{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);
  margin:26px 0 10px;font-weight:700}
ol.points{margin:0;padding:0;list-style:none;counter-reset:p}
ol.points li{counter-increment:p;display:flex;gap:12px;padding:9px 0;border-bottom:1px dashed var(--line)}
ol.points li:last-child{border-bottom:0}
ol.points li::before{content:counter(p);flex:0 0 22px;height:22px;border-radius:50%;
  background:var(--accent-soft);color:var(--accent);font-size:11.5px;font-weight:800;
  display:grid;place-items:center;margin-top:3px}
ol.points .txt{flex:1 1 auto}
ol.points .txt b{font-weight:600}

/* 回合时间线 */
ol.beats{margin:0;padding:0 0 0 4px;list-style:none}
ol.beats li{position:relative;padding:0 0 14px 22px;border-left:1px solid var(--line)}
ol.beats li:last-child{border-left-color:transparent;padding-bottom:0}
ol.beats li::before{content:"";position:absolute;left:-4px;top:8px;width:7px;height:7px;border-radius:50%;
  background:#c8beb0;border:2px solid var(--card)}
.ts{font-variant-numeric:tabular-nums;font-size:12px;color:var(--accent);font-weight:700;
  background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.ts:hover{color:var(--play)}
.beat-txt{font-size:14.5px;color:#3b352e}

/* 证据层 */
details.evidence{margin-top:20px;border-top:1px solid var(--line);padding-top:14px}
details.evidence summary{cursor:pointer;font-size:13px;color:var(--muted);font-weight:600;list-style:none}
details.evidence summary::-webkit-details-marker{display:none}
details.evidence summary::before{content:"＋ ";color:var(--accent);font-weight:700}
details.evidence[open] summary::before{content:"－ "}
.ev-list{margin:12px 0 0;padding:0;list-style:none;font-size:13.5px;color:#4a443c}
.ev-list li{padding:7px 0;border-bottom:1px dotted var(--line);display:flex;gap:10px}
.ev-list li:last-child{border-bottom:0}
.ev-list .cid{color:#a49a8c;font-variant-numeric:tabular-nums;flex:0 0 34px}

/* 依赖 */
.deps{margin-top:16px;font-size:13px;color:var(--muted);background:#f4efe6;border-radius:9px;padding:11px 14px}
.deps a{color:var(--accent);font-weight:600}

/* 播放条 */
.bar{position:fixed;left:0;right:0;bottom:0;background:rgba(28,26,23,.96);color:#f3eee5;
  backdrop-filter:blur(8px);border-top:1px solid rgba(255,255,255,.12);z-index:50}
.bar-in{max-width:1180px;margin:0 auto;padding:12px 20px;display:flex;gap:16px;align-items:center}
.bar .now{flex:1 1 auto;min-width:0}
.bar .now .t{font-size:13.5px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .now .r{font-size:12px;color:#b9b0a4;font-variant-numeric:tabular-nums}
.bar button{background:#f3eee5;color:#1c1a17;border:0;border-radius:999px;padding:8px 16px;
  font-size:13px;font-weight:700;cursor:pointer;white-space:nowrap}
.bar button.ghost{background:transparent;color:#f3eee5;border:1px solid rgba(255,255,255,.3)}
.bar .seek{flex:0 0 260px;display:flex;align-items:center;gap:10px}
.bar input[type=range]{width:100%;accent-color:#f3eee5}
@media(max-width:720px){.bar .seek{display:none}.bar-in{gap:10px}}
.note{font-size:12.5px;color:#9a9186;margin-top:10px}
"""

JS = """
const AUDIO = document.getElementById('au');
let arcEnd = null, curArc = null;
const dur = (s)=>{s=Math.max(0,Math.round(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};

function toast(msg){
  const t=document.getElementById('nowT'); if(t) t.textContent=msg;
}
function playArc(id, start, end, title){
  if(!AUDIO.getAttribute('src')){ toast('这期没有可播放的音频地址'); return; }
  document.querySelectorAll('.arc').forEach(a=>a.classList.remove('playing'));
  const el=document.getElementById(id);
  if(el) el.classList.add('playing');
  curArc={id,start,end,title};
  arcEnd=end;
  const go=()=>{ AUDIO.currentTime=start; AUDIO.play().catch(()=>toast('浏览器拦了自动播放，再点一次即可')); };
  if(AUDIO.readyState>=1){ go(); }
  else { AUDIO.addEventListener('loadedmetadata', go, {once:true}); AUDIO.load(); }
  toast(title+' · '+dur(start)+'–'+dur(end));
  document.getElementById('nowR').textContent=dur(start)+' – '+dur(end)+'（'+dur(end-start)+'）';
}
function seek(t){
  if(!AUDIO.src) return;
  AUDIO.currentTime=t;
  if(AUDIO.paused) AUDIO.play().catch(()=>{});
}
AUDIO.addEventListener('timeupdate',()=>{
  const s=document.getElementById('seek');
  if(s && AUDIO.duration) s.value=String(Math.round(AUDIO.currentTime/AUDIO.duration*1000));
  document.getElementById('tCur').textContent=dur(AUDIO.currentTime);
  if(arcEnd!==null && AUDIO.currentTime>=arcEnd){
    AUDIO.pause(); arcEnd=null;
    if(curArc){
      document.getElementById('nowR').textContent='这一段听完了 · 继续往下听？';
      document.querySelectorAll('.arc').forEach(a=>a.classList.remove('playing'));
    }
  }
});
document.getElementById('seek').addEventListener('input',e=>{
  if(AUDIO.duration){ AUDIO.currentTime=Number(e.target.value)/1000*AUDIO.duration; }
});
document.getElementById('tToggle').addEventListener('click',()=>{
  if(AUDIO.paused) AUDIO.play(); else AUDIO.pause();
});
document.getElementById('navToggle').addEventListener('click',()=>{
  document.querySelector('nav.toc').classList.toggle('open');
});
"""


def render(data: dict, curated: dict | None = None, source_label: str = "") -> str:
    src = data.get("source", {}) or {}
    people = {p["person_id"]: p.get("name", p["person_id"]) for p in data.get("people", []) or []}
    roles = {p["person_id"]: p.get("role", "") for p in data.get("people", []) or []}
    arcs = data.get("arcs", []) or []
    claims = {c["claim_id"]: c for c in data.get("claims", []) or []}
    stats = data.get("stats", {}) or {}
    audio_url = src.get("audio_url") or ""
    curated = curated or {}

    title = src.get("title") or data.get("content_id", "")
    kicker = " · ".join(x for x in [src.get("series"), f"EP.{src.get('episode_no')}" if src.get("episode_no") else "", src.get("published_at")] if x)

    speakers = "、".join(
        f"{p.get('name')}（{'主持' if p.get('role') == 'host' else '嘉宾'}）"
        for p in (data.get("people", []) or []) if p.get("role") in ("host", "guest")
    )

    total = int(src.get("duration_sec") or 0)
    out: list[str] = []
    w = out.append

    w("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">")
    w('<meta name="viewport" content="width=device-width,initial-scale=1">')
    w(f"<title>{esc(title)}</title><style>{CSS}</style></head><body>")
    w('<div class="wrap">')

    # 刊头
    w('<header class="head">')
    if kicker:
        w(f'<div class="kicker">{esc(kicker)}</div>')
    w(f"<h1 class=\"title\">{esc(title)}</h1>")
    w('<div class="meta">')
    if speakers:
        w(f"<span>{esc(speakers)}</span>")
    if total:
        w(f'<span class="num">全程 {mmss(total)}</span>')
    if source_label:
        w(f"<span>{esc(source_label)}</span>")
    w("</div>")

    mc = stats.get("median_claim_sec", 0)
    ma = stats.get("median_arc_sec", 0)
    w('<div class="compare">')
    w(f'<div><b>{stats.get("claims", len(claims))}</b>张逐句观点卡<!--  --><span class="num">（中位 {mc}s）</span></div>')
    w('<div class="arrow">→</div>')
    w(f'<div><b>{len(arcs)}</b>段完整讨论<span class="num">（中位 {ma // 60}分{ma % 60:02d}秒）</span></div>')
    w('<div>点一次 = 连播一整段，播到段末自动停</div>')
    w("</div>")
    w('<p class="note">每段是一次「主持人开启话题 → 嘉宾讲完 → 收束」的完整回合。段内的「要点」可以单独点，但默认单位是段：'
      '先听完语境，再看提炼。下面的原始观点卡折叠在每段末尾，只作溯源用。</p>')
    w("</header>")

    w('<div style="margin:14px 0 0"><button id="navToggle" class="play alt" style="margin-top:0">☰ 段落目录</button></div>')
    w('<div class="cols">')

    # 侧栏
    w('<nav class="toc">')
    w('<div class="h">段落目录</div>')
    for a in arcs:
        w(f'<a href="#{esc(a["arc_id"])}"><span class="t">{esc(a["start"])} · {mmss(a["duration_sec"])}</span>'
          f'{esc((curated.get(a["arc_id"], {}) or {}).get("title") or a["title"])}</a>')
    w("</nav>")

    w("<main>")
    for i, a in enumerate(arcs, 1):
        cur = curated.get(a["arc_id"], {}) or {}
        a_title = cur.get("title") or a["title"]
        a_sum = cur.get("summary") or ""
        start, end = to_sec(a["start"]), to_sec(a["end"])
        who = []
        for cid in a.get("evidence", []):
            sp = (claims.get(cid) or {}).get("speaker")
            if sp and people.get(sp) and people[sp] not in who:
                who.append(people[sp])
        main_speaker = next((x for x in who if roles.get(next(k for k, v in people.items() if v == x), "") == "guest"), "")

        w(f'<article class="arc" id="{esc(a["arc_id"])}">')
        w('<div class="arc-top">')
        w(f'<span class="idx">{i:02d}</span>')
        w(f"<h2>{esc(a_title)}</h2>")
        w("</div>")
        meta_bits = [f'{a["start"]} – {a["end"]}', mmss(a["duration_sec"]),
                     f'{len(a.get("evidence", []))} 条原始观点']
        if main_speaker:
            meta_bits.append(f"发言：{main_speaker}")
        if a.get("group"):
            meta_bits.append(a["group"])
        w('<div class="arc-meta">' + "".join(f"<span>{esc(x)}</span>" for x in meta_bits) + "</div>")

        if a_sum:
            w(f'<p class="summary">{esc(a_sum)}</p>')

        w(f'<button class="play" onclick="playArc(\'{esc(a["arc_id"])}\',{start},{end},\'{esc(a_title).replace(chr(39), " ")}\')">'
          f'▶ 完整听这一段 <span class="dur">{mmss(a["duration_sec"])}</span></button>')

        if a.get("open_line"):
            w(f'<blockquote class="open"><span class="lbl">这一段是从这句话开始的（转写原话）</span>{esc(a["open_line"])}</blockquote>')

        points = a.get("points", []) or []
        if points:
            w('<h3 class="sec">这一段在讲什么</h3><ol class="points">')
            for p in points:
                w(f'<li><div class="txt">{esc(p["statement"])}<br>'
                  f'<button class="ts" onclick="seek({to_sec(p["at"])})">{esc(p["at"])}</button></div></li>')
            w("</ol>")

        beats = a.get("beats", []) or []
        if beats:
            w('<h3 class="sec">回合推进（按顺序听）</h3><ol class="beats">')
            for b in beats:
                w(f'<li><button class="ts" onclick="seek({to_sec(b["at"])})">{esc(b["at"])}</button> '
                  f'<span class="beat-txt">{esc(b["gist"])}</span></li>')
            w("</ol>")

        deps = a.get("context", []) or []
        if deps:
            links = "；".join(f'<a href="#{esc(d["arc_id"])}">{esc(d["arc_id"])} {esc(d["title"])}</a>' for d in deps[:3])
            w(f'<div class="deps">要听懂这一段，前面这些已铺垫过：{links}</div>')

        ev = a.get("evidence", []) or []
        if ev:
            w(f'<details class="evidence"><summary>展开这 {len(ev)} 条原始观点（溯源用，不建议单独听）</summary><ul class="ev-list">')
            for cid in ev:
                c = claims.get(cid) or {}
                sp = people.get(c.get("speaker"), "")
                w(f'<li><span class="cid">{esc(cid)}</span><div>'
                  f'<button class="ts" onclick="seek({to_sec(c.get("timestamp", "0:00"))})">{esc(c.get("timestamp", ""))}</button> '
                  f'{esc(c.get("statement", ""))}'
                  f'<span style="color:#a49a8c"> · {esc(sp)}</span></div></li>')
            w("</ul></details>")

        w("</article>")
    w("</main></div></div>")

    # 播放条
    w('<div class="bar"><div class="bar-in">')
    w(f'<audio id="au" preload="metadata" src="{esc(audio_url)}"></audio>')
    w('<button id="tToggle">▶ / ⏸</button>')
    w('<div class="now"><div class="t" id="nowT">选一段开始听</div>'
      '<div class="r" id="nowR">点上面任意一段的「完整听这一段」</div></div>')
    w('<div class="seek"><input id="seek" type="range" min="0" max="1000" value="0">'
      f'<span class="num" id="tCur" style="font-size:12px;color:#b9b0a4;font-variant-numeric:tabular-nums">0:00</span></div>')
    w("</div></div>")
    w(f"<script>{JS}</script></body></html>")
    return "\n".join(out)


def render_file(path: str, curated_path: str | None = None, out: str | None = None) -> str:
    data = json.load(open(path, encoding="utf-8"))
    curated = {}
    if curated_path:
        try:
            curated = (json.load(open(curated_path, encoding="utf-8")) or {}).get(data.get("content_id"), {})
        except FileNotFoundError:
            curated = {}
    html_text = render(data, curated=curated)
    target = out or path.rsplit(".", 1)[0] + ".html"
    with open(target, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    return target
