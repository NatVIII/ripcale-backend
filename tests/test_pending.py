"""Tests for the pending-post enqueue stage (F65)."""
#region: imports
from sqlmodel import Session, SQLModel, create_engine

from app.models import PendingPost, Source
from app.schema import GathererResult, ScrapedEvent, SourceConfig
from app.services.pending import enqueue
#endregion


def _post(uid, caption, images=None):
    return ScrapedEvent(
        uid=uid, title=caption, description=caption, images=images or [],
    )


def test_enqueue_new_changed_unchanged(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'pending.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="hikerapi", url="https://x")

    with Session(engine) as session:
        src = Source(name="Test", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        sid = src.id

        result = enqueue(session, src, GathererResult(source=cfg, events=[_post("u1", "caption A")]))
        session.commit()
        assert result == {"enqueued": 1, "changed": 0, "unchanged": 0}

    with Session(engine) as session:
        src = session.get(Source, sid)
        result = enqueue(session, src, GathererResult(source=cfg, events=[_post("u1", "caption A")]))
        session.commit()
        assert result["unchanged"] == 1

    with Session(engine) as session:
        src = session.get(Source, sid)
        result = enqueue(session, src, GathererResult(source=cfg, events=[_post("u1", "caption B")]))
        session.commit()
        assert result["changed"] == 1

    with Session(engine) as session:
        p = session.get(PendingPost, "u1")
        assert p.caption == "caption B"
        assert p.status == "pending"


def test_enqueue_skips_missing_uid(tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'pending2.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="hikerapi", url="https://x")

    with Session(engine) as session:
        src = Source(name="Test", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        result = enqueue(
            session, src,
            GathererResult(source=cfg, events=[ScrapedEvent(title="no uid", description="x")]),
        )
        session.commit()
    assert result["enqueued"] == 0
#endregion


def test_enqueue_stores_published_at(tmp_path, monkeypatch):
    from datetime import datetime

    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'pub.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="hikerapi", url="https://x")

    pub = datetime(2026, 10, 5, 16, 32)
    with Session(engine) as session:
        src = Source(name="Test", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        event = ScrapedEvent(uid="u1", title="ride", description="ride", start_at=pub)
        enqueue(session, src, GathererResult(source=cfg, events=[event]))
        session.commit()

    with Session(engine) as session:
        assert session.get(PendingPost, "u1").published_at == pub


def test_enqueue_unchanged_when_only_source_url_differs(tmp_path, monkeypatch):
    from app.config import settings
    from app.schema import ImageRef

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'churn.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = SourceConfig(name="Test", gatherer="hikerapi", url="https://x")

    with Session(engine) as session:
        src = Source(name="Test", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        sid = src.id

        img1 = ImageRef(url="/images/abc.jpg", source_url="https://signed1.example/x.jpg")
        enqueue(session, src, GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="x", description="x", images=[img1])]))
        session.commit()

    with Session(engine) as session:
        src = session.get(Source, sid)
        img2 = ImageRef(url="/images/abc.jpg", source_url="https://signed2.example/y.jpg")
        result = enqueue(session, src, GathererResult(source=cfg, events=[ScrapedEvent(uid="u1", title="x", description="x", images=[img2])]))
        session.commit()
        assert result["unchanged"] == 1  # source_url churn must not mark the post changed


def test_reset_stale_processing(tmp_path, monkeypatch):
    from datetime import datetime

    from app.config import settings
    from app.services.pending import reset_stale_processing

    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    engine = create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="Test", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(PendingPost(uid="p1", source_id=src.id, status="processing", updated_at=datetime(2020, 1, 1)))
        session.add(PendingPost(uid="p2", source_id=src.id, status="processing"))
        session.commit()

    with Session(engine) as session:
        reset = reset_stale_processing(session, 600)
        session.commit()

    assert reset == 1
    with Session(engine) as session:
        assert session.get(PendingPost, "p1").status == "pending"   # stale -> reset
        assert session.get(PendingPost, "p2").status == "processing"  # recent -> untouched
#endregion
