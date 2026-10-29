from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Decimal в JSON-ответах отдаётся числом (значения уже округлены сервером).
Num = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Envelope(BaseModel, Generic[T]):
    """Единый формат успешного ответа: {"data": ..., "meta": {...}}."""
    data: T
    meta: Optional[dict[str, Any]] = None


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def ok(data, **meta):
    return {"data": data, "meta": meta or None}
