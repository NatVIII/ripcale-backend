"""Tests for config/intake coherence checks (F49)."""
#region: imports
from app.services.coherence import check
#endregion


def _setup(tmp_path, monkeypatch, content=None):
    from app.config import settings

    path = tmp_path / "intake.yaml"
    if content is not None:
        path.write_text(content)
    monkeypatch.setattr(settings, "intake_file", str(path))
    return path


#region: intake structure
def test_missing_intake_is_ok(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert check() == []


def test_malformed_yaml_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources: [unclosed")
    issues = check()
    assert any(i["severity"] == "error" and i["scope"] == "intake" for i in issues)


def test_non_mapping_root_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "- just\n- a list\n")
    issues = check()
    assert any(i["severity"] == "error" and "mapping" in i["message"] for i in issues)


def test_invalid_shape_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources:\n  - gatherer: elfsight\n    url: https://x\n")
    issues = check()
    assert any("validation failed" in i["message"] for i in issues)


def test_valid_intake_is_ok(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources:\n  - name: X\n    gatherer: elfsight\n    url: https://x\n")
    assert check() == []
#endregion


#region: semantic
def test_missing_gatherer_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources:\n  - name: X\n    gatherer: nope\n    url: https://x\n")
    issues = check()
    assert any("gatherer 'nope'" in i["message"] for i in issues)


def test_category_multiclass_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "category_definitions:\n  external: [art]\n  intake: [art]\n")
    issues = check()
    assert any("multiple classes" in i["message"] for i in issues)


def test_unknown_class_reports_warning(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "category_definitions:\n  weird: [art]\n")
    issues = check()
    assert any(i["severity"] == "warning" and "unknown category class" in i["message"] for i in issues)


def test_self_symlink_reports_warning(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "category_symlinks:\n  art: art\n")
    issues = check()
    assert any(i["severity"] == "warning" and "maps to itself" in i["message"] for i in issues)
#endregion


#region: rules
def test_invalid_regex_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources:\n  - name: X\n    gatherer: elfsight\n    url: https://x\n    rules:\n      - mode: regex\n        fields: [title]\n        regex: \"(\"\n        categories: [art]\n")
    issues = check()
    assert any("invalid regex" in i["message"] for i in issues)


def test_regex_missing_pattern_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources:\n  - name: X\n    gatherer: elfsight\n    url: https://x\n    rules:\n      - mode: regex\n        fields: [title]\n        categories: [art]\n")
    issues = check()
    assert any("missing a regex" in i["message"] for i in issues)


def test_unknown_field_reports_warning(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "sources:\n  - name: X\n    gatherer: elfsight\n    url: https://x\n    rules:\n      - mode: regex\n        fields: [bogus]\n        regex: \"a\"\n        categories: [art]\n")
    issues = check()
    assert any(i["severity"] == "warning" and "unknown field" in i["message"] for i in issues)


def test_gatherer_rule_invalid_regex_reports_error(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "gatherers:\n  elfsight:\n    rules:\n      - mode: regex\n        fields: [title]\n        regex: \"(\"\n        categories: [art]\n")
    issues = check()
    assert any("gatherer 'elfsight'" in i["message"] and "invalid regex" in i["message"] for i in issues)
#endregion


#region: route
def _dashboard_client(tmp_path, monkeypatch):
    import app.routers.debug as debug_router_mod
    from sqlmodel import SQLModel, create_engine

    engine = create_engine(f"sqlite:///{tmp_path / 'coherence.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(debug_router_mod, "engine", engine)

    from robyn.testing import TestClient

    from app.admin import app

    return TestClient(app)


def test_dashboard_shows_coherence_all_good(tmp_path, monkeypatch):
    client = _dashboard_client(tmp_path, monkeypatch)
    r = client.get("/debug")
    assert r.status_code == 200
    assert "coherence" in r.text
    assert "all good" in r.text


def test_dashboard_shows_coherence_issue(tmp_path, monkeypatch):
    (tmp_path / "intake.yaml").write_text("sources: [unclosed")
    client = _dashboard_client(tmp_path, monkeypatch)
    r = client.get("/debug")
    assert r.status_code == 200
    assert "coherence" in r.text
    assert "not valid YAML" in r.text
#endregion
