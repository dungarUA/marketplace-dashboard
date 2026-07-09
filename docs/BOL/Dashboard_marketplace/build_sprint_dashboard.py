#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Собирает дашборд «Спринт 50/мес» для CleanWin.

Источники (всё локально, ничего не выдумывает):
  • Штук/мес (Bol+Amazon) — тянутся АВТОМАТИЧЕСКИ из marketplace_dashboard.html
    (const MONTHLY=..., который каждый день обновляет update_dashboard.py).
  • Отзывы и Kwaliteitsscore — из sprint_manual.json (ручной ввод раз в неделю).

Результат: самодостаточный Dashboard_Спринт_50.html (данные вшиты, без fetch/CORS).
Запуск: python build_sprint_dashboard.py
Автозапуск: добавить вызов после update_dashboard.py в Task Scheduler (см. setup_autorun.md).
"""
import json, re, os, sys
from datetime import date

HERE       = os.path.dirname(os.path.abspath(__file__))
SRC_HTML   = os.path.join(HERE, "marketplace_dashboard.html")
MANUAL     = os.path.join(HERE, "sprint_manual.json")
OUT_HTML   = os.path.join(HERE, "Dashboard_Спринт_50.html")

MONTHS_RU = {1:"янв",2:"фев",3:"мар",4:"апр",5:"май",6:"июн",
             7:"июл",8:"авг",9:"сен",10:"окт",11:"ноя",12:"дек"}


def read_monthly():
    """Достаёт const MONTHLY={...} из основного дашборда и парсит в dict."""
    if not os.path.exists(SRC_HTML):
        print(f"⚠️  Не найден {SRC_HTML} — штуки/мес недоступны.")
        return {}
    html = open(SRC_HTML, encoding="utf-8").read()
    m = re.search(r"const MONTHLY=(\{.*?\})\s*[;\n]", html, re.S)
    if not m:
        print("⚠️  const MONTHLY не найден в marketplace_dashboard.html")
        return {}
    raw = m.group(1)
    # ключи в JS без кавычек (bol_ord и т.п.) → делаем валидный JSON
    raw = re.sub(r'([{,])\s*([a-zA-Z_]\w*)\s*:', r'\1"\2":', raw)
    try:
        return json.loads(raw)
    except Exception as e:
        print(f"⚠️  Не разобрал MONTHLY: {e}")
        return {}


def build_units_series(monthly):
    """[(YYYY-MM, units, bol, amz), ...] по возрастанию месяца."""
    out = []
    for k in sorted(monthly):
        v = monthly[k]
        bol = int(v.get("bol_ord", 0))
        amz = int(v.get("amz_ord", 0))
        out.append((k, bol + amz, bol, amz))
    return out


def month_label(ym):
    y, m = ym.split("-")
    return f"{MONTHS_RU[int(m)]} {y[2:]}"


def main():
    manual  = json.load(open(MANUAL, encoding="utf-8"))
    monthly = read_monthly()
    series  = build_units_series(monthly)

    target   = manual["target_units"]
    deadline = manual["deadline"]
    today    = date.today()
    dl       = date.fromisoformat(deadline)
    days_left = (dl - today).days

    cur_ym = today.strftime("%Y-%m")
    cur = next((s for s in series if s[0] == cur_ym), None)
    cur_units = cur[1] if cur else 0
    cur_bol   = cur[2] if cur else 0
    cur_amz   = cur[3] if cur else 0

    # проекция на конец месяца по темпу
    import calendar
    dim = calendar.monthrange(today.year, today.month)[1]
    day = today.day
    projection = round(cur_units / day * dim) if day > 0 else 0

    baseline = manual.get("baseline_units", 0)
    max_units = max([s[1] for s in series] + [target, 1])

    # ── бары штук/мес ──
    bars = ""
    for ym, u, bol, amz in series[-9:]:
        h = int(u / max_units * 140)
        bh = int(bol / max_units * 140)
        ah = int(amz / max_units * 140)
        is_cur = (ym == cur_ym)
        bars += f'''
        <div class="barcol">
          <div class="barval">{u}</div>
          <div class="bar" style="height:{max(h,2)}px" title="Bol {bol} + Amazon {amz}">
            <div class="seg amz" style="height:{ah}px"></div>
            <div class="seg bol" style="height:{bh}px"></div>
          </div>
          <div class="barlbl{' cur' if is_cur else ''}">{month_label(ym)}</div>
        </div>'''
    target_line_bottom = int(target / max_units * 140) + 44  # +оффсет под подпись

    # ── отзывы ──
    rv = manual["reviews"]
    def stars(avg):
        if avg is None: return "—"
        full = int(round(avg))
        return "★"*full + "☆"*(5-full) + f"  {avg}".replace(".", ",")
    def rev_card(name, d, icon):
        avg = d.get("avg")
        goal_c = d.get("goal_count", 0)
        cnt = d.get("count", 0)
        pct = int(min(cnt/goal_c*100,100)) if goal_c else 0
        note = d.get("note","")
        goal_txt = f"цель {goal_c}+ / ★{str(d.get('goal_avg','')).replace('.',',')}" if goal_c else "нет KPI"
        avgcls = "ok" if (avg or 0) >= 4.2 else ("warn" if (avg or 0) >= 3.5 else "bad")
        return f'''
        <div class="rev">
          <div class="revhd">{icon} {name}</div>
          <div class="revcount">{cnt}<span> отзывов</span></div>
          <div class="stars {avgcls}">{stars(avg)}</div>
          <div class="revbar"><div style="width:{pct}%"></div></div>
          <div class="revgoal">{goal_txt}</div>
          {f'<div class="revnote">{note}</div>' if note else ''}
        </div>'''

    reviews_html = (rev_card("Bol", rv["bol"], "🟦")
                    + rev_card("Amazon", rv["amazon"], "🟧")
                    + rev_card("Сайт", rv["site"], "🌐"))

    # ── Kwaliteitsscore ──
    ks = manual["kwaliteitsscore"]
    ks_val, ks_goal = ks["value"], ks["goal"]
    ks_pct = int(min(ks_val/100*100,100))
    ks_ok  = ks_val >= ks_goal
    ks_gpos = int(ks_goal/100*100)

    acos = manual.get("acos", {})

    prog_pct = int(min(projection/target*100, 100))
    fact_pct = int(min(cur_units/target*100, 100))

    updated = manual.get("updated","")
    fetched = monthly and "из marketplace_dashboard.html" or "—"

    html = f'''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CleanWin · Спринт 50/мес</title>
<style>
:root{{--ink:#12232e;--mut:#5b7180;--line:#e2e8ee;--bg:#f6f8fa;--card:#fff;
--bol:#1f4fd8;--amz:#ff9900;--good:#12924b;--warn:#c88a00;--bad:#d0402c;--accent:#0f766e;}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:var(--bg);color:var(--ink);padding:22px}}
.wrap{{max-width:1060px;margin:0 auto}}
h1{{font-size:22px;font-weight:600;margin:0 0 2px}}
.sub{{color:var(--mut);font-size:13px;margin-bottom:18px}}
.grid{{display:grid;gap:16px}}
.g2{{grid-template-columns:1.4fr 1fr}}
@media(max-width:820px){{.g2{{grid-template-columns:1fr}}}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}}
.card h2{{font-size:14px;font-weight:600;margin:0 0 14px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}}
.hero .big{{font-size:52px;font-weight:700;line-height:1}}
.hero .big small{{font-size:20px;color:var(--mut);font-weight:600}}
.hero .row{{display:flex;gap:26px;align-items:flex-end;margin-bottom:14px;flex-wrap:wrap}}
.metric .lbl{{font-size:12px;color:var(--mut);margin-bottom:2px}}
.metric .v{{font-size:26px;font-weight:700}}
.pbar{{height:14px;background:#eef1f4;border-radius:8px;overflow:hidden;position:relative;margin:6px 0 4px}}
.pbar>div{{height:100%;border-radius:8px}}
.pbar .fact{{background:var(--accent)}}
.pbar .proj{{background:repeating-linear-gradient(45deg,#9fc7c2,#9fc7c2 6px,#b9d8d4 6px,#b9d8d4 12px)}}
.chip{{display:inline-block;font-size:12px;font-weight:600;padding:3px 9px;border-radius:20px}}
.chip.ok{{background:#e3f5ea;color:var(--good)}} .chip.bad{{background:#fbe7e3;color:var(--bad)}}
.chip.warn{{background:#fbf1d9;color:var(--warn)}}
.chart{{display:flex;align-items:flex-end;gap:10px;height:190px;position:relative;padding-top:4px;border-bottom:1px solid var(--line)}}
.barcol{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}}
.bar{{width:70%;max-width:46px;display:flex;flex-direction:column-reverse;border-radius:5px 5px 0 0;overflow:hidden;background:#eef1f4}}
.seg.bol{{background:var(--bol)}} .seg.amz{{background:var(--amz)}}
.barval{{font-size:12px;font-weight:700;margin-bottom:3px}}
.barlbl{{font-size:11px;color:var(--mut);margin-top:6px}} .barlbl.cur{{color:var(--accent);font-weight:700}}
.tline{{position:absolute;left:0;right:0;border-top:2px dashed #d0402c}}
.tline span{{position:absolute;right:0;top:-16px;font-size:11px;color:var(--bad);font-weight:700;background:var(--card);padding:0 4px}}
.legend{{display:flex;gap:16px;font-size:12px;color:var(--mut);margin-top:10px}}
.legend i{{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:5px;vertical-align:-1px}}
.revs{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
@media(max-width:820px){{.revs{{grid-template-columns:1fr}}}}
.rev{{border:1px solid var(--line);border-radius:12px;padding:13px}}
.revhd{{font-size:13px;font-weight:600;margin-bottom:6px}}
.revcount{{font-size:30px;font-weight:700;line-height:1}} .revcount span{{font-size:12px;color:var(--mut);font-weight:500}}
.stars{{font-size:15px;letter-spacing:1px;margin:5px 0}}
.stars.ok{{color:var(--good)}} .stars.warn{{color:var(--warn)}} .stars.bad{{color:var(--bad)}}
.revbar{{height:7px;background:#eef1f4;border-radius:5px;overflow:hidden;margin:6px 0 4px}}
.revbar>div{{height:100%;background:var(--accent);border-radius:5px}}
.revgoal{{font-size:11px;color:var(--mut)}} .revnote{{font-size:11px;color:var(--mut);margin-top:6px;font-style:italic}}
.gauge{{display:flex;align-items:center;gap:18px}}
.gwrap{{flex:1}}
.gbar{{height:22px;background:#eef1f4;border-radius:12px;position:relative;overflow:visible}}
.gbar>div{{height:100%;border-radius:12px}}
.ggoal{{position:absolute;top:-6px;bottom:-6px;width:3px;background:var(--ink)}}
.ggoal span{{position:absolute;top:-18px;left:-10px;font-size:11px;font-weight:700;white-space:nowrap}}
.gval{{font-size:40px;font-weight:700;line-height:1}}
.foot{{color:var(--mut);font-size:12px;margin-top:14px;text-align:center}}
.diag{{display:flex;gap:22px;flex-wrap:wrap;font-size:13px;color:var(--mut)}}
.diag b{{color:var(--ink)}}
</style></head>
<body><div class="wrap">
<h1>CleanWin · Спринт 50 швабр/мес</h1>
<div class="sub">Цель к {dl.day:02d}.{dl.month:02d}.{dl.year} · осталось <b>{days_left} дн.</b> · штук/мес — авто {fetched} · отзывы/Kwaliteit обновлены {updated}</div>

<div class="grid g2">
  <div class="card hero">
    <h2>Главное число — штук/мес (Bol + Amazon)</h2>
    <div class="row">
      <div><div class="big">{cur_units}<small> / {target}</small></div>
        <div class="metric"><div class="lbl">факт за {month_label(cur_ym)} (на сегодня)</div></div></div>
      <div class="metric"><div class="lbl">проекция на конец месяца</div><div class="v">≈ {projection}</div></div>
      <div class="metric"><div class="lbl">было в июне</div><div class="v">{baseline}</div></div>
    </div>
    <div class="pbar"><div class="proj" style="width:{prog_pct}%"></div></div>
    <div class="pbar"><div class="fact" style="width:{fact_pct}%"></div></div>
    <div style="font-size:12px;color:var(--mut)">Сплошная — факт ({fact_pct}% цели) · штриховая — проекция ({prog_pct}% цели)</div>
    <div style="margin-top:12px">{'<span class="chip ok">проекция ≥ цели ✔</span>' if projection>=target else ('<span class="chip warn">на траектории роста</span>' if projection>baseline else '<span class="chip bad">ниже базы — жать рычаги</span>')}
      &nbsp; Bol {cur_bol} · Amazon {cur_amz}</div>
  </div>

  <div class="card">
    <h2>Kwaliteitsscore Bol → Select Deals</h2>
    <div class="gauge">
      <div class="gval" style="color:{'var(--good)' if ks_ok else 'var(--bad)'}">{ks_val}</div>
      <div class="gwrap">
        <div class="gbar">
          <div style="width:{ks_pct}%;background:{'var(--good)' if ks_ok else 'var(--bad)'}"></div>
          <div class="ggoal" style="left:{ks_gpos}%"><span>цель {ks_goal}</span></div>
        </div>
        <div style="font-size:12px;color:var(--mut);margin-top:12px">{ks['note']}</div>
      </div>
    </div>
    <div style="margin-top:10px">{'<span class="chip ok">Select Deals разблокирован</span>' if ks_ok else '<span class="chip bad">ниже 70 — badge заблокирован</span>'}</div>
  </div>
</div>

<div class="card" style="margin-top:16px">
  <h2>Штук/мес по месяцам (цель — красный пунктир на 50)</h2>
  <div class="chart">
    <div class="tline" style="bottom:{target_line_bottom}px"><span>цель {target}</span></div>
    {bars}
  </div>
  <div class="legend"><span><i style="background:var(--bol)"></i>Bol</span><span><i style="background:var(--amz)"></i>Amazon</span><span><i style="background:#d0402c"></i>цель {target}/мес</span></div>
</div>

<div class="card" style="margin-top:16px">
  <h2>Отзывы 4–5★ по площадкам (рычаг конверсии)</h2>
  <div class="revs">{reviews_html}</div>
</div>

<div class="card" style="margin-top:16px">
  <h2>Диагностика (не цель — контроль рычагов)</h2>
  <div class="diag">
    <div>ACoS сейчас: <b>{acos.get('note','—')}</b> · цель BE ≤{acos.get('goal_be','')}% / NL ≤{acos.get('goal_nl','')}%</div>
    <div>База: <b>{baseline} шт</b> (июнь) → цель <b>{target} шт</b></div>
    <div>Дней до дедлайна: <b>{days_left}</b></div>
  </div>
</div>

<div class="foot">Штук/мес — автоматически из daily-пайплайна (update_dashboard.py). Отзывы и Kwaliteitsscore — sprint_manual.json (обновлять по понедельникам). Пересборка: <code>python build_sprint_dashboard.py</code></div>
</div></body></html>'''

    open(OUT_HTML, "w", encoding="utf-8").write(html)
    print(f"✅ Готово: {OUT_HTML}")
    print(f"   Текущий месяц {cur_ym}: {cur_units} шт (Bol {cur_bol}+Amazon {cur_amz}), проекция ≈{projection}, цель {target}")
    print(f"   Месяцев в графике: {len(series)}; Kwaliteitsscore {ks_val}/{ks_goal}")


if __name__ == "__main__":
    main()
