"""Tests for the shared gatherer fetch helpers (F37.01 graceful failure)."""
#region: imports
import httpx
import pytest

import app.gatherers.base as base
from app.gatherers.errors import SourceIssue
#endregion


class _Resp:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json_body = json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("GET", "https://x"),
                response=self,
            )

    def json(self):
        if self._json_body is not None:
            return self._json_body
        raise ValueError("not json")

    @property
    def text(self):
        return "not json"


#region: network / HTTP -> SourceIssue
def test_fetch_json_network_error_is_source_issue(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(base, "safe_get", boom)
    with pytest.raises(SourceIssue) as exc:
        base.fetch_json("https://example.com/feed")
    assert "unreachable" in str(exc.value)


def test_fetch_text_network_error_is_source_issue(monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(base, "safe_get", boom)
    with pytest.raises(SourceIssue):
        base.fetch_text("https://example.com/feed")


def test_fetch_json_http_error_is_source_issue(monkeypatch):
    monkeypatch.setattr(base, "safe_get", lambda url, **kwargs: _Resp(503))
    with pytest.raises(SourceIssue) as exc:
        base.fetch_json("https://example.com/feed")
    assert "503" in str(exc.value)


def test_fetch_text_http_error_is_source_issue(monkeypatch):
    monkeypatch.setattr(base, "safe_get", lambda url, **kwargs: _Resp(404))
    with pytest.raises(SourceIssue) as exc:
        base.fetch_text("https://example.com/feed")
    assert "404" in str(exc.value)
#endregion


#region: unparseable content stays a hard error
def test_fetch_json_unparseable_is_hard_error(monkeypatch):
    monkeypatch.setattr(base, "safe_get", lambda url, **kwargs: _Resp(200))
    with pytest.raises(ValueError):
        base.fetch_json("https://example.com/feed")
#endregion


#region: success
def test_fetch_json_success(monkeypatch):
    monkeypatch.setattr(base, "safe_get", lambda url, **kwargs: _Resp(200, json_body={"ok": True}))
    assert base.fetch_json("https://example.com/feed") == {"ok": True}


def test_fetch_text_success(monkeypatch):
    class _TextResp(_Resp):
        @property
        def text(self):
            return "BEGIN:VCALENDAR"

    monkeypatch.setattr(base, "safe_get", lambda url, **kwargs: _TextResp(200))
    assert base.fetch_text("https://example.com/feed") == "BEGIN:VCALENDAR"
#endregion
