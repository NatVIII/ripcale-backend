"""Authentication: argon2id password hashing + DB-backed sessions/tokens + login.

Passwords are hashed with argon2id and never stored plaintext. Login sessions
and per-user API tokens are DB-backed (survive restart); API tokens are stored
as SHA-256 hashes (the raw value is shown only once at creation). Login is
timing-safe (a dummy verify runs for unknown users) and rate-limited.
"""
#region: imports
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlmodel import Session, delete, select

from app.config import settings
from app.db import engine
from app.models import ApiToken, LoginSession, User, utcnow
from app.services.actions import ActionError
#endregion


#region: password hashing
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536   # 64 MiB
ARGON2_PARALLELISM = 4

_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
)

_dummy_hash: str | None = None


def _apply_pepper(password: str) -> str:
    """Key the password with the configured pepper (no-op when pepper is empty)."""
    if not settings.pepper:
        return password
    return hmac.new(settings.pepper.encode(), password.encode(), hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    return _hasher.hash(_apply_pepper(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, _apply_pepper(password))
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if `password_hash` was made with stale/weaker argon2 parameters."""
    return _hasher.check_needs_rehash(password_hash)


def _dummy_verify(password: str) -> None:
    """Run a real argon2 verify against a dummy hash to equalize timing."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("ripcale-dummy-password-for-timing")
    verify_password(password or "", _dummy_hash)
#endregion


#region: sessions
SESSION_TTL = 24 * 3600.0


def _session_expiry() -> datetime:
    return utcnow() + timedelta(seconds=SESSION_TTL)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with Session(engine) as session:
        cutoff = utcnow()
        session.exec(delete(LoginSession).where(LoginSession.user_id == user_id, LoginSession.expires_at < cutoff))
        session.add(LoginSession(token=token, user_id=user_id, expires_at=_session_expiry()))
        session.commit()
    return token


def validate_session(token: str | None) -> int | None:
    if not token:
        return None
    with Session(engine) as session:
        row = session.get(LoginSession, token)
        if row is None:
            return None
        if row.expires_at < utcnow():
            session.delete(row)
            session.commit()
            return None
        return row.user_id


def destroy_session(token: str | None) -> None:
    if not token:
        return
    with Session(engine) as session:
        row = session.get(LoginSession, token)
        if row is not None:
            session.delete(row)
            session.commit()
#endregion


#region: api tokens
def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_api_token(user_id: int, label: str = "") -> str:
    raw = secrets.token_urlsafe(32)
    with Session(engine) as session:
        session.add(ApiToken(token_hash=_token_hash(raw), user_id=user_id, label=(label or "").strip()))
        session.commit()
    return raw


def validate_api_token(raw_token: str | None) -> int | None:
    if not raw_token:
        return None
    with Session(engine) as session:
        row = session.get(ApiToken, _token_hash(raw_token))
        return row.user_id if row is not None else None


def revoke_api_token(raw_token: str | None) -> bool:
    if not raw_token:
        return False
    with Session(engine) as session:
        row = session.get(ApiToken, _token_hash(raw_token))
        if row is None:
            return False
        session.delete(row)
        session.commit()
    return True


def list_api_tokens(user_id: int) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(ApiToken).where(ApiToken.user_id == user_id)).all()
    return [{"token_hash": r.token_hash[:12], "label": r.label, "created_at": r.created_at} for r in rows]
#endregion


#region: login (rate-limited + timing-safe + lockout)
_RATE_LIMIT = 5
_RATE_WINDOW = 300.0
_attempts: dict[str, list[float]] = {}

LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION = 900.0  # 15 min
_lockouts: dict[str, float] = {}
_failures: dict[str, int] = {}


def _prune(key: str) -> list[float]:
    now = time.time()
    kept = [t for t in _attempts.get(key, []) if now - t < _RATE_WINDOW]
    _attempts[key] = kept
    return kept


def _rate_limited(*keys: str) -> bool:
    return any(len(_prune(k)) >= _RATE_LIMIT for k in keys)


def _record_failure(*keys: str) -> None:
    for k in keys:
        _attempts.setdefault(k, []).append(time.time())


def _is_locked(username: str) -> bool:
    until = _lockouts.get(username)
    if until is None:
        return False
    if until < time.time():
        _lockouts.pop(username, None)
        return False
    return True


def _record_login_failure(username: str) -> None:
    _failures[username] = _failures.get(username, 0) + 1
    if _failures[username] >= LOCKOUT_THRESHOLD:
        _lockouts[username] = time.time() + LOCKOUT_DURATION
        _failures[username] = 0


def _clear_login_failures(username: str) -> None:
    _failures.pop(username, None)
    _lockouts.pop(username, None)


def login(username: str, password: str, ip: str | None = None) -> str:
    """Verify credentials and return a fresh session token.

    Raises `ActionError("account locked", 423)` when locked out,
    `ActionError("too many attempts", 429)` when rate-limited, and
    `ActionError("invalid credentials", 401)` on failure (identical for
    unknown-user vs wrong-password, and timing-equalized).
    """
    username = (username or "").strip()

    if _is_locked(username):
        raise ActionError("account locked", 423)

    keys = [f"ip:{ip}", f"user:{username}"]
    if _rate_limited(*keys):
        raise ActionError("too many attempts", 429)

    user = _get_user(username)
    if user is None:
        _dummy_verify(password)
        _record_failure(*keys)
        _record_login_failure(username)
        raise ActionError("invalid credentials", 401)

    if not verify_password(password or "", user.password_hash):
        _record_failure(*keys)
        _record_login_failure(username)
        raise ActionError("invalid credentials", 401)

    _clear_login_failures(username)

    if needs_rehash(user.password_hash):
        _set_user_hash(username, hash_password(password or ""))

    return create_session(user.id)


def _get_user(username: str) -> User | None:
    with Session(engine) as session:
        return session.exec(select(User).where(User.username == username)).first()


def _set_user_hash(username: str, password_hash: str) -> None:
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is not None:
            user.password_hash = password_hash
            session.add(user)
            session.commit()
#endregion


#region: bootstrap
def ensure_admin_user() -> bool:
    """Create the admin user from config if it doesn't exist. Returns True if created."""
    if not settings.admin_password_hash:
        return False
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == settings.admin_username)).first()
        if existing is not None:
            return False
        session.add(User(username=settings.admin_username, password_hash=settings.admin_password_hash))
        session.commit()
    return True
#endregion


#region: user management
def create_user(username: str, password: str) -> bool:
    """Create a user (hashes the password with the configured pepper). Returns False if taken."""
    username = (username or "").strip()
    if not username or not password:
        raise ActionError("username and password are required")
    with Session(engine) as session:
        if session.exec(select(User).where(User.username == username)).first() is not None:
            return False
        session.add(User(username=username, password_hash=hash_password(password)))
        session.commit()
    return True


def change_password(username: str, password: str) -> bool:
    """Update a user's password. Returns False if the user doesn't exist."""
    username = (username or "").strip()
    if not password:
        raise ActionError("password is required")
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            return False
        user.password_hash = hash_password(password)
        session.add(user)
        session.commit()
    return True


def remove_user(username: str) -> bool:
    """Delete a user. Returns False if the user doesn't exist."""
    username = (username or "").strip()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            return False
        session.delete(user)
        session.commit()
    return True


def list_users() -> list[str]:
    with Session(engine) as session:
        return sorted(u.username for u in session.exec(select(User)).all())
#endregion
