"""Tests for the backup service (F23)."""
#region: imports
import sqlite3
import tarfile

import app.services.backup as backup
#endregion


def _configure(tmp_path, monkeypatch, *, backup_dir="backups", count=7):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "backup_dir", backup_dir)
    monkeypatch.setattr(settings, "backup_count", count)
    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))


def _make_db(tmp_path) -> None:
    conn = sqlite3.connect(tmp_path / "ripcale.db")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('hello')")
    conn.commit()
    conn.close()


def _write_intake(tmp_path) -> None:
    (tmp_path / "intake.yaml").write_text("sources: []\n")


def _extract_db(tmp_path, archive_path) -> bytes:
    with tarfile.open(archive_path, "r:gz") as tar:
        return tar.extractfile("ripcale.db").read()


#region: snapshot
def test_backup_creates_archive_with_both_entries(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _make_db(tmp_path)
    _write_intake(tmp_path)

    result = backup.backup_now()
    assert result["created"] is True

    archive = tmp_path / "backups" / result["filename"]
    assert archive.exists()
    with tarfile.open(archive, "r:gz") as tar:
        names = tar.getnames()
    assert "ripcale.db" in names
    assert "intake.yaml" in names


def test_backup_snapshot_is_a_valid_db(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    _make_db(tmp_path)
    _write_intake(tmp_path)

    result = backup.backup_now()
    archive = tmp_path / "backups" / result["filename"]
    snap = tmp_path / "snap.db"
    snap.write_bytes(_extract_db(tmp_path, archive))

    conn = sqlite3.connect(snap)
    row = conn.execute("SELECT v FROM t").fetchone()
    conn.close()
    assert row == ("hello",)
#endregion


#region: skip / disable
def test_backup_skips_missing_db(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    result = backup.backup_now()
    assert result["created"] is False
    assert "not found" in result["reason"]


def test_backup_disabled_when_dir_empty(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, backup_dir="")
    _make_db(tmp_path)
    result = backup.backup_now()
    assert result["created"] is False
    assert "disabled" in result["reason"]
#endregion


#region: retention
def test_prune_keeps_newest(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, count=2)
    bdir = tmp_path / "backups"
    bdir.mkdir(parents=True)
    for ts in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (bdir / f"ripcale-{ts}.tar.gz").write_bytes(b"x")

    assert backup.prune() == 1
    remaining = sorted(p.name for p in bdir.glob("ripcale-*.tar.gz"))
    assert remaining == ["ripcale-20260102-000000.tar.gz", "ripcale-20260103-000000.tar.gz"]


def test_prune_zero_keeps_all(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch, count=0)
    bdir = tmp_path / "backups"
    bdir.mkdir(parents=True)
    (bdir / "ripcale-20260101-000000.tar.gz").write_bytes(b"x")

    assert backup.prune() == 0
    assert len(list(bdir.glob("ripcale-*.tar.gz"))) == 1
#endregion


#region: listing
def test_list_backups(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    bdir = tmp_path / "backups"
    bdir.mkdir(parents=True)
    (bdir / "ripcale-20260101-000000.tar.gz").write_bytes(b"abc")

    rows = backup.list_backups()
    assert len(rows) == 1
    assert rows[0]["filename"] == "ripcale-20260101-000000.tar.gz"
    assert rows[0]["size"] == 3
    assert "created_at" in rows[0]
#endregion
