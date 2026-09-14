"""Datetime helpers enforcing the naive-UTC storage convention.

`to_utc_naive()` is used by gatherers when normalizing timestamps;
`parse_iso_utc()` is used by routers to read `start`/`end` query params;
`display_time()` formats a stored time in the configured display timezone for
the admin UI (storage stays naive-UTC).
"""
#region: imports
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
#endregion


#region: conversions
def to_utc_naive(dt: datetime) -> datetime:
    """Convert an aware datetime to naive UTC (naive input assumed already UTC)."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def parse_iso_utc(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp (with optional Z / offset) into naive UTC."""
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return to_utc_naive(dt)
#endregion


#region: display
def display_time(dt: datetime | None) -> str | None:
    """Format a naive-UTC datetime as `local TZ (… UTC)` for the admin UI.

    Uses `settings.display_timezone` (an IANA name); falls back to UTC if the
    zone is empty or unrecognized.
    """
    if dt is None:
        return None
    utc = dt.replace(tzinfo=timezone.utc)
    tz_name = settings.display_timezone or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
        tz_name = "UTC"
    local = utc.astimezone(tz)
    utc_str = f"{utc.strftime('%Y-%m-%d %H:%M')} UTC"
    if tz_name == "UTC":
        return utc_str
    return f"{local.strftime('%Y-%m-%d %H:%M')} {tz_name} · {utc_str}"
#endregion
