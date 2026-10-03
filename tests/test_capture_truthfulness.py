import pytest

from xfetch.connectors.wechat import WeChatConnector
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


def test_xiaohongshu_video_note_is_partial(monkeypatch):
    html = '''
    <script>
      window.__INITIAL_STATE__ = {
        "note": {"noteDetailMap": {"67b8e3f5000000000b00d8e2": {"note": {
          "title": "Video note",
          "desc": "Video description",
          "type": "video",
          "user": {"nickname": "Alice XHS"},
          "imageList": [{"urlDefault": "https://sns-webpic-qc.xhscdn.com/cover.jpg"}]
        }}}}
      };
    </script>
    '''
    monkeypatch.setattr(
        "xfetch.connectors.xiaohongshu.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2"),
    )
    doc = XiaohongshuConnector().fetch("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2")
    assert doc.capture_status == "partial"
    assert doc.metadata["unpreserved_media"] == ["video"]
    assert "![](https://sns-webpic-qc.xhscdn.com/cover.jpg)" in doc.markdown


def test_wechat_verification_page_fails_even_with_body_text(monkeypatch):
    html = '''
    <html><body>
      <div class="rich_media_content"><p>Some body text</p></div>
      <div>访问过于频繁，请去验证</div>
    </body></html>
    '''
    monkeypatch.setattr(
        "xfetch.connectors.wechat.urlopen",
        lambda request, timeout=15: FakeResponse(html, "https://mp.weixin.qq.com/s/example"),
    )
    with pytest.raises(ValueError, match="verification"):
        WeChatConnector().fetch("https://mp.weixin.qq.com/s/example")
