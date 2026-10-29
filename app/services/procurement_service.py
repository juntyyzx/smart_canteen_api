"""Закупки: предварительный расчёт (ничего не меняет) -> утверждённый план -> поступление."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import conflict, not_found, unprocessable
from app.core.utils import transaction, utcnow
from app.domain.calculator import CalculationError, ProcurementReport, calculate_procurement
from app.domain.money import D, money
from app.models import Dish, Ingredient, Order, OrderItem, PurchasePlan, PurchasePlanItem
from app.schemas.procurement import (PlanCreateIn, PlanOut, PreviewIn, ProcItemOut, ProcurementReportOut, ReceiveIn)
from app.services.calc_inputs import to_dish_info, to_ingredient_info
from app.services.inventory_service import apply_movement


def reserved_by_earlier_plans(db: Session, target: date) -> dict:
    """Резерв: часть потребности более ранних (но не прошедших) утверждённых планов, которую нужно
    закрыть из текущего склада. Каждый план учитывается один раз; план на ту же дату не учитывается."""
    plans = db.scalars(select(PurchasePlan).where(
        PurchasePlan.status.in_(("approved", "received")),
        PurchasePlan.plan_date >= date.today(), PurchasePlan.plan_date < target)).all()
    reserved: dict = defaultdict(lambda: Decimal(0))
    for plan in plans:
        for item in plan.items:
            if plan.status == "received":
                part = item.required_quantity  # закупленное уже на складе
            else:
                part = max(Decimal(0), item.required_quantity - item.purchase_quantity)
            reserved[item.ingredient_id] += part
    return dict(reserved)


def build_report(db: Session, target: date, include_pending: bool, include_demo: bool) -> ProcurementReport:
    statuses = ["confirmed"] + (["pending"] if include_pending else [])
    stmt = (select(OrderItem.dish_id, func.sum(OrderItem.quantity))
            .join(Order, Order.id == OrderItem.order_id)
            .where(Order.order_date == target, Order.status.in_(statuses)).group_by(OrderItem.dish_id))
    if not include_demo:
        stmt = stmt.where(Order.is_demo.is_(False))
    demand = {dish_id: int(total) for dish_id, total in db.execute(stmt).all()}

    dishes = {d.id: to_dish_info(d) for d in db.scalars(select(Dish).where(Dish.id.in_(list(demand)))).all()} if demand else {}
    ing_ids = {ln.ingredient_id for d in dishes.values() for ln in d.recipe}
    ing_rows = db.scalars(select(Ingredient).where(Ingredient.id.in_(list(ing_ids)))).all() if ing_ids else []
    infos = {i.id: to_ingredient_info(i) for i in ing_rows}
    stock = {i.id: i.stock_quantity for i in ing_rows}
    try:
        return calculate_procurement(target, demand, dishes, infos, stock, reserved_by_earlier_plans(db, target))
    except CalculationError as exc:
        raise unprocessable(exc.code, exc.message) from None


def _report_out(report: ProcurementReport) -> ProcurementReportOut:
    return ProcurementReportOut.model_validate(report.to_dict())


def preview(db: Session, payload: PreviewIn) -> ProcurementReportOut:
    """Только чтение: склад и заказы не изменяются."""
    return _report_out(build_report(db, payload.date, payload.include_pending, payload.include_demo))


def plan_to_out(plan: PurchasePlan) -> PlanOut:
    items = [ProcItemOut(
        ingredient_id=i.ingredient_id, ingredient_name=i.ingredient.name, unit=i.unit,
        required_quantity=i.required_quantity, stock_quantity=i.stock_quantity,
        reserved_quantity=i.reserved_quantity, available_quantity=i.available_quantity, net_need=i.net_need,
        package_size=i.package_size, package_count=i.package_count, purchase_quantity=i.purchase_quantity,
        price_per_unit=i.purchase_price, estimated_cost=i.estimated_cost, status=i.status,
        explanation=i.explanation or "") for i in sorted(plan.items, key=lambda x: x.ingredient.name)]
    return PlanOut(id=plan.id, plan_date=plan.plan_date, status=plan.status,
                   total_estimated_cost=plan.total_estimated_cost, total_is_complete=plan.total_is_complete,
                   created_at=plan.created_at, received_at=plan.received_at, items=items)


def get_plan(db: Session, plan_id: int) -> PurchasePlan:
    plan = db.get(PurchasePlan, plan_id)
    if plan is None:
        raise not_found("План закупки", plan_id)
    return plan


def list_plans(db: Session, on_date: Optional[date]) -> list:
    stmt = select(PurchasePlan).order_by(PurchasePlan.id.desc())
    if on_date:
        stmt = stmt.where(PurchasePlan.plan_date == on_date)
    return db.scalars(stmt).all()


def create_plan(db: Session, payload: PlanCreateIn, user_id: Optional[int], header_key: Optional[str] = None) -> tuple:
    key = payload.idempotency_key or header_key
    if key:
        existing = db.scalar(select(PurchasePlan).where(PurchasePlan.idempotency_key == key))
        if existing is not None:
            return existing, False
    active = db.scalar(select(PurchasePlan).where(
        PurchasePlan.plan_date == payload.date, PurchasePlan.status.in_(("approved", "received"))))
    if active is not None:
        raise conflict("plan_exists", "На эту дату уже есть действующий план закупки", {"plan_id": active.id})

    report = build_report(db, payload.date, payload.include_pending, payload.include_demo)
    if not report.items and not report.dishes_requiring_recipe:
        raise unprocessable("no_demand", "На выбранную дату нет подходящих заказов")
    missing = [i.ingredient_name for i in report.items if i.status == "missing_price"]
    no_recipe = [d.dish_name for d in report.dishes_requiring_recipe]
    if (missing or no_recipe) and not payload.allow_incomplete:
        raise unprocessable("incomplete_calculation",
                            "План нельзя утвердить: не хватает цен или рецептур (или передайте allow_incomplete=true)",
                            {"missing_price": missing, "requiring_recipe": no_recipe})
    try:
        with transaction(db):
            plan = PurchasePlan(plan_date=payload.date, status="approved", idempotency_key=key, created_by=user_id,
                                total_estimated_cost=report.total_estimated_cost,
                                total_is_complete=report.total_is_complete)
            for it in report.items:
                plan.items.append(PurchasePlanItem(
                    ingredient_id=it.ingredient_id, unit=it.unit, required_quantity=it.required_quantity,
                    stock_quantity=it.stock_quantity, available_quantity=it.available_quantity,
                    reserved_quantity=it.reserved_quantity, net_need=it.net_need,
                    purchase_quantity=it.purchase_quantity, package_size=it.package_size,
                    package_count=it.package_count, purchase_price=it.price_per_unit,
                    estimated_cost=it.estimated_cost, status=it.status, explanation=it.explanation))
            db.add(plan)
    except IntegrityError:
        replay = db.scalar(select(PurchasePlan).where(PurchasePlan.idempotency_key == key)) if key else None
        if replay is not None:
            return replay, False
        raise conflict("plan_exists", "На эту дату уже есть действующий план закупки") from None
    return plan, True


def cancel_plan(db: Session, plan_id: int) -> tuple:
    plan = get_plan(db, plan_id)
    if plan.status == "cancelled":
        return plan, False
    if plan.status == "received":
        raise conflict("plan_received", "Товары уже приняты на склад — план отменить нельзя")
    with transaction(db):
        plan.status = "cancelled"
    return plan, True


def receive_plan(db: Session, plan_id: int, payload: Optional[ReceiveIn]) -> tuple:
    """Фактическое поступление. Повторный вызов ничего не меняет (склад не увеличивается дважды)."""
    plan = get_plan(db, plan_id)
    if plan.status == "received":
        return plan, False
    if plan.status == "cancelled":
        raise conflict("plan_cancelled", "План отменён — приёмка невозможна")
    overrides: dict = {}
    if payload and payload.items:
        known = {i.ingredient_id for i in plan.items}
        bad = [o.ingredient_id for o in payload.items if o.ingredient_id not in known]
        if bad:
            raise unprocessable("unknown_ingredient", "Ингредиенты отсутствуют в плане", {"ingredient_ids": bad})
        overrides = {o.ingredient_id: D(o.received_quantity) for o in payload.items}
    with transaction(db):
        # атомарный переход approved -> received: выигрывает только один из конкурирующих запросов
        result = db.execute(update(PurchasePlan).where(PurchasePlan.id == plan_id, PurchasePlan.status == "approved")
                            .values(status="received", received_at=utcnow()))
        if result.rowcount == 0:
            applied = False
        else:
            applied = True
            for item in plan.items:
                received = overrides.get(item.ingredient_id, item.purchase_quantity)
                item.received_quantity = received
                if received > 0:
                    ing = db.get(Ingredient, item.ingredient_id)
                    apply_movement(db, ing, "purchase", received, unit_cost=item.purchase_price,
                                   reference_type="purchase_plan", reference_id=plan.id,
                                   reason=f"Поступление по плану закупки #{plan.id}")
    db.refresh(plan)
    return plan, applied
