"""Recurrence helpers (RFC 5545 RRULE).

`last_occurrence()` is used by the sieve's expiry filter (F13) and the garbage
collector (F22) to decide whether a recurring series has fully ended. F12
(recurrence expansion) will build the full occurrence generator here too.
"""
#region: imports
import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
#endregion


#region: normalization
_UNTIL_ISO = re.compile(
    r"UNTIL=(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?Z?",
    re.IGNORECASE,
)
_UNTIL_Z = re.compile(r"(UNTIL=\d{8}(?:T\d{6})?)Z", re.IGNORECASE)


def _normalize_until(rrule_str: str) -> str:
    """Rewrite `UNTIL` into the compact form dateutil accepts.

    Real calendars emit RFC 5545 `UNTIL` values dateutil's `rrulestr` rejects:
    a trailing `Z` (`UNTIL=20240129T000000Z`) and ISO-dashed dates
    (`UNTIL=2024-01-29T00:00:00Z`). This collapses both to `UNTIL=YYYYMMDDTHHMMSS`
    (or `YYYYMMDD` for date-only), and strips the `Z`.
    """
    def _rebuild(m):
        date_ = f"{m.group(1)}{m.group(2)}{m.group(3)}"
        if m.group(4):
            return f"UNTIL={date_}T{m.group(4)}{m.group(5)}{m.group(6)}"
        return f"UNTIL={date_}"

    return _UNTIL_Z.sub(r"\1", _UNTIL_ISO.sub(_rebuild, rrule_str))
#endregion


#region: rrule normalization (RFC 5545, UTC UNTIL — F64)
def _local_to_utc(dt: datetime, tz: str | None) -> datetime:
    """Interpret `dt` in IANA `tz` (or UTC if unknown) and return naive UTC."""
    if tz:
        try:
            aware = dt.replace(tzinfo=ZoneInfo(tz))
        except (ZoneInfoNotFoundError, ValueError):
            aware = dt.replace(tzinfo=timezone.utc)
    else:
        aware = dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_until_value(value: str, tz: str | None) -> str:
    """Normalize one `UNTIL` value (sans the `UNTIL=` prefix) to compact UTC."""
    v = value.strip()
    has_z = v.upper().endswith("Z")
    if has_z:
        v = v[:-1]

    if "T" in v:
        date_part, time_part = v.split("T", 1)
        date_part = date_part.replace("-", "")
        time_part = time_part.replace(":", "")
        time_part = (time_part + "000000")[:6]
        if not has_z:
            dt = datetime.strptime(f"{date_part}T{time_part}", "%Y%m%dT%H%M%S")
            dt = _local_to_utc(dt, tz)
            date_part = dt.strftime("%Y%m%d")
            time_part = dt.strftime("%H%M%S")
        return f"UNTIL={date_part}T{time_part}Z"

    return f"UNTIL={v.replace('-', '')}"


def normalize_rrule(rrule_str: str, tz: str | None = None) -> str:
    """Normalize an RRULE's `UNTIL` to compact UTC form.

    - ISO-dashed dates collapse to `YYYYMMDD` / `YYYYMMDDTHHMMSS`.
    - A date-time `UNTIL` without a trailing `Z` is treated as local and
      converted to UTC using `tz` (IANA); missing/unknown `tz` assumes UTC.
    - UTC `UNTIL` keeps its `Z`; date-only `UNTIL` is left as a date.
    - Idempotent; other rule parts pass through untouched.
    """
    parts = rrule_str.split(";")
    out = []
    for part in parts:
        if part.strip().upper().startswith("UNTIL="):
            out.append(_normalize_until_value(part.strip()[6:], tz))
        else:
            out.append(part)
    return ";".join(out)
#endregion


#region: last occurrence
def last_occurrence(rrule_str: str | None, start_at: datetime | None) -> datetime | None:
    """Return the final occurrence of a bounded RRULE, or None.

    None means "no determinable last occurrence": the series is unbounded (no
    `UNTIL`/`COUNT`), unparseable, or `start_at` is missing. Callers treat None
    as "never expires" (fail-safe — over-keeping is better than over-dropping).
    """
    if not rrule_str or start_at is None:
        return None

    normalized = _normalize_until(rrule_str)
    upper = normalized.upper()
    if "COUNT=" not in upper and "UNTIL=" not in upper:
        return None  # unbounded series has no last occurrence

    try:
        rule = rrulestr(normalized, dtstart=start_at)
        last = rule[-1]
    except Exception:  # noqa: BLE001 — any parse/expansion failure -> None
        return None
    if isinstance(last, datetime):
        return last
    if isinstance(last, date):  # all-day UNTIL may come back as a date
        return datetime.combine(last, time.min)
    return None
#endregion
