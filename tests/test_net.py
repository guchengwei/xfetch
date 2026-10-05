import socket

import pytest

from xfetch.net import validate_public_url


def test_validate_public_url_blocks_loopback(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ValueError, match="non-public"):
        validate_public_url("https://example.test/private")


def test_validate_public_url_blocks_link_local_metadata(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))])
    with pytest.raises(ValueError, match="non-public"):
        validate_public_url("http://metadata.invalid/latest")


def test_validate_public_url_accepts_public_address(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    assert validate_public_url("https://example.com/article") == "https://example.com/article"


def test_validate_public_url_accepts_egress_fake_ip(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.1", 443))],
    )
    url = "https://vocus.cc/article/676cfc02fd89780001bbaaa4"
    assert validate_public_url(url) == url


def test_validate_public_url_blocks_rfc1918_private(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))],
    )
    with pytest.raises(ValueError, match="non-public"):
        validate_public_url("https://example.test/internal")


def test_safe_urlopen_installs_cookie_jar_when_provided(monkeypatch):
    from http.cookiejar import CookieJar
    from urllib.request import HTTPCookieProcessor
    from xfetch.net import safe_urlopen

    seen = {}

    class Response:
        def geturl(self):
            return "https://example.com/a"

        def close(self):
            return None

    class Opener:
        def open(self, value, timeout):
            return Response()

    def build(*handlers):
        seen["handlers"] = handlers
        return Opener()

    monkeypatch.setattr("xfetch.net.build_opener", build)
    monkeypatch.setattr("xfetch.net.validate_public_url", lambda value: value)
    jar = CookieJar()
    safe_urlopen("https://example.com/a", cookie_jar=jar)
    assert isinstance(seen["handlers"][0], HTTPCookieProcessor)
    assert seen["handlers"][0].cookiejar is jar
    assert type(seen["handlers"][1]).__name__ == "_SafeRedirectHandler"


@pytest.mark.parametrize('as_request', [False, True])
def test_safe_urlopen_encodes_unicode_without_double_encoding(monkeypatch, as_request):
    from urllib.request import Request
    from xfetch.net import safe_urlopen
    url = 'https://example.com/工作流/%E4%B8%AD?q=測試&keep=a%2Fb'
    expected = 'https://example.com/%E5%B7%A5%E4%BD%9C%E6%B5%81/%E4%B8%AD?q=%E6%B8%AC%E8%A9%A6&keep=a%2Fb'
    checked = []
    monkeypatch.setattr('xfetch.net.validate_public_url', lambda value: checked.append(value))
    class Response:
        def geturl(self): return expected
    class Opener:
        def open(self, value, timeout):
            assert (value.full_url if as_request else value) == expected
            if as_request:
                assert value.get_header('User-agent') == 'test-agent'
                assert value.data == b'body'
                assert value.get_method() == 'POST'
            return Response()
    monkeypatch.setattr('xfetch.net.build_opener', lambda *args: Opener())
    request = Request(url, data=b'body', headers={'User-Agent': 'test-agent'}) if as_request else url
    safe_urlopen(request)
    assert checked == [url, expected]
    if as_request:
        assert request.full_url == url
