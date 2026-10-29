from typing import Optional

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import idempotency_key, require_roles
from app.database import get_db
from app.models import ROLE_COOK
from app.schemas.common import Envelope, ok
from app.schemas.production import ProductionIn, ProductionOut, WasteIn, WasteOut
from app.services import production_service as svc

router = APIRouter(prefix="/api", tags=["production & waste"])


@router.post("/production", status_code=201, response_model=Envelope[ProductionOut],
             summary="Записать приготовление: списывает продукты по рецептуре, выброшенное попадает в отходы")
def production(payload: ProductionIn, response: Response, db: Session = Depends(get_db),
               key: Optional[str] = Depends(idempotency_key), _=Depends(require_roles(ROLE_COOK))):
    rec, created, waste, consumed = svc.record_production(db, payload, key)
    if not created:
        waste, consumed = svc.describe_production(db, rec)
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return ok(svc.production_to_out(rec, consumed, waste), created=created)


@router.post("/waste", status_code=201, response_model=Envelope[WasteOut],
             summary="Записать отход: готовое блюдо (порции) или сырой ингредиент (списывается со склада)")
def waste(payload: WasteIn, response: Response, db: Session = Depends(get_db),
          key: Optional[str] = Depends(idempotency_key), _=Depends(require_roles(ROLE_COOK))):
    rec, created = svc.record_waste(db, payload, key)
    if not created:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return ok(svc.waste_to_out(rec), created=created)
