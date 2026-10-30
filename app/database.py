from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.types import DecimalText
from decimal import Decimal


class Base(DeclarativeBase):
    type_annotation_map = {Decimal: DecimalText}


def normalize_db_url(url: str) -> str:
    """Render/Neon/Supabase отдают postgres://… или postgresql://…; SQLAlchemy нужен драйвер psycopg (v3)."""
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str):
    url = normalize_db_url(url)
    kwargs = {}
    is_sqlite = url.startswith("sqlite")
    if not is_sqlite:
        kwargs["pool_pre_ping"] = True  # бесплатные Postgres обрывают простаивающие соединения
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if is_sqlite:
        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _record):  # внешние ключи в SQLite по умолчанию выключены
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=5000")
            cur.close()
    return engine


def make_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine) -> None:
    from app import models  # noqa: F401  (регистрирует таблицы)

    Base.metadata.create_all(engine)


def get_db(request: Request):
    """FastAPI-зависимость: сессия на запрос; незавершённая транзакция откатывается."""
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
