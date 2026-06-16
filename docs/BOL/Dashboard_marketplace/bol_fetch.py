"""
bol.com Retailer API — выгрузка данных для дашборда
Запуск: python bol_fetch.py
Требования: pip install requests
"""

import requests, json
from datetime import datetime

CLIENT_ID     = "37e84817-0897-47fa-9a52-4cf0d629ff34"
CLIENT_SECRET = "9V2VYFR2MT)R61fh2y8Nix?4TR6JnRyW1@vs4TtRBDTUAMeLQoNQsyOLPzQrKIzx"

# Абсолютный путь — файл всегда рядом со скриптом
import os
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bol_data.json")

# ============================================================
def get_token():
    resp = requests.post(
        "https://login.bol.com/token",
        params={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        timeout=15
    )
    resp.raise_for_status()
    print("✅ Токен получен")
    return resp.json()["access_token"]

def h(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.retailer.v10+json"
    }

def get(token, url, params=None):
    r = requests.get(url, headers=h(token), params=params, timeout=15)
    print(f"  GET {url.split('bol.com')[-1]} → {r.status_code}")
    if r.status_code == 200:
        return r.json()
    print(f"     {r.text[:120]}")
    return None

# ============================================================
# ORDERS — все статусы
# ============================================================
def fetch_all_orders(token):
    base = "https://api.bol.com/retailer/orders"
    all_orders = []
    for status in ["OPEN", "SHIPPED", "ALL"]:
        page = 1
        while True:
            data = get(token, base, {"page": page, "status": status})
            if not data:
                break
            orders = data.get("orders", [])
            if not orders:
                break
            # избегаем дублей
            existing_ids = {o.get("orderId") for o in all_orders}
            new = [o for o in orders if o.get("orderId") not in existing_ids]
            all_orders.extend(new)
            print(f"     статус={status} стр={page}: +{len(new)} заказов")
            page += 1
            if page > 20:
                break
    print(f"✅ Заказов итого: {len(all_orders)}")
    return all_orders

# ============================================================
# SHIPMENTS — отгрузки (хороший источник исторических данных)
# ============================================================
def fetch_shipments(token):
    base = "https://api.bol.com/retailer/shipments"
    all_ships = []
    page = 1
    while True:
        data = get(token, base, {"page": page})
        if not data:
            break
        ships = data.get("shipments", [])
        if not ships:
            break
        all_ships.extend(ships)
        page += 1
        if page > 50:
            break
    print(f"✅ Отгрузок: {len(all_ships)}")
    return all_ships

# ============================================================
# SETTLEMENTS — выплаты с комиссиями
# ============================================================
def fetch_settlements(token):
    data = get(token, "https://api.bol.com/retailer/settlements")
    if not data:
        return []
    settlements = data.get("settlements", [])
    print(f"✅ Периодов выплат: {len(settlements)}")

    all_tx = []
    for s in settlements[:6]:  # последние 6 периодов
        sid = s.get("settlementId")
        if not sid:
            continue
        page = 1
        while True:
            d = get(token, f"https://api.bol.com/retailer/settlements/{sid}", {"page": page})
            if not d:
                break
            tx = d.get("transactions", [])
            if not tx:
                break
            all_tx.extend(tx)
            page += 1
            if page > 10:
                break
        print(f"  Settlement {sid}: {len(all_tx)} транзакций")

    return settlements, all_tx

# ============================================================
# RETURNS
# ============================================================
def fetch_returns(token):
    all_ret = []
    for handled in ["false", "true"]:
        data = get(token, "https://api.bol.com/retailer/returns", {"page": 1, "handled": handled})
        if data:
            all_ret.extend(data.get("returns", []))
    print(f"✅ Возвратов: {len(all_ret)}")
    return all_ret

# ============================================================
# INVENTORY
# ============================================================
def fetch_inventory(token):
    all_items = []
    page = 1
    while True:
        data = get(token, "https://api.bol.com/retailer/inventory", {"page": page})
        if not data:
            break
        items = data.get("items", [])
        if not items:
            break
        all_items.extend(items)
        page += 1
        if page > 10:
            break
    print(f"✅ Товаров: {len(all_items)}")
    return all_items

# ============================================================
# ORDER DETAILS — цены и комиссии по конкретным заказам
# ============================================================
def fetch_order_details(token, shipments):
    """GET /retailer/orders/{orderId} возвращает unitPrice и commissionAmount"""
    seen = set()
    order_ids = []
    for s in shipments:
        oid = s.get("order", {}).get("orderId")
        if oid and oid not in seen:
            seen.add(oid)
            order_ids.append(oid)

    print(f"  Уникальных заказов из отгрузок: {len(order_ids)}")
    details = []
    for oid in order_ids[:30]:  # максимум 30 запросов
        d = get(token, f"https://api.bol.com/retailer/orders/{oid}")
        if d:
            details.append(d)
    print(f"✅ Деталей заказов: {len(details)}")
    return details

# ============================================================
# FINANCE TRANSACTIONS — альтернатива settlements
# ============================================================
def fetch_finance_transactions(token):
    """Попытка получить транзакции через finance endpoint"""
    data = get(token, "https://api.bol.com/retailer/finance/transactions",
               {"year": 2026, "month": 6})
    if not data:
        return []
    tx = data.get("transactions", [])
    print(f"✅ Финансовых транзакций: {len(tx)}")
    return tx

# ============================================================
# OFFER / PRICING — активные предложения
# ============================================================
def fetch_offers(token):
    all_offers = []
    page = 1
    while True:
        data = get(token, "https://api.bol.com/retailer/offers/export",
                   {"format": "CSV"})
        # offers/export требует другого подхода — пробуем список
        break
    # Альтернатива: GET /retailer/offers (список офферов)
    data = get(token, "https://api.bol.com/retailer/offers")
    if data:
        all_offers = data.get("offers", [])
    print(f"✅ Офферов: {len(all_offers)}")
    return all_offers

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 52)
    print("bol.com API — выгрузка данных")
    print(f"Файл: {OUTPUT_FILE}")
    print("=" * 52)

    try:
        token = get_token()
    except Exception as e:
        print(f"❌ Ошибка авторизации: {e}")
        return

    result = {
        "fetched_at":    datetime.now().isoformat(),
        "orders":        [],
        "shipments":     [],
        "order_details": [],   # цены и комиссии из /orders/{id}
        "settlements":   [],
        "transactions":  [],
        "finance_tx":    [],   # альтернативный финансовый endpoint
        "returns":       [],
        "inventory":     [],
        "offers":        [],
    }

    print("\n📦 Заказы...")
    try:
        result["orders"] = fetch_all_orders(token)
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n🚚 Отгрузки...")
    try:
        result["shipments"] = fetch_shipments(token)
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n💰 Цены и комиссии из деталей заказов...")
    try:
        result["order_details"] = fetch_order_details(token, result["shipments"])
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n💶 Выплаты / settlements...")
    try:
        settlements, tx = fetch_settlements(token)
        result["settlements"] = settlements
        result["transactions"] = tx
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n📒 Finance transactions (альтернатива)...")
    try:
        result["finance_tx"] = fetch_finance_transactions(token)
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n↩️  Возвраты...")
    try:
        result["returns"] = fetch_returns(token)
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n📊 Инвентарь...")
    try:
        result["inventory"] = fetch_inventory(token)
    except Exception as e:
        print(f"  ❌ {e}")

    print("\n🏷  Товары / офферы...")
    try:
        result["offers"] = fetch_offers(token)
    except Exception as e:
        print(f"  ❌ {e}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*52}")
    print(f"✅ Сохранено: {OUTPUT_FILE}")
    print(f"   Заказов:         {len(result['orders'])}")
    print(f"   Отгрузок:        {len(result['shipments'])}")
    print(f"   Деталей заказов: {len(result['order_details'])}")
    print(f"   Транзакций:      {len(result['transactions'])}")
    print(f"   Finance TX:      {len(result['finance_tx'])}")
    print(f"   Возвратов:       {len(result['returns'])}")

    # Краткая сводка по ценам из деталей заказов
    if result["order_details"]:
        total_rev = 0
        total_com = 0
        for od in result["order_details"]:
            for item in od.get("orderItems", []):
                qty = item.get("quantity", 1)
                total_rev += item.get("unitPrice", 0) * qty
                total_com += item.get("commission", 0) * qty   # правильное поле
        net = total_rev - total_com
        vat_rate = 0.21
        rev_ex_vat = total_rev / (1 + vat_rate)
        net_ex_vat = net / (1 + vat_rate)
        print(f"\n   💶 Выручка брутто (incl. 21% НДС):  €{total_rev:.2f}")
        print(f"   📉 Комиссии bol.com:                  €{total_com:.2f}  ({total_com/total_rev*100:.1f}%)")
        print(f"   ✅ После комиссии (incl. НДС):        €{net:.2f}")
        print(f"   📋 Выручка без НДС (excl. VAT):       €{rev_ex_vat:.2f}")
        print(f"   💰 Чистая без НДС (excl. VAT):        €{net_ex_vat:.2f}")

if __name__ == "__main__":
    main()
