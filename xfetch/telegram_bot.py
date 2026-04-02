from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Final

from xfetch.config import PublishTargetConfig, load_config
from xfetch.connectors.x import XConnector
from xfetch.pipeline.bundle import write_bundle
from xfetch.publishing.git_publish import publish_repo
from xfetch.publishing.github_repo_sync import sync_bundle_to_repo
from xfetch.publishing.url import build_pages_url
from xfetch.storage.render import render_bundle_page


@dataclass(slots=True)
class SaveResult:
    bundle_dir: Path
    public_url: str | None
    revision: str | None
    published: bool


@dataclass(slots=True)
class TelegramBotRuntimeConfig:
    token: str
    content_root: Path | None = None
    target_repo: Path | None = None
    repo_owner: str | None = None
    repo_name: str | None = None
    branch: str = "main"
    content_subdir: str = "content"
    site_subdir: str = "site"


PRIMARY_TELEGRAM_COMMAND: Final[str] = "link"
LEGACY_TELEGRAM_COMMANDS: Final[tuple[str, ...]] = ("save",)
TELEGRAM_COMMANDS: Final[tuple[str, ...]] = (PRIMARY_TELEGRAM_COMMAND, *LEGACY_TELEGRAM_COMMANDS)


def parse_save_command(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    command = parts[0].split("@")[0].lstrip("/").lower()
    if command not in TELEGRAM_COMMANDS:
        return None
    url = parts[1].strip()
    return url or None


def parse_plaintext_save(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    if parts[0].lower() not in TELEGRAM_COMMANDS:
        return None
    url = parts[1].strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    return url


def _load_publish_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))



def _write_publish_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")



def _mark_publish_metadata(bundle_dir: Path, target_bundle_dir: Path, public_url: str, revision: str | None, published: bool) -> None:
    for publish_path in (bundle_dir / "publish.json", target_bundle_dir / "publish.json"):
        payload = _load_publish_json(publish_path)
        payload["published"] = published
        payload["public_url"] = public_url
        if revision is not None:
            payload["revision"] = revision
        _write_publish_json(publish_path, payload)



def save_url(
    url: str,
    *,
    content_root: str | Path | None = None,
    target_repo: str | Path | None = None,
    repo_owner: str | None = None,
    repo_name: str | None = None,
    branch: str = "main",
    content_subdir: str = "content",
    site_subdir: str = "site",
) -> SaveResult:
    connector = XConnector()
    if not connector.can_handle(url):
        raise ValueError(f"unsupported URL: {url}")

    config = load_config(content_root=content_root)
    doc = connector.fetch(url)
    bundle_dir = write_bundle(doc, config)

    if not (target_repo and repo_owner and repo_name):
        return SaveResult(bundle_dir=bundle_dir, public_url=None, revision=None, published=False)

    publish_target = PublishTargetConfig(
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch=branch,
        content_subdir=content_subdir,
        site_subdir=site_subdir,
    )
    public_url = build_pages_url(publish_target, slug=bundle_dir.name)
    rendered_page = render_bundle_page(bundle_dir, config.site_root, public_url=public_url)
    result = sync_bundle_to_repo(
        bundle_dir=bundle_dir,
        target_repo=Path(target_repo),
        rendered_page=rendered_page,
        publish_target=publish_target,
        target_subdir=publish_target.content_subdir,
    )
    _mark_publish_metadata(bundle_dir, result.bundle_destination_dir, public_url, revision=None, published=True)
    revision = publish_repo(Path(target_repo), branch=publish_target.branch, commit_message=f"publish: {bundle_dir.name}")
    payload = _load_publish_json(bundle_dir / "publish.json")
    payload["revision"] = revision
    _write_publish_json(bundle_dir / "publish.json", payload)
    return SaveResult(bundle_dir=bundle_dir, public_url=public_url, revision=revision, published=True)



def build_save_reply(result: SaveResult) -> str:
    if result.published:
        return "\n".join(
            [
                "Published.",
                f"URL: {result.public_url}",
                f"Revision: {result.revision}",
                f"Bundle: {result.bundle_dir}",
            ]
        )
    return "\n".join(["Saved locally.", f"Bundle: {result.bundle_dir}"])


async def _start(update, context) -> None:
    await update.message.reply_text(f"Send /{PRIMARY_TELEGRAM_COMMAND} <x-url> to fetch and archive a post.")


async def _save(update, context) -> None:
    message_text = update.message.text if update.message else ""
    url = parse_save_command(message_text)
    if not url:
        await update.message.reply_text(f"Usage: /{PRIMARY_TELEGRAM_COMMAND} <x-url>")
        return

    runtime: TelegramBotRuntimeConfig = context.application.bot_data["xfetch_runtime"]
    try:
        result = save_url(
            url,
            content_root=runtime.content_root,
            target_repo=runtime.target_repo,
            repo_owner=runtime.repo_owner,
            repo_name=runtime.repo_name,
            branch=runtime.branch,
            content_subdir=runtime.content_subdir,
            site_subdir=runtime.site_subdir,
        )
    except Exception as exc:
        await update.message.reply_text(f"Save failed: {exc}")
        return

    await update.message.reply_text(build_save_reply(result))


async def _fallback_text(update, context) -> None:
    text = (update.message.text or "").strip() if update.message else ""
    url = parse_plaintext_save(text) or text
    if url.startswith("http://") or url.startswith("https://"):
        runtime: TelegramBotRuntimeConfig = context.application.bot_data["xfetch_runtime"]
        try:
            result = save_url(
                url,
                content_root=runtime.content_root,
                target_repo=runtime.target_repo,
                repo_owner=runtime.repo_owner,
                repo_name=runtime.repo_name,
                branch=runtime.branch,
                content_subdir=runtime.content_subdir,
                site_subdir=runtime.site_subdir,
            )
        except Exception as exc:
            await update.message.reply_text(f"Save failed: {exc}")
            return
        await update.message.reply_text(build_save_reply(result))
        return

    await update.message.reply_text("Send save <x-url> or just paste a supported URL.")



def run_telegram_bot(runtime: TelegramBotRuntimeConfig) -> int:
    try:
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
    except ImportError as exc:
        raise ImportError("Install Telegram bot support with: pip install -e .[telegram-bot]") from exc

    application = Application.builder().token(runtime.token).build()
    application.bot_data["xfetch_runtime"] = runtime
    application.add_handler(CommandHandler("start", _start))
    application.add_handler(CommandHandler(PRIMARY_TELEGRAM_COMMAND, _save))
    for legacy_command in LEGACY_TELEGRAM_COMMANDS:
        application.add_handler(CommandHandler(legacy_command, _save))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _fallback_text))
    application.run_polling()
    return 0
