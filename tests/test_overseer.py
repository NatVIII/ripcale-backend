"""Tests for the overseer detection layer (F67.01)."""
#region: imports
from datetime import datetime, timedelta

from sqlmodel import Session, SQLModel, create_engine

from app.models import Event, Source
from app.services import overseer
#endregion


NOW = datetime(2026, 10, 15, 12, 0)  # naive UTC


def _setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'overseer.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(overseer, "clock_now", lambda: NOW)
    return engine


def _source(engine, name):
    with Session(engine) as session:
        src = Source(name=name, url="https://x", gatherer="ics")
        session.add(src)
        session.commit()
        session.refresh(src)
        return src.id


def _seed(engine, sid, events):
    with Session(engine) as session:
        for e in events:
            session.add(Event(id=e["id"], source_id=sid, uid=e["id"], title=e["title"], start_at=e["start_at"], **e.get("kw", {})))
        session.commit()


#region: completeness score
def test_completeness_score_richer_is_higher():
    poor = Event(id="p", source_id=1, uid="p", title="X")
    rich = Event(
        id="r", source_id=1, uid="r", title="X",
        description="d" * 200, location="L", url="https://x",
        end_at=NOW + timedelta(hours=2),
        images='[{"url":"/images/a.jpg"},{"url":"/images/b.jpg"}]',
    )
    assert overseer.completeness_score(rich) > overseer.completeness_score(poor)
    assert overseer.completeness_score(poor) == 0.0


def test_title_similarity():
    assert overseer.title_similarity("River Jaunt", "river jaunt") > 0.9
    assert overseer.title_similarity("River Jaunt", "Painting Workshop") < 0.5
    assert overseer.title_similarity("", "River") == 0.0
    assert overseer.title_similarity(None, None) == 0.0
#endregion


#region: candidate pairs
def test_find_candidate_pairs_cross_source(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid1 = _source(engine, "A")
    sid2 = _source(engine, "B")
    _seed(engine, sid1, [{"id": "e1", "title": "River Jaunt Ride", "start_at": NOW + timedelta(days=3)}])
    _seed(engine, sid2, [{"id": "e2", "title": "River Jaunt!", "start_at": NOW + timedelta(days=3, hours=2)}])

    with Session(engine) as session:
        pairs = overseer.find_candidate_pairs(session, window_days=14)

    assert len(pairs) == 1
    assert {pairs[0][0].id, pairs[0][1].id} == {"e1", "e2"}


def test_find_candidate_pairs_excludes_same_source(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid = _source(engine, "A")
    _seed(engine, sid, [
        {"id": "e1", "title": "River Jaunt", "start_at": NOW + timedelta(days=3)},
        {"id": "e2", "title": "River Jaunt", "start_at": NOW + timedelta(days=3, hours=1)},
    ])

    with Session(engine) as session:
        assert overseer.find_candidate_pairs(session, window_days=14) == []


def test_find_candidate_pairs_excludes_dissimilar_titles(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid1 = _source(engine, "A")
    sid2 = _source(engine, "B")
    _seed(engine, sid1, [{"id": "e1", "title": "River Jaunt", "start_at": NOW + timedelta(days=3)}])
    _seed(engine, sid2, [{"id": "e2", "title": "Screenprinting 101", "start_at": NOW + timedelta(days=3, hours=1)}])

    with Session(engine) as session:
        assert overseer.find_candidate_pairs(session, window_days=14) == []


def test_find_candidate_pairs_excludes_distant_times(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid1 = _source(engine, "A")
    sid2 = _source(engine, "B")
    _seed(engine, sid1, [{"id": "e1", "title": "River Jaunt", "start_at": NOW + timedelta(days=3)}])
    _seed(engine, sid2, [{"id": "e2", "title": "River Jaunt", "start_at": NOW + timedelta(days=10)}])

    with Session(engine) as session:
        assert overseer.find_candidate_pairs(session, window_days=14) == []


def test_find_candidate_pairs_excludes_placeholder_redirect_archived(tmp_path, monkeypatch):
    engine = _setup(tmp_path, monkeypatch)
    sid1 = _source(engine, "A")
    sid2 = _source(engine, "B")
    # a valid cross-source pair
    _seed(engine, sid1, [{"id": "good1", "title": "River Jaunt", "start_at": NOW + timedelta(days=3)}])
    _seed(engine, sid2, [{"id": "good2", "title": "River Jaunt", "start_at": NOW + timedelta(days=3, hours=1)}])
    # excluded variants on a third source
    _seed(engine, sid2, [
        {"id": "ph", "title": "River Jaunt", "start_at": NOW + timedelta(days=3), "kw": {"placeholder": True}},
        {"id": "redir", "title": "River Jaunt", "start_at": NOW + timedelta(days=3), "kw": {"redirect_to_id": "good1"}},
        {"id": "arch", "title": "River Jaunt", "start_at": NOW + timedelta(days=3), "kw": {"archived_at": NOW}},
    ])

    with Session(engine) as session:
        pairs = overseer.find_candidate_pairs(session, window_days=14)

    assert len(pairs) == 1
    assert {pairs[0][0].id, pairs[0][1].id} == {"good1", "good2"}
#endregion


#region: worker smoke
def test_worker_run_once_finds_pairs(tmp_path, monkeypatch):
    from app.services import overseer_worker

    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(overseer_worker, "engine", engine)
    monkeypatch.setattr(overseer_worker.settings, "overseer_enabled", True)
    monkeypatch.setattr(overseer_worker.settings, "deepseek_key", "test-key")
    monkeypatch.setattr(overseer, "clock_now", lambda: NOW)
    monkeypatch.setattr(overseer, "decide_pair", lambda a, b, source_names=None: overseer.PairDecision(same=True, canonical_id=a.id))

    sid1 = _source(engine, "A")
    sid2 = _source(engine, "B")
    _seed(engine, sid1, [{"id": "e1", "title": "River Jaunt", "start_at": NOW + timedelta(days=3)}])
    _seed(engine, sid2, [{"id": "e2", "title": "River Jaunt", "start_at": NOW + timedelta(days=3, hours=1)}])

    res = overseer_worker.run_once()
    assert res["enabled"] is True
    assert res["reason"] is None
    assert res["pairs"] == 1
    assert res["decisions"] == [{"same": True, "canonical_id": "e1", "enrich": {}, "reason": ""}]


def test_worker_disabled_without_flag(tmp_path, monkeypatch):
    from app.services import overseer_worker

    engine = create_engine(f"sqlite:///{tmp_path / 'worker2.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(overseer_worker, "engine", engine)
    monkeypatch.setattr(overseer_worker.settings, "overseer_enabled", False)

    res = overseer_worker.run_once()
    assert res["enabled"] is False
    assert res["reason"] == "overseer_enabled is false"


def test_worker_disabled_without_deepseek_key(tmp_path, monkeypatch):
    from app.services import overseer_worker

    engine = create_engine(f"sqlite:///{tmp_path / 'worker3.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(overseer_worker, "engine", engine)
    monkeypatch.setattr(overseer_worker.settings, "overseer_enabled", True)
    monkeypatch.setattr(overseer_worker.settings, "deepseek_key", "")

    res = overseer_worker.run_once()
    assert res["enabled"] is False
    assert res["reason"] == "RIPCALE_DEEPSEEK_KEY is not set"
#endregion


#region: pairwise decision (F67.02)
def _event(eid, title, source_id=1, **kw):
    return Event(id=eid, source_id=source_id, uid=eid, title=title, **kw)


def test_decide_pair_parses_and_validates(monkeypatch):
    a = _event("a", "River Jaunt", source_id=1, location="Park")
    b = _event("b", "River Jaunt", source_id=2)
    monkeypatch.setattr(
        overseer.deepseek, "chat",
        lambda messages, **kw: '{"same": true, "canonical_id": "a", "enrich": {"location": "Park"}, "reason": "dup"}',
    )
    d = overseer.decide_pair(a, b)
    assert d.same is True
    assert d.canonical_id == "a"
    assert d.enrich == {"location": "Park"}


def test_decide_pair_coerces_invalid_canonical(monkeypatch):
    a = _event("a", "X", source_id=1, location="L")  # richer
    b = _event("b", "X", source_id=2)
    monkeypatch.setattr(overseer.deepseek, "chat", lambda m, **k: '{"same": true, "canonical_id": "zzz", "enrich": {}, "reason": "x"}')
    d = overseer.decide_pair(a, b)
    assert d.same is True
    assert d.canonical_id == "a"  # coerced to the more complete event


def test_decide_pair_filters_enrich_fields(monkeypatch):
    a = _event("a", "X", source_id=1)
    b = _event("b", "X", source_id=2)
    monkeypatch.setattr(overseer.deepseek, "chat", lambda m, **k: '{"same": true, "canonical_id": "a", "enrich": {"location": "L", "pinned": "yes"}, "reason": "x"}')
    d = overseer.decide_pair(a, b)
    assert d.enrich == {"location": "L"}  # 'pinned' is not enrichable


def test_decide_pair_not_same_clears(monkeypatch):
    a = _event("a", "X", source_id=1)
    b = _event("b", "X", source_id=2)
    monkeypatch.setattr(overseer.deepseek, "chat", lambda m, **k: '{"same": false, "canonical_id": "a", "enrich": {"location": "L"}, "reason": "distinct"}')
    d = overseer.decide_pair(a, b)
    assert d.same is False
    assert d.canonical_id is None
    assert d.enrich == {}
#endregion


#region: elevate / redirect (F67.03)
def test_propose_merge_creates_and_dedupes(tmp_path):
    from sqlmodel import select

    from app.models import Approval

    engine = create_engine(f"sqlite:///{tmp_path / 'merge.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        winner = _event("w", "River Jaunt", source_id=1, location="Park")
        loser = _event("l", "River Jaunt", source_id=2)
        session.add(winner)
        session.add(loser)
        session.commit()

        assert overseer.propose_merge(session, winner, loser, {"location": "Park"}, "dup") is True
        assert overseer.propose_merge(session, winner, loser, {"location": "Park"}, "dup") is False  # deduped
        session.commit()

        rows = session.exec(select(Approval)).all()
        assert len(rows) == 1
        assert rows[0].kind == "event_merge"
        assert rows[0].status == "pending"


def test_apply_event_merge_end_to_end(tmp_path, monkeypatch):
    from app.services import approvals

    engine = create_engine(f"sqlite:///{tmp_path / 'merge_e2e.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(approvals, "engine", engine)

    with Session(engine) as session:
        session.add(_event("w", "River Jaunt", source_id=1))            # winner, missing location
        session.add(_event("l", "River Jaunt", source_id=2, location="Park"))  # loser, has location
        session.commit()

    aid = approvals.create(
        "event_merge", source_name="",
        payload={"canonical_id": "w", "loser_id": "l", "enrich": {"location": "Park"}},
        reason="dup",
    )
    assert approvals.approve(aid) is True

    with Session(engine) as session:
        winner = session.get(Event, "w")
        loser = session.get(Event, "l")
        assert winner.pinned is True
        assert winner.location == "Park"          # enriched from loser
        assert loser.redirect_to_id == "w"        # redirected


def test_apply_event_merge_only_fills_missing(tmp_path, monkeypatch):
    from app.services import approvals

    engine = create_engine(f"sqlite:///{tmp_path / 'merge_missing.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(approvals, "engine", engine)

    with Session(engine) as session:
        session.add(_event("w", "River Jaunt", source_id=1, location="Original Park"))
        session.add(_event("l", "River Jaunt", source_id=2, location="Different Park", description="desc"))
        session.commit()

    aid = approvals.create(
        "event_merge", source_name="",
        payload={"canonical_id": "w", "loser_id": "l", "enrich": {"location": "Different Park", "description": "desc"}},
        reason="dup",
    )
    approvals.approve(aid)

    with Session(engine) as session:
        winner = session.get(Event, "w")
        assert winner.location == "Original Park"  # NOT overwritten (already present)
        assert winner.description == "desc"        # gap filled
        assert winner.pinned is True
        assert session.get(Event, "l").redirect_to_id == "w"
#endregion


#region: observability (F67.04)
def test_actions_overseer_status_and_run(monkeypatch):
    from app.services import actions, overseer_worker

    monkeypatch.setattr(overseer_worker, "status", lambda: {"enabled": True, "scanned": 1})
    monkeypatch.setattr(overseer_worker, "run_once", lambda: {"pairs": 2, "merges": 1})

    assert actions.overseer_status() == {"enabled": True, "scanned": 1}
    assert actions.overseer_run() == {"pairs": 2, "merges": 1}


def test_debug_overseer_route(tmp_path, monkeypatch):
    from robyn.testing import TestClient

    from app.admin import app
    from app.security import debug_csrf_token
    from app.services import approvals, overseer_worker

    engine = create_engine(f"sqlite:///{tmp_path / 'route.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(approvals, "engine", engine)
    monkeypatch.setattr(overseer_worker.settings, "overseer_enabled", True)
    monkeypatch.setattr(overseer_worker.settings, "deepseek_key", "test-key")
    monkeypatch.setattr(overseer_worker, "run_once", lambda: {"pairs": 0, "merges": 0, "decisions": [], "enabled": True, "reason": None})

    client = TestClient(app)

    r = client.get("/debug/overseer")
    assert r.status_code == 200
    assert "overseer" in r.text

    r = client.post("/debug/overseer", form_data={"csrf_token": debug_csrf_token()})
    assert r.status_code == 200
    assert "scan done" in r.text
#endregion
