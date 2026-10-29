"""Конфигурация. Все секреты и настройки — из переменных окружения (см. .env.example)."""
import os
from dataclasses import dataclass
from typing import Optional

try:  # python-dotenv необязателен
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DEV_CORS = ("http://localhost:3000", "http://localhost:5173", "http://localhost:8080",
            "http://127.0.0.1:5500", "http://localhost:5500")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or not raw.strip() else int(raw)


def _list(name: str, default: tuple) -> tuple:
    raw = os.getenv(name)
    if raw is None:
        return tuple(default)
    return tuple(x.strip() for x in raw.split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    database_url: str = "sqlite:///./smart_canteen.db"
    cors_origins: tuple = DEV_CORS
    token_ttl_minutes: int = 480
    order_auto_confirm: bool = True
    max_item_quantity: int = 50
    max_days_ahead: int = 30
    min_history_days: int = 14
    seed_on_startup: bool = True
    seed_demo_history: bool = True
    seed_admin_password: Optional[str] = None
    seed_cook_password: Optional[str] = None
    seed_economist_password: Optional[str] = None

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


def load_settings() -> Settings:
    env = os.getenv("APP_ENV", "development").lower()
    prod = env == "production"
    # Тестовые пароли подставляются ТОЛЬКО вне production. В production пароли берутся
    # из переменных окружения, а если их нет — пользователи не создаются.
    dev = lambda name, value: os.getenv(name) or (None if prod else value)  # noqa: E731
    return Settings(
        app_env=env,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./smart_canteen.db"),
        cors_origins=_list("CORS_ORIGINS", () if prod else DEV_CORS),
        token_ttl_minutes=_int("TOKEN_TTL_MINUTES", 480),
        order_auto_confirm=_bool("ORDER_AUTO_CONFIRM", True),
        max_item_quantity=_int("MAX_ITEM_QUANTITY", 50),
        max_days_ahead=_int("MAX_DAYS_AHEAD", 30),
        min_history_days=_int("MIN_HISTORY_DAYS", 14),
        seed_on_startup=_bool("SEED_ON_STARTUP", True),
        seed_demo_history=_bool("SEED_DEMO_HISTORY", not prod),
        seed_admin_password=dev("SEED_ADMIN_PASSWORD", "admin12345"),
        seed_cook_password=dev("SEED_COOK_PASSWORD", "cook12345"),
        seed_economist_password=dev("SEED_ECONOMIST_PASSWORD", "economist12345"),
    )
