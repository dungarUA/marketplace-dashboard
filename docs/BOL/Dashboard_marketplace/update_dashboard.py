"""
update_dashboard.py — автообновление marketplace_dashboard.html
Запуск: python update_dashboard.py
Настройка: отредактируйте CLIENT_ID и CLIENT_SECRET ниже.
Планировщик Windows: Task Scheduler → запускать ежедневно в 08:00
"""

import requests, json, re, os, subprocess
from datetime import date, timedelta, datetime
from collections import defaultdict

# ── Настройки ────────────────────────────────────────────────
CLIENT_ID     = "80b0332e-bfd7-47a7-ab0d-4dc0237fa946"
CLIENT_SECRET = "W!BsCAKSmYzZ7QdEgEuQImBVvz6rB!Ey6sn3GDjjadcMVjRHy7Uc1B(6VbUzIfO9"   # ← замените после смены в кабинете bol.com

DASHBOARD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketplace_dashboard.html")

# ── GitHub Pages (оставьте True чтобы автоматически публиковать) ──
GITHUB_AUTOPUSH = True   # False = только обновить файл локально, без публикации
VAT_RATE = 1.21   # Бельгия, 21%

# Диапазон дат в дашборде: с какой даты начинаем
DATA_START = date(2025, 11, 2)

# ── API ──────────────────────────────────────────────────────
def get_token():
    r = requests.post(
        "https://login.bol.com/token",
        params={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        timeout=15
    )
    r.raise_for_status()
    print("✅ Токен получен")
    return r.json()["access_token"]

def api_get(token, url, params=None):
    r = requests.get(url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.retailer.v10+json"},
        params=params, timeout=15)
    if r.status_code == 200:
        return r.json()
    print(f"  ⚠️  {url.split('bol.com')[-1]} → {r.status_code}")
    return None

def fetch_shipments(token):
    """Все отгрузки (paginated) — основной источник выручки по дням"""
    all_ships = []
    page = 1
    while page <= 50:
        data = api_get(token, "https://api.bol.com/retailer/shipments", {"page": page})
        if not data:
            break
        ships = data.get("shipments", [])
        if not ships:
            break
        all_ships.extend(ships)
        page += 1
    print(f"✅ Отгрузок: {len(all_ships)}")
    return all_ships

def fetch_order_details(token, order_ids):
    """Получить unitPrice из деталей заказов"""
    details = {}
    for oid in order_ids:
        d = api_get(token, f"https://api.bol.com/retailer/orders/{oid}")
        if d:
            items = d.get("orderItems", [])
            for item in items:
                qty = item.get("quantity", 1)
                price = item.get("unitPrice", 0)
                details[item.get("orderItemId")] = price * qty
    print(f"✅ Деталей заказов: {len(details)}")
    return details

# ── Построение дневных рядов ──────────────────────────────────
def build_daily_bol(shipments, order_details):
    """
    Строим daily dict: date_str → {rev, ord}
    Цена = unitPrice из деталей заказа (incl. VAT 21%).
    Если деталей нет — оцениваем по кол-ву единиц × 27.99 (fallback).
    """
    FALLBACK_PRICE = 27.99
    daily = defaultdict(lambda: {"rev": 0.0, "ord": 0})

    for ship in shipments:
        # Дата отгрузки
        shipped_at = ship.get("shipmentDate") or ship.get("shipmentDateTime", "")
        if not shipped_at:
            continue
        day = shipped_at[:10]   # "2026-06-15"

        items = ship.get("shipmentItems", [])
        for item in items:
            qty = item.get("quantity", 1)
            oid_item = item.get("orderItemId")
            if oid_item and oid_item in order_details:
                rev = order_details[oid_item]
            else:
                rev = FALLBACK_PRICE * qty
            daily[day]["rev"] += round(rev, 2)
            daily[day]["ord"] += qty

    return daily

def build_arrays(daily_bol):
    """Строим DATES / BOL_REV / BOL_ORD от DATA_START до сегодня"""
    today = date.today()
    dates, revs, ords = [], [], []
    d = DATA_START
    while d <= today:
        s = d.isoformat()
        dates.append(s)
        entry = daily_bol.get(s, {"rev": 0.0, "ord": 0})
        revs.append(round(entry["rev"], 2))
        ords.append(entry["ord"])
        d += timedelta(days=1)
    return dates, revs, ords

def build_monthly(dates, revs, ords, amz_rev_orig, amz_ord_orig, amz_dates_orig):
    """
    Строим MONTHLY. AMZ данные пока берём из текущего HTML (статика).
    BOL — из свежего API.
    """
    monthly = defaultdict(lambda: {"bol_rev": 0.0, "bol_ord": 0, "amz_rev": 0.0, "amz_ord": 0})
    for i, d in enumerate(dates):
        key = d[:7]   # "2026-06"
        monthly[key]["bol_rev"] = round(monthly[key]["bol_rev"] + revs[i], 2)
        monthly[key]["bol_ord"] += ords[i]

    # Добавляем AMZ из старых данных (они не меняются автоматически)
    for i, d in enumerate(amz_dates_orig):
        key = d[:7]
        monthly[key]["amz_rev"] = round(monthly[key]["amz_rev"] + amz_rev_orig[i], 2)
        monthly[key]["amz_ord"] += amz_ord_orig[i]

    return dict(sorted(monthly.items()))

# ── Чтение текущего HTML ──────────────────────────────────────
def read_html():
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        return f.read()

def extract_array(html, name):
    m = re.search(rf'const {name}=\[([^\]]+)\]', html)
    if not m:
        return []
    return [float(x) for x in m.group(1).split(",")]

def extract_str_array(html, name):
    m = re.search(rf'const {name}=\[([^\]]+)\]', html)
    if not m:
        return []
    return [x.strip().strip('"') for x in m.group(1).split(",")]

# ── Запись обновлённого HTML ──────────────────────────────────
def arr_js(vals):
    return ",".join(str(v) for v in vals)

def update_html(html, dates, bol_rev, bol_ord, monthly):
    # DATES
    dates_js = ",".join(f'"{d}"' for d in dates)
    html = re.sub(r'const DATES=\[[^\]]+\]', f'const DATES=[{dates_js}]', html)

    # BOL_REV
    html = re.sub(r'const BOL_REV=\[[^\]]+\]', f'const BOL_REV=[{arr_js(bol_rev)}]', html)

    # BOL_ORD
    html = re.sub(r'const BOL_ORD=\[[^\]]+\]', f'const BOL_ORD=[{arr_js(bol_ord)}]', html)

    # MONTHLY
    monthly_js = "{" + ",".join(
        f'"{k}"' + ":{bol_rev:" + str(round(v["bol_rev"],2)) +
        ",bol_ord:" + str(v["bol_ord"]) +
        ",amz_rev:" + str(round(v["amz_rev"],2)) +
        ",amz_ord:" + str(v["amz_ord"]) + "}"
        for k, v in monthly.items()
    ) + "}"
    html = re.sub(r'const MONTHLY=\{[^;]+\}', f'const MONTHLY={monthly_js}', html)

    # Метка времени
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    html = re.sub(
        r'(document\.getElementById\(\'upd-time\'\)\.textContent=).*?;',
        rf'\1"{ts} (авто)";',
        html
    )
    # Дата "today" в getPeriodRange
    today_str = date.today().isoformat()
    html = re.sub(r"const today='[0-9-]+'", f"const today='{today_str}'", html)
    # dt-to default (end date)
    html = re.sub(
        r'(id="dt-to" value=")[^"]+(")',
        rf'\g<1>{today_str}\g<2>',
        html
    )

    return html

# ── MAIN ─────────────────────────────────────────────────────
def main():
    print("=" * 52)
    print(f"Обновление дашборда — {datetime.now():%d.%m.%Y %H:%M}")
    print("=" * 52)

    # Читаем текущий HTML (для AMZ-данных, которые не меняются автоматически)
    html = read_html()
    amz_rev_orig  = extract_array(html, "AMZ_REV")
    amz_ord_orig  = [int(x) for x in extract_array(html, "AMZ_ORD")]
    dates_orig    = extract_str_array(html, "DATES")

    # Если AMZ длиннее/короче — используем dates_orig для AMZ
    amz_dates = dates_orig[:len(amz_rev_orig)]

    try:
        token = get_token()
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        print("Дашборд НЕ обновлён.")
        return

    print("\n🚚 Отгрузки...")
    shipments = fetch_shipments(token)

    # Собираем order IDs для получения цен
    order_ids = list({
        s.get("order", {}).get("orderId")
        for s in shipments
        if s.get("order", {}).get("orderId")
    })
    print(f"  Уникальных заказов: {len(order_ids)}")

    print("\n💰 Цены (детали заказов)...")
    order_details = fetch_order_details(token, order_ids[:50])

    print("\n📊 Строим дневные ряды...")
    daily_bol = build_daily_bol(shipments, order_details)
    dates, bol_rev, bol_ord = build_arrays(daily_bol)

    print(f"  Дат: {len(dates)} ({dates[0]} → {dates[-1]})")
    print(f"  BOL выручка итого: €{sum(bol_rev):.2f}")
    print(f"  BOL заказов итого: {sum(bol_ord)}")

    print("\n📅 Месячные агрегаты...")
    monthly = build_monthly(dates, bol_rev, bol_ord, amz_rev_orig, amz_ord_orig, amz_dates)
    for k, v in list(monthly.items())[-3:]:
        print(f"  {k}: BOL €{v['bol_rev']:.2f} ({v['bol_ord']} ord) | AMZ €{v['amz_rev']:.2f} ({v['amz_ord']} ord)")

    print("\n✏️  Обновляем HTML...")
    html_new = update_html(html, dates, bol_rev, bol_ord, monthly)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_new)

    print(f"\n✅ Готово! Дашборд обновлён: {DASHBOARD_PATH}")
    print(f"   Последняя дата: {dates[-1]}")

    if GITHUB_AUTOPUSH:
        git_push(dates[-1])

def git_push(last_date):
    """Коммит и пуш на GitHub → страница обновится автоматически"""
    repo_dir = os.path.dirname(DASHBOARD_PATH)
    print("\n🚀 Публикуем на GitHub Pages...")

    def run(cmd):
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    try:
        run(["git", "add", "marketplace_dashboard.html"])
        # Проверяем есть ли изменения
        status = run(["git", "status", "--porcelain"])
        if not status:
            print("  Изменений нет — пуш не нужен.")
            return
        run(["git", "commit", "-m", f"dashboard: обновление {last_date}"])
        run(["git", "push"])
        print(f"  ✅ Опубликовано! Страница обновится через ~1 минуту.")
    except RuntimeError as e:
        print(f"  ❌ Ошибка git: {e}")
        print("  Дашборд обновлён локально, но не опубликован.")
        print("  Проверьте: git настроен? Есть доступ в интернет?")

if __name__ == "__main__":
    main()
