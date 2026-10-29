"""Склад. Любое изменение остатка проходит ТОЛЬКО через apply_movement."""
from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import conflict, not_found, unprocessable
from app.core.utils import transaction
from app.domain.money import qty
from app.domain.units import UnitError, convert, is_compatible
from app.models import MOVEMENT_TYPES, Ingredient, IngredientPriceHistory, InventoryMovement
from app.schemas.inventory import (AdjustmentIn, IngredientCreate, IngredientOut, IngredientPatch, MovementOut)
from app.services.calc_inputs import csv, price_per_base

_POSITIVE = {"purchase", "return"}
_NEGATIVE = {"consumption", "waste"}


def apply_movement(db: Session, ingredient: Ingredient, movement_type: str, delta: Decimal, *,
                   unit_cost: Optional[Decimal] = None, reference_type: Optional[str] = None,
                   reference_id: Optional[int] = None, reason: Optional[str] = None,
                   idempotency_key: Optional[str] = None) -> InventoryMovement:
    """Изменяет остаток и фиксирует движение. Вызывать внутри транзакции вызывающего кода."""
    if movement_type not in MOVEMENT_TYPES:
        raise unprocessable("invalid_movement_type", f"Неизвестный тип движения: {movement_type}")
    delta = qty(delta)
    if delta == 0:
        raise unprocessable("zero_quantity", "Количество движения не может быть нулевым")
    if movement_type in _POSITIVE and delta < 0:
        raise unprocessable("invalid_sign", f"Для «{movement_type}» количество должно быть положительным")
    if movement_type in _NEGATIVE and delta > 0:
        raise unprocessable("invalid_sign", f"Для «{movement_type}» количество должно быть отрицательным")
    new_balance = ingredient.stock_quantity + delta
    if new_balance < 0:
        raise conflict("insufficient_stock", f"Недостаточно «{ingredient.name}» на складе",
                       {"ingredient_id": ingredient.id, "stock": str(ingredient.stock_quantity), "requested": str(-delta)})
    ingredient.stock_quantity = new_balance
    movement = InventoryMovement(
        ingredient_id=ingredient.id, movement_type=movement_type, quantity=delta, unit=ingredient.unit,
        unit_cost=unit_cost, balance_after=new_balance, reference_type=reference_type,
        reference_id=reference_id, reason=reason, idempotency_key=idempotency_key)
    db.add(movement)
    return movement


# ---------------------------------------------------------------- ингредиенты
def ingredient_to_out(i: Ingredient) -> IngredientOut:
    return IngredientOut(
        id=i.id, name=i.name, slug=i.slug, unit=i.unit, purchase_price=i.purchase_price, price_unit=i.price_unit,
        price_per_base_unit=price_per_base(i), package_size=i.package_size, package_unit=i.package_unit,
        stock_quantity=i.stock_quantity, minimum_stock=i.minimum_stock,
        below_minimum=i.stock_quantity < i.minimum_stock, is_perishable=i.is_perishable,
        shelf_life_days=i.shelf_life_days, allergens=csv(i.allergens),
        is_purchased_product=i.is_purchased_product, is_active=i.is_active, is_demo=i.is_demo)


def get_ingredient(db: Session, ingredient_id: int) -> Ingredient:
    ing = db.get(Ingredient, ingredient_id)
    if ing is None:
        raise not_found("Ингредиент", ingredient_id)
    return ing


def list_ingredients(db: Session, active: Optional[bool] = None, search: Optional[str] = None) -> list:
    stmt = select(Ingredient).order_by(Ingredient.name)
    if active is not None:
        stmt = stmt.where(Ingredient.is_active.is_(active))
    rows = db.scalars(stmt).all()
    if search:
        needle = search.casefold()
        rows = [r for r in rows if needle in r.name.casefold()]
    return rows


def _check_price_and_package(unit: str, price, price_unit, pkg, pkg_unit) -> None:
    if (price is None) != (price_unit is None):
        raise unprocessable("price_unit_required", "purchase_price и price_unit задаются вместе")
    if (pkg is None) != (pkg_unit is None):
        raise unprocessable("package_unit_required", "package_size и package_unit задаются вместе")
    try:
        if price_unit is not None and not is_compatible(price_unit, unit):
            raise UnitError(f"единица цены {price_unit} несовместима с единицей учёта {unit}")
        if pkg_unit is not None and not is_compatible(pkg_unit, unit):
            raise UnitError(f"единица упаковки {pkg_unit} несовместима с единицей учёта {unit}")
    except UnitError as exc:
        raise unprocessable("incompatible_units", str(exc)) from None


def create_ingredient(db: Session, payload: IngredientCreate) -> Ingredient:
    if db.scalar(select(Ingredient.id).where(Ingredient.slug == payload.slug)) is not None:
        raise conflict("slug_exists", f"Ингредиент со slug «{payload.slug}» уже существует")
    _check_price_and_package(payload.unit, payload.purchase_price, payload.price_unit,
                             payload.package_size, payload.package_unit)
    data = payload.model_dump(exclude={"initial_stock", "allergens"})
    with transaction(db):
        ing = Ingredient(**data, allergens=",".join(payload.allergens), stock_quantity=Decimal(0), is_demo=False)
        db.add(ing)
        db.flush()
        if payload.purchase_price is not None:
            db.add(IngredientPriceHistory(ingredient_id=ing.id, purchase_price=payload.purchase_price,
                                          price_unit=payload.price_unit))
        if payload.initial_stock > 0:
            apply_movement(db, ing, "adjustment", payload.initial_stock, reason="Начальный остаток при создании")
    db.refresh(ing)
    return ing


_NON_NULL = {"name", "minimum_stock", "is_perishable", "allergens", "is_active"}


def patch_ingredient(db: Session, ingredient_id: int, payload: IngredientPatch) -> Ingredient:
    ing = get_ingredient(db, ingredient_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise unprocessable("empty_patch", "Не передано ни одного поля для изменения")
    for field in _NON_NULL:
        if field in data and data[field] is None:
            raise unprocessable("null_not_allowed", f"Поле {field} не может быть null")
    merged = {
        "price": data.get("purchase_price", ing.purchase_price), "price_unit": data.get("price_unit", ing.price_unit),
        "pkg": data.get("package_size", ing.package_size), "pkg_unit": data.get("package_unit", ing.package_unit),
    }
    _check_price_and_package(ing.unit, merged["price"], merged["price_unit"], merged["pkg"], merged["pkg_unit"])
    price_changed = ("purchase_price" in data and data["purchase_price"] != ing.purchase_price) or \
                    ("price_unit" in data and data["price_unit"] != ing.price_unit)
    with transaction(db):
        for key, value in data.items():
            setattr(ing, key, ",".join(value) if key == "allergens" else value)
        if price_changed:
            db.add(IngredientPriceHistory(ingredient_id=ing.id, purchase_price=ing.purchase_price, price_unit=ing.price_unit))
    db.refresh(ing)
    return ing


# ---------------------------------------------------------------- движения
def movement_to_out(m: InventoryMovement) -> MovementOut:
    return MovementOut(id=m.id, ingredient_id=m.ingredient_id, ingredient_name=m.ingredient.name,
                       movement_type=m.movement_type, quantity=m.quantity, unit=m.unit, unit_cost=m.unit_cost,
                       balance_after=m.balance_after, reference_type=m.reference_type, reference_id=m.reference_id,
                       reason=m.reason, created_at=m.created_at)


def adjust(db: Session, payload: AdjustmentIn, header_key: Optional[str] = None) -> tuple:
    key = payload.idempotency_key or header_key
    if key:
        existing = db.scalar(select(InventoryMovement).where(InventoryMovement.idempotency_key == key))
        if existing is not None:
            return existing, False
    ing = get_ingredient(db, payload.ingredient_id)
    with transaction(db):
        movement = apply_movement(db, ing, "adjustment", payload.quantity_delta, reason=payload.reason,
                                  reference_type="manual_adjustment", idempotency_key=key)
    return movement, True


def list_movements(db: Session, ingredient_id: Optional[int], movement_type: Optional[str],
                   date_from: Optional[date], date_to: Optional[date], limit: int, offset: int) -> list:
    stmt = select(InventoryMovement).order_by(InventoryMovement.id.desc()).limit(limit).offset(offset)
    if ingredient_id:
        stmt = stmt.where(InventoryMovement.ingredient_id == ingredient_id)
    if movement_type:
        stmt = stmt.where(InventoryMovement.movement_type == movement_type)
    if date_from:
        stmt = stmt.where(InventoryMovement.created_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(InventoryMovement.created_at <= datetime.combine(date_to, time.max))
    return db.scalars(stmt).all()
