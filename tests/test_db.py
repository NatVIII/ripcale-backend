from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Event, Source


def test_create_and_query(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        source = Source(name="Test", url="https://example.com/feed.ics")
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id

        event = Event(id="evt-1", source_id=source_id, title="Test Event")
        session.add(event)
        session.commit()

    with Session(engine) as session:
        result = session.exec(select(Event)).all()
        assert len(result) == 1
        assert result[0].title == "Test Event"
        assert result[0].source_id == source_id


def test_event_defaults(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'defaults.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        source = Source(name="S", url="https://example.com/feed.ics")
        session.add(source)
        session.commit()
        session.refresh(source)

        event = Event(id="evt-2", source_id=source.id, title="Plain")
        session.add(event)
        session.commit()

        saved = session.exec(select(Event)).one()
        assert saved.all_day is False
        assert saved.categories == ""
        assert saved.rrule is None
