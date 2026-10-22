"""Database backups (F23) — scheduled, in-app tar.gz snapshots.

`backup_now()` produces a `ripcale-<UTC-timestamp>.tar.gz` in `backup_dir`
(relative paths resolve against `data_dir`) containing:

- `ripcale.db` — a consistent snapshot taken with SQLite's **online backup API**
  (`sqlite3.Connection.backup`), which is safe under WAL without pausing ingest.
- `intake.yaml` — copied from `settings.intake_file` (included only if present),
  so a restore can re-ingest the same sources.

Retention (`backup_count`) keeps the N most-recent archives. `restore()` (F23.02)
reverse-restores an archive into the live DB (online-backup API) + `intake.yaml`.
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
    # Microsecond precision so two snapshots in the same second (e.g. a backup
    # immediately followed by its restore safety-net) never collide.
    return utcnow().strftime("%Y%m%d-%H%M%S-%f")


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


#region: restore (F23.02)
def _valid_archive_name(name: str) -> bool:
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        return False
    return name.startswith(_ARCHIVE_PREFIX) and name.endswith(_ARCHIVE_SUFFIX)


def restore(filename: str) -> dict:
    """Restore a snapshot (DB + intake.yaml) into the live system.

    Uses SQLite's online-backup API in reverse (`snapshot -> live`), which is
    safe under WAL without stopping the app. A safety-net snapshot is taken
    first, and the ingest lock is held for the duration so a scheduled ingest
    can't interleave. Restarting the app afterwards is recommended (the public
    process's pooled connections can't be reset from here).
    """
    name = (filename or "").strip()
    if not _valid_archive_name(name):
        return {"restored": False, "reason": "invalid backup name"}

    dest_dir = backup_dir_path()
    if dest_dir is None:
        return {"restored": False, "reason": "backup_dir is empty (backups disabled)"}

    archive = dest_dir / name
    if not archive.exists():
        return {"restored": False, "reason": f"backup not found: {name}"}

    db = _db_file()
    if db is None or not db.exists():
        return {"restored": False, "reason": "live database is not present"}
    if not os.access(db, os.W_OK) or not os.access(db.parent, os.W_OK):
        return {"restored": False, "reason": f"live database is not writable: {db}"}

    safety = backup_now()

    from app.services import lock

    acquired = lock.acquire()
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix=".ripcale-restore-", dir=dest_dir))
        try:
            with tarfile.open(archive, "r:gz") as tar:
                names = {m.name for m in tar.getmembers()}
                if "ripcale.db" not in names:
                    return {"restored": False, "reason": "archive has no ripcale.db"}
                tar.extractall(tmp_dir)

            snapshot = tmp_dir / "ripcale.db"
            snap = sqlite3.connect(snapshot)
            try:
                live = sqlite3.connect(db, timeout=30)
                try:
                    try:
                        snap.backup(live)
                        live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    except sqlite3.Error as exc:
                        return {"restored": False, "reason": f"restore failed: {exc}"}
                finally:
                    live.close()
            finally:
                snap.close()

            intake_archived = tmp_dir / "intake.yaml"
            if intake_archived.exists():
                dest_intake = Path(settings.intake_file)
                dest_intake.parent.mkdir(parents=True, exist_ok=True)
                os.replace(intake_archived, dest_intake)

            from app.db import engine

            engine.dispose()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    finally:
        if acquired:
            lock.release()

    return {
        "restored": True,
        "filename": name,
        "safety_backup": safety.get("filename") if safety.get("created") else None,
        "restart_recommended": True,
    }
#endregion
