"""Tests for the ICS (iCalendar) gatherer (F25)."""
#region: imports
from datetime import datetime

import app.gatherers.ics.gatherer as gatherer
from app.schema import SourceConfig
#endregion


FIXTURE = """BEGIN:VCALENDAR
VERSION:2.0
X-WR-TIMEZONE:America/New_York
BEGIN:VTIMEZONE
TZID:America/New_York
END:VTIMEZONE
BEGIN:VEVENT
UID:u-utc
DTSTART:20260704T210000Z
DTEND:20260705T010000Z
SUMMARY:UTC Event
STATUS:CONFIRMED
END:VEVENT
BEGIN:VEVENT
UID:u-tzid
DTSTART;TZID=America/New_York:20250316T100000
DTEND;TZID=America/New_York:20250316T120000
SUMMARY:TZID Event
END:VEVENT
BEGIN:VEVENT
UID:u-allday
DTSTART;VALUE=DATE:20260930
DTEND;VALUE=DATE:20261001
SUMMARY:All Day
END:VEVENT
BEGIN:VEVENT
UID:u-recur
DTSTART;TZID=America/New_York:20250316T100000
DTEND;TZID=America/New_York:20250316T120000
RRULE:FREQ=WEEKLY;BYDAY=SU
EXDATE;TZID=America/New_York:20250323T100000
SUMMARY:Weekly
STATUS:CANCELLED
END:VEVENT
BEGIN:VEVENT
UID:u-override
RECURRENCE-ID;TZID=America/New_York:20250330T100000
DTSTART;TZID=America/New_York:20250330T110000
SUMMARY:Moved
STATUS:TENTATIVE
END:VEVENT
END:VCALENDAR
"""


def _run(monkeypatch):
    monkeypatch.setattr(gatherer, "fetch_text", lambda url: FIXTURE)
    return gatherer.run(SourceConfig(name="Test", gatherer="ics", url="https://x/feed.ics"))


def _by_uid(result):
    return {e.uid: e for e in result.events}


def test_ics_parses_utc_and_tzid(monkeypatch):
    by = _by_uid(_run(monkeypatch))

    utc = by["u-utc"]
    assert utc.start_at == datetime(2026, 7, 4, 21, 0)
    assert utc.end_at == datetime(2026, 7, 5, 1, 0)
    assert utc.all_day is False
    assert utc.timezone == "America/New_York"  # from X-WR-TIMEZONE
    assert utc.categories == ["confirmed"]

    tzid = by["u-tzid"]
    assert tzid.start_at == datetime(2025, 3, 16, 14, 0)  # 10:00 EDT -> 14:00 UTC
    assert tzid.end_at == datetime(2025, 3, 16, 16, 0)
    assert tzid.categories == []  # no STATUS -> no tag


def test_ics_all_day(monkeypatch):
    e = _by_uid(_run(monkeypatch))["u-allday"]
    assert e.all_day is True
    assert e.start_at == datetime(2026, 9, 30, 0, 0)
    assert e.end_at == datetime(2026, 10, 1, 0, 0)


def test_ics_recurrence_and_status(monkeypatch):
    by = _by_uid(_run(monkeypatch))

    recur = by["u-recur"]
    assert recur.rrule == "FREQ=WEEKLY;BYDAY=SU"
    assert recur.exdates == [datetime(2025, 3, 23, 14, 0)]
    assert recur.categories == ["cancelled"]

    override = by["u-override"]
    assert override.recurrence_id == datetime(2025, 3, 30, 14, 0)
    assert override.categories == ["tentative"]


def test_ics_event_count(monkeypatch):
    assert len(_run(monkeypatch).events) == 5


def test_ics_normalizes_local_until_to_utc(monkeypatch):
    fixture = """BEGIN:VCALENDAR
VERSION:2.0
X-WR-TIMEZONE:America/New_York
BEGIN:VEVENT
UID:u-local
DTSTART;TZID=America/New_York:20240101T190000
RRULE:FREQ=WEEKLY;UNTIL=20241229T235959
SUMMARY:Local Until
END:VEVENT
END:VCALENDAR
"""
    monkeypatch.setattr(gatherer, "fetch_text", lambda url: fixture)
    result = gatherer.run(SourceConfig(name="Test", gatherer="ics", url="https://x/feed.ics"))
    assert "UNTIL=20241230T045959Z" in result.events[0].rrule  # 23:59:59 EST -> 04:59:59 UTC
#endregion
