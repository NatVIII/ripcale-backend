"""Tests for the approval queue (F66)."""
#region: imports
from sqlmodel import SQLModel, create_engine

from app.models import Approval
from app.services import approvals
#endregion


def _setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'approvals.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(approvals, "engine", engine)
    return engine


def test_create_and_list(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    approvals.create("recurrence_add", source_name="S", payload={"title": "Ride"}, reason="weekly")

    rows = approvals.list_approvals()
    assert len(rows) == 1
    assert rows[0]["kind"] == "recurrence_add"
    assert rows[0]["source_name"] == "S"
    assert rows[0]["payload"] == {"title": "Ride"}
    assert rows[0]["status"] == "pending"


def test_list_filters_by_status(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    aid = approvals.create("k", source_name="S")
    approvals.reject(aid)
    approvals.create("k2", source_name="S")

    assert [r["status"] for r in approvals.list_approvals(status="pending")] == ["pending"]
    assert [r["status"] for r in approvals.list_approvals(status="rejected")] == ["rejected"]


def test_approve_dispatches_to_registered_applier(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(approvals, "_appliers", {})
    calls = []

    def applier(session, approval):
        calls.append(approval.kind)

    approvals.register("test_kind", applier)
    aid = approvals.create("test_kind", source_name="S")

    assert approvals.approve(aid) is True
    assert calls == ["test_kind"]
    assert approvals.list_approvals()[0]["status"] == "approved"


def test_approve_rolls_back_on_applier_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(approvals, "_appliers", {})

    def boom(session, approval):
        raise RuntimeError("apply failed")

    approvals.register("boom_kind", boom)
    aid = approvals.create("boom_kind")

    try:
        approvals.approve(aid)
    except RuntimeError:
        pass

    # status stays pending (rolled back), and it can still be rejected
    assert approvals.list_approvals()[0]["status"] == "pending"


def test_approve_reject_idempotence(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    aid = approvals.create("k")

    assert approvals.reject(aid) is True
    assert approvals.reject(aid) is False   # already resolved
    assert approvals.approve(aid) is False  # not pending

    assert approvals.approve("does-not-exist") is False
    assert approvals.reject("does-not-exist") is False
#endregion


def test_debug_approvals_route(tmp_path, monkeypatch):
    from robyn.testing import TestClient

    from app.admin import app
    from app.security import debug_csrf_token

    engine = create_engine(f"sqlite:///{tmp_path / 'route.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(approvals, "engine", engine)

    aid = approvals.create("recurrence_add", source_name="S", reason="weekly")

    client = TestClient(app)

    r = client.get("/debug/approvals")
    assert r.status_code == 200
    assert "recurrence_add" in r.text
    assert "weekly" in r.text

    r = client.post(f"/debug/approvals/{aid}/approve", form_data={"csrf_token": debug_csrf_token()})
    assert r.status_code == 200
    assert approvals.list_approvals()[0]["status"] == "approved"
#endregion
