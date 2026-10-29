"""Создание пользователя: python -m scripts.create_user <username> <administrator|cook|economist>"""
import getpass
import sys

from sqlalchemy import select

from app.core.config import load_settings
from app.database import init_db, make_engine, make_session_factory
from app.models import User
from app.services import auth_service

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in ("administrator", "cook", "economist"):
        sys.exit(__doc__)
    username, role = sys.argv[1], sys.argv[2]
    password = getpass.getpass("Пароль (не менее 10 символов): ")
    if len(password) < 10:
        sys.exit("Пароль слишком короткий")
    engine = make_engine(load_settings().database_url)
    init_db(engine)
    with make_session_factory(engine)() as db:
        if db.scalar(select(User.id).where(User.username == username)):
            sys.exit("Пользователь уже существует")
        auth_service.create_user(db, username, password, role)
        db.commit()
    print("Создан:", username, role)
