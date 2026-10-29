from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import STAFF, get_settings, require_roles
from app.core.config import Settings
from app.database import get_db
from app.schemas.analytics import PopularityOut, SummaryOut, WasteAnalyticsOut
from app.schemas.common import Envelope, ok
from app.services import analytics_service as svc

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

_DEMO = Query(False, description="Включить демонстрационные данные (is_demo). По умолчанию — только реальные.")


@router.get("/popularity", response_model=Envelope[PopularityOut])
def popularity(date_from: date = Query(..., alias="from"), date_to: date = Query(..., alias="to"),
               include_demo: bool = _DEMO, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
               _=Depends(require_roles(*STAFF))):
    return ok(svc.popularity(db, settings, date_from, date_to, include_demo))


@router.get("/waste", response_model=Envelope[WasteAnalyticsOut])
def waste(date_from: date = Query(..., alias="from"), date_to: date = Query(..., alias="to"),
          include_demo: bool = _DEMO, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(svc.waste_analytics(db, date_from, date_to, include_demo))


@router.get("/summary", response_model=Envelope[SummaryOut])
def summary(date_from: date = Query(..., alias="from"), date_to: date = Query(..., alias="to"),
            include_demo: bool = _DEMO, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
            _=Depends(require_roles(*STAFF))):
    return ok(svc.summary(db, settings, date_from, date_to, include_demo))
