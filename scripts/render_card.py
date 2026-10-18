#!/usr/bin/env python3
"""HERON · render_card.py — 知识卡 JSON → 纵向可折叠思维导图 HTML（JSON 单一数据源）

用法: python render_card.py <knowledge_card.json> [out.html]

结构（纵向树，逐级点开）:
  L1 中心节点（节目名）
    L2 主题组（默认收起，显示条数）        ← 点击展开
      L3 claim 一句话摘要                   ← 点击展开
        L4 详情：完整论断 / 证据 / 说话人 / 时间 / 关系（可跳转、可跳音频）

特性:
  - 树形连线随展开/收起重绘（肘形折线）
  - 详情里点关系目标 → 自动展开父级并滚动定位、闪烁高亮
  - 点击时间戳 → 原音频跳到起点，播到 end 自动暂停
  - 分组来自 card["groups"]；缺失时按时序自动分段，绝不产出"其他"
"""
import json, sys, re

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

TOOLS_BLOCK = """  <div class="tools">
    <button onclick="expandAll()">全部展开</button>
    <button onclick="collapseAll()">全部收起</button>
    <button onclick="expandLevel(1)">只到主题</button>
    <button id="editbtn" onclick="toggleEdit()">✎ 编辑推荐</button>
    <span class="legend">__LEGEND__</span>
  </div>"""

TMPL = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<title>__TITLE__ · HERON 思维导图</title><style>
*{box-sizing:border-box}
body{margin:0;background:#f7f7f4;font-family:"PingFang SC","Microsoft YaHei",sans-serif;color:#212529}
header{padding:16px 26px 12px;background:#fff;border-bottom:1px solid #e9ecef;position:sticky;top:0;z-index:30}
h1{font-size:17px;margin:0 0 5px;font-weight:600}
.meta{font-size:12px;color:#868e96}.meta a{color:#3b5bdb;text-decoration:none}
.tools{margin-top:10px;display:flex;gap:8px;align-items:center;font-size:11.5px;flex-wrap:wrap}
.tools button{border:1px solid #ced4da;background:#fff;border-radius:5px;padding:4px 10px;cursor:pointer;
  font-size:11.5px;color:#495057;transition:.15s}
.tools button:hover{background:#f1f3f5;border-color:#adb5bd}
.legend{display:flex;gap:12px;flex-wrap:wrap;margin-left:6px;color:#868e96}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:4px}

#tree{padding:22px 26px 160px;position:relative}
#edges{position:absolute;left:0;top:0;pointer-events:none;z-index:0}
.node{position:relative;z-index:1}

/* L1 根 */
.root{display:inline-flex;align-items:center;gap:10px;background:#1f2937;color:#fff;
  border-radius:8px;padding:9px 16px;font-size:13.5px;font-weight:600;margin-bottom:4px}
.root small{font-weight:400;opacity:.6;font-size:11px}

/* 子层容器 */
.children{margin-left:26px;padding-left:0;position:relative}
.children.collapsed{display:none}

/* L2 主题 */
.grp{position:relative;margin:6px 0}
.grp-h{display:inline-flex;align-items:center;gap:8px;cursor:pointer;user-select:none;
  border-radius:6px;padding:6px 12px;font-size:13px;font-weight:600;color:#fff;transition:.15s}
.grp-h:hover{filter:brightness(1.08)}
.grp-h .cnt{font-weight:400;opacity:.75;font-size:11px}
.grp-h .tri{font-size:9px;opacity:.85;transition:transform .2s;display:inline-block}
.grp.open>.grp-h .tri{transform:rotate(90deg)}

/* L3 claim */
.claim{position:relative;margin:4px 0}
.claim-h{display:flex;align-items:flex-start;gap:8px;background:#fff;border:1px solid #e9ecef;
  border-radius:6px;padding:7px 11px;cursor:pointer;font-size:12.5px;line-height:1.55;transition:.15s}
.claim-h:hover{border-color:#adb5bd;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.claim.open>.claim-h{background:#f8f9fa;border-color:#ced4da;border-bottom-left-radius:0;border-bottom-right-radius:0}
.claim-h .tri{font-size:9px;color:#adb5bd;margin-top:3px;transition:transform .2s}
.claim.open>.claim-h .tri{transform:rotate(90deg)}
.claim-h .txt{flex:1}
.cid{font-family:ui-monospace,monospace;font-size:10.5px;color:#adb5bd;margin-right:4px}
.ts{font-family:ui-monospace,monospace;font-size:10.5px;color:#e8590c;background:#fff4e6;
  border-radius:3px;padding:1px 5px;margin-left:6px;white-space:nowrap;cursor:pointer}
.ts:hover{background:#ffe8cc}
.sp{display:inline-block;font-size:10px;background:#f1f3f5;color:#6c757d;border-radius:3px;padding:0 5px;margin-left:5px}
.tag{display:inline-block;font-size:10px;background:#e7f5ff;color:#1971c2;border-radius:3px;padding:0 5px;margin-right:4px}

/* L4 详情 */
.detail{display:none;background:#fff;border:1px solid #ced4da;border-top:none;
  border-radius:0 0 6px 6px;padding:11px 13px 12px 26px;font-size:12px;line-height:1.65}
.claim.open>.detail{display:block}
.detail .full{color:#212529;margin-bottom:8px;font-size:13px;line-height:1.7}
.detail .ev{color:#495057;background:#f8f9fa;border-left:3px solid #dee2e6;padding:7px 10px;border-radius:0 4px 4px 0;margin:7px 0}
.detail .ev b{color:#868e96;font-weight:500;font-size:11px;display:block;margin-bottom:2px}
.detail .rels{margin-top:9px}
.detail .rels .lbl{font-size:11px;color:#868e96;margin-bottom:4px;display:block}
.relbtn{display:inline-flex;align-items:center;gap:5px;border:1px solid #dee2e6;background:#fff;
  border-radius:12px;padding:2px 9px;font-size:11px;margin:0 4px 5px 0;cursor:pointer;color:#495057;transition:.15s}
.relbtn:hover{background:#f1f3f5;border-color:#adb5bd}
.relbtn i{display:inline-block;width:8px;height:8px;border-radius:50%}
.relbtn .tgt{font-family:ui-monospace,monospace;font-size:10.5px;color:#3b5bdb}
.conf{font-size:10.5px;color:#adb5bd;margin-top:8px}
.detail-row{padding:6px 0;border-bottom:1px dashed #e9ecef;font-size:12px;line-height:1.6}
.detail-row:last-child{border-bottom:none}
.detail-row .note{color:#868e96;font-size:11.5px}
.detail-row .tgt{color:#3b5bdb;text-decoration:none;font-family:ui-monospace,monospace;font-size:11px}
ol.steps{margin:4px 0 2px;padding-left:20px;font-size:11.5px;color:#495057}
ol.steps li{margin:2px 0}

/* ---- 我的推荐（置顶）---- */
.pickbox{background:linear-gradient(135deg,#fff9db 0%,#fff 60%);border:1px solid #ffe066;
  border-radius:10px;padding:10px 12px;margin:2px 0 16px;box-shadow:0 2px 10px rgba(224,176,0,.08)}
.pickhead{font-size:12.5px;font-weight:700;color:#b8860b;margin-bottom:7px;display:flex;
  align-items:baseline;gap:8px}
.pickhead .cnt{font-weight:400;font-size:11px;color:#c9a227}
.pick{display:flex;align-items:flex-start;gap:9px;background:#fff;border:1px solid #ffe8a3;
  border-radius:7px;padding:8px 11px;margin:5px 0;cursor:pointer;transition:.15s}
.pick:hover{background:#fffdf0;border-color:#f59f00;transform:translateX(2px);
  box-shadow:0 2px 8px rgba(245,159,0,.15)}
.pick.playing{background:#e6f7eb;border-color:#2f9e44}
.pnum{flex:0 0 18px;height:18px;border-radius:50%;background:#f59f00;color:#fff;font-size:11px;
  display:flex;align-items:center;justify-content:center;font-weight:700;margin-top:1px}
.pbody{flex:1;min-width:0}
.ptxt{display:block;font-size:12.5px;line-height:1.5;color:#212529}
.pnote{display:block;font-size:11px;color:#a08000;margin-top:3px;line-height:1.45}
.pplay{flex:0 0 auto;font-size:11px;color:#e8590c;font-family:ui-monospace,monospace;
  background:#fff4e6;border-radius:4px;padding:2px 7px;white-space:nowrap}

/* ---- 编辑推荐 ---- */
.star{flex:0 0 auto;font-size:14px;color:#ced4da;cursor:pointer;line-height:1;padding:0 2px;
  margin-top:1px;transition:.15s;user-select:none}
.star:hover{color:#f59f00;transform:scale(1.25)}
.star.on{color:#f59f00}
body.editing .star{color:#adb5bd}
body.editing .star.on{color:#f59f00;text-shadow:0 0 6px rgba(245,159,0,.4)}
body.editing .pickbox{box-shadow:0 0 0 2px #ffe066}
.pick .pops{flex:0 0 auto;display:none;gap:6px;align-items:center}
body.editing .pick .pops{display:flex}
.pick .pops button{border:none;background:#f1f3f5;color:#495057;border-radius:4px;
  width:22px;height:22px;cursor:pointer;font-size:11px;padding:0}
.pick .pops button:hover{background:#e9ecef}
.pick .preason{display:none;width:100%;border:1px solid #ffe8a3;border-radius:4px;
  padding:3px 6px;font-size:11px;margin-top:4px;font-family:inherit;color:#495057}
body.editing .pick .preason{display:block}
.pick .pnote.view{display:block}
body.editing .pick .pnote.view{display:none}
#exportbox{position:fixed;left:0;right:0;bottom:56px;background:#1f2937;color:#e9ecef;
  padding:10px 16px;display:none;z-index:45;box-shadow:0 -4px 16px rgba(0,0,0,.25)}
#exportbox.show{display:block}
#exportbox .hd{font-size:11.5px;color:#adb5bd;margin-bottom:6px;display:flex;gap:10px;align-items:center}
#exportbox .hd b{color:#ffd43b}
#exportbox textarea{width:100%;height:110px;background:#111827;color:#a5d8ff;border:1px solid #374151;
  border-radius:5px;font-family:ui-monospace,monospace;font-size:11px;padding:8px;resize:vertical}
#exportbox .btns{display:flex;gap:8px;margin-top:6px}
#exportbox .btns button{background:#3b5bdb;color:#fff;border:none;border-radius:5px;
  padding:5px 12px;font-size:11.5px;cursor:pointer}
#exportbox .btns button.ghost{background:#374151}
#toast{position:fixed;left:50%;top:70px;transform:translateX(-50%);background:#1f2937;color:#fff;
  padding:8px 16px;border-radius:6px;font-size:12px;z-index:60;opacity:0;transition:.25s;pointer-events:none}
#toast.show{opacity:1}

/* 跳转闪烁 */
@keyframes flash{0%{box-shadow:0 0 0 3px #ffe066}100%{box-shadow:0 0 0 3px rgba(255,224,102,0)}}
.flash{animation:flash 1.2s ease-out 2}

/* 播放器 */
#player{position:fixed;bottom:0;left:0;right:0;background:#fff;border-top:1px solid #dee2e6;
  padding:9px 18px calc(9px + env(safe-area-inset-bottom,0px));font-size:12px;z-index:40;
  box-shadow:0 -2px 12px rgba(0,0,0,.05)}
.pbar{display:flex;align-items:center;gap:12px;max-width:760px;margin:0 auto}
#playbtn{flex:0 0 38px;width:38px;height:38px;border-radius:50%;border:none;cursor:pointer;
  background:#1f2937;color:#fff;font-size:13px;line-height:1;display:flex;align-items:center;
  justify-content:center;transition:.15s;padding:0}
#playbtn:hover{background:#343a40;transform:scale(1.05)}
#playbtn:active{transform:scale(.96)}
#playbtn.loading{background:#adb5bd}
.pmeta{flex:1;min-width:0}
#now{color:#495057;font-size:11.5px;line-height:1.4;margin-bottom:5px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
#ptrack{height:4px;background:#e9ecef;border-radius:2px;cursor:pointer;position:relative}
#ptrack:hover{height:6px}
#pfill{height:100%;width:0;background:#2f9e44;border-radius:2px;transition:width .12s linear}
#ptime{flex:0 0 auto;font-family:ui-monospace,monospace;font-size:11px;color:#868e96}
@media (max-width:768px){
  #player{padding:8px 12px calc(8px + env(safe-area-inset-bottom,0px))}
  .pbar{gap:9px}
  #playbtn{flex-basis:34px;width:34px;height:34px;font-size:12px}
  #now{font-size:11px;margin-bottom:4px}
  #ptime{font-size:10px}
}
#player audio{flex:1;height:32px}
#now{color:#495057;white-space:nowrap;font-family:ui-monospace,monospace;font-size:11px;min-width:190px}

/* ---- 桌面端：居中收窄 + 字号回补 ---- */
@media (min-width:900px){
  /* 头部与内容区共用同一条中线：810px 内容宽 + 26px 内边距 = 862 */
  header{padding-left:max(26px, calc((100% - 862px) / 2));
         padding-right:max(26px, calc((100% - 862px) / 2))}
  #tree{max-width:862px;margin:0 auto}
  .pbar{max-width:810px}
  h1{font-size:19px;line-height:1.45}
  .meta{font-size:12.5px}
  .tools{font-size:12px}
  .tools button{padding:5px 11px;font-size:12px}
  .root{font-size:14.5px;padding:10px 18px;border-radius:9px}
  .root small{font-size:11.5px}
  .children{margin-left:28px}
  .grp-h{font-size:13.5px;padding:7px 14px}
  .claim-h{font-size:13.5px;padding:9px 13px;line-height:1.62}
  .detail{font-size:12.8px;padding:13px 15px 14px 30px}
  .detail .full{font-size:14px;line-height:1.75}
  .detail .ev{font-size:12.5px;padding:8px 12px}
  .ptxt{font-size:13.5px;line-height:1.55}
  .pnote{font-size:11.8px}
  .pplay{font-size:11.5px;padding:3px 8px}
  .pickhead{font-size:13px}
  .relbtn{font-size:11.5px;padding:3px 11px}
  .ts{font-size:11px;padding:2px 6px}
  #now{font-size:12px}
  #ptime{font-size:11.5px}
}

/* ---- 移动端适配 ---- */
@media (max-width: 768px){
  header{padding:12px 14px 10px;position:static}
  h1{font-size:15px}
  .tools{margin-top:8px}
  .tools button{padding:6px 12px;font-size:12px}          /* 加大点按目标 */
  .legend{width:100%;margin-left:0;margin-top:6px;gap:10px}
  #tree{padding:14px 10px 130px}
  .root{font-size:12.5px;padding:8px 12px;border-radius:7px}
  .children{margin-left:16px}
  .grp-h{font-size:12px;padding:7px 11px}
  .claim-h{padding:9px 10px;font-size:12.5px}             /* 行高与触控区 */
  .claim-h .tri{margin-top:4px}
  .detail{padding:10px 11px 12px 16px;font-size:12px}
  .detail .full{font-size:12.5px}
  .relbtn{padding:4px 10px;font-size:11.5px;margin-right:5px}
  .ts{padding:3px 7px}                                    /* 时间戳更大可点 */
  .sp,.tag{padding:1px 5px}
  #player{padding:7px 10px;gap:8px;flex-wrap:wrap}
  #now{min-width:0;flex-basis:100%;font-size:10.5px;padding-bottom:2px}
  #player audio{height:34px}
  .conf{font-size:10px}
}
</style></head><body>
<header>
  <h1>__TITLE__</h1>
  <div class="meta">__META__</div>
__TOOLS__
</header>
<div id="tree"><svg id="edges"></svg>__TREE__</div>
<div id="player">
  <div class="pbar">
    <button id="playbtn" onclick="togglePlay()" aria-label="播放/暂停">▶</button>
    <div class="pmeta">
      <div id="now">点上方任一条推荐或时间戳</div>
      <div id="ptrack"><div id="pfill"></div></div>
    </div>
    <span id="ptime">0:00</span>
  </div>
  <audio id="au" preload="metadata"></audio>
</div>
<div id="exportbox">
  <div class="hd">编辑完成后点「复制 JSON」（会自动全选），直接粘给我即可合入卡片
    <span id="expcnt"></span></div>
  <textarea id="exptext" readonly onclick="this.select()"></textarea>
  <div class="btns">
    <button id="copybtn" onclick="copyExport()">⧉ 复制 JSON</button>
    <button class="ghost" onclick="downloadExport()">下载 .json</button>
    <button class="ghost" onclick="toggleEdit()">完成</button>
  </div>
</div>
<div id="toast"></div>
<script>
const REL_CN_MAP=__REL_CN__, REL_COLORS=__COLORS__;
const au=document.getElementById('au'), now=document.getElementById('now'), svg=document.getElementById('edges');
let curEnd=null;

/* ---------- 展开 / 收起 ---------- */
function toggle(el, sel){
  const box = el.closest(sel);
  const opening = !box.classList.contains('open');
  box.classList.toggle('open', opening);
  const kids = box.querySelector(':scope > .children');
  if(kids){
    kids.classList.toggle('collapsed', !opening);
    if(sel==='.claim' && opening){          // 展开 claim 时同步显示详情层
      kids.classList.remove('collapsed');   // .children 容器
      const det = box.querySelector(':scope > .children > .detail');
      if(det) det.style.display = opening ? 'block' : '';
    }
  }
  if(sel==='.grp' && box.classList.contains('open')){
    box.querySelectorAll(':scope > .children > .claim').forEach(k=>{
      k.classList.remove('open');
      const kk=k.querySelector(':scope > .children');
      if(kk) kk.classList.add('collapsed');
    });
  }
  redraw();
}
function expandAll(){
  document.querySelectorAll('.grp,.claim').forEach(n=>{
    n.classList.add('open');
    const k=n.querySelector(':scope > .children'); if(k) k.classList.remove('collapsed');
  });
  redraw();
}
function collapseAll(){
  document.querySelectorAll('.claim').forEach(n=>{n.classList.remove('open');
    const k=n.querySelector(':scope > .children'); if(k) k.classList.add('collapsed')});
  document.querySelectorAll('.grp').forEach(n=>{n.classList.remove('open');
    const k=n.querySelector(':scope > .children'); if(k) k.classList.add('collapsed')});
  redraw();
}
function expandLevel(lv){
  collapseAll();
  if(lv>=1) document.querySelectorAll('.grp').forEach(n=>{
    n.classList.add('open');
    const k=n.querySelector(':scope > .children'); if(k) k.classList.remove('collapsed')});
  redraw();
}

/* ---------- 跳转到节点 ---------- */
function gotoClaim(cid){
  const el=document.getElementById('claim-'+cid); if(!el) return;
  // 逐级展开父级
  let p=el.parentElement;
  while(p && p.id!=='tree'){
    if(p.classList.contains('children')) p.classList.remove('collapsed');
    const owner=p.parentElement;
    if(owner && (owner.classList.contains('grp')||owner.classList.contains('claim'))) owner.classList.add('open');
    p=owner;
  }
  redraw();
  setTimeout(()=>{
    el.scrollIntoView({behavior:'smooth',block:'center'});
    const h=el.querySelector(':scope > .claim-h');
    if(h){h.classList.remove('flash');void h.offsetWidth;h.classList.add('flash');}
  },60);
}

/* ---------- 音频 ---------- */
/* 模式 A（内联片段）：页面自带 5 个小片段，点击直接播放，无网络依赖，微信/iOS 最稳
   模式 B（远端整集）：流式播放原始整集，可拖动到任意时间戳 */
const SEGS=__SEGS_JSON__;      // {claim_id:{src,dur,start,end}} 或 {}
const FULL_URL=__AUDIO__;      // 整集直链（可能为空字符串）
const FULL_DUR=__FULL_DUR__;
const ORIG_URL=__ORIG_URL__;
let segURLs={}, curSeg=null;
function toSec(t){const p=t.split(':').map(Number);return p.length===3?p[0]*3600+p[1]*60+p[2]:p[0]*60+p[1]}
function fmt(x){x=Math.floor(x);const m=Math.floor(x/60),s=x%60;return m+':'+String(s).padStart(2,'0')}
let pendingSeek=null;

/* 解码 base64 → Blob URL（比 data: URI 更省内存，iOS 上 seek 更可靠） */
function segSrc(cid){
  if(segURLs[cid]) return segURLs[cid];
  const s=SEGS[cid]; if(!s||!s.b64) return null;
  try{
    const bin=atob(s.b64), n=bin.length, buf=new Uint8Array(n);
    for(let i=0;i<n;i++) buf[i]=bin.charCodeAt(i);
    segURLs[cid]=URL.createObjectURL(new Blob([buf],{type:'audio/mpeg'}));
    return segURLs[cid];
  }catch(e){ return null; }
}
function markPlaying(ev,cid){
  document.querySelectorAll('.pick.playing').forEach(x=>x.classList.remove('playing'));
  if(ev&&ev.currentTarget&&ev.currentTarget.classList.contains('pick')) ev.currentTarget.classList.add('playing');
  else{
    const el=document.querySelector('.pick[data-cid="'+cid+'"]');
    if(el) el.classList.add('playing');
  }
}
function seek(ev,cid,t,e){
  if(ev) ev.stopPropagation();
  const src=segSrc(cid);
  now.textContent=cid+'  '+t+'–'+e;
  markPlaying(ev,cid);
  if(src){
    curEnd=null;                       // 片段自带截断，不需要 timeupdate 停止
    au.src=src;
    const p=au.play();
    if(p&&p.catch) p.catch(()=>{ now.textContent+='  ⚠️ 点下面播放条的 ▶ 再试一次'; });
    return;
  }
  if(!FULL_URL){
    now.textContent='ℹ️ '+cid+' '+t+'–'+e+'：这条观点没有内嵌音频，请到原平台收听 → '+ORIG_URL;
    return;
  }
  /* 回退：整集流播 */
  const target=toSec(t); curEnd=toSec(e);
  now.textContent=cid+'  '+fmt(target)+'–'+fmt(curEnd);
  if(au.getAttribute('src')!==FULL_URL){ au.src=FULL_URL; pendingSeek=target;
    au.load();
    au.addEventListener('loadedmetadata',function om(){au.removeEventListener('loadedmetadata',om);
      if(pendingSeek!==null){try{au.currentTime=pendingSeek}catch(x){};pendingSeek=null;au.play().catch(()=>{});}},{once:true});
    return;
  }
  if(au.readyState>=1){
    trySetTime(target);
  }else{
    pendingSeek=target;
    now.textContent+='  ⏳ 加载音频中，请稍候…';
    au.load();
    const onMeta=()=>{au.removeEventListener('loadedmetadata',onMeta); trySetTime(pendingSeek);};
    au.addEventListener('loadedmetadata',onMeta);
    setTimeout(()=>{if(pendingSeek!==null&&au.readyState<1){
      now.textContent='⚠️ 音频加载超时。可能是网络无法访问该音频源，请点下方播放条手动播放';}},15000);
  }
  function trySetTime(sec){
    pendingSeek=null;
    try{ au.currentTime=sec; }catch(err){}
    const p=au.play();
    if(p&&p.catch) p.catch(err=>{
      now.textContent+='  ⚠️ 播放被拦截，请点播放条上的 ▶';
    });
  }
}
/* ---- 自绘播放条 ---- */
const playbtn=document.getElementById('playbtn'), pfill=document.getElementById('pfill'),
      ptime=document.getElementById('ptime'), ptrack=document.getElementById('ptrack');
function syncBar(){
  const d=au.duration||0, t=au.currentTime||0;
  if(d>0){ pfill.style.width=Math.min(100,t/d*100)+'%'; ptime.textContent=fmt(t)+' / '+fmt(d); }
  else { pfill.style.width='0'; ptime.textContent='0:00'; }
  playbtn.textContent = (au.paused||au.ended) ? '▶' : '❚❚';
}
function togglePlay(){
  if(!au.src){ toast('先点上方任意一条推荐或时间戳'); return; }
  if(au.paused){ const p=au.play(); if(p&&p.catch) p.catch(()=>{now.textContent='⚠️ 播放被系统拦截，请再点一次';}); }
  else au.pause();
}
function seekTo(ratio){
  if(!au.duration) return;
  au.currentTime=Math.max(0,Math.min(1,ratio))*au.duration;
  syncBar();
}
ptrack.addEventListener('click',ev=>{
  const r=ptrack.getBoundingClientRect();
  seekTo((ev.clientX-r.left)/r.width);
});
au.addEventListener('timeupdate',()=>{
  if(curEnd!==null && au.currentTime>=curEnd){au.pause();curEnd=null;now.textContent+='  · 片段结束';}
  syncBar();
});
au.addEventListener('play',syncBar);
au.addEventListener('pause',syncBar);
au.addEventListener('ended',()=>{syncBar();});
au.addEventListener('loadedmetadata',syncBar);
syncBar();
au.addEventListener('error',()=>{
  const c=au.error?au.error.code:0;
  const m={1:'加载被中断',2:'网络错误',3:'解码失败',4:'音频格式不支持或地址不可达'}[c]||'未知错误';
  now.textContent='⚠️ 音频无法播放：'+m+'（code '+c+'）';
});
au.addEventListener('stalled',()=>{ if(au.readyState<2) now.textContent='⏳ 缓冲中…'; });

/* ---------- 编辑推荐 ---------- */
const INIT_PICKS=__PICKS_JSON__;
const REL_CLAIMS=__CLAIMS_MAP__;
const CONTENT_ID=__CONTENT_ID__, CONTENT_TITLE=__CONTENT_TITLE__;
let picks=JSON.parse(JSON.stringify(INIT_PICKS));
let editing=false;

function toast(msg){
  let t=document.getElementById('toast');
  t.textContent=msg;t.classList.add('show');
  clearTimeout(t._tm);t._tm=setTimeout(()=>t.classList.remove('show'),1800);
}
function syncStars(){
  const set=new Set(picks.map(p=>p.claim_id));
  document.querySelectorAll('.star').forEach(s=>{
    s.classList.toggle('on', set.has(s.dataset.cid));
    s.textContent = set.has(s.dataset.cid) ? '★' : '☆';
  });
}
function toggleEdit(){
  editing=!editing;
  document.body.classList.toggle('editing',editing);
  const eb=document.getElementById('editbtn');
  if(eb) eb.textContent = editing ? '✓ 完成编辑' : '✎ 编辑推荐';
  document.getElementById('exportbox').classList.toggle('show', editing);
  if(editing){
    document.querySelectorAll('.grp').forEach(g=>{
      const h=g.querySelector('.grp-h'), k=g.querySelector(':scope > .children');
      if(h&&!g.classList.contains('open')){g.classList.add('open'); if(k) k.classList.remove('collapsed');}
    });
    renderExport(); toast('已进入编辑模式：点 ☆ 加入推荐');
  }
  redraw();
}
function togglePick(ev,cid){
  ev.stopPropagation();
  if(!editing){ toast('先点右上角「✎ 编辑推荐」'); return; }
  const i=picks.findIndex(p=>p.claim_id===cid);
  if(i>=0){ picks.splice(i,1); }
  else{
    const c=REL_CLAIMS[cid]||{};
    picks.push({claim_id:cid,label:c.statement||cid,note:'',timestamp:c.timestamp||'',end:c.end||''});
  }
  rerenderPicks(); syncStars(); renderExport();
}
function removePick(ev,i){ ev.stopPropagation(); picks.splice(i,1); rerenderPicks(); syncStars(); renderExport(); }
function movePick(ev,i,d){
  ev.stopPropagation();
  const j=i+d; if(j<0||j>=picks.length) return;
  [picks[i],picks[j]]=[picks[j],picks[i]];
  rerenderPicks(); renderExport();
}
function rerenderPicks(){
  const box=document.querySelector('.pickbox');
  if(!picks.length){
    if(box) box.remove();
    return;
  }
  let html='<div class="pickhead">★ 我的推荐<span class="cnt">'+picks.length+' 条 · 点击 ▶ 播放</span></div>';
  picks.forEach((p,i)=>{
    const cid=p.claim_id, t=p.timestamp||'', e=p.end||'';
    html+='<div class="pick" data-cid="'+cid+'" data-t="'+t+'" data-e="'+e+'" '
      +'onclick="seek(event,&quot;'+cid+'&quot;,&quot;'+t+'&quot;,&quot;'+e+'&quot;)">'
      +'<span class="pnum">'+(i+1)+'</span>'
      +'<span class="pbody"><span class="ptxt">'+escHtml(p.label||cid)+'</span>'
      +'<span class="pnote view">'+(p.note?'推荐理由：'+escHtml(p.note):'')+'</span>'
      +'<input class="preason" value="'+escHtml(p.note||'')+'" placeholder="写推荐理由（可选）" '
      +'onclick="event.stopPropagation()" oninput="onReason('+i+',this.value)">'
      +'</span>'
      +'<span class="pops"><button onclick="movePick(event,'+i+',-1)">↑</button>'
      +'<button onclick="movePick(event,'+i+',1)">↓</button>'
      +'<button onclick="removePick(event,'+i+')">✕</button></span>'
      +'<span class="pplay">▶ '+t+'</span></div>';
  });
  let el=document.querySelector('.pickbox');
  if(!el){
    el=document.createElement('div'); el.className='pickbox';
    const host=document.querySelector('.root + .children')||document.getElementById('tree');
    host.insertBefore(el, host.firstChild);
  }
  el.innerHTML=html;
  redraw();
}
function onReason(i,v){ picks[i].note=v; renderExport(); }
function escHtml(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')}
function buildJSON(){
  const out=picks.map(p=>({claim_id:p.claim_id,label:p.label,note:p.note||'',
                           timestamp:p.timestamp||'',end:p.end||''}));
  return JSON.stringify({content_id:CONTENT_ID,title:CONTENT_TITLE,picks:out},null,2);
}
function renderExport(){
  const ta=document.getElementById('exptext');
  const n=document.getElementById('expcnt');
  if(ta) ta.value=buildJSON();
  if(n) n.textContent='（当前 '+picks.length+' 条）';
}
function copyExport(){
  const ta=document.getElementById('exptext');
  const txt=buildJSON();
  ta.value=txt;                       // 复制前强制刷新，避免复制到旧内容
  ta.focus(); ta.select(); ta.setSelectionRange(0,txt.length);
  let ok=false;
  try{ ok=document.execCommand('copy'); }catch(e){ ok=false; }
  const verify=()=>{
    if(ok){ toast('已复制 '+picks.length+' 条推荐，发给我即可合入卡片'); return; }
    toast('自动复制被浏览器拦了，已全选，请按 Ctrl/⌘+C 手动复制');
  };
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(()=>{
      toast('已复制 '+picks.length+' 条推荐，发给我即可合入卡片');
    }).catch(verify);
  } else { verify(); }
}
function downloadExport(){
  const blob=new Blob([buildJSON()],{type:'application/json'});
  const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download='picks_'+CONTENT_ID+'.json'; a.click();
}
document.addEventListener('DOMContentLoaded',syncStars);
setTimeout(syncStars,100);

/* ---------- 树形连线 ---------- */
function draw(){
  const tree=document.getElementById('tree');
  const base=tree.getBoundingClientRect();
  const W=tree.scrollWidth, H=tree.scrollHeight;
  svg.setAttribute('width',W); svg.setAttribute('height',H);
  svg.style.width=W+'px'; svg.style.height=H+'px';
  svg.innerHTML='';
  tree.querySelectorAll('.grp').forEach(g=>{
    if(!g.classList.contains('open')) return;
    const kids=g.querySelector(':scope > .children');
    if(!kids||kids.classList.contains('collapsed')) return;
    const hr=g.querySelector(':scope > .grp-h').getBoundingClientRect();
    const x0=hr.left-base.left+11, y0=hr.bottom-base.top;
    Array.from(kids.children).forEach(k=>{
      const r=k.getBoundingClientRect();
      // 指向该子项左侧展开符
      const x1=r.left-base.left+11, y1=r.top-base.top+13;
      if(y1<y0-2) return;
      const d=`M${x0},${y0} L${x0},${y1} L${x1},${y1}`;
      const p=document.createElementNS('http://www.w3.org/2000/svg','path');
      p.setAttribute('d',d);p.setAttribute('fill','none');
      p.setAttribute('stroke','#ced4da');p.setAttribute('stroke-width','1.2');
      svg.appendChild(p);
    });
  });
}
const redraw=()=>{draw();requestAnimationFrame(draw)};
window.addEventListener('resize',redraw);
window.addEventListener('load',()=>{setTimeout(draw,60)});
// 展开动画后重绘
document.addEventListener('transitionend',redraw);
</script>
</body></html>"""


def build_groups(card):
    if card.get("groups"):
        return [(g["gid"], g["name"], list(g["ids"])) for g in card["groups"]]
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


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def load_segments(card, seg_dir):
    """读取 seg_dir 下的 {cid}.mp3，转 base64，返回 {cid:{b64,dur,start,end}}。
    约定：文件名前缀为 claim_id，例如 1_c21.mp3 / c21.mp3 均可。"""
    segs = {}
    audio_url = card["source"].get("audio_url", "")
    if not seg_dir:
        return segs, audio_url
    import base64, glob, os
    # 全量：每条 claim 都内联对应片段（不再只限 picks）
    meta = {c["claim_id"]: (c.get("timestamp", ""), c.get("end", "")) for c in card["claims"]}
    for f in sorted(glob.glob(os.path.join(seg_dir, "*.mp3"))):
        base = os.path.basename(f)
        cid = os.path.splitext(base)[0].split("_")[-1]
        if cid not in meta:
            continue
        with open(f, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        st, en = meta[cid]
        def _sec(t):
            q = [int(x) for x in t.split(":")] if t else [0]
            return q[0] * 60 + q[1] if len(q) == 2 else (q[0] * 3600 + q[1] * 60 + q[2] if len(q) == 3 else 0)
        segs[cid] = {"b64": b64, "start": st, "end": en,
                     "dur": max(0, _sec(en) - _sec(st))}
    # 整集直链始终保留：无内联片段时走远端流播，有片段时作为兜底
    return segs, card["source"].get("audio_url", "")


def render(card: dict, seg_dir=None, mode="audio", chrome=True) -> str:
    """mode="audio"    内联/流播，页面自带播放器
       mode="redirect" 纯导流：不内联任何音频、不请求 CDN，点时间戳只复制定位提示
       chrome=False    去掉顶部的操作按钮行与关系图例（分享给读者看的干净版）"""
    segs_map, full_url = load_segments(card, seg_dir)
    if mode == "redirect":
        segs_map, full_url = {}, ""
    claims = {c["claim_id"]: c for c in card["claims"]}
    people = {p["person_id"]: p for p in card.get("people", [])}
    groups = build_groups(card)
    used = {cid for _, _, ids in groups for cid in ids}
    missing = [c["claim_id"] for c in card["claims"] if c["claim_id"] not in used]
    if missing:
        groups.append(("gx", f"补 · 未入组 {len(missing)} 条", missing))

    # 关系索引（用于反查被引用）
    rels_all = [[c["claim_id"], r["target"], r["type"], r.get("note", "")]
                for c in card["claims"] for r in c.get("relations", [])]

    parts = []
    for idx, (gid, gname, ids) in enumerate(groups):
        color = GROUP_COLORS[int(gid[1:]) % len(GROUP_COLORS)] if gid[1:].isdigit() else "#868e96"
        claim_html = []
        for cid in ids:
            c = claims.get(cid)
            if not c:
                continue
            tags = "".join(f'<span class="tag">{esc(t)}</span>' for t in c.get("tags", [])[:3])
            sp = people.get(c.get("speaker"), {}).get("name", c.get("speaker", ""))
            rels = [r for r in rels_all if r[0] == cid]
            back = [r for r in rels_all if r[1] == cid]
            relbtns = ""
            for _, tgt, rtype, note in rels:
                relbtns += (f'<button class="relbtn" onclick="gotoClaim(\'{tgt}\')" title="{esc(note)}">'
                            f'<i style="background:{REL_COLOR.get(rtype,"#868e96")}"></i>'
                            f'{REL_CN.get(rtype,rtype)} <span class="tgt">{tgt}</span></button>')
            for src, _, rtype, note in back:
                relbtns += (f'<button class="relbtn" onclick="gotoClaim(\'{src}\')" title="{esc(note)}" '
                            f'style="border-style:dashed"><i style="background:{REL_COLOR.get(rtype,"#868e96")};opacity:.5"></i>'
                            f'被{REL_CN.get(rtype,rtype)} <span class="tgt">{src}</span></button>')
            ev = c.get("evidence", "")
            detail = ('<div class="detail">'
                      f'<div class="full">{esc(c["statement"])}</div>'
                      + (f'<div class="ev"><b>证据 / 语料</b>{esc(ev)}</div>' if ev else '')
                      + (f'<div class="rels"><span class="lbl">关系（实线=本节点指向，虚线=被指向）</span>{relbtns}</div>'
                         if relbtns else '')
                      + f'<div class="conf">{esc(c.get("type",""))} · {esc(c.get("confidence",""))} · {esc(sp)} · {esc(c["timestamp"])}–{esc(c["end"])}</div>'
                      '</div>')
            claim_html.append(
                f'<div class="claim" id="claim-{cid}"><div class="claim-h" onclick="toggle(this,\'.claim\')">'
                f'<span class="tri">▶</span>'
                f'<span class="star" data-cid="{cid}" onclick="togglePick(event,\'{cid}\')" title="加入/移出推荐">☆</span>'
                f'<span class="txt">{tags}<span class="cid">{cid}</span>'
                f'{esc(c["statement"])}<span class="sp">{esc(sp)}</span>'
                f'<span class="ts" onclick="seek(event,\'{cid}\',\'{c["timestamp"]}\',\'{c["end"]}\')">'
                f'⏱{c["timestamp"]}–{c["end"]}</span></span></div>'
                f'<div class="children collapsed">{detail}</div></div>')

        parts.append(f'<div class="grp"><div class="grp-h" style="background:{color}" onclick="toggle(this,\'.grp\')">'
                     f'<span class="tri">▶</span>{esc(gname)}<span class="cnt">{len(ids)} 条</span></div>'
                     f'<div class="children collapsed">{"".join(claim_html)}</div></div>')

    # 图例
    used_types = [t for t in REL_COLOR if any(r[2] == t for r in rels_all)]
    legend = "".join(f'<span><i style="background:{REL_COLOR[t]}"></i>{REL_CN.get(t,t)}</span>'
                     for t in used_types)
    colors_js = json.dumps({t: REL_COLOR[t] for t in used_types}, ensure_ascii=False)

    src = card["source"]
    meta = (f'{esc(src.get("platform",""))} · {src.get("duration_sec",0)//60} 分钟 · '
            f'{len(card["claims"])} 条 claim · {len(rels_all)} 条关系 · '
            f'<a href="{src.get("url","")}" target="_blank">原文 ↗</a>')

    # ── 我的推荐区（置顶，card["picks"] 驱动）──
    picks = card.get("picks") or []
    pick_html = ""
    if picks:
        rows = ""
        for i, pk in enumerate(picks, 1):
            cid = pk.get("claim_id", "")
            c = claims.get(cid, {})
            t = pk.get("timestamp") or c.get("timestamp", "")
            e = pk.get("end") or c.get("end", "")
            note = pk.get("note", "")
            label = pk.get("label") or c.get("statement", "")
            rows += (f'<div class="pick" data-cid="{cid}" data-t="{esc(t)}" data-e="{esc(e)}" '
                     f'onclick="seek(event,\'{cid}\',\'{t}\',\'{e}\')">'
                     f'<span class="pnum">{i}</span>'
                     f'<span class="pbody"><span class="ptxt">{esc(label)}</span>'
                     f'<span class="pnote view">' + (f'推荐理由：{esc(note)}' if note else '') + '</span>'
                     f'<input class="preason" value="{esc(note)}" placeholder="写推荐理由（可选）" '
                     f'onclick="event.stopPropagation()" oninput="onReason({i-1},this.value)">'
                     f'</span>'
                     f'<span class="pops"><button onclick="movePick(event,{i-1},-1)">↑</button>'
                     f'<button onclick="movePick(event,{i-1},1)">↓</button>'
                     f'<button onclick="removePick(event,{i-1})">✕</button></span>'
                     f'<span class="pplay">▶ {esc(t)}</span></div>')
        pick_html = (f'<div class="pickbox"><div class="pickhead">★ 我的推荐'
                     f'<span class="cnt">{len(picks)} 条 · 点击直接播放</span></div>{rows}</div>')

    tree = (f'<div class="root">{esc(src["title"][:46])}'
            f'<small>{len(groups)} 主题 / {len(card["claims"])} 观点</small></div>'
            f'<div class="children">{pick_html}{"".join(parts)}</div>')

    tools_block = TOOLS_BLOCK if chrome else ""
    html = (TMPL.replace("__TITLE__", esc(src["title"]))
                .replace("__META__", meta)
                .replace("__TOOLS__", tools_block.replace("__LEGEND__", legend))
                .replace("__TREE__", tree)
                .replace("__PICKBOX__", "")
                .replace("__AUDIO__", json.dumps(full_url, ensure_ascii=False))
                .replace("__FULL_DUR__", str(int(src.get("duration_sec") or 0)))
                .replace("__ORIG_URL__", json.dumps(src.get("url", ""), ensure_ascii=False))
                .replace("__SEGS_JSON__", json.dumps(segs_map, ensure_ascii=False))
                .replace("__REL_CN__", json.dumps(REL_CN, ensure_ascii=False))
                .replace("__COLORS__", colors_js)
                .replace("__PICKS_JSON__", json.dumps(picks, ensure_ascii=False))
                .replace("__CONTENT_ID__", json.dumps(card.get("content_id") or
                         card["source"].get("content_id", ""), ensure_ascii=False))
                .replace("__CONTENT_TITLE__", json.dumps(card["source"]["title"], ensure_ascii=False))
                .replace("__CLAIMS_MAP__", json.dumps(
                    {c["claim_id"]: {"statement": c["statement"], "timestamp": c["timestamp"],
                                     "end": c["end"]} for c in card["claims"]},
                    ensure_ascii=False)))
    if mode == "redirect":
        html = _to_redirect(html, card)
    return html


REDIRECT_CSS = """
<style>
#xzbar{position:fixed;bottom:0;left:0;right:0;z-index:60;background:#fff;
  border-top:1px solid #dee2e6;padding:10px 16px calc(10px + env(safe-area-inset-bottom,0px));
  box-shadow:0 -4px 16px rgba(0,0,0,.06);font-size:13px}
.xzlink{display:flex;align-items:center;gap:9px;text-decoration:none;color:#1a1a1a}
.xzico{width:24px;height:24px;border-radius:50%;background:#ff5a3c;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:13px;flex:none}
.xztxt{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xzgo{color:#ff5a3c;font-weight:600;flex:none}
.xzhint{margin-top:7px;color:#868e96;font-size:12px;line-height:1.55;transition:color .2s}
.xzhint.flash{color:#1971c2;font-weight:500}
body{padding-bottom:96px}
@media(max-width:480px){.xztxt{font-size:12px}.xzhint{font-size:11px}}
</style>
"""

REDIRECT_SEEK = r"""
function seek(ev,cid,t,e){
  if(ev) ev.stopPropagation();
  markPlaying(ev,cid);
  const mins=Math.round(toSec(t)/60);
  const txt='小宇宙《'+SERIES+'》EP.'+EPNO+' 约第 '+mins+' 分钟（'+t+'）';
  const done=(ok)=>{
    const b=document.getElementById('xzhint');
    if(!b) return;
    b.innerHTML=(ok?'✅ 已复制：':'📍 ')+txt+
      '　<a href="'+ORIG_URL+'" target="_blank" rel="noopener" style="color:#ff5a3c">打开小宇宙 →</a>';
    b.classList.add('flash');
    clearTimeout(b._tm); b._tm=setTimeout(()=>b.classList.remove('flash'),2200);
  };
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(()=>done(true)).catch(()=>done(false));
  }else{done(false);}
}
"""


def _to_redirect(html: str, card: dict) -> str:
    """把带播放器的页面剃成纯导流页：删 audio、换成小宇宙导流条、seek 改为复制定位提示。"""
    src = card["source"]
    dur = int(src.get("duration_sec") or 0)
    series = src.get("series", "")
    epno = src.get("episode_no", "")

    # 1) 播放器 → 导流条
    i = html.find('<div id="player">')
    j = html.find('<div id="exportbox">')
    assert i > 0 and j > i, "播放器区块定位失败"
    bar = (
        '<div id="xzbar">'
        f'<a class="xzlink" href="{esc(src.get("url",""))}" target="_blank" rel="noopener">'
        '<span class="xzico">◉</span>'
        f'<span class="xztxt"><b>小宇宙</b>　{esc(series)} EP.{esc(epno)}　·　全程 {dur//60}:{dur%60:02d}</span>'
        '<span class="xzgo">去听原声 →</span></a>'
        '<div class="xzhint" id="xzhint">点任一条后面的 <b>⏱ 时间</b>：自动复制「第 X 分钟」定位提示，'
        '回到小宇宙拖到该处即可。</div></div>'
    )
    html = html[:i] + bar + html[j:]

    # 2) CSS 追加到现有样式表末尾
    html = html.replace("</style>", REDIRECT_CSS.strip()[len("<style>"):], 1)

    # 3) 音频常量清零
    html = re.sub(r'const SEGS=\{.*?\};', 'const SEGS={};', html, count=1, flags=re.S)
    html = re.sub(r'const FULL_URL="[^"]*";', 'const FULL_URL="";', html, count=1)

    # 3b) 整段移除「自绘播放条」初始化（引用已删除的 playbtn/ptrack/au，会抛错中断后续脚本）
    a = html.find('/* ---- 自绘播放条 ---- */')
    b_ = html.find("au.addEventListener('stalled'")
    assert a > 0 and b_ > a, "播放条代码段定位失败"
    b_ = html.find('\n', b_) + 1
    html = html[:a] + '/* 导流模式：无本地播放器 */\n' + html[b_:]
    html = html.replace('id="au"', 'data-dead="au"')

    # 4) seek 整函数替换（花括号配对定位）
    k = html.find('function seek(ev,cid,t,e){')
    assert k > 0, "seek 函数未找到"
    p = html.find('{', k)
    depth, q = 0, p
    while q < len(html):
        if html[q] == '{':
            depth += 1
        elif html[q] == '}':
            depth -= 1
            if depth == 0:
                q += 1
                break
        q += 1
    html = html[:k] + REDIRECT_SEEK.strip() + html[q:]

    # 5) SERIES / EPNO 并入主脚本（seek 里要用）
    html = html.replace(
        'const ORIG_URL=',
        f'const SERIES={json.dumps(series, ensure_ascii=False)};\n'
        f'const EPNO={json.dumps(epno, ensure_ascii=False)};\nconst ORIG_URL=', 1)
    return html


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    card = json.load(open(sys.argv[1]))
    out = sys.argv[2] if len(sys.argv) > 2 else sys.argv[1].replace(".json", "_mindmap.html")
    seg_dir = None
    for i, a in enumerate(sys.argv):
        if a == "--seg" and i + 1 < len(sys.argv):
            seg_dir = sys.argv[i + 1]
    html = render(card, seg_dir)
    open(out, "w").write(html)
    n_seg = len(__import__("re").findall(r'"b64":', html))
    print(f"内联片段: {n_seg} 段")
    print("HTML:", out, f"({len(card['claims'])} claims, "
          f"{sum(len(c.get('relations', [])) for c in card['claims'])} relations)")
