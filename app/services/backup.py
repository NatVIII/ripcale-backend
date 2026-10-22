"""Database backups (F23) — scheduled, in-app tar.gz snapshots.

`backup_now()` produces a `ripcale-<UTC-timestamp>.tar.gz` in `backup_dir`
(relative paths resolve against `data_dir`) containing:

- `ripcale.db` — a consistent snapshot taken with SQLite's **online backup API**
  (`sqlite3.Connection.backup`), which is safe under WAL without pausing ingest.
- `intake.yaml` — copied from `settings.intake_file` (included only if present),
  so a restore can re-ingest the same sources.

Retention (`backup_count`) keeps the N most-recent archives. Restore is a
follow-up (F23.02), deliberately out of scope here.
"""
#region: imports
import os
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.models import utcnow
#endregion


#region: constants
_ARCHIVE_PREFIX = "ripcale-"
_ARCHIVE_SUFFIX = ".tar.gz"
#endregion


#region: paths
def _is_sqlite() -> bool:
    return settings.resolved_database_url.startswith("sqlite")


def _db_file() -> Path | None:
    if not _is_sqlite():
        return None
    return Path(settings.resolved_database_url.removeprefix("sqlite:///"))


def backup_dir_path() -> Path | None:
    """Resolve `backup_dir` (None = disabled). Relative -> under `data_dir`."""
    raw = (settings.backup_dir or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = Path(settings.data_dir) / path
    return path
#endregion


#region: archive
def _timestamp() -> str:
    return utcnow().strftime("%Y%m%d-%H%M%S")


def backup_now() -> dict:
    """Snapshot the DB + intake.yaml into a new archive, then apply retention."""
    dest_dir = backup_dir_path()
    if dest_dir is None:
        return {"created": False, "reason": "backup_dir is empty (backups disabled)"}
    db = _db_file()
    if db is None:
        return {"created": False, "reason": "database is not SQLite"}
    if not db.exists():
        return {"created": False, "reason": f"database file not found: {db}"}

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_ARCHIVE_PREFIX}{_timestamp()}{_ARCHIVE_SUFFIX}"

    tmp_dir = Path(tempfile.mkdtemp(prefix=".ripcale-backup-", dir=dest_dir))
    try:
        snapshot = tmp_dir / "ripcale.db"
        source = sqlite3.connect(db)
        try:
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()

        intake_path = Path(settings.intake_file)
        if intake_path.exists():
            shutil.copyfile(intake_path, tmp_dir / "intake.yaml")

        archive = dest_dir / filename
        tmp_archive = dest_dir / f".{filename}.tmp"
        with tarfile.open(tmp_archive, "w:gz") as tar:
            tar.add(snapshot, arcname="ripcale.db")
            if (tmp_dir / "intake.yaml").exists():
                tar.add(tmp_dir / "intake.yaml", arcname="intake.yaml")
        os.replace(tmp_archive, archive)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        "created": True,
        "filename": filename,
        "size": (dest_dir / filename).stat().st_size,
        "pruned": prune(),
    }
#endregion


#region: listing + retention
def list_backups() -> list[dict]:
    """List archives, oldest-first (name sorts chronologically)."""
    dest_dir = backup_dir_path()
    if dest_dir is None or not dest_dir.exists():
        return []
    out = []
    for path in sorted(dest_dir.glob(f"{_ARCHIVE_PREFIX}*{_ARCHIVE_SUFFIX}")):
        stat = path.stat()
        out.append(
            {
                "filename": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )
    return out


def prune() -> int:
    """Delete the oldest archives beyond `backup_count`; returns the count removed."""
    dest_dir = backup_dir_path()
    count = settings.backup_count
    if dest_dir is None or not dest_dir.exists() or not count:
        return 0
    archives = sorted(dest_dir.glob(f"{_ARCHIVE_PREFIX}*{_ARCHIVE_SUFFIX}"))
    excess = archives[:-count] if count > 0 else []
    for path in excess:
        path.unlink(missing_ok=True)
    return len(excess)
#endregion
