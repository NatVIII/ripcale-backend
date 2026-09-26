"""Tests for VTIMEZONE generation (F64)."""
#region: imports
from app.services.vtimezone import build
#endregion


def test_build_america_new_york():
    vtz = build("America/New_York")
    assert vtz is not None
    ical = vtz.to_ical().decode()
    assert "BEGIN:VTIMEZONE" in ical
    assert "TZID:America/New_York" in ical
    assert "BEGIN:STANDARD" in ical
    assert "BEGIN:DAYLIGHT" in ical
    assert "TZOFFSETTO:-0500" in ical  # EST
    assert "TZOFFSETTO:-0400" in ical  # EDT


def test_build_zone_without_dst_has_no_daylight():
    vtz = build("Africa/Lagos")  # never observed DST
    assert vtz is not None
    ical = vtz.to_ical().decode()
    assert "BEGIN:STANDARD" in ical
    assert "BEGIN:DAYLIGHT" not in ical


def test_build_unknown_zone_returns_none():
    assert build("Not/AZone") is None


def test_build_utc_returns_none():
    # UTC has no transitions, so there's no VTIMEZONE to emit (recurring UTC
    # events fall back to Z timestamps, which is correct).
    assert build("UTC") is None
#endregion
