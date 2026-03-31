import json
from pathlib import Path
import subprocess

from xfetch.cli import build_parser, main
from xfetch.config import load_config
from xfetch.models import NormalizedDocument



def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()



def _make_bundle(root: Path) -> Path:
    bundle_dir = root / "2026-03" / "x-123-alice"
    assets_dir = bundle_dir / "assets"
    assets_dir.mkdir(parents=True)
    (bundle_dir / "document.json").write_text(
        json.dumps(
            {
                "title": "Hello",
                "canonical_url": "https://x.com/alice/status/123",
                "author_handle": "alice",
                "created_at": "2026-03-31T00:00:00Z",
                "text": "hello world",
                "external_id": "123",
            }
        ) + "\n",
        encoding="utf-8",
    )
    (bundle_dir / "index.md").write_text("# hello\n", encoding="utf-8")
    (bundle_dir / "publish.json").write_text(
        '{\n  "published": false,\n  "public_url": null,\n  "target": null,\n  "revision": null\n}\n',
        encoding="utf-8",
    )
    (assets_dir / "image.jpg").write_text("fake-image", encoding="utf-8")
    return bundle_dir



def _init_target_repo(root: Path) -> Path:
    remote = root / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True)

    repo = root / "target-repo"
    subprocess.run(["git", "init", str(repo)], check=True)
    _git("config", "user.name", "Hermes Agent", cwd=repo)
    _git("config", "user.email", "hermes@example.com", cwd=repo)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    return repo



def test_build_parser_exposes_ingest_command():
    parser = build_parser()
    args = parser.parse_args(["ingest", "https://x.com/a/status/1"])
    assert args.command == "ingest"
    assert args.url == "https://x.com/a/status/1"



def test_build_parser_exposes_sync_command():
    parser = build_parser()
    args = parser.parse_args([
        "sync",
        "./content-out/2026-03/x-123-alice",
        "--target-repo",
        "../target",
        "--repo-owner",
        "guchengwei",
        "--repo-name",
        "x-reader",
    ])
    assert args.command == "sync"
    assert args.bundle_dir == "./content-out/2026-03/x-123-alice"
    assert args.target_repo == "../target"



def test_build_parser_exposes_publish_command():
    parser = build_parser()
    args = parser.parse_args([
        "publish",
        "./content-out/2026-03/x-123-alice",
        "--target-repo",
        "../target",
        "--repo-owner",
        "guchengwei",
        "--repo-name",
        "x-reader",
    ])
    assert args.command == "publish"
    assert args.bundle_dir == "./content-out/2026-03/x-123-alice"
    assert args.target_repo == "../target"



def test_load_config_prefers_explicit_content_root(tmp_path, monkeypatch):
    monkeypatch.setenv("XFETCH_CONTENT_ROOT", "/tmp/wrong")
    cfg = load_config(content_root=tmp_path)
    assert cfg.content_root == tmp_path.resolve()



def test_load_config_uses_repo_local_defaults_when_no_args_or_env(monkeypatch):
    monkeypatch.delenv("XFETCH_CONTENT_ROOT", raising=False)
    monkeypatch.delenv("XFETCH_SITE_ROOT", raising=False)
    cfg = load_config()
    assert cfg.content_root.name == "content-out"
    assert cfg.site_root.name == "site-out"



def test_cli_ingest_writes_bundle(tmp_path, monkeypatch):
    doc = NormalizedDocument(
        source_type="x",
        source_url="https://x.com/alice/status/123",
        canonical_url="https://x.com/alice/status/123",
        external_id="123",
        title="hello",
        author="alice",
        author_handle="alice",
        created_at="2026-03-31T00:00:00Z",
        language=None,
        text="hello",
        markdown="# hello",
        summary=None,
    )

    class FakeConnector:
        def fetch(self, url):
            return doc

    monkeypatch.setattr("xfetch.cli.pick_connector", lambda url: FakeConnector())
    rc = main(["ingest", "https://x.com/alice/status/123", "--content-root", str(tmp_path)])
    assert rc == 0



def test_cli_returns_2_for_unsupported_url(tmp_path):
    rc = main(["ingest", "https://example.com/post/123", "--content-root", str(tmp_path)])
    assert rc == 2



def test_cli_sync_writes_into_target_repo(tmp_path):
    bundle_dir = _make_bundle(tmp_path / "content-out")
    target_repo = tmp_path / "target-repo"
    target_repo.mkdir()

    rc = main([
        "sync",
        str(bundle_dir),
        "--target-repo",
        str(target_repo),
        "--repo-owner",
        "guchengwei",
        "--repo-name",
        "x-reader",
    ])
    assert rc == 0
    assert (target_repo / "content" / "2026-03" / "x-123-alice" / "document.json").exists()
    assert (target_repo / "site" / "d" / "x-123-alice" / "index.html").exists()



def test_cli_publish_writes_public_url_and_revision(tmp_path):
    bundle_dir = _make_bundle(tmp_path / "content-out")
    target_repo = _init_target_repo(tmp_path)

    rc = main([
        "publish",
        str(bundle_dir),
        "--target-repo",
        str(target_repo),
        "--repo-owner",
        "guchengwei",
        "--repo-name",
        "x-reader",
    ])
    assert rc == 0
    publish_data = json.loads((bundle_dir / "publish.json").read_text(encoding="utf-8"))
    assert publish_data["published"] is True
    assert publish_data["public_url"] == "https://guchengwei.github.io/x-reader/d/x-123-alice/"
    assert publish_data["revision"]



def test_cli_publish_returns_nonzero_for_non_git_target_repo(tmp_path):
    bundle_dir = _make_bundle(tmp_path / "content-out")
    target_repo = tmp_path / "not-a-git-repo"
    target_repo.mkdir()

    rc = main([
        "publish",
        str(bundle_dir),
        "--target-repo",
        str(target_repo),
        "--repo-owner",
        "guchengwei",
        "--repo-name",
        "x-reader",
    ])
    assert rc != 0
