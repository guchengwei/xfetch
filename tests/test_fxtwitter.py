from xfetch.backends.fxtwitter import parse_fxtwitter_payload


def test_parse_fxtwitter_payload_falls_back_to_raw_text_when_text_empty():
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "",
            "raw_text": {"text": "hello from raw text"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "created_at": "Sat Mar 28 03:09:48 +0000 2026",
            "media": {"all": []},
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert result["text"] == "hello from raw text"


def test_parse_fxtwitter_payload_uses_article_content_when_post_is_article():
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "",
            "raw_text": {"text": "https://t.co/abc"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "created_at": "Sat Mar 28 03:09:48 +0000 2026",
            "article": {
                "title": "Article title",
                "preview_text": "Preview text",
                "content": {
                    "blocks": [
                        {"type": "header-two", "text": "Heading"},
                        {"type": "unstyled", "text": "Paragraph one"},
                        {"type": "unstyled", "text": "Paragraph two"},
                    ]
                },
            },
            "media": {"all": []},
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert "Article title" in result["text"]
    assert "Heading" in result["text"]
    assert "Paragraph one" in result["text"]
    assert "https://t.co/abc" not in result["text"]


def test_parse_fxtwitter_payload_preserves_markdown_entities_in_article_blocks():
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "",
            "raw_text": {"text": "https://t.co/abc"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "created_at": "Sat Mar 28 03:09:48 +0000 2026",
            "article": {
                "title": "Article title",
                "preview_text": "Preview text",
                "content": {
                    "blocks": [
                        {"type": "unstyled", "text": "Intro paragraph"},
                        {"type": "atomic", "text": " ", "entityRanges": [{"key": 0, "offset": 0, "length": 1}]},
                        {"type": "unstyled", "text": "Outro paragraph"},
                    ],
                    "entityMap": [
                        {"key": "0", "value": {"type": "MARKDOWN", "data": {"markdown": "```python\nprint('hello')\n```"}}}
                    ],
                },
            },
            "media": {"all": []},
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert "Intro paragraph" in result["text"]
    assert "```python" in result["text"]
    assert "print('hello')" in result["text"]
    assert "Outro paragraph" in result["text"]


def test_parse_fxtwitter_payload_preserves_inline_article_images_and_assets():
    image_url = "https://pbs.twimg.com/media/example-inline.jpg"
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "",
            "raw_text": {"text": "https://t.co/abc"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "created_at": "Sat Mar 28 03:09:48 +0000 2026",
            "article": {
                "title": "Article title",
                "preview_text": "Preview text",
                "content": {
                    "blocks": [
                        {"type": "unstyled", "text": "Before image"},
                        {"type": "atomic", "text": " ", "entityRanges": [{"key": 0, "offset": 0, "length": 1}]},
                        {"type": "unstyled", "text": "After image"},
                    ],
                    "entityMap": [
                        {"key": "0", "value": {"type": "MEDIA", "data": {"mediaItems": [{"mediaId": "999"}]}}}
                    ],
                },
                "media_entities": [
                    {"media_id": "999", "media_info": {"original_img_url": image_url}}
                ],
            },
            "media": {"all": []},
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert "Before image" in result["markdown"]
    assert f"![]({image_url})" in result["markdown"]
    assert result["markdown"].index("Before image") < result["markdown"].index(f"![]({image_url})") < result["markdown"].index("After image")
    assert result["assets"] == [{"url": image_url, "type": "image", "source": "article_inline", "media_id": "999"}]


def test_parse_fxtwitter_payload_preserves_article_heading_list_and_code_structure():
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "",
            "raw_text": {"text": "https://t.co/abc"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "article": {
                "title": "Article title",
                "content": {
                    "blocks": [
                        {"type": "header-two", "text": "Heading"},
                        {"type": "unstyled", "text": "Paragraph one"},
                        {"type": "ordered-list-item", "text": "First"},
                        {"type": "ordered-list-item", "text": "Second"},
                        {"type": "code-block", "text": "keep  spaces\nnext"},
                    ]
                },
            },
            "media": {"all": []},
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert "## Heading\n\nParagraph one\n\n1. First\n2. Second" in result["markdown"]
    assert "```\nkeep  spaces\nnext\n```" in result["markdown"]
    assert "## Heading" not in result["text"]
    assert "Heading" in result["text"]


def test_parse_fxtwitter_payload_places_tweet_photos_after_text():
    first = "https://pbs.twimg.com/media/photo-1.jpg"
    second = "https://pbs.twimg.com/media/photo-2.jpg"
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "photo post",
            "raw_text": {"text": "photo post"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "media": {
                "photos": [
                    {"id": "m1", "type": "photo", "url": first},
                    {"id": "m2", "type": "photo", "url": second},
                ],
                "all": [
                    {"id": "m1", "type": "photo", "url": first},
                    {"id": "m2", "type": "photo", "url": second},
                ],
            },
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert result["markdown"].index("photo post") < result["markdown"].index(first) < result["markdown"].index(second)
    assert f"![]({first})" in result["markdown"]
    assert f"![]({second})" in result["markdown"]


def test_oembed_keeps_line_breaks_and_links():
    from xfetch.backends.fxtwitter import parse_oembed_payload

    payload = {
        "author_name": "Alice",
        "html": '<blockquote><p>First line<br>Second line <a href="https://example.com/a">docs</a> and more words.</p></blockquote>',
    }
    result = parse_oembed_payload(payload, "https://x.com/alice/status/123")
    assert "First line\n\nSecond line" in result["markdown"]
    assert "[docs](https://example.com/a)" in result["markdown"]


def test_parse_fxtwitter_payload_preserves_normal_tweet_photos():
    image_url = "https://pbs.twimg.com/media/photo-1.jpg"
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "photo post",
            "raw_text": {"text": "photo post"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "media": {
                "photos": [{"id": "m1", "type": "photo", "url": image_url}],
                "all": [{"id": "m1", "type": "photo", "url": image_url}],
            },
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert result["assets"] == [{"url": image_url, "type": "image", "source": "tweet_media", "media_id": "m1"}]
    assert result["has_unpreserved_video"] is False


def test_parse_fxtwitter_payload_marks_video_as_unpreserved():
    payload = {
        "tweet": {
            "id": "123",
            "url": "https://x.com/alice/status/123",
            "text": "video post",
            "raw_text": {"text": "video post"},
            "author": {"screen_name": "alice", "name": "Alice"},
            "media": {
                "videos": [{"id": "v1", "type": "video", "url": "https://video.twimg.com/video.mp4"}],
                "all": [{"id": "v1", "type": "video", "url": "https://video.twimg.com/video.mp4"}],
            },
        }
    }
    result = parse_fxtwitter_payload(payload)
    assert result["has_unpreserved_video"] is True
