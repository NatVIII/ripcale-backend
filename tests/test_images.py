"""Tests for local image hosting (F18) + image GC (F18.01)."""
#region: imports
import hashlib
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, Source
from app.schema import ImageRef, ScrapedEvent, dump_images
from app.services import images
#endregion


class _Resp:
    def __init__(self, content: bytes, content_type: str = "image/jpeg"):
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        pass


def _fake_get(monkeypatch, content: bytes, content_type: str = "image/jpeg"):
    monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(content, content_type))


def test_store_content_addressed(tmp_path, monkeypatch):
    _fake_get(monkeypatch, b"hello image bytes", "image/png")

    url = images.store("https://cdn.example/a.jpg")

    sha = hashlib.sha256(b"hello image bytes").hexdigest()
    assert url == f"/images/{sha}.png"
    assert (tmp_path / "images" / f"{sha}.png").read_bytes() == b"hello image bytes"


def test_store_dedupes_same_bytes(tmp_path, monkeypatch):
    _fake_get(monkeypatch, b"same bytes")

    a = images.store("https://cdn.example/one.jpg")
    b = images.store("https://cdn.example/two.jpg")

    assert a == b  # content-addressed
    assert len(list((tmp_path / "images").iterdir())) == 1


def test_store_falls_back_to_img_extension(tmp_path, monkeypatch):
    _fake_get(monkeypatch, b"x", "application/octet-stream")

    url = images.store("https://cdn.example/noext")

    assert url.endswith(".img")


def test_resolve_guards_traversal():
    assert images.resolve("not-valid") is None
    assert images.resolve("../etc/passwd") is None
    assert images.resolve("A" * 64 + ".jpg") is None  # uppercase rejected
    assert images.resolve("a" * 64 + ".jpg") is not None


def test_host_images_rewrites_urls():
    events = [ScrapedEvent(uid="u1", title="E", images=[ImageRef(url="https://cdn.example/a.jpg")])]

    images.host_images(events)

    img = events[0].images[0]
    assert img.url.startswith("/images/")
    assert img.source_url == "https://cdn.example/a.jpg"


def test_host_images_skips_already_hosted():
    events = [
        ScrapedEvent(
            uid="u1", title="E",
            images=[ImageRef(url="/images/abc.jpg", source_url="https://cdn.example/a.jpg")],
        )
    ]

    images.host_images(events)

    img = events[0].images[0]
    assert img.url == "/images/abc.jpg"
    assert img.source_url == "https://cdn.example/a.jpg"


def test_images_endpoint_serves_file(tmp_path):
    from robyn.testing import TestClient

    from app.public import app

    filename = "a" * 64 + ".jpg"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / filename).write_bytes(b"fake-jpeg-bytes")

    client = TestClient(app)

    assert client.get(f"/images/{filename}").status_code == 200
    assert client.get("/images/" + "a" * 64 + ".png").status_code == 404  # missing file
    assert client.get("/images/not-valid").status_code == 404  # traversal guard
#endregion


#region: F18.01 — GC + re-host
def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gc.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_images(engine, images_json, *, archived_at=None):
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            Event(id="e", source_id=src.id, title="E", images=images_json, archived_at=archived_at)
        )
        session.commit()


def test_is_local(tmp_path):
    fn = "a" * 64 + ".jpg"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / fn).write_bytes(b"x")

    assert images.is_local(f"/images/{fn}") is True
    assert images.is_local(f"/images/{'b' * 64}.jpg") is False
    assert images.is_local("https://cdn.example/a.jpg") is False


def test_prune_deletes_orphans(tmp_path):
    engine = _engine(tmp_path)
    fn_kept = "a" * 64 + ".jpg"
    fn_orphan = "b" * 64 + ".jpg"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / fn_kept).write_bytes(b"kept")
    (tmp_path / "images" / fn_orphan).write_bytes(b"orphan")

    _seed_images(engine, dump_images([ImageRef(url=f"/images/{fn_kept}")]))

    with Session(engine) as session:
        result = images.prune(session, dry_run=True)

    assert result["dry_run"] is True
    assert result["orphan_count"] == 1
    assert fn_orphan in result["preview"]
    assert (tmp_path / "images" / fn_orphan).exists()  # dry-run leaves it

    with Session(engine) as session:
        result = images.prune(session, dry_run=False)

    assert result["orphan_count"] == 1
    assert not (tmp_path / "images" / fn_orphan).exists()
    assert (tmp_path / "images" / fn_kept).exists()


def test_prune_deletes_archived_only_images(tmp_path):
    engine = _engine(tmp_path)
    fn = "c" * 64 + ".png"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / fn).write_bytes(b"x")

    _seed_images(engine, dump_images([ImageRef(url=f"/images/{fn}")]), archived_at=datetime(2026, 1, 1))

    with Session(engine) as session:
        result = images.prune(session, dry_run=False)

    assert result["orphan_count"] == 1
    assert not (tmp_path / "images" / fn).exists()


def test_rehost_missing_images_re_downloads(tmp_path, monkeypatch):
    _fake_get(monkeypatch, b"rehost bytes", "image/png")
    sha = hashlib.sha256(b"rehost bytes").hexdigest()
    fn = f"{sha}.png"

    img = ImageRef(url=f"/images/{fn}", source_url="https://cdn.example/a.jpg")
    out = images.rehost_missing_images([img])

    assert out[0].url == f"/images/{fn}"
    assert (tmp_path / "images" / fn).read_bytes() == b"rehost bytes"


def test_rehost_skips_present_file(tmp_path, monkeypatch):
    fn = "a" * 64 + ".jpg"
    (tmp_path / "images").mkdir(parents=True, exist_ok=True)
    (tmp_path / "images" / fn).write_bytes(b"existing")

    img = ImageRef(url=f"/images/{fn}", source_url="https://cdn.example/a.jpg")
    out = images.rehost_missing_images([img])

    assert out[0].url == f"/images/{fn}"
    assert (tmp_path / "images" / fn).read_bytes() == b"existing"


def test_rehost_skips_external_and_missing_source(tmp_path, monkeypatch):
    ext = ImageRef(url="https://cdn.example/a.jpg", source_url=None)
    local_no_src = ImageRef(url=f"/images/{'b' * 64}.jpg", source_url=None)
    out = images.rehost_missing_images([ext, local_no_src])

    assert out[0].url == "https://cdn.example/a.jpg"
    assert out[1].url == f"/images/{'b' * 64}.jpg"
#endregion
