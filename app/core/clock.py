"""Injectable clock.

WHY: services must never call datetime.now() directly - tests freeze time
by handing in a different provider instead of patching globals.
"""
from datetime import datetime, timezone
from typing import Callable

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
