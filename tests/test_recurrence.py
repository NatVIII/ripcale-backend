"""Tests for recurrence helpers (app/services/recurrence.py)."""
#region: imports
from datetime import datetime

from app.services.recurrence import last_occurrence, normalize_rrule
#endregion


START = datetime(2024, 1, 1, 18, 0)


def test_last_occurrence_count():
    assert last_occurrence("FREQ=WEEKLY;COUNT=5", START) == datetime(2024, 1, 29, 18, 0)


def test_last_occurrence_until_compact():
    assert last_occurrence("FREQ=WEEKLY;UNTIL=20240129T000000", START) == datetime(2024, 1, 22, 18, 0)


def test_last_occurrence_until_z_suffix():
    assert last_occurrence("FREQ=WEEKLY;UNTIL=20240129T000000Z", START) == datetime(2024, 1, 22, 18, 0)


def test_last_occurrence_until_iso_dashed():
    assert last_occurrence("FREQ=WEEKLY;UNTIL=2024-01-29T00:00:00Z", START) == datetime(2024, 1, 22, 18, 0)


def test_last_occurrence_until_date_only():
    assert last_occurrence("FREQ=WEEKLY;UNTIL=20240129", START) == datetime(2024, 1, 22, 18, 0)


def test_last_occurrence_unbounded_is_none():
    assert last_occurrence("FREQ=WEEKLY", START) is None
    assert last_occurrence("FREQ=WEEKLY;BYDAY=MO,WE", START) is None


def test_last_occurrence_unparseable_is_none():
    assert last_occurrence("FREQ=WEEKLY;WTF=1", START) is None
    assert last_occurrence("garbage", START) is None


def test_last_occurrence_missing_inputs():
    assert last_occurrence(None, START) is None
    assert last_occurrence("FREQ=WEEKLY;COUNT=5", None) is None
#endregion


#region: normalize_rrule (F64)
def test_normalize_rrule_utc_z_unchanged():
    assert normalize_rrule("FREQ=WEEKLY;BYDAY=MO;UNTIL=20241230T045959Z") == "FREQ=WEEKLY;BYDAY=MO;UNTIL=20241230T045959Z"


def test_normalize_rrule_iso_dashed_until_compacts():
    assert normalize_rrule("FREQ=WEEKLY;UNTIL=2024-12-30T04:59:59Z") == "FREQ=WEEKLY;UNTIL=20241230T045959Z"


def test_normalize_rrule_local_until_converts_to_utc():
    # 2024-12-29 23:59:59 America/New_York (EST) -> 2024-12-30 04:59:59 UTC
    assert (
        normalize_rrule("FREQ=WEEKLY;UNTIL=20241229T235959", tz="America/New_York")
        == "FREQ=WEEKLY;UNTIL=20241230T045959Z"
    )


def test_normalize_rrule_local_until_unknown_tz_assumes_utc():
    assert normalize_rrule("FREQ=WEEKLY;UNTIL=20241230T045959") == "FREQ=WEEKLY;UNTIL=20241230T045959Z"


def test_normalize_rrule_date_only_until():
    assert normalize_rrule("FREQ=WEEKLY;UNTIL=20241230") == "FREQ=WEEKLY;UNTIL=20241230"
    assert normalize_rrule("FREQ=WEEKLY;UNTIL=2024-12-30") == "FREQ=WEEKLY;UNTIL=20241230"


def test_normalize_rrule_no_until_passthrough():
    assert normalize_rrule("FREQ=WEEKLY;BYDAY=MO,WE") == "FREQ=WEEKLY;BYDAY=MO,WE"


def test_normalize_rrule_idempotent():
    once = normalize_rrule("FREQ=WEEKLY;UNTIL=2024-12-30T04:59:59Z")
    assert normalize_rrule(once) == once
#endregion


#region: expiry boundary (F22.08)
def test_is_expired_last_occurrence_duration_boundary():
    from app.services.expiry import is_expired

    now = datetime(2026, 9, 15, 12, 0)  # cutoff = 2026-09-05 12:00 (10 days)
    start = datetime(2026, 8, 1, 8, 0)
    rrule = "FREQ=WEEKLY;COUNT=6"  # last occurrence = 2026-09-05 08:00

    # last start (09-05 08:00) is before the cutoff, but start + 6h ends after it -> still relevant
    assert is_expired(start, datetime(2026, 8, 1, 14, 0), rrule, now, 10) is False
    # start + 2h ends before the cutoff -> expired
    assert is_expired(start, datetime(2026, 8, 1, 10, 0), rrule, now, 10) is True
#endregion
