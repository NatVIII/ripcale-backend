"""Tests for recurrence helpers (app/services/recurrence.py)."""
#region: imports
from datetime import datetime

from app.services.recurrence import last_occurrence
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
