"""Единый формат ошибок: {"error": {"code", "message", "details"}}."""
from typing import Any, Optional


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def not_found(what: str, ident=None) -> AppError:
    suffix = f" (id={ident})" if ident is not None else ""
    return AppError(404, "not_found", f"{what} не найден(а){suffix}")


def conflict(code: str, message: str, details=None) -> AppError:
    return AppError(409, code, message, details)


def unprocessable(code: str, message: str, details=None) -> AppError:
    return AppError(422, code, message, details)
