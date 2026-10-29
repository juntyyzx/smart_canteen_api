from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.schemas.common import Num


class HistoryInfo(BaseModel):
    history_days: int
    min_history_days: int
    insufficient_history: bool
    data_basis: str  # none | real | demo | mixed
    contains_demo_data: bool
    message: Optional[str] = None


class DishPopularity(BaseModel):
    dish_id: int
    dish_name: str
    category: str
    orders: int
    portions: int
    revenue: Num


class CategoryPopularity(BaseModel):
    category: str
    portions: int
    revenue: Num


class WeekdayDemand(BaseModel):
    weekday: int
    weekday_name: str
    days_observed: int
    portions: int
    avg_portions_per_day: Num


class PopularityOut(BaseModel):
    date_from: date
    date_to: date
    currency: str = "KGS"
    history: HistoryInfo
    dishes: list[DishPopularity]
    categories: list[CategoryPopularity]
    weekdays: list[WeekdayDemand]


class WasteByDish(BaseModel):
    dish_id: int
    dish_name: str
    waste_portions: Num
    waste_cost: Num
    prepared_portions: int
    waste_percent: Optional[Num]


class WasteByReason(BaseModel):
    reason: str
    records: int
    cost: Num


class WasteByIngredient(BaseModel):
    ingredient_id: int
    ingredient_name: str
    quantity: Num
    unit: str
    cost: Num


class WasteAnalyticsOut(BaseModel):
    date_from: date
    date_to: date
    currency: str = "KGS"
    contains_demo_data: bool
    total_waste_cost: Num
    cost_is_complete: bool
    total_prepared_portions: int
    total_wasted_portions: Num
    waste_percent_of_prepared: Optional[Num]
    by_dish: list[WasteByDish]
    by_ingredient: list[WasteByIngredient]
    by_reason: list[WasteByReason]


class SummaryOut(BaseModel):
    date_from: date
    date_to: date
    currency: str = "KGS"
    history: HistoryInfo
    orders: int
    portions: int
    revenue: Num
    ingredient_cost_of_sold: Optional[Num]
    gross_difference_over_ingredients: Optional[Num]
    cost_is_complete: bool
    waste_cost: Num
    waste_percent_of_prepared: Optional[Num]
    note: str
