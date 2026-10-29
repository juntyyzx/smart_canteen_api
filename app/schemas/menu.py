import re
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORM, Num

SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class CategoryOut(ORM):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    display_order: int
    dish_count: int = 0


class CategoryRef(ORM):
    id: int
    name: str
    slug: str


class DishOut(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    category: CategoryRef
    product_type: str
    sourcing: str
    sale_price: Num
    currency: str = "KGS"
    serving_size: Num
    serving_unit: str
    image_url: Optional[str]
    is_available: bool
    is_preorder_only: bool
    preparation_time_minutes: Optional[int]
    allergens: list[str]
    dietary_tags: list[str]
    has_recipe: bool
    is_demo: bool


class DishCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(pattern=SLUG, max_length=100)
    description: Optional[str] = Field(default=None, max_length=2000)
    category_id: int
    product_type: str = Field(pattern=r"^(prepared_dish|beverage|dessert|snack|sauce|extra)$")
    sourcing: str = Field(default="prepared", pattern=r"^(prepared|purchased)$")
    sale_price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    serving_size: Decimal = Field(gt=0, max_digits=10, decimal_places=3)
    serving_unit: str = Field(pattern=r"^(g|kg|ml|l|pcs|portion)$")
    image_url: Optional[str] = Field(default=None, max_length=500)
    is_available: bool = True
    is_preorder_only: bool = False
    preparation_time_minutes: Optional[int] = Field(default=None, ge=0, le=1440)


class DishPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    category_id: Optional[int] = None
    sale_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    serving_size: Optional[Decimal] = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    serving_unit: Optional[str] = Field(default=None, pattern=r"^(g|kg|ml|l|pcs|portion)$")
    image_url: Optional[str] = Field(default=None, max_length=500)
    is_available: Optional[bool] = None
    is_preorder_only: Optional[bool] = None
    preparation_time_minutes: Optional[int] = Field(default=None, ge=0, le=1440)


class RecipeLineIn(BaseModel):
    ingredient_id: int
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: str = Field(pattern=r"^(g|kg|ml|l|pcs)$")
    yield_factor: Optional[Decimal] = Field(default=None, gt=0, le=1, max_digits=5, decimal_places=3)
    is_optional: bool = False


class RecipeIn(BaseModel):
    items: list[RecipeLineIn] = Field(min_length=1, max_length=60)


class RecipeLineOut(BaseModel):
    ingredient_id: int
    ingredient_name: str
    quantity_per_portion: Num
    unit: str
    yield_factor: Optional[Num]
    is_optional: bool
    line_cost: Optional[Num]


class RecipeOut(BaseModel):
    dish_id: int
    dish_name: str
    items: list[RecipeLineOut]
    is_demo: bool


class DishCostingOut(BaseModel):
    dish_id: int
    dish_name: str
    currency: str = "KGS"
    sale_price: Num
    ingredient_cost_per_portion: Optional[Num]
    gross_difference_per_portion: Optional[Num]
    cost_is_complete: bool
    missing_price_ingredients: list[str]
    note: str
