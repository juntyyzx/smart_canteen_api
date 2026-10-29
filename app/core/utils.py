from contextlib import contextmanager
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Наивное UTC-время (SQLite не хранит часовые пояса)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@contextmanager
def transaction(db):
    """Одна транзакция: commit при успехе, rollback при любой ошибке."""
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
