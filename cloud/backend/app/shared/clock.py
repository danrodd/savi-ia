from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite devuelve datetimes naive; Postgres, aware. Normaliza a UTC aware."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
