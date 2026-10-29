"""Преобразование ORM-объектов во входные структуры расчётного ядра."""
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.calculator import DishInfo, IngredientInfo, RecipeLine
from app.domain.units import convert, price_per_base_unit
from app.models import Dish, Ingredient


def csv(value: Optional[str]) -> list:
    return [x for x in (value or "").split(",") if x]


def price_per_base(ing: Ingredient) -> Optional[Decimal]:
    if ing.purchase_price is None or not ing.price_unit:
        return None
    return price_per_base_unit(ing.purchase_price, ing.price_unit, ing.unit)


def package_base(ing: Ingredient) -> Optional[Decimal]:
    if ing.package_size is None or not ing.package_unit:
        return None
    return convert(ing.package_size, ing.package_unit, ing.unit)


def to_ingredient_info(ing: Ingredient) -> IngredientInfo:
    return IngredientInfo(ing.id, ing.name, ing.unit, price_per_base(ing), package_base(ing))


def to_dish_info(dish: Dish) -> DishInfo:
    lines = tuple(
        RecipeLine(r.ingredient_id, r.quantity_per_portion, r.yield_factor, r.is_optional)
        for r in dish.recipe_items
    )
    return DishInfo(dish.id, dish.name, lines)


def load_ingredient_infos(db: Session, ids: Iterable[int]) -> dict:
    ids = list(set(ids))
    if not ids:
        return {}
    rows = db.scalars(select(Ingredient).where(Ingredient.id.in_(ids))).all()
    return {i.id: to_ingredient_info(i) for i in rows}


def derive_traits(ingredients: Iterable[Ingredient], sourcing: str) -> tuple:
    """Аллергены и диет-теги выводятся из состава (не выдумываются)."""
    ingredients = list(ingredients)
    allergens = sorted({a for i in ingredients for a in csv(i.allergens)})
    tags = []
    if sourcing == "prepared" and ingredients and not any(i.contains_meat for i in ingredients):
        tags.append("vegetarian")
    return ",".join(allergens), ",".join(tags)
