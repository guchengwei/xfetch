from xfetch.cli import build_parser
from xfetch.config import load_config


def test_build_parser_exposes_ingest_command():
    parser = build_parser()
    args = parser.parse_args(["ingest", "https://x.com/a/status/1"])
    assert args.command == "ingest"
    assert args.url == "https://x.com/a/status/1"


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
