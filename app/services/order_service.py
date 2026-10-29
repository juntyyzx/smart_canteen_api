import hashlib
import json
import secrets
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import conflict, not_found, unprocessable
from app.core.utils import transaction, utcnow
from app.domain.money import money
from app.models import Dish, Order, OrderItem
from app.schemas.orders import (DishDemand, OrderCreate, OrderItemOut, OrderOut, OrderSummaryOut, OrderTrackOut)

COUNTED_STATUSES = ("confirmed", "completed")


def _items_out(order: Order) -> list:
    return [OrderItemOut(dish_id=i.dish_id, dish_name=i.dish.name, quantity=i.quantity,
                         unit_sale_price=i.unit_sale_price, line_total=i.line_total, notes=i.notes)
            for i in order.items]


def order_to_out(o: Order) -> OrderOut:
    return OrderOut(id=o.id, public_order_number=o.public_order_number, customer_ref=o.customer_ref,
                    order_date=o.order_date, status=o.status, total_amount=o.total_amount,
                    items=_items_out(o), is_demo=o.is_demo, created_at=o.created_at, cancelled_at=o.cancelled_at)


def order_to_track(o: Order) -> OrderTrackOut:
    return OrderTrackOut(public_order_number=o.public_order_number, order_date=o.order_date, status=o.status,
                         total_amount=o.total_amount, items=_items_out(o))


def _request_hash(payload: OrderCreate, order_date: date) -> str:
    canon = json.dumps({
        "c": payload.customer_ref, "d": order_date.isoformat(),
        "i": sorted([i.dish_id, i.quantity, i.notes or ""] for i in payload.items),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


def _number(order_date: date) -> str:
    return f"SC-{order_date:%Y%m%d}-{secrets.token_hex(3).upper()}"


def get_order(db: Session, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise not_found("Заказ", order_id)
    return order


def get_order_by_number(db: Session, number: str) -> Order:
    order = db.scalar(select(Order).where(Order.public_order_number == number))
    if order is None:
        raise not_found("Заказ")
    return order


def _by_key(db: Session, key: Optional[str]) -> Optional[Order]:
    return db.scalar(select(Order).where(Order.idempotency_key == key)) if key else None


def create_order(db: Session, payload: OrderCreate, settings: Settings, header_key: Optional[str] = None) -> tuple:
    """Возвращает (order, created). created=False — повтор запроса с тем же Idempotency-Key."""
    key = payload.idempotency_key or header_key
    today = date.today()
    order_date = payload.order_date or today
    if order_date < today:
        raise unprocessable("order_date_in_past", "Дата заказа не может быть в прошлом")
    if order_date > today + timedelta(days=settings.max_days_ahead):
        raise unprocessable("order_date_too_far", f"Предзаказ возможен не более чем на {settings.max_days_ahead} дн. вперёд")
    for it in payload.items:
        if it.quantity > settings.max_item_quantity:
            raise unprocessable("quantity_too_large", f"Максимум {settings.max_item_quantity} порций одной позиции")

    req_hash = _request_hash(payload, order_date)
    existing = _by_key(db, key)
    if existing is not None:
        if existing.request_hash != req_hash:
            raise conflict("idempotency_key_reused", "Этот Idempotency-Key уже использован с другим содержимым заказа")
        return existing, False

    ids = sorted({i.dish_id for i in payload.items})
    dishes = {d.id: d for d in db.scalars(select(Dish).where(Dish.id.in_(ids))).all()}
    unknown = [i for i in ids if i not in dishes]
    if unknown:
        raise unprocessable("unknown_dish", "Блюда не найдены", {"dish_ids": unknown})
    unavailable = [d.id for d in dishes.values() if not d.is_available or not d.category.is_active]
    if unavailable:
        raise conflict("dish_unavailable", "Некоторые позиции сейчас недоступны", {"dish_ids": unavailable})

    status = "confirmed" if settings.order_auto_confirm else "pending"
    for _attempt in range(3):
        try:
            with transaction(db):
                order = Order(public_order_number=_number(order_date), customer_ref=payload.customer_ref,
                              order_date=order_date, status=status, idempotency_key=key,
                              request_hash=req_hash, is_demo=False, currency="KGS")
                total = Decimal(0)
                for it in payload.items:
                    dish = dishes[it.dish_id]
                    line_total = money(dish.sale_price * it.quantity)
                    total += line_total
                    order.items.append(OrderItem(dish_id=dish.id, quantity=it.quantity,
                                                 unit_sale_price=dish.sale_price,  # снимок цены
                                                 line_total=line_total, notes=it.notes))
                order.total_amount = money(total)
                db.add(order)
            return order, True
        except IntegrityError:
            replay = _by_key(db, key)  # гонка двух одинаковых запросов
            if replay is not None:
                return replay, False
    raise conflict("order_not_created", "Не удалось создать заказ, повторите запрос")


def list_orders(db: Session, on_date: Optional[date], status: Optional[str], limit: int, offset: int) -> list:
    stmt = select(Order).order_by(Order.id.desc()).limit(limit).offset(offset)
    if on_date:
        stmt = stmt.where(Order.order_date == on_date)
    if status:
        stmt = stmt.where(Order.status == status)
    return db.scalars(stmt).all()


def _transition(db: Session, order: Order, allowed_from: tuple, target: str) -> bool:
    if order.status == target:
        return False  # повтор: ничего не меняем
    if order.status not in allowed_from:
        raise conflict("invalid_status_transition", f"Нельзя перевести заказ из «{order.status}» в «{target}»")
    with transaction(db):
        order.status = target
        if target == "cancelled":
            order.cancelled_at = utcnow()
    return True


def confirm_order(db, order_id): o = get_order(db, order_id); return o, _transition(db, o, ("pending",), "confirmed")
def complete_order(db, order_id): o = get_order(db, order_id); return o, _transition(db, o, ("confirmed",), "completed")
def cancel_order(db, order_id): o = get_order(db, order_id); return o, _transition(db, o, ("pending", "confirmed"), "cancelled")


def summary(db: Session, on_date: date) -> OrderSummaryOut:
    orders = db.scalars(select(Order).where(Order.order_date == on_date)).all()
    by_status: dict = defaultdict(int)
    portions: dict = defaultdict(int)
    revenue: dict = defaultdict(lambda: Decimal(0))
    names: dict = {}
    for o in orders:
        by_status[o.status] += 1
        if o.status in COUNTED_STATUSES:
            for it in o.items:
                portions[it.dish_id] += it.quantity
                revenue[it.dish_id] += it.line_total
                names[it.dish_id] = it.dish.name
    dishes = [DishDemand(dish_id=i, dish_name=names[i], portions=portions[i], revenue=money(revenue[i]))
              for i in sorted(portions, key=lambda k: (-portions[k], names[k]))]
    return OrderSummaryOut(
        date=on_date, orders_by_status={s: by_status.get(s, 0) for s in ("pending", "confirmed", "completed", "cancelled")},
        counted_statuses=list(COUNTED_STATUSES), total_portions=sum(portions.values()),
        total_revenue=money(sum(revenue.values(), Decimal(0))), dishes=dishes)
