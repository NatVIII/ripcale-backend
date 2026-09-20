"""Tests for the central clock (F56.01)."""
#region: imports
from datetime import datetime

import app.services.clock as clock
#endregion


def test_clock_real_when_unset(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "debug_now", None)
    assert clock.debug_active() is False
    assert clock.now() > datetime(2020, 1, 1)  # sane "now"


def test_clock_frozen(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "debug_now", "2026-12-25T12:00:00")
    assert clock.debug_active() is True
    assert clock.now() == datetime(2026, 12, 25, 12, 0)


def test_clock_aware_override_normalized_to_naive(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "debug_now", "2026-12-25T12:00:00Z")
    assert clock.now() == datetime(2026, 12, 25, 12, 0)  # Z stripped -> naive


def test_clock_invalid_falls_back_to_real(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "debug_now", "not-a-date")
    assert clock.debug_active() is False
    assert clock.now() > datetime(2020, 1, 1)
#endregion
