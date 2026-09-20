"""Tests for system settings (app/config.py)."""
#region: imports
from app.config import Settings
#endregion


def test_expire_past_days_accepts_none():
    assert Settings(expire_past_days=None).expire_past_days is None


def test_expire_future_days_accepts_none():
    assert Settings(expire_past_days=90, expire_future_days=None).expire_future_days is None


def test_archive_grace_hours_default():
    assert Settings(expire_past_days=90, expire_future_days=None).archive_grace_hours == 6


def test_archive_grace_hours_accepts_none():
    assert Settings(archive_grace_hours=None).archive_grace_hours is None


def test_ingest_interval_default():
    assert Settings(display_timezone="America/New_York").ingest_interval_minutes == 60


def test_ingest_interval_accepts_none():
    assert Settings(ingest_interval_minutes=None).ingest_interval_minutes is None


def test_ingest_startup_delay_default():
    assert Settings(display_timezone="America/New_York").ingest_startup_delay_minutes == 3
#endregion
