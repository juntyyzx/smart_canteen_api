"""Ручной запуск заполнения БД: python -m scripts.seed"""
import json
import logging

from app.core.config import load_settings
from app.database import init_db, make_engine, make_session_factory
from app.seed.seed import run_seed

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    print(json.dumps(run_seed(make_session_factory(engine), settings), ensure_ascii=False, indent=2))
