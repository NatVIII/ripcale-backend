"""Tests for logging config + the constant-time log tail (F37.02)."""
#region: imports
import logging
from logging.handlers import RotatingFileHandler

import pytest

import app.logging as app_logging
#endregion


#region: root-logger isolation
@pytest.fixture
def isolated_root_logger():
    """Detach the root logger's handlers so setup_logging tests don't leak."""
    root = logging.getLogger()
    saved = list(root.handlers)
    root.handlers = []
    try:
        yield root
    finally:
        for h in list(root.handlers):
            h.close()
        root.handlers = []
        for h in saved:
            root.addHandler(h)
#endregion


#region: tail
def _write_log(tmp_path, text: str):
    p = tmp_path / "ripcale.log"
    p.write_text(text)
    return p


def test_tail_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    assert app_logging.read_log_tail() == ""


def test_tail_last_n_lines(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    lines = [f"line{i}" for i in range(10)]
    _write_log(tmp_path, "\n".join(lines) + "\n")
    assert app_logging.read_log_tail(3) == "line7\nline8\nline9"


def test_tail_fewer_lines_than_n(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    _write_log(tmp_path, "x\ny\n")
    assert app_logging.read_log_tail(200) == "x\ny"


def test_tail_no_trailing_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    _write_log(tmp_path, "a\nb\nc")
    assert app_logging.read_log_tail(200) == "a\nb\nc"


def test_tail_large_file_crosses_block_boundary(tmp_path, monkeypatch):
    """A file larger than the 8 KB read block still tails exactly the last N."""
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    lines = [f"line{i:05d}" for i in range(3000)]
    _write_log(tmp_path, "\n".join(lines) + "\n")
    assert app_logging.read_log_tail(200) == "\n".join(lines[-200:])
#endregion


#region: setup
def test_setup_logging_attaches_rotating_handler(isolated_root_logger, monkeypatch, tmp_path):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    app_logging.setup_logging()
    files = [h for h in isolated_root_logger.handlers if isinstance(h, RotatingFileHandler)]
    assert len(files) == 1
    assert files[0].baseFilename == str(tmp_path / "ripcale.log")


def test_setup_logging_idempotent(isolated_root_logger, monkeypatch, tmp_path):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    app_logging.setup_logging()
    app_logging.setup_logging()
    files = [h for h in isolated_root_logger.handlers if isinstance(h, RotatingFileHandler)]
    streams = [h for h in isolated_root_logger.handlers if type(h) is logging.StreamHandler]
    assert len(files) == 1
    assert len(streams) == 1


def test_log_rotation_caps_disk(isolated_root_logger, monkeypatch, tmp_path):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(app_logging.settings, "log_max_bytes", 500)
    monkeypatch.setattr(app_logging.settings, "log_backup_count", 2)
    app_logging.setup_logging()

    logger = logging.getLogger("test.rotation")
    for i in range(100):
        logger.info("line %d %s", i, "x" * 60)

    handler = next(h for h in isolated_root_logger.handlers if isinstance(h, RotatingFileHandler))
    handler.flush()

    assert (tmp_path / "ripcale.log").exists()
    backups = list(tmp_path.glob("ripcale.log.*"))
    assert 1 <= len(backups) <= 2
#endregion


#region: route
def test_logs_route_renders_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))
    _write_log(tmp_path, "hello world\nsecond line\n")

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.get("/debug/logs")
    assert r.status_code == 200
    assert "hello world" in r.text
    assert "second line" in r.text


def test_logs_route_empty_file(tmp_path, monkeypatch):
    monkeypatch.setattr(app_logging.settings, "data_dir", str(tmp_path))

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.get("/debug/logs")
    assert r.status_code == 200
    assert "no log entries yet" in r.text
#endregion
