"""Instagram gatherer (HikerAPI) — F21.

Fetches a public Instagram account's recent posts via HikerAPI and maps each to a
`ScrapedEvent` for the pipeline. HikerAPI sources are LLM-resolved (F65): their
posts are enqueued (not inserted) and the LLM decides create/modify/ignore. The
gatherer's capabilities are declared here (not in config).
"""
# Contract: Gatherer v8 (docs/GATHERER_CONTRACT.md)
CONTRACT_VERSION = 9
PERMANENT = True                # posts never "removed at source", only expire
DECIDE_BEFORE_INSERT = True     # enqueue posts for LLM resolution (F65)

#region: imports
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.schema import GathererResult, ImageRef, ScrapedEvent, SourceConfig
#endregion


logger = logging.getLogger(__name__)

#region: constants
BASE_URL = "https://api.hikerapi.com"
TIMEOUT = 30.0

_USERNAME_RE = re.compile(r"instagram\.com/([^/?#]+)")
#endregion


#region: helpers
def _username_from_url(url: str) -> str | None:
    """Extract an Instagram username from a profile URL or a bare handle."""
    match = _USERNAME_RE.search(url)
    if match:
        return match.group(1).strip()
    candidate = url.strip().strip("/").split("/")[-1].lstrip("@")
    if candidate and not candidate.startswith(("http", "?")):
        return candidate
    return None


def _truncate(text: str, limit: int = 1000) -> str:
    text = (text or "").strip()
    return text[:limit] + "…" if len(text) > limit else text


def _json_or_text(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def _get(url: str, params: dict[str, Any] | None = None, capture: list[dict] | None = None) -> Any:
    """GET a HikerAPI endpoint; on error, raise a clear message including the body."""
    headers = {"x-access-key": settings.hikerapi_key}
    try:
        resp = httpx.get(url, headers=headers, params=params, follow_redirects=True, timeout=TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = _json_or_text(exc.response)
        if capture is not None:
            capture.append(
                {"url": url, "status": exc.response.status_code, "headers": dict(exc.response.headers), "body": body}
            )
        raise RuntimeError(f"HikerAPI {exc.response.status_code} for {url}: {_truncate(str(body))}") from exc
    except httpx.RequestError as exc:
        if capture is not None:
            capture.append({"url": url, "status": None, "headers": {}, "body": str(exc)})
        raise RuntimeError(f"HikerAPI request failed ({type(exc).__name__}): {exc}") from exc

    body = resp.json()
    if capture is not None:
        capture.append(
            {"url": url, "status": resp.status_code, "headers": dict(resp.headers), "body": body}
        )
    return body


def _media_list(payload: Any) -> list[dict]:
    """Normalize a media-feed payload to a flat list of media dicts.

    Handles the current `/g2/user/medias` shape (`{"response": {"items": [...]}}`),
    the retired `/v1/user/medias/chunk` shape (`[[medias…], cursor]`), and a bare
    list.
    """
    if isinstance(payload, dict):
        response = payload.get("response")
        items = response.get("items") if isinstance(response, dict) else payload.get("items")
        return [m for m in items if isinstance(m, dict)] if isinstance(items, list) else []
    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        return [m for m in payload[0] if isinstance(m, dict)]
    if isinstance(payload, list):
        return [m for m in payload if isinstance(m, dict)]
    return []


def _best_image_url(versions: list | None) -> str | None:
    """Pick the highest-resolution URL from an image-candidate list."""
    best: tuple[int, str] | None = None
    for v in versions or []:
        if not isinstance(v, dict):
            continue
        url = v.get("url")
        if not url:
            continue
        area = int(v.get("width") or 0) * int(v.get("height") or 0)
        if best is None or area > best[0]:
            best = (area, url)
    return best[1] if best else None


def _candidates(item: dict) -> list:
    """Image candidates from the g2 (`image_versions2.candidates`) or v1 (`image_versions`) shape."""
    iv2 = item.get("image_versions2")
    if isinstance(iv2, dict):
        return iv2.get("candidates") or []
    iv = item.get("image_versions")
    return iv if isinstance(iv, list) else []


def _image_refs(media: dict) -> list[ImageRef]:
    images: list[ImageRef] = []
    for item in media.get("carousel_media") or media.get("resources") or []:
        if isinstance(item, dict):
            url = _best_image_url(_candidates(item)) or item.get("thumbnail_url")
            if url:
                images.append(ImageRef(url=url))
    if not images:
        top = _best_image_url(_candidates(media))
        if top:
            images.append(ImageRef(url=top))
    if not images:
        thumb = media.get("thumbnail_url")
        if thumb:
            images.append(ImageRef(url=thumb))
    return images


def _taken_at(media: dict) -> datetime | None:
    for key in ("taken_at_ts", "taken_at", "1ltaken_at"):
        val = media.get(key)
        if not val:
            continue
        if isinstance(val, int) or (isinstance(val, str) and val.isdigit()):
            try:
                return datetime.fromtimestamp(int(val), tz=timezone.utc).replace(tzinfo=None)
            except (TypeError, ValueError, OSError):
                continue
        try:
            return datetime.fromisoformat(str(val).replace("Z", "+00:00")).replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
    return None


def _title_and_description(caption: str | None) -> tuple[str, str | None]:
    text = (caption or "").strip()
    if not text:
        return "(untitled)", None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0] if lines else "(untitled)"
    if len(title) > 120:
        title = title[:117].rstrip() + "…"
    return title, text
#endregion


#region: mapping
def to_event(media: dict) -> ScrapedEvent:
    pk_val = media.get("pk") or str(media.get("id") or "").split("_")[0]
    pk = str(pk_val) if pk_val else ""
    code = media.get("code")
    caption = media.get("caption")
    caption_text = caption.get("text") if isinstance(caption, dict) else (caption or media.get("caption_text"))
    title, description = _title_and_description(caption_text)

    location = None
    loc = media.get("location")
    if isinstance(loc, dict):
        location = loc.get("name") or loc.get("address")

    return ScrapedEvent(
        uid=pk or None,
        title=title,
        description=description,
        location=location,
        url=f"https://www.instagram.com/p/{code}/" if code else None,
        images=_image_refs(media),
        start_at=_taken_at(media),
        timezone=None,
        categories=[],
        raw=dict(media),
    )
#endregion


#region: fetch + run
def fetch_medias(source: SourceConfig) -> list[dict]:
    """Fetch the account's recent posts (latest page)."""
    if not settings.hikerapi_key:
        raise ValueError("RIPCALE_HIKERAPI_KEY is not set — cannot fetch Instagram")
    username = _username_from_url(source.url)
    if not username:
        raise ValueError(f"cannot parse an Instagram username from {source.url!r}")
    user = _get(f"{BASE_URL}/v1/user/by/username", {"username": username})
    pk = user.get("pk")
    if pk is None:
        raise ValueError(f"no 'pk' in HikerAPI user response for {username!r}")
    return _media_list(_get(f"{BASE_URL}/g2/user/medias", {"user_id": str(pk)}))


def fetch_raw(source: SourceConfig) -> list[dict]:
    """Fetch both calls and return the full captured responses (status + headers + body).

    Used by the standalone runner's `--save-raw` for offline verification and
    error diagnosis. Raises (with the body) on the first failed call.
    """
    if not settings.hikerapi_key:
        raise ValueError("RIPCALE_HIKERAPI_KEY is not set — cannot fetch Instagram")
    username = _username_from_url(source.url)
    if not username:
        raise ValueError(f"cannot parse an Instagram username from {source.url!r}")

    captured: list[dict] = []
    user = _get(f"{BASE_URL}/v1/user/by/username", {"username": username}, capture=captured)
    pk = user.get("pk")
    if pk is None:
        raise ValueError(f"no 'pk' in HikerAPI user response for {username!r}")
    _get(f"{BASE_URL}/g2/user/medias", {"user_id": str(pk)}, capture=captured)
    return captured


def verify(user: Any, medias: Any) -> list[str]:
    """Sanity-check the raw responses against the shapes the gatherer expects.

    Returns a list of human-readable warnings (empty = shapes look right); never
    raises. `user` may be None to check only the media list.
    """
    warnings: list[str] = []
    if user is not None:
        if not isinstance(user, dict):
            warnings.append("user response is not an object")
        else:
            if not user.get("pk"):
                warnings.append("user response missing 'pk'")
            if not user.get("username"):
                warnings.append("user response missing 'username'")

    if not isinstance(medias, list):
        warnings.append("media response is not a list")
        return warnings

    for i, media in enumerate(medias):
        if not isinstance(media, dict):
            warnings.append(f"media[{i}] is not an object")
            continue
        if not (media.get("pk") or media.get("id")):
            warnings.append(f"media[{i}] missing 'pk'/'id'")
        if not media.get("code"):
            warnings.append(f"media[{i}] missing 'code'")
        caption = media.get("caption")
        has_caption = (isinstance(caption, dict) and caption.get("text")) or media.get("caption_text")
        if not has_caption:
            warnings.append(f"media[{i}] missing caption ('caption.text'/'caption_text')")
        if not (media.get("image_versions2") or media.get("image_versions")
                or media.get("carousel_media") or media.get("resources") or media.get("thumbnail_url")):
            warnings.append(f"media[{i}] has no image source")
        if not (media.get("taken_at_ts") or media.get("taken_at") or media.get("1ltaken_at")):
            warnings.append(f"media[{i}] has no timestamp")
    return warnings


def run(source: SourceConfig) -> GathererResult:
    medias = fetch_medias(source)
    events = [to_event(m) for m in medias]
    logger.info("hikerapi %s: %d posts", source.name, len(events))
    return GathererResult(source=source, events=events)
#endregion
