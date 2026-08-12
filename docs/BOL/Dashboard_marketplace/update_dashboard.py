"""
update_dashboard.py — автообновление marketplace_dashboard.html
Запуск: python update_dashboard.py
Планировщик Windows: Task Scheduler → запускать ежедневно в 08:00
"""

import requests, json, re, os, subprocess
from datetime import date, timedelta, datetime, timezone
from collections import defaultdict

# ── Credentials (читаются из amazon_credentials.json, не хранятся в git) ─────
def _load_creds():
    creds_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amazon_credentials.json")
    if not os.path.exists(creds_path):
        raise FileNotFoundError(
            f"Файл с credentials не найден: {creds_path}\n"
            "Создайте его по образцу amazon_credentials.json.example"
        )
    with open(creds_path, encoding="utf-8") as f:
        return json.load(f)

_creds            = _load_creds()
CLIENT_ID         = _creds["bol_client_id"]
CLIENT_SECRET     = _creds["bol_client_secret"]
AMZ_CLIENT_ID     = _creds["amz_client_id"]
AMZ_CLIENT_SECRET = _creds["amz_client_secret"]
AMZ_REFRESH_TOKEN = _creds["amz_refresh_token"]
AMZ_MARKETPLACE   = "AMEN7PMS3EDWL"          # Amazon.be (Belgium)
AMZ_ENDPOINT      = "https://sellingpartnerapi-eu.amazon.com"
AMZ_TOKEN_URL     = "https://api.amazon.com/auth/o2/token"

DASHBOARD_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "marketplace_dashboard.html")
BOL_CACHE_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bol_cache.json")
GITHUB_AUTOPUSH = True
VAT_RATE        = 1.21      # Бельгия, 21%
DATA_START      = date(2025, 11, 2)


# ════════════════════════════════════════════════════════════════════
#  bol.com кэш (защита от скользящего окна API)
# ════════════════════════════════════════════════════════════════════

def load_bol_cache():
    """Загружает сохранённые исторические данные bol.com."""
    if os.path.exists(BOL_CACHE_PATH):
        try:
            with open(BOL_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Конвертируем в нужный формат {date: {"rev": float, "ord": int}}
            cache = {k: {"rev": float(v["rev"]), "ord": int(v["ord"])} for k, v in data.items()}
            print(f"  📦 bol.com кэш: {len(cache)} дат загружено")
            return cache
        except Exception as e:
            print(f"  ⚠️  bol.com кэш повреждён, игнорируем: {e}")
    return {}

def save_bol_cache(daily_bol):
    """Сохраняет объединённые данные bol.com в кэш."""
    try:
        with open(BOL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(daily_bol, f, ensure_ascii=False, indent=2)
        nonzero = sum(1 for v in daily_bol.values() if v["rev"] > 0)
        print(f"  💾 bol.com кэш сохранён: {len(daily_bol)} дат, {nonzero} с продажами")
    except Exception as e:
        print(f"  ⚠️  Не удалось сохранить bol.com кэш: {e}")


# ════════════════════════════════════════════════════════════════════
#  bol.com
# ════════════════════════════════════════════════════════════════════

def get_token():
    r = requests.post(
        "https://login.bol.com/token",
        params={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        timeout=15
    )
    r.raise_for_status()
    print("✅ bol.com токен получен")
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
    print(f"✅ bol.com отгрузок: {len(all_ships)}")
    return all_ships

def fetch_order_details(token, order_ids):
    details = {}
    for oid in order_ids:
        d = api_get(token, f"https://api.bol.com/retailer/orders/{oid}")
        if d:
            for item in d.get("orderItems", []):
                qty   = item.get("quantity", 1)
                price = item.get("unitPrice", 0)
                details[item.get("orderItemId")] = price * qty
    print(f"✅ bol.com деталей заказов: {len(details)}")
    return details

def build_daily_bol(shipments, order_details):
    FALLBACK = 27.99
    daily = defaultdict(lambda: {"rev": 0.0, "ord": 0})
    for ship in shipments:
        day = (ship.get("shipmentDate") or ship.get("shipmentDateTime", ""))[:10]
        if not day:
            continue
        for item in ship.get("shipmentItems", []):
            qty  = item.get("quantity", 1)
            iid  = item.get("orderItemId")
            rev  = order_details.get(iid, FALLBACK * qty) if iid else FALLBACK * qty
            daily[day]["rev"] += round(rev, 2)
            daily[day]["ord"] += qty
    return daily


# ════════════════════════════════════════════════════════════════════
#  Amazon SP-API
# ════════════════════════════════════════════════════════════════════

def get_amz_access_token():
    r = requests.post(AMZ_TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": AMZ_REFRESH_TOKEN,
        "client_id":     AMZ_CLIENT_ID,
        "client_secret": AMZ_CLIENT_SECRET,
    }, timeout=15)
    r.raise_for_status()
    print("✅ Amazon access token получен")
    return r.json()["access_token"]

def fetch_amazon_orders(access_token):
    headers = {"x-amz-access-token": access_token, "Content-Type": "application/json"}
    params  = {
        "MarketplaceIds":    AMZ_MARKETPLACE,
        "CreatedAfter":      DATA_START.strftime("%Y-%m-%dT00:00:00Z"),
        "MaxResultsPerPage": 100,
    }
    all_orders = []
    url = f"{AMZ_ENDPOINT}/orders/v0/orders"

    while url:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            print(f"  ⚠️  Amazon Orders API → {r.status_code}: {r.text[:200]}")
            break
        payload    = r.json().get("payload", {})
        all_orders.extend(payload.get("Orders", []))
        next_token = payload.get("NextToken")
        if next_token:
            url    = f"{AMZ_ENDPOINT}/orders/v0/orders"
            params = {"MarketplaceIds": AMZ_MARKETPLACE, "NextToken": next_token}
        else:
            url = None

    print(f"✅ Amazon заказов: {len(all_orders)}")
    return all_orders

def build_daily_amz(orders):
    daily = defaultdict(lambda: {"rev": 0.0, "ord": 0})
    for o in orders:
        if o.get("OrderStatus") == "Canceled":
            continue
        day = o.get("PurchaseDate", "")[:10]
        if not day:
            continue
        amount = float(o.get("OrderTotal", {}).get("Amount", 0))
        if amount > 0:
            daily[day]["rev"] += amount
            daily[day]["ord"] += 1
    return daily


def fetch_amazon_finance(access_token):
    """Finance API: комиссии (ReferralFee) и затраты на рекламу"""
    headers     = {"x-amz-access-token": access_token}
    all_ship    = []
    all_ads     = []
    today       = date.today()
    chunk_start = DATA_START

    while chunk_start <= today:
        chunk_end = min(chunk_start + timedelta(days=179), today)
        # PostedBefore не должен быть в будущем — Amazon принимает только прошедшие моменты
        if chunk_end >= today:
            # берём текущий UTC минус 5 минут
            now_utc = datetime.now(timezone.utc) - timedelta(minutes=5)
            posted_before = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            posted_before = chunk_end.strftime("%Y-%m-%dT23:59:59Z")
        params    = {
            "PostedAfter":  chunk_start.strftime("%Y-%m-%dT00:00:00Z"),
            "PostedBefore": posted_before,
        }
        url = f"{AMZ_ENDPOINT}/finances/v0/financialEvents"
        while url:
            r = requests.get(url, headers=headers, params=params, timeout=30)
            if not r.ok:
                print(f"  ⚠️  Finance API → {r.status_code}: {r.text[:200]}")
                break
            payload = r.json().get("payload", {})
            events  = payload.get("FinancialEvents", {})
            all_ship.extend(events.get("ShipmentEventList", []))
            all_ads.extend(events.get("AdvertisingTransactionEventList", []))
            next_token = payload.get("NextToken")
            params = {"NextToken": next_token} if next_token else {}
            url    = f"{AMZ_ENDPOINT}/finances/v0/financialEvents" if next_token else None
        chunk_start = chunk_end + timedelta(days=1)

    print(f"✅ Amazon Finance: {len(all_ship)} событий продаж, {len(all_ads)} рекламных")
    return all_ship, all_ads


def build_daily_amz_finance(shipment_events, ad_events):
    """Комиссии и реклама Amazon по дням.

    FeeType на Amazon.be (европейский маркетплейс):
      Commission        — основная комиссия (~15-20% от цены)
      FixedClosingFee   — фиксированный сбор
      VariableClosingFee — переменный сбор
      GiftwrapCommission — упаковка в подарок (обычно 0)
      ShippingHB        — удержание за доставку (проходящее)
      DigitalServicesFee — налог DST (с покупателя, НЕ комиссия продавца → исключаем)
    """
    daily_fees = defaultdict(float)
    daily_ads  = defaultdict(float)

    # DigitalServicesFee — налог с покупателя, не затраты продавца
    EXCLUDE_TYPES = {"DigitalServicesFee"}

    for ev in shipment_events:
        day = ev.get("PostedDate", "")[:10]
        if not day:
            continue
        for item in ev.get("ShipmentItemList", []):
            for fee in item.get("ItemFeeList", []):
                if fee.get("FeeType") in EXCLUDE_TYPES:
                    continue
                amt = fee.get("FeeAmount", {}).get("CurrencyAmount", 0)
                daily_fees[day] += abs(float(amt or 0))

    for ev in ad_events:
        day = ev.get("PostedDate", "")[:10]
        if not day:
            continue
        amt = (ev.get("BaseValue") or ev.get("TransactionValue") or {}).get("CurrencyAmount", 0)
        daily_ads[day] += abs(float(amt or 0))

    return daily_fees, daily_ads


# ════════════════════════════════════════════════════════════════════
#  Сборка массивов для дашборда
# ════════════════════════════════════════════════════════════════════

def build_arrays(daily_bol, daily_amz, daily_fees=None, daily_ads=None):
    today = date.today()
    dates, bol_rev, bol_ord, amz_rev, amz_ord, amz_fees, amz_ads = [], [], [], [], [], [], []
    daily_fees = daily_fees or {}
    daily_ads  = daily_ads  or {}
    d = DATA_START
    while d <= today:
        s = d.isoformat()
        dates.append(s)
        b = daily_bol.get(s, {"rev": 0.0, "ord": 0})
        a = daily_amz.get(s, {"rev": 0.0, "ord": 0})
        bol_rev.append(round(b["rev"], 2))
        bol_ord.append(b["ord"])
        amz_rev.append(round(a["rev"], 2))
        amz_ord.append(a["ord"])
        amz_fees.append(round(daily_fees.get(s, 0.0), 2))
        amz_ads.append(round(daily_ads.get(s, 0.0), 2))
        d += timedelta(days=1)
    return dates, bol_rev, bol_ord, amz_rev, amz_ord, amz_fees, amz_ads

def build_monthly(dates, bol_rev, bol_ord, amz_rev, amz_ord, amz_fees=None, amz_ads=None):
    monthly = defaultdict(lambda: {
        "bol_rev": 0.0, "bol_ord": 0,
        "amz_rev": 0.0, "amz_ord": 0,
        "amz_fees": 0.0, "amz_ads": 0.0
    })
    amz_fees = amz_fees or [0.0] * len(dates)
    amz_ads  = amz_ads  or [0.0] * len(dates)
    for i, d in enumerate(dates):
        key = d[:7]
        monthly[key]["bol_rev"]  = round(monthly[key]["bol_rev"]  + bol_rev[i],  2)
        monthly[key]["bol_ord"]  += bol_ord[i]
        monthly[key]["amz_rev"]  = round(monthly[key]["amz_rev"]  + amz_rev[i],  2)
        monthly[key]["amz_ord"]  += amz_ord[i]
        monthly[key]["amz_fees"] = round(monthly[key]["amz_fees"] + amz_fees[i], 2)
        monthly[key]["amz_ads"]  = round(monthly[key]["amz_ads"]  + amz_ads[i],  2)
    return dict(sorted(monthly.items()))


# ════════════════════════════════════════════════════════════════════
#  Чтение / запись HTML
# ════════════════════════════════════════════════════════════════════

def read_html():
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        return f.read()

def arr_js(vals):
    return ",".join(str(v) for v in vals)

def update_html(html, dates, bol_rev, bol_ord, amz_rev, amz_ord, monthly,
                amz_fees=None, amz_ads=None):
    amz_fees = amz_fees or [0.0] * len(dates)
    amz_ads  = amz_ads  or [0.0] * len(dates)

    dates_js = ",".join(f'"{d}"' for d in dates)
    html = re.sub(r'const DATES=\[[^\]]+\]',     f'const DATES=[{dates_js}]',            html)
    html = re.sub(r'const BOL_REV=\[[^\]]+\]',   f'const BOL_REV=[{arr_js(bol_rev)}]',   html)
    html = re.sub(r'const BOL_ORD=\[[^\]]+\]',   f'const BOL_ORD=[{arr_js(bol_ord)}]',   html)
    html = re.sub(r'const AMZ_REV=\[[^\]]+\]',   f'const AMZ_REV=[{arr_js(amz_rev)}]',   html)
    html = re.sub(r'const AMZ_ORD=\[[^\]]+\]',   f'const AMZ_ORD=[{arr_js(amz_ord)}]',   html)
    html = re.sub(r'const AMZ_FEES=\[[^\]]*\]',  f'const AMZ_FEES=[{arr_js(amz_fees)}]', html)
    html = re.sub(r'const AMZ_ADS=\[[^\]]*\]',   f'const AMZ_ADS=[{arr_js(amz_ads)}]',   html)

    monthly_js = "{" + ",".join(
        f'"{k}"' + ":{bol_rev:" + str(round(v["bol_rev"], 2)) +
        ",bol_ord:" + str(v["bol_ord"]) +
        ",amz_rev:" + str(round(v["amz_rev"], 2)) +
        ",amz_ord:" + str(v["amz_ord"]) +
        ",amz_fees:" + str(round(v.get("amz_fees", 0.0), 2)) +
        ",amz_ads:" + str(round(v.get("amz_ads", 0.0), 2)) + "}"
        for k, v in monthly.items()
    ) + "}"
    html = re.sub(r'const MONTHLY=\{[^;]+\}', f'const MONTHLY={monthly_js}', html)

    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    html = re.sub(
        r'(document\.getElementById\(\'upd-time\'\)\.textContent=).*?;',
        rf'\1"{ts} (авто)";',
        html
    )
    today_str = date.today().isoformat()
    html = re.sub(r"const today='[0-9-]+'", f"const today='{today_str}'", html)
    html = re.sub(r'(id="dt-to" value=")[^"]+(")', rf'\g<1>{today_str}\g<2>', html)

    return html


# ════════════════════════════════════════════════════════════════════
#  Git push → GitHub Pages
# ════════════════════════════════════════════════════════════════════

def git_push(last_date):
    repo_dir = os.path.dirname(DASHBOARD_PATH)
    print("\n🚀 Публикуем на GitHub Pages...")

    def run(cmd):
        result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    try:
        run(["git", "add", "marketplace_dashboard.html",
             "Dashboard_Спринт_50.html", "sprint_manual.json",
             "build_sprint_dashboard.py"])
        status = run(["git", "status", "--porcelain"])
        if not status:
            print("  Изменений нет — пуш не нужен.")
            return
        run(["git", "commit", "-m", f"dashboard: обновление {last_date}"])
        run(["git", "push"])
        print("  ✅ Опубликовано! Страница обновится через ~1 минуту.")
    except RuntimeError as e:
        print(f"  ❌ Ошибка git: {e}")
        print("  Дашборд обновлён локально, но не опубликован.")


# ════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════

def main():
    print("=" * 52)
    print(f"Обновление дашборда — {datetime.now():%d.%m.%Y %H:%M}")
    print("=" * 52)

    # ── bol.com ──
    try:
        token = get_token()
    except Exception as e:
        print(f"❌ bol.com авторизация: {e}")
        return

    # Загружаем кэш до запроса к API
    print("\n🗄️  Загружаем bol.com кэш...")
    cached_bol = load_bol_cache()

    print("\n🚚 bol.com отгрузки...")
    shipments = fetch_shipments(token)
    order_ids = list({
        s.get("order", {}).get("orderId")
        for s in shipments if s.get("order", {}).get("orderId")
    })
    print(f"  Уникальных заказов: {len(order_ids)}")
    print("\n💰 bol.com цены...")
    order_details = fetch_order_details(token, order_ids[:50])
    daily_bol_fresh = build_daily_bol(shipments, order_details)

    # Мержим: кэш — база, свежие данные перезаписывают совпадающие даты
    # Так исторические месяцы не "теряются" при сужении окна API
    daily_bol = {**cached_bol, **daily_bol_fresh}
    new_days = len(set(daily_bol_fresh) - set(cached_bol))
    updated_days = len(set(daily_bol_fresh) & set(cached_bol))
    print(f"  📊 Кэш + API: новых дат {new_days}, обновлено {updated_days}")

    # Сохраняем обновлённый кэш
    print("\n🗄️  Сохраняем bol.com кэш...")
    save_bol_cache(daily_bol)

    # ── Amazon ──
    daily_amz  = {}
    daily_fees = {}
    daily_ads  = {}
    try:
        amz_token = get_amz_access_token()
        print("\n📦 Amazon заказы...")
        amz_orders = fetch_amazon_orders(amz_token)
        daily_amz  = build_daily_amz(amz_orders)

        print("\n💳 Amazon Finance (комиссии + реклама)...")
        ship_events, ad_events = fetch_amazon_finance(amz_token)
        daily_fees, daily_ads  = build_daily_amz_finance(ship_events, ad_events)
    except Exception as e:
        print(f"\u26a0\ufe0f  Amazon \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d: {e}")
        print("   \u041f\u0440\u043e\u0434\u043e\u043b\u0436\u0430\u0435\u043c \u0442\u043e\u043b\u044c\u043a\u043e \u0441 bol.com \u0434\u0430\u043d\u043d\u044b\u043c\u0438...")

    # \u2500\u2500 \u0421\u0431\u043e\u0440\u043a\u0430 \u2500\u2500
    print("\n\U0001f4ca \u0421\u0442\u0440\u043e\u0438\u043c \u043c\u0430\u0441\u0441\u0438\u0432\u044b...")
    dates, bol_rev, bol_ord, amz_rev, amz_ord, amz_fees, amz_ads = build_arrays(
        daily_bol, daily_amz, daily_fees, daily_ads
    )
    monthly = build_monthly(dates, bol_rev, bol_ord, amz_rev, amz_ord, amz_fees, amz_ads)

    print(f"  \u0414\u0430\u0442: {len(dates)} ({dates[0]} \u2192 {dates[-1]})")
    print(f"  BOL: \u20ac{sum(bol_rev):.2f} / {sum(bol_ord)} \u0437\u0430\u043a\u0430\u0437\u043e\u0432")
    print(f"  AMZ: \u20ac{sum(amz_rev):.2f} / {sum(amz_ord)} \u0437\u0430\u043a\u0430\u0437\u043e\u0432")
    print(f"  AMZ \u043a\u043e\u043c\u0438\u0441\u0441\u0438\u044f: \u20ac{sum(amz_fees):.2f} | \u0440\u0435\u043a\u043b\u0430\u043c\u0430: \u20ac{sum(amz_ads):.2f}")

    print("\n\U0001f4c5 \u041c\u0435\u0441\u044f\u0447\u043d\u044b\u0435 \u0430\u0433\u0440\u0435\u0433\u0430\u0442\u044b (\u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0435 3 \u043c\u0435\u0441\u044f\u0446\u0430):")
    for k, v in list(monthly.items())[-3:]:
        print(f"  {k}: BOL \u20ac{v['bol_rev']:.2f} ({v['bol_ord']}) | "
              f"AMZ \u20ac{v['amz_rev']:.2f} ({v['amz_ord']}) | "
              f"fees \u20ac{v['amz_fees']:.2f} | ads \u20ac{v['amz_ads']:.2f}")

    print("\n\u270f\ufe0f  \u041e\u0431\u043d\u043e\u0432\u043b\u044f\u0435\u043c HTML...")
    html = read_html()
    html_new = update_html(html, dates, bol_rev, bol_ord, amz_rev, amz_ord, monthly,
                           amz_fees, amz_ads)
    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html_new)
    print(f"\u2705 \u0414\u0430\u0448\u0431\u043e\u0440\u0434 \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u043e: {dates[-1]}")

    # ── Спринт-дашборд 50/мес (штуки берёт из этого же MONTHLY) ──
    try:
        import subprocess, sys, os
        _sd = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_sprint_dashboard.py')
        subprocess.run([sys.executable, _sd], check=False)
    except Exception as _e:
        print(f'⚠️  Спринт-дашборд не собран: {_e}')

    if GITHUB_AUTOPUSH:
        git_push(dates[-1])

    print("\n=== \u0413\u043e\u0442\u043e\u0432\u043e! ===")


if __name__ == "__main__":
    main()
