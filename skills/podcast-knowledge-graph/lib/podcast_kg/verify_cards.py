#!/usr/bin/env python3
"""跨卡实体/人物归一校验

由 `podcast-kg verify` 调用。三类输出:
  A. id 冲突    —— 同名（或同别名）在不同卡里用了不同 id
  B. 疑似同一  —— 名称高度相似但 id 不同（归一化后相同、别名交叉）
  C. 新实体    —— 当前注册表中不存在的实体（需人工确认后写入）
"""
import json, re, unicodedata, os
from collections import defaultdict


def norm(s: str) -> str:
    """归一化：去空格/标点/括号内容/大小写，用于相似度判定。"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[（(].*?[）)]", "", s)      # 去括号补充说明
    s = re.sub(r"[\s\-_·・./]+", "", s)
    return s


def slugify(s: str) -> str:
    """中文无法直接 slug 时，回退为拼音占位标记。"""
    s = unicodedata.normalize("NFKC", s).strip()
    if re.fullmatch(r"[A-Za-z0-9 .\-_]+", s):
        return re.sub(r"[\s_.]+", "-", s.lower()).strip("-")
    return None  # 纯中文名，需人工给 slug


def collect(files):
    recs = defaultdict(list)   # norm_name -> [(card, id, name, type)]
    by_id = defaultdict(set)   # id -> {(card, name)}
    for f in files:
        card = json.load(open(f, encoding="utf-8"))
        short = os.path.basename(f).replace("知识卡_", "").replace(".json", "")
        for e in card.get("entities", []):
            eid = e.get("entity_id") or e.get("name")
            name = e.get("name", eid)
            aliases = e.get("aliases", [])
            for n in [name] + list(aliases):
                recs[norm(n)].append((short, eid, name, e.get("type", "entity")))
            by_id[eid].add((short, name))
        for p in card.get("people", []):
            pid = p.get("person_id")
            name = p.get("name", pid)
            for n in [name] + list(p.get("aliases", [])):
                recs[norm(n)].append((short, pid, name, "person"))
            by_id[pid].add((short, name))
    return recs, by_id


CORE_DIMS = ["contrarian_views", "opportunities", "action_items",
             "metrics", "methods", "mental_models"]
DIM_CN = {"contrarian_views": "反共识", "opportunities": "机会", "action_items": "行动",
          "metrics": "量化", "methods": "方法步骤", "mental_models": "心智模型"}
# 各维度的文本信号词（用于漏抽检测）
DIM_SIGNALS = {
    "contrarian_views": ["很多人认为", "大家认为", "主流认为", "其实不是", "反共识", "恰恰相反", "误区", "颠覆"],
    "opportunities": ["机会在", "巨大机会", "最大的机会", "空白", "没人做", "窗口期", "红利", "赛道", "切入点"],
    "action_items": ["你去做", "第一步", "建议你", "应该先", "可以先", "做法是"],
    "metrics": ["%", "亿", "万", "倍", "个月", "美元"],
    "methods": ["第一步", "第二步", "三步", "流程", "方法论", "步骤"],
    "mental_models": ["就像", "好像", "类比", "好比", "相当于", "理论", "模型"],
}
# 误报抑制：这些词命中不计入（避免"机会成本"被当作"机会"）
DIM_STOPWORDS = {
    "opportunities": ["机会成本"],
}


def check_coverage(card, transcript_text=None, label=""):
    """检查 6 个共性维度的覆盖情况；有转写文本时做漏抽检测。"""
    ext = card.get("extensions", {}) or {}
    print("=" * 70)
    print(f"D. 共性维度覆盖 {label}")
    print("=" * 70)
    for d in CORE_DIMS:
        v = ext.get(d)
        n = len(v) if isinstance(v, list) else (1 if v else 0)
        status = f"有 {n} 条" if n else "省略"
        flag = ""
        if not n and transcript_text:
            txt = transcript_text
            for stop in DIM_STOPWORDS.get(d, []):
                txt = txt.replace(stop, "")
            hits = sum(txt.count(s) for s in DIM_SIGNALS[d])
            if hits >= 5:
                flag = f"  ⚠️ 疑似漏抽（转写中命中 {hits} 次信号词）"
        print(f"  {DIM_CN[d]:8s} {status:10s}{flag}")
    private = [k for k in ext if k not in CORE_DIMS]
    if private:
        print(f"  私有维度: {private}")


def report(recs, by_id):
    print("=" * 70)
    print("A. id 冲突（同一名称用了不同 id）")
    print("=" * 70)
    conflicts = 0
    for n, lst in sorted(recs.items()):
        ids = {x[1] for x in lst}
        if len(ids) > 1:
            conflicts += 1
            print(f"  [{lst[0][2]}]  →  ids: {sorted(ids)}")
            for card, eid, name, typ in lst:
                print(f"      - {card:28s} {eid:24s} ({typ})")
    if not conflicts:
        print("  （无）")

    print()
    print("=" * 70)
    print("B. 跨卡共用实体（已经对上的）")
    print("=" * 70)
    shared = 0
    for n, lst in sorted(recs.items()):
        cards = {x[0] for x in lst}
        ids = {x[1] for x in lst}
        if len(cards) > 1 and len(ids) == 1:
            shared += 1
            print(f"  {lst[0][1]:22s} {lst[0][2]:28s} 出现在 {len(cards)} 卡: {sorted(cards)}")
    if not shared:
        print("  （无）")

    print()
    print("=" * 70)
    print("C. 全量 ID 清单（供注册表草案）")
    print("=" * 70)
    for eid in sorted(by_id):
        names = sorted({x[1] for x in by_id[eid]})
        cards = sorted({x[0] for x in by_id[eid]})
        print(f"  {eid:26s} {' / '.join(names):28s} {cards}")
    return conflicts


def build_registry(files):
    """生成注册表草案：每个 id 一条，含 name/aliases/cards/type。"""
    reg = {}
    for f in files:
        card = json.load(open(f, encoding="utf-8"))
        cid = card.get("content_id", f)
        for e in card.get("entities", []):
            eid = e.get("entity_id") or e.get("name")
            r = reg.setdefault(eid, {"id": eid, "name": e.get("name", eid),
                                     "aliases": [], "type": e.get("type", "entity"),
                                     "cards": []})
            for a in e.get("aliases", []) or []:
                if a not in r["aliases"]:
                    r["aliases"].append(a)
            r["cards"].append(cid)
        for p in card.get("people", []):
            pid = p.get("person_id")
            r = reg.setdefault(pid, {"id": pid, "name": p.get("name", pid),
                                     "aliases": [], "type": "person",
                                     "cards": []})
            r["cards"].append(cid)
    for v in reg.values():
        v["cards"] = sorted(set(v["cards"]))
    return reg


def verify(files):
    """Cross-card entity/person normalisation report."""
    recs, by_id = collect(files)
    return report(recs, by_id)


def write_registry(out, files):
    """Write a registry draft for the given cards."""
    reg = build_registry(files)
    parent = os.path.dirname(out)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    print(f"注册表草案已写入 {out}（{len(reg)} 条）")
    return out


def coverage(card_path, transcript_path=None):
    """Coverage report for the six core dimensions."""
    card = json.load(open(card_path, encoding="utf-8"))
    txt = open(transcript_path, encoding="utf-8").read() if transcript_path else None
    check_coverage(card, txt, os.path.basename(card_path))
