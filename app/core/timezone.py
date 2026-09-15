from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# Moscow Time (UTC+3)
MSK_TZ = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    """Returns the current datetime in Moscow timezone (UTC+3)."""
    return datetime.now(MSK_TZ)


def now_utc() -> datetime:
    """Returns the current datetime in UTC timezone."""
    return datetime.now(timezone.utc)


def to_msk(dt: Optional[datetime]) -> Optional[datetime]:
    """Converts a datetime (naive UTC or aware) to Moscow timezone (UTC+3)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Naive datetime from SQLite is assumed to be UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK_TZ)


def format_datetime_msk(dt: Optional[datetime], fmt: str = "%d.%m.%Y %H:%M:%S (МСК)") -> str:
    """Formats a datetime into a human-readable Moscow time string."""
    msk_dt = to_msk(dt)
    if msk_dt is None:
        return "—"
    return msk_dt.strftime(fmt)


def format_time_msk(dt: Optional[datetime]) -> str:
    """Formats only the time portion in Moscow timezone (HH:MM:SS)."""
    msk_dt = to_msk(dt)
    if msk_dt is None:
        return "—"
    return msk_dt.strftime("%H:%M:%S")
