"""Shared helpers for gatherers.

`fetch_json()` / `fetch_text()` are used by each gatherer (elfsight, ics, …) to
retrieve its source payload. They classify a *down/unreachable* source (network
or HTTP error) as `SourceIssue` so ingest records a `warning` rather than a hard
`error`; unparseable content (invalid JSON/ICS) is left as a hard error.
"""
#region: imports
import httpx

from app.gatherers.errors import SourceIssue
from app.services.ssrf import get as safe_get
#endregion


#region: defaults
FETCH_TIMEOUT = 30.0  # seconds allowed for a source HTTP request
#endregion


#region: fetch
def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict:
    """GET `url` and return its JSON body.

    A network/HTTP failure raises `SourceIssue` (source unavailable); an
    unparseable JSON body raises `ValueError` (hard error).
    """
    try:
        resp = safe_get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SourceIssue(f"source returned HTTP {exc.response.status_code} for {url}") from exc
    except httpx.RequestError as exc:
        raise SourceIssue(f"source unreachable ({type(exc).__name__}): {exc}") from exc
    return resp.json()


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    """GET `url` and return its text body.

    A network/HTTP failure raises `SourceIssue` (source unavailable).
    """
    try:
        resp = safe_get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SourceIssue(f"source returned HTTP {exc.response.status_code} for {url}") from exc
    except httpx.RequestError as exc:
        raise SourceIssue(f"source unreachable ({type(exc).__name__}): {exc}") from exc
    return resp.text
#endregion
