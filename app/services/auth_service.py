from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import burn_password_check, hash_password, hash_token, new_token, verify_password
from app.core.utils import transaction, utcnow
from app.models import AuthToken, Role, User


def get_or_create_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def create_user(db: Session, username: str, password: str, role_name: str) -> User:
    role = get_or_create_role(db, role_name)
    user = User(username=username, password_hash=hash_password(password), role_id=role.id)
    db.add(user)
    db.flush()
    return user


def login(db: Session, settings: Settings, username: str, password: str) -> tuple:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        burn_password_check(password)
        raise AppError(401, "invalid_credentials", "Неверный логин или пароль")
    if not verify_password(password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Неверный логин или пароль")
    token = new_token()
    expires = utcnow() + timedelta(minutes=settings.token_ttl_minutes)
    with transaction(db):
        db.add(AuthToken(token_hash=hash_token(token), user_id=user.id, expires_at=expires))
    return token, expires, user


def user_from_token(db: Session, token: str) -> Optional[User]:
    row = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(token)))
    if row is None or row.expires_at < utcnow():
        return None
    user = db.get(User, row.user_id)
    return user if user is not None and user.is_active else None
