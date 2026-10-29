from typing import Optional

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AppError
from app.database import get_db
from app.models import ROLE_ADMIN, ROLE_COOK, ROLE_ECONOMIST, User
from app.services import auth_service

bearer = HTTPBearer(auto_error=False, description="Токен из POST /api/auth/login")

STAFF = (ROLE_ADMIN, ROLE_COOK, ROLE_ECONOMIST)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
                     db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise AppError(401, "not_authenticated", "Требуется авторизация (заголовок Authorization: Bearer <token>)")
    user = auth_service.user_from_token(db, creds.credentials)
    if user is None:
        raise AppError(401, "invalid_token", "Токен недействителен или истёк")
    return user


def require_roles(*roles: str):
    """Администратору разрешено всё; остальным — только перечисленные роли."""
    allowed = set(roles) | {ROLE_ADMIN}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in allowed:
            raise AppError(403, "forbidden", "Недостаточно прав для этой операции",
                           {"required_roles": sorted(allowed), "your_role": user.role.name})
        return user

    return dependency


def idempotency_key(key: Optional[str] = Header(default=None, alias="Idempotency-Key")) -> Optional[str]:
    if key is not None and not (8 <= len(key) <= 100):
        raise AppError(422, "invalid_idempotency_key", "Idempotency-Key должен быть длиной 8–100 символов")
    return key
