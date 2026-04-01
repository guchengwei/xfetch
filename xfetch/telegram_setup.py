from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import stat


@dataclass(slots=True)
class SetupConfig:
    telegram_bot_token: str
    target_repo: Path
    repo_owner: str
    repo_name: str
    content_root: Path
    branch: str = "main"
    content_subdir: str = "content"
    site_subdir: str = "site"


@dataclass(slots=True)
class ServiceDefaults:
    service_manager: str
    target_repo: Path
    repo_owner: str
    repo_name: str
    content_root: Path


def service_defaults_for_platform(system_name: str | None = None) -> ServiceDefaults:
    name = (system_name or platform.system()).lower()
    home = Path.home()
    repo_root = home / "x-tweet-fetcher"
    return ServiceDefaults(
        service_manager="launchd" if name == "darwin" else "systemd",
        target_repo=home / "link-vault-publish",
        repo_owner="guchengwei",
        repo_name="link-vault",
        content_root=repo_root / "content-out",
    )


def render_env_file(config: SetupConfig) -> str:
    lines = [
        f"TELEGRAM_BOT_TOKEN={config.telegram_bot_token}",
        f"XFETCH_TARGET_REPO={config.target_repo}",
        f"XFETCH_REPO_OWNER={config.repo_owner}",
        f"XFETCH_REPO_NAME={config.repo_name}",
        f"XFETCH_CONTENT_ROOT={config.content_root}",
        f"XFETCH_BRANCH={config.branch}",
        f"XFETCH_CONTENT_SUBDIR={config.content_subdir}",
        f"XFETCH_SITE_SUBDIR={config.site_subdir}",
    ]
    return "\n".join(lines) + "\n"


def write_env_file(path: Path, config: SetupConfig) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_env_file(config), encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def prompt_with_default(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default


def run_interactive_setup() -> int:
    defaults = service_defaults_for_platform()
    env_path = Path.home() / ".config" / "xfetch" / "telegram-bot.env"

    print("xfetch Telegram bot setup")
    print()
    print("This writes a local runtime env file for the bot service.")
    print(f"Env file: {env_path}")
    print()

    token = ""
    while not token:
        token = input("Paste Telegram bot token: ").strip()
        if not token:
            print("Token is required.")

    target_repo = Path(prompt_with_default("Target repo working tree", str(defaults.target_repo))).expanduser().resolve()
    repo_owner = prompt_with_default("GitHub repo owner", defaults.repo_owner)
    repo_name = prompt_with_default("GitHub repo name", defaults.repo_name)
    content_root = Path(prompt_with_default("Local content root", str(defaults.content_root))).expanduser().resolve()
    branch = prompt_with_default("Publish branch", "main")
    content_subdir = prompt_with_default("Content subdir", "content")
    site_subdir = prompt_with_default("Site subdir", "site")

    config = SetupConfig(
        telegram_bot_token=token,
        target_repo=target_repo,
        repo_owner=repo_owner,
        repo_name=repo_name,
        content_root=content_root,
        branch=branch,
        content_subdir=content_subdir,
        site_subdir=site_subdir,
    )
    write_env_file(env_path, config)

    print()
    print(f"Saved env file: {env_path}")
    print(f"Service manager hint: {defaults.service_manager}")
    print("Next steps:")
    if defaults.service_manager == "launchd":
        print("  launchctl unload ~/Library/LaunchAgents/com.zion.xfetch-telegram-bot.plist 2>/dev/null || true")
        print("  launchctl load ~/Library/LaunchAgents/com.zion.xfetch-telegram-bot.plist")
        print("  launchctl kickstart -k gui/$(id -u)/com.zion.xfetch-telegram-bot")
    else:
        print("  Start the bot with your service manager or run the command manually.")
    return 0
