#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATLAS · ГПР-движок — обогащение реестра MPP реальными данными из .mpp-страниц
+ расчёт снабжения «материал до старта» (SUPPLY).

Читает mpp/<...>.html (вшитый const TASKS=[...]) →
  • реестр MPP{} (start, finish, ct[крит.листы]) для дерева/прогноза/критпути;
  • SUPPLY[] — что заказать: для не завершённых работ «заказать-до = старт − срок
    поставки(оценка по типу работы)», в горизонте до +90 дн от снимка.
Инжектит обе константы в index.html. Реф.дата снимка = 28.05.2026.
"""
import json, os, re, datetime
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDX = os.path.join(HERE, "index.html")
idx = open(IDX, encoding="utf-8").read()
REF = datetime.date(2026, 5, 28)

reg = json.loads(re.search(r'const MPP = (\{.*\});', idx).group(1))
T_re = re.compile(r'const TASKS=(\[.*\]),\s*META=', re.DOTALL)

def secshort(c):
    c = c or ""
    for k, v in [("Земл","Земляные"),("Бетон","Бетон"),("елезобетон","Каркас"),
                 ("идроизол","Гидроизоляция"),("ровля","Кровля"),("бщестро","Общестрой"),
                 ("нженер","Инженерка/лифты"),("лагоустр","Благоустройство"),
                 ("спытан","Испытания"),("лининг","Клининг")]:
        if k in c: return v
    return c

# ДЛИННЫЕ позиции закупа (lead ≥ ~35 дн) — то, что надо заказывать заранее.
# ОЦЕНКА срока поставки, калибровать с PM. Короткие/местные материалы не включаем.
LONG = [
    (("монтаж лифт", "лифтов"), 75, "Лифты (оборудование)"),
    (("металлоконстр", "металлаконстр"), 60, "Металлоконструкции"),
    (("стеклопакет", "монтаж окон", "оконных проф"), 40, "Окна / витражи"),
    (("двери",), 35, "Двери"),
    (("оборудования (апс",), 40, "АПС — оборудование"),
    (("видеонаблюд", "оборудования (видео"), 40, "Видеонаблюдение"),
    (("домофон",), 40, "Домофоны"),
    (("насос", "тепловой пункт"), 40, "Насосы / ИТП"),
    (("устройство фасада", "вент. фасад", "вентилируемый фасад"), 35, "Фасад (система)"),
    (("этажных щит", "врщ", "грщ"), 35, "Щиты ВРУ / ГРЩ"),
]
EXCLUDE = ("кнопк", "пуско", "наладк", "решетк")       # монтаж/наладка, не закуп
def matchlong(name):
    s = (name or "").lower()
    if any(k in s for k in EXCLUDE): return None
    for kws, d, label in LONG:
        if any(k in s for k in kws): return (d, label)
    return None

def pdate(s): return datetime.date.fromisoformat(s)

out, supply = {}, []
for key, info in reg.items():
    oid, spot = key.split("/", 1)
    tasks = json.loads(T_re.search(open(os.path.join(HERE, info["src"]), encoding="utf-8").read()).group(1))
    leaf = [t for t in tasks if not t.get("summary")]
    pct = int(round((tasks[0].get("pct") or 0) * 100)) if tasks else 0
    starts = [t["start"] for t in leaf if t.get("start")]
    finishes = [t["finish"] for t in leaf if t.get("finish")]
    critleaf = [t for t in leaf if t.get("crit")]
    ct = [{"n": t["name"], "c": secshort(t.get("cat")), "s": t.get("start"),
           "f": t.get("finish"), "p": int(round((t.get("pct") or 0) * 100))} for t in critleaf]
    cats = []
    for t in critleaf:
        s = secshort(t.get("cat"))
        if s and s not in cats: cats.append(s)
    out[key] = {"src": info["src"], "pct": pct,
                "links": sum(len(t.get("pred", [])) for t in tasks),
                "crit": ", ".join(cats) if cats else "—",
                "start": min(starts) if starts else None,
                "finish": max(finishes) if finishes else None, "ct": ct}
    # снабжение: незавершённые работы с датой старта
    seen = {}                                  # дедуп по типу закупа на блок → самый ранний фронт
    for t in leaf:
        nm = (t.get("name") or "").strip(); p = int(round((t.get("pct") or 0) * 100)); st = t.get("start")
        if not nm or not st or p >= 100: continue
        ml = matchlong(nm)
        if not ml: continue
        L, label = ml
        d = pdate(st)
        if d < REF - datetime.timedelta(days=7) or d > REF + datetime.timedelta(days=180): continue  # предстоящие фронты, горизонт ~полгода
        if label not in seen or d < seen[label][0]:
            seen[label] = (d, L, nm)
    for label, (d, L, nm) in seen.items():
        ob = d - datetime.timedelta(days=L)
        status = "overdue" if ob < REF else ("now" if ob <= REF + datetime.timedelta(days=14) else "soon")
        supply.append({"o": oid, "b": spot, "n": label, "c": nm[:42],
                       "s": d.isoformat(), "l": L, "ob": ob.isoformat(), "st": status})

supply.sort(key=lambda x: x["ob"])

reg_js = "const MPP = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";"
idx = re.sub(r'const MPP = \{.*\};', lambda mm: reg_js, idx, count=1)
sup_js = "const SUPPLY = " + json.dumps(supply, ensure_ascii=False, separators=(",", ":")) + ";"
if re.search(r'const SUPPLY = \[.*?\];', idx):
    idx = re.sub(r'const SUPPLY = \[.*?\];', lambda mm: sup_js, idx, count=1)
else:
    print("!! нет плейсхолдера const SUPPLY = []; в index.html")
open(IDX, "w", encoding="utf-8").write(idx)

byst = Counter(x["st"] for x in supply)
print(f"✓ MPP обогащён: {len(out)} блоков · ct {sum(len(v['ct']) for v in out.values())}")
print(f"✓ SUPPLY: {len(supply)} позиций · просрочен {byst['overdue']} · сейчас {byst['now']} · скоро {byst['soon']}")
print("реестр %dКБ · supply %dКБ" % (len(reg_js)//1024, len(sup_js)//1024))
