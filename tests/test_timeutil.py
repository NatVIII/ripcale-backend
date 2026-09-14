"""Tests for datetime helpers (app/timeutil.py)."""
#region: imports
from datetime import datetime

from app.timeutil import display_time, parse_iso_utc, to_utc_naive
#endregion


def test_display_time_edt(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "display_timezone", "America/New_York")
    # 22:00 UTC on 2026-09-30 -> 18:00 EDT (UTC-4)
    assert display_time(datetime(2026, 9, 30, 22, 0)) == "2026-09-30 18:00 America/New_York · 2026-09-30 22:00 UTC"


def test_display_time_est(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "display_timezone", "America/New_York")
    # 22:00 UTC on 2026-01-15 -> 17:00 EST (UTC-5)
    assert display_time(datetime(2026, 1, 15, 22, 0)) == "2026-01-15 17:00 America/New_York · 2026-01-15 22:00 UTC"


def test_display_time_date_rollover(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "display_timezone", "America/New_York")
    # 01:00 UTC on 2026-10-01 -> 21:00 EDT the previous day
    assert display_time(datetime(2026, 10, 1, 1, 0)) == "2026-09-30 21:00 America/New_York · 2026-10-01 01:00 UTC"


def test_display_time_none(monkeypatch):
    assert display_time(None) is None


def test_display_time_invalid_zone_falls_back_to_utc(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "display_timezone", "Not/AZone")
    assert display_time(datetime(2026, 9, 30, 22, 0)) == "2026-09-30 22:00 UTC"


def test_display_time_utc_single(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "display_timezone", "UTC")
    assert display_time(datetime(2026, 9, 30, 22, 0)) == "2026-09-30 22:00 UTC"
#endregion
