"""Интеграционные тесты API (FastAPI TestClient, отдельная БД на каждый тест)."""
from datetime import date, timedelta
from decimal import Decimal as Dc

from app.main import create_app
from app.seed.menu_data import CATEGORIES, DISHES
from tests.conftest import (PASSWORDS, auth, dish_ids, ingredient_ids, make_settings, place_order, stock_of)

from fastapi.testclient import TestClient


def D(x):
    return Dc(str(x))


# ---------------------------------------------------------------- запуск, БД, меню
def test_01_app_starts_and_swagger_available(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/api/version").json()["data"]["version"]


def test_02_database_created_automatically(settings, client):
    assert client.get("/api/categories").json()["meta"]["count"] == len(CATEGORIES)
    assert (settings.database_url.replace("sqlite:///", "")).endswith("test.db")


def test_03_all_categories_present(client):
    slugs = [c["slug"] for c in client.get("/api/categories").json()["data"]]
    assert slugs == [c[0] for c in CATEGORIES]
    hot = client.get("/api/menu", params={"category": "hot-dishes"}).json()
    assert hot["meta"]["count"] == 13


def test_04_all_declared_items_present(client):
    data = client.get("/api/menu").json()["data"]
    assert len(data) == len(DISHES)
    names = {d["name"] for d in data}
    assert {"Плов", "Борщ", "Айран", "Груша", "Конфеты — порция", "Халва — упаковка"} <= names
    assert all(d["currency"] == "KGS" for d in data)
    assert client.get("/api/menu", params={"available": "true"}).json()["meta"]["count"] == len(DISHES)
    plov = next(d for d in data if d["slug"] == "plov")
    assert client.get(f"/api/menu/{plov['id']}").json()["data"]["name"] == "Плов"


def test_05_recipes_are_correct_and_linked(client, admin):
    ids = dish_ids(client)
    recipe = client.get(f"/api/dishes/{ids['plov']}/recipe", headers=admin).json()["data"]
    by_name = {i["ingredient_name"]: i["quantity_per_portion"] for i in recipe["items"]}
    assert by_name["Рис"] == 100 and by_name["Говядина"] == 100 and by_name["Морковь"] == 60
    assert recipe["is_demo"] is True
    costing = client.get(f"/api/dishes/{ids['plov']}/costing", headers=admin).json()["data"]
    assert D(costing["ingredient_cost_per_portion"]) == Dc("66.95")
    assert D(costing["gross_difference_per_portion"]) == Dc("63.05")
    # готовый закупаемый товар: связь с одной позицией закупки, без выдуманной рецептуры
    candy = client.get(f"/api/dishes/{ids['candy-portion']}/recipe", headers=admin).json()["data"]
    assert len(candy["items"]) == 1 and candy["items"][0]["quantity_per_portion"] == 30


# ---------------------------------------------------------------- заказы
def test_06_order_with_several_items_and_money(client, tomorrow):
    r = place_order(client, {"plov": 3, "black-tea": 2, "ketchup": 1}, tomorrow)
    assert r.status_code == 201
    order = r.json()["data"]
    assert order["status"] == "confirmed" and len(order["items"]) == 3
    assert D(order["total_amount"]) == Dc("438.00")      # 3×130 + 2×20 + 8
    assert order["currency"] == "KGS"
    assert order["public_order_number"].startswith("SC-")


def test_07_order_keeps_price_snapshot(client, economist, admin, tomorrow):
    order = place_order(client, {"plov": 2}, tomorrow).json()["data"]
    pid = dish_ids(client)["plov"]
    assert client.patch(f"/api/dishes/{pid}", json={"sale_price": "200.00"}, headers=economist).status_code == 200
    again = client.get(f"/api/orders/{order['id']}", headers=admin).json()["data"]
    assert D(again["items"][0]["unit_sale_price"]) == Dc("130.00") and D(again["total_amount"]) == Dc("260.00")


def test_08_cancel_order_is_idempotent(client, cook, admin, tomorrow):
    oid = place_order(client, {"plov": 5}, tomorrow).json()["data"]["id"]
    first = client.patch(f"/api/orders/{oid}/cancel", headers=cook)
    second = client.patch(f"/api/orders/{oid}/cancel", headers=cook)
    assert first.json()["data"]["status"] == "cancelled" and first.json()["meta"]["changed"] is True
    assert second.status_code == 200 and second.json()["meta"]["changed"] is False
    summary = client.get("/api/orders/summary", params={"date": tomorrow}, headers=admin).json()["data"]
    assert summary["orders_by_status"]["cancelled"] == 1 and summary["total_portions"] == 0


def test_09_duplicate_order_protection(client, admin, tomorrow):
    r1 = place_order(client, {"plov": 2}, tomorrow, key="retry-key-0001")
    r2 = place_order(client, {"plov": 2}, tomorrow, key="retry-key-0001")
    assert r1.status_code == 201 and r2.status_code == 200
    assert r2.headers["Idempotent-Replay"] == "true"
    assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
    assert client.get("/api/orders", params={"date": tomorrow}, headers=admin).json()["meta"]["count"] == 1
    r3 = place_order(client, {"plov": 3}, tomorrow, key="retry-key-0001")
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "idempotency_key_reused"


def test_10_order_validation(client, tomorrow):
    ids = dish_ids(client)
    bad = client.post("/api/orders", json={"order_date": tomorrow, "items": [{"dish_id": ids["plov"], "quantity": -1}]})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"
    past = place_order(client, {"plov": 1}, (date.today() - timedelta(days=1)).isoformat())
    assert past.status_code == 422 and past.json()["error"]["code"] == "order_date_in_past"
    assert client.post("/api/orders", json={"order_date": tomorrow, "items": []}).status_code == 422
    assert client.post("/api/orders", json={"order_date": tomorrow, "items": [{"dish_id": 99999, "quantity": 1}]}).status_code == 422


def test_11_unavailable_dish_rejected_and_track_is_public(client, admin, economist, tomorrow):
    ids = dish_ids(client)
    client.patch(f"/api/dishes/{ids['lagman']}", json={"is_available": False}, headers=economist)
    r = place_order(client, {"lagman": 1}, tomorrow)
    assert r.status_code == 409 and r.json()["error"]["code"] == "dish_unavailable"
    body = {"customer_ref": "student-42", "order_date": tomorrow, "items": [{"dish_id": ids["plov"], "quantity": 1}]}
    number = client.post("/api/orders", json=body).json()["data"]["public_order_number"]
    tracked = client.get(f"/api/orders/track/{number}").json()["data"]
    assert tracked["public_order_number"] == number and "customer_ref" not in tracked


# ---------------------------------------------------------------- закупки
def _plov_120(client, tomorrow):
    for q in (50, 50, 20):
        assert place_order(client, {"plov": q}, tomorrow).status_code == 201


def test_12_procurement_for_120_portions(client, economist, tomorrow):
    _plov_120(client, tomorrow)
    r = client.post("/api/procurement-plan/preview", json={"date": tomorrow}, headers=economist)
    assert r.status_code == 200
    rep = r.json()["data"]
    assert rep["total_portions"] == 120 and rep["kind"] == "preview"
    items = {i["ingredient_name"]: i for i in rep["items"]}
    assert items["Рис"]["required_quantity"] == 12000 and items["Морковь"]["required_quantity"] == 7200
    beef = items["Говядина"]
    # нужно 12000 г, на складе (демо) 8000 г -> чистая потребность 4000 г -> 4 упаковки по 1 кг
    assert beef["available_quantity"] == 8000 and beef["net_need"] == 4000
    assert beef["package_count"] == 4 and beef["purchase_quantity"] == 4000
    assert D(beef["estimated_cost"]) == Dc("2080.00")            # 4000 г × 0.52
    assert "4 уп." in beef["explanation"]
    assert D(rep["total_estimated_cost"]) == Dc("2080.00") and rep["total_is_complete"] is True


def test_13_same_ingredient_summed_across_dishes_and_zero_purchase(client, economist, tomorrow):
    place_order(client, {"plov": 10, "chicken-rice": 20}, tomorrow)
    rep = client.post("/api/procurement-plan/preview", json={"date": tomorrow}, headers=economist).json()["data"]
    rice = next(i for i in rep["items"] if i["ingredient_name"] == "Рис")
    assert rice["required_quantity"] == 2800 and {b["dish_name"] for b in rice["breakdown"]} == {"Плов", "Курица с рисом"}
    assert all(i["status"] == "sufficient_stock" and i["purchase_quantity"] == 0 for i in rep["items"])
    assert D(rep["total_estimated_cost"]) == Dc("0.00")


def test_14_preview_does_not_change_stock_or_orders(client, economist, admin, tomorrow):
    _plov_120(client, tomorrow)
    before = stock_of(client, admin, "beef")
    for _ in range(3):
        client.post("/api/procurement-plan/preview", json={"date": tomorrow}, headers=economist)
    assert stock_of(client, admin, "beef") == before
    assert client.get("/api/inventory/movements", params={"movement_type": "purchase"}, headers=admin).json()["meta"]["count"] == 0
    assert client.get("/api/procurement-plan", params={"date": tomorrow}, headers=economist).json()["meta"]["count"] == 0


def test_15_missing_price_is_flagged_and_blocks_approval(client, economist, tomorrow):
    _plov_120(client, tomorrow)
    ids = ingredient_ids(client, economist)
    r = client.patch(f"/api/ingredients/{ids['beef']}", json={"purchase_price": None, "price_unit": None}, headers=economist)
    assert r.status_code == 200 and r.json()["data"]["price_per_base_unit"] is None
    rep = client.post("/api/procurement-plan/preview", json={"date": tomorrow}, headers=economist).json()["data"]
    beef = next(i for i in rep["items"] if i["ingredient_name"] == "Говядина")
    assert beef["status"] == "missing_price" and beef["estimated_cost"] is None
    assert rep["total_is_complete"] is False and any("missing_price" in w for w in rep["warnings"])
    plan = client.post("/api/procurement-plan", json={"date": tomorrow}, headers=economist)
    assert plan.status_code == 422 and plan.json()["error"]["code"] == "incomplete_calculation"


def test_16_dish_without_recipe(client, admin, economist, cook, tomorrow):
    cat = client.get("/api/categories").json()["data"][0]["id"]
    created = client.post("/api/dishes", headers=admin, json={
        "name": "Новое блюдо", "slug": "new-dish", "category_id": cat, "product_type": "prepared_dish",
        "sale_price": "90.00", "serving_size": "250", "serving_unit": "g"})
    assert created.status_code == 201 and created.json()["data"]["has_recipe"] is False
    did = created.json()["data"]["id"]
    assert place_order(client, {"new-dish": 5, "plov": 10}, tomorrow).status_code == 201
    rep = client.post("/api/procurement-plan/preview", json={"date": tomorrow}, headers=economist).json()["data"]
    assert rep["dishes_requiring_recipe"][0]["dish_name"] == "Новое блюдо"
    assert rep["dishes_requiring_recipe"][0]["status"] == "requiring_recipe" and rep["total_is_complete"] is False
    rice = next(i for i in rep["items"] if i["ingredient_name"] == "Рис")
    assert rice["required_quantity"] == 1000     # потребность блюда без рецепта не выдумываем
    prod = client.post("/api/production", headers=cook, json={
        "dish_id": did, "production_date": tomorrow, "prepared_portions": 5, "served_portions": 5})
    assert prod.status_code == 422 and prod.json()["error"]["code"] == "requires_recipe"


def test_17_approve_plan_and_receive_without_double_posting(client, economist, cook, admin, tomorrow):
    _plov_120(client, tomorrow)
    r = client.post("/api/procurement-plan", json={"date": tomorrow}, headers=economist)
    assert r.status_code == 201 and r.json()["data"]["status"] == "approved"
    pid = r.json()["data"]["id"]
    assert stock_of(client, admin, "beef") == 8000                 # утверждение не меняет склад
    assert client.post("/api/procurement-plan", json={"date": tomorrow}, headers=economist).status_code == 409
    first = client.post(f"/api/procurement-plan/{pid}/receive", headers=cook)
    second = client.post(f"/api/procurement-plan/{pid}/receive", headers=cook)
    assert first.json()["meta"]["stock_updated"] is True and second.json()["meta"]["stock_updated"] is False
    assert stock_of(client, admin, "beef") == 12000                # 8000 + 4000, один раз
    moves = client.get("/api/inventory/movements", params={"movement_type": "purchase"}, headers=admin).json()["meta"]["count"]
    assert moves == 1
    assert client.patch(f"/api/procurement-plan/{pid}/cancel", headers=economist).status_code == 409


# ---------------------------------------------------------------- склад, производство, отходы
def test_18_inventory_rules(client, cook, economist):
    ids = ingredient_ids(client, cook)
    no_reason = client.post("/api/inventory/adjustments", headers=cook, json={"ingredient_id": ids["rice"], "quantity_delta": "5"})
    assert no_reason.status_code == 422
    ok = client.post("/api/inventory/adjustments", headers=cook,
                     json={"ingredient_id": ids["rice"], "quantity_delta": "-500", "reason": "Пересчёт склада"})
    assert ok.status_code == 201 and ok.json()["data"]["balance_after"] == 19500
    too_much = client.post("/api/inventory/adjustments", headers=cook,
                           json={"ingredient_id": ids["rice"], "quantity_delta": "-999999", "reason": "Ошибка ввода"})
    assert too_much.status_code == 409 and too_much.json()["error"]["code"] == "insufficient_stock"
    # остаток нельзя изменить напрямую через PATCH
    direct = client.patch(f"/api/ingredients/{ids['rice']}", headers=economist, json={"stock_quantity": 1})
    assert direct.status_code in (200, 422)
    assert stock_of(client, cook, "rice") == 19500
    neg_price = client.patch(f"/api/ingredients/{ids['rice']}", headers=economist, json={"purchase_price": "-5", "price_unit": "kg"})
    assert neg_price.status_code == 422


def test_19_production_consumption_waste_and_analytics(client, cook, admin, tomorrow):
    today = date.today().isoformat()
    ids = dish_ids(client)
    r = client.post("/api/production", headers=cook, json={
        "dish_id": ids["plov"], "production_date": today, "planned_portions": 20, "prepared_portions": 20,
        "served_portions": 15, "discarded_portions": 3})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["leftover_portions"] == 2 and data["stock_consumed"] is True
    assert D(data["waste_cost"]) == Dc("200.85")                    # 3 × 66.95
    assert stock_of(client, admin, "rice") == 18000                 # 20 × 100 г списано
    waste = client.get("/api/analytics/waste", params={"from": today, "to": today, "include_demo": "true"}, headers=admin).json()["data"]
    assert D(waste["total_waste_cost"]) == Dc("200.85") and D(waste["waste_percent_of_prepared"]) == Dc("15.00")
    assert waste["by_dish"][0]["dish_name"] == "Плов" and waste["cost_is_complete"] is True
    # сырой ингредиент: запись + движение waste
    ing = ingredient_ids(client, cook)["tomato"]
    w = client.post("/api/waste", headers=cook, json={"ingredient_id": ing, "quantity": "1", "unit": "kg",
                                                       "reason": "Испортились", "waste_date": today})
    assert w.status_code == 201 and D(w.json()["data"]["estimated_cost"]) == Dc("90.00")
    assert stock_of(client, admin, "tomato") == 3000
    bad = client.post("/api/production", headers=cook, json={
        "dish_id": ids["plov"], "production_date": today, "prepared_portions": 5, "served_portions": 9})
    assert bad.status_code == 422


def test_20_production_is_atomic_and_not_double_counted(client, cook, admin, tomorrow):
    ids = dish_ids(client)
    ing = ingredient_ids(client, cook)
    client.post("/api/inventory/adjustments", headers=cook,
                json={"ingredient_id": ing["beef"], "quantity_delta": "-7990", "reason": "Тест нехватки"})
    before = client.get("/api/inventory/movements", headers=admin).json()["meta"]["count"]
    fail = client.post("/api/production", headers=cook, json={
        "dish_id": ids["plov"], "production_date": tomorrow, "prepared_portions": 50, "served_portions": 50})
    assert fail.status_code == 409 and fail.json()["error"]["code"] == "insufficient_stock"
    assert client.get("/api/inventory/movements", headers=admin).json()["meta"]["count"] == before
    assert stock_of(client, admin, "rice") == 20000                 # ничего не списано частично
    client.post("/api/inventory/adjustments", headers=cook,
                json={"ingredient_id": ing["beef"], "quantity_delta": "7990", "reason": "Возврат остатка"})
    body = {"dish_id": ids["plov"], "production_date": tomorrow, "prepared_portions": 10, "served_portions": 10}
    a = client.post("/api/production", json=body, headers={**cook, "Idempotency-Key": "prod-key-0001"})
    b = client.post("/api/production", json=body, headers={**cook, "Idempotency-Key": "prod-key-0001"})
    assert a.status_code == 201 and b.status_code == 200
    assert stock_of(client, admin, "rice") == 19000                 # списано один раз


# ---------------------------------------------------------------- безопасность
def test_21_role_based_access(client, cook, economist, admin, tomorrow):
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/orders", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/api/procurement-plan", json={"date": tomorrow}).status_code == 401
    r = client.post("/api/procurement-plan", json={"date": tomorrow}, headers=cook)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert client.post("/api/production", headers=economist, json={
        "dish_id": 1, "production_date": tomorrow, "prepared_portions": 1, "served_portions": 1}).status_code == 403
    assert client.get("/api/orders", headers=cook).status_code == 200
    assert client.get("/api/analytics/summary", params={"from": tomorrow, "to": tomorrow}, headers=economist).status_code == 200
    assert client.post("/api/dishes", headers=economist, json={}).status_code == 403
    bad_login = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert bad_login.status_code == 401


def test_22_passwords_are_hashed(settings, client):
    from sqlalchemy import create_engine, text
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        hashes = [row[0] for row in conn.execute(text("SELECT password_hash FROM users"))]
    assert len(hashes) == 3 and all(h.startswith("scrypt$") for h in hashes)
    assert not any(p in h for h in hashes for p in PASSWORDS.values())


def test_23_cors_is_configurable(client):
    ok = client.options("/api/menu", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/api/menu", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


# ---------------------------------------------------------------- seed и аналитика
def test_24_seed_is_idempotent(tmp_path):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings)) as c1:
        first = c1.get("/api/menu").json()["meta"]["count"]
        ing1 = len(c1.get("/api/ingredients", headers=auth(c1, "admin")).json()["data"])
    with TestClient(create_app(settings)) as c2:     # повторный запуск на той же БД
        assert c2.get("/api/menu").json()["meta"]["count"] == first == len(DISHES)
        assert c2.get("/api/categories").json()["meta"]["count"] == len(CATEGORIES)
        assert len(c2.get("/api/ingredients", headers=auth(c2, "admin")).json()["data"]) == ing1


def test_25_analytics_separates_demo_from_real(demo_client):
    admin = auth(demo_client, "admin")
    today = date.today()
    params = {"from": (today - timedelta(days=40)).isoformat(), "to": today.isoformat()}
    real = demo_client.get("/api/analytics/popularity", params=params, headers=admin).json()["data"]
    assert real["history"]["insufficient_history"] is True and real["history"]["data_basis"] == "none" and real["dishes"] == []
    demo = demo_client.get("/api/analytics/popularity", params={**params, "include_demo": "true"}, headers=admin).json()["data"]
    assert demo["history"]["contains_demo_data"] is True and demo["history"]["history_days"] >= 14
    assert demo["dishes"][0]["portions"] >= demo["dishes"][-1]["portions"] and demo["weekdays"]
    summary = demo_client.get("/api/analytics/summary", params={**params, "include_demo": "true"}, headers=admin).json()["data"]
    assert summary["revenue"] > 0 and "не чистая прибыль" in summary["note"]
    waste = demo_client.get("/api/analytics/waste", params={**params, "include_demo": "true"}, headers=admin).json()["data"]
    assert waste["contains_demo_data"] is True and waste["total_waste_cost"] > 0
    # демо-заказы на ближайший рабочий день доступны для демонстрации закупок
    tomorrow_demo = demo_client.get("/api/orders", params={"limit": 500, "status": "confirmed"}, headers=admin).json()["data"]
    target = tomorrow_demo[0]["order_date"]
    rep = demo_client.post("/api/procurement-plan/preview", json={"date": target}, headers=auth(demo_client, "economist")).json()["data"]
    assert rep["total_portions"] > 0 and rep["items"]
    only_real = demo_client.post("/api/procurement-plan/preview", json={"date": target, "include_demo": False},
                                 headers=auth(demo_client, "economist")).json()["data"]
    assert only_real["total_portions"] == 0
