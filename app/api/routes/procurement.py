from datetime import date
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import STAFF, idempotency_key, require_roles
from app.database import get_db
from app.models import ROLE_COOK, ROLE_ECONOMIST, User
from app.schemas.common import Envelope, ok
from app.schemas.procurement import PlanCreateIn, PlanOut, PreviewIn, ProcurementReportOut, ReceiveIn
from app.services import procurement_service as svc

router = APIRouter(prefix="/api/procurement-plan", tags=["procurement"])


@router.post("/preview", response_model=Envelope[ProcurementReportOut],
             summary="Предварительный расчёт закупки (склад и заказы не изменяются)")
def preview(payload: PreviewIn, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(svc.preview(db, payload), kind="preview")


@router.post("", status_code=201, response_model=Envelope[PlanOut], summary="Утвердить план закупки")
def create_plan(payload: PlanCreateIn, response: Response, db: Session = Depends(get_db),
                key: Optional[str] = Depends(idempotency_key), user: User = Depends(require_roles(ROLE_ECONOMIST))):
    plan, created = svc.create_plan(db, payload, user.id, key)
    if not created:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return ok(svc.plan_to_out(plan), created=created)


@router.get("", response_model=Envelope[list[PlanOut]])
def list_plans(on_date: Optional[date] = Query(None, alias="date"), db: Session = Depends(get_db),
               _=Depends(require_roles(*STAFF))):
    data = [svc.plan_to_out(p) for p in svc.list_plans(db, on_date)]
    return ok(data, count=len(data))


@router.get("/{plan_id}", response_model=Envelope[PlanOut])
def get_plan(plan_id: int, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(svc.plan_to_out(svc.get_plan(db, plan_id)))


@router.post("/{plan_id}/receive", response_model=Envelope[PlanOut],
             summary="Зарегистрировать поступление товаров по плану (повтор безопасен)")
def receive(plan_id: int, payload: Optional[ReceiveIn] = Body(default=None), db: Session = Depends(get_db),
            _=Depends(require_roles(ROLE_COOK))):
    plan, applied = svc.receive_plan(db, plan_id, payload)
    return ok(svc.plan_to_out(plan), stock_updated=applied)


@router.patch("/{plan_id}/cancel", response_model=Envelope[PlanOut])
def cancel(plan_id: int, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_ECONOMIST))):
    plan, changed = svc.cancel_plan(db, plan_id)
    return ok(svc.plan_to_out(plan), changed=changed)
