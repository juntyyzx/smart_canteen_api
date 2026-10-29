"""Тип колонки для точных Decimal в SQLite (хранится строкой, без потери точности)."""
from decimal import Decimal

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class DecimalText(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            value = Decimal(str(value))
        return format(Decimal(value), "f")

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)
