import json

import pytest

from xfetch.connectors.bilibili import BilibiliConnector


class FakeResponse:
    def __init__(self, body: str, url: str, content_type: str = "application/json"):
        self._body = body.encode("utf-8")
        self._url = url
        self.headers = {"Content-Type": content_type}
    def read(self): return self._body
    def geturl(self): return self._url
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb): return False


def test_bilibili_connector_extracts_metadata_from_api(monkeypatch):
    payload = """
    {"code":0,"data":{"title":"Bilibili Test Video","desc":"This is a bilibili description.","owner":{"name":"UP Author"},"pic":"https://i0.hdslb.com/test-cover.jpg","duration":321,"stat":{"view":12345}}}
    """
    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", lambda request, timeout=10: FakeResponse(payload, request.full_url))
    doc = BilibiliConnector().fetch("https://www.bilibili.com/video/BV1xx411c7mD")
    assert doc.source_type == "bilibili"
    assert doc.external_id == "BV1xx411c7mD"
    assert doc.title == "Bilibili Test Video"
    assert doc.author == "UP Author"
    assert doc.author_handle == "up-author"
    assert "This is a bilibili description." in doc.text
    assert doc.assets == [{"url": "https://i0.hdslb.com/test-cover.jpg", "type": "image"}]
    assert doc.metadata["view_count"] == 12345
    assert doc.metadata["duration"] == 321
    assert doc.metadata["has_transcript"] is False
    assert doc.metadata["transcript_available"] is False
    assert doc.capture_status == "metadata_only"


def test_bilibili_connector_captures_public_subtitle(monkeypatch):
    view_payload = {
        "code": 0,
        "data": {
            "title": "Bilibili Test Video",
            "desc": "Video description.",
            "owner": {"name": "UP Author"},
            "pic": "https://i0.hdslb.com/test-cover.jpg",
            "cid": 987654,
            "duration": 321,
            "stat": {"view": 12345},
        },
    }
    player_payload = {
        "code": 0,
        "data": {
            "subtitle": {
                "subtitles": [
                    {
                        "lan": "zh-CN",
                        "lan_doc": "中文（简体）",
                        "subtitle_url": "//i0.hdslb.com/bfs/subtitle/test.json",
                    }
                ]
            }
        },
    }
    subtitle_payload = {
        "body": [
            {"from": 0.0, "to": 1.0, "content": "第一句"},
            {"from": 1.0, "to": 2.0, "content": "第二句"},
        ]
    }
    calls = []

    def fake_urlopen(request, timeout=10):
        calls.append(request.full_url)
        if "/x/web-interface/view" in request.full_url:
            return FakeResponse(json.dumps(view_payload), request.full_url)
        if "/x/player/v2" in request.full_url:
            return FakeResponse(json.dumps(player_payload), request.full_url)
        if "/bfs/subtitle/" in request.full_url:
            return FakeResponse(json.dumps(subtitle_payload), request.full_url)
        raise AssertionError(request.full_url)

    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", fake_urlopen)
    doc = BilibiliConnector().fetch("https://www.bilibili.com/video/BV1xx411c7mD")

    assert doc.capture_status == "partial"
    assert doc.content_kinds == ["text", "transcript", "metadata", "thumbnail"]
    assert doc.metadata["has_transcript"] is True
    assert doc.metadata["transcript_available"] is True
    assert doc.metadata["transcript_language"] == "zh-CN"
    assert doc.metadata["transcript_language_name"] == "中文（简体）"
    assert doc.metadata["cid"] == 987654
    assert doc.metadata["unpreserved_media"] == ["video"]
    assert doc.language == "zh-CN"
    assert "第一句\n第二句" in doc.text
    assert "## Transcript" in doc.markdown
    assert any("/x/player/v2" in call and "cid=987654" in call for call in calls)
    assert any(call.startswith("https://i0.hdslb.com/bfs/subtitle/") for call in calls)


def test_bilibili_connector_records_login_required_subtitles(monkeypatch):
    view_payload = {
        "code": 0,
        "data": {
            "title": "Bilibili Test Video",
            "desc": "Video description.",
            "owner": {"name": "UP Author"},
            "cid": 987654,
        },
    }
    player_payload = {
        "code": 0,
        "data": {
            "subtitle": {
                "need_login_subtitle": True,
                "subtitles": [],
            }
        },
    }

    def fake_urlopen(request, timeout=10):
        if "/x/web-interface/view" in request.full_url:
            return FakeResponse(json.dumps(view_payload), request.full_url)
        if "/x/player/v2" in request.full_url:
            return FakeResponse(json.dumps(player_payload), request.full_url)
        raise AssertionError(request.full_url)

    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", fake_urlopen)
    doc = BilibiliConnector().fetch("https://www.bilibili.com/video/BV1xx411c7mD")

    assert doc.capture_status == "metadata_only"
    assert doc.metadata["has_transcript"] is False
    assert doc.metadata["transcript_available"] is False
    assert doc.metadata["transcript_requires_login"] is True
    assert "transcript_capture_error" not in doc.metadata


def test_bilibili_connector_resolves_b23_short_link(monkeypatch):
    short_url = "https://b23.tv/AbCdEf"
    resolved_url = "https://www.bilibili.com/video/BV1xx411c7mD?spm_id_from=333.999.0.0"
    view_payload = {
        "code": 0,
        "data": {
            "title": "Resolved video",
            "desc": "Resolved description.",
            "owner": {"name": "UP Author"},
        },
    }
    calls = []

    def fake_urlopen(request, timeout=10):
        calls.append(request.full_url)
        if request.full_url == short_url:
            return FakeResponse("", resolved_url, "text/html")
        if "/x/web-interface/view" in request.full_url:
            return FakeResponse(json.dumps(view_payload), request.full_url)
        raise AssertionError(request.full_url)

    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", fake_urlopen)
    doc = BilibiliConnector().fetch(short_url)

    assert doc.source_url == short_url
    assert doc.external_id == "BV1xx411c7mD"
    assert doc.canonical_url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert calls[0] == short_url
    assert any("bvid=BV1xx411c7mD" in call for call in calls[1:])


def test_bilibili_connector_rejects_path_without_bvid(monkeypatch):
    def fail_urlopen(request, timeout=10):
        raise AssertionError("API should not be called")

    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", fail_urlopen)
    with pytest.raises(ValueError, match="Cannot extract Bilibili BV ID"):
        BilibiliConnector().fetch("https://www.bilibili.com/video/not-a-bv")


def test_bilibili_connector_matches_bilibili_urls_only():
    connector = BilibiliConnector()
    assert connector.can_handle("https://www.bilibili.com/video/BV1xx411c7mD") is True
    assert connector.can_handle("https://b23.tv/BV1xx411c7mD") is True
    assert connector.can_handle("https://www.bilibili.com/opus/1245575923568214023") is True
    assert connector.can_handle("https://example.com/video/BV1xx411c7mD") is False


def test_bilibili_connector_captures_opus_article(monkeypatch):
    payload = json.dumps({
        "code": 0,
        "message": "0",
        "data": {"item": {
            "basic": {"title": "Opus Title"},
            "modules": [
                {"module_author": {"name": "UP Author", "pub_ts": 1788846644}},
                {"module_content": {"paragraphs": [
                    {"para_type": 1, "text": {"nodes": [{"word": {"words": "Hello opus", "font_level": "xxLarge"}}]}},
                    {"para_type": 1, "text": {"nodes": [
                        {"word": {"words": "Body text", "font_level": "regular"}},
                        {"rich": {"text": "docs", "jump_url": "http://example.com/a"}},
                    ]}},
                    {"para_type": 2, "pic": {"pics": [{"url": "http://i0.hdslb.com/bfs/a.png", "width": 10, "height": 20}]}},
                    {"para_type": 5, "list": {"style": 1, "theme": "arabic_num", "start": 1, "items": [
                        {"nodes": [{"word": {"words": "One"}}]},
                        {"nodes": [{"word": {"words": "Two"}}]},
                    ]}},
                ]}},
            ],
        }},
    })
    calls = []

    def fake(request, timeout=10, cookie_jar=None):
        calls.append((request.full_url, cookie_jar))
        return FakeResponse(payload, request.full_url)

    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", fake)
    doc = BilibiliConnector().fetch("https://www.bilibili.com/opus/124?spm=1")
    assert doc.source_type == "bilibili"
    assert doc.external_id == "124"
    assert doc.canonical_url == "https://www.bilibili.com/opus/124"
    assert doc.title == "Opus Title"
    assert doc.author == "UP Author"
    assert doc.author_handle == "up-author"
    assert doc.created_at == "2026-09-08T05:50:44Z"
    assert "Hello opus" in doc.text
    assert "Body text[docs](https://example.com/a)" in doc.text
    assert "## Hello opus" in doc.markdown
    assert "1. One\n2. Two" in doc.markdown
    assert doc.assets == [{"url": "https://i0.hdslb.com/bfs/a.png", "type": "image", "width": 10, "height": 20}]
    assert doc.capture_status == "complete"
    assert doc.content_kinds == ["text", "metadata", "images"]
    assert calls[0][0] == "https://www.bilibili.com/opus/124?spm=1"
    assert "opus/detail" in calls[1][0] and "features=html" in calls[1][0] and "id=124" in calls[1][0]
    assert calls[0][1] is calls[1][1]


def test_bilibili_connector_reports_opus_risk_control(monkeypatch):
    payload = json.dumps({"code": -352, "message": "-352", "data": {}})

    def fake(request, timeout=10, cookie_jar=None):
        return FakeResponse(payload, request.full_url)

    monkeypatch.setattr("xfetch.connectors.bilibili.urlopen", fake)
    with pytest.raises(ValueError, match="risk control"):
        BilibiliConnector().fetch("https://www.bilibili.com/opus/124")


def test_bilibili_connector_marks_unknown_opus_blocks_partial(monkeypatch):
    payload = json.dumps({
        "code": 0,
        "data": {"item": {
            "basic": {"title": "Opus Title"},
            "modules": [{"module_content": {"paragraphs": [
                {"para_type": 1, "text": {"nodes": [{"word": {"words": "Kept"}}]}},
                {"para_type": 9, "text": {"nodes": []}},
            ]}}],
        }},
    })
    monkeypatch.setattr(
        "xfetch.connectors.bilibili.urlopen",
        lambda request, timeout=10, cookie_jar=None: FakeResponse(payload, request.full_url),
    )
    doc = BilibiliConnector().fetch("https://www.bilibili.com/opus/124")
    assert doc.capture_status == "partial"
    assert "Kept" in doc.text
    assert "not converted" in doc.metadata["capture_limitation"]
