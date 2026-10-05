from __future__ import annotations

from dataclasses import dataclass
from copy import copy
import ipaddress
import socket
from urllib.parse import quote, urlparse, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener


DEFAULT_MAX_BYTES = 5 * 1024 * 1024

# Some egress proxies (e.g. Clash fake-ip) resolve public hostnames to this range.
_EGRESS_FAKE_IP_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def _is_acceptable_public_resolution(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_global:
        return True
    return ip in _EGRESS_FAKE_IP_NETWORK


def _encode_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc,
                      quote(parts.path, safe="/%:@!$&'()*+,;=-._~"),
                      quote(parts.query, safe="%/?@:!$&'()*+,;=-._~"),
                      parts.fragment))


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme or '<missing>'}")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("refusing localhost URL")

    try:
        resolved = socket.getaddrinfo(hostname, parsed.port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"cannot resolve hostname: {hostname}") from exc

    if not resolved:
        raise ValueError(f"cannot resolve hostname: {hostname}")
    for _family, _type, _proto, _canonname, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if not _is_acceptable_public_resolution(ip):
            raise ValueError(f"refusing non-public address for {hostname}: {ip}")
    return url


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = _encode_url(newurl)
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass
class _LimitedResponse:
    response: object
    max_bytes: int

    @property
    def headers(self):
        return self.response.headers

    def geturl(self):
        return self.response.geturl()

    def read(self, amt: int | None = None):
        if amt is not None:
            return self.response.read(min(amt, self.max_bytes + 1))
        payload = self.response.read(self.max_bytes + 1)
        if len(payload) > self.max_bytes:
            raise ValueError(f"response exceeds {self.max_bytes} byte limit")
        return payload

    def close(self):
        return self.response.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def safe_urlopen(request_or_url, timeout: int = 10, max_bytes: int = DEFAULT_MAX_BYTES, cookie_jar=None):
    if isinstance(request_or_url, Request):
        url = request_or_url.full_url
    else:
        url = str(request_or_url)
    validate_public_url(url)
    encoded_url = _encode_url(url)
    if isinstance(request_or_url, Request):
        request_or_url = copy(request_or_url)
        request_or_url.full_url = encoded_url
    else:
        request_or_url = encoded_url
    handlers = []
    if cookie_jar is not None:
        handlers.append(HTTPCookieProcessor(cookie_jar))
    handlers.append(_SafeRedirectHandler())
    opener = build_opener(*handlers)
    response = opener.open(request_or_url, timeout=timeout)
    final_url = response.geturl()
    try:
        validate_public_url(final_url)
    except Exception:
        response.close()
        raise
    return _LimitedResponse(response=response, max_bytes=max_bytes)
