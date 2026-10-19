import os
from datetime import datetime, timezone

import pytest

from app.core.timezone import EAT

# Monday 2026-10-19, 08:00 EAT - a working day for all test doctors.
FROZEN_NOW = datetime(2026, 10, 19, 8, 0, tzinfo=EAT)


@pytest.fixture
def now():
    return FROZEN_NOW


@pytest.fixture
def clock(now):
    return lambda: now
