from xfetch.connectors.wechat import WeChatConnector


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


def test_wechat_connector_extracts_article_fields(monkeypatch):
    html = """
    <html>
      <head>
        <meta property=\"og:title\" content=\"WeChat Article Title\" />
        <meta name=\"author\" content=\"Alice Writer\" />
        <script>
          var nickname = \"AI Daily\";
          var ct = \"1711958400\";
        </script>
      </head>
      <body>
        <div class=\"rich_media_content \" id=\"js_content\">
          <p>First paragraph.</p>
          <p>Second paragraph.</p>
          <img data-src=\"https://mmbiz.qpic.cn/image-1.jpg\" />
        </div>
      </body>
    </html>
    """

    monkeypatch.setattr(
        "xfetch.connectors.wechat.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://mp.weixin.qq.com/s/example"),
    )

    connector = WeChatConnector()
    doc = connector.fetch("https://mp.weixin.qq.com/s/example")

    assert doc.source_type == "wechat"
    assert doc.title == "WeChat Article Title"
    assert doc.author == "Alice Writer"
    assert doc.author_handle == "AI Daily"
    assert doc.created_at == "2024-04-01T08:00:00Z"
    assert "First paragraph." in doc.text
    assert "Second paragraph." in doc.text
    assert "First paragraph.\n\nSecond paragraph." in doc.markdown
    assert "Second paragraph.\n\n![](https://mmbiz.qpic.cn/image-1.jpg)" in doc.markdown
    assert doc.assets == [{"url": "https://mmbiz.qpic.cn/image-1.jpg", "type": "image"}]
    assert doc.capture_status == "complete"
    assert doc.metadata["account"] == "AI Daily"


def test_wechat_markdown_keeps_heading_structure_and_image_position(monkeypatch):
    html = """
    <html>
      <head>
        <meta property="og:title" content="Structured Note" />
        <meta name="author" content="Alice Writer" />
      </head>
      <body>
        <img data-src="https://mmbiz.qpic.cn/outside.jpg" />
        <div class="rich_media_content" id="js_content">
          <p>Before the figure.</p>
          <h2>Section title</h2>
          <img src="https://mmbiz.qpic.cn/placeholder.gif" data-src="https://mmbiz.qpic.cn/chart.jpg" alt="Chart" />
          <p>After the figure.</p>
          <script>do not capture</script>
        </div>
      </body>
    </html>
    """
    monkeypatch.setattr(
        "xfetch.connectors.wechat.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://mp.weixin.qq.com/s/example"),
    )

    doc = WeChatConnector().fetch("https://mp.weixin.qq.com/s/example")

    assert "Before the figure.\n\n## Section title\n\n![Chart](https://mmbiz.qpic.cn/chart.jpg)\n\nAfter the figure." in doc.markdown
    assert doc.markdown.index("Before the figure.") < doc.markdown.index("## Section title") < doc.markdown.index("chart.jpg") < doc.markdown.index("After the figure.")
    assert "outside.jpg" not in doc.markdown
    assert "placeholder.gif" not in doc.markdown
    assert "do not capture" not in doc.markdown
    assert doc.assets == [{"url": "https://mmbiz.qpic.cn/chart.jpg", "type": "image"}]
    assert doc.capture_status == "complete"
    assert "Before the figure." in doc.text
    assert "chart.jpg" not in doc.text


def test_wechat_connector_matches_mp_weixin_urls_only():
    connector = WeChatConnector()
    assert connector.can_handle("https://mp.weixin.qq.com/s/example") is True
    assert connector.can_handle("https://example.com/s/example") is False
