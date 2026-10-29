"""Smart Canteen API. Запуск: uvicorn app.main:create_app --factory"""
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import analytics, inventory, menu, orders, procurement, production, system
from app.core.config import Settings, load_settings
from app.core.errors import AppError
from app.database import init_db, make_engine, make_session_factory
from app.seed.seed import run_seed

log = logging.getLogger("smart_canteen")

DESCRIPTION = """
Backend для «Умной столовой»: предзаказы, расчёт закупок, учёт отходов.

* Все цены, рецептуры и остатки во встроенном меню — **демонстрационные** (валюта KGS).
* Формат успеха: `{"data": ..., "meta": {...}}`; формат ошибки: `{"error": {"code", "message", "details"}}`.
* Защищённые маршруты: `POST /api/auth/login` -> нажмите **Authorize** и вставьте токен.
* Повторы запросов: заголовок `Idempotency-Key` (заказы, план закупки, производство, отходы, корректировки).
"""


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or load_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    engine = make_engine(settings.database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    app = FastAPI(title="Smart Canteen API", version=__version__, description=DESCRIPTION, docs_url="/docs")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    if settings.seed_on_startup:
        run_seed(session_factory, settings)

    app.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"], expose_headers=["Idempotent-Replay"])

    def error_response(status: int, code: str, message: str, details=None) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": details}})

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return error_response(422, "validation_error", "Некорректные данные запроса", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return error_response(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Необработанная ошибка: %s %s", request.method, request.url.path)  # без тела запроса и секретов
        return error_response(500, "internal_error", "Внутренняя ошибка сервера")

    for module in (system, menu, orders, inventory, procurement, production, analytics):
        app.include_router(module.router)
    return app
