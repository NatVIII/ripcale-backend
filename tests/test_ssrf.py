"""Tests for the SSRF guard (F60)."""
#region: imports
import ipaddress
import socket

import httpx
import pytest

from app.services import ssrf
#endregion


#region: address policy
def test_is_global_ip():
    assert ssrf._is_global_ip(ipaddress.ip_address("93.184.216.34")) is True
    assert ssrf._is_global_ip(ipaddress.ip_address("127.0.0.1")) is False
    assert ssrf._is_global_ip(ipaddress.ip_address("10.0.0.1")) is False
    assert ssrf._is_global_ip(ipaddress.ip_address("169.254.169.254")) is False
    assert ssrf._is_global_ip(ipaddress.ip_address("192.168.1.1")) is False
    assert ssrf._is_global_ip(ipaddress.ip_address("172.16.0.1")) is False
    assert ssrf._is_global_ip(ipaddress.ip_address("::1")) is False
    assert ssrf._is_global_ip(ipaddress.ip_address("fc00::1")) is False


def test_resolve_global_allows_public(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))],
    )
    assert ssrf._resolve_global("example.com", 443) == "93.184.216.34"


def test_resolve_global_blocks_private(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda host, port, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port))],
    )
    with pytest.raises(ssrf.SSRFBlocked):
        ssrf._resolve_global("internal.example.com", 443)


def test_resolve_global_picks_public_when_mixed(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ],
    )
    assert ssrf._resolve_global("x", 443) == "93.184.216.34"


def test_resolve_global_prefers_ipv4_over_ipv6(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", port, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
        ],
    )
    assert ssrf._resolve_global("example.com", 443) == "93.184.216.34"


def test_resolve_global_falls_back_to_ipv6(monkeypatch):
    monkeypatch.setattr(
        ssrf.socket, "getaddrinfo",
        lambda host, port, *a, **k: [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", port, 0, 0)),
        ],
    )
    assert ssrf._resolve_global("example.com", 443) == "2606:2800:220:1:248:1893:25c8:1946"


def test_resolve_global_dns_failure(monkeypatch):
    def boom(host, port, *a, **k):
        raise socket.gaierror("nope")

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", boom)
    with pytest.raises(ssrf.SSRFBlocked):
        ssrf._resolve_global("does-not-exist.invalid", 443)
#endregion


#region: pinned transport
def _stub_transport(captured):
    class Inner(httpx.BaseTransport):
        def handle_request(self, request):
            captured["url"] = str(request.url)
            captured["host"] = request.headers.get("host")
            captured["sni"] = request.extensions.get("sni_hostname")
            return httpx.Response(200, request=request, content=b"ok")

        def close(self):
            pass

    return Inner()


def test_pinned_transport_rewrites_and_preserves_host_sni(monkeypatch):
    captured = {}
    monkeypatch.setattr(ssrf.settings, "ssrf_guard_enabled", True)
    monkeypatch.setattr(ssrf, "_resolve_global", lambda host, port: "93.184.216.34")

    with httpx.Client(transport=ssrf.PinnedTransport(_stub_transport(captured))) as c:
        resp = c.get("https://example.com/feed")

    assert resp.status_code == 200
    assert "93.184.216.34" in captured["url"]
    assert captured["host"] == "example.com"
    assert captured["sni"] == "example.com"


def test_pinned_transport_blocks_ip_literal(monkeypatch):
    monkeypatch.setattr(ssrf.settings, "ssrf_guard_enabled", True)
    with httpx.Client(transport=ssrf.PinnedTransport()) as c:
        with pytest.raises(ssrf.SSRFBlocked):
            c.get("http://127.0.0.1/")


def test_pinned_transport_blocks_metadata_ip_literal(monkeypatch):
    monkeypatch.setattr(ssrf.settings, "ssrf_guard_enabled", True)
    with httpx.Client(transport=ssrf.PinnedTransport()) as c:
        with pytest.raises(ssrf.SSRFBlocked):
            c.get("http://169.254.169.254/latest/meta-data/")


def test_guard_off_bypasses(monkeypatch):
    captured = {}
    monkeypatch.setattr(ssrf.settings, "ssrf_guard_enabled", False)

    with httpx.Client(transport=ssrf.PinnedTransport(_stub_transport(captured))) as c:
        c.get("https://example.com/feed")

    assert "example.com" in captured["url"]  # unchanged, no pinning
#endregion


#region: integration
def test_store_blocks_private_url(monkeypatch):
    from app.services import images

    monkeypatch.setattr(ssrf.settings, "ssrf_guard_enabled", True)
    with pytest.raises(ssrf.SSRFBlocked):
        images.store("http://169.254.169.254/latest/meta-data/")
#endregion
