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
from sqlmodel import Session, select

from app.config import settings
from app.models import Event
from app.schema import ImageRef, ScrapedEvent, load_images
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


#region: local-file queries + GC (F18.01)
def _filename_from_url(url: str) -> str | None:
    prefix = "/images/"
    if url.startswith(prefix):
        return url[len(prefix):]
    return None


def is_local(url: str) -> bool:
    """True when `url` is a hosted `/images/<file>` whose file exists on disk."""
    filename = _filename_from_url(url)
    if filename is None:
        return False
    path = resolve(filename)
    return path is not None and path.is_file()


def referenced_filenames(session: Session) -> set[str]:
    """Filenames referenced by live (non-archived) events' image galleries."""
    referenced: set[str] = set()
    rows = session.exec(select(Event).where(Event.archived_at.is_(None))).all()
    for event in rows:
        for img in load_images(event.images):
            filename = _filename_from_url(img.url)
            if filename:
                referenced.add(filename)
    return referenced


def prune(session: Session, dry_run: bool = True) -> dict:
    """Delete hosted image files no live event references (F18.01).

    Files referenced only by archived events are also pruned (they re-host on
    restore). Returns a report; `dry_run=True` only previews.
    """
    directory = _dir()
    on_disk: list[Path] = []
    if directory.is_dir():
        on_disk = [
            p for p in directory.iterdir()
            if p.is_file() and _FILENAME_RE.fullmatch(p.name)
        ]
    referenced = referenced_filenames(session)
    orphans = [p for p in on_disk if p.name not in referenced]
    bytes_freed = sum(p.stat().st_size for p in orphans)

    if not dry_run:
        for path in orphans:
            try:
                path.unlink()
            except OSError:
                logger.warning("failed to unlink orphan image %s", path)

    return {
        "dry_run": dry_run,
        "on_disk": len(on_disk),
        "referenced": len(referenced),
        "orphan_count": len(orphans),
        "bytes_freed": bytes_freed,
        "preview": sorted(p.name for p in orphans),
    }


def rehost_missing_images(images: list[ImageRef]) -> list[ImageRef]:
    """Re-download hosted images whose local file is missing (e.g. after a prune).

    Content-addressing means identical bytes re-land on the same filename; a
    failed or impossible re-host (no `source_url`) leaves the image untouched.
    """
    for img in images:
        if _filename_from_url(img.url) is None or not img.source_url or is_local(img.url):
            continue
        try:
            img.url = store(img.source_url)
        except Exception:  # noqa: BLE001 — keep the stale local URL on failure
            logger.warning("re-host failed for %r", img.source_url)
    return images
#endregion
