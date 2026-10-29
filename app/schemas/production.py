from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Num


class ProductionIn(BaseModel):
    dish_id: int
    production_date: date
    planned_portions: int = Field(default=0, ge=0, le=100000)
    prepared_portions: int = Field(ge=0, le=100000)
    served_portions: int = Field(ge=0, le=100000)
    leftover_portions: Optional[int] = Field(default=None, ge=0, le=100000,
                                             description="Остаток, который будет использован; по умолчанию = prepared − served − discarded")
    discarded_portions: int = Field(default=0, ge=0, le=100000, description="Выброшено; автоматически попадает в учёт отходов")
    notes: Optional[str] = Field(default=None, max_length=300)
    consume_stock: bool = Field(default=True, description="Списать ингредиенты со склада по рецептуре")
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=100)

    @model_validator(mode="after")
    def _balance(self):
        leftover = self.leftover_portions
        if leftover is None:
            leftover = self.prepared_portions - self.served_portions - self.discarded_portions
            if leftover < 0:
                raise ValueError("served + discarded не может превышать prepared")
            self.leftover_portions = leftover
        if self.served_portions + leftover + self.discarded_portions != self.prepared_portions:
            raise ValueError("Должно выполняться: served + leftover + discarded = prepared")
        return self


class ProductionOut(BaseModel):
    id: int
    dish_id: int
    dish_name: str
    production_date: date
    planned_portions: int
    prepared_portions: int
    served_portions: int
    leftover_portions: int
    discarded_portions: int
    notes: Optional[str]
    stock_consumed: bool
    waste_record_id: Optional[int] = None
    waste_cost: Optional[Num] = None
    is_demo: bool


class WasteIn(BaseModel):
    dish_id: Optional[int] = None
    ingredient_id: Optional[int] = None
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(pattern=r"^(portion|g|kg|ml|l|pcs)$")
    reason: str = Field(min_length=3, max_length=300)
    waste_date: date
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=100)

    @model_validator(mode="after")
    def _one_subject(self):
        if (self.dish_id is None) == (self.ingredient_id is None):
            raise ValueError("Укажите ровно одно: dish_id (готовое блюдо) или ingredient_id (сырой ингредиент)")
        return self


class WasteOut(BaseModel):
    id: int
    dish_id: Optional[int]
    ingredient_id: Optional[int]
    subject_name: str
    quantity: Num
    unit: str
    reason: str
    estimated_cost: Optional[Num]
    cost_complete: bool
    waste_date: date
    is_demo: bool
