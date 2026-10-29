from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import STAFF, get_settings, idempotency_key, require_roles
from app.core.config import Settings
from app.database import get_db
from app.models import ROLE_COOK
from app.schemas.common import Envelope, ok
from app.schemas.orders import OrderCreate, OrderOut, OrderSummaryOut, OrderTrackOut
from app.services import order_service as svc

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", status_code=201, response_model=Envelope[OrderOut],
             summary="Создать заказ (публичный; поддерживает Idempotency-Key)")
def create_order(payload: OrderCreate, response: Response, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings), key: Optional[str] = Depends(idempotency_key)):
    order, created = svc.create_order(db, payload, settings, key)
    if not created:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return ok(svc.order_to_out(order), created=created)


@router.get("", response_model=Envelope[list[OrderOut]])
def list_orders(on_date: Optional[date] = Query(None, alias="date"), status: Optional[str] = Query(
                None, pattern="^(pending|confirmed|cancelled|completed)$"),
                limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    data = [svc.order_to_out(o) for o in svc.list_orders(db, on_date, status, limit, offset)]
    return ok(data, count=len(data))


@router.get("/summary", response_model=Envelope[OrderSummaryOut])
def summary(on_date: date = Query(..., alias="date"), db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(svc.summary(db, on_date))


@router.get("/track/{public_order_number}", response_model=Envelope[OrderTrackOut],
            summary="Публичное подтверждение заказа по номеру (без персональных данных)")
def track(public_order_number: str, db: Session = Depends(get_db)):
    return ok(svc.order_to_track(svc.get_order_by_number(db, public_order_number)))


@router.get("/{order_id}", response_model=Envelope[OrderOut])
def get_order(order_id: int, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(svc.order_to_out(svc.get_order(db, order_id)))


@router.patch("/{order_id}/cancel", response_model=Envelope[OrderOut], summary="Отменить заказ (идемпотентно)")
def cancel(order_id: int, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_COOK))):
    order, changed = svc.cancel_order(db, order_id)
    return ok(svc.order_to_out(order), changed=changed)


@router.patch("/{order_id}/confirm", response_model=Envelope[OrderOut])
def confirm(order_id: int, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_COOK))):
    order, changed = svc.confirm_order(db, order_id)
    return ok(svc.order_to_out(order), changed=changed)


@router.patch("/{order_id}/complete", response_model=Envelope[OrderOut])
def complete(order_id: int, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_COOK))):
    order, changed = svc.complete_order(db, order_id)
    return ok(svc.order_to_out(order), changed=changed)
