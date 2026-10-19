from datetime import date, datetime, time, timezone

from app.core.timezone import EAT, eat_day_to_utc_range, is_aligned, to_eat, to_utc


def test_naive_is_treated_as_eat():
    assert to_utc(datetime(2026, 10, 20, 10, 0)) == datetime(
        2026, 10, 20, 7, 0, tzinfo=timezone.utc
    )


def test_offset_and_z_convert_the_same():
    a = to_utc(datetime.fromisoformat("2026-10-20T10:00:00+03:00"))
    b = to_utc(datetime.fromisoformat("2026-10-20T07:00:00Z"))
    assert a == b == datetime(2026, 10, 20, 7, 0, tzinfo=timezone.utc)


def test_early_eat_slot_is_previous_utc_day():
    utc = to_utc(datetime(2026, 10, 21, 0, 30))
    assert utc == datetime(2026, 10, 20, 21, 30, tzinfo=timezone.utc)


def test_day_range_covers_eat_day():
    start, end = eat_day_to_utc_range(date(2026, 10, 20))
    assert start == datetime(2026, 10, 19, 21, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc)


def test_alignment_is_judged_in_eat():
    assert is_aligned(datetime(2026, 10, 20, 10, 0, tzinfo=EAT))
    assert is_aligned(datetime(2026, 10, 20, 10, 30, tzinfo=EAT))
    assert not is_aligned(datetime(2026, 10, 20, 10, 15, tzinfo=EAT))


def test_to_eat_returns_offset():
    result = to_eat(datetime(2026, 10, 20, 7, 0, tzinfo=timezone.utc))
    assert result.utcoffset().total_seconds() == 3 * 3600
    assert result.hour == 10
