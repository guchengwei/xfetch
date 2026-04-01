from pathlib import Path
import os
import stat

from xfetch.cli import build_parser
from xfetch.telegram_setup import SetupConfig, render_env_file, write_env_file, service_defaults_for_platform



def test_build_parser_exposes_setup_telegram_bot_command():
    parser = build_parser()
    args = parser.parse_args(["setup-telegram-bot"])
    assert args.command == "setup-telegram-bot"



def test_render_env_file_includes_token_and_publish_target():
    cfg = SetupConfig(
        telegram_bot_token="123:abc",
        target_repo=Path("/Users/zion/link-vault-publish"),
        repo_owner="guchengwei",
        repo_name="link-vault",
        content_root=Path("/Users/zion/x-tweet-fetcher/content-out"),
    )
    text = render_env_file(cfg)
    assert "TELEGRAM_BOT_TOKEN=123:abc" in text
    assert "XFETCH_TARGET_REPO=/Users/zion/link-vault-publish" in text
    assert "XFETCH_REPO_NAME=link-vault" in text



def test_write_env_file_creates_parent_and_sets_0600_permissions(tmp_path):
    cfg = SetupConfig(
        telegram_bot_token="123:abc",
        target_repo=tmp_path / "target",
        repo_owner="guchengwei",
        repo_name="link-vault",
        content_root=tmp_path / "content-out",
    )
    env_path = tmp_path / ".config" / "xfetch" / "telegram-bot.env"
    write_env_file(env_path, cfg)
    assert env_path.exists()
    mode = stat.S_IMODE(env_path.stat().st_mode)
    assert mode == 0o600



def test_service_defaults_for_macos_use_launchd():
    defaults = service_defaults_for_platform("darwin")
    assert defaults.service_manager == "launchd"
    assert defaults.target_repo.name == "link-vault-publish"



def test_service_defaults_for_linux_use_systemd(tmp_path=None):
    defaults = service_defaults_for_platform("linux")
    assert defaults.service_manager == "systemd"
    assert defaults.repo_name == "link-vault"
