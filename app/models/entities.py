"""Модели БД. Деньги и количества — Decimal (хранятся строкой, без потери точности)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utcnow
from app.database import Base

MOVEMENT_TYPES = ("purchase", "consumption", "waste", "adjustment", "return")
ORDER_STATUSES = ("pending", "confirmed", "cancelled", "completed")
PRODUCT_TYPES = ("prepared_dish", "beverage", "dessert", "snack", "sauce", "extra")
ROLE_ADMIN, ROLE_COOK, ROLE_ECONOMIST = "administrator", "cook", "economist"

__all__ = [
    "Category", "Dish", "Ingredient", "RecipeItem", "Order", "OrderItem", "InventoryMovement",
    "ProductionRecord", "WasteRecord", "PurchasePlan", "PurchasePlanItem", "Role", "User", "AuthToken",
    "IngredientPriceHistory", "AppMeta", "MOVEMENT_TYPES", "ORDER_STATUSES", "PRODUCT_TYPES",
    "ROLE_ADMIN", "ROLE_COOK", "ROLE_ECONOMIST",
]


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Dish(Base):
    __tablename__ = "dishes"
    __table_args__ = (
        CheckConstraint("sale_price >= 0", name="ck_dish_price_nonneg"),
        CheckConstraint("product_type IN ('prepared_dish','beverage','dessert','snack','sauce','extra')", name="ck_dish_type"),
        CheckConstraint("sourcing IN ('prepared','purchased')", name="ck_dish_sourcing"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    product_type: Mapped[str] = mapped_column(String(20))
    sourcing: Mapped[str] = mapped_column(String(10), default="prepared")  # prepared | purchased
    sale_price: Mapped[Decimal] = mapped_column()
    serving_size: Mapped[Decimal] = mapped_column()
    serving_unit: Mapped[str] = mapped_column(String(10))
    image_url: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_preorder_only: Mapped[bool] = mapped_column(Boolean, default=False)
    preparation_time_minutes: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    allergens: Mapped[str] = mapped_column(String(200), default="")      # через запятую
    dietary_tags: Mapped[str] = mapped_column(String(200), default="")   # через запятую
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    category: Mapped["Category"] = relationship(lazy="selectin")
    recipe_items: Mapped[list["RecipeItem"]] = relationship(
        back_populates="dish", cascade="all, delete-orphan", lazy="selectin")


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("unit IN ('g','ml','pcs')", name="ck_ing_unit"),
        CheckConstraint("stock_quantity >= 0", name="ck_ing_stock_nonneg"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    unit: Mapped[str] = mapped_column(String(5))                         # базовая единица учёта
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(default=None)  # KGS за 1 price_unit
    price_unit: Mapped[Optional[str]] = mapped_column(String(5), default=None)
    package_size: Mapped[Optional[Decimal]] = mapped_column(default=None)
    package_unit: Mapped[Optional[str]] = mapped_column(String(5), default=None)
    stock_quantity: Mapped[Decimal] = mapped_column(default=Decimal(0))
    minimum_stock: Mapped[Decimal] = mapped_column(default=Decimal(0))
    is_perishable: Mapped[bool] = mapped_column(Boolean, default=False)
    shelf_life_days: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    allergens: Mapped[str] = mapped_column(String(200), default="")
    contains_meat: Mapped[bool] = mapped_column(Boolean, default=False)
    is_purchased_product: Mapped[bool] = mapped_column(Boolean, default=False)  # готовый закупаемый товар
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RecipeItem(Base):
    __tablename__ = "recipe_items"
    __table_args__ = (
        UniqueConstraint("dish_id", "ingredient_id", name="uq_recipe_dish_ingredient"),
        CheckConstraint("quantity_per_portion > 0", name="ck_recipe_qty_pos"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    quantity_per_portion: Mapped[Decimal] = mapped_column()   # в базовой единице ингредиента (нетто)
    unit: Mapped[str] = mapped_column(String(5))
    yield_factor: Mapped[Optional[Decimal]] = mapped_column(default=None)  # (0;1], None = потерь нет
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)

    dish: Mapped["Dish"] = relationship(back_populates="recipe_items")
    ingredient: Mapped["Ingredient"] = relationship(lazy="selectin")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_order_number: Mapped[str] = mapped_column(String(32), unique=True)
    customer_ref: Mapped[Optional[str]] = mapped_column(String(64), default=None)  # анонимный идентификатор
    order_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    total_amount: Mapped[Decimal] = mapped_column(default=Decimal(0))
    currency: Mapped[str] = mapped_column(String(3), default="KGS")
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, default=None)
    request_hash: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)

    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_orderitem_qty_pos"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_sale_price: Mapped[Decimal] = mapped_column()   # цена на момент заказа (снимок)
    line_total: Mapped[Decimal] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(String(200), default=None)

    order: Mapped["Order"] = relationship(back_populates="items")
    dish: Mapped["Dish"] = relationship(lazy="selectin")


class InventoryMovement(Base):
    """Любое изменение остатка проходит через движение. quantity — со знаком (+ приход, − расход)."""
    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("movement_type IN ('purchase','consumption','waste','adjustment','return')", name="ck_mv_type"),
        Index("ix_mv_ingredient_created", "ingredient_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    movement_type: Mapped[str] = mapped_column(String(12))
    quantity: Mapped[Decimal] = mapped_column()
    unit: Mapped[str] = mapped_column(String(5))
    unit_cost: Mapped[Optional[Decimal]] = mapped_column(default=None)  # KGS за базовую единицу
    balance_after: Mapped[Decimal] = mapped_column()
    reference_type: Mapped[Optional[str]] = mapped_column(String(30), default=None)
    reference_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    reason: Mapped[Optional[str]] = mapped_column(String(300), default=None)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    ingredient: Mapped["Ingredient"] = relationship(lazy="selectin")


class ProductionRecord(Base):
    __tablename__ = "production_records"
    __table_args__ = (
        CheckConstraint("prepared_portions >= 0 AND served_portions >= 0 AND leftover_portions >= 0 "
                        "AND discarded_portions >= 0 AND planned_portions >= 0", name="ck_prod_nonneg"),
        CheckConstraint("served_portions + leftover_portions + discarded_portions = prepared_portions", name="ck_prod_balance"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dishes.id"), index=True)
    production_date: Mapped[date] = mapped_column(Date, index=True)
    planned_portions: Mapped[int] = mapped_column(Integer, default=0)
    prepared_portions: Mapped[int] = mapped_column(Integer)
    served_portions: Mapped[int] = mapped_column(Integer)
    leftover_portions: Mapped[int] = mapped_column(Integer)
    discarded_portions: Mapped[int] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(String(300), default=None)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, default=None)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    dish: Mapped["Dish"] = relationship(lazy="selectin")


class WasteRecord(Base):
    __tablename__ = "waste_records"
    __table_args__ = (
        CheckConstraint("(dish_id IS NULL) <> (ingredient_id IS NULL)", name="ck_waste_one_subject"),
        CheckConstraint("quantity > 0", name="ck_waste_qty_pos"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[Optional[int]] = mapped_column(ForeignKey("dishes.id"), index=True, default=None)
    ingredient_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ingredients.id"), index=True, default=None)
    production_record_id: Mapped[Optional[int]] = mapped_column(ForeignKey("production_records.id"), default=None)
    quantity: Mapped[Decimal] = mapped_column()
    unit: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(String(300))
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(default=None)
    cost_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    waste_date: Mapped[date] = mapped_column(Date, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, default=None)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    dish: Mapped[Optional["Dish"]] = relationship(lazy="selectin")
    ingredient: Mapped[Optional["Ingredient"]] = relationship(lazy="selectin")


class PurchasePlan(Base):
    __tablename__ = "purchase_plans"
    __table_args__ = (
        # на одну дату — не более одного действующего (approved/received) плана
        Index("uq_active_plan_per_date", "plan_date", unique=True,
              sqlite_where=text("status IN ('approved','received')"),
              postgresql_where=text("status IN ('approved','received')")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(12), default="approved")  # approved | received | cancelled
    total_estimated_cost: Mapped[Decimal] = mapped_column(default=Decimal(0))
    total_is_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(100), unique=True, default=None)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)

    items: Mapped[list["PurchasePlanItem"]] = relationship(back_populates="plan", cascade="all, delete-orphan", lazy="selectin")


class PurchasePlanItem(Base):
    __tablename__ = "purchase_plan_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_plan_id: Mapped[int] = mapped_column(ForeignKey("purchase_plans.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"))
    unit: Mapped[str] = mapped_column(String(5))
    required_quantity: Mapped[Decimal] = mapped_column()
    stock_quantity: Mapped[Decimal] = mapped_column()
    available_quantity: Mapped[Decimal] = mapped_column()
    reserved_quantity: Mapped[Decimal] = mapped_column()
    net_need: Mapped[Decimal] = mapped_column()
    purchase_quantity: Mapped[Decimal] = mapped_column()
    package_size: Mapped[Optional[Decimal]] = mapped_column(default=None)
    package_count: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(default=None)   # KGS за базовую единицу
    estimated_cost: Mapped[Optional[Decimal]] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    explanation: Mapped[Optional[str]] = mapped_column(Text, default=None)
    received_quantity: Mapped[Optional[Decimal]] = mapped_column(default=None)

    plan: Mapped["PurchasePlan"] = relationship(back_populates="items")
    ingredient: Mapped["Ingredient"] = relationship(lazy="selectin")


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    role: Mapped["Role"] = relationship(lazy="selectin")


class AuthToken(Base):
    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256; сам токен не хранится
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IngredientPriceHistory(Base):
    __tablename__ = "ingredient_price_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredients.id"), index=True)
    purchase_price: Mapped[Optional[Decimal]] = mapped_column(default=None)
    price_unit: Mapped[Optional[str]] = mapped_column(String(5), default=None)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppMeta(Base):
    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
