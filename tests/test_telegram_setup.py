from pathlib import Path
import stat

from xfetch.cli import build_parser
from xfetch.telegram_setup import (
    SetupConfig,
    ServiceInstallPlan,
    install_service_files,
    render_env_file,
    render_launchd_plist,
    render_systemd_unit,
    service_defaults_for_platform,
    service_install_plan_for_platform,
    write_env_file,
)



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
    defaults = service_defaults_for_platform("darwin", home=Path("/Users/zion"))
    assert defaults.service_manager == "launchd"
    assert defaults.target_repo == Path("/Users/zion/link-vault-publish")



def test_service_defaults_for_linux_use_systemd():
    defaults = service_defaults_for_platform("linux", home=Path("/home/zion"))
    assert defaults.service_manager == "systemd"
    assert defaults.content_root == Path("/home/zion/x-tweet-fetcher/content-out")



def test_service_install_plan_for_launchd_has_launchagent_path():
    plan = service_install_plan_for_platform("darwin", home=Path("/Users/zion"), repo_dir=Path("/Users/zion/x-tweet-fetcher"))
    assert plan.service_manager == "launchd"
    assert plan.unit_path == Path("/Users/zion/Library/LaunchAgents/com.zion.xfetch-telegram-bot.plist")
    assert plan.start_commands[-1].startswith("launchctl kickstart")



def test_service_install_plan_for_systemd_has_user_unit_path():
    plan = service_install_plan_for_platform("linux", home=Path("/home/zion"), repo_dir=Path("/home/zion/x-tweet-fetcher"))
    assert plan.service_manager == "systemd"
    assert plan.unit_path == Path("/home/zion/.config/systemd/user/xfetch-telegram-bot.service")
    assert "systemctl --user enable --now xfetch-telegram-bot.service" in plan.start_commands



def test_render_launchd_plist_contains_service_script_path():
    plan = ServiceInstallPlan(
        service_manager="launchd",
        unit_path=Path("/Users/zion/Library/LaunchAgents/com.zion.xfetch-telegram-bot.plist"),
        repo_dir=Path("/Users/zion/x-tweet-fetcher"),
        service_script=Path("/Users/zion/x-tweet-fetcher/scripts/telegram-bot-service.sh"),
        log_dir=Path("/Users/zion/.local/state/xfetch"),
        start_commands=[],
    )
    text = render_launchd_plist(plan)
    assert "/Users/zion/x-tweet-fetcher/scripts/telegram-bot-service.sh" in text
    assert "com.zion.xfetch-telegram-bot" in text



def test_render_systemd_unit_contains_execstart():
    plan = ServiceInstallPlan(
        service_manager="systemd",
        unit_path=Path("/home/zion/.config/systemd/user/xfetch-telegram-bot.service"),
        repo_dir=Path("/home/zion/x-tweet-fetcher"),
        service_script=Path("/home/zion/x-tweet-fetcher/scripts/telegram-bot-service.sh"),
        log_dir=Path("/home/zion/.local/state/xfetch"),
        start_commands=[],
    )
    text = render_systemd_unit(plan)
    assert "ExecStart=/home/zion/x-tweet-fetcher/scripts/telegram-bot-service.sh" in text
    assert "WorkingDirectory=/home/zion/x-tweet-fetcher" in text



def test_install_service_files_writes_unit_and_script(tmp_path):
    plan = ServiceInstallPlan(
        service_manager="systemd",
        unit_path=tmp_path / ".config" / "systemd" / "user" / "xfetch-telegram-bot.service",
        repo_dir=tmp_path / "x-tweet-fetcher",
        service_script=tmp_path / "x-tweet-fetcher" / "scripts" / "telegram-bot-service.sh",
        log_dir=tmp_path / ".local" / "state" / "xfetch",
        start_commands=["systemctl --user daemon-reload"],
    )
    install_service_files(plan, python_executable=Path("/usr/bin/python3"), env_file=tmp_path / ".config" / "xfetch" / "telegram-bot.env")
    assert plan.unit_path.exists()
    assert plan.service_script.exists()
    script_text = plan.service_script.read_text(encoding="utf-8")
    assert "telegram-bot.env" in script_text
    assert "/usr/bin/python3 -m xfetch telegram-bot" in script_text
