from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, Source
from app.serializers import to_fullcalendar
from app.services.events import query_events
from app.timeutil import parse_iso_utc


def _make_event(**kw):
    defaults = dict(
        id="e1",
        source_id=1,
        title="T",
        start_at=datetime(2026, 9, 10, 18, 0),
        end_at=datetime(2026, 9, 10, 20, 0),
        all_day=False,
    )
    defaults.update(kw)
    return Event(**defaults)


def test_to_fullcalendar():
    e = _make_event(categories="art,workshop", description="<p>hi</p>", url="https://x")
    out = to_fullcalendar(e, "Studio Two Three")
    assert out["id"] == "e1"
    assert out["title"] == "T"
    assert out["start"] == "2026-09-10T18:00:00Z"
    assert out["end"] == "2026-09-10T20:00:00Z"
    assert out["allDay"] is False
    assert out["url"] == "https://x"
    assert out["extendedProps"]["categories"] == ["art", "workshop"]
    assert out["extendedProps"]["description"] == "<p>hi</p>"
    assert out["extendedProps"]["source"] == "Studio Two Three"


def test_to_fullcalendar_rrule():
    e = _make_event(rrule="FREQ=WEEKLY")
    out = to_fullcalendar(e)
    assert out["extendedProps"]["rrule"] == "FREQ=WEEKLY"


def test_to_fullcalendar_recurrence():
    e = _make_event(
        rrule="FREQ=WEEKLY",
        exdates='["2026-09-17T18:00:00"]',
        recurrence_id=datetime(2026, 9, 10, 18, 0),
    )
    out = to_fullcalendar(e)
    assert out["extendedProps"]["exdates"] == ["2026-09-17T18:00:00"]
    assert out["extendedProps"]["recurrence_id"] == "2026-09-10T18:00:00"


def test_to_fullcalendar_all_day():
    e = _make_event(
        all_day=True,
        start_at=datetime(2026, 9, 10, 0, 0),
        end_at=datetime(2026, 9, 11, 0, 0),
    )
    out = to_fullcalendar(e)
    assert out["allDay"] is True
    assert out["start"] == "2026-09-10"
    assert out["end"] == "2026-09-11"


def test_parse_iso_utc():
    assert parse_iso_utc("2026-09-01T00:00:00Z") == datetime(2026, 9, 1, 0, 0)
    assert parse_iso_utc("2026-09-01T04:00:00-04:00") == datetime(2026, 9, 1, 8, 0)
    assert parse_iso_utc(None) is None
    assert parse_iso_utc("") is None


def test_query_events(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'q.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="S", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(
            _make_event(
                id="past",
                source_id=src.id,
                title="Past",
                start_at=datetime(2020, 1, 1, 0, 0),
                end_at=datetime(2020, 1, 1, 1, 0),
                categories="other",
            )
        )
        session.add(
            _make_event(
                id="now",
                source_id=src.id,
                title="Now",
                categories="art",
            )
        )
        session.commit()

    with Session(engine) as session:
        assert [e.title for e in query_events(session)] == ["Past", "Now"]
        assert [e.title for e in query_events(session, start=datetime(2026, 1, 1))] == ["Now"]
        assert [e.title for e in query_events(session, end=datetime(2025, 1, 1))] == ["Past"]
        assert [e.title for e in query_events(session, category="art")] == ["Now"]
        assert [e.title for e in query_events(session, limit=1)] == ["Past"]


def test_endpoints(tmp_path, monkeypatch):
    import app.routers.events as router_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'api.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="Studio Two Three", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(_make_event(id="e1", source_id=src.id, title="Upcoming", categories="art,workshop"))
        session.add(
            _make_event(
                id="e2",
                source_id=src.id,
                title="Past",
                start_at=datetime(2020, 1, 1, 0, 0),
                end_at=datetime(2020, 1, 1, 1, 0),
                categories="Film Screenings",
            )
        )
        session.commit()

    monkeypatch.setattr(router_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.public import app

    client = TestClient(app)

    r = client.get("/events")
    assert r.status_code == 200
    data = r.json()
    assert [e["title"] for e in data] == ["Past", "Upcoming"]
    assert data[1]["extendedProps"]["categories"] == ["art", "workshop"]
    assert data[1]["extendedProps"]["source"] == "Studio Two Three"

    r = client.get("/events", query_params={"category": "art"})
    assert [e["title"] for e in r.json()] == ["Upcoming"]

    r = client.get("/events", query_params={"category": "Film%20Screenings"})
    assert [e["title"] for e in r.json()] == ["Past"]

    r = client.get(
        "/events",
        query_params={"start": "2026-09-01T00%3A00%3A00Z", "end": "2026-10-01T00%3A00%3A00Z"},
    )
    assert [e["title"] for e in r.json()] == ["Upcoming"]

    r = client.get("/events/e1")
    assert r.status_code == 200
    assert r.json()["title"] == "Upcoming"

    r = client.get("/events/nope")
    assert r.status_code == 404
