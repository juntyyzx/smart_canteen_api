"""Тесты расчётного ядра. Не требуют БД и FastAPI."""
from datetime import date
from decimal import Decimal as Dc

from app.domain.calculator import (
    CalculationError,
    DishInfo,
    IngredientInfo,
    RecipeLine,
    calculate_procurement,
    dish_unit_cost,
)
from app.domain.money import fmt, money
from app.domain.units import UnitError, convert, price_per_base_unit

DAY = date(2026, 11, 2)

# Ингредиенты: цена за 1 базовую единицу (g / ml)
RICE = IngredientInfo(1, "Рис", "g", Dc("0.095"), Dc("5000"))       # 95 KGS/kg, упаковка 5 кг
BEEF = IngredientInfo(2, "Говядина", "g", Dc("0.52"), Dc("1000"))   # 520 KGS/kg, упаковка 1 кг
CARROT = IngredientInfo(3, "Морковь", "g", Dc("0.035"), Dc("5000"))
ONION = IngredientInfo(4, "Лук", "g", Dc("0.03"), Dc("5000"))
OIL = IngredientInfo(5, "Масло", "ml", Dc("0.14"), Dc("5000"))
CHICKEN = IngredientInfo(6, "Курица", "g", Dc("0.33"), Dc("1000"))

PLOV = DishInfo(1, "Плов", (
    RecipeLine(1, Dc(100)), RecipeLine(2, Dc(100)), RecipeLine(3, Dc(60)),
    RecipeLine(4, Dc(20)), RecipeLine(5, Dc(15)),
))
CHICKEN_RICE = DishInfo(2, "Курица с рисом", (
    RecipeLine(6, Dc(120)), RecipeLine(1, Dc(90)), RecipeLine(5, Dc(10)),
))
NO_RECIPE = DishInfo(3, "Новое блюдо", ())

DISHES = {d.id: d for d in (PLOV, CHICKEN_RICE, NO_RECIPE)}
INGS = {i.id: i for i in (RICE, BEEF, CARROT, ONION, OIL, CHICKEN)}


def _item(report, ingredient_id):
    return next(it for it in report.items if it.ingredient_id == ingredient_id)


def test_120_portions_of_plov_empty_stock():
    r = calculate_procurement(DAY, {1: 120}, DISHES, INGS, stock={})
    assert _item(r, 1).required_quantity == Dc("12000")   # рис 120 × 100 г
    assert _item(r, 2).required_quantity == Dc("12000")   # мясо
    assert _item(r, 3).required_quantity == Dc("7200")    # морковь 120 × 60
    assert _item(r, 4).required_quantity == Dc("2400")    # лук
    assert _item(r, 5).required_quantity == Dc("1800")    # масло 120 × 15 мл
    assert r.total_portions == 120


def test_package_rounding_up_and_cost():
    r = calculate_procurement(DAY, {1: 120}, DISHES, INGS, stock={})
    rice = _item(r, 1)
    assert rice.package_count == 3            # ceil(12000 / 5000)
    assert rice.purchase_quantity == Dc("15000")
    assert rice.estimated_cost == money("1425.00")   # 15000 × 0.095
    beef = _item(r, 2)
    assert beef.package_count == 12 and beef.purchase_quantity == Dc("12000")
    assert beef.estimated_cost == money("6240.00")   # 12000 × 0.52


def test_same_ingredient_summed_across_dishes():
    r = calculate_procurement(DAY, {1: 10, 2: 20}, DISHES, INGS, stock={})
    rice = _item(r, 1)
    assert rice.required_quantity == Dc("2800")       # 10×100 + 20×90
    assert {b.dish_id for b in rice.breakdown} == {1, 2}
    assert _item(r, 5).required_quantity == Dc("350")  # 10×15 + 20×10


def test_stock_is_subtracted():
    r = calculate_procurement(DAY, {1: 120}, DISHES, INGS, stock={1: Dc("4000")})
    rice = _item(r, 1)
    assert rice.available_quantity == Dc("4000")
    assert rice.net_need == Dc("8000")
    assert rice.package_count == 2 and rice.purchase_quantity == Dc("10000")


def test_zero_purchase_when_stock_is_enough():
    r = calculate_procurement(DAY, {1: 10}, DISHES, INGS, stock={1: Dc("5000"), 2: Dc("5000"), 3: Dc("5000"), 4: Dc("5000"), 5: Dc("5000")})
    for it in r.items:
        assert it.net_need == 0
        assert it.purchase_quantity == 0
        assert it.estimated_cost == money(0)
        assert it.status == "sufficient_stock"
    assert r.total_estimated_cost == money(0)
    assert r.total_is_complete is True


def test_reserved_is_subtracted_exactly_once():
    # на складе 6000, из них 5000 зарезервировано -> доступно 1000, нужно 12000
    r = calculate_procurement(DAY, {1: 120}, DISHES, INGS, stock={1: Dc("6000")}, reserved={1: Dc("5000")})
    rice = _item(r, 1)
    assert rice.available_quantity == Dc("1000")
    assert rice.net_need == Dc("11000")


def test_reserved_cannot_make_available_negative():
    r = calculate_procurement(DAY, {1: 1}, DISHES, INGS, stock={1: Dc("100")}, reserved={1: Dc("900")})
    assert _item(r, 1).available_quantity == 0
    assert _item(r, 1).net_need == Dc("100")


def test_missing_price_is_reported_not_zero():
    ings = dict(INGS)
    ings[2] = IngredientInfo(2, "Говядина", "g", None, Dc("1000"))
    r = calculate_procurement(DAY, {1: 120}, DISHES, ings, stock={})
    beef = _item(r, 2)
    assert beef.status == "missing_price"
    assert beef.estimated_cost is None
    assert r.total_is_complete is False
    assert any("missing_price" in w for w in r.warnings)
    # итог не включает неизвестную стоимость и не выдаётся за достоверный
    assert r.total_estimated_cost == sum((it.estimated_cost for it in r.items if it.estimated_cost is not None), Dc(0))


def test_missing_price_not_needed_when_stock_covers():
    ings = dict(INGS)
    ings[2] = IngredientInfo(2, "Говядина", "g", None, Dc("1000"))
    r = calculate_procurement(DAY, {1: 10}, DISHES, ings, stock={2: Dc("5000")})
    assert _item(r, 2).status == "sufficient_stock"


def test_dish_without_recipe_is_flagged_and_excluded():
    r = calculate_procurement(DAY, {1: 10, 3: 7}, DISHES, INGS, stock={})
    assert [d.dish_id for d in r.dishes_requiring_recipe] == [3]
    assert r.dishes_requiring_recipe[0].status == "requiring_recipe"
    assert r.total_is_complete is False
    assert _item(r, 1).required_quantity == Dc("1000")  # 7 порций без рецепта не добавили ничего
    assert any("рецептур" in w for w in r.warnings)


def test_negative_quantity_rejected():
    for bad in (-1,):
        try:
            calculate_procurement(DAY, {1: bad}, DISHES, INGS, stock={})
        except CalculationError as e:
            assert e.code == "invalid_portions"
        else:
            raise AssertionError("ожидалась ошибка")
    bad_dish = DishInfo(9, "Плохое", (RecipeLine(1, Dc("-5")),))
    try:
        calculate_procurement(DAY, {9: 1}, {9: bad_dish}, INGS, stock={})
    except CalculationError as e:
        assert e.code == "invalid_quantity"
    else:
        raise AssertionError("ожидалась ошибка")


def test_invalid_yield_factor_and_package_rejected():
    for y in (Dc("0"), Dc("1.2"), Dc("-0.5")):
        d = DishInfo(9, "X", (RecipeLine(1, Dc(100), yield_factor=y),))
        try:
            calculate_procurement(DAY, {9: 1}, {9: d}, INGS, stock={})
        except CalculationError as e:
            assert e.code == "invalid_yield_factor"
        else:
            raise AssertionError("ожидалась ошибка yield_factor")
    zero_pkg = {1: IngredientInfo(1, "Рис", "g", Dc("0.1"), Dc("0"))}
    try:
        calculate_procurement(DAY, {1: 1}, {1: DishInfo(1, "P", (RecipeLine(1, Dc(10)),))}, zero_pkg, stock={})
    except CalculationError as e:
        assert e.code == "invalid_package_size"   # защита от деления на ноль
    else:
        raise AssertionError("ожидалась ошибка package_size")


def test_yield_factor_applied_only_when_explicit():
    d = DishInfo(9, "Картофель", (RecipeLine(1, Dc(80), yield_factor=Dc("0.8")),))
    r = calculate_procurement(DAY, {9: 10}, {9: d}, INGS, stock={})
    assert _item(r, 1).required_quantity == Dc("1000")   # 80 / 0.8 = 100 г брутто × 10
    r2 = calculate_procurement(DAY, {1: 10}, DISHES, INGS, stock={})
    assert _item(r2, 1).required_quantity == Dc("1000")  # без выхода — как в рецепте


def test_optional_lines_excluded_by_default():
    d = DishInfo(9, "Чай", (RecipeLine(1, Dc(2)), RecipeLine(2, Dc(10), is_optional=True)))
    r = calculate_procurement(DAY, {9: 10}, {9: d}, INGS, stock={})
    assert [it.ingredient_id for it in r.items] == [1]
    r2 = calculate_procurement(DAY, {9: 10}, {9: d}, INGS, stock={}, include_optional=True)
    assert {it.ingredient_id for it in r2.items} == {1, 2}


def test_no_package_means_purchase_equals_net_need():
    ings = {1: IngredientInfo(1, "Рис", "g", Dc("0.1"), None)}
    d = DishInfo(1, "P", (RecipeLine(1, Dc(100)),))
    r = calculate_procurement(DAY, {1: 3}, {1: d}, ings, stock={})
    it = r.items[0]
    assert it.package_count is None and it.purchase_quantity == Dc("300")
    assert it.estimated_cost == money("30.00")


def test_exact_multiple_of_package_does_not_add_extra_package():
    ings = {1: IngredientInfo(1, "Рис", "g", Dc("0.1"), Dc("1000"))}
    d = DishInfo(1, "P", (RecipeLine(1, Dc(100)),))
    r = calculate_procurement(DAY, {1: 10}, {1: d}, ings, stock={})
    assert r.items[0].package_count == 1   # ровно 1000 г -> одна упаковка, не две


def test_money_rounding_half_up_and_exactness():
    assert money("1.005") == Dc("1.01")
    assert money("2.675") == Dc("2.68")      # float дал бы 2.67
    assert money("0.1") + money("0.2") == money("0.3")
    assert fmt(Dc("12000.000")) == "12000"
    assert fmt(Dc("0.095")) == "0.095"


def test_unit_conversion_rules():
    assert convert(Dc("1.5"), "kg", "g") == Dc("1500")
    assert convert(Dc("2"), "l", "ml") == Dc("2000")
    assert price_per_base_unit(Dc("95"), "kg", "g") == Dc("0.095")
    for a, b in (("g", "ml"), ("ml", "g"), ("kg", "pcs"), ("g", "package")):
        try:
            convert(Dc(1), a, b)
        except UnitError:
            pass
        else:
            raise AssertionError(f"{a}->{b} не должно конвертироваться")


def test_dish_unit_cost_and_missing_price():
    cost, missing = dish_unit_cost(PLOV, INGS)
    # 100×0.095 + 100×0.52 + 60×0.035 + 20×0.03 + 15×0.14 = 9.5 + 52 + 2.1 + 0.6 + 2.1
    assert cost == Dc("66.3") and missing == []
    ings = dict(INGS)
    ings[3] = IngredientInfo(3, "Морковь", "g", None, None)
    cost2, missing2 = dish_unit_cost(PLOV, ings)
    assert missing2 == [3]
    assert cost2 == Dc("64.2")


def test_explanation_mentions_numbers():
    r = calculate_procurement(DAY, {1: 120}, DISHES, INGS, stock={1: Dc("4000")})
    text = _item(r, 1).explanation
    assert "12000" in text and "4000" in text and "8000" in text and "2 уп." in text
