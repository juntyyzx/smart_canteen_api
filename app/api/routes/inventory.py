from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import STAFF, idempotency_key, require_roles
from app.database import get_db
from app.models import ROLE_COOK, ROLE_ECONOMIST
from app.schemas.common import Envelope, ok
from app.schemas.inventory import (AdjustmentIn, IngredientCreate, IngredientOut, IngredientPatch, MovementOut,
                                   StockSetIn)
from app.services import inventory_service as svc

router = APIRouter(prefix="/api", tags=["ingredients & inventory"])


@router.get("/ingredients", response_model=Envelope[list[IngredientOut]])
def list_ingredients(active: Optional[bool] = Query(None), q: Optional[str] = Query(None, max_length=100),
                     db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    data = [svc.ingredient_to_out(i) for i in svc.list_ingredients(db, active, q)]
    return ok(data, count=len(data))


@router.post("/ingredients", status_code=201, response_model=Envelope[IngredientOut])
def create_ingredient(payload: IngredientCreate, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_ECONOMIST))):
    return ok(svc.ingredient_to_out(svc.create_ingredient(db, payload)))


@router.patch("/ingredients/{ingredient_id}", response_model=Envelope[IngredientOut],
              summary="Изменить ингредиент (остаток здесь менять нельзя)")
def patch_ingredient(ingredient_id: int, payload: IngredientPatch, db: Session = Depends(get_db),
                     _=Depends(require_roles(ROLE_ECONOMIST))):
    return ok(svc.ingredient_to_out(svc.patch_ingredient(db, ingredient_id, payload)))


@router.get("/inventory", response_model=Envelope[list[IngredientOut]], summary="Складские остатки")
def inventory(only_below_minimum: bool = Query(False), db: Session = Depends(get_db),
              _=Depends(require_roles(*STAFF))):
    data = [svc.ingredient_to_out(i) for i in svc.list_ingredients(db, active=True)]
    if only_below_minimum:
        data = [d for d in data if d.below_minimum]
    return ok(data, count=len(data))


@router.post("/inventory/adjustments", status_code=201, response_model=Envelope[MovementOut],
             summary="Корректировка остатка (причина обязательна)")
def adjustment(payload: AdjustmentIn, response: Response, db: Session = Depends(get_db),
               key: Optional[str] = Depends(idempotency_key), _=Depends(require_roles(ROLE_COOK))):
    movement, created = svc.adjust(db, payload, key)
    if not created:
        response.status_code = 200
        response.headers["Idempotent-Replay"] = "true"
    return ok(svc.movement_to_out(movement), created=created)


@router.put("/inventory/stock", response_model=Envelope[list[IngredientOut]],
            summary="Ввести фактические остатки склада (повар)")
def set_stock(payload: StockSetIn, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_COOK))):
    data = [svc.ingredient_to_out(i) for i in svc.set_stock(db, payload)]
    return ok(data, count=len(data))


@router.get("/inventory/movements", response_model=Envelope[list[MovementOut]])
def movements(ingredient_id: Optional[int] = Query(None),
              movement_type: Optional[str] = Query(None, pattern="^(purchase|consumption|waste|adjustment|return)$"),
              date_from: Optional[date] = Query(None, alias="from"), date_to: Optional[date] = Query(None, alias="to"),
              limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    data = [svc.movement_to_out(m) for m in svc.list_movements(db, ingredient_id, movement_type, date_from, date_to, limit, offset)]
    return ok(data, count=len(data))
