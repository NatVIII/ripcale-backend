"""Agnostic per-source run status.

Every run of a source — whether from the batch ingest (`python -m app.ingest`)
or the pipeline playground (`/debug/pipeline/*`) — records its outcome here, so
the /debug status light reads one source of truth regardless of how the run was
triggered.

The store is a single JSON file (`data/status.json`) keyed by source name.
"""
#region: imports
import json
import os
from pathlib import Path

from app.config import settings
from app.models import utcnow
#endregion


#region: store path
def _path() -> Path:
    return Path(settings.data_dir) / "status.json"
#endregion


#region: read
def read_status() -> dict:
    """Return the status map (source name -> entry), or {} if absent."""
    path = _path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
#endregion


#region: write
def record_status(name: str, status: str, message: str | None = None, events: int = 0) -> None:
    """Upsert one source's status entry (read-modify-write, atomic)."""
    statuses = read_status()
    entry: dict = {"status": status, "at": utcnow().isoformat() + "Z", "events": events}
    if message is not None:
        entry["message"] = message
    statuses[name] = entry

    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(statuses, indent=2))
    os.replace(tmp, path)


def record_run(name: str, total_events: int) -> None:
    """Record a successful run: 'ok', or 'warning' when 0 events were returned."""
    if total_events == 0:
        record_status(name, "warning", message="returned 0 events", events=0)
    else:
        record_status(name, "ok", events=total_events)
#endregion


#region: derivation
def source_status(statuses: dict, name: str) -> str:
    """Return a source's status string, defaulting to 'never'."""
    return statuses.get(name, {}).get("status", "never")


def gatherer_rollup(sources: list[dict], statuses: dict) -> dict[str, str]:
    """Roll per-source status into per-gatherer (highest severity wins)."""
    severity = {"error": 2, "warning": 1, "ok": 0, "never": -1}
    rollup: dict[str, str] = {}
    for source in sources:
        gatherer = source["gatherer"]
        rollup.setdefault(gatherer, "never")
        status = source_status(statuses, source["name"])
        if severity.get(status, -1) > severity.get(rollup[gatherer], -1):
            rollup[gatherer] = status
    return rollup
#endregion
