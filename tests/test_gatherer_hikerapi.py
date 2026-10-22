"""Tests for the Instagram (HikerAPI) gatherer (F21)."""
#region: imports
from datetime import datetime, timezone

import httpx
import pytest

import app.gatherers.hikerapi.gatherer as gatherer
from app.gatherers.errors import SourceIssue
from app.schema import SourceConfig
#endregion


SOURCE = SourceConfig(name="Test", gatherer="hikerapi", url="https://www.instagram.com/somevenue/")


def _media(**kw):
    base = {
        "pk": "123",
        "id": "123_12031962527",
        "code": "AbCdEf",
        "taken_at": 1775000000,
        "media_type": 1,
        "product_type": "feed",
        "caption": {"text": "Join us Friday 7pm for live music!"},
        "location": {"name": "The Broadberry"},
        "image_versions2": {"candidates": [
            {"url": "https://cdn.example/high.jpg", "width": 1080, "height": 1350},
            {"url": "https://cdn.example/low.jpg", "width": 300, "height": 375},
        ]},
        "carousel_media": None,
        "video_versions": [],
    }
    base.update(kw)
    return base


def _patch_get(monkeypatch, user, medias):
    def fake_get(url, params=None):
        if "user/by/username" in url:
            return user
        if "user/medias" in url:
            return {"response": {"items": medias}}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(gatherer, "_get", fake_get)
    monkeypatch.setattr(gatherer.settings, "hikerapi_key", "test-key")


def test_username_from_url():
    assert gatherer._username_from_url("https://www.instagram.com/somevenue/") == "somevenue"
    assert gatherer._username_from_url("https://instagram.com/othervenue") == "othervenue"
    assert gatherer._username_from_url("somevenue") == "somevenue"
    assert gatherer._username_from_url("@somevenue") == "somevenue"


def test_to_event_mapping():
    event = gatherer.to_event(_media())
    assert event.uid == "123"
    assert event.url == "https://www.instagram.com/p/AbCdEf/"
    assert event.title == "Join us Friday 7pm for live music!"
    assert event.description == "Join us Friday 7pm for live music!"
    assert event.location == "The Broadberry"
    assert event.images[0].url == "https://cdn.example/high.jpg"
    assert event.start_at == datetime.fromtimestamp(1775000000, tz=timezone.utc).replace(tzinfo=None)


def test_to_event_pk_normalized_to_str():
    event = gatherer.to_event(_media(pk=123456789, id="123456789_12031962527"))
    assert event.uid == "123456789"


def test_to_event_id_fallback_strips_user_suffix():
    media = _media()
    media.pop("pk")
    event = gatherer.to_event(media)
    assert event.uid == "123"


def test_to_event_caption_object():
    event = gatherer.to_event(_media(caption={"text": "Post the caption"}))
    assert event.title == "Post the caption"


def test_to_event_taken_at_int():
    event = gatherer.to_event(_media(taken_at=1775000000))
    assert event.start_at == datetime.fromtimestamp(1775000000, tz=timezone.utc).replace(tzinfo=None)


def test_to_event_taken_at_g2_prefixed():
    media = _media()
    media.pop("taken_at")
    media["1ltaken_at"] = 1775000000
    event = gatherer.to_event(media)
    assert event.start_at == datetime.fromtimestamp(1775000000, tz=timezone.utc).replace(tzinfo=None)


def test_to_event_carousel_images():
    media = _media(
        media_type=8,
        carousel_media=[
            {"image_versions2": {"candidates": [{"url": "https://cdn.example/a.jpg", "width": 100, "height": 100}]}},
            {"image_versions2": {"candidates": [{"url": "https://cdn.example/b.jpg", "width": 200, "height": 200}]}},
        ],
        image_versions2={"candidates": [{"url": "https://cdn.example/cover.jpg", "width": 300, "height": 300}]},
    )
    urls = [img.url for img in gatherer.to_event(media).images]
    assert urls == ["https://cdn.example/a.jpg", "https://cdn.example/b.jpg"]


def test_to_event_reel_uses_thumbnail():
    media = _media(media_type=2, product_type="clips", image_versions2={"candidates": []}, thumbnail_url="https://cdn.example/thumb.jpg")
    assert gatherer.to_event(media).images[0].url == "https://cdn.example/thumb.jpg"


def test_to_event_empty_caption_title():
    event = gatherer.to_event(_media(caption={"text": ""}))
    assert event.title == "(untitled)"
    assert event.description is None


def test_fetch_medias_parses_chunk(monkeypatch):
    _patch_get(monkeypatch, {"pk": "123"}, [_media()])
    medias = gatherer.fetch_medias(SOURCE)
    assert [m["pk"] for m in medias] == ["123"]


def test_run_keeps_all_posts(monkeypatch):
    event_media = _media(caption={"text": "Join us Friday 7pm for live music!"})
    non_event = _media(pk="456", id="456_12031962527", code="ZzZzZz", caption={"text": "New merch drop!"})
    _patch_get(monkeypatch, {"pk": "123"}, [event_media, non_event])

    result = gatherer.run(SOURCE)

    assert [e.uid for e in result.events] == ["123", "456"]  # nothing dropped; the LLM decides


def test_run_requires_key(monkeypatch):
    monkeypatch.setattr(gatherer.settings, "hikerapi_key", "")
    import pytest

    with pytest.raises(ValueError):
        gatherer.fetch_medias(SOURCE)


class _Resp:
    """Minimal httpx.Response stand-in for exercising `_get`'s status handling."""

    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body

    def json(self):
        if isinstance(self._body, dict):
            return self._body
        raise ValueError("not json")

    @property
    def text(self):
        return self._body if isinstance(self._body, str) else ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} error",
                request=httpx.Request("GET", "https://x"),
                response=self,
            )


def _patch_safe_get(monkeypatch, responses, calls=None):
    """Return successive responses from `safe_get`; record the call count."""
    iterator = iter(responses)

    def fake_get(url, **kwargs):
        if calls is not None:
            calls.append(url)
        return next(iterator)

    monkeypatch.setattr(gatherer, "safe_get", fake_get)
    monkeypatch.setattr(gatherer.settings, "hikerapi_key", "test-key")


def test_backoff_sleep_exponential(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gatherer.time, "sleep", lambda s: sleeps.append(s))
    gatherer._backoff_sleep(1)
    gatherer._backoff_sleep(2)
    gatherer._backoff_sleep(3)
    assert sleeps == [1.0, 2.0, 4.0]


def test_backoff_sleep_honors_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gatherer.time, "sleep", lambda s: sleeps.append(s))
    gatherer._backoff_sleep(1, "10")
    assert sleeps == [10.0]


def test_backoff_sleep_ignores_bad_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gatherer.time, "sleep", lambda s: sleeps.append(s))
    gatherer._backoff_sleep(1, "abc")
    assert sleeps == [1.0]


def test_backoff_sleep_caps(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gatherer.time, "sleep", lambda s: sleeps.append(s))
    gatherer._backoff_sleep(1, "999")
    assert sleeps == [gatherer._BACKOFF_CAP]


def test_get_403_raises_source_issue(monkeypatch):
    _patch_safe_get(monkeypatch, [_Resp(403, {"error": "private account"})])

    with pytest.raises(SourceIssue) as exc:
        gatherer._get("https://api.hikerapi.com/v1/user/by/username")

    assert "403" in str(exc.value)
    assert "private account" in str(exc.value)


def test_get_404_raises_source_issue(monkeypatch):
    _patch_safe_get(monkeypatch, [_Resp(404, {"error": "user not found"})])

    with pytest.raises(SourceIssue) as exc:
        gatherer._get("https://api.hikerapi.com/v1/user/by/username")

    assert "404" in str(exc.value)
    assert "not found" in str(exc.value)


def test_get_429_retries_then_succeeds(monkeypatch):
    calls = []
    _patch_safe_get(monkeypatch, [_Resp(429, "rate limited", {"Retry-After": "0"}), _Resp(200, {"ok": True})], calls)
    sleeps = []
    monkeypatch.setattr(gatherer, "_backoff_sleep", lambda attempt, retry_after=None: sleeps.append((attempt, retry_after)))

    result = gatherer._get("https://api.hikerapi.com/x")

    assert result == {"ok": True}
    assert len(calls) == 2
    assert sleeps == [(1, "0")]  # Retry-After passed through


def test_get_429_exhausts_retries(monkeypatch):
    calls = []
    _patch_safe_get(monkeypatch, [_Resp(429, "rate limited")] * 3, calls)
    sleeps = []
    monkeypatch.setattr(gatherer, "_backoff_sleep", lambda attempt, retry_after=None: sleeps.append(attempt))

    with pytest.raises(RuntimeError) as exc:
        gatherer._get("https://api.hikerapi.com/x")

    assert "429" in str(exc.value)
    assert "retried" in str(exc.value)
    assert len(calls) == 3          # exactly _MAX_ATTEMPTS calls
    assert sleeps == [1, 2]         # backoff after the first two attempts


def test_get_5xx_retries(monkeypatch):
    calls = []
    _patch_safe_get(monkeypatch, [_Resp(503, "down"), _Resp(200, {"ok": True})], calls)
    monkeypatch.setattr(gatherer, "_backoff_sleep", lambda *a, **k: None)

    assert gatherer._get("https://api.hikerapi.com/x") == {"ok": True}
    assert len(calls) == 2


def test_get_401_is_hard_error_no_retry(monkeypatch):
    calls = []
    _patch_safe_get(monkeypatch, [_Resp(401, {"error": "invalid key"})], calls)

    def _no_retry(*a, **k):
        raise AssertionError("401 must not be retried")

    monkeypatch.setattr(gatherer, "_backoff_sleep", _no_retry)

    with pytest.raises(RuntimeError) as exc:
        gatherer._get("https://api.hikerapi.com/x")

    assert "401" in str(exc.value)
    assert len(calls) == 1


def test_get_network_error_retries(monkeypatch):
    monkeypatch.setattr(gatherer.settings, "hikerapi_key", "test-key")
    calls = {"n": 0}

    def fake_get(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom")
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(gatherer, "safe_get", fake_get)
    monkeypatch.setattr(gatherer, "_backoff_sleep", lambda *a, **k: None)

    assert gatherer._get("https://api.hikerapi.com/x") == {"ok": True}
    assert calls["n"] == 2


def test_get_403_captures_before_raising(monkeypatch):
    _patch_safe_get(monkeypatch, [_Resp(403, {"error": "private"}, {"X-Rate": "1"})])
    capture = []

    with pytest.raises(SourceIssue):
        gatherer._get("https://api.hikerapi.com/v1/user/by/username", capture=capture)

    assert len(capture) == 1
    assert capture[0]["status"] == 403
    assert capture[0]["body"] == {"error": "private"}
    assert capture[0]["headers"] == {"X-Rate": "1"}


def test_run_raises_source_issue_on_403(monkeypatch):
    _patch_safe_get(monkeypatch, [_Resp(403, {"error": "private account"})])

    with pytest.raises(SourceIssue):
        gatherer.run(SOURCE)


def test_fetch_raw_captures_responses(monkeypatch):
    monkeypatch.setattr(gatherer.settings, "hikerapi_key", "test-key")

    def fake_get(url, params=None, capture=None):
        body = {"pk": "123", "username": "venue"} if "user/by/username" in url else {"response": {"items": [_media()]}}
        if capture is not None:
            capture.append({"url": url, "status": 200, "headers": {"X-Test": "1"}, "body": body})
        return body

    monkeypatch.setattr(gatherer, "_get", fake_get)

    captured = gatherer.fetch_raw(SOURCE)

    assert len(captured) == 2
    assert captured[0]["status"] == 200
    assert "user/by/username" in captured[0]["url"]
    assert "user/medias" in captured[1]["url"]


def test_verify_ok():
    assert gatherer.verify({"pk": "1", "username": "x"}, [_media()]) == []


def test_verify_flags_missing_fields():
    warnings = gatherer.verify(None, [{"caption_text": "missing most fields"}])
    joined = " ".join(warnings)
    assert "pk" in joined
    assert "code" in joined
    assert "image" in joined
    assert "timestamp" in joined
#endregion
