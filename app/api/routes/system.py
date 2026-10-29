from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.api.deps import get_current_user, get_settings
from app.core.config import Settings
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginIn, TokenOut, UserOut
from app.schemas.common import Envelope, ok
from app.services import auth_service

router = APIRouter()


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@router.get("/api/version", tags=["system"])
def version(settings: Settings = Depends(get_settings)):
    return ok({"name": "Smart Canteen API", "version": __version__, "environment": settings.app_env, "currency": "KGS"})


@router.post("/api/auth/login", tags=["auth"], response_model=Envelope[TokenOut])
def login(payload: LoginIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    token, expires, user = auth_service.login(db, settings, payload.username, payload.password)
    return ok(TokenOut(access_token=token, expires_at=expires, role=user.role.name, username=user.username))


@router.get("/api/auth/me", tags=["auth"], response_model=Envelope[UserOut])
def me(user: User = Depends(get_current_user)):
    return ok(UserOut(id=user.id, username=user.username, role=user.role.name))
