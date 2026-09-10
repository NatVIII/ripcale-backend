"""Tests for the debug tests page (F37.05)."""
#region: imports
import subprocess

from app.security import debug_csrf_token
#endregion


#region: service
def test_collect_tests_parses_node_ids(monkeypatch):
    from app.services import testrunner

    captured = {}
    fake = subprocess.CompletedProcess(
        args=[], returncode=0,
        stdout="tests/test_db.py::test_a\ntests/test_x.py::test_b\n77 tests collected in 0.5s\n",
        stderr="",
    )

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        captured["kwargs"] = kwargs
        return fake

    monkeypatch.setattr(testrunner.subprocess, "run", fake_run)

    assert testrunner.collect_tests() == ["tests/test_db.py::test_a", "tests/test_x.py::test_b"]
    assert "--collect-only" in captured["cmd"]
    assert "-q" in captured["cmd"]
    assert captured["kwargs"]["cwd"] == testrunner.PROJECT_ROOT


def test_run_tests_all_and_single(monkeypatch):
    from app.services import testrunner

    captured = {}

    def fake_run(*args, **kwargs):
        captured["cmd"] = args[0]
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="77 passed", stderr="")

    monkeypatch.setattr(testrunner.subprocess, "run", fake_run)

    rc, out = testrunner.run_tests(None)
    assert rc == 0
    assert out == "77 passed"
    assert captured["cmd"][-1] == "-q"

    rc, out = testrunner.run_tests("tests/test_x.py::test_b")
    assert captured["cmd"][-1] == "tests/test_x.py::test_b"


def test_run_tests_concats_stdout_and_stderr(monkeypatch):
    from app.services import testrunner

    fake = subprocess.CompletedProcess(args=[], returncode=1, stdout="OUT\n", stderr="ERR\n")
    monkeypatch.setattr(testrunner.subprocess, "run", lambda *a, **k: fake)

    rc, out = testrunner.run_tests(None)
    assert rc == 1
    assert out == "OUT\nERR"
#endregion


#region: route
def test_tests_route_get_and_post(tmp_path, monkeypatch):
    import app.services.actions as actions_mod

    monkeypatch.setattr(
        actions_mod, "tests_list",
        lambda: ["tests/test_db.py::test_a", "tests/test_x.py::test_b"],
    )

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)

    r = client.get("/debug/tests")
    assert r.status_code == 200
    assert "all tests" in r.text
    assert "test_a" in r.text

    # pass
    monkeypatch.setattr(actions_mod, "tests_run", lambda node_id: {"exit": 0, "output": "1 passed"})
    r = client.post("/debug/tests", form_data={"csrf_token": debug_csrf_token(), "test": "tests/test_db.py::test_a"})
    assert r.status_code == 200
    assert "🟢" in r.text
    assert "passed" in r.text

    # fail
    monkeypatch.setattr(actions_mod, "tests_run", lambda node_id: {"exit": 1, "output": "1 failed"})
    r = client.post("/debug/tests", form_data={"csrf_token": debug_csrf_token(), "test": ""})
    assert r.status_code == 200
    assert "🔴" in r.text
    assert "failed" in r.text


def test_tests_route_requires_csrf(tmp_path, monkeypatch):
    import app.services.actions as actions_mod

    monkeypatch.setattr(actions_mod, "tests_list", lambda: [])
    monkeypatch.setattr(actions_mod, "tests_run", lambda node_id: {"exit": 0, "output": ""})

    from robyn.testing import TestClient

    from app.admin import app

    client = TestClient(app)
    r = client.post("/debug/tests", form_data={"test": ""})
    assert r.status_code == 403
#endregion
