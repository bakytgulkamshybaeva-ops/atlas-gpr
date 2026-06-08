#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATLAS · ГПР-движок — генерация реальных ГПР-страниц из .mpp-экстракта.

Вход: /tmp/all_mpp.json (вывод MppExtract на всех .mpp).
Шаблон: mpp/aura-3.html (присланный пользователем рендер — WBS+связи+критпуть+hover).
Делает: mpp/<oid>-<slug>.html на каждый блок + вшивает реестр MPP{} в index.html.
"""
import json, os, re, unicodedata

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # gpr-engine/
MPPDIR = os.path.join(HERE, "mpp")
TEMPLATE = open(os.path.join(MPPDIR, "aura-3.html"), encoding="utf-8").read()

raw = open("/tmp/all_mpp.json", encoding="utf-8").read()
ALL = json.loads(raw[raw.index("{"):])

OBJ = [("Атмосфера", "atmo", "ЖК «Атмосфера»"), ("Аура", "aura", "ЖК «Аура»"),
       ("Керуен", "keruen", "ЖК «Керуен»"), ("Аксай", "aksai", "ЖК «Аксай резорт»")]
TRANSLIT = {"А":"A","Б":"B","В":"V","Г":"G","Д":"D","Е":"E"}

def oid_of(base):
    for kw, oid, _ in OBJ:
        if kw in base: return oid
    return "obj"

def name_of(oid):
    return {o[1]: o[2] for o in OBJ}[oid]

def spot_of(base):
    return re.sub(r'^ЖК\s+\S+\s+(пятно\s+)?', '', base[:-4]).strip()

def slug(spot):
    s = spot
    for k, v in TRANSLIT.items(): s = s.replace(k, v)
    return re.sub(r'[^0-9A-Za-z]+', '-', s).strip('-')

# блоки движка (из gpr_data.json) — куда привязывать реестр
gd = json.load(open(os.path.join(HERE, "gpr_data.json"), encoding="utf-8"))
engine_spots = {(o["id"], b["spot"]) for o in gd["portfolio"] for b in o["blocks"]}

T_re = re.compile(r'const TASKS=\[.*\],\s*META=\{.*?\};', re.DOTALL)
title_re = re.compile(r'<title>.*?</title>', re.DOTALL)
h1_re = re.compile(r'<h1>.*?</h1>', re.DOTALL)
sub_re = re.compile(r'<div class="sub">.*?</div>', re.DOTALL)

registry = {}
generated = 0
for base, data in ALL.items():
    base = unicodedata.normalize("NFC", base)   # macOS отдаёт имена в NFD (й = и+˘)
    if "error" in data:
        print("  ERR", base, data["error"][:50]); continue
    oid, spot = oid_of(base), spot_of(base)
    tasks = data["tasks"]; meta = data["meta"]
    links = sum(len(t["pred"]) for t in tasks)
    root_pct = int(round((tasks[0]["pct"] or 0) * 100)) if tasks else 0
    crit_leaf = [t for t in tasks if t["crit"] and not t["summary"]]
    crit_cats = []
    for t in crit_leaf:
        c = t.get("cat") or "—"
        if c not in crit_cats: crit_cats.append(c)
    crit_str = ", ".join(crit_cats) if crit_cats else "—"
    # границы оси — из min/max дат задач (в .mpp дата старта проекта бывает устаревшей)
    starts = [t["start"] for t in tasks if t["start"]]
    finishes = [t["finish"] for t in tasks if t["finish"]]
    m_start = min(starts) if starts else meta["start"]
    m_finish = max(finishes) if finishes else meta["finish"]
    meta2 = {"start": m_start, "finish": m_finish, "pct": root_pct/100,
             "name": f"{name_of(oid)} — Пятно {spot}", "src": base}
    period = f"{m_start}–{m_finish}" if m_start else "—"
    title = f"ГПР — {name_of(oid)} — Пятно {spot}"
    sub = (f'<div class="sub">Источник: MS Project «{base}» · период {period} · '
           f'готовность {root_pct}% · связей: {links} (Finish→Start) · критпуть: {crit_str}</div>')

    html = TEMPLATE
    html = title_re.sub(f"<title>{title}</title>", html, count=1)
    html = h1_re.sub(f"<h1>График производства работ — {name_of(oid)} — Пятно {spot}</h1>", html, count=1)
    html = sub_re.sub(sub, html, count=1)
    new_data = ("const TASKS=" + json.dumps(tasks, ensure_ascii=False, separators=(",", ":"))
                + ", META=" + json.dumps(meta2, ensure_ascii=False, separators=(",", ":")) + ";")
    html, n = T_re.subn(lambda m: new_data, html, count=1)
    if n != 1:
        print("  !! не заменил TASKS в", base); continue

    fn = f"{oid}-{slug(spot)}.html"
    with open(os.path.join(MPPDIR, fn), "w", encoding="utf-8") as f:
        f.write(html)
    generated += 1
    if (oid, spot) in engine_spots:
        registry[f"{oid}/{spot}"] = {"src": f"mpp/{fn}", "pct": root_pct, "links": links, "crit": crit_str}
    else:
        print(f"  (вне отчёта, без привязки) {oid}/{spot} → {fn}")

# реестр в index.html
idx_path = os.path.join(HERE, "index.html")
idx = open(idx_path, encoding="utf-8").read()
reg_js = "const MPP = " + json.dumps(registry, ensure_ascii=False) + ";"
idx2, n = re.subn(r'const MPP = \{.*\};', reg_js, idx, count=1)
if n == 1:
    open(idx_path, "w", encoding="utf-8").write(idx2)
    print(f"✓ index.html ← реестр MPP ({len(registry)} блоков привязано)")
else:
    print("!! не нашёл строку const MPP в index.html")
print(f"✓ сгенерировано HTML: {generated} · в реестре: {len(registry)}")
