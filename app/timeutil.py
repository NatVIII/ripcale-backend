"""Datetime helpers enforcing the naive-UTC storage convention.

`to_utc_naive()` is used by source modules when normalizing timestamps;
`parse_iso_utc()` is used by routers to read `start`/`end` query params.
"""
#region: imports
from datetime import datetime, timezone
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
