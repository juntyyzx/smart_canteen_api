from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORM, Num

SLUG = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"


class IngredientOut(BaseModel):
    id: int
    name: str
    slug: str
    unit: str
    purchase_price: Optional[Num]
    price_unit: Optional[str]
    price_per_base_unit: Optional[Num]
    package_size: Optional[Num]
    package_unit: Optional[str]
    stock_quantity: Num
    minimum_stock: Num
    below_minimum: bool
    is_perishable: bool
    shelf_life_days: Optional[int]
    allergens: list[str]
    is_purchased_product: bool
    is_active: bool
    is_demo: bool
    currency: str = "KGS"


class IngredientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=SLUG, max_length=100)
    unit: str = Field(pattern=r"^(g|ml|pcs)$")
    purchase_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    price_unit: Optional[str] = Field(default=None, pattern=r"^(g|kg|ml|l|pcs)$")
    package_size: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_unit: Optional[str] = Field(default=None, pattern=r"^(g|kg|ml|l|pcs)$")
    initial_stock: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=3)
    minimum_stock: Decimal = Field(default=Decimal(0), ge=0, max_digits=14, decimal_places=3)
    is_perishable: bool = False
    shelf_life_days: Optional[int] = Field(default=None, ge=1, le=3650)
    allergens: list[str] = Field(default_factory=list, max_length=14)
    is_purchased_product: bool = False


class IngredientPatch(BaseModel):
    """Остаток здесь изменить нельзя — только через /api/inventory/adjustments."""
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    purchase_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    price_unit: Optional[str] = Field(default=None, pattern=r"^(g|kg|ml|l|pcs)$")
    package_size: Optional[Decimal] = Field(default=None, gt=0, max_digits=12, decimal_places=3)
    package_unit: Optional[str] = Field(default=None, pattern=r"^(g|kg|ml|l|pcs)$")
    minimum_stock: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    is_perishable: Optional[bool] = None
    shelf_life_days: Optional[int] = Field(default=None, ge=1, le=3650)
    allergens: Optional[list[str]] = Field(default=None, max_length=14)
    is_active: Optional[bool] = None


class AdjustmentIn(BaseModel):
    ingredient_id: int
    quantity_delta: Decimal = Field(description="Изменение остатка: + приход, − уменьшение", max_digits=14, decimal_places=3)
    reason: str = Field(min_length=3, max_length=300, description="Причина корректировки (обязательна)")
    idempotency_key: Optional[str] = Field(default=None, min_length=8, max_length=100)


class MovementOut(BaseModel):
    id: int
    ingredient_id: int
    ingredient_name: str
    movement_type: str
    quantity: Num
    unit: str
    unit_cost: Optional[Num]
    balance_after: Num
    reference_type: Optional[str]
    reference_id: Optional[int]
    reason: Optional[str]
    created_at: datetime


class StockSetItem(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3,
                              description="Фактический остаток в единице учёта ингредиента (g, ml или pcs)")


class StockSetIn(BaseModel):
    items: list[StockSetItem] = Field(min_length=1, max_length=300)
    reason: str = Field(default="Ручной ввод остатка поваром", min_length=3, max_length=300)
