"""Tests for system settings (app/config.py)."""
#region: imports
from app.config import Settings
#endregion


def test_expire_past_days_accepts_none():
    assert Settings(expire_past_days=None).expire_past_days is None


def test_expire_future_days_accepts_none():
    assert Settings(expire_past_days=90, expire_future_days=None).expire_future_days is None
#endregion
