"""Database wipe (destructive maintenance, admin-only).

`wipe_all()` empties the Event + Source tables and resets the run-status and
last-ingest files, leaving the schema intact so the server keeps serving and a
later ingest repopulates everything. Called from `app/routers/wipe.py`.
"""
#region: imports
from pathlib import Path

from app.config import settings
from app.db import wipe_db
from app.services.status import reset_status
#endregion


def wipe_all() -> dict:
    """Wipe the DB + reset status/last-ingest. Returns a summary dict."""
    events, sources = wipe_db()
    reset_status()

    last_ingest = Path(settings.data_dir) / "last_ingest.json"
    if last_ingest.exists():
        last_ingest.unlink()

    return {"events": events, "sources": sources}
#endregion
