"""Tests for local image hosting (F18)."""
#region: imports
import hashlib

from app.schema import ImageRef, ScrapedEvent
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
