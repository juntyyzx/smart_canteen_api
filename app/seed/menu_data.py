"""Встроенное ДЕМОНСТРАЦИОННОЕ меню.

ВАЖНО: массы порций и рецептуры ниже — условные, не утверждённые нормы питания.
Закупочные цены (KGS) ориентированы на розничные цены в Кыргызстане/Бишкеке (мониторинг
Антимонопольной службы КР, август–октябрь 2026; рис, говядина, овощи, мука, масло, сахар, яйца, молоко,
макароны, сливочное масло — по официальным данным, остальное — оценка). Цены продажи — от себестоимости
по рецептуре с наценкой (~1,5–1,8×), округление до 5 сомов. Это ориентиры, не реальный прайс столовой:
меняйте цены через API (PATCH /api/ingredients, /api/dishes).

Единицы количества в рецептах — базовые единицы ингредиента (g, ml, pcs).
Формат рецепта: "ингредиент:количество[?]" через запятую; "?" — необязательный ингредиент.
"""
from decimal import Decimal

CATEGORIES = [
    # (slug, name, description, display_order)
    ("hot-dishes", "Горячие блюда", "Основные горячие блюда", 1),
    ("soups", "Супы", "Первые блюда", 2),
    ("sides", "Гарниры", "Гарниры к горячим блюдам", 3),
    ("salads", "Салаты", "Холодные закуски и салаты", 4),
    ("bakery-snacks", "Выпечка и перекусы", "Выпечка, сэндвичи, перекусы", 5),
    ("desserts-sweets", "Десерты и сладости", "Десерты, сладости, конфеты", 6),
    ("hot-drinks", "Чай и горячие напитки", "Чай, кофе, какао", 7),
    ("cold-drinks", "Холодные напитки", "Компоты, соки, вода", 8),
    ("sauces-extras", "Соусы и дополнения", "Соусы и дополнительные порции", 9),
    ("extra-items", "Дополнительные товары", "Яйца, йогурты, орехи, фрукты", 10),
]


def _I(slug, name, unit, price, price_unit, pkg, pkg_unit, stock, minimum,
       shelf=None, allergens="", meat=False, purchased=False):
    return {
        "slug": slug, "name": name, "unit": unit,
        "price": Decimal(str(price)), "price_unit": price_unit,
        "package_size": Decimal(str(pkg)), "package_unit": pkg_unit,
        "stock": Decimal(str(stock)), "minimum": Decimal(str(minimum)),
        "shelf_life_days": shelf, "is_perishable": shelf is not None,
        "allergens": allergens, "contains_meat": meat, "is_purchased_product": purchased,
    }


# slug, название, база, цена, ед. цены, упаковка, ед. упаковки, остаток, мин. остаток, срок годности (дн.), аллергены
INGREDIENTS = [
    # --- сырьё для кухни собственного приготовления ---
    _I("rice", "Рис", "g", 150, "kg", 5, "kg", 20000, 5000),
    _I("beef", "Говядина", "g", 800, "kg", 1, "kg", 8000, 3000, shelf=3, meat=True),
    _I("chicken", "Курица", "g", 380, "kg", 1, "kg", 10000, 3000, shelf=2, meat=True),
    _I("carrot", "Морковь", "g", 45, "kg", 5, "kg", 10000, 3000, shelf=30),
    _I("onion", "Лук репчатый", "g", 40, "kg", 5, "kg", 8000, 2000, shelf=30),
    _I("potato", "Картофель", "g", 38, "kg", 10, "kg", 30000, 8000, shelf=30),
    _I("oil", "Масло растительное", "ml", 172, "l", 5, "l", 10000, 2000),
    _I("salt", "Соль", "g", 25, "kg", 1, "kg", 5000, 500),
    _I("spices", "Специи", "g", 600, "kg", 500, "g", 1000, 200),
    _I("lagman_noodles", "Лапша для лагмана", "g", 140, "kg", 1, "kg", 4000, 1000, allergens="gluten,egg"),
    _I("pasta", "Макароны", "g", 80, "kg", 5, "kg", 12000, 3000, allergens="gluten"),
    _I("buckwheat", "Гречка", "g", 120, "kg", 5, "kg", 15000, 3000),
    _I("flour", "Мука пшеничная", "g", 45, "kg", 10, "kg", 25000, 5000, allergens="gluten"),
    _I("egg", "Яйцо куриное", "pcs", 11, "pcs", 30, "pcs", 90, 30, shelf=14, allergens="egg"),
    _I("milk", "Молоко", "ml", 80, "l", 1, "l", 15000, 3000, shelf=5, allergens="milk"),
    _I("cabbage", "Капуста", "g", 30, "kg", 5, "kg", 10000, 2000, shelf=20),
    _I("tomato", "Помидоры", "g", 90, "kg", 1, "kg", 4000, 1000, shelf=5),
    _I("cucumber", "Огурцы", "g", 80, "kg", 1, "kg", 3000, 1000, shelf=5),
    _I("beet", "Свёкла", "g", 35, "kg", 5, "kg", 6000, 1000, shelf=30),
    _I("lentil", "Чечевица", "g", 150, "kg", 1, "kg", 3000, 500),
    _I("tomato_paste", "Томатная паста", "g", 250, "kg", 1, "kg", 2000, 500),
    _I("sugar", "Сахар", "g", 80, "kg", 5, "kg", 10000, 2000),
    _I("butter", "Масло сливочное", "g", 600, "kg", 200, "g", 2000, 400, shelf=30, allergens="milk"),
    _I("sour_cream", "Сметана", "g", 300, "kg", 1, "kg", 3000, 800, shelf=7, allergens="milk"),
    _I("cheese", "Сыр", "g", 710, "kg", 1, "kg", 3000, 800, shelf=30, allergens="milk"),
    _I("black_tea", "Чай чёрный", "g", 700, "kg", 500, "g", 1500, 300),
    _I("green_tea", "Чай зелёный", "g", 800, "kg", 500, "g", 1000, 300),
    _I("mint", "Мята", "g", 1200, "kg", 100, "g", 300, 50, shelf=5),
    _I("ginger", "Имбирь", "g", 450, "kg", 1, "kg", 800, 200, shelf=14),
    _I("lemon", "Лимон", "g", 200, "kg", 1, "kg", 2000, 500, shelf=14),
    _I("honey", "Мёд", "g", 900, "kg", 1, "kg", 1000, 200),
    _I("coffee", "Кофе молотый", "g", 1800, "kg", 1, "kg", 1500, 300),
    _I("cocoa", "Какао-порошок", "g", 900, "kg", 500, "g", 1000, 200),
    _I("chocolate", "Шоколад тёмный", "g", 1000, "kg", 1, "kg", 1500, 300, allergens="milk"),
    _I("dried_fruit", "Сухофрукты", "g", 400, "kg", 1, "kg", 3000, 500),
    _I("berries", "Ягоды замороженные", "g", 350, "kg", 1, "kg", 3000, 500),
    _I("water", "Вода питьевая (для приготовления)", "ml", 1, "l", 20, "l", 200000, 20000),
    _I("yeast", "Дрожжи", "g", 400, "kg", 500, "g", 1000, 200),
    _I("garlic", "Чеснок", "g", 300, "kg", 500, "g", 1000, 200),
    _I("greens", "Зелень", "g", 200, "kg", 500, "g", 800, 200, shelf=3),
    _I("sausage", "Сосиски", "g", 450, "kg", 1, "kg", 3000, 1000, shelf=10, meat=True),
    _I("breadcrumbs", "Панировочные сухари", "g", 200, "kg", 1, "kg", 2000, 500, allergens="gluten"),
    _I("bread", "Хлеб", "g", 65, "kg", 400, "g", 8000, 2000, shelf=3, allergens="gluten", purchased=True),
    # --- сырьё, продаваемое порциями ---
    _I("apple", "Яблоки", "g", 80, "kg", 5, "kg", 10000, 2000, shelf=20),
    _I("banana", "Бананы", "g", 160, "kg", 5, "kg", 4000, 1000, shelf=5),
    _I("pear", "Груши", "g", 130, "kg", 5, "kg", 4000, 1000, shelf=10),
    _I("seasonal_fruit", "Сезонные фрукты", "g", 100, "kg", 5, "kg", 4000, 1000, shelf=5),
    _I("nuts", "Орехи", "g", 1300, "kg", 1, "kg", 2000, 500, purchased=True),
    # --- готовые закупаемые товары (состав и аллергены — по маркировке поставщика) ---
    _I("p_ketchup", "Кетчуп (готовый)", "g", 180, "kg", 1, "kg", 3000, 500, purchased=True),
    _I("p_mayo", "Майонез (готовый)", "g", 200, "kg", 1, "kg", 3000, 500, purchased=True),
    _I("p_mustard", "Горчица (готовая)", "g", 220, "kg", 1, "kg", 1000, 200, purchased=True),
    _I("p_cheese_sauce", "Сырный соус (готовый)", "g", 350, "kg", 1, "kg", 2000, 400, purchased=True),
    _I("p_medovik", "Медовик (готовый)", "pcs", 40, "pcs", 12, "pcs", 24, 12, purchased=True),
    _I("p_napoleon", "Наполеон (готовый)", "pcs", 42, "pcs", 12, "pcs", 24, 12, purchased=True),
    _I("p_sponge", "Бисквитный торт (готовый, порц.)", "pcs", 38, "pcs", 12, "pcs", 24, 12, purchased=True),
    _I("p_cupcake", "Кекс (готовый)", "pcs", 25, "pcs", 24, "pcs", 48, 24, purchased=True),
    _I("p_cookies", "Печенье (готовое)", "g", 300, "kg", 1, "kg", 5000, 1000, purchased=True),
    _I("p_waffles", "Вафли (готовые)", "pcs", 12, "pcs", 30, "pcs", 60, 30, purchased=True),
    _I("p_donut", "Пончик (готовый)", "pcs", 22, "pcs", 12, "pcs", 24, 12, purchased=True),
    _I("p_cheesecake", "Чизкейк (готовый, порц.)", "pcs", 55, "pcs", 8, "pcs", 16, 8, purchased=True),
    _I("p_icecream", "Мороженое (готовое)", "pcs", 35, "pcs", 24, "pcs", 48, 24, purchased=True),
    _I("p_choco_bar", "Шоколадный батончик (готовый)", "pcs", 28, "pcs", 36, "pcs", 72, 36, purchased=True),
    _I("p_candy", "Конфеты (готовые)", "g", 650, "kg", 1, "kg", 5000, 1000, purchased=True),
    _I("p_marmalade", "Мармелад (готовый)", "g", 450, "kg", 1, "kg", 4000, 1000, purchased=True),
    _I("p_zefir", "Зефир (готовый)", "g", 500, "kg", 1, "kg", 4000, 1000, purchased=True),
    _I("p_halva", "Халва (готовая)", "g", 650, "kg", 1, "kg", 4000, 1000, purchased=True),
    _I("p_yogurt", "Йогурт (готовый)", "pcs", 30, "pcs", 12, "pcs", 36, 12, shelf=14, purchased=True),
    _I("p_curd_dessert", "Творожный десерт (готовый)", "pcs", 35, "pcs", 12, "pcs", 36, 12, shelf=10, purchased=True),
    _I("p_mineral_water", "Минеральная вода 0,5 л", "pcs", 18, "pcs", 12, "pcs", 96, 24, purchased=True),
    _I("p_drinking_water", "Питьевая вода 0,5 л", "pcs", 12, "pcs", 12, "pcs", 96, 24, purchased=True),
    _I("p_juice", "Сок в упаковке 0,2 л", "pcs", 25, "pcs", 24, "pcs", 72, 24, purchased=True),
    _I("p_apple_juice", "Яблочный сок 0,2 л", "pcs", 28, "pcs", 24, "pcs", 72, 24, purchased=True),
    _I("p_orange_juice", "Апельсиновый сок 0,2 л", "pcs", 30, "pcs", 24, "pcs", 72, 24, purchased=True),
    _I("p_ayran", "Айран (готовый)", "ml", 100, "l", 1, "l", 10000, 2000, shelf=5, purchased=True),
]

# Блюда: slug, название, категория, тип, цена KGS, размер порции, ед. порции, время приготовления (мин), рецепт
# sourcing: "prepared" — готовится в столовой; "purchased" — покупается готовым / продаётся порциями.


def P(slug, name, cat, ptype, price, size, unit, prep, recipe):
    return dict(slug=slug, name=name, category=cat, product_type=ptype, price=Decimal(str(price)),
                serving_size=Decimal(str(size)), serving_unit=unit, prep=prep, recipe=recipe, sourcing="prepared")


def B(slug, name, cat, ptype, price, size, unit, recipe):
    return dict(slug=slug, name=name, category=cat, product_type=ptype, price=Decimal(str(price)),
                serving_size=Decimal(str(size)), serving_unit=unit, prep=None, recipe=recipe, sourcing="purchased")


HOT, SOUP, SIDE, SALAD = "hot-dishes", "soups", "sides", "salads"
BAKE, DESS, HOTD, COLD, SAUCE, EXTRA = "bakery-snacks", "desserts-sweets", "hot-drinks", "cold-drinks", "sauces-extras", "extra-items"

DISHES = [
    # ---- A. Горячие блюда ----
    P("plov", "Плов", HOT, "prepared_dish", 185, 350, "g", 60, "rice:100,beef:100,carrot:60,onion:20,oil:15,salt:2,spices:1"),
    P("chicken-rice", "Курица с рисом", HOT, "prepared_dish", 120, 330, "g", 45, "chicken:120,rice:90,carrot:30,onion:20,oil:10,salt:2,spices:1"),
    P("lagman", "Лагман", HOT, "prepared_dish", 145, 450, "g", 50, "beef:70,lagman_noodles:100,potato:40,carrot:30,onion:25,tomato_paste:15,oil:10,salt:3,spices:1,water:250"),
    P("pasta-chicken", "Макароны с курицей", HOT, "prepared_dish", 110, 300, "g", 30, "pasta:100,chicken:90,onion:20,tomato_paste:15,oil:10,salt:2"),
    P("chicken-cutlet", "Куриная котлета", HOT, "prepared_dish", 85, 100, "g", 30, "chicken:110,onion:15,breadcrumbs:20,oil:10,salt:1.5"),
    P("beef-cutlet", "Говяжья котлета", HOT, "prepared_dish", 155, 100, "g", 30, "beef:100,onion:15,breadcrumbs:20,oil:10,salt:1.5"),
    P("chicken-potato", "Курица с картофелем", HOT, "prepared_dish", 115, 350, "g", 45, "chicken:120,potato:200,onion:20,oil:10,salt:2,spices:1"),
    P("pelmeni", "Пельмени", HOT, "prepared_dish", 120, 250, "g", 40, "flour:60,beef:70,onion:20,salt:1.5,water:25,butter:5"),
    P("manty", "Манты", HOT, "prepared_dish", 160, 300, "g", 60, "flour:70,beef:100,onion:40,salt:2,spices:1,butter:5,water:30"),
    P("buckwheat-chicken", "Гречка с курицей", HOT, "prepared_dish", 105, 320, "g", 40, "buckwheat:80,chicken:100,onion:20,carrot:20,oil:10,salt:2"),
    P("zharkoe", "Жаркое с мясом и картофелем", HOT, "prepared_dish", 170, 380, "g", 60, "beef:100,potato:200,onion:30,carrot:20,oil:10,salt:2,spices:1,tomato_paste:10"),
    P("omelet", "Омлет", HOT, "prepared_dish", 75, 150, "g", 10, "egg:3,milk:60,butter:5,salt:1"),
    P("veg-ragu", "Овощное рагу", HOT, "prepared_dish", 80, 320, "g", 35, "potato:150,carrot:40,cabbage:60,onion:25,tomato:40,oil:10,salt:2"),
    # ---- B. Супы ----
    P("chicken-noodle-soup", "Куриный суп с лапшой", SOUP, "prepared_dish", 75, 350, "ml", 40, "chicken:50,lagman_noodles:30,potato:40,carrot:20,onion:15,greens:3,salt:2,water:300"),
    P("borscht", "Борщ", SOUP, "prepared_dish", 90, 350, "ml", 60, "beef:50,beet:50,cabbage:50,potato:50,carrot:20,onion:20,tomato_paste:10,oil:5,salt:2,water:300,sour_cream:20?"),
    P("shorpo", "Шорпо", SOUP, "prepared_dish", 160, 400, "ml", 90, "beef:100,potato:80,carrot:30,onion:30,tomato:30,greens:3,salt:2,spices:1,water:300"),
    P("lentil-soup", "Чечевичный суп", SOUP, "prepared_dish", 65, 350, "ml", 40, "lentil:40,carrot:20,onion:20,potato:40,oil:5,salt:2,spices:1,water:300"),
    P("veg-soup", "Овощной суп", SOUP, "prepared_dish", 55, 350, "ml", 35, "potato:60,carrot:20,cabbage:40,onion:15,tomato:20,oil:5,salt:2,water:300"),
    P("milk-pasta-soup", "Молочный суп с макаронами", SOUP, "prepared_dish", 55, 300, "ml", 20, "milk:250,pasta:30,sugar:5,butter:5,salt:0.5"),
    # ---- C. Гарниры ----
    P("mashed-potato", "Картофельное пюре", SIDE, "prepared_dish", 45, 200, "g", 30, "potato:200,milk:40,butter:10,salt:2"),
    P("baked-potato", "Запечённый картофель", SIDE, "prepared_dish", 45, 200, "g", 40, "potato:200,oil:10,salt:2,spices:1"),
    P("rice-side", "Рис", SIDE, "prepared_dish", 35, 180, "g", 25, "rice:70,salt:1.5,oil:5,water:140"),
    P("buckwheat-side", "Гречка", SIDE, "prepared_dish", 35, 180, "g", 25, "buckwheat:70,salt:1.5,oil:5,water:140"),
    P("pasta-side", "Макароны", SIDE, "prepared_dish", 30, 200, "g", 20, "pasta:80,salt:1.5,oil:5,water:200"),
    P("steamed-veg", "Овощи на пару", SIDE, "prepared_dish", 50, 180, "g", 20, "carrot:60,cabbage:80,potato:40,salt:1"),
    P("braised-cabbage", "Тушёная капуста", SIDE, "prepared_dish", 40, 200, "g", 35, "cabbage:200,carrot:30,onion:20,tomato_paste:10,oil:8,salt:2"),
    # ---- D. Салаты ----
    P("veg-salad", "Овощной салат", SALAD, "prepared_dish", 50, 150, "g", 10, "cucumber:60,tomato:60,cabbage:40,onion:10,oil:8,salt:1,greens:3"),
    P("cabbage-carrot-salad", "Салат из капусты и моркови", SALAD, "prepared_dish", 35, 140, "g", 10, "cabbage:100,carrot:40,oil:8,salt:1,sugar:2"),
    P("cucumber-tomato-salad", "Салат из огурцов и помидоров", SALAD, "prepared_dish", 55, 170, "g", 10, "cucumber:80,tomato:80,onion:10,oil:8,salt:1,greens:3"),
    P("vinaigrette", "Винегрет", SALAD, "prepared_dish", 45, 160, "g", 30, "beet:70,potato:50,carrot:30,onion:10,oil:10,salt:1"),
    P("chicken-salad", "Салат с курицей", SALAD, "prepared_dish", 90, 180, "g", 20, "chicken:60,cucumber:40,tomato:40,cabbage:30,egg:0.5,sour_cream:20,salt:1"),
    # ---- E. Выпечка и перекусы ----
    P("samsa-meat", "Самса с мясом", BAKE, "snack", 100, 1, "pcs", 40, "flour:80,beef:70,onion:40,butter:10,salt:1.5,spices:0.5"),
    P("samsa-potato", "Самса с картофелем", BAKE, "snack", 50, 1, "pcs", 40, "flour:80,potato:80,onion:30,butter:10,salt:1.5"),
    P("pirozhok-potato", "Пирожок с картофелем", BAKE, "snack", 30, 1, "pcs", 45, "flour:60,potato:60,onion:15,yeast:1,oil:8,salt:1,sugar:2"),
    P("pirozhok-meat", "Пирожок с мясом", BAKE, "snack", 60, 1, "pcs", 45, "flour:60,beef:45,onion:20,yeast:1,oil:8,salt:1,sugar:2"),
    P("sausage-in-dough", "Сосиска в тесте", BAKE, "snack", 55, 1, "pcs", 40, "flour:70,sausage:60,yeast:1,oil:8,salt:1"),
    P("chicken-sandwich", "Сэндвич с курицей", BAKE, "snack", 100, 1, "pcs", 10, "bread:80,chicken:70,tomato:20,cucumber:20,butter:5,salt:0.5"),
    P("cheese-toast", "Тост с сыром", BAKE, "snack", 60, 1, "pcs", 8, "bread:60,cheese:40,butter:5"),
    P("pizza-slice", "Пицца порционная", BAKE, "snack", 90, 1, "pcs", 30, "flour:90,yeast:2,tomato_paste:20,cheese:50,sausage:30,oil:5,salt:1.5,water:50"),
    P("blini", "Блины", BAKE, "snack", 55, 2, "pcs", 20, "flour:40,milk:80,egg:0.5,sugar:5,oil:5,salt:0.5"),
    P("lepeshka", "Лепёшка", BAKE, "snack", 20, 1, "pcs", 40, "flour:120,water:70,yeast:2,salt:2,oil:6"),
    # ---- F. Десерты и сладости (готовые закупаемые товары) ----
    B("medovik", "Медовик", DESS, "dessert", 75, 1, "pcs", "p_medovik:1"),
    B("napoleon", "Наполеон", DESS, "dessert", 75, 1, "pcs", "p_napoleon:1"),
    B("sponge-cake", "Бисквитный торт порционный", DESS, "dessert", 70, 1, "pcs", "p_sponge:1"),
    B("cupcake", "Кекс", DESS, "dessert", 45, 1, "pcs", "p_cupcake:1"),
    B("cookies", "Печенье", DESS, "dessert", 35, 50, "g", "p_cookies:50"),
    B("waffles", "Вафли", DESS, "dessert", 25, 1, "pcs", "p_waffles:1"),
    B("donut", "Пончик", DESS, "dessert", 40, 1, "pcs", "p_donut:1"),
    B("cheesecake", "Чизкейк порционный", DESS, "dessert", 95, 1, "pcs", "p_cheesecake:1"),
    B("ice-cream", "Мороженое", DESS, "dessert", 60, 1, "pcs", "p_icecream:1"),
    B("choco-bar", "Шоколадный батончик", DESS, "dessert", 45, 1, "pcs", "p_choco_bar:1"),
    B("candy-portion", "Конфеты — порция", DESS, "dessert", 25, 30, "g", "p_candy:30"),
    B("candy-pack", "Конфеты — упаковка", DESS, "dessert", 180, 200, "g", "p_candy:200"),
    B("marmalade-pack", "Мармелад — упаковка", DESS, "dessert", 160, 250, "g", "p_marmalade:250"),
    B("zefir-portion", "Зефир — порция", DESS, "dessert", 30, 40, "g", "p_zefir:40"),
    B("zefir-pack", "Зефир — упаковка", DESS, "dessert", 175, 250, "g", "p_zefir:250"),
    B("halva-portion", "Халва — порция", DESS, "dessert", 45, 50, "g", "p_halva:50"),
    B("halva-pack", "Халва — упаковка", DESS, "dessert", 275, 300, "g", "p_halva:300"),
    B("dried-fruit-portion", "Сухофрукты — порция", DESS, "dessert", 30, 40, "g", "dried_fruit:40"),
    # ---- G. Чай и горячие напитки ----
    P("black-tea", "Чёрный чай", HOTD, "beverage", 20, 200, "ml", 5, "black_tea:2,water:200,sugar:10?"),
    P("green-tea", "Зелёный чай", HOTD, "beverage", 25, 200, "ml", 5, "green_tea:2,water:200,sugar:10?"),
    P("lemon-tea", "Чай с лимоном", HOTD, "beverage", 30, 210, "ml", 5, "black_tea:2,water:200,lemon:10,sugar:10?"),
    P("milk-tea", "Чай с молоком", HOTD, "beverage", 30, 200, "ml", 5, "black_tea:2,water:150,milk:50,sugar:10?"),
    P("mint-tea", "Чай с мятой", HOTD, "beverage", 30, 200, "ml", 5, "black_tea:2,mint:2,water:200,sugar:10?"),
    P("ginger-tea", "Имбирный чай", HOTD, "beverage", 40, 200, "ml", 8, "ginger:6,water:200,lemon:5,honey:8?"),
    P("americano", "Кофе американо", HOTD, "beverage", 60, 200, "ml", 3, "coffee:9,water:200"),
    P("coffee-milk", "Кофе с молоком", HOTD, "beverage", 80, 250, "ml", 4, "coffee:9,water:100,milk:120,sugar:10?"),
    P("cocoa", "Какао", HOTD, "beverage", 55, 250, "ml", 6, "cocoa:10,milk:180,sugar:12,water:50"),
    P("hot-chocolate", "Горячий шоколад", HOTD, "beverage", 95, 250, "ml", 6, "chocolate:35,milk:200,sugar:5"),
    # ---- H. Холодные напитки ----
    P("kompot", "Компот", COLD, "beverage", 25, 250, "ml", 30, "dried_fruit:25,apple:20,sugar:15,water:230"),
    P("mors", "Морс", COLD, "beverage", 30, 250, "ml", 20, "berries:40,sugar:15,water:220"),
    P("lemonade", "Лимонад домашний", COLD, "beverage", 45, 300, "ml", 10, "lemon:40,sugar:25,water:250,mint:1"),
    B("mineral-water", "Минеральная вода", COLD, "beverage", 35, 0.5, "l", "p_mineral_water:1"),
    B("drinking-water", "Питьевая вода", COLD, "beverage", 25, 0.5, "l", "p_drinking_water:1"),
    B("juice-pack", "Сок в упаковке", COLD, "beverage", 40, 0.2, "l", "p_juice:1"),
    B("apple-juice", "Яблочный сок", COLD, "beverage", 45, 0.2, "l", "p_apple_juice:1"),
    B("orange-juice", "Апельсиновый сок", COLD, "beverage", 45, 0.2, "l", "p_orange_juice:1"),
    P("cold-tea", "Холодный чай", COLD, "beverage", 30, 300, "ml", 15, "black_tea:2,sugar:12,lemon:10,water:250"),
    B("ayran", "Айран", COLD, "beverage", 45, 250, "ml", "p_ayran:250"),
    # ---- I. Соусы и дополнения ----
    B("ketchup", "Кетчуп", SAUCE, "sauce", 8, 20, "g", "p_ketchup:20"),
    B("mayonnaise", "Майонез", SAUCE, "sauce", 8, 20, "g", "p_mayo:20"),
    P("sour-cream-sauce", "Сметанный соус", SAUCE, "sauce", 15, 35, "g", 5, "sour_cream:30,greens:2,salt:0.5"),
    P("garlic-sauce", "Чесночный соус", SAUCE, "sauce", 20, 35, "g", 5, "sour_cream:30,garlic:3,salt:0.5"),
    B("cheese-sauce", "Сырный соус", SAUCE, "sauce", 20, 25, "g", "p_cheese_sauce:25"),
    P("tomato-sauce", "Томатный соус", SAUCE, "sauce", 15, 55, "g", 15, "tomato_paste:25,water:30,sugar:2,garlic:1,salt:0.5"),
    B("mustard", "Горчица", SAUCE, "sauce", 8, 15, "g", "p_mustard:15"),
    B("butter-portion", "Сливочное масло — порция", SAUCE, "extra", 15, 10, "g", "butter:10"),
    B("sour-cream-portion", "Сметана — порция", SAUCE, "extra", 15, 30, "g", "sour_cream:30"),
    B("cheese-extra", "Сыр — дополнительная порция", SAUCE, "extra", 25, 20, "g", "cheese:20"),
    B("bread-slice", "Хлеб", SAUCE, "extra", 5, 30, "g", "bread:30"),
    P("lepeshka-extra", "Лепёшка — дополнительная порция", SAUCE, "extra", 20, 1, "pcs", 40, "flour:120,water:70,yeast:2,salt:2,oil:6"),
    B("lemon-slice", "Лимон — долька", SAUCE, "extra", 8, 10, "g", "lemon:10"),
    B("sugar-portion", "Сахар — порция", SAUCE, "extra", 3, 10, "g", "sugar:10"),
    B("milk-for-tea", "Молоко для чая и кофе", SAUCE, "extra", 10, 50, "ml", "milk:50"),
    # ---- J. Дополнительные товары ----
    P("boiled-egg", "Яйцо варёное", EXTRA, "extra", 20, 1, "pcs", 12, "egg:1,salt:0.3"),
    B("yogurt", "Йогурт", EXTRA, "extra", 45, 1, "pcs", "p_yogurt:1"),
    B("curd-dessert", "Творожный десерт", EXTRA, "dessert", 55, 1, "pcs", "p_curd_dessert:1"),
    B("nuts-portion", "Орехи — порция", EXTRA, "extra", 60, 30, "g", "nuts:30"),
    B("seasonal-fruit", "Фрукты сезонные — порция", EXTRA, "extra", 50, 150, "g", "seasonal_fruit:150"),
    B("apple", "Яблоко", EXTRA, "extra", 25, 180, "g", "apple:180"),
    B("banana", "Банан", EXTRA, "extra", 25, 120, "g", "banana:120"),
    B("pear", "Груша", EXTRA, "extra", 30, 170, "g", "pear:170"),
]

# Веса популярности для генерации демо-истории заказов (is_demo=True)
DEMO_WEIGHTS = {
    "plov": 6, "chicken-rice": 4, "lagman": 4, "pelmeni": 3, "borscht": 3, "chicken-cutlet": 3,
    "mashed-potato": 3, "rice-side": 3, "samsa-meat": 4, "samsa-potato": 3, "lepeshka": 2,
    "black-tea": 5, "kompot": 4, "juice-pack": 3, "veg-salad": 2, "pizza-slice": 3, "donut": 2,
}
