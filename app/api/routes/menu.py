from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import STAFF, require_roles
from app.database import get_db
from app.models import ROLE_COOK, ROLE_ECONOMIST
from app.schemas.common import Envelope, ok
from app.schemas.menu import (CategoryOut, DishCostingOut, DishCreate, DishOut, DishPatch, RecipeIn, RecipeOut)
from app.services import menu_service

router = APIRouter(prefix="/api", tags=["menu"])


@router.get("/categories", response_model=Envelope[list[CategoryOut]])
def categories(db: Session = Depends(get_db)):
    data = menu_service.list_categories(db)
    return ok(data, count=len(data))


@router.get("/menu", response_model=Envelope[list[DishOut]])
def menu(category: Optional[str] = Query(None, description="slug категории, напр. hot-dishes"),
         available: Optional[bool] = Query(None), product_type: Optional[str] = Query(None),
         q: Optional[str] = Query(None, max_length=100, description="Поиск по названию"),
         db: Session = Depends(get_db)):
    data = menu_service.list_menu(db, category, available, product_type, q)
    return ok(data, count=len(data))


@router.get("/menu/{dish_id}", response_model=Envelope[DishOut])
def menu_item(dish_id: int, db: Session = Depends(get_db)):
    return ok(menu_service.dish_to_out(menu_service.get_dish(db, dish_id)))


@router.post("/dishes", status_code=201, response_model=Envelope[DishOut])
def create_dish(payload: DishCreate, db: Session = Depends(get_db), _=Depends(require_roles())):
    return ok(menu_service.dish_to_out(menu_service.create_dish(db, payload)))


@router.patch("/dishes/{dish_id}", response_model=Envelope[DishOut])
def patch_dish(dish_id: int, payload: DishPatch, db: Session = Depends(get_db),
               _=Depends(require_roles(ROLE_ECONOMIST))):
    return ok(menu_service.dish_to_out(menu_service.patch_dish(db, dish_id, payload)))


@router.get("/dishes/{dish_id}/recipe", response_model=Envelope[RecipeOut])
def get_recipe(dish_id: int, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(menu_service.recipe_out(db, menu_service.get_dish(db, dish_id)))


@router.put("/dishes/{dish_id}/recipe", response_model=Envelope[RecipeOut])
def put_recipe(dish_id: int, payload: RecipeIn, db: Session = Depends(get_db), _=Depends(require_roles(ROLE_COOK))):
    return ok(menu_service.set_recipe(db, dish_id, payload))


@router.get("/dishes/{dish_id}/costing", response_model=Envelope[DishCostingOut])
def costing(dish_id: int, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return ok(menu_service.dish_costing(db, dish_id))
