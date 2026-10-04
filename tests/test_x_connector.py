from pathlib import Path
import json

from xfetch.backends.fxtwitter import parse_fxtwitter_payload
from xfetch.connectors.x import XConnector


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
    monkeypatch.setattr("xfetch.connectors.x.fetch_fxtwitter_json", lambda url: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(
        "xfetch.connectors.x.fetch_oembed_json",
        lambda url: {"author_name": "Alice", "html": "<blockquote><p>Hello from fallback with enough real content to be useful.</p></blockquote>"},
    )
    doc = XConnector().fetch("https://x.com/alice/status/123")
    assert doc.capture_status == "partial"
    assert doc.author_handle == "alice"
    assert doc.lineage["backend"] == "oembed"
    assert doc.metadata["fallback_from"] == "fxtwitter"


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
