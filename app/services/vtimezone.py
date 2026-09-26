"""RFC 5545 `VTIMEZONE` generation from IANA zone names (F64).

`build()` returns an `icalendar.Timezone` component (with `STANDARD`/`DAYLIGHT`
sub-components carrying explicit `DTSTART`/`RDATE` transition instants) so that a
recurring event can be emitted with `TZID` + local times and stay wall-clock
correct across DST. Transitions are emitted as `RDATE`s (robust for any zone
history) rather than a derived yearly `RRULE`.
"""
#region: imports
from datetime import datetime, timedelta, timezone

from dateutil.tz import gettz
from icalendar import Timezone, TimezoneDaylight, TimezoneStandard
#endregion


#region: helpers
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _sub(kind_cls, transitions, offset_from: int, offset_to: int):
    sub = kind_cls()
    sub.add("DTSTART", transitions[0][0])
    for when, _ in transitions[1:]:
        sub.add("RDATE", when)
    sub.add("TZOFFSETFROM", timedelta(seconds=offset_from))
    sub.add("TZOFFSETTO", timedelta(seconds=offset_to))
    return sub
#endregion


#region: build
def build(tz_name: str) -> Timezone | None:
    """Build a `VTIMEZONE` for `tz_name`, or None if the zone is unknown/UTC-like."""
    tz = gettz(tz_name)
    if tz is None:
        return None

    standard: list[tuple[datetime, object]] = []
    daylight: list[tuple[datetime, object]] = []
    for ts, info in zip(tz._trans_list, tz._trans_idx):
        when = _EPOCH + timedelta(seconds=ts)
        (daylight if info.isdst else standard).append((when, info))

    if not standard:
        return None

    std_offset = standard[0][1].offset
    dst_offset = daylight[0][1].offset if daylight else std_offset

    component = Timezone()
    component.add("TZID", tz_name)
    component.add_component(_sub(TimezoneStandard, standard, dst_offset, std_offset))
    if daylight:
        component.add_component(_sub(TimezoneDaylight, daylight, std_offset, dst_offset))
    return component
#endregion
