"""Производство (приготовлено/выдано/остаток/выброшено) и учёт отходов."""
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import conflict, unprocessable
from app.core.utils import transaction
from app.domain.calculator import CalculationError, dish_unit_cost
from app.domain.money import money, qty
from app.domain.units import UnitError, convert
from app.models import Dish, Ingredient, ProductionRecord, WasteRecord
from app.schemas.production import ProductionIn, ProductionOut, WasteIn, WasteOut
from app.services.calc_inputs import load_ingredient_infos, price_per_base, to_dish_info
from app.services.inventory_service import apply_movement, get_ingredient
from app.services.menu_service import get_dish


def dish_cost_per_portion(db: Session, dish: Dish) -> tuple:
    """(стоимость ингредиентов на порцию | None, данные полные?)."""
    if not any(not r.is_optional for r in dish.recipe_items):
        return None, False
    infos = load_ingredient_infos(db, [r.ingredient_id for r in dish.recipe_items])
    try:
        cost, missing = dish_unit_cost(to_dish_info(dish), infos)
    except CalculationError as exc:
        raise unprocessable(exc.code, exc.message) from None
    return (cost, True) if not missing else (None, False)


def production_to_out(p: ProductionRecord, consumed: bool, waste: Optional[WasteRecord]) -> ProductionOut:
    return ProductionOut(
        id=p.id, dish_id=p.dish_id, dish_name=p.dish.name, production_date=p.production_date,
        planned_portions=p.planned_portions, prepared_portions=p.prepared_portions, served_portions=p.served_portions,
        leftover_portions=p.leftover_portions, discarded_portions=p.discarded_portions, notes=p.notes,
        stock_consumed=consumed, waste_record_id=waste.id if waste else None,
        waste_cost=waste.estimated_cost if waste else None, is_demo=p.is_demo)


def record_production(db: Session, payload: ProductionIn, header_key: Optional[str] = None) -> tuple:
    key = payload.idempotency_key or header_key
    if key:
        existing = db.scalar(select(ProductionRecord).where(ProductionRecord.idempotency_key == key))
        if existing is not None:
            return existing, False, None, False  # (record, created, waste, consumed)
    dish = get_dish(db, payload.dish_id)
    lines = [r for r in dish.recipe_items if not r.is_optional]
    consume = payload.consume_stock and payload.prepared_portions > 0
    if consume and not lines:
        raise unprocessable("requires_recipe", "У блюда нет рецептуры — списание продуктов невозможно (requiring_recipe)")

    needs: dict = defaultdict(lambda: Decimal(0))
    if consume:
        for r in lines:
            gross = r.quantity_per_portion / r.yield_factor if r.yield_factor else r.quantity_per_portion
            needs[r.ingredient_id] += gross * payload.prepared_portions
        needs = {i: qty(v) for i, v in needs.items()}
        ings = {i.id: i for i in db.scalars(select(Ingredient).where(Ingredient.id.in_(list(needs)))).all()}
        shortages = [{"ingredient_id": i, "ingredient": ings[i].name, "required": str(n), "in_stock": str(ings[i].stock_quantity)}
                     for i, n in needs.items() if ings[i].stock_quantity < n]
        if shortages:
            raise conflict("insufficient_stock", "Не хватает продуктов на складе для списания", {"shortages": shortages})

    cost, complete = dish_cost_per_portion(db, dish)
    try:
        with transaction(db):  # запись, списание и отходы — одна транзакция
            rec = ProductionRecord(
                dish_id=dish.id, production_date=payload.production_date, planned_portions=payload.planned_portions,
                prepared_portions=payload.prepared_portions, served_portions=payload.served_portions,
                leftover_portions=payload.leftover_portions, discarded_portions=payload.discarded_portions,
                notes=payload.notes, idempotency_key=key, is_demo=False)
            db.add(rec)
            db.flush()
            if consume:
                for ing_id, need in needs.items():
                    ing = ings[ing_id]
                    apply_movement(db, ing, "consumption", -need, unit_cost=price_per_base(ing),
                                   reference_type="production", reference_id=rec.id,
                                   reason=f"Приготовление: {dish.name} × {payload.prepared_portions}")
            waste = None
            if payload.discarded_portions > 0:
                waste = WasteRecord(
                    dish_id=dish.id, production_record_id=rec.id, quantity=Decimal(payload.discarded_portions),
                    unit="portion", reason="Выброшено при производстве (неиспользованный остаток)",
                    estimated_cost=money(cost * payload.discarded_portions) if complete else None,
                    cost_complete=complete, waste_date=payload.production_date, is_demo=False)
                db.add(waste)
    except IntegrityError:
        replay = db.scalar(select(ProductionRecord).where(ProductionRecord.idempotency_key == key)) if key else None
        if replay is not None:
            return replay, False, None, False
        raise
    return rec, True, waste, consume


def waste_to_out(w: WasteRecord) -> WasteOut:
    name = w.dish.name if w.dish is not None else w.ingredient.name
    return WasteOut(id=w.id, dish_id=w.dish_id, ingredient_id=w.ingredient_id, subject_name=name,
                    quantity=w.quantity, unit=w.unit, reason=w.reason, estimated_cost=w.estimated_cost,
                    cost_complete=w.cost_complete, waste_date=w.waste_date, is_demo=w.is_demo)


def record_waste(db: Session, payload: WasteIn, header_key: Optional[str] = None) -> tuple:
    """Готовое блюдо: только запись отхода (ингредиенты списаны при производстве).
    Сырой ингредиент: запись + движение 'waste' (уменьшает склад)."""
    key = payload.idempotency_key or header_key
    if key:
        existing = db.scalar(select(WasteRecord).where(WasteRecord.idempotency_key == key))
        if existing is not None:
            return existing, False
    try:
        with transaction(db):
            if payload.dish_id is not None:
                if payload.unit != "portion":
                    raise unprocessable("invalid_unit", "Для готового блюда единица отхода — portion")
                dish = get_dish(db, payload.dish_id)
                cost, complete = dish_cost_per_portion(db, dish)
                rec = WasteRecord(dish_id=dish.id, quantity=payload.quantity, unit="portion", reason=payload.reason,
                                  estimated_cost=money(cost * payload.quantity) if complete else None,
                                  cost_complete=complete, waste_date=payload.waste_date, idempotency_key=key)
                db.add(rec)
            else:
                ing = get_ingredient(db, payload.ingredient_id)
                if payload.unit == "portion":
                    raise unprocessable("invalid_unit", "Для ингредиента укажите g/kg/ml/l/pcs")
                try:
                    base_qty = qty(convert(payload.quantity, payload.unit, ing.unit))
                except UnitError as exc:
                    raise unprocessable("incompatible_units", str(exc)) from None
                price = price_per_base(ing)
                rec = WasteRecord(ingredient_id=ing.id, quantity=base_qty, unit=ing.unit, reason=payload.reason,
                                  estimated_cost=money(base_qty * price) if price is not None else None,
                                  cost_complete=price is not None, waste_date=payload.waste_date, idempotency_key=key)
                db.add(rec)
                db.flush()
                apply_movement(db, ing, "waste", -base_qty, unit_cost=price, reference_type="waste_record",
                               reference_id=rec.id, reason=payload.reason)
    except IntegrityError:
        replay = db.scalar(select(WasteRecord).where(WasteRecord.idempotency_key == key)) if key else None
        if replay is not None:
            return replay, False
        raise
    return rec, True


def describe_production(db: Session, rec: ProductionRecord) -> tuple:
    """(waste, stock_consumed) для уже существующей записи — нужно при повторном запросе."""
    from app.models import InventoryMovement
    waste = db.scalar(select(WasteRecord).where(WasteRecord.production_record_id == rec.id))
    consumed = db.scalar(select(InventoryMovement.id).where(
        InventoryMovement.reference_type == "production", InventoryMovement.reference_id == rec.id).limit(1)) is not None
    return waste, consumed
