"""SQLModel table definitions (the storage layer).

These models are imported by `app/db.py` (via `init_db()` -> `create_all`) and
used throughout the pipeline: the sieve reads `Event`, the decisionmaker writes
`Event`/`Source`, the routers and stats read them.

Convention: all datetimes are stored as naive UTC (see `app/timeutil.py`); the
original IANA zone is kept in `Event.timezone`.
"""
#region: imports
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel
#endregion


#region: time helper
def utcnow() -> datetime:
    """Current time as a naive UTC datetime (matches the storage convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
#endregion


#region: source
class Source(SQLModel, table=True):
    """A calendar source configured in `config.yaml` (the secret feed URL)."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    url: str                      # kept secret, never exposed by the API
    gatherer: str = "ics"             # gatherer name (e.g. "elfsight")
    is_public: bool = False
    default_categories: str = ""  # comma-separated tags applied to every event
    enabled: bool = True
    last_fetched_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
#endregion


#region: event
class Event(SQLModel, table=True):
    """A normalized event, keyed by a stable string id (see app/identity.py)."""

    id: str = Field(primary_key=True)
    source_id: int = Field(foreign_key="source.id", index=True)
    uid: str | None = None        # original id from the source
    title: str
    description: str | None = None
    location: str | None = None
    geo: str | None = None
    url: str | None = None
    images: str = Field(default="[]")  # JSON array of {url, alt, source_url}
    start_at: datetime | None = Field(default=None, index=True)
    end_at: datetime | None = None
    timezone: str | None = None   # original IANA zone (e.g. America/New_York)
    all_day: bool = False
    rrule: str | None = None      # RFC 5545 RRULE value (recurrence series master)
    recurrence_id: datetime | None = None  # original DTSTART of an overridden occurrence (F31.02)
    exdates: str = Field(default="[]")     # JSON array of cancelled occurrence DTSTARTs (F31.02)
    redirect_to_id: str | None = Field(default=None, index=True)  # event redirect/symlink (F31.01)
    priority: int | None = None   # manual override; None = inherit source priority (F31.01)
    categories: str = ""          # comma-separated tags
    content_hash: str = Field(default="", index=True)  # used by the sieve for diffing
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
#endregion
