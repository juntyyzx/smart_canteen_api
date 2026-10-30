"""Тип колонки для точных Decimal.

SQLite: хранится строкой (без потери точности, у SQLite нет настоящего DECIMAL).
PostgreSQL: настоящий NUMERIC — иначе CHECK-ограничения вида «stock_quantity >= 0» не работают
(Postgres не сравнивает текст с числом) и суммы считались бы по строкам.
"""
from decimal import Decimal

from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator


class DecimalText(TypeDecorator):
    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Numeric(24, 6))
        return dialect.type_descriptor(String())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, float):
            value = Decimal(str(value))
        value = Decimal(value)
        return value if dialect.name == "postgresql" else format(value, "f")

    def process_result_value(self, value, dialect):
        return None if value is None else Decimal(value)
