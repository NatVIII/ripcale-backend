"""Tests for authentication (F48)."""
#region: imports
import time

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models import User
from app.security import debug_csrf_token
from app.services import auth
from app.services.actions import ActionError
#endregion


def _setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(auth, "engine", engine)
    monkeypatch.setattr("app.db.engine", engine)
    monkeypatch.setattr("app.services.actions.engine", engine)
    auth._attempts.clear()
    auth._sessions.clear()
    auth._lockouts.clear()
    auth._failures.clear()
    return engine


def _create_admin(monkeypatch, password="hunter2"):
    from app.config import settings

    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password_hash", auth.hash_password(password))
    return auth.ensure_admin_user()


#region: hashing
def test_hash_verify_round_trip():
    h = auth.hash_password("hunter2")
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("wrong", h) is False
#endregion


#region: login
def test_login_success(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)
    token = auth.login("admin", "hunter2")
    assert auth.validate_session(token) == "admin"


def test_login_wrong_password(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)
    with pytest.raises(ActionError) as exc:
        auth.login("admin", "wrong")
    assert exc.value.status == 401
    assert str(exc.value) == "invalid credentials"


def test_login_unknown_user(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)
    with pytest.raises(ActionError) as exc:
        auth.login("nobody", "whatever")
    assert exc.value.status == 401
    assert str(exc.value) == "invalid credentials"


def test_login_rate_limited(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)
    # distinct usernames so only the per-IP counter accumulates (isolates the rate limiter)
    for i in range(auth._RATE_LIMIT):
        with pytest.raises(ActionError):
            auth.login(f"nobody{i}", "wrong", ip="1.2.3.4")
    with pytest.raises(ActionError) as exc:
        auth.login("admin", "hunter2", ip="1.2.3.4")
    assert exc.value.status == 429


def test_login_locks_account_after_failures(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)
    for _ in range(auth.LOCKOUT_THRESHOLD):
        with pytest.raises(ActionError) as exc:
            auth.login("admin", "wrong")
        assert exc.value.status == 401
    # locked: even the correct password is rejected
    with pytest.raises(ActionError) as exc:
        auth.login("admin", "hunter2")
    assert exc.value.status == 423
    assert str(exc.value) == "account locked"


def test_lock_expires(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)
    for _ in range(auth.LOCKOUT_THRESHOLD):
        with pytest.raises(ActionError):
            auth.login("admin", "wrong")
    # simulate both windows passing
    auth._lockouts["admin"] = time.time() - 1
    auth._attempts.clear()
    assert auth.validate_session(auth.login("admin", "hunter2")) == "admin"
#endregion


#region: sessions
def test_session_validate_expiry():
    token = auth.create_session("admin")
    assert auth.validate_session(token) == "admin"
    auth._sessions[token]["expires"] = time.time() - 1
    assert auth.validate_session(token) is None


def test_session_destroy():
    token = auth.create_session("admin")
    auth.destroy_session(token)
    assert auth.validate_session(token) is None
#endregion


#region: bootstrap
def test_ensure_admin_user_creates_once(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert _create_admin(monkeypatch) is True
    assert _create_admin(monkeypatch) is False
#endregion


#region: routes
def _client(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    _create_admin(monkeypatch)

    from robyn.testing import TestClient

    from app.admin import app

    return TestClient(app)


def test_login_route_issues_session(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/v1/auth/login", json_data={"username": "admin", "password": "hunter2"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert auth.validate_session(body["data"]["token"]) == "admin"


def test_login_route_bad_credentials(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post("/api/v1/auth/login", json_data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid credentials"


def test_dashboard_requires_session(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/debug")
    assert r.status_code == 302

    token = auth.create_session("admin")
    r = client.get("/debug", headers={"Cookie": f"ripcale_session={token}"})
    assert r.status_code == 200


def test_html_login_flow(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/debug/login")
    assert r.status_code == 200
    assert "log in" in r.text

    r = client.post("/debug/login", form_data={"csrf_token": debug_csrf_token(), "username": "admin", "password": "hunter2"})
    assert r.status_code == 302
    assert r.headers["location"] == "/debug"
#endregion


#region: pepper + rehash (F48.07)
def test_pepper_keys_password(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "pepper", "secret-pepper")
    h = auth.hash_password("hunter2")
    assert auth.verify_password("hunter2", h) is True
    assert auth.verify_password("wrong", h) is False

    # a hash made without the pepper no longer verifies once pepper is set
    monkeypatch.setattr(settings, "pepper", "")
    no_pepper = auth.hash_password("hunter2")
    monkeypatch.setattr(settings, "pepper", "secret-pepper")
    assert auth.verify_password("hunter2", no_pepper) is False


def test_needs_rehash_detects_weak_params():
    from argon2 import PasswordHasher

    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    weak_hash = weak.hash("hunter2")
    assert auth.needs_rehash(weak_hash) is True
    assert auth.needs_rehash(auth.hash_password("hunter2")) is False


def test_login_rehashes_stale_hash(tmp_path, monkeypatch):
    from argon2 import PasswordHasher

    engine = _setup(tmp_path, monkeypatch)
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    with Session(engine) as session:
        session.add(User(username="admin", password_hash=weak.hash("hunter2")))
        session.commit()

    token = auth.login("admin", "hunter2")
    assert auth.validate_session(token) == "admin"

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == "admin")).first()
        assert auth.needs_rehash(user.password_hash) is False
#endregion


#region: user management (F48.04)
def test_create_user_and_login(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert auth.create_user("alice", "hunter2") is True
    assert auth.create_user("alice", "again") is False  # taken
    assert auth.validate_session(auth.login("alice", "hunter2")) == "alice"


def test_change_password(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    auth.create_user("alice", "hunter2")
    assert auth.change_password("alice", "newpass") is True
    with pytest.raises(ActionError):
        auth.login("alice", "hunter2")
    assert auth.validate_session(auth.login("alice", "newpass")) == "alice"
    assert auth.change_password("nobody", "x") is False


def test_remove_user_and_list(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    auth.create_user("alice", "hunter2")
    auth.create_user("bob", "hunter2")
    assert auth.list_users() == ["alice", "bob"]

    assert auth.remove_user("alice") is True
    assert auth.remove_user("alice") is False
    assert auth.list_users() == ["bob"]
    with pytest.raises(ActionError):
        auth.login("alice", "hunter2")
#endregion


