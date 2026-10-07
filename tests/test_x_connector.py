from pathlib import Path
import json

import pytest

from xfetch.backends.fxtwitter import parse_fxtwitter_payload
from xfetch.backends.x_guest import guest_response_to_status_payload, x_api_response_to_status_payload
from xfetch.connectors.x import XConnector


_ARTICLE_URL = "https://x.com/dotey/status/2105181393638531536"
_GUEST_FIXTURE = json.loads(Path("tests/fixtures/x_guest_article.json").read_text())


def _fail(message):
    def _raise(_url):
        raise RuntimeError(message)

    return _raise


def test_parse_fxtwitter_payload_extracts_minimum_fields():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    raw = parse_fxtwitter_payload(payload)
    assert raw["tweet_id"]
    assert raw["screen_name"]
    assert raw["text"]
    assert raw["markdown"]


def test_x_connector_normalizes_fixture_payload():
    payload = json.loads(Path("tests/fixtures/fxtwitter_single_tweet.json").read_text())
    doc = XConnector().normalize_payload(source_url="https://x.com/alice/status/123", payload=payload)
    assert doc.source_type == "x"
    assert doc.external_id == "123"
    assert doc.author_handle == "alice"
    assert doc.metadata["platform"] == "x"
    assert doc.lineage["backend"] == "fxtwitter"
    assert doc.capture_status == "complete"
    assert "# hello from fixture" in doc.markdown.lower()


def test_x_connector_uses_partial_oembed_fallback_with_stable_handle(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", _fail("down"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_vxtwitter_json", _fail("down"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_guest_status_payload", _fail("down"))
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_oembed_json",
        lambda url: {"author_name": "Alice", "html": "<blockquote><p>Hello from fallback with enough real content to be useful.</p></blockquote>"},
    )
    doc = XConnector().fetch("https://x.com/alice/status/123")
    assert doc.capture_status == "partial"
    assert doc.author_handle == "alice"
    assert doc.lineage["backend"] == "oembed"
    assert doc.metadata["fallback_from"] == "fxtwitter"
    assert doc.metadata["fallback_error"] == "RuntimeError"


def test_x_connector_saves_article_from_guest_when_fx_vx_blocked_and_oembed_is_thin(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_vxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_guest_status_payload",
        lambda url: guest_response_to_status_payload(_GUEST_FIXTURE),
    )
    oembed_calls = {"n": 0}

    def oembed(_url):
        oembed_calls["n"] += 1
        return {"author_name": "宝玉", "html": "<blockquote><p>https://t.co/LAqhpQoY1c</p></blockquote>"}

    monkeypatch.setattr("xfetch.connectors.x.fetch_oembed_json", oembed)
    doc = XConnector().fetch(_ARTICLE_URL)
    assert oembed_calls["n"] == 0
    assert doc.lineage["backend"] == "x-guest"
    assert doc.metadata["fallback_from"] == "fxtwitter"
    assert doc.author == "宝玉"
    assert doc.author_handle == "dotey"
    assert doc.title.startswith("Claude Opus 5.5")
    assert doc.text.count("先说结论：视频是程序画出来的") == 1
    assert "第二段把生成步骤写完整，不是短链接。" in doc.text
    assert "https://t.co/LAqhpQoY1c" not in doc.text
    assert "## 过程" in doc.markdown
    assert "https://pbs.twimg.com/media/cover.jpg" in doc.markdown
    assert "https://pbs.twimg.com/media/inline.jpg" in doc.markdown
    assert doc.markdown.index("cover.jpg") < doc.markdown.index("inline.jpg")
    assert doc.capture_status == "partial"
    assert doc.metadata["unpreserved_media"] == ["video"]
    assert {asset["url"] for asset in doc.assets} >= {
        "https://pbs.twimg.com/media/cover.jpg",
        "https://pbs.twimg.com/media/inline.jpg",
    }


def test_fxtwitter_article_url_card_still_saves_the_article_body(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_fxtwitter_json",
        lambda url: {
            "tweet": {
                "id": "2105181393638531536",
                "url": _ARTICLE_URL,
                "text": "https://x.com/i/article/2105179653925150720",
                "raw_text": {"text": "https://t.co/LAqhpQoY1c"},
                "author": {"screen_name": "dotey", "name": "宝玉"},
                "article": {
                    "title": "Claude Opus 5.5 是怎么做出视频的",
                    "content": {"blocks": [{"type": "unstyled", "text": "正文在 FxTwitter 的 article 里，不应该退回短链。"}]},
                },
            }
        },
    )
    monkeypatch.setattr("xfetch.connectors.x.fetch_vxtwitter_json", _fail("vx should not run"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_guest_status_payload", _fail("guest should not run"))
    doc = XConnector().fetch(_ARTICLE_URL)
    assert doc.lineage["backend"] == "fxtwitter"
    assert "正文在 FxTwitter 的 article 里，不应该退回短链。" in doc.text
    assert "https://t.co/LAqhpQoY1c" not in doc.text


def test_vxtwitter_article_is_preferred_over_guest(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_vxtwitter_json",
        lambda url: {
            "tweet": {
                "id": "123",
                "url": "https://x.com/alice/status/123",
                "text": "",
                "raw_text": {"text": "https://t.co/abc"},
                "author": {"screen_name": "alice", "name": "Alice"},
                "article": {
                    "title": "From VxTwitter",
                    "content": {"blocks": [{"type": "unstyled", "text": "VxTwitter kept the article body intact."}]},
                },
            }
        },
    )
    monkeypatch.setattr("xfetch.connectors.x.fetch_guest_status_payload", _fail("guest should not run"))
    doc = XConnector().fetch("https://x.com/alice/status/123")
    assert doc.lineage["backend"] == "vxtwitter"
    assert "VxTwitter kept the article body intact." in doc.text
    assert doc.capture_status == "complete"


def test_fxtwitter_text_ending_in_ellipsis_is_not_treated_as_a_thin_card(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_fxtwitter_json",
        lambda url: {
            "tweet": {
                "id": "123",
                "url": "https://x.com/alice/status/123",
                "text": "A real post that happens to end with an ellipsis...",
                "author": {"screen_name": "alice", "name": "Alice"},
            }
        },
    )
    doc = XConnector().fetch("https://x.com/alice/status/123")
    assert doc.lineage["backend"] == "fxtwitter"
    assert doc.text.endswith("...")


def test_thin_fxtwitter_article_card_continues_to_guest(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)

    def thin_fx(_url):
        return {
            "tweet": {
                "id": "2105181393638531536",
                "url": _ARTICLE_URL,
                "text": "https://t.co/LAqhpQoY1c",
                "raw_text": {"text": "https://t.co/LAqhpQoY1c"},
                "author": {"screen_name": "dotey", "name": "宝玉"},
            }
        }

    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", thin_fx)
    monkeypatch.setattr("xfetch.connectors.x.fetch_vxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_guest_status_payload",
        lambda url: guest_response_to_status_payload(_GUEST_FIXTURE),
    )
    doc = XConnector().fetch(_ARTICLE_URL)
    assert doc.lineage["backend"] == "x-guest"
    assert "第二段把生成步骤写完整，不是短链接。" in doc.text


def test_x_api_token_saves_article_plain_text_when_guest_fails(monkeypatch):
    monkeypatch.setenv("XFETCH_X_BEARER_TOKEN", "test-token")
    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_vxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_guest_status_payload", _fail("guest-down"))
    payload = {
        "data": {
            "id": "2105181393638531536",
            "text": "https://t.co/LAqhpQoY1c",
            "lang": "zxx",
            "created_at": "2026-09-30T06:22:11.000Z",
            "author_id": "3178231",
            "public_metrics": {"like_count": 1, "retweet_count": 2, "reply_count": 3, "impression_count": 4},
            "article": {
                "title": "Claude Opus 5.5 是怎么做出视频的",
                "plain_text": "先说结论：视频是程序画出来的。\n\n这一段来自官方帖子接口，足够作为正文保存。",
                "cover_media_url": "https://pbs.twimg.com/media/cover.jpg",
            },
        },
        "includes": {"users": [{"id": "3178231", "name": "宝玉", "username": "dotey"}]},
    }
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_x_api_status_payload",
        lambda url: x_api_response_to_status_payload(payload),
    )
    doc = XConnector().fetch(_ARTICLE_URL)
    assert doc.lineage["backend"] == "x-api"
    assert doc.author_handle == "dotey"
    assert "这一段来自官方帖子接口，足够作为正文保存。" in doc.text
    assert "https://t.co/LAqhpQoY1c" not in doc.text
    assert "https://pbs.twimg.com/media/cover.jpg" in doc.markdown
    assert "test-token" not in doc.markdown


def test_thin_oembed_article_card_is_not_saved(monkeypatch):
    monkeypatch.delenv("XFETCH_X_BEARER_TOKEN", raising=False)
    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_vxtwitter_json", _fail("cloudflare"))
    monkeypatch.setattr("xfetch.connectors.x.fetch_guest_status_payload", _fail("guest-down"))
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_oembed_json",
        lambda url: {"author_name": "宝玉", "html": "<blockquote><p>https://t.co/LAqhpQoY1c</p></blockquote>"},
    )
    with pytest.raises(ValueError, match="thin or truncated"):
        XConnector().fetch(_ARTICLE_URL)


def test_x_photo_post_keeps_image_in_markdown_and_complete_status():
    image_url = "https://pbs.twimg.com/media/photo-1.jpg"
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "photo post",
            "raw_text": {"text": "photo post"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "media": {"photos": [{"id": "m1", "type": "photo", "url": image_url}]},
        }
    }
    doc = XConnector().normalize_payload("https://x.com/alice/status/123", payload)
    assert f"![]({image_url})" in doc.markdown
    assert doc.markdown.index("photo post") < doc.markdown.index(image_url)
    assert doc.capture_status == "complete"


def test_x_photo_url_in_the_text_still_becomes_an_image():
    image_url = "https://pbs.twimg.com/media/photo-1.jpg"
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": f"look {image_url}",
            "raw_text": {"text": f"look {image_url}"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "media": {"photos": [{"id": "m1", "type": "photo", "url": image_url}]},
        }
    }
    doc = XConnector().normalize_payload("https://x.com/alice/status/123", payload)
    assert f"![]({image_url})" in doc.markdown
    assert doc.markdown.index(f"look {image_url}") < doc.markdown.index(f"![]({image_url})")
    assert doc.capture_status == "complete"


def test_x_text_without_inline_image_is_not_a_complete_visual_capture():
    doc = XConnector()._normalize_raw(
        "https://x.com/alice/status/123",
        {
            "text": "hello",
            "markdown": "hello",
            "screen_name": "alice",
            "display_name": "Alice",
            "tweet_id": "123",
            "canonical_url": "https://x.com/alice/status/123",
            "created_at": None,
            "language": None,
            "stats": {},
            "assets": [{"url": "https://cdn.example.com/pic.jpg", "type": "image"}],
            "has_unpreserved_video": False,
        },
        backend="fxtwitter",
        capture_status="complete",
    )
    assert "pic.jpg" not in doc.markdown
    assert doc.capture_status == "partial"


def test_x_connector_marks_video_post_partial():
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "video post",
            "raw_text": {"text": "video post"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "media": {"videos": [{"type": "video", "url": "https://video.twimg.com/video.mp4"}]},
        }
    }
    doc = XConnector().normalize_payload("https://x.com/alice/status/123", payload)
    assert doc.capture_status == "partial"
    assert doc.metadata["unpreserved_media"] == ["video"]
