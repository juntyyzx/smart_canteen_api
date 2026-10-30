"""Идемпотентное заполнение БД: меню, ингредиенты, рецепты, остатки, демо-история.

Повторный запуск ничего не дублирует и не перезаписывает: существующие записи
определяются по slug и не изменяются. Все данные помечены is_demo=True.
"""
import logging
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import Settings
from app.core.utils import transaction
from app.domain.calculator import dish_unit_cost
from app.domain.money import money
from app.models import (AppMeta, Category, Dish, Ingredient, IngredientPriceHistory, Order, OrderItem,
                        ProductionRecord, RecipeItem, WasteRecord, ROLE_ADMIN, ROLE_COOK, ROLE_ECONOMIST, User)
from app.seed.menu_data import CATEGORIES, DEMO_WEIGHTS, DISHES, INGREDIENTS
from app.services import auth_service
from app.services.calc_inputs import derive_traits, load_ingredient_infos, to_dish_info
from app.services.inventory_service import apply_movement

log = logging.getLogger("smart_canteen.seed")
DEMO_FLAG = "demo_history_v1"


def _parse_recipe(text: str) -> list:
    out = []
    for part in text.split(","):
        optional = part.endswith("?")
        slug, quantity = part.rstrip("?").split(":")
        out.append((slug, Decimal(quantity), optional))
    return out


def _description(dish: dict, ingredient_names: list) -> str:
    size = f"{dish['serving_size'].normalize():f} {dish['serving_unit']}"
    if dish["sourcing"] == "purchased":
        return (f"Демонстрационная позиция: готовый закупаемый товар. Порция {size}. "
                f"Состав и аллергены — по маркировке производителя.")
    return f"Демонстрационная позиция. Состав: {', '.join(n.lower() for n in ingredient_names)}. Порция {size}."


def _seed_users(db, settings: Settings) -> int:
    created = 0
    for role, username, password in (
        (ROLE_ADMIN, "admin", settings.seed_admin_password),
        (ROLE_COOK, "cook", settings.seed_cook_password),
        (ROLE_ECONOMIST, "economist", settings.seed_economist_password),
    ):
        auth_service.get_or_create_role(db, role)
        if password and db.scalar(select(User.id).where(User.username == username)) is None:
            auth_service.create_user(db, username, password, role)
            created += 1
    if settings.is_production and created == 0 and db.scalar(select(User.id).limit(1)) is None:
        log.warning("В production не заданы SEED_*_PASSWORD: пользователи не созданы (scripts/create_user.py).")
    return created


def _seed_menu(db, demo_stock: bool = True) -> dict:
    stats = {"categories": 0, "ingredients": 0, "dishes": 0}
    cats = {c.slug: c for c in db.scalars(select(Category)).all()}
    for slug, name, description, order in CATEGORIES:
        if slug not in cats:
            cats[slug] = Category(slug=slug, name=name, description=description, display_order=order)
            db.add(cats[slug])
            stats["categories"] += 1
    db.flush()  # получаем id категорий
    ings = {i.slug: i for i in db.scalars(select(Ingredient)).all()}
    for row in INGREDIENTS:
        if row["slug"] in ings:
            continue
        ing = Ingredient(
            slug=row["slug"], name=row["name"], unit=row["unit"], purchase_price=row["price"], price_unit=row["price_unit"],
            package_size=row["package_size"], package_unit=row["package_unit"], stock_quantity=Decimal(0),
            minimum_stock=row["minimum"], is_perishable=row["is_perishable"], shelf_life_days=row["shelf_life_days"],
            allergens=row["allergens"], contains_meat=row["contains_meat"],
            is_purchased_product=row["is_purchased_product"], is_demo=True)
        db.add(ing)
        db.flush()
        db.add(IngredientPriceHistory(ingredient_id=ing.id, purchase_price=row["price"], price_unit=row["price_unit"]))
        if demo_stock and row["stock"] > 0:
            apply_movement(db, ing, "adjustment", row["stock"], reason="Демонстрационный начальный остаток")
        ings[ing.slug] = ing
        stats["ingredients"] += 1
    db.flush()
    existing = {d.slug for d in db.scalars(select(Dish)).all()}
    for row in DISHES:
        if row["slug"] in existing:
            continue
        lines = _parse_recipe(row["recipe"])
        used = [ings[s] for s, _, _ in lines]
        allergens, tags = derive_traits(used, row["sourcing"])
        dish = Dish(
            slug=row["slug"], name=row["name"], category_id=cats[row["category"]].id, product_type=row["product_type"],
            sourcing=row["sourcing"], sale_price=row["price"], serving_size=row["serving_size"],
            serving_unit=row["serving_unit"], preparation_time_minutes=row["prep"], allergens=allergens,
            dietary_tags=tags, description=_description(row, [i.name for i in used]), is_demo=True)
        for slug, quantity, optional in lines:
            dish.recipe_items.append(RecipeItem(ingredient_id=ings[slug].id, quantity_per_portion=quantity,
                                                unit=ings[slug].unit, is_optional=optional))
        db.add(dish)
        stats["dishes"] += 1
    return stats


def _seed_demo_history(db) -> dict:
    rng = random.Random(42)  # детерминированно
    dishes = db.scalars(select(Dish).where(Dish.is_demo.is_(True), Dish.is_available.is_(True))).all()
    dishes.sort(key=lambda d: d.slug)
    weights = [DEMO_WEIGHTS.get(d.slug, 1) for d in dishes]
    infos = load_ingredient_infos(db, {r.ingredient_id for d in dishes for r in d.recipe_items})
    unit_cost = {}
    for d in dishes:
        cost, missing = dish_unit_cost(to_dish_info(d), infos)
        unit_cost[d.id] = None if missing else cost
    factor = {0: 1.0, 1: 1.05, 2: 1.1, 3: 1.0, 4: 0.85}
    counts = {"orders": 0, "production": 0, "waste": 0}

    def make_orders(day: date, status: str, n: int) -> dict:
        sold: dict = defaultdict(int)
        for k in range(n):
            picks: dict = defaultdict(int)
            for d in rng.choices(dishes, weights, k=rng.randint(1, 3)):
                picks[d.id] += rng.randint(1, 2)
            order = Order(public_order_number=f"DEMO-{day:%Y%m%d}-{k:04d}", customer_ref=f"demo-{rng.randint(1, 200)}",
                          order_date=day, status=status, is_demo=True, created_at=datetime.combine(day, time(8, 0)))
            total = Decimal(0)
            for dish_id, qty_ in picks.items():
                dish = next(d for d in dishes if d.id == dish_id)
                line = money(dish.sale_price * qty_)
                total += line
                order.items.append(OrderItem(dish_id=dish_id, quantity=qty_, unit_sale_price=dish.sale_price, line_total=line))
                sold[dish_id] += qty_
            order.total_amount = money(total)
            db.add(order)
            counts["orders"] += 1
        return sold

    today = date.today()
    for back in range(28, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        sold = make_orders(day, "completed", int(rng.randint(40, 60) * factor[day.weekday()]))
        for dish in dishes:
            n = sold.get(dish.id, 0)
            if dish.sourcing != "prepared" or n < 3:
                continue
            discarded = rng.randint(0, max(1, n // 8))
            leftover = rng.randint(0, 2)
            prepared = n + leftover + discarded
            prod = ProductionRecord(dish_id=dish.id, production_date=day, planned_portions=max(0, prepared + rng.randint(-2, 3)),
                                    prepared_portions=prepared, served_portions=n, leftover_portions=leftover,
                                    discarded_portions=discarded, is_demo=True, notes="demo")
            db.add(prod)
            counts["production"] += 1
            if discarded:
                db.flush()
                cost = unit_cost[dish.id]
                db.add(WasteRecord(dish_id=dish.id, production_record_id=prod.id, quantity=Decimal(discarded), unit="portion",
                                   reason="Выброшено при производстве (неиспользованный остаток)",
                                   estimated_cost=money(cost * discarded) if cost is not None else None,
                                   cost_complete=cost is not None, waste_date=day, is_demo=True))
                counts["waste"] += 1
    # Подтверждённые демо-заказы на ближайший рабочий день — для демонстрации расчёта закупок
    target = today + timedelta(days=1)
    while target.weekday() >= 5:
        target += timedelta(days=1)
    make_orders(target, "confirmed", 70)
    counts["procurement_demo_date"] = target.isoformat()
    return counts


def run_seed(session_factory, settings: Settings) -> dict:
    result: dict = {}
    with session_factory() as db:
        with transaction(db):
            result["users_created"] = _seed_users(db, settings)
            result.update(_seed_menu(db, settings.seed_demo_stock))
        if settings.seed_demo_history and db.get(AppMeta, DEMO_FLAG) is None:
            with transaction(db):
                result["demo_history"] = _seed_demo_history(db)
                db.add(AppMeta(key=DEMO_FLAG, value=datetime.now().isoformat(timespec="seconds")))
    log.info("seed: %s", result)
    return result
