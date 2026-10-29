"""Аналитика. Демо-данные (is_demo) отделены от реальных наблюдений."""
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import unprocessable
from app.domain.calculator import CalculationError, dish_unit_cost
from app.domain.money import money, qty
from app.models import Category, Dish, Order, OrderItem, ProductionRecord, WasteRecord
from app.schemas.analytics import (CategoryPopularity, DishPopularity, HistoryInfo, PopularityOut, SummaryOut,
                                   WasteAnalyticsOut, WasteByDish, WasteByIngredient, WasteByReason, WeekdayDemand)
from app.services.calc_inputs import load_ingredient_infos, to_dish_info
from app.services.order_service import COUNTED_STATUSES

WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def _check_range(d_from: date, d_to: date) -> None:
    if d_from > d_to:
        raise unprocessable("invalid_range", "Дата «from» не может быть позже «to»")
    if (d_to - d_from).days > 366:
        raise unprocessable("range_too_large", "Максимальный период — 366 дней")


def _percent(part: Decimal, whole: Decimal) -> Optional[Decimal]:
    if whole <= 0:
        return None
    return (part * 100 / whole).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _order_rows(db: Session, d_from: date, d_to: date, include_demo: bool) -> list:
    stmt = (select(Order.id, Order.order_date, Order.is_demo, OrderItem.dish_id, OrderItem.quantity,
                   OrderItem.line_total, Dish.name, Category.name)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Dish, Dish.id == OrderItem.dish_id)
            .join(Category, Category.id == Dish.category_id)
            .where(Order.status.in_(COUNTED_STATUSES), Order.order_date >= d_from, Order.order_date <= d_to))
    if not include_demo:
        stmt = stmt.where(Order.is_demo.is_(False))
    return db.execute(stmt).all()


def _history(rows: list, settings: Settings) -> HistoryInfo:
    days = {r[1] for r in rows}
    flags = {bool(r[2]) for r in rows}
    basis = "none" if not rows else ("demo" if flags == {True} else "real" if flags == {False} else "mixed")
    insufficient = len(days) < settings.min_history_days
    message = None
    if not rows:
        message = "Нет данных за выбранный период: рейтинг популярности и прогноз построить нельзя."
    elif insufficient:
        message = (f"Недостаточно истории для надёжных выводов: {len(days)} дн. из {settings.min_history_days} минимальных. "
                   f"Рейтинг ориентировочный.")
    if basis in ("demo", "mixed"):
        message = ((message + " ") if message else "") + "В выборке есть ДЕМОНСТРАЦИОННЫЕ данные — это не реальные наблюдения."
    return HistoryInfo(history_days=len(days), min_history_days=settings.min_history_days,
                       insufficient_history=insufficient, data_basis=basis,
                       contains_demo_data=basis in ("demo", "mixed"), message=message)


def popularity(db: Session, settings: Settings, d_from: date, d_to: date, include_demo: bool) -> PopularityOut:
    _check_range(d_from, d_to)
    rows = _order_rows(db, d_from, d_to, include_demo)
    dishes: dict = {}
    cats: dict = defaultdict(lambda: [0, Decimal(0)])
    wd_portions: dict = defaultdict(int)
    wd_days: dict = defaultdict(set)
    for order_id, odate, _demo, dish_id, quantity, line_total, dish_name, cat_name in rows:
        d = dishes.setdefault(dish_id, {"name": dish_name, "cat": cat_name, "orders": set(), "portions": 0, "rev": Decimal(0)})
        d["orders"].add(order_id)
        d["portions"] += quantity
        d["rev"] += line_total
        cats[cat_name][0] += quantity
        cats[cat_name][1] += line_total
        wd_portions[odate.weekday()] += quantity
        wd_days[odate.weekday()].add(odate)
    dish_list = [DishPopularity(dish_id=i, dish_name=d["name"], category=d["cat"], orders=len(d["orders"]),
                                portions=d["portions"], revenue=money(d["rev"]))
                 for i, d in sorted(dishes.items(), key=lambda kv: (-kv[1]["portions"], kv[1]["name"]))]
    cat_list = [CategoryPopularity(category=c, portions=v[0], revenue=money(v[1]))
                for c, v in sorted(cats.items(), key=lambda kv: -kv[1][0])]
    weekdays = [WeekdayDemand(weekday=w, weekday_name=WEEKDAYS[w], days_observed=len(wd_days[w]),
                              portions=wd_portions[w],
                              avg_portions_per_day=(Decimal(wd_portions[w]) / len(wd_days[w])).quantize(Decimal("0.01")))
                for w in sorted(wd_portions)]
    return PopularityOut(date_from=d_from, date_to=d_to, history=_history(rows, settings),
                         dishes=dish_list, categories=cat_list, weekdays=weekdays)


def waste_analytics(db: Session, d_from: date, d_to: date, include_demo: bool) -> WasteAnalyticsOut:
    _check_range(d_from, d_to)
    w_stmt = select(WasteRecord).where(WasteRecord.waste_date >= d_from, WasteRecord.waste_date <= d_to)
    p_stmt = select(ProductionRecord).where(ProductionRecord.production_date >= d_from, ProductionRecord.production_date <= d_to)
    if not include_demo:
        w_stmt = w_stmt.where(WasteRecord.is_demo.is_(False))
        p_stmt = p_stmt.where(ProductionRecord.is_demo.is_(False))
    wastes = db.scalars(w_stmt).all()
    prods = db.scalars(p_stmt).all()

    prepared: dict = defaultdict(int)
    for p in prods:
        prepared[p.dish_id] += p.prepared_portions
    by_dish: dict = {}
    by_ing: dict = {}
    by_reason: dict = defaultdict(lambda: [0, Decimal(0)])
    total_cost = Decimal(0)
    complete = True
    wasted_portions = Decimal(0)
    for w in wastes:
        cost = w.estimated_cost if w.estimated_cost is not None else Decimal(0)
        complete = complete and w.cost_complete
        total_cost += cost
        by_reason[w.reason][0] += 1
        by_reason[w.reason][1] += cost
        if w.dish_id is not None:
            e = by_dish.setdefault(w.dish_id, {"name": w.dish.name, "q": Decimal(0), "c": Decimal(0)})
            e["q"] += w.quantity
            e["c"] += cost
            wasted_portions += w.quantity
        else:
            e = by_ing.setdefault(w.ingredient_id, {"name": w.ingredient.name, "unit": w.unit, "q": Decimal(0), "c": Decimal(0)})
            e["q"] += w.quantity
            e["c"] += cost
    total_prepared = sum(prepared.values())
    dish_names = {p.dish_id: p.dish.name for p in prods}
    ids = set(by_dish) | set(prepared)
    dish_rows = []
    for i in ids:
        name = by_dish[i]["name"] if i in by_dish else dish_names[i]
        q = by_dish[i]["q"] if i in by_dish else Decimal(0)
        c = by_dish[i]["c"] if i in by_dish else Decimal(0)
        dish_rows.append(WasteByDish(dish_id=i, dish_name=name, waste_portions=qty(q), waste_cost=money(c),
                                     prepared_portions=prepared.get(i, 0), waste_percent=_percent(q, Decimal(prepared.get(i, 0)))))
    dish_rows.sort(key=lambda r: (-r.waste_cost, r.dish_name))
    return WasteAnalyticsOut(
        date_from=d_from, date_to=d_to, contains_demo_data=any(w.is_demo for w in wastes) or any(p.is_demo for p in prods),
        total_waste_cost=money(total_cost), cost_is_complete=complete, total_prepared_portions=total_prepared,
        total_wasted_portions=qty(wasted_portions), waste_percent_of_prepared=_percent(wasted_portions, Decimal(total_prepared)),
        by_dish=dish_rows,
        by_ingredient=[WasteByIngredient(ingredient_id=i, ingredient_name=e["name"], quantity=qty(e["q"]), unit=e["unit"], cost=money(e["c"]))
                       for i, e in sorted(by_ing.items(), key=lambda kv: -kv[1]["c"])],
        by_reason=[WasteByReason(reason=r, records=v[0], cost=money(v[1])) for r, v in sorted(by_reason.items(), key=lambda kv: -kv[1][1])])


def summary(db: Session, settings: Settings, d_from: date, d_to: date, include_demo: bool) -> SummaryOut:
    _check_range(d_from, d_to)
    rows = _order_rows(db, d_from, d_to, include_demo)
    portions: dict = defaultdict(int)
    revenue = Decimal(0)
    for _oid, _d, _demo, dish_id, quantity, line_total, _n, _c in rows:
        portions[dish_id] += quantity
        revenue += line_total
    cost_total = Decimal(0)
    complete = True
    if portions:
        dishes = db.scalars(select(Dish).where(Dish.id.in_(list(portions)))).all()
        ing_ids = {r.ingredient_id for d in dishes for r in d.recipe_items}
        infos = load_ingredient_infos(db, ing_ids)
        for d in dishes:
            if not any(not r.is_optional for r in d.recipe_items):
                complete = False
                continue
            try:
                unit_cost, missing = dish_unit_cost(to_dish_info(d), infos)
            except CalculationError:
                complete = False
                continue
            if missing:
                complete = False
                continue
            cost_total += unit_cost * portions[d.id]
    waste = waste_analytics(db, d_from, d_to, include_demo)
    return SummaryOut(
        date_from=d_from, date_to=d_to, history=_history(rows, settings), orders=len({r[0] for r in rows}),
        portions=sum(portions.values()), revenue=money(revenue),
        ingredient_cost_of_sold=money(cost_total) if complete else None,
        gross_difference_over_ingredients=money(revenue - cost_total) if complete else None,
        cost_is_complete=complete, waste_cost=waste.total_waste_cost,
        waste_percent_of_prepared=waste.waste_percent_of_prepared,
        note=("Валовая разница по ингредиентам = выручка − стоимость ингредиентов проданных порций (по текущим ценам и рецептурам). "
              "Это не чистая прибыль: зарплаты, электричество и аренда не учитываются."))
