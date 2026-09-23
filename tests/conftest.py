"""Shared test fixtures."""
#region: imports
import hashlib

import pytest
#endregion


class _FakeResponse:
    """Minimal httpx.Response stand-in so image hosting never hits the network."""

    def __init__(self, content: bytes):
        self.content = content
        self.headers = {"Content-Type": "image/jpeg"}

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return {}

    @property
    def text(self) -> str:
        return ""


@pytest.fixture(autouse=True)
def _fake_http(monkeypatch):
    """Stub outbound HTTP so tests never download images from real CDNs."""
    def fake_get(url, **kwargs):
        return _FakeResponse(hashlib.sha256(url.encode()).hexdigest().encode())

    monkeypatch.setattr("httpx.get", fake_get)


@pytest.fixture
def session_headers(tmp_path, monkeypatch):
    """A valid session cookie header (authenticates the /debug dashboard)."""
    from sqlmodel import SQLModel, create_engine

    from app.services import auth

    engine = create_engine(f"sqlite:///{tmp_path / 'sess.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(auth, "engine", engine)
    token = auth.create_session(1)  # user_id 1 (no FK enforcement on a fresh engine)
    return {"Cookie": f"ripcale_session={token}"}


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """Point `settings.data_dir` and `settings.intake_file` at a temp dir so
    tests never touch real `data/` or `intake.yaml`."""
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.config.settings.intake_file", str(tmp_path / "intake.yaml"))
