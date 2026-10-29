from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num


class PreviewIn(BaseModel):
    date: date
    include_pending: bool = Field(default=False, description="Учитывать неподтверждённые (pending) заказы")
    include_demo: bool = Field(default=True, description="Учитывать демонстрационные заказы (is_demo)")


class PlanCreateIn(PreviewIn):
    allow_incomplete: bool = Field(default=False, description="Разрешить утверждение при missing_price / requiring_recipe")
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=100)


class BreakdownOut(BaseModel):
    dish_id: int
    dish_name: str
    portions: int
    quantity_per_portion: Num
    quantity: Num


class ProcItemOut(BaseModel):
    ingredient_id: int
    ingredient_name: str
    unit: str
    required_quantity: Num
    stock_quantity: Num
    reserved_quantity: Num
    available_quantity: Num
    net_need: Num
    package_size: Optional[Num]
    package_count: Optional[int]
    purchase_quantity: Num
    price_per_unit: Optional[Num]
    estimated_cost: Optional[Num]
    status: str
    breakdown: list[BreakdownOut] = []
    explanation: str = ""


class DishNoRecipeOut(BaseModel):
    dish_id: int
    dish_name: str
    portions: int
    status: str


class ProcurementReportOut(BaseModel):
    plan_date: date
    kind: str = "preview"
    currency: str = "KGS"
    total_portions: int
    items: list[ProcItemOut]
    dishes_requiring_recipe: list[DishNoRecipeOut]
    warnings: list[str]
    total_estimated_cost: Num
    total_is_complete: bool


class PlanOut(BaseModel):
    id: int
    plan_date: date
    status: str
    kind: str = "approved_plan"
    currency: str = "KGS"
    total_estimated_cost: Num
    total_is_complete: bool
    created_at: datetime
    received_at: Optional[datetime]
    items: list[ProcItemOut]


class ReceiveItemIn(BaseModel):
    ingredient_id: int
    received_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)


class ReceiveIn(BaseModel):
    items: Optional[list[ReceiveItemIn]] = Field(default=None, description="Фактически принятые количества; для не указанных позиций принимается количество из плана")
