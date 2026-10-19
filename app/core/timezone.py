"""ALL time zone logic lives here; the rest of the app speaks UTC.

WHY: doctors' working hours are human intent expressed in EAT, while
storage and every comparison must be unambiguous. Keeping the conversion
in one module means a single place to inspect when a time looks wrong.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

EAT = ZoneInfo("Africa/Nairobi")  # UTC+3, no DST - safe to use by name.


def ensure_aware(dt: datetime) -> datetime:
    """A naive datetime is interpreted as EAT (the clinic's wall clock)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=EAT)
    return dt


def to_utc(dt: datetime) -> datetime:
    """Normalise any datetime to UTC for storage and comparison."""
    return ensure_aware(dt).astimezone(timezone.utc)


def to_eat(dt: datetime) -> datetime:
    """Convert a stored datetime back to EAT for responses (+03:00 offset)."""
    return ensure_aware(dt).astimezone(EAT)


def eat_day_to_utc_range(day: date) -> tuple[datetime, datetime]:
    """Half-open UTC range covering one EAT calendar day."""
    start = datetime.combine(day, time(0, 0), tzinfo=EAT)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def eat_slot_to_utc(day: date, at: time) -> datetime:
    """A wall-clock slot on a given EAT day, as UTC."""
    return datetime.combine(day, at, tzinfo=EAT).astimezone(timezone.utc)


def is_aligned(dt: datetime) -> bool:
    """Slots start on :00 or :30 of the EAT clock, so slot length is fixed."""
    local = to_eat(dt)
    return local.minute in (0, 30) and local.second == 0 and local.microsecond == 0
