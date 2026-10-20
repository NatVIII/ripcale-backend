"""Tests for URL scrubbing (F61)."""
#region: imports
import logging
import sys

from app.logging import SanitizingFormatter, sanitize
#endregion


def test_sanitize_redacts_urls():
    assert sanitize("fetch failed for https://secret.example.com/feed?id=123") == "fetch failed for [redacted-url]"
    assert sanitize("Client error '404' for url 'https://x.y/a?b=c' more") == "Client error '404' for url '[redacted-url]' more"


def test_sanitize_multiple_urls():
    text = "a https://one.example x b https://two.example/p?q=1"
    assert sanitize(text) == "a [redacted-url] x b [redacted-url]"


def test_sanitize_non_string_passthrough():
    assert sanitize(None) is None
    assert sanitize(123) == 123
    assert sanitize("no urls here") == "no urls here"


def test_sanitizing_formatter_redacts_message():
    fmt = SanitizingFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom https://secret.example/feed", (), None)
    out = fmt.format(record)
    assert "secret.example" not in out
    assert "[redacted-url]" in out


def test_sanitizing_formatter_redacts_traceback():
    fmt = SanitizingFormatter("%(levelname)s %(message)s")
    try:
        raise RuntimeError("failed for https://secret.example/feed")
    except RuntimeError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "source failed", (), sys.exc_info())
        out = fmt.format(record)
    assert "secret.example" not in out
    assert "[redacted-url]" in out
#endregion
