"""Security helpers for the debug/admin endpoints.

Called from `app/routers/debug.py` and `app/routers/pipeline.py`.

Two protections:
  1. IP allowlist (`is_debug_allowed`) — loopback is always allowed; other
     hosts must fall within `settings.debug_allowed_cidrs`.
  2. CSRF token (`verify_csrf`) — the pipeline playground embeds a token in
     its forms and validates it on POST so a cross-origin page cannot drive
     the endpoints.
"""
#region: imports
import ipaddress
import os
import secrets
from urllib.parse import parse_qs

from robyn import Response

from app.config import settings
#endregion


#region: docker detection
# Docker bridge subnets live in 172.16.0.0/12 (default bridge 172.17.x,
# compose/user networks 172.18.x - 172.31.x). The bridge gateway is what the
# admin app sees as the peer when a request comes through a published port.
DOCKER_BRIDGE_CIDR = "172.16.0.0/12"


def in_docker() -> bool:
    """Return True if running inside a Docker container.

    Auto-detected via the `/.dockerenv` marker Docker creates; overridable with
    `RIPCALE_IN_DOCKER=1`.
    """
    env = os.environ.get("RIPCALE_IN_DOCKER", "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    return os.path.exists("/.dockerenv")
#endregion


#region: form parsing
def form_data(request) -> dict:
    """Return the request's form fields as a dict.

    Robyn's real server leaves `application/x-www-form-urlencoded` bodies in
    `request.body` (and `request.form_data` empty); the TestClient passes
    `form_data` directly. Handle both.
    """
    fd = getattr(request, "form_data", None)
    if fd:
        return dict(fd)
    body = getattr(request, "body", None) or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    return {key: value[-1] for key, value in parse_qs(body).items()}
#endregion


#region: csrf token
# A gatherer-level token: use the configured one, or generate an ephemeral one.
_DEBUG_CSRF_TOKEN: str = settings.debug_token or secrets.token_urlsafe(32)


def debug_csrf_token() -> str:
    """Return the token to embed in rendered forms."""
    return _DEBUG_CSRF_TOKEN


def verify_csrf(request) -> bool:
    """Return True if the request's form carries the matching CSRF token."""
    return form_data(request).get("csrf_token", None) == _DEBUG_CSRF_TOKEN
#endregion


#region: ip allowlist
def is_debug_allowed(ip: str | None) -> bool:
    """Return True if `ip` may access the debug endpoints."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    if addr.is_loopback:
        return True

    # Inside Docker, the admin app binds 0.0.0.0 and the host publish is
    # loopback-only, so the only peer is the bridge gateway. Accept it.
    if in_docker() and addr in ipaddress.ip_network(DOCKER_BRIDGE_CIDR):
        return True

    for raw in (settings.debug_allowed_cidrs or "").split(","):
        cidr = raw.strip()
        if not cidr:
            continue
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            # Fail-safe: a malformed CIDR simply does not grant access.
            continue
    return False
#endregion


#region: guard
def debug_guard(request) -> Response | None:
    """Return a 404 Response if the request is not allowed, else None.

    404 (rather than 403) is used to avoid confirming the debug path exists.
    """
    if is_debug_allowed(getattr(request, "ip_addr", None)):
        return None
    return Response(status_code=404, headers={}, description="")
#endregion
