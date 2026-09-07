"""End-to-end pipeline tests: prove every stage works in one flow.

Walks the full chain — gather -> sieve (sort) -> decide (persist) ->
DB -> JSON API -> ICS — and verifies change detection on re-ingest.
"""
#region: imports
import json
from pathlib import Path

import app.gatherers.elfsight.gatherer as elfsight_gatherer
from sqlmodel import Session, SQLModel, create_engine, select

from app.decisionmaker import apply
from app.ingest import _ensure_source, process_source
from app.models import Event
from app.schema import SourceConfig
from app.sieve import classify
#endregion


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "elfsight_boot.json").read_text())
WIDGET_URL = "https://fake/boot/?w=24ddbed9-c732-4102-abd2-02990fae125b"


def _cfg():
    return SourceConfig(name="Studio Two Three", gatherer="elfsight", url=WIDGET_URL, default_categories=["art"])


def test_full_pipeline_end_to_end(tmp_path, monkeypatch):
    """Fixture -> gather -> sieve -> decide -> DB -> JSON -> ICS."""
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: FIXTURE)

    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = _cfg()

    # -- Stage 1: gather -----------------------------------------
    result = elfsight_gatherer.run(cfg)
    assert len(result.events) == 3
    assert result.events[0].uid == "70e8fcb0-92de-476f-81ec-49d21da955a3"

    # -- Stage 2: sieve (sort, read-only) ---------------------------------
    with Session(engine) as session:
        sieved = classify(session, result)
    assert len(sieved.new) == 3
    assert sieved.unchanged == 0
    assert sieved.new[0].event.categories == ["Film Screenings", "art"]

    # -- Stage 3: decide (persist) ----------------------------------------
    with Session(engine) as session:
        source = _ensure_source(session, cfg)
        report = apply(session, source, sieved)
        session.commit()
    assert report == {"inserted": 3, "updated": 0, "unchanged": 0, "removed": 0}

    # -- Stage 4: DB ------------------------------------------------------
    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 3

    # -- Stage 5: JSON API + ICS ------------------------------------------
    import app.routers.events as events_router_mod
    import app.routers.feeds as feeds_router_mod

    monkeypatch.setattr(events_router_mod, "engine", engine)
    monkeypatch.setattr(feeds_router_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.public import app

    client = TestClient(app)

    data = client.get("/events").json()
    titles = {e["title"] for e in data}
    assert titles == {
        "Steel Magnolias Screening benefitting Oakwood Arts",
        "Beautiful Pigs, Forced Resonance, and the Perry Menestres Big Band",
        "Richmond DSA presents Grief Stricken Winds",
    }

    event_id = data[0]["id"]
    assert client.get(f"/events/{event_id}").json()["id"] == event_id

    feed = client.get("/feed.ics")
    assert feed.status_code == 200
    assert feed.text.count("BEGIN:VEVENT") == 3
    assert f"UID:{event_id}" in feed.text

    single = client.get(f"/events/{event_id}/ics")
    assert single.status_code == 200
    assert f"UID:{event_id}" in single.text


def test_change_detection_on_reingest(tmp_path, monkeypatch):
    """A changed source event is flagged updated, not re-inserted."""
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: FIXTURE)

    engine = create_engine(f"sqlite:///{tmp_path / 'change.db'}")
    SQLModel.metadata.create_all(engine)
    cfg = _cfg()

    # first ingest
    with Session(engine) as session:
        _, report = process_source(session, cfg, elfsight_gatherer.run)
        session.commit()
    assert report == {"inserted": 3, "updated": 0, "unchanged": 0, "removed": 0}

    # mutate one event's title in a deep copy of the fixture
    changed = json.loads(json.dumps(FIXTURE))
    wid = "24ddbed9-c732-4102-abd2-02990fae125b"
    changed["data"]["widgets"][wid]["data"]["settings"]["events"][0]["name"] = "Steel Magnolias CHANGED"
    monkeypatch.setattr(elfsight_gatherer, "fetch_json", lambda url: changed)

    # second ingest
    with Session(engine) as session:
        sieved, report = process_source(session, cfg, elfsight_gatherer.run)
        session.commit()

    assert sieved.unchanged == 2
    assert len(sieved.updated) == 1
    assert sieved.updated[0].changed_fields == ["title"]
    assert report == {"inserted": 0, "updated": 1, "unchanged": 2, "removed": 0}

    with Session(engine) as session:
        assert len(session.exec(select(Event)).all()) == 3


def test_registry_load_sources(monkeypatch):
    """load_sources() returns the configured source list."""
    from app.config import settings
    from app.registry import load_sources

    monkeypatch.setattr(
        settings,
        "sources",
        [SourceConfig(name="X", gatherer="elfsight", url="https://x")],
    )
    srcs = load_sources()
    assert [s.name for s in srcs] == ["X"]
