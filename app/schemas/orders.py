from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import Num


class OrderItemIn(BaseModel):
    dish_id: int
    quantity: int = Field(ge=1, le=1000)
    notes: Optional[str] = Field(default=None, max_length=200)


class OrderCreate(BaseModel):
    customer_ref: Optional[str] = Field(default=None, max_length=64, description="Анонимный идентификатор клиента")
    order_date: Optional[date] = Field(default=None, description="Дата получения; по умолчанию — сегодня")
    items: list[OrderItemIn] = Field(min_length=1, max_length=40)
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=100)


class OrderItemOut(BaseModel):
    dish_id: int
    dish_name: str
    quantity: int
    unit_sale_price: Num
    line_total: Num
    notes: Optional[str]


class OrderOut(BaseModel):
    id: int
    public_order_number: str
    customer_ref: Optional[str]
    order_date: date
    status: str
    total_amount: Num
    currency: str = "KGS"
    items: list[OrderItemOut]
    is_demo: bool
    created_at: datetime
    cancelled_at: Optional[datetime]


class OrderTrackOut(BaseModel):
    """Публичное представление (для подтверждения заказа на сайте) — без персональных данных."""
    public_order_number: str
    order_date: date
    status: str
    total_amount: Num
    currency: str = "KGS"
    items: list[OrderItemOut]


class DishDemand(BaseModel):
    dish_id: int
    dish_name: str
    portions: int
    revenue: Num


class OrderSummaryOut(BaseModel):
    date: date
    orders_by_status: dict[str, int]
    counted_statuses: list[str]
    total_portions: int
    total_revenue: Num
    currency: str = "KGS"
    dishes: list[DishDemand]
