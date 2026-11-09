"""Shared helpers for gatherers.

`fetch_json()` / `fetch_text()` are used by each gatherer (elfsight, ics, …) to
retrieve its source payload. They classify a *down/unreachable* source (network
or HTTP error) as `SourceIssue` so ingest records a `warning` rather than a hard
`error`; unparseable content (invalid JSON/ICS) is left as a hard error.
"""
#region: imports
from typing import Protocol, runtime_checkable

import httpx

from app.gatherers.errors import SourceIssue
from app.schema import GathererResult, SourceConfig
from app.services.ssrf import get as safe_get
#endregion


#region: interface
@runtime_checkable
class Gatherer(Protocol):
    """The interface every gatherer provides (a module or class under
    ``app/gatherers/<name>/``). It is consumed by ``registry`` and the pipeline.

    Capabilities are optional module/class constants (read by ``registry``):
    ``PERMANENT`` and ``DECIDE_BEFORE_INSERT`` are declared by every gatherer
    today; ``CHANGE_PROBE`` + ``probe()`` are only on ``ChangeProbeGatherer``.
    """

    CONTRACT_VERSION: int
    PERMANENT: bool
    DECIDE_BEFORE_INSERT: bool

    def run(self, source: SourceConfig) -> GathererResult: ...


@runtime_checkable
class ChangeProbeGatherer(Gatherer, Protocol):
    """A gatherer that can cheaply detect whether its source changed."""

    CHANGE_PROBE: bool

    def probe(self, source: SourceConfig, previous_state: dict | None = None) -> dict: ...
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
