from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PublishTargetConfig, load_config
from .connectors.x import XConnector
from .pipeline.bundle import write_bundle
from .publishing.git_publish import publish_repo
from .publishing.github_repo_sync import sync_bundle_to_repo
from .publishing.url import build_pages_url
from .storage.render import render_bundle_page
from .telegram_bot import TelegramBotRuntimeConfig, run_telegram_bot
from .telegram_setup import run_interactive_setup


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="xfetch")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("url")
    ingest.add_argument("--content-root")
    ingest.add_argument("--json", action="store_true")

    sync = subparsers.add_parser("sync")
    sync.add_argument("bundle_dir")
    sync.add_argument("--target-repo", required=True)
    sync.add_argument("--repo-owner", required=True)
    sync.add_argument("--repo-name", required=True)
    sync.add_argument("--branch", default="main")
    sync.add_argument("--target-subdir", default="content")
    sync.add_argument("--site-subdir", default="site")
    sync.add_argument("--json", action="store_true")

    publish = subparsers.add_parser("publish")
    publish.add_argument("bundle_dir")
    publish.add_argument("--target-repo", required=True)
    publish.add_argument("--repo-owner", required=True)
    publish.add_argument("--repo-name", required=True)
    publish.add_argument("--branch", default="main")
    publish.add_argument("--content-subdir", default="content")
    publish.add_argument("--site-subdir", default="site")
    publish.add_argument("--json", action="store_true")

    telegram_bot = subparsers.add_parser("telegram-bot")
    telegram_bot.add_argument("--token", required=True)
    telegram_bot.add_argument("--content-root")
    telegram_bot.add_argument("--target-repo")
    telegram_bot.add_argument("--repo-owner")
    telegram_bot.add_argument("--repo-name")
    telegram_bot.add_argument("--branch", default="main")
    telegram_bot.add_argument("--content-subdir", default="content")
    telegram_bot.add_argument("--site-subdir", default="site")

    subparsers.add_parser("setup-telegram-bot")
    return parser


def pick_connector(url: str):
    connector = XConnector()
    if connector.can_handle(url):
        return connector
    return None


def _build_publish_target(args) -> PublishTargetConfig:
    content_subdir = getattr(args, "content_subdir", None) or getattr(args, "target_subdir", "content")
    site_subdir = getattr(args, "site_subdir", "site")
    return PublishTargetConfig(
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        branch=args.branch,
        content_subdir=content_subdir,
        site_subdir=site_subdir,
    )


def _load_publish_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_publish_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_and_sync(bundle_dir: Path, target_repo: Path, publish_target: PublishTargetConfig):
    public_url = build_pages_url(publish_target, slug=bundle_dir.name)
    rendered_page = render_bundle_page(bundle_dir, Path("site-out"), public_url=public_url)
    result = sync_bundle_to_repo(
        bundle_dir=bundle_dir,
        target_repo=target_repo,
        rendered_page=rendered_page,
        publish_target=publish_target,
        target_subdir=publish_target.content_subdir,
    )
    return result, public_url


def _mark_publish_metadata(bundle_dir: Path, target_bundle_dir: Path, public_url: str, revision: str | None, published: bool) -> None:
    for publish_path in (bundle_dir / "publish.json", target_bundle_dir / "publish.json"):
        payload = _load_publish_json(publish_path)
        payload["published"] = published
        payload["public_url"] = public_url
        if revision is not None:
            payload["revision"] = revision
        _write_publish_json(publish_path, payload)


def run_ingest(args) -> int:
    config = load_config(content_root=args.content_root)
    connector = pick_connector(args.url)
    if connector is None:
        return 2

    doc = connector.fetch(args.url)
    bundle_dir = write_bundle(doc, config)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "source_type": doc.source_type,
                    "external_id": doc.external_id,
                    "bundle_dir": str(bundle_dir),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(bundle_dir)
    return 0


def run_sync(args) -> int:
    publish_target = _build_publish_target(args)
    result, _public_url = _render_and_sync(Path(args.bundle_dir), Path(args.target_repo), publish_target)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "destination_dir": str(result.bundle_destination_dir),
                    "target_path": result.target_path,
                    "published": result.published,
                    "public_url": result.public_url,
                    "revision": result.revision,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(result.bundle_destination_dir)
    return 0


def run_publish(args) -> int:
    target_repo = Path(args.target_repo)
    if not (target_repo / ".git").exists():
        return 4

    publish_target = _build_publish_target(args)
    bundle_dir = Path(args.bundle_dir)
    result, public_url = _render_and_sync(bundle_dir, target_repo, publish_target)
    _mark_publish_metadata(bundle_dir, result.bundle_destination_dir, public_url, revision=None, published=True)
    revision = publish_repo(target_repo=target_repo, branch=publish_target.branch, commit_message=f"publish: {bundle_dir.name}")
    source_publish = _load_publish_json(bundle_dir / "publish.json")
    source_publish["revision"] = revision
    _write_publish_json(bundle_dir / "publish.json", source_publish)

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "bundle_dir": str(bundle_dir),
                    "public_url": public_url,
                    "revision": revision,
                    "target_repo": str(target_repo),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(public_url)
    return 0


def run_telegram(args) -> int:
    runtime = TelegramBotRuntimeConfig(
        token=args.token,
        content_root=Path(args.content_root).resolve() if args.content_root else None,
        target_repo=Path(args.target_repo).resolve() if args.target_repo else None,
        repo_owner=args.repo_owner,
        repo_name=args.repo_name,
        branch=args.branch,
        content_subdir=args.content_subdir,
        site_subdir=args.site_subdir,
    )
    return run_telegram_bot(runtime)



def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        return run_ingest(args)
    if args.command == "sync":
        return run_sync(args)
    if args.command == "publish":
        return run_publish(args)
    if args.command == "telegram-bot":
        return run_telegram(args)
    if args.command == "setup-telegram-bot":
        return run_interactive_setup()
    return 0
