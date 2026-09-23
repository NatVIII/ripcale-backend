"""Local, content-addressed image hosting (F18).

`store()` downloads an image once and saves it under
`{data_dir}/images/<sha256>.<ext>`, returning a stable local `/images/...` path.
Content-addressing means identical bytes dedupe and the hash is a stable
identity (unlike the ephemeral Instagram CDN URLs). `host_images()` rewrites a
batch of events' images pre-sieve so `content_hash` stays stable.
"""
#region: imports
import hashlib
import logging
import os
import re
from pathlib import Path

import httpx

from app.config import settings
from app.schema import ScrapedEvent
#endregion


logger = logging.getLogger(__name__)


#region: constants
TIMEOUT = 30.0

_CONTENT_TYPE_EXTS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/heic": ".heic",
    "image/heif": ".heif",
    "image/avif": ".avif",
}

_FILENAME_RE = re.compile(r"[0-9a-f]{64}\.[a-z0-9]+")
#endregion


#region: paths
def _dir() -> Path:
    return Path(settings.data_dir) / "images"


def _ext(content_type: str | None, url: str) -> str:
    if content_type:
        ext = _CONTENT_TYPE_EXTS.get(content_type.split(";")[0].strip().lower())
        if ext:
            return ext
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{2,5}", suffix):
        return suffix
    return ".img"
#endregion


#region: store / serve
def store(url: str) -> str:
    """Download `url`, store content-addressed, and return the local `/images/...` path."""
    resp = httpx.get(url, follow_redirects=True, timeout=TIMEOUT)
    resp.raise_for_status()

    sha = hashlib.sha256(resp.content).hexdigest()
    ext = _ext(resp.headers.get("Content-Type"), url)
    filename = f"{sha}{ext}"
    path = _dir() / filename

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        tmp.write_bytes(resp.content)
        os.replace(tmp, path)

    return f"/images/{filename}"


def resolve(filename: str) -> Path | None:
    """Return the on-disk path for a served filename, or None if invalid (traversal guard)."""
    if not _FILENAME_RE.fullmatch(filename):
        return None
    return _dir() / filename
#endregion


#region: pre-sieve rewrite
def host_images(events: list[ScrapedEvent]) -> None:
    """Rewrite each event's image URLs to stable local paths (pre-sieve).

    A download failure leaves the image on its original external URL (graceful),
    so a broken image never aborts the ingest.
    """
    for event in events:
        for img in event.images:
            if img.url.startswith("/images/"):
                continue  # already hosted
            original = img.url
            try:
                local = store(original)
            except Exception:  # noqa: BLE001 — keep the external URL on failure
                logger.warning("image store failed for %r", original)
                continue
            img.source_url = original
            img.url = local
#endregion
