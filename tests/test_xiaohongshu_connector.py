from xfetch.connectors.xiaohongshu import XiaohongshuConnector


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


def test_xiaohongshu_connector_extracts_note_from_initial_state(monkeypatch):
    html = """
    <html>
      <head>
        <script>
          window.__INITIAL_STATE__ = {
            "note": {
              "noteDetailMap": {
                "67b8e3f5000000000b00d8e2": {
                  "note": {
                    "title": "XHS Note",
                    "desc": "Line one\\nLine two",
                    "type": "normal",
                    "time": 1711958400000,
                    "user": {"nickname": "Alice XHS"},
                    "imageList": [
                      {"urlDefault": "https://sns-webpic-qc.xhscdn.com/img-1.jpg"}
                    ],
                    "tagList": [{"name": "AI"}, {"name": "Agents"}],
                    "interactInfo": {
                      "likedCount": "12",
                      "collectedCount": "3",
                      "commentCount": "4",
                      "shareCount": "1"
                    }
                  }
                }
              }
            }
          };
        </script>
      </head>
      <body></body>
    </html>
    """

    monkeypatch.setattr(
        "xfetch.connectors.xiaohongshu.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2"),
    )

    connector = XiaohongshuConnector()
    doc = connector.fetch("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2")

    assert doc.source_type == "xiaohongshu"
    assert doc.external_id == "67b8e3f5000000000b00d8e2"
    assert doc.title == "XHS Note"
    assert doc.author == "Alice XHS"
    assert doc.author_handle == "alice-xhs"
    assert doc.created_at == "2024-04-01T08:00:00Z"
    assert "Line one" in doc.text
    assert "Line one\n\nLine two\n\n![](https://sns-webpic-qc.xhscdn.com/img-1.jpg)" in doc.markdown
    assert doc.markdown.index("Line two") < doc.markdown.index("img-1.jpg")
    assert doc.capture_status == "complete"
    assert doc.tags == ["AI", "Agents"]
    assert doc.assets == [{"url": "https://sns-webpic-qc.xhscdn.com/img-1.jpg", "type": "image"}]
    assert doc.metadata["note_type"] == "image"
    assert doc.metadata["stats"]["likes"] == 12


def test_xiaohongshu_caption_keeps_literal_markup(monkeypatch):
    html = """
    <html><head><script>
      window.__INITIAL_STATE__ = {
        "note": {"noteDetailMap": {"67b8e3f5000000000b00d8e2": {"note": {
          "title": "Literal caption",
          "desc": "Show &lt;b&gt;bold&lt;/b&gt; and &lt;img src=&quot;https://cdn.example.com/evil.jpg&quot;&gt;",
          "type": "normal",
          "user": {"nickname": "Alice XHS"},
          "imageList": [
            {"urlDefault": "https://cdn.example.com/gallery.jpg"}
          ]
        }}}}
      };
    </script></head></html>
    """
    monkeypatch.setattr(
        "xfetch.connectors.xiaohongshu.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2"),
    )
    doc = XiaohongshuConnector().fetch("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2")
    caption = 'Show <b>bold</b> and <img src="https://cdn.example.com/evil.jpg">'
    assert caption in doc.text
    assert caption in doc.markdown
    assert "**bold**" not in doc.markdown
    assert "![evil" not in doc.markdown
    assert doc.markdown.index(caption) < doc.markdown.index("gallery.jpg")
    assert [asset["url"] for asset in doc.assets] == ["https://cdn.example.com/gallery.jpg"]
    assert doc.capture_status == "complete"


def test_xiaohongshu_caption_url_still_gets_a_gallery_image(monkeypatch):
    html = """
    <html><head><script>
      window.__INITIAL_STATE__ = {
        "note": {"noteDetailMap": {"67b8e3f5000000000b00d8e2": {"note": {
          "title": "Linked shot",
          "desc": "See https://cdn.example.com/gallery.jpg for the shot",
          "type": "normal",
          "user": {"nickname": "Alice XHS"},
          "imageList": [
            {"urlDefault": "https://cdn.example.com/gallery.jpg"}
          ]
        }}}}
      };
    </script></head></html>
    """
    monkeypatch.setattr(
        "xfetch.connectors.xiaohongshu.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2"),
    )
    doc = XiaohongshuConnector().fetch("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2")
    image = "https://cdn.example.com/gallery.jpg"
    assert f"See {image} for the shot" in doc.markdown
    assert f"![]({image})" in doc.markdown
    assert doc.markdown.index("for the shot") < doc.markdown.index(f"![]({image})")
    assert [asset["url"] for asset in doc.assets] == [image]
    assert doc.capture_status == "complete"


def test_xiaohongshu_connector_matches_site_and_short_urls():
    connector = XiaohongshuConnector()
    assert connector.can_handle("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2") is True
    assert connector.can_handle("https://xhslink.com/abc123") is True
    assert connector.can_handle("https://example.com/post/1") is False
