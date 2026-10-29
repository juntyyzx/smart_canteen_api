"""Единицы измерения.

Правила:
- масса: g, kg  -> базовая единица g
- объём: ml, l  -> базовая единица ml
- штуки: pcs    -> базовая единица pcs
- portion, package — отдельные «счётные» единицы, ни во что не конвертируются.

Граммы НЕ конвертируются в миллилитры (плотность неизвестна) и наоборот.
"""
from decimal import Decimal

MASS = "mass"
VOLUME = "volume"
COUNT = "count"
PORTION = "portion"
PACKAGE = "package"

_UNITS: dict[str, tuple[str, Decimal]] = {
    "g": (MASS, Decimal(1)),
    "kg": (MASS, Decimal(1000)),
    "ml": (VOLUME, Decimal(1)),
    "l": (VOLUME, Decimal(1000)),
    "pcs": (COUNT, Decimal(1)),
    "portion": (PORTION, Decimal(1)),
    "package": (PACKAGE, Decimal(1)),
}

_BASE = {MASS: "g", VOLUME: "ml", COUNT: "pcs", PORTION: "portion", PACKAGE: "package"}

# Единицы, в которых допускается складской учёт ингредиентов.
STOCK_UNITS = ("g", "ml", "pcs")
ALL_UNITS = tuple(_UNITS)


class UnitError(ValueError):
    """Неизвестная или несовместимая единица измерения."""


def unit_kind(unit: str) -> str:
    try:
        return _UNITS[unit][0]
    except KeyError:
        raise UnitError(f"Неизвестная единица измерения: {unit!r}") from None


def base_unit(unit: str) -> str:
    return _BASE[unit_kind(unit)]


def is_compatible(unit_a: str, unit_b: str) -> bool:
    return unit_kind(unit_a) == unit_kind(unit_b)


def convert(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    """Конвертирует количество между совместимыми единицами (kg->g, l->ml ...)."""
    kind_from, factor_from = _UNITS.get(from_unit, (None, None))
    kind_to, factor_to = _UNITS.get(to_unit, (None, None))
    if kind_from is None:
        raise UnitError(f"Неизвестная единица измерения: {from_unit!r}")
    if kind_to is None:
        raise UnitError(f"Неизвестная единица измерения: {to_unit!r}")
    if kind_from != kind_to:
        raise UnitError(
            f"Нельзя конвертировать {from_unit} в {to_unit}: разные типы величин "
            f"(без известной плотности продукта массу и объём не смешиваем)."
        )
    return Decimal(quantity) * factor_from / factor_to


def price_per_base_unit(price: Decimal, price_unit: str, base: str) -> Decimal:
    """Цена за 1 `price_unit` -> цена за 1 базовую единицу `base`.

    Пример: 95 KGS за kg, база g -> 0.095 KGS за g.
    """
    one_price_unit_in_base = convert(Decimal(1), price_unit, base)
    if one_price_unit_in_base <= 0:
        raise UnitError("Некорректная единица цены")
    return Decimal(price) / one_price_unit_in_base
