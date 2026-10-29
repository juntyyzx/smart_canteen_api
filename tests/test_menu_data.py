"""Проверка встроенного меню (без БД): состав, рецепты, ссылки на ингредиенты, цены."""
from decimal import Decimal as Dc

from app.domain.calculator import DishInfo, IngredientInfo, RecipeLine, dish_unit_cost
from app.domain.units import STOCK_UNITS, convert, price_per_base_unit
from app.seed.menu_data import CATEGORIES, DISHES, INGREDIENTS

EXPECTED = {
    "hot-dishes": ["Плов", "Курица с рисом", "Лагман", "Макароны с курицей", "Куриная котлета", "Говяжья котлета",
                   "Курица с картофелем", "Пельмени", "Манты", "Гречка с курицей", "Жаркое с мясом и картофелем",
                   "Омлет", "Овощное рагу"],
    "soups": ["Куриный суп с лапшой", "Борщ", "Шорпо", "Чечевичный суп", "Овощной суп", "Молочный суп с макаронами"],
    "sides": ["Картофельное пюре", "Запечённый картофель", "Рис", "Гречка", "Макароны", "Овощи на пару", "Тушёная капуста"],
    "salads": ["Овощной салат", "Салат из капусты и моркови", "Салат из огурцов и помидоров", "Винегрет", "Салат с курицей"],
    "bakery-snacks": ["Самса с мясом", "Самса с картофелем", "Пирожок с картофелем", "Пирожок с мясом", "Сосиска в тесте",
                      "Сэндвич с курицей", "Тост с сыром", "Пицца порционная", "Блины", "Лепёшка"],
    "desserts-sweets": ["Медовик", "Наполеон", "Бисквитный торт порционный", "Кекс", "Печенье", "Вафли", "Пончик",
                        "Чизкейк порционный", "Мороженое", "Шоколадный батончик", "Конфеты", "Мармелад", "Зефир",
                        "Халва", "Сухофрукты"],
    "hot-drinks": ["Чёрный чай", "Зелёный чай", "Чай с лимоном", "Чай с молоком", "Чай с мятой", "Имбирный чай",
                   "Кофе американо", "Кофе с молоком", "Какао", "Горячий шоколад"],
    "cold-drinks": ["Компот", "Морс", "Лимонад домашний", "Минеральная вода", "Питьевая вода", "Сок в упаковке",
                    "Яблочный сок", "Апельсиновый сок", "Холодный чай", "Айран"],
    "sauces-extras": ["Кетчуп", "Майонез", "Сметанный соус", "Чесночный соус", "Сырный соус", "Томатный соус", "Горчица",
                      "Сливочное масло", "Сметана", "Сыр", "Хлеб", "Лепёшка", "Лимон", "Сахар", "Молоко для чая и кофе"],
    "extra-items": ["Яйцо варёное", "Йогурт", "Творожный десерт", "Орехи", "Фрукты сезонные", "Яблоко", "Банан", "Груша"],
}
PRODUCT_TYPES = {"prepared_dish", "beverage", "dessert", "snack", "sauce", "extra"}


def _parse(recipe):
    out = []
    for part in recipe.split(","):
        optional = part.endswith("?")
        slug, q = part.rstrip("?").split(":")
        out.append((slug, Dc(q), optional))
    return out


def test_all_categories_present():
    assert [c[0] for c in CATEGORIES] == list(EXPECTED)


def test_all_declared_items_present_in_each_category():
    for cat, names in EXPECTED.items():
        have = [d["name"] for d in DISHES if d["category"] == cat]
        for expected_name in names:
            assert any(h == expected_name or h.startswith(expected_name + " —") or h.startswith(expected_name + " ")
                       for h in have), f"{cat}: нет позиции «{expected_name}»"


def test_unique_slugs_and_valid_fields():
    slugs = [d["slug"] for d in DISHES]
    assert len(slugs) == len(set(slugs))
    ing_slugs = [i["slug"] for i in INGREDIENTS]
    assert len(ing_slugs) == len(set(ing_slugs))
    cats = {c[0] for c in CATEGORIES}
    for d in DISHES:
        assert d["category"] in cats, d["slug"]
        assert d["product_type"] in PRODUCT_TYPES, d["slug"]
        assert d["price"] >= 0 and d["serving_size"] > 0, d["slug"]
        assert d["serving_unit"] in ("g", "ml", "l", "pcs"), d["slug"]


def test_every_recipe_references_known_ingredients_with_positive_quantities():
    ing = {i["slug"]: i for i in INGREDIENTS}
    for d in DISHES:
        lines = _parse(d["recipe"])
        assert lines, f"{d['slug']}: пустая рецептура"
        assert len({s for s, _, _ in lines}) == len(lines), f"{d['slug']}: дубли ингредиентов"
        assert any(not opt for _, _, opt in lines), f"{d['slug']}: все строки необязательные"
        for slug, q, _ in lines:
            assert slug in ing, f"{d['slug']}: неизвестный ингредиент {slug}"
            assert q > 0


def test_ingredient_units_prices_and_packages_are_consistent():
    for i in INGREDIENTS:
        assert i["unit"] in STOCK_UNITS, i["slug"]
        assert i["price"] > 0 and i["package_size"] > 0 and i["stock"] >= 0
        convert(Dc(1), i["price_unit"], i["unit"])      # не бросает -> единицы совместимы
        convert(Dc(1), i["package_unit"], i["unit"])


def test_purchased_dishes_link_to_single_ingredient_and_prepared_have_no_unknown_composition():
    for d in DISHES:
        lines = _parse(d["recipe"])
        if d["sourcing"] == "purchased":
            assert len(lines) == 1, d["slug"]
        else:
            for slug, _, _ in lines:
                src = next(i for i in INGREDIENTS if i["slug"] == slug)
                # собственное приготовление использует только сырьё с известным составом (кроме хлеба)
                assert not (src["is_purchased_product"] and slug != "bread"), f"{d['slug']} использует готовый товар {slug}"


def test_unit_cost_is_computable_and_gross_difference_is_positive():
    infos = {}
    for n, i in enumerate(INGREDIENTS, start=1):
        infos[i["slug"]] = IngredientInfo(n, i["name"], i["unit"], price_per_base_unit(i["price"], i["price_unit"], i["unit"]),
                                          convert(i["package_size"], i["package_unit"], i["unit"]))
    by_id = {v.id: v for v in infos.values()}
    bad = []
    for d in DISHES:
        recipe = tuple(RecipeLine(infos[s].id, q, None, opt) for s, q, opt in _parse(d["recipe"]))
        cost, missing = dish_unit_cost(DishInfo(1, d["name"], recipe), by_id)
        assert not missing
        if cost >= d["price"]:
            bad.append((d["slug"], str(cost), str(d["price"])))
    assert not bad, f"Цена продажи не выше себестоимости ингредиентов: {bad}"


def test_plov_matches_documented_demo_recipe():
    plov = next(d for d in DISHES if d["slug"] == "plov")
    lines = {s: q for s, q, _ in _parse(plov["recipe"])}
    assert lines["rice"] == 100 and lines["beef"] == 100 and lines["carrot"] == 60
    assert lines["onion"] == 20 and lines["oil"] == 15
