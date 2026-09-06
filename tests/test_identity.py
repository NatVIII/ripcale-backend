from datetime import datetime

from app.identity import content_hash, stable_id
from app.schema import ImageRef, ScrapedEvent


def make_event(**kw):
    defaults = dict(uid="abc", title="Event", start_at=datetime(2026, 9, 5, 18, 0))
    defaults.update(kw)
    return ScrapedEvent(**defaults)


def test_stable_id_deterministic():
    assert stable_id("src", make_event()) == stable_id("src", make_event())


def test_stable_id_depends_on_source_and_uid():
    assert stable_id("src", make_event(uid="a")) != stable_id("src", make_event(uid="b"))
    assert stable_id("src", make_event()) != stable_id("other", make_event())


def test_stable_id_falls_back_without_uid():
    assert stable_id("src", make_event(uid=None)) == stable_id("src", make_event(uid=None))


def test_content_hash_stable_and_ignores_uid_and_raw():
    assert content_hash(make_event()) == content_hash(make_event())
    assert content_hash(make_event(uid="x")) == content_hash(make_event(uid="y"))
    assert content_hash(make_event(raw={"a": 1})) == content_hash(make_event(raw={"b": 2}))


def test_content_hash_changes_on_content():
    assert content_hash(make_event(title="A")) != content_hash(make_event(title="B"))
    assert content_hash(make_event(categories=["x"])) != content_hash(make_event(categories=["y"]))


def test_content_hash_changes_on_images():
    a = make_event(images=[ImageRef(url="https://x.com/a.jpg")])
    b = make_event(images=[ImageRef(url="https://x.com/b.jpg")])
    assert content_hash(a) != content_hash(b)
