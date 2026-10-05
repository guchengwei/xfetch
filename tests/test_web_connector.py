from xfetch.connectors.web import WebConnector


class FakeResponse:
    def __init__(self, body: str, url: str, content_type: str = "text/html; charset=utf-8"):
        self._body = body.encode("utf-8")
        self._url = url
        self.headers = {"Content-Type": content_type}

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_web_connector_extracts_basic_document_fields(monkeypatch):
    html = """
    <html>
      <head>
        <title>Example Article</title>
        <meta name=\"author\" content=\"Alice Example\">
      </head>
      <body>
        <main>
          <h1>Example Article</h1>
          <p>Hello world.</p>
          <p>This is a test article.</p>
        </main>
      </body>
    </html>
    """

    monkeypatch.setattr(
        "xfetch.connectors.web.urlopen",
        lambda request, timeout=10: FakeResponse(html, "https://example.com/posts/123"),
    )

    connector = WebConnector()
    doc = connector.fetch("https://example.com/posts/123")

    assert doc.source_type == "web"
    assert doc.canonical_url == "https://example.com/posts/123"
    assert doc.title == "Example Article"
    assert doc.author == "Alice Example"
    assert doc.author_handle == "example.com"
    assert "Hello world." in doc.text
    assert "Hello world.\n\nThis is a test article." in doc.markdown
    assert doc.capture_status == "partial"
    assert doc.metadata["content_type"] == "text/html; charset=utf-8"
    assert doc.lineage["connector"] == "web"


def test_web_connector_preserves_open_graph_and_article_image_candidates(monkeypatch):
    html = """
    <html>
      <head>
        <title>Fallback Browser Title</title>
        <meta property="og:title" content="Specific Canonical Article Title">
        <meta property="og:description" content="A factual description of the captured article.">
        <meta property="og:image" content="/images/cover.jpg">
        <meta property="og:image:width" content="1200">
        <meta property="og:image:height" content="675">
      </head>
      <body><main>
        <p>Article content.</p>
        <img src="/images/diagram.png" width="900" height="600" alt="System diagram">
      </main></body>
    </html>
    """
    monkeypatch.setattr(
        "xfetch.connectors.web.urlopen",
        lambda request, timeout=10: FakeResponse(html, "https://example.com/posts/123"),
    )

    doc = WebConnector().fetch("https://example.com/posts/123")

    assert doc.title == "Specific Canonical Article Title"
    assert doc.summary == "A factual description of the captured article."
    assert doc.assets == [
        {
            "url": "https://example.com/images/cover.jpg",
            "type": "image",
            "source": "open_graph",
            "width": "1200",
            "height": "675",
        },
        {
            "url": "https://example.com/images/diagram.png",
            "type": "image",
            "source": "article_image",
            "alt": "System diagram",
            "width": "900",
            "height": "600",
        },
    ]
    assert doc.content_kinds == ["text", "metadata", "images"]
    assert "Article content.\n\n![System diagram](https://example.com/images/diagram.png)" in doc.markdown
    assert "cover.jpg" not in doc.markdown
    assert doc.capture_status == "partial"


def test_web_connector_keeps_heading_list_and_image_position(monkeypatch):
    html = """
    <html>
      <head>
        <title>Page</title>
        <meta property="og:image" content="https://cdn.example.com/card.jpg">
      </head>
      <body>
        <nav><p>Menu</p><img src="https://cdn.example.com/logo.png" alt="Logo"></nav>
        <main>
          <h2>Overview</h2>
          <p>Intro paragraph.</p>
          <img src="https://cdn.example.com/diagram.png" alt="Diagram">
          <p>After image.</p>
          <ol><li>First</li><li>Second</li></ol>
        </main>
      </body>
    </html>
    """
    monkeypatch.setattr(
        "xfetch.connectors.web.urlopen",
        lambda request, timeout=10: FakeResponse(html, "https://example.com/posts/123"),
    )

    doc = WebConnector().fetch("https://example.com/posts/123")

    assert "## Overview\n\nIntro paragraph.\n\n![Diagram](https://cdn.example.com/diagram.png)\n\nAfter image." in doc.markdown
    assert "1. First\n2. Second" in doc.markdown
    assert doc.markdown.index("Intro paragraph.") < doc.markdown.index("diagram.png") < doc.markdown.index("After image.")
    assert "Menu" not in doc.markdown
    assert "logo.png" not in doc.markdown
    assert doc.capture_status == "partial"
    assert [asset["url"] for asset in doc.assets] == [
        "https://cdn.example.com/card.jpg",
        "https://cdn.example.com/diagram.png",
    ]


def test_web_connector_bounds_fallback_images_and_keeps_article_images(monkeypatch):
    many = "".join(f'<img alt="n{i}" src="/img-{i}.jpg">' for i in range(1, 6))

    def fetch(html):
        monkeypatch.setattr(
            "xfetch.connectors.web.urlopen",
            lambda request, timeout=10: FakeResponse(html, "https://example.com/posts/123"),
        )
        return WebConnector().fetch("https://example.com/posts/123")

    fallback = fetch(f"<html><head><title>Page</title></head><body><p>Intro.</p>{many}</body></html>")
    assert [asset["url"] for asset in fallback.assets] == [
        f"https://example.com/img-{i}.jpg" for i in range(1, 5)
    ]
    assert "img-5.jpg" not in fallback.markdown
    assert "Intro." in fallback.markdown

    prose = (
        "This paragraph is long enough to show the main element is the article "
        "body rather than a gallery of cards."
    )
    article = fetch(
        "<html><head><title>Page</title>"
        '<meta property="og:image" content="https://cdn.example.com/card.jpg">'
        f"</head><body><main><p>{prose}</p>{many}</main></body></html>"
    )
    assert [asset["url"] for asset in article.assets] == [
        "https://cdn.example.com/card.jpg",
        *[f"https://example.com/img-{i}.jpg" for i in range(1, 6)],
    ]
    assert "img-5.jpg" in article.markdown
    assert "card.jpg" not in article.markdown

    cards = "".join(
        f'<article><h2>Card {i}</h2><img alt="c{i}" src="/card-{i}.jpg"></article>'
        for i in range(1, 7)
    )
    listing = fetch(f"<html><head><title>Blog</title></head><body><main>{cards}</main></body></html>")
    assert [asset["url"] for asset in listing.assets] == [
        f"https://example.com/card-{i}.jpg" for i in range(1, 5)
    ]
    assert "card-6.jpg" not in listing.markdown
    assert "Card 6" in listing.markdown


def test_web_connector_matches_generic_http_urls_but_not_x_or_rss():
    connector = WebConnector()
    assert connector.can_handle("https://example.com/posts/123") is True
    assert connector.can_handle("https://x.com/alice/status/123") is False
    assert connector.can_handle("https://example.com/feed.xml") is False


def test_medium_403_uses_matching_feed_article(monkeypatch):
    from urllib.error import HTTPError
    url = 'https://medium.com/@author/工作流-f9a378cea385'
    def blocked(*args): raise HTTPError(url, 403, 'Forbidden', {}, None)
    monkeypatch.setattr('xfetch.connectors.web._fetch_url', blocked)
    rss = '''<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
    <item><title>Other</title><guid>other</guid></item>
    <item><title>Target</title><guid>https://medium.com/p/f9a378cea385</guid>
    <link>https://medium.com/@author/article-f9a378cea385</link>
    <content:encoded><![CDATA[<p>Full body</p>]]></content:encoded></item>
    </channel></rss>'''
    def feed(request, **kwargs):
        assert request.full_url == 'https://medium.com/feed/@author'
        return FakeResponse(rss, request.full_url, 'application/rss+xml')
    monkeypatch.setattr('xfetch.connectors.rss.urlopen', feed)
    doc = WebConnector().fetch(url)
    assert doc.title == 'Target'
    assert doc.text == 'Full body'
    assert doc.source_url == url
    assert doc.capture_status == 'partial'
    assert doc.metadata['fallback'] == 'medium_rss'
    import pytest
    with pytest.raises(ValueError, match='not found'):
        WebConnector().fetch(url.replace('f9a378cea385', 'aaaaaaaaaaaa'))


def test_zhihu_403_challenge_raises_explicit_error(monkeypatch):
    from urllib.error import HTTPError
    import pytest
    url = "https://zhuanlan.zhihu.com/p/692256732"

    class Body:
        def read(self, amt=-1):
            return b'<html><meta id="zh-zse-ck" content="token"></html>'

        def close(self):
            return None

    def blocked(*args, **kwargs):
        raise HTTPError(url, 403, "Forbidden", {}, Body())

    monkeypatch.setattr("xfetch.connectors.web._fetch_url", blocked)
    with pytest.raises(ValueError, match="zse-ck anti-bot challenge"):
        WebConnector().fetch(url)


def test_zhihu_403_without_challenge_marker_stays_http_error(monkeypatch):
    from urllib.error import HTTPError
    import pytest
    url = "https://zhuanlan.zhihu.com/p/692256732"

    class Body:
        def read(self, amt=-1):
            return b"<html>forbidden</html>"

        def close(self):
            return None

    def blocked(*args, **kwargs):
        raise HTTPError(url, 403, "Forbidden", {}, Body())

    monkeypatch.setattr("xfetch.connectors.web._fetch_url", blocked)
    with pytest.raises(HTTPError):
        WebConnector().fetch(url)


def test_non_medium_and_non_403_errors_do_not_use_feed(monkeypatch):
    from urllib.error import HTTPError
    import pytest
    for url, code in [('https://example.com/@author/article-f9a378cea385', 403),
                      ('https://medium.com.evil.test/@author/article-f9a378cea385', 403),
                      ('https://medium.com/@author/article-f9a378cea385', 404)]:
        def blocked(*args): raise HTTPError(url, code, 'Blocked', {}, None)
        monkeypatch.setattr('xfetch.connectors.web._fetch_url', blocked)
        with pytest.raises(HTTPError):
            WebConnector().fetch(url)
