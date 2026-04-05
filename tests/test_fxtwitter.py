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
                        {
                            "key": "0",
                            "value": {
                                "type": "MARKDOWN",
                                "data": {
                                    "markdown": "```python\nprint('hello')\n```"
                                },
                            },
                        }
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