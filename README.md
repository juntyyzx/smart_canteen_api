# Smart Canteen — backend «Умной столовой»

Backend для хакатонного кейса «Борьба с пищевыми отходами»: меню, предзаказы, расчёт закупок,
учёт склада, производства и отходов, аналитика. Frontend — отдельный сайт (CORS настроен).

Стек: Python 3.12, FastAPI, SQLAlchemy 2.x, SQLite, Pydantic 2.x, pytest. Без Docker, платных API и внешних сервисов.
Вся арифметика — `Decimal`, детерминированный код, ИИ в расчётах не участвует.

> **Массы порций и рецептуры во встроенном меню — демонстрационные** (не утверждённые нормы питания), записи помечены `is_demo = true`. Закупочные цены (KGS) ориентированы на розничные цены Бишкека за 2026 год (рис, говядина, овощи, мука, масло, сахар, яйца, молоко, макароны — по мониторингу Антимонопольной службы КР, остальное — оценка), цены продажи считаются от себестоимости. Это ориентиры, а не реальный прайс столовой: меняйте их через API.

## Статус проверки (честно)

| Что | Статус |
|---|---|
| Расчётное ядро (`app/domain`): 20 тестов | ✅ запущены и проходят |
| Встроенное меню (102 позиции, рецепты, единицы, себестоимость): 8 тестов | ✅ запущены и проходят |
| Остальной код (БД, сервисы, API) — компилируется, импорты сверены | ⚠️ **не запускался**: в среде, где писался код, не было FastAPI/SQLAlchemy и интернета |
| Интеграционные тесты API (`tests/test_api.py`, 25 тестов) | ⚠️ написаны, **не запускались** |

Поэтому первым делом выполните шаги 1–3 ниже. Если тест упадёт — это ошибка в коде, которую нужно поправить
(скорее всего мелкая: имя поля, импорт). Не считайте проект проверенным, пока `pytest` не зелёный.

## Запуск с нуля

```bash
cd smart_canteen
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env

pytest -q                            # шаг 1: все тесты (отдельная БД на каждый тест)
python run.py                        # шаг 2: сервер на http://127.0.0.1:8000
# или: uvicorn app.main:create_app --factory --reload
```

Шаг 3: откройте **http://127.0.0.1:8000/docs** (Swagger UI). БД `smart_canteen.db` создаётся и заполняется
меню автоматически при первом запуске. Повторный запуск ничего не дублирует.

Ручной seed: `python -m scripts.seed`. Новый пользователь: `python -m scripts.create_user <имя> <роль>`.

## Деплой на Render без потери данных

Файловая система бесплатного Render **стирается при каждом перезапуске**, поэтому SQLite-файл там не сохраняется. Подключите внешнюю PostgreSQL:

1. Создайте БД (например, бесплатную на Neon или Supabase; встроенная бесплатная Postgres на Render живёт всего 30 дней).
2. В Render → сервис → Environment добавьте `DATABASE_URL` = строка подключения (`postgresql://…`; `postgres://` тоже подойдёт — драйвер подставится сам).
3. Остальные переменные: `APP_ENV=production`, `CORS_ORIGINS=https://juntyyzx.github.io`, `SEED_ADMIN_PASSWORD`, `SEED_COOK_PASSWORD`, `SEED_ECONOMIST_PASSWORD`.
4. Redeploy. Таблицы и меню создаются при первом запуске, повторные запуски ничего не затирают.

Склад по умолчанию стартует **пустым**: остатки вводит повар на вкладке «Склад» (`PUT /api/inventory/stock`). Чтобы вернуть демонстрационные остатки, задайте `SEED_DEMO_STOCK=true`.

## Пользователи (только development)

| Логин | Пароль (тестовый!) | Роль |
|---|---|---|
| admin | admin12345 | administrator |
| cook | cook12345 | cook |
| economist | economist12345 | economist |

В `APP_ENV=production` тестовых паролей нет: задайте `SEED_*_PASSWORD` в окружении или создайте пользователей
скриптом. Пароли хранятся как scrypt-хэш, токены — как sha256 (в открытом виде нигде).

Авторизация: `POST /api/auth/login` → `access_token` → заголовок `Authorization: Bearer <token>`
(в Swagger — кнопка **Authorize**).

## Формат ответов

Успех: `{"data": ..., "meta": {...}}`. Ошибка: `{"error": {"code": "...", "message": "...", "details": ...}}`.
Деньги и количества в JSON — числа; валюта везде KGS. Frontend ничего не пересчитывает: себестоимость, потребность
и стоимость закупок приходят готовыми, с полем `explanation` для каждой позиции.

Повторы запросов безопасны: заголовок `Idempotency-Key` (8–100 символов) для заказов, плана закупки,
производства, отходов и корректировок склада. Повтор → `200` + `Idempotent-Replay: true`, без новых записей.

## Эндпоинты и роли

Публичные: меню, заказы (создание, проверка по номеру), `/health`, `/api/version`.
Администратор (`administrator`) имеет доступ ко всему. «Staff» = administrator, cook, economist.

| Метод и путь | Доступ |
|---|---|
| `GET /api/categories`, `GET /api/menu[?category=hot-dishes&available=true&q=плов]`, `GET /api/menu/{id}` | публично |
| `POST /api/orders` | публично (`order_date`, `items[]`, `customer_ref` — анонимный id) |
| `GET /api/orders/track/{номер}` | публично (без персональных данных) |
| `GET /api/orders[?date=]`, `GET /api/orders/{id}`, `GET /api/orders/summary?date=` | staff |
| `PATCH /api/orders/{id}/cancel`, `/confirm`, `/complete` | cook |
| `POST /api/dishes` | administrator |
| `PATCH /api/dishes/{id}` (цена, доступность…) | economist |
| `GET /api/dishes/{id}/recipe`, `/costing` | staff |
| `PUT /api/dishes/{id}/recipe` | cook |
| `GET /api/ingredients`, `GET /api/inventory`, `GET /api/inventory/movements` | staff |
| `POST/PATCH /api/ingredients` | economist |
| `POST /api/inventory/adjustments` (причина обязательна) | cook |
| `POST /api/procurement-plan/preview` | staff |
| `POST /api/procurement-plan` (утвердить), `PATCH …/{id}/cancel` | economist |
| `POST /api/procurement-plan/{id}/receive` (поступление) | cook |
| `GET /api/procurement-plan[?date=]`, `GET /api/procurement-plan/{id}` | staff |
| `POST /api/production`, `POST /api/waste` | cook |
| `GET /api/analytics/waste\|popularity\|summary?from=&to=[&include_demo=true]` | staff |

## Как считаются закупки (`app/domain/calculator.py`)

1. Берутся заказы на дату со статусом `confirmed` (опционально `pending`; демо — `include_demo`).
2. Порции группируются по блюдам; блюдо без рецептуры → `requiring_recipe`, его потребность **не** включается в итог.
3. `required = Σ порции × количество_в_рецепте` (деление на `yield_factor` — только если он задан явно, диапазон (0; 1]).
   Необязательные ингредиенты (`is_optional`, например сахар в чае) не считаются.
4. `available = max(0, остаток − резерв)`; резерв — часть потребности более ранних утверждённых планов, вычитается один раз.
5. `net_need = max(0, required − available)`; `package_count = ceil(net_need / package_size)`;
   `purchase_quantity = package_count × package_size`; `cost = purchase_quantity × цена_за_единицу` (округление до 0,01 KGS).
6. Нет цены → `missing_price`, стоимость `null`, `total_is_complete = false`, утвердить план нельзя (`incomplete_calculation`).

Единицы: kg/g → g, l/ml → ml, pcs. Граммы в миллилитры **не** конвертируются. Отрицательные цены/количества,
нулевая упаковка, `yield_factor` вне (0; 1] отклоняются.

Жизненный цикл: **preview** (ничего не меняет) → **утверждённый план** (`approved`, склад не меняется) →
**receive** (приход на склад, один раз) → `received`. Повторный receive склад не увеличивает.

## Склад, производство, отходы

- Остаток меняется только через движения (`purchase`, `consumption`, `waste`, `adjustment`, `return`), количество со знаком.
  Отрицательный остаток невозможен (`409 insufficient_stock`). Прямой правки остатка через `PATCH /api/ingredients` нет.
- `POST /api/production`: `served + leftover + discarded = prepared`. Списывает ингредиенты по рецептуре **атомарно**
  (нехватка любого → ничего не списано). `discarded_portions` автоматически попадает в отходы со стоимостью.
  Не отправляйте то же выброшенное блюдо ещё и в `POST /api/waste`. `consume_stock=false` — записать факт без списания.
- `POST /api/waste`: готовое блюдо (`unit=portion`, склад не трогается) или сырой ингредиент (списывается со склада).

## Аналитика и честность данных

По умолчанию считаются только реальные данные. Демо-данные включаются `include_demo=true`; ответ содержит
`history.data_basis` (`none|real|demo|mixed`), `contains_demo_data` и `insufficient_history`
(меньше `MIN_HISTORY_DAYS`=14 дней истории). «Валовая разница по ингредиентам» = выручка − стоимость ингредиентов;
это **не** чистая прибыль (зарплаты, электричество, аренда не учитываются). Себестоимость считается по текущим ценам и рецептурам.

## Структура

```
app/ main.py · database.py · core/ (config, security, errors) · models/ · schemas/ · services/ · api/ (deps, routes/)
     domain/ (units, money, calculator — чистый Python) · seed/ (menu_data, seed)
scripts/ seed.py, create_user.py · tests/ · run.py · requirements.txt · .env.example
```

## Допущения и ограничения MVP

- Миграций Alembic нет: таблицы создаются `create_all`. Для production стоит добавить Alembic.
- Не реализованы отдельные таблицы Suppliers, MenuSchedules, RecipeVersions, Allergens/DietaryTags
  (аллергены и теги хранятся строкой и выводятся из состава; для готовых закупаемых товаров состав неизвестен — аллергены не заявляются).
- Сумма резервов считается по датам утверждённых планов; после фактического списания на производстве резерв того же дня
  может учитываться повторно до окончания дня.
- SQLite: запускайте один процесс uvicorn; для нескольких воркеров нужна другая БД.
- Отмена заказа клиентом (по номеру) не сделана — отменяет повар/администратор.
- Телеграм-бота и frontend здесь нет (по ТЗ).
