from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import conflict, not_found, unprocessable
from app.core.utils import transaction
from app.domain.calculator import CalculationError, dish_unit_cost
from app.domain.money import money
from app.domain.units import UnitError, convert
from app.models import Category, Dish, Ingredient, RecipeItem
from app.schemas.menu import (CategoryOut, CategoryRef, DishCostingOut, DishCreate, DishOut, DishPatch,
                              RecipeIn, RecipeLineOut, RecipeOut)
from app.services.calc_inputs import csv, derive_traits, load_ingredient_infos, price_per_base, to_dish_info


def dish_to_out(d: Dish) -> DishOut:
    return DishOut(
        id=d.id, name=d.name, slug=d.slug, description=d.description,
        category=CategoryRef(id=d.category.id, name=d.category.name, slug=d.category.slug),
        product_type=d.product_type, sourcing=d.sourcing, sale_price=d.sale_price,
        serving_size=d.serving_size, serving_unit=d.serving_unit, image_url=d.image_url,
        is_available=d.is_available, is_preorder_only=d.is_preorder_only,
        preparation_time_minutes=d.preparation_time_minutes,
        allergens=csv(d.allergens), dietary_tags=csv(d.dietary_tags),
        has_recipe=any(not r.is_optional for r in d.recipe_items), is_demo=d.is_demo,
    )


def list_categories(db: Session) -> list:
    counts = dict(db.execute(select(Dish.category_id, func.count(Dish.id)).group_by(Dish.category_id)).all())
    cats = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.display_order)).all()
    return [CategoryOut(id=c.id, name=c.name, slug=c.slug, description=c.description,
                        display_order=c.display_order, dish_count=counts.get(c.id, 0)) for c in cats]


def list_menu(db: Session, category: Optional[str], available: Optional[bool],
              product_type: Optional[str], search: Optional[str]) -> list:
    stmt = (select(Dish).join(Category, Dish.category_id == Category.id)
            .where(Category.is_active.is_(True)).order_by(Category.display_order, Dish.name))
    if category:
        stmt = stmt.where(Category.slug == category)
    if available is not None:
        stmt = stmt.where(Dish.is_available.is_(available))
    if product_type:
        stmt = stmt.where(Dish.product_type == product_type)
    dishes = db.scalars(stmt).all()
    if search:  # SQLite LIKE не учитывает регистр кириллицы, поэтому фильтруем в Python
        needle = search.casefold()
        dishes = [d for d in dishes if needle in d.name.casefold()]
    return [dish_to_out(d) for d in dishes]


def get_dish(db: Session, dish_id: int) -> Dish:
    dish = db.get(Dish, dish_id)
    if dish is None:
        raise not_found("Блюдо", dish_id)
    return dish


def create_dish(db: Session, payload: DishCreate) -> Dish:
    if db.scalar(select(Dish.id).where(Dish.slug == payload.slug)) is not None:
        raise conflict("slug_exists", f"Блюдо со slug «{payload.slug}» уже существует")
    if db.get(Category, payload.category_id) is None:
        raise unprocessable("unknown_category", f"Категория id={payload.category_id} не найдена")
    with transaction(db):
        dish = Dish(**payload.model_dump(), is_demo=False)
        db.add(dish)
        db.flush()
    db.refresh(dish)
    return dish


def patch_dish(db: Session, dish_id: int, payload: DishPatch) -> Dish:
    dish = get_dish(db, dish_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise unprocessable("empty_patch", "Не передано ни одного поля для изменения")
    for field in ("name", "category_id", "sale_price", "serving_size", "serving_unit", "is_available", "is_preorder_only"):
        if field in data and data[field] is None:
            raise unprocessable("null_not_allowed", f"Поле {field} не может быть null")
    if "category_id" in data and db.get(Category, data["category_id"]) is None:
        raise unprocessable("unknown_category", f"Категория id={data['category_id']} не найдена")
    with transaction(db):
        for key, value in data.items():
            setattr(dish, key, value)  # цена старых заказов не меняется: в заказах хранится снимок цены
    db.refresh(dish)
    return dish


def set_recipe(db: Session, dish_id: int, payload: RecipeIn) -> RecipeOut:
    dish = get_dish(db, dish_id)
    ids = [i.ingredient_id for i in payload.items]
    if len(set(ids)) != len(ids):
        raise unprocessable("duplicate_ingredient", "Ингредиент указан в рецептуре несколько раз")
    ings = {i.id: i for i in db.scalars(select(Ingredient).where(Ingredient.id.in_(ids))).all()}
    unknown = [i for i in ids if i not in ings]
    if unknown:
        raise unprocessable("unknown_ingredient", "Ингредиенты не найдены", {"ingredient_ids": unknown})
    new_items = []
    for line in payload.items:
        ing = ings[line.ingredient_id]
        if not ing.is_active:
            raise unprocessable("inactive_ingredient", f"Ингредиент «{ing.name}» отключён")
        try:
            base_qty = convert(line.quantity, line.unit, ing.unit)
        except UnitError as exc:
            raise unprocessable("incompatible_units", f"«{ing.name}»: {exc}") from None
        new_items.append(RecipeItem(ingredient_id=ing.id, quantity_per_portion=base_qty, unit=ing.unit,
                                    yield_factor=line.yield_factor, is_optional=line.is_optional))
    with transaction(db):
        dish.recipe_items.clear()
        db.flush()  # сначала DELETE старых строк, затем INSERT новых (уникальность dish+ingredient)
        dish.recipe_items.extend(new_items)
        dish.allergens, tags = derive_traits(ings.values(), dish.sourcing)
        dish.dietary_tags = tags
    db.refresh(dish)
    return recipe_out(db, dish)


def recipe_out(db: Session, dish: Dish) -> RecipeOut:
    infos = load_ingredient_infos(db, [r.ingredient_id for r in dish.recipe_items])
    lines = []
    for r in dish.recipe_items:
        info = infos[r.ingredient_id]
        cost = None
        if info.price_per_unit is not None and not r.is_optional:
            gross = r.quantity_per_portion / r.yield_factor if r.yield_factor else r.quantity_per_portion
            cost = money(gross * info.price_per_unit)
        lines.append(RecipeLineOut(ingredient_id=r.ingredient_id, ingredient_name=info.name,
                                   quantity_per_portion=r.quantity_per_portion, unit=r.unit,
                                   yield_factor=r.yield_factor, is_optional=r.is_optional, line_cost=cost))
    return RecipeOut(dish_id=dish.id, dish_name=dish.name, items=lines, is_demo=dish.is_demo)


def dish_costing(db: Session, dish_id: int) -> DishCostingOut:
    dish = get_dish(db, dish_id)
    infos = load_ingredient_infos(db, [r.ingredient_id for r in dish.recipe_items])
    note = ("Валовая разница по ингредиентам = цена продажи − стоимость ингредиентов. Это НЕ чистая прибыль: "
            "зарплаты, электричество, аренда и прочие расходы не учитываются.")
    if not any(not r.is_optional for r in dish.recipe_items):
        return DishCostingOut(dish_id=dish.id, dish_name=dish.name, sale_price=dish.sale_price,
                              ingredient_cost_per_portion=None, gross_difference_per_portion=None,
                              cost_is_complete=False, missing_price_ingredients=[],
                              note="Рецептура отсутствует (requiring_recipe). " + note)
    try:
        cost, missing = dish_unit_cost(to_dish_info(dish), infos)
    except CalculationError as exc:
        raise unprocessable(exc.code, exc.message) from None
    complete = not missing
    cost_q = money(cost) if complete else None
    return DishCostingOut(
        dish_id=dish.id, dish_name=dish.name, sale_price=dish.sale_price,
        ingredient_cost_per_portion=cost_q,
        gross_difference_per_portion=money(dish.sale_price - cost) if complete else None,
        cost_is_complete=complete, missing_price_ingredients=[infos[i].name for i in missing], note=note)
