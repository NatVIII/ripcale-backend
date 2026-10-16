"""Tests for the LLM pipeline (F65): transcribe, decide, apply, process_one."""
#region: imports
from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from app.models import Event, PendingPost, Source
from app.schema import ImageRef, dump_images
from app.services import llm
from app.services.llm import Decision, EventFields, RecurrenceFields
#endregion


def _setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'llm.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(llm, "engine", engine)
    return engine


def _source(engine):
    with Session(engine) as session:
        src = Source(name="Test", url="https://x", gatherer="hikerapi")
        session.add(src)
        session.commit()
        session.refresh(src)
        return src.id


def _post(session, source_id, uid="p1"):
    post = PendingPost(
        uid=uid,
        source_id=source_id,
        url="https://www.instagram.com/p/X/",
        caption="caption",
        images=dump_images([ImageRef(url="https://cdn.example/a.jpg")]),
    )
    session.add(post)
    session.commit()
    return post


def test_apply_decision_create(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        decision = Decision(
            action="create",
            event=EventFields(
                title="Monday Ride", location="O-Hill",
                start_at="2026-09-21T18:00:00-04:00",
                end_at="2026-09-21T20:00:00-04:00",
                timezone="America/New_York", categories=["ride"],
            ),
        )
        llm.apply_decision(session, post, decision)
        session.commit()
        assert post.status == "created"
        event = session.exec(select(Event)).first()
        assert event.title == "Monday Ride"
        assert event.pinned is True
        assert event.start_at == datetime(2026, 9, 21, 22, 0)  # 18:00 -04:00 = 22:00 UTC


def test_apply_decision_modify(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        session.add(Event(id="e1", source_id=sid, uid="p1", title="Old", start_at=datetime(2026, 9, 21, 22, 0)))
        session.commit()
        post = _post(session, sid)
        decision = Decision(
            action="modify", match_id="e1",
            event=EventFields(title="New Title", categories=[]),
        )
        llm.apply_decision(session, post, decision)
        session.commit()
        assert post.status == "modified"
        event = session.get(Event, "e1")
        assert event.title == "New Title"
        assert event.pinned is True


def test_apply_decision_ignore(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        llm.apply_decision(session, post, Decision(action="ignore", reason="nope"))
        session.commit()
        assert post.status == "ignored"
        assert session.exec(select(Event)).all() == []


def test_decide_parses_json(monkeypatch):
    monkeypatch.setattr(
        llm.deepseek, "chat",
        lambda messages, json_mode=False, **kwargs: '{"action":"ignore","reason":"nope"}',
    )
    decision = llm.decide("text", "caption", [])
    assert decision.action == "ignore"


def test_decide_uses_non_thinking(monkeypatch):
    captured = {}

    def fake_chat(messages, **kwargs):
        captured.update(kwargs)
        return '{"action":"ignore","reason":"nope"}'

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.decide("text", "caption", [])
    assert captured["thinking"] is False
    assert captured["json_mode"] is True


def test_decision_tolerates_null_fields():
    decision = Decision.model_validate_json(
        '{"action":"create","event":{"title":"X","all_day":null,"categories":null},"reason":""}'
    )
    assert decision.event.all_day is False
    assert decision.event.categories == []


def test_decide_includes_context_and_today(monkeypatch):
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return '{"action":"ignore","reason":"nope"}'

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.decide("text", "caption", [], context="rides every Monday 6:30pm ET")
    assert "Source context" in captured["user"]
    assert "rides every Monday 6:30pm ET" in captured["user"]
    assert "Today's date is" in captured["user"]


def test_decide_without_context_omits_block(monkeypatch):
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return '{"action":"ignore","reason":"nope"}'

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.decide("text", "caption", [])
    assert "Source context" not in captured["user"]
    assert "Today's date is" in captured["user"]


def test_process_one_passes_source_context(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid = _source(engine)
    with Session(engine) as session:
        src = session.get(Source, sid)
        src.llm_context = "rides Monday 6:30pm"
        session.commit()
        uid = _post(session, sid).uid

    captured = {}

    def fake_chat(messages, **kwargs):
        if kwargs.get("json_mode"):
            captured["user"] = messages[-1]["content"]
            return '{"action":"create","event":{"title":"X","categories":[]},"reason":"flyer"}'
        return "transcription"

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.process_one(uid)

    assert "rides Monday 6:30pm" in captured["user"]


def test_decide_includes_publish_date_and_relative_instruction(monkeypatch):
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return '{"action":"ignore","reason":"nope"}'

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.decide("text", "caption", [], published_at=datetime(2026, 10, 5, 16, 32))
    assert "This post was published on" in captured["user"]
    assert "relative to the post's publish date" in captured["user"]


def test_decide_without_publish_date_notes_unknown(monkeypatch):
    captured = {}

    def fake_chat(messages, **kwargs):
        captured["user"] = messages[1]["content"]
        return '{"action":"ignore","reason":"nope"}'

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.decide("text", "caption", [])
    assert "publish time is unknown" in captured["user"]


def test_process_one_passes_published_at(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid = _source(engine)
    with Session(engine) as session:
        uid = _post(session, sid).uid
        post = session.get(PendingPost, uid)
        post.published_at = datetime(2026, 10, 5, 16, 32)
        session.commit()

    captured = {}

    def fake_chat(messages, **kwargs):
        if kwargs.get("json_mode"):
            captured["user"] = messages[-1]["content"]
            return '{"action":"create","event":{"title":"X","categories":[]},"reason":"flyer"}'
        return "transcription"

    monkeypatch.setattr(llm.deepseek, "chat", fake_chat)
    llm.process_one(uid)

    assert "2026-10-05" in captured["user"]


def test_process_one_end_to_end(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid = _source(engine)
    with Session(engine) as session:
        uid = _post(session, sid).uid

    monkeypatch.setattr(
        llm.deepseek, "chat",
        lambda messages, json_mode=False, **kwargs: (
            '{"action":"create","event":{"title":"Monday Ride",'
            '"start_at":"2026-09-21T18:00:00-04:00","timezone":"America/New_York",'
            '"categories":[]},"reason":"flyer"}'
            if json_mode
            else "Monday Ride 6pm at O-Hill"
        ),
    )

    llm.process_one(uid)

    with Session(engine) as session:
        post = session.get(PendingPost, uid)
        assert post.status == "created"
        assert post.transcription == "Monday Ride 6pm at O-Hill"
        event = session.exec(select(Event)).first()
        assert event.title == "Monday Ride"
        assert event.pinned is True
#endregion


def test_apply_decision_uses_normalized_categories(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "normalize_proposed", lambda names: ["external:art"])
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        decision = Decision(action="create", event=EventFields(title="X", categories=["art", "madeup"]))
        llm.apply_decision(session, post, decision)
        session.commit()
        event = session.exec(select(Event)).first()
        assert event.categories == "external:art"


def test_transient_failure_retries_then_caps(tmp_path, monkeypatch):
    from app.services import deepseek as deepseek_mod

    engine = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(llm.settings, "llm_max_attempts", 2)
    sid = _source(engine)
    with Session(engine) as session:
        uid = _post(session, sid).uid

    def boom(messages, **kwargs):
        raise deepseek_mod.DeepSeekTransient("transient boom")

    monkeypatch.setattr(llm.deepseek, "chat", boom)

    llm.process_one(uid)
    with Session(engine) as session:
        p = session.get(PendingPost, uid)
        assert p.status == "pending"
        assert p.attempts == 1

    llm.process_one(uid)
    with Session(engine) as session:
        p = session.get(PendingPost, uid)
        assert p.status == "failed"
        assert "transient boom" in (p.error or "")


def test_permanent_failure_marks_failed_with_error(tmp_path, monkeypatch):
    from app.services import deepseek as deepseek_mod

    engine = _setup(tmp_path, monkeypatch)
    sid = _source(engine)
    with Session(engine) as session:
        uid = _post(session, sid).uid

    def boom(messages, **kwargs):
        raise deepseek_mod.DeepSeekPermanent("bad key")

    monkeypatch.setattr(llm.deepseek, "chat", boom)

    llm.process_one(uid)
    with Session(engine) as session:
        p = session.get(PendingPost, uid)
        assert p.status == "failed"
        assert "bad key" in (p.error or "")
#endregion


#region: F66.03 — new decision actions
def test_apply_delete_archives_event(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        session.add(Event(id="e1", source_id=sid, uid="old", title="Old Ride"))
        session.commit()

        llm.apply_decision(session, post, Decision(action="delete", match_id="e1"))
        session.commit()

        assert session.get(Event, "e1").archived_at is not None
        assert session.get(Event, "e1").archived_reason == "cancelled"
        assert post.status == "deleted"


def test_apply_delete_occurrence_adds_exdate(tmp_path, monkeypatch):
    from app.schema import load_exdates

    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        master = Event(id="master", source_id=sid, uid="recurrence:abc", title="Weekly", rrule="FREQ=WEEKLY;BYDAY=MO", placeholder=True)
        session.add(master)
        session.commit()

        llm.apply_decision(session, post, Decision(action="delete", match_id="master", recurrence_id="2026-10-26T18:30:00-04:00"))
        session.commit()

        assert len(load_exdates(session.get(Event, "master").exdates)) == 1
        assert session.get(Event, "master").archived_at is None  # series survives
        assert post.status == "deleted"


def test_apply_modify_override_creates_occurrence_override(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        master = Event(id="master", source_id=sid, uid="recurrence:abc", title="Weekly Ride", rrule="FREQ=WEEKLY;BYDAY=MO", start_at=datetime(2026, 10, 19, 22, 30), placeholder=True, pinned=True)
        session.add(master)
        session.commit()

        decision = Decision(
            action="modify", match_id="master", recurrence_id="2026-10-26T18:30:00-04:00",
            event=EventFields(title="River Jaunt", location="O-Hill", start_at="2026-10-26T18:30:00-04:00", timezone="America/New_York"),
        )
        llm.apply_decision(session, post, decision)
        session.commit()

        overrides = session.exec(select(Event).where(Event.uid == "recurrence:abc", Event.recurrence_id.is_not(None))).all()
        assert len(overrides) == 1
        assert overrides[0].title == "River Jaunt"
        assert post.status == "modified"


def test_apply_modify_rejects_bad_recurrence_id(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        master = Event(id="master", source_id=sid, uid="recurrence:abc", title="Weekly", rrule="FREQ=WEEKLY;BYDAY=MO", start_at=datetime(2026, 10, 19, 22, 30), placeholder=True, pinned=True)
        session.add(master)
        session.commit()

        # Tuesday is NOT an occurrence of a Monday series
        decision = Decision(action="modify", match_id="master", recurrence_id="2026-10-27T22:30:00Z", event=EventFields(title="Ride", start_at="2026-10-27T22:30:00Z"))
        llm.apply_decision(session, post, decision)
        session.commit()

        assert post.status == "failed"
        assert "not an occurrence" in (post.error or "")


def test_apply_modify_rejects_master_without_recurrence_id(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        master = Event(id="master", source_id=sid, uid="recurrence:abc", title="Weekly", rrule="FREQ=WEEKLY;BYDAY=MO", start_at=datetime(2026, 10, 19, 22, 30), placeholder=True)
        session.add(master)
        session.commit()

        # modify WITHOUT recurrence_id targeting the recurring master → must not mutate it
        llm.apply_decision(session, post, Decision(action="modify", match_id="master", event=EventFields(title="Changed")))
        session.commit()

        assert post.status == "failed"
        assert "recurrence_id" in (post.error or "")
        assert session.get(Event, "master").title == "Weekly"


def test_apply_delete_rejects_bad_recurrence_id(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        master = Event(id="master", source_id=sid, uid="recurrence:abc", title="Weekly", rrule="FREQ=WEEKLY;BYDAY=MO", start_at=datetime(2026, 10, 19, 22, 30), placeholder=True)
        session.add(master)
        session.commit()

        decision = Decision(action="delete", match_id="master", recurrence_id="2026-10-28T22:30:00Z")
        llm.apply_decision(session, post, decision)
        session.commit()

        assert post.status == "failed"
        assert "not an occurrence" in (post.error or "")


def test_apply_create_is_idempotent_on_reprocess(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        decision = Decision(action="create", event=EventFields(title="Ride", start_at="2026-10-19T18:00:00-04:00", timezone="America/New_York"))
        llm.apply_decision(session, post, decision)
        session.commit()
        llm.apply_decision(session, post, decision)  # re-process same post — must not collide
        session.commit()

        assert len(session.exec(select(Event)).all()) == 1
        assert post.status == "created"


def test_apply_add_recurrence_creates_proposal(tmp_path, monkeypatch):
    from app.models import Approval

    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        decision = Decision(
            action="add_recurrence",
            recurrence=RecurrenceFields(title="Weekly", rrule="FREQ=WEEKLY;BYDAY=MO", start_at="2026-10-19T18:30:00-04:00", timezone="America/New_York"),
            reason="weekly ride",
        )
        llm.apply_decision(session, post, decision)
        session.commit()

        assert post.status == "proposed"
        approval = session.exec(select(Approval)).one()
        assert approval.kind == "recurrence_add"
        assert approval.status == "pending"


def test_apply_add_recurrence_rejects_invalid_rrule(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        decision = Decision(
            action="add_recurrence",
            recurrence=RecurrenceFields(title="Weekly", rrule="NOT-A-RULE", start_at="2026-10-19T18:30:00-04:00"),
        )
        llm.apply_decision(session, post, decision)
        session.commit()

        assert post.status == "failed"
        assert "invalid rrule" in (post.error or "")


def test_apply_remove_recurrence_creates_proposal(tmp_path, monkeypatch):
    from app.models import Approval

    engine = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        sid = _source(engine)
        post = _post(session, sid)
        decision = Decision(action="remove_recurrence", recurrence=RecurrenceFields(title="Weekly"))
        llm.apply_decision(session, post, decision)
        session.commit()

        assert post.status == "proposed"
        approval = session.exec(select(Approval)).one()
        assert approval.kind == "recurrence_remove"


def test_current_recurrences_reads_intake(tmp_path, monkeypatch):
    from app.config import settings
    from app.intake import IntakeSettings, save
    from app.schema import RecurrenceConfig, SourceConfig

    monkeypatch.setattr(settings, "intake_file", str(tmp_path / "intake.yaml"))
    save(
        IntakeSettings(
            sources=[SourceConfig(name="S", gatherer="hikerapi", url="https://x",
                                  recurrences=[RecurrenceConfig(title="Weekly", rrule="FREQ=WEEKLY;BYDAY=MO", start_at="2026-10-19T18:30:00-04:00", timezone="America/New_York")])]
        )
    )

    assert llm.current_recurrences("S")[0]["title"] == "Weekly"
    assert llm.current_recurrences("missing") == []


def test_decide_parses_new_actions(monkeypatch):
    monkeypatch.setattr(llm.deepseek, "chat", lambda messages, **kw: '{"action":"delete","match_id":"e1","reason":"cancelled"}')
    assert llm.decide("t", "c", []).action == "delete"

    monkeypatch.setattr(llm.deepseek, "chat", lambda messages, **kw: '{"action":"add_recurrence","recurrence":{"title":"W","rrule":"FREQ=WEEKLY;BYDAY=MO","start_at":"2026-10-19T18:30:00-04:00"}}')
    d = llm.decide("t", "c", [])
    assert d.action == "add_recurrence"
    assert d.recurrence.title == "W"
#endregion
