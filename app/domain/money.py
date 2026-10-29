"""Точная арифметика: только Decimal, никаких float в расчётах."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CURRENCY = "KGS"
_CENT = Decimal("0.01")
_MILLI = Decimal("0.001")


def D(value) -> Decimal:
    """Безопасное создание Decimal. float принимается только через str()."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("bool не является числом")
    if isinstance(value, float):
        value = str(value)
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Некорректное число: {value!r}") from None


def money(value) -> Decimal:
    """Округление денег до 0.01 (half-up)."""
    return D(value).quantize(_CENT, rounding=ROUND_HALF_UP)


def qty(value) -> Decimal:
    """Округление количества до 0.001 (half-up)."""
    return D(value).quantize(_MILLI, rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    """Человекочитаемая запись Decimal без экспоненты и лишних нулей."""
    value = D(value)
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"
