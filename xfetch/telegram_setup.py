from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shlex
import stat
import subprocess


SERVICE_LABEL = "com.zion.xfetch-telegram-bot"
SYSTEMD_UNIT_NAME = "xfetch-telegram-bot.service"


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


@dataclass(slots=True)
class ServiceInstallPlan:
    service_manager: str
    unit_path: Path
    repo_dir: Path
    service_script: Path
    log_dir: Path
    start_commands: list[str]


@dataclass(slots=True)
class SetupPaths:
    home: Path
    repo_dir: Path
    env_file: Path
    python_executable: Path



def service_defaults_for_platform(system_name: str | None = None, home: Path | None = None) -> ServiceDefaults:
    name = (system_name or platform.system()).lower()
    home_dir = (home or Path.home()).expanduser()
    repo_root = home_dir / "x-tweet-fetcher"
    return ServiceDefaults(
        service_manager="launchd" if name == "darwin" else "systemd",
        target_repo=home_dir / "link-vault-publish",
        repo_owner="guchengwei",
        repo_name="link-vault",
        content_root=repo_root / "content-out",
    )



def build_setup_paths(home: Path | None = None, repo_dir: Path | None = None, python_executable: Path | None = None) -> SetupPaths:
    home_dir = (home or Path.home()).expanduser()
    repo_root = (repo_dir or (home_dir / "x-tweet-fetcher")).expanduser()
    python_path = (python_executable or Path(sys_executable())).expanduser().resolve()
    env_file = home_dir / ".config" / "xfetch" / "telegram-bot.env"
    return SetupPaths(home=home_dir, repo_dir=repo_root, env_file=env_file, python_executable=python_path)



def sys_executable() -> str:
    return os.environ.get("PYTHON_EXECUTABLE") or os.sys.executable



def service_install_plan_for_platform(system_name: str | None = None, home: Path | None = None, repo_dir: Path | None = None) -> ServiceInstallPlan:
    name = (system_name or platform.system()).lower()
    paths = build_setup_paths(home=home, repo_dir=repo_dir)
    log_dir = paths.home / ".local" / "state" / "xfetch"
    service_script = paths.repo_dir / "scripts" / "telegram-bot-service.sh"

    if name == "darwin":
        unit_path = paths.home / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
        start_commands = [
            f"launchctl unload {shlex.quote(str(unit_path))} 2>/dev/null || true",
            f"launchctl load {shlex.quote(str(unit_path))}",
            f"launchctl kickstart -k gui/$(id -u)/{SERVICE_LABEL}",
        ]
        return ServiceInstallPlan("launchd", unit_path, paths.repo_dir, service_script, log_dir, start_commands)

    unit_path = paths.home / ".config" / "systemd" / "user" / SYSTEMD_UNIT_NAME
    start_commands = [
        "systemctl --user daemon-reload",
        f"systemctl --user enable --now {SYSTEMD_UNIT_NAME}",
    ]
    return ServiceInstallPlan("systemd", unit_path, paths.repo_dir, service_script, log_dir, start_commands)



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



def render_service_script(plan: ServiceInstallPlan, python_executable: Path, env_file: Path) -> str:
    py = shlex.quote(str(python_executable))
    repo = shlex.quote(str(plan.repo_dir))
    env = shlex.quote(str(env_file))
    log_dir = shlex.quote(str(plan.log_dir))
    return f'''#!/bin/bash
set -euo pipefail

REPO_DIR={repo}
ENV_FILE={env}
LOG_DIR={log_dir}
mkdir -p "$LOG_DIR"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

: "${{TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required in $ENV_FILE}}"
: "${{XFETCH_TARGET_REPO:?XFETCH_TARGET_REPO is required in $ENV_FILE}}"
: "${{XFETCH_REPO_OWNER:?XFETCH_REPO_OWNER is required in $ENV_FILE}}"
: "${{XFETCH_REPO_NAME:?XFETCH_REPO_NAME is required in $ENV_FILE}}"
: "${{XFETCH_CONTENT_ROOT:?XFETCH_CONTENT_ROOT is required in $ENV_FILE}}"
: "${{XFETCH_BRANCH:=main}}"
: "${{XFETCH_CONTENT_SUBDIR:=content}}"
: "${{XFETCH_SITE_SUBDIR:=site}}"

cd "$REPO_DIR"
exec {py} -m xfetch telegram-bot \
  --token "$TELEGRAM_BOT_TOKEN" \
  --content-root "$XFETCH_CONTENT_ROOT" \
  --target-repo "$XFETCH_TARGET_REPO" \
  --repo-owner "$XFETCH_REPO_OWNER" \
  --repo-name "$XFETCH_REPO_NAME" \
  --branch "$XFETCH_BRANCH" \
  --content-subdir "$XFETCH_CONTENT_SUBDIR" \
  --site-subdir "$XFETCH_SITE_SUBDIR" \
  >> "$LOG_DIR/telegram-bot.stdout.log" \
  2>> "$LOG_DIR/telegram-bot.stderr.log"
'''



def render_launchd_plist(plan: ServiceInstallPlan) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>{SERVICE_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
      <string>/bin/bash</string>
      <string>{plan.service_script}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>{plan.repo_dir}</string>
    <key>StandardOutPath</key>
    <string>{plan.log_dir / 'launchd.stdout.log'}</string>
    <key>StandardErrorPath</key>
    <string>{plan.log_dir / 'launchd.stderr.log'}</string>
  </dict>
</plist>
'''



def render_systemd_unit(plan: ServiceInstallPlan) -> str:
    return f'''[Unit]
Description=xfetch Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={plan.repo_dir}
ExecStart={plan.service_script}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
'''



def install_service_files(plan: ServiceInstallPlan, python_executable: Path, env_file: Path) -> ServiceInstallPlan:
    plan.log_dir.mkdir(parents=True, exist_ok=True)
    plan.service_script.parent.mkdir(parents=True, exist_ok=True)
    plan.service_script.write_text(render_service_script(plan, python_executable, env_file), encoding="utf-8")
    os.chmod(plan.service_script, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    plan.unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_text = render_launchd_plist(plan) if plan.service_manager == "launchd" else render_systemd_unit(plan)
    plan.unit_path.write_text(unit_text, encoding="utf-8")
    return plan



def run_service_start_commands(plan: ServiceInstallPlan) -> None:
    for command in plan.start_commands:
        subprocess.run(command, shell=True, check=True)



def prompt_with_default(label: str, default: str) -> str:
    value = input(f"{label} [{default}]: ").strip()
    return value or default



def run_interactive_setup() -> int:
    paths = build_setup_paths()
    defaults = service_defaults_for_platform(home=paths.home)
    plan = service_install_plan_for_platform(home=paths.home, repo_dir=paths.repo_dir)

    print("xfetch Telegram bot setup")
    print()
    print("This will write a local env file, install a user service, and start it.")
    print(f"Service manager: {plan.service_manager}")
    print(f"Env file: {paths.env_file}")
    print(f"Service file: {plan.unit_path}")
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
    write_env_file(paths.env_file, config)
    install_service_files(plan, python_executable=paths.python_executable, env_file=paths.env_file)

    print()
    print(f"Saved env file: {paths.env_file}")
    print(f"Installed service file: {plan.unit_path}")
    print("Starting service...")
    run_service_start_commands(plan)
    print("Service started.")
    return 0
