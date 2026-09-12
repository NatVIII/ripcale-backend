"""Authentication: argon2id password hashing + in-memory sessions + login.

Passwords are hashed with argon2id and never stored plaintext. Sessions are
opaque, server-generated tokens held in memory (lost on restart). Login is
timing-safe (a dummy verify runs for unknown users) and rate-limited.
"""
#region: imports
import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import User
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
_sessions: dict[str, dict] = {}


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"username": username, "expires": time.time() + SESSION_TTL}
    return token


def validate_session(token: str | None) -> str | None:
    if not token:
        return None
    sess = _sessions.get(token)
    if sess is None:
        return None
    if sess["expires"] < time.time():
        _sessions.pop(token, None)
        return None
    return sess["username"]


def destroy_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)
#endregion


#region: login (rate-limited + timing-safe)
_RATE_LIMIT = 5
_RATE_WINDOW = 300.0
_attempts: dict[str, list[float]] = {}


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


def login(username: str, password: str, ip: str | None = None) -> str:
    """Verify credentials and return a fresh session token.

    Raises `ActionError("invalid credentials", 401)` on failure (identical for
    unknown-user vs wrong-password, and timing-equalized), or
    `ActionError("too many attempts", 429)` when rate-limited.
    """
    username = (username or "").strip()
    keys = [f"ip:{ip}", f"user:{username}"]
    if _rate_limited(*keys):
        raise ActionError("too many attempts", 429)

    user = _get_user(username)
    if user is None:
        _dummy_verify(password)
        _record_failure(*keys)
        raise ActionError("invalid credentials", 401)

    if not verify_password(password or "", user.password_hash):
        _record_failure(*keys)
        raise ActionError("invalid credentials", 401)

    if needs_rehash(user.password_hash):
        _set_user_hash(username, hash_password(password or ""))

    return create_session(username)


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
