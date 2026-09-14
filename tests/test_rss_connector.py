from xfetch.connectors.rss import RSSConnector


class FakeResponse:
    def __init__(self, body: str, url: str, content_type: str = "application/rss+xml"):
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


def test_rss_connector_normalizes_latest_entry(monkeypatch):
    rss_xml = """
    <rss version=\"2.0\">
      <channel>
        <title>Example Feed</title>
        <item>
          <title>First post</title>
          <link>https://example.com/posts/1</link>
          <guid>post-1</guid>
          <author>alice@example.com (Alice Example)</author>
          <pubDate>Tue, 01 Apr 2026 12:00:00 GMT</pubDate>
          <description>Hello from RSS.</description>
        </item>
      </channel>
    </rss>
    """

    monkeypatch.setattr(
        "xfetch.connectors.rss.urlopen",
        lambda request, timeout=10: FakeResponse(rss_xml, "https://example.com/feed.xml"),
    )

    connector = RSSConnector()
    doc = connector.fetch("https://example.com/feed.xml")

    assert doc.source_type == "rss"
    assert doc.source_url == "https://example.com/feed.xml"
    assert doc.canonical_url == "https://example.com/posts/1"
    assert doc.title == "First post"
    assert doc.author == "Alice Example"
    assert doc.author_handle == "example.com"
    assert doc.created_at == "2026-04-01T12:00:00Z"
    assert "Hello from RSS." in doc.text
    assert doc.metadata["feed_title"] == "Example Feed"
    assert doc.lineage["connector"] == "rss"


def test_rss_connector_matches_feed_urls_only():
    connector = RSSConnector()
    assert connector.can_handle("https://example.com/feed.xml") is True
    assert connector.can_handle("https://example.com/feed") is True
    assert connector.can_handle("https://example.com/posts/1") is False


def test_encoded_body_exact_entry_and_image(monkeypatch):
    rss = '''<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
    <item><title>Wrong latest article</title><guid>other</guid></item>
    <item><title>Requested</title><guid>target</guid><link>https://medium.com/@author/article</link>
    <description>Short teaser</description><content:encoded><![CDATA[<p>Full body 中文</p>
    <img src="https://cdn.example.com/diagram.png"/>
    <img src="https://medium.com/_/stat?event=post.clientViewed"/>]]></content:encoded></item>
    </channel></rss>'''
    monkeypatch.setattr('xfetch.connectors.rss.urlopen', lambda *args, **kwargs: FakeResponse(rss, 'https://medium.com/feed/@author'))
    doc = RSSConnector().fetch('https://medium.com/feed/@author', entry_id='target')
    assert doc.title == 'Requested'
    assert doc.text == 'Full body 中文'
    assert 'Short teaser' not in doc.markdown
    assert doc.capture_status == 'complete'
    assert doc.content_kinds == ['text', 'metadata', 'images']
    assert len(doc.assets) == 1
    assert 'https://cdn.example.com/diagram.png' in doc.markdown
    import pytest
    with pytest.raises(ValueError, match='not found'):
        RSSConnector().fetch('https://medium.com/feed/@author', entry_id='missing')


def test_title_only_is_metadata_only(monkeypatch):
    rss = '<rss><channel><item><title>Only title</title></item></channel></rss>'
    monkeypatch.setattr('xfetch.connectors.rss.urlopen', lambda *args, **kwargs: FakeResponse(rss, 'https://example.com/feed'))
    doc = RSSConnector().fetch('https://example.com/feed')
    assert doc.capture_status == 'metadata_only'
    assert doc.content_kinds == ['metadata']
