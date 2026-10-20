"""Shared helpers for gatherers.

`fetch_json()` is used by each gatherer (e.g. `app.gatherers.elfsight.gatherer`) to
retrieve its source payload.
"""
#region: imports
from app.services.ssrf import get as safe_get
#endregion


#region: defaults
FETCH_TIMEOUT = 30.0  # seconds allowed for a source HTTP request
#endregion


#region: fetch
def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict:
    """GET `url` and return its JSON body (raises on HTTP errors)."""
    resp = safe_get(url, headers=headers, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    """GET `url` and return its text body (raises on HTTP errors)."""
    resp = safe_get(url, headers=headers, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    return resp.text
#endregion
