#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATLAS · ГПР-движок — обогащение реестра MPP реальными данными из .mpp-страниц.

Читает mpp/<...>.html (там вшит const TASKS=[...]) и добавляет в реестр MPP{}
в index.html по каждому блоку: start, finish, ct[] (критические листовые работы
с датами/готовностью). Это «правда из MS Project» для дерева/портфеля/прогноза
без зависимости от JVM. Реф.дата снимка = 28.05.2026.
"""
import json, os, re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(HERE, "index.html")
idx = open(IDX, encoding="utf-8").read()

m = re.search(r'const MPP = (\{.*\});', idx)          # реестр — одна строка
reg = json.loads(m.group(1))

T_re = re.compile(r'const TASKS=(\[.*\]),\s*META=', re.DOTALL)

def secshort(c):
    c = c or ""
    for k, v in [("Земл","Земляные"),("Бетон","Бетон"),("елезобетон","Каркас"),
                 ("идроизол","Гидроизоляция"),("ровля","Кровля"),("бщестро","Общестрой"),
                 ("нженер","Инженерка/лифты"),("лагоустр","Благоустройство"),
                 ("спытан","Испытания"),("лининг","Клининг")]:
        if k in c: return v
    return c

out = {}
for key, info in reg.items():
    html = open(os.path.join(HERE, info["src"]), encoding="utf-8").read()
    tasks = json.loads(T_re.search(html).group(1))
    leaf = [t for t in tasks if not t.get("summary")]
    pct = int(round((tasks[0].get("pct") or 0) * 100)) if tasks else 0
    starts = [t["start"] for t in leaf if t.get("start")]
    finishes = [t["finish"] for t in leaf if t.get("finish")]
    start = min(starts) if starts else None
    finish = max(finishes) if finishes else None
    critleaf = [t for t in leaf if t.get("crit")]
    ct = [{"n": t["name"], "c": secshort(t.get("cat")), "s": t.get("start"),
           "f": t.get("finish"), "p": int(round((t.get("pct") or 0) * 100))}
          for t in critleaf]
    cats = []
    for t in critleaf:
        s = secshort(t.get("cat"))
        if s and s not in cats: cats.append(s)
    out[key] = {"src": info["src"], "pct": pct,
                "links": sum(len(t.get("pred", [])) for t in tasks),
                "crit": ", ".join(cats) if cats else "—",
                "start": start, "finish": finish, "ct": ct}

reg_js = "const MPP = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";"
idx = re.sub(r'const MPP = \{.*\};', lambda mm: reg_js, idx, count=1)
open(IDX, "w", encoding="utf-8").write(idx)

# отчёт: системные узкие места по критпути (по cat)
from collections import Counter
cc = Counter()
for v in out.values():
    for t in v["ct"]:
        cc[t["c"]] += 1
print("✓ реестр MPP обогащён:", len(out), "блоков · ct-задач:", sum(len(v["ct"]) for v in out.values()))
print("системные узкие места (cat крит.работ, ×блоков):")
for c, n in cc.most_common(8):
    print(f"   {n:>3}× {c}")
print("размер реестра:", round(len(reg_js)/1024), "КБ")
