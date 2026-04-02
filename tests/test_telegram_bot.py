import json

import pytest

from xfetch.cli import build_parser
from xfetch.models import NormalizedDocument
from xfetch.telegram_bot import (
    LEGACY_TELEGRAM_COMMANDS,
    PRIMARY_TELEGRAM_COMMAND,
    SaveResult,
    build_save_reply,
    parse_plaintext_save,
    parse_save_command,
    save_url,
)



def test_parse_save_command_extracts_url_from_primary_command():
    assert parse_save_command(f"/{PRIMARY_TELEGRAM_COMMAND} https://x.com/alice/status/123") == "https://x.com/alice/status/123"



def test_parse_save_command_accepts_legacy_commands():
    for command in LEGACY_TELEGRAM_COMMANDS:
        assert parse_save_command(f"/{command} https://x.com/alice/status/123") == "https://x.com/alice/status/123"



def test_parse_save_command_returns_none_without_url():
    assert parse_save_command(f"/{PRIMARY_TELEGRAM_COMMAND}") is None



def test_parse_plaintext_save_accepts_plain_save_command():
    assert parse_plaintext_save("save https://x.com/alice/status/123") == "https://x.com/alice/status/123"



def test_parse_plaintext_save_accepts_plain_link_command():
    assert parse_plaintext_save("link https://x.com/alice/status/123") == "https://x.com/alice/status/123"



def test_parse_plaintext_save_rejects_non_url_argument():
    assert parse_plaintext_save("save not-a-url") is None



def test_build_parser_exposes_telegram_bot_command():
    parser = build_parser()
    args = parser.parse_args(["telegram-bot", "--token", "secret-token"])
    assert args.command == "telegram-bot"
    assert args.token == "secret-token"



def test_build_save_reply_for_local_ingest(tmp_path):
    result = SaveResult(bundle_dir=tmp_path / "2026-03" / "x-123-alice", public_url=None, revision=None, published=False)
    reply = build_save_reply(result)
    assert "Saved locally" in reply
    assert str(result.bundle_dir) in reply



def test_build_save_reply_for_published_bundle(tmp_path):
    result = SaveResult(
        bundle_dir=tmp_path / "2026-03" / "x-123-alice",
        public_url="https://guchengwei.github.io/x-reader/d/x-123-alice/",
        revision="abc123",
        published=True,
    )
    reply = build_save_reply(result)
    assert "Published" in reply
    assert result.public_url in reply
    assert result.revision in reply



def test_save_url_writes_local_bundle_without_publish_target(tmp_path, monkeypatch):
    doc = NormalizedDocument(
        source_type="x",
        source_url="https://x.com/alice/status/123",
        canonical_url="https://x.com/alice/status/123",
        external_id="123",
        title="hello",
        author="Alice",
        author_handle="alice",
        created_at="2026-03-31T00:00:00Z",
        language=None,
        text="hello world",
        markdown="# hello",
        summary=None,
    )

    class FakeConnector:
        def can_handle(self, url):
            return True

        def fetch(self, url):
            assert url == "https://x.com/alice/status/123"
            return doc

    monkeypatch.setattr("xfetch.telegram_bot.XConnector", lambda: FakeConnector())

    result = save_url("https://x.com/alice/status/123", content_root=tmp_path)

    assert result.published is False
    assert result.public_url is None
    assert (result.bundle_dir / "document.json").exists()



def test_save_url_publishes_when_target_repo_configured(tmp_path, monkeypatch):
    doc = NormalizedDocument(
        source_type="x",
        source_url="https://x.com/alice/status/123",
        canonical_url="https://x.com/alice/status/123",
        external_id="123",
        title="hello",
        author="Alice",
        author_handle="alice",
        created_at="2026-03-31T00:00:00Z",
        language=None,
        text="hello world",
        markdown="# hello",
        summary=None,
    )

    class FakeConnector:
        def can_handle(self, url):
            return True

        def fetch(self, url):
            return doc

    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()
    destination = target_repo / "content" / "2026-03" / "x-123-alice"
    destination.mkdir(parents=True)
    (destination / "publish.json").write_text(json.dumps({"published": False, "public_url": None, "target": None, "revision": None}) + "\n", encoding="utf-8")

    class FakeSyncResult:
        bundle_destination_dir = destination
        site_destination_path = target_repo / "site" / "d" / "x-123-alice" / "index.html"
        target_path = "content/2026-03/x-123-alice"
        published = False
        public_url = None
        revision = None

    monkeypatch.setattr("xfetch.telegram_bot.XConnector", lambda: FakeConnector())
    monkeypatch.setattr("xfetch.telegram_bot.render_bundle_page", lambda bundle_dir, site_root, public_url=None: tmp_path / "site-out" / "d" / bundle_dir.name / "index.html")
    monkeypatch.setattr("xfetch.telegram_bot.sync_bundle_to_repo", lambda **kwargs: FakeSyncResult())
    monkeypatch.setattr("xfetch.telegram_bot.publish_repo", lambda target_repo, branch, commit_message: "abc123")

    result = save_url(
        "https://x.com/alice/status/123",
        content_root=tmp_path / "content-out",
        target_repo=target_repo,
        repo_owner="guchengwei",
        repo_name="x-reader",
    )

    payload = json.loads((result.bundle_dir / "publish.json").read_text(encoding="utf-8"))
    assert result.published is True
    assert result.public_url == "https://guchengwei.github.io/x-reader/d/x-123-alice/"
    assert result.revision == "abc123"
    assert payload["published"] is True
    assert payload["public_url"] == result.public_url
    assert payload["revision"] == "abc123"
