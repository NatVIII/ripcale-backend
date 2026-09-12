from datetime import datetime

from icalendar import Calendar
from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, Source
from app.services.ics import event_to_vevent, events_to_ics


def _make_event(**kw):
    defaults = dict(
        id="e1",
        source_id=1,
        title="Test",
        start_at=datetime(2026, 9, 10, 18, 0),
        end_at=datetime(2026, 9, 10, 20, 0),
        categories="external:art,external:workshop",
        description="<p>hello &amp; welcome</p>",
        location="Studio Two Three",
        url="https://x.com",
        images='[{"url": "https://x.com/img.jpg"}]',
        timezone="America/New_York",
        updated_at=datetime(2026, 9, 1, 0, 0),
    )
    defaults.update(kw)
    return Event(**defaults)


def test_event_to_vevent():
    ical = event_to_vevent(_make_event(), "Studio Two Three").to_ical().decode()
    assert "SUMMARY:Test" in ical
    assert "DTSTART:20260910T180000Z" in ical
    assert "DTEND:20260910T200000Z" in ical
    assert "UID:e1" in ical
    assert "CATEGORIES:external:art,external:workshop" in ical
    assert "LOCATION:Studio Two Three" in ical
    assert "ATTACH:https://x.com/img.jpg" in ical
    assert "X-RVA-SOURCE:Studio Two Three" in ical
    assert "X-RVA-TIMEZONE:America/New_York" in ical
    assert "X-RVA-IMAGE:https://x.com/img.jpg" in ical
    assert "X-ALT-DESC;FMTTYPE=text/html:" in ical
    assert "DESCRIPTION:hello" in ical


def test_event_to_vevent_all_day():
    e = _make_event(
        all_day=True,
        start_at=datetime(2026, 9, 10, 0, 0),
        end_at=datetime(2026, 9, 11, 0, 0),
    )
    ical = event_to_vevent(e).to_ical().decode()
    assert "DTSTART;VALUE=DATE:20260910" in ical
    assert "DTEND;VALUE=DATE:20260911" in ical


def test_event_to_vevent_handles_newlines():
    e = _make_event(description="<div>line one</div>\n<div>line two</div>")
    ical = event_to_vevent(e).to_ical().decode()
    assert "X-ALT-DESC;FMTTYPE=text/html:<div>line one</div> <div>line two</div>" in ical
    assert "DESCRIPTION:line one" in ical


def test_event_to_vevent_multiple_images():
    e = _make_event(
        images='[{"url": "https://x.com/a.jpg"}, {"url": "https://x.com/b.jpg"}]'
    )
    ical = event_to_vevent(e).to_ical().decode()
    assert "ATTACH:https://x.com/a.jpg" in ical
    assert "ATTACH:https://x.com/b.jpg" in ical
    assert "X-RVA-IMAGE:https://x.com/a.jpg" in ical


def test_event_to_vevent_rrule():
    e = _make_event(rrule="FREQ=WEEKLY;BYDAY=MO,WE")
    ical = event_to_vevent(e).to_ical().decode()
    assert "RRULE:FREQ=WEEKLY" in ical
    assert "BYDAY=MO,WE" in ical


def test_event_to_vevent_exdates_and_recurrence_id():
    e = _make_event(
        rrule="FREQ=WEEKLY",
        exdates='["2026-09-17T18:00:00"]',
        recurrence_id=datetime(2026, 9, 10, 18, 0),
    )
    ical = event_to_vevent(e).to_ical().decode()
    assert "EXDATE" in ical and "20260917T180000Z" in ical
    assert "RECURRENCE-ID" in ical and "20260910T180000Z" in ical


def test_events_to_ics_parses():
    events = [_make_event(id="e1", title="A"), _make_event(id="e2", title="B")]
    ical_text = events_to_ics(events, {1: "Studio Two Three"})
    cal = Calendar.from_ical(ical_text)
    summaries = [str(c.get("SUMMARY")) for c in cal.subcomponents if c.name == "VEVENT"]
    assert summaries == ["A", "B"]


def test_feed_endpoints(tmp_path, monkeypatch):
    import app.routers.feeds as feeds_mod

    engine = create_engine(f"sqlite:///{tmp_path / 'feed.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        src = Source(name="Studio Two Three", url="https://x")
        session.add(src)
        session.commit()
        session.refresh(src)
        session.add(_make_event(id="e1", source_id=src.id, title="Upcoming", categories="external:art"))
        session.add(_make_event(id="e2", source_id=src.id, title="Music Night", categories="external:music"))
        session.commit()

    monkeypatch.setattr(feeds_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.public import app

    client = TestClient(app)

    r = client.get("/feed.ics")
    assert r.status_code == 200
    assert "SUMMARY:Upcoming" in r.text
    assert "SUMMARY:Music Night" in r.text

    r = client.get("/feed.ics", query_params={"tag": "external:art"})
    assert "SUMMARY:Upcoming" in r.text
    assert "SUMMARY:Music Night" not in r.text

    r = client.get("/events/e1/ics")
    assert r.status_code == 200
    assert "SUMMARY:Upcoming" in r.text
    assert "SUMMARY:Music Night" not in r.text

    r = client.get("/events/nope/ics")
    assert r.status_code == 404
