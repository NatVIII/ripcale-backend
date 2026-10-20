"""SSRF guard (F60): outbound fetches are pinned to validated, globally-routable IPs.

Server-Side Request Forgery: a URL embedded in scraped data (or a compromised
source config) could point at internal/cloud-metadata addresses. This module
closes that by (a) only allowing `http(s)`, (b) resolving the host and rejecting
non-global addresses, and (c) **pinning** the actual connection to the validated
IP while preserving the original hostname for the `Host` header and TLS SNI —
so DNS rebinding (a host that resolves to a public IP on check but a private one
on connect) is defeated, not just mitigated.

`client()` returns a shared `httpx.Client` wired with a `PinnedTransport` and a
redirect cap. Callers use it instead of top-level `httpx.get`.
"""
#region: imports
import ipaddress
import socket

import httpx

from app.config import settings
#endregion


#region: constants
_REDIRECT_MAX = 5
#endregion


#region: error
class SSRFBlocked(ValueError):
    """Raised when an outbound URL resolves to a non-global / blocked address."""
#endregion


#region: address policy
# Belt-and-suspenders on top of `ipaddress.is_global` (which already rejects
# loopback/private/link-local/multicast/reserved). Kept explicit for clarity.
_BLOCKED_NETS = [
    ipaddress.ip_network("0.0.0.0/8"),       # "this" network
    ipaddress.ip_network("10.0.0.0/8"),      # private
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),     # loopback
    ipaddress.ip_network("169.254.0.0/16"),  # link-local + cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),   # private
    ipaddress.ip_network("192.168.0.0/16"),  # private
    ipaddress.ip_network("224.0.0.0/4"),     # multicast
    ipaddress.ip_network("240.0.0.0/4"),     # reserved
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # unique-local
    ipaddress.ip_network("fe80::/10"),       # link-local
    ipaddress.ip_network("ff00::/8"),        # multicast
]


def _is_global_ip(ip: ipaddress._BaseAddress) -> bool:
    return ip.is_global and not any(ip in net for net in _BLOCKED_NETS)


def _resolve_global(host: str, port: int) -> str:
    """Resolve `host` and return a globally-routable address (else raise).

    IPv4 is preferred over IPv6: a host may advertise a broken/unreachable IPv6
    that sorts first in `getaddrinfo`, and pinning to it would fail where IPv4
    would succeed.
    """
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlocked(f"cannot resolve host {host!r}") from exc
    global_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_global_ip(ip):
            global_ips.append(ip)
    if not global_ips:
        raise SSRFBlocked(f"no globally-routable address for {host!r}")
    for ip in global_ips:
        if ip.version == 4:
            return str(ip)
    return str(global_ips[0])
#endregion


#region: pinned transport
class PinnedTransport(httpx.BaseTransport):
    """A transport that resolves, validates, and pins each request's host to an IP.

    The connection is made to the validated IP, while the `Host` header and TLS
    SNI (via `extensions["sni_hostname"]`) still carry the original hostname, so
    cert validation and virtual-host routing are unaffected.
    """

    def __init__(self, inner: httpx.BaseTransport | None = None) -> None:
        self._inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if not settings.ssrf_guard_enabled:
            return self._inner.handle_request(request)

        host = request.url.raw_host
        if host is None:
            raise SSRFBlocked("request has no host")
        hostname = host.decode("ascii")

        try:
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            port = request.url.port or (443 if request.url.scheme == "https" else 80)
            ip_str = _resolve_global(hostname, port)
        else:
            if not _is_global_ip(ip):
                raise SSRFBlocked(f"blocked address {ip}")
            ip_str = str(ip)

        pinned = httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=ip_str),
            headers=request.headers,
            content=request.stream,
            extensions={**request.extensions, "sni_hostname": hostname},
        )
        return self._inner.handle_request(pinned)

    def close(self) -> None:
        self._inner.close()
#endregion


#region: shared client
_client: httpx.Client | None = None


def client() -> httpx.Client:
    """A shared, guarded HTTP client (redirects capped; no keepalive reuse)."""
    global _client
    if _client is None:
        _client = httpx.Client(
            transport=PinnedTransport(),
            follow_redirects=True,
            max_redirects=_REDIRECT_MAX,
            limits=httpx.Limits(max_keepalive_connections=0),
        )
    return _client


def get(url: str, **kwargs) -> httpx.Response:
    """GET `url` through the guarded client when the guard is on, else plain httpx."""
    if settings.ssrf_guard_enabled:
        return client().get(url, **kwargs)
    kwargs.setdefault("follow_redirects", True)
    return httpx.get(url, **kwargs)
#endregion
