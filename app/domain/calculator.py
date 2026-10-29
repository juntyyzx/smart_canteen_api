"""ProcurementCalculator — расчёт потребности в продуктах и стоимости закупки.

Модуль не зависит ни от БД, ни от FastAPI: на входе обычные структуры, на выходе
отчёт с объяснением каждого числа. Вся арифметика — Decimal, ИИ не используется.

Все количества — в БАЗОВЫХ единицах ингредиента (g, ml или pcs),
цена — за одну базовую единицу.

Формулы:
    gross_per_portion   = quantity_per_portion / yield_factor   (yield_factor задан явно, иначе 1)
    required_quantity   = sum(portions * gross_per_portion)     по всем блюдам
    available           = max(0, stock - reserved)              (резерв вычитается один раз)
    net_need            = max(0, required_quantity - available)
    package_count       = ceil(net_need / package_size)         (если упаковка задана)
    purchase_quantity   = package_count * package_size          (иначе = net_need)
    estimated_cost      = money(purchase_quantity * price_per_unit)
"""
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Mapping, Optional, Sequence

from app.domain.money import D, fmt, money, qty

STATUS_OK = "ok"
STATUS_SUFFICIENT = "sufficient_stock"
STATUS_MISSING_PRICE = "missing_price"
STATUS_REQUIRING_RECIPE = "requiring_recipe"


class CalculationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- входные данные
@dataclass(frozen=True)
class RecipeLine:
    ingredient_id: int
    quantity_per_portion: Decimal  # в базовой единице ингредиента, на 1 порцию (нетто)
    yield_factor: Optional[Decimal] = None  # доля выхода (0 < y <= 1); None = потерь нет
    is_optional: bool = False


@dataclass(frozen=True)
class IngredientInfo:
    id: int
    name: str
    unit: str  # базовая единица: g | ml | pcs
    price_per_unit: Optional[Decimal] = None  # KGS за 1 базовую единицу
    package_size: Optional[Decimal] = None  # размер упаковки в базовых единицах


@dataclass(frozen=True)
class DishInfo:
    id: int
    name: str
    recipe: tuple = ()


# --------------------------------------------------------------------------- результат
@dataclass
class BreakdownLine:
    dish_id: int
    dish_name: str
    portions: int
    quantity_per_portion: Decimal  # с учётом выхода (брутто)
    quantity: Decimal


@dataclass
class ProcurementItem:
    ingredient_id: int
    ingredient_name: str
    unit: str
    required_quantity: Decimal
    stock_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    net_need: Decimal
    package_size: Optional[Decimal]
    package_count: Optional[int]
    purchase_quantity: Decimal
    price_per_unit: Optional[Decimal]
    estimated_cost: Optional[Decimal]
    status: str
    breakdown: list = field(default_factory=list)
    explanation: str = ""


@dataclass
class DishWithoutRecipe:
    dish_id: int
    dish_name: str
    portions: int
    status: str = STATUS_REQUIRING_RECIPE


@dataclass
class ProcurementReport:
    plan_date: date
    total_portions: int
    items: list
    dishes_requiring_recipe: list
    warnings: list
    total_estimated_cost: Decimal
    total_is_complete: bool

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- проверки
def validate_line(line: RecipeLine) -> None:
    if line.quantity_per_portion is None or D(line.quantity_per_portion) <= 0:
        raise CalculationError("invalid_quantity", "Количество в рецепте должно быть больше нуля")
    if line.yield_factor is not None and not (Decimal(0) < D(line.yield_factor) <= Decimal(1)):
        raise CalculationError("invalid_yield_factor", "Коэффициент выхода должен быть в диапазоне (0; 1]")


def validate_ingredient(info: IngredientInfo) -> None:
    if info.package_size is not None and D(info.package_size) <= 0:
        raise CalculationError("invalid_package_size", f"Размер упаковки «{info.name}» должен быть больше нуля")
    if info.price_per_unit is not None and D(info.price_per_unit) < 0:
        raise CalculationError("invalid_price", f"Цена «{info.name}» не может быть отрицательной")


def gross_per_portion(line: RecipeLine) -> Decimal:
    """Расход на порцию с учётом технологических потерь (только если выход задан явно)."""
    validate_line(line)
    quantity = D(line.quantity_per_portion)
    if line.yield_factor is None:
        return quantity
    return quantity / D(line.yield_factor)


def _ceil_div(a: Decimal, b: Decimal) -> int:
    whole = a // b
    return int(whole if a % b == 0 else whole + 1)


def _active_lines(dish: DishInfo, include_optional: bool) -> list:
    return [ln for ln in dish.recipe if include_optional or not ln.is_optional]


# --------------------------------------------------------------------------- себестоимость
def dish_unit_cost(
    dish: DishInfo,
    ingredients: Mapping[int, IngredientInfo],
    include_optional: bool = False,
) -> tuple:
    """Себестоимость ингредиентов на 1 порцию (без округления) и список ингредиентов без цены."""
    total = Decimal(0)
    missing: list = []
    for line in _active_lines(dish, include_optional):
        info = ingredients.get(line.ingredient_id)
        if info is None:
            raise CalculationError("unknown_ingredient", f"Ингредиент id={line.ingredient_id} не найден")
        validate_ingredient(info)
        if info.price_per_unit is None:
            missing.append(line.ingredient_id)
            continue
        total += gross_per_portion(line) * D(info.price_per_unit)
    return total, missing


# --------------------------------------------------------------------------- главный расчёт
def calculate_procurement(
    plan_date: date,
    demand: Mapping[int, int],
    dishes: Mapping[int, DishInfo],
    ingredients: Mapping[int, IngredientInfo],
    stock: Mapping[int, Decimal],
    reserved: Optional[Mapping[int, Decimal]] = None,
    include_optional: bool = False,
) -> ProcurementReport:
    reserved = reserved or {}
    warnings: list = []
    no_recipe: list = []
    needs: dict = {}  # ingredient_id -> {"total": Decimal, "lines": [BreakdownLine]}
    total_portions = 0

    for dish_id in sorted(demand):
        portions = demand[dish_id]
        if not isinstance(portions, int) or isinstance(portions, bool) or portions < 0:
            raise CalculationError("invalid_portions", f"Количество порций блюда id={dish_id} должно быть целым числом >= 0")
        if portions == 0:
            continue
        dish = dishes.get(dish_id)
        if dish is None:
            raise CalculationError("unknown_dish", f"Блюдо id={dish_id} не найдено")
        total_portions += portions
        lines = _active_lines(dish, include_optional)
        if not lines:
            no_recipe.append(DishWithoutRecipe(dish.id, dish.name, portions))
            warnings.append(
                f"Для блюда «{dish.name}» ({portions} порц.) нет рецептуры (requiring_recipe): "
                f"его потребность в ингредиентах НЕ включена в расчёт."
            )
            continue
        for line in lines:
            gross = gross_per_portion(line)
            bucket = needs.setdefault(line.ingredient_id, {"total": Decimal(0), "lines": []})
            bucket["total"] += gross * portions
            bucket["lines"].append(
                BreakdownLine(dish.id, dish.name, portions, qty(gross), qty(gross * portions))
            )

    items: list = []
    total_cost = Decimal(0)
    complete = not no_recipe

    for ingredient_id, bucket in needs.items():
        info = ingredients.get(ingredient_id)
        if info is None:
            raise CalculationError("unknown_ingredient", f"Ингредиент id={ingredient_id} не найден")
        validate_ingredient(info)

        stock_q = D(stock.get(ingredient_id, Decimal(0)))
        reserved_q = D(reserved.get(ingredient_id, Decimal(0)))
        if stock_q < 0 or reserved_q < 0:
            raise CalculationError("invalid_stock", f"Остаток/резерв «{info.name}» не может быть отрицательным")

        required = qty(bucket["total"])
        available = max(Decimal(0), stock_q - reserved_q)  # резерв вычитается один раз
        net_need = max(Decimal(0), required - available)

        package_size = D(info.package_size) if info.package_size is not None else None
        if net_need == 0:
            package_count = 0 if package_size is not None else None
            purchase_qty = Decimal(0)
        elif package_size is not None:
            package_count = _ceil_div(net_need, package_size)
            purchase_qty = package_count * package_size
        else:
            package_count = None
            purchase_qty = net_need

        price = D(info.price_per_unit) if info.price_per_unit is not None else None
        if net_need == 0:
            status, cost = STATUS_SUFFICIENT, money(0)
        elif price is None:
            status, cost = STATUS_MISSING_PRICE, None
            complete = False
            warnings.append(
                f"Для ингредиента «{info.name}» не задана закупочная цена (missing_price): "
                f"стоимость закупки неизвестна, итог неполный."
            )
        else:
            status, cost = STATUS_OK, money(purchase_qty * price)
            total_cost += cost

        items.append(
            ProcurementItem(
                ingredient_id=ingredient_id,
                ingredient_name=info.name,
                unit=info.unit,
                required_quantity=required,
                stock_quantity=stock_q,
                reserved_quantity=reserved_q,
                available_quantity=available,
                net_need=net_need,
                package_size=package_size,
                package_count=package_count,
                purchase_quantity=purchase_qty,
                price_per_unit=price,
                estimated_cost=cost,
                status=status,
                breakdown=bucket["lines"],
                explanation=_explain(info, required, stock_q, reserved_q, available, net_need,
                                     package_size, package_count, purchase_qty, price, cost, status),
            )
        )

    items.sort(key=lambda it: it.ingredient_name)
    return ProcurementReport(
        plan_date=plan_date,
        total_portions=total_portions,
        items=items,
        dishes_requiring_recipe=no_recipe,
        warnings=warnings,
        total_estimated_cost=money(total_cost),
        total_is_complete=complete,
    )


def _explain(info, required, stock_q, reserved_q, available, net_need,
             package_size, package_count, purchase_qty, price, cost, status) -> str:
    u = info.unit
    parts = [
        f"Требуется {fmt(required)} {u}; на складе {fmt(stock_q)} {u}, "
        f"зарезервировано {fmt(reserved_q)} {u}, доступно {fmt(available)} {u}; "
        f"чистая потребность {fmt(net_need)} {u}."
    ]
    if status == STATUS_SUFFICIENT:
        parts.append("Запаса достаточно — закупка не нужна.")
        return " ".join(parts)
    if package_size is not None:
        parts.append(
            f"Упаковка {fmt(package_size)} {u}: {package_count} уп. × {fmt(package_size)} = {fmt(purchase_qty)} {u}."
        )
    else:
        parts.append(f"Упаковка не задана: закупка = {fmt(purchase_qty)} {u}.")
    if status == STATUS_MISSING_PRICE:
        parts.append("Цена не задана — стоимость неизвестна (missing_price).")
    else:
        parts.append(f"Цена {fmt(price)} KGS за {u}: {fmt(purchase_qty)} × {fmt(price)} = {fmt(cost)} KGS.")
    return " ".join(parts)
