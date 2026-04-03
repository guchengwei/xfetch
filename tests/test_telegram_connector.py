from xfetch.connectors.telegram import TelegramConnector


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


def test_telegram_connector_extracts_public_message_metadata(monkeypatch):
    html = """
    <html>
      <head>
        <meta property=\"og:title\" content=\"Telegram: Contact @ai_daily\" />
        <meta property=\"og:description\" content=\"This is a public Telegram post.\" />
        <meta property=\"og:image\" content=\"https://cdn4.telegram.org/file/test.jpg\" />
      </head>
      <body></body>
    </html>
    """

    monkeypatch.setattr(
        "xfetch.connectors.telegram.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://t.me/ai_daily/123"),
    )

    connector = TelegramConnector()
    doc = connector.fetch("https://t.me/ai_daily/123")

    assert doc.source_type == "telegram"
    assert doc.external_id == "ai_daily-123"
    assert doc.title == "Telegram: Contact @ai_daily"
    assert doc.author == "ai_daily"
    assert doc.author_handle == "ai_daily"
    assert doc.text == "This is a public Telegram post."
    assert doc.assets == [{"url": "https://cdn4.telegram.org/file/test.jpg", "type": "image"}]
    assert doc.metadata["channel"] == "ai_daily"
    assert doc.metadata["message_id"] == "123"


def test_telegram_connector_matches_public_telegram_urls_only():
    connector = TelegramConnector()
    assert connector.can_handle("https://t.me/ai_daily/123") is True
    assert connector.can_handle("https://telegram.me/ai_daily/123") is True
    assert connector.can_handle("https://example.com/ai_daily/123") is False
