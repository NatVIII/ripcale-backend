"""Shared helpers for gatherers.

`fetch_json()` is used by each gatherer (e.g. `app.gatherers.elfsight.gatherer`) to
retrieve its source payload.
"""
#region: imports
import httpx
#endregion


#region: fetch
def fetch_json(url: str) -> dict:
    """GET `url` and return its JSON body (raises on HTTP errors)."""
    resp = httpx.get(url, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    return resp.json()
#endregion
