"""Tests for the DeepSeek client (F65)."""
#region: imports
import httpx
import pytest

from app.services import deepseek
#endregion


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = payload if isinstance(payload, str) else str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("POST", "https://x"), response=self
            )

    def json(self):
        return self._payload


def _patch(monkeypatch, content="hello"):
    def fake_post(url, headers=None, json=None, timeout=None):
        assert headers["Authorization"].startswith("Bearer ")
        return _Resp(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(deepseek.httpx, "post", fake_post)
    monkeypatch.setattr(deepseek.settings, "deepseek_key", "test-key")


def test_chat_returns_content(monkeypatch):
    _patch(monkeypatch, content="hi")
    assert deepseek.chat([{"role": "user", "content": "x"}]) == "hi"


def test_chat_json_mode_sets_response_format(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["payload"] = json
        return _Resp(200, {"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr(deepseek.httpx, "post", fake_post)
    monkeypatch.setattr(deepseek.settings, "deepseek_key", "k")
    deepseek.chat([{"role": "user", "content": "x"}], json_mode=True)
    assert seen["payload"]["response_format"] == {"type": "json_object"}


def test_chat_requires_key(monkeypatch):
    monkeypatch.setattr(deepseek.settings, "deepseek_key", "")
    with pytest.raises(deepseek.DeepSeekPermanent):
        deepseek.chat([{"role": "user", "content": "x"}])


def test_chat_400_raises_permanent(monkeypatch):
    monkeypatch.setattr(deepseek.httpx, "post", lambda *a, **k: _Resp(400, {"error": "bad"}))
    monkeypatch.setattr(deepseek.settings, "deepseek_key", "k")
    with pytest.raises(deepseek.DeepSeekPermanent):
        deepseek.chat([{"role": "user", "content": "x"}])


def test_chat_exhausted_retries_raises_transient(monkeypatch):
    monkeypatch.setattr(deepseek.httpx, "post", lambda *a, **k: _Resp(429, {"error": "rate limited"}))
    monkeypatch.setattr(deepseek.settings, "deepseek_key", "k")
    monkeypatch.setattr(deepseek.time, "sleep", lambda s: None)
    with pytest.raises(deepseek.DeepSeekTransient):
        deepseek.chat([{"role": "user", "content": "x"}])


def test_chat_retries_on_429_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, {"error": "rate limited"})
        return _Resp(200, {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(deepseek.httpx, "post", fake_post)
    monkeypatch.setattr(deepseek.settings, "deepseek_key", "k")
    monkeypatch.setattr(deepseek.time, "sleep", lambda s: None)
    assert deepseek.chat([{"role": "user", "content": "x"}]) == "ok"
    assert calls["n"] == 2
#endregion
