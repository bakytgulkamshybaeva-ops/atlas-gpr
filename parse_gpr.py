#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ATLAS · ГПР-движок — парсер по-работного уровня из PDF-отчётов.

Читает отчёты «Отчёт <ЖК> 28.05.2026.pdf» (по-работные таблицы) и собирает
структуру портфель→объект→очередь→блок→раздел→работа в gpr_data.json,
который инлайнится в index.html (Фаза 1 остаётся self-contained).

PDF отдаёт текст НЕ в визуальном порядке → разбор по координатам:
  • якорь строки — № работы в левой колонке (x≈56);
  • колонки распознаются по x-полосам (План%/Факт% — фикс. полосы, даты — dd.mm.yyyy,
    дни/отставание — целые справа от даты окончания);
  • заголовок блока «Пятно "X" N очередь» + его блочные План%/Факт% (authoritative);
  • разделы (Общестрой/Отделка/Инженерка/Благоустройство) — по подписям между группами.

Приёмочный тест (--validate): факт, взвешенный по дням, воспроизводит отчётный
блочный Факт (±2 пп). Блочный План берётся из отчёта (из работ не выводится:
в колонке «План» у всех работ 100%).
"""
import fitz, re, json, datetime, sys, os

STATUS = datetime.date(2026, 5, 28)  # «По состоянию на» из отчётов

PCT  = re.compile(r'^(\d{1,3})%$')
DATE = re.compile(r'^(\d{2})\.(\d{2})\.(\d{4})$')
INT  = re.compile(r'^\d{1,4}$')
NOIDX = re.compile(r'^\d{1,2}$')

# нормализованный ключ раздела -> короткое имя (в отчётах встречаются опечатки:
# «металлаконструкция», «металлаконструкции» и т.п.)
SECTION_KEYS = [
    ("общестроительные", "Общестрой"),
    ("внутриотделочные", "Отделка"),
    ("инженерные",       "Инженерка"),
    ("благоустройство",  "Благоустройство"),
]

# x-полосы колонок План% / Факт% (из замеров: План≈223, Факт≈250)
PLAN_X = (215, 238)
FACT_X = (239, 268)

# заголовок блока — варианты по объектам:
#   Аура:      Пятно "3" 2 очередь
#   Атмосфера: Пятно "25 А" 5 очередь   (имя с пробелом/буквой)
#   Керуен:    Пятно "1,1"- 1 очередь   (дефис после кавычки)
#   Аксай:     Пятно "1,1" 1 очередь
PYATNO = re.compile(r'Пятно\s*"([^"]+)"\s*-?\s*(\d+)\s*очеред', re.IGNORECASE)


def to_date(s):
    m = DATE.match(s)
    return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def visual_lines(words, gap=2.0):
    """Сгруппировать слова в визуальные строки кластеризацией по зазору y.

    Фикс. бакеты дробят строку на границе (токен с y=154.7 уходит в соседний
    бакет от y=154.6) → у строки пропадает % и она теряется. Кластеризация по
    зазору ≤gap между соседними по y словами устойчива к этому; строки таблицы
    отстоят на ~6-8px, перенос названия на ~3px (станет отдельным фрагментом)."""
    ws_sorted = sorted(words, key=lambda w: (w[1], w[0]))
    groups, cur, anchor_y = [], [], None
    for w in ws_sorted:
        if anchor_y is None or abs(w[1] - anchor_y) <= gap:
            cur.append(w)
            if anchor_y is None:
                anchor_y = w[1]
        else:
            groups.append(cur)
            cur, anchor_y = [w], w[1]
    if cur:
        groups.append(cur)
    out = []
    for grp in groups:
        grp = sorted(grp, key=lambda w: w[0])
        out.append({
            "y": min(w[1] for w in grp),
            "ws": grp,
            "text": " ".join(w[4] for w in grp),
        })
    return out


def section_of(text):
    t = text.lower()
    if len(text) > 70:
        return None
    for kw, name in SECTION_KEYS:
        if kw in t:
            return name
    return None


def parse_page_rows(words):
    """Вернуть (block_headers, sections, work_rows) с координатами по странице.

    Разбор по визуальным строкам: строка-работа = первый токен № (1-2 цифры слева)
    + ≥2 процента на строке. Перенос названия (строки без № и без %) пришивается
    к ближайшей работе вторым проходом."""
    lines = visual_lines(words)
    headers, sections, rows = [], [], []
    frag_lines = []  # строки-фрагменты (возможный перенос названия): (y, x0, text)

    for ln in lines:
        ws, text = ln["ws"], ln["text"]
        m = PYATNO.search(text)
        if m:
            # % могут лежать на соседней визуальной строке → ищем по близости ±5px
            near = sorted([w for w in words if abs(w[1] - ln["y"]) <= 5 and PCT.match(w[4])],
                          key=lambda w: w[0])
            pcts = [int(PCT.match(w[4]).group(1)) for w in near]
            headers.append({
                "y": ln["y"], "spot": m.group(1), "queue": int(m.group(2)),
                "plan": pcts[0] if len(pcts) >= 2 else None,
                "fact": pcts[1] if len(pcts) >= 2 else None,
            })
            continue
        sec = section_of(text)
        if sec and not any(PCT.match(w[4]) for w in ws) and not any(DATE.match(w[4]) for w in ws):
            sections.append({"y": ln["y"], "name": sec})
            continue

        first = ws[0]
        pct_ws = sorted([w for w in ws if PCT.match(w[4])], key=lambda w: w[0])
        is_work = NOIDX.match(first[4]) and first[0] < 70 and len(pct_ws) >= 2
        if not is_work:
            # потенциальный перенос названия: текст без № и без процентов/дат
            if ws and not any(PCT.match(w[4]) for w in ws) and not any(DATE.match(w[4]) for w in ws) \
               and not section_of(text):
                frag_lines.append({"y": ln["y"], "x0": first[0], "text": text})
            continue

        plan = next((int(PCT.match(w[4]).group(1)) for w in pct_ws if PLAN_X[0] <= w[0] <= PLAN_X[1]), None)
        fact = next((int(PCT.match(w[4]).group(1)) for w in pct_ws if FACT_X[0] <= w[0] <= FACT_X[1]), None)
        if plan is None: plan = int(PCT.match(pct_ws[0][4]).group(1))
        if fact is None: fact = int(PCT.match(pct_ws[1][4]).group(1))

        dates = sorted([w for w in ws if DATE.match(w[4])], key=lambda w: w[0])
        start = to_date(dates[0][4]) if dates else None
        end   = to_date(dates[-1][4]) if len(dates) >= 2 else (to_date(dates[0][4]) if dates else None)
        endx  = dates[-1][2] if dates else 360

        right = [int(w[4]) for w in ws if INT.match(w[4]) and w[0] > endx + 2 and w[0] < 470]
        days = right[0] if right else (max(1, (end - start).days) if start and end else None)
        lag  = right[1] if len(right) > 1 else 0

        name_ws = [w for w in ws if w is not first and w[0] < PLAN_X[0]
                   and not PCT.match(w[4]) and not DATE.match(w[4]) and not INT.match(w[4])]
        name = re.sub(r'\s+', ' ', " ".join(w[4] for w in name_ws)).strip()

        # правая зона: материалы/договор (есть/нет) + исполнитель (ТОО…/ИП…) + статус
        far = [w[4] for w in sorted(ws, key=lambda w: w[0]) if w[0] >= 460]
        contractor = None
        for i, t in enumerate(far):
            if t in ("ТОО", "ИП"):
                rest = []
                for u in far[i + 1:]:
                    if u in ("подписан", "есть", "нет") or "подписан" in u:
                        break
                    rest.append(u)
                contractor = (t + " " + " ".join(rest)).strip()
                break

        rows.append({
            "y": ln["y"], "no": int(first[4]), "name": name,
            "plan": plan, "fact": fact,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "days": days, "lag": lag,
            "contractor": contractor or None,
        })

    # второй проход — пришить перенос названия (фрагмент между двумя работами)
    rows.sort(key=lambda r: r["y"])
    for fr in frag_lines:
        cand = [r for r in rows if abs(r["y"] - fr["y"]) <= 9]
        if not cand:
            continue
        r = min(cand, key=lambda r: abs(r["y"] - fr["y"]))
        extra = fr["text"].strip()
        if extra and not section_of(extra):
            r["name"] = (r["name"] + " " + extra).strip() if r["name"] else extra
    for r in rows:
        r["name"] = re.sub(r'\s+', ' ', r["name"]).strip()
    return headers, sections, rows


def parse_pdf(path, obj_name, obj_id="obj"):
    doc = fitz.open(path)
    blocks = []           # [{spot,queue,plan,fact, works:[...]}]
    cur = None
    cur_section = "Общестрой"
    for pno in range(doc.page_count):
        words = doc[pno].get_text("words")
        headers, sections, rows = parse_page_rows(words)

        # события страницы в порядке сверху вниз
        events = ([("h", h["y"], h) for h in headers]
                  + [("s", s["y"], s) for s in sections]
                  + [("r", r["y"], r) for r in rows])
        events.sort(key=lambda e: e[1])

        for kind, _, payload in events:
            if kind == "h":
                cur = {"spot": payload["spot"], "queue": payload["queue"],
                       "plan": payload["plan"], "fact": payload["fact"], "works": []}
                blocks.append(cur)
                cur_section = "Общестрой"
            elif kind == "s":
                cur_section = payload["name"]
            elif kind == "r":
                if cur is None:  # работа до первого заголовка — пропустить
                    continue
                if payload["plan"] is None or payload["fact"] is None:
                    continue
                payload = dict(payload); payload["section"] = cur_section
                payload.pop("y", None)
                cur["works"].append(payload)

    # отфильтровать пустые/битые блоки; стабильный порядок очередь→пятно
    blocks = [b for b in blocks if b["works"]]
    blocks.sort(key=lambda b: (b["queue"], b["spot"]))
    return {"id": obj_id, "object": obj_name, "blocks": blocks}


def weighted_fact(works):
    good = [w for w in works if w.get("days")]
    sd = sum(w["days"] for w in good)
    if not sd:
        return None
    return sum((w["fact"] or 0) * w["days"] for w in good) / sd


PDFS = [
    ("Отчет Атмо 28.05.2026 (1).pdf", "atmo",   "ЖК «Атмосфера»"),
    ("Отчет Аура 28.05.2026.pdf",     "aura",   "ЖК «Аура»"),
    ("Отчет Керуен 28.05.2026.pdf",   "keruen", "ЖК «Керуен»"),
    ("Отчет Аксай 28.05.2026.pdf",    "aksai",  "ЖК «Аксай резорт»"),
]
SRC = os.path.expanduser("~/Documents/Claude/gpr-source/ГПР по объектам")


def inject_into_html():
    """Вшить gpr_data.json в index.html (в <script id="gpr-data">)."""
    here = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(here, "gpr_data.json")
    html_path = os.path.join(here, "index.html")
    with open(data_path, encoding="utf-8") as f:
        compact = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    pat = re.compile(r'(<script id="gpr-data" type="application/json">).*?(</script>)', re.DOTALL)
    if not pat.search(html):
        print("!! не найден <script id=\"gpr-data\"> в index.html"); return
    html = pat.sub(lambda m: m.group(1) + compact + m.group(2), html, count=1)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ index.html ← данные вшиты ({round(len(compact)/1024)} КБ)")


def main():
    validate = "--validate" in sys.argv
    if "--build" in sys.argv:
        inject_into_html(); return
    only = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    portfolio = []
    for fname, oid, oname in PDFS:
        if only and only.lower() not in fname.lower() and only.lower() not in oname.lower():
            continue
        path = os.path.join(SRC, fname)
        if not os.path.exists(path):
            print(f"!! нет файла: {path}"); continue
        obj = parse_pdf(path, oname, oid)
        portfolio.append(obj)
        if validate:
            print(f"\n== {oname} ==  блоков: {len(obj['blocks'])}")
            print(f"{'Пятно/оч':<14}{'работ':>6}{'  План отч':>10}{'  Факт отч':>10}{'  Факт(взвеш)':>14}{'  Δ':>7}")
            for b in obj["blocks"]:
                wf = weighted_fact(b["works"])
                d = (wf - b["fact"]) if (wf is not None and b["fact"] is not None) else None
                print(f"{'«'+b['spot']+'» '+str(b['queue'])+' оч':<14}"
                      f"{len(b['works']):>6}"
                      f"{(str(b['plan'])+'%' if b['plan'] is not None else '—'):>10}"
                      f"{(str(b['fact'])+'%' if b['fact'] is not None else '—'):>10}"
                      f"{(f'{wf:.1f}%' if wf is not None else '—'):>14}"
                      f"{(f'{d:+.1f}' if d is not None else '—'):>7}")
    out = {"status_date": STATUS.isoformat(), "portfolio": portfolio}
    if not validate:
        dest = os.path.join(os.path.dirname(__file__), "gpr_data.json")
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        nb = sum(len(o["blocks"]) for o in portfolio)
        nw = sum(len(b["works"]) for o in portfolio for b in o["blocks"])
        print(f"✓ {dest}\n  объектов {len(portfolio)} · блоков {nb} · работ {nw}")


if __name__ == "__main__":
    main()
