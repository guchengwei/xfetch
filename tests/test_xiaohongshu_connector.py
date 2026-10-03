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


def test_xiaohongshu_html_caption_keeps_image_position_and_gallery_order(monkeypatch):
    html = """
    <html><head><script>
      window.__INITIAL_STATE__ = {
        "note": {"noteDetailMap": {"67b8e3f5000000000b00d8e2": {"note": {
          "title": "Structured note",
          "desc": "<p>Before.</p><img alt=\\"Shot\\" src=\\"https://cdn.example.com/inline.jpg\\"><h2>Next</h2><p>After.</p>",
          "type": "normal",
          "user": {"nickname": "Alice XHS"},
          "imageList": [
            {"urlDefault": "https://cdn.example.com/inline.jpg"},
            {"urlDefault": "https://cdn.example.com/extra.jpg"}
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
    assert "Before.\n\n![Shot](https://cdn.example.com/inline.jpg)\n\n## Next\n\nAfter." in doc.markdown
    assert doc.markdown.index("Before.") < doc.markdown.index("inline.jpg") < doc.markdown.index("## Next") < doc.markdown.index("After.")
    assert doc.markdown.index("After.") < doc.markdown.index("extra.jpg")
    assert [asset["url"] for asset in doc.assets] == [
        "https://cdn.example.com/inline.jpg",
        "https://cdn.example.com/extra.jpg",
    ]
    assert doc.capture_status == "complete"


def test_xiaohongshu_connector_matches_site_and_short_urls():
    connector = XiaohongshuConnector()
    assert connector.can_handle("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2") is True
    assert connector.can_handle("https://xhslink.com/abc123") is True
    assert connector.can_handle("https://example.com/post/1") is False
