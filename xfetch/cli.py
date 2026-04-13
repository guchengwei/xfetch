from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import PublishTargetConfig, load_config
from .connectors.registry import pick_connector as pick_registered_connector
from .pipeline.bundle import write_bundle
from .publishing.git_publish import publish_repo
from .publishing.github_repo_sync import sync_bundle_to_repo
from .publishing.url import build_pages_url
from .storage.render import render_bundle_page


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

    save = subparsers.add_parser("save")
    save.add_argument("url")
    save.add_argument("--content-root")
    save.add_argument("--target-repo")
    save.add_argument("--repo-owner")
    save.add_argument("--repo-name")
    save.add_argument("--branch", default="main")
    save.add_argument("--content-subdir", default="content")
    save.add_argument("--site-subdir", default="site")
    save.add_argument("--json", action="store_true")

    return parser


def pick_connector(url: str):
    return pick_registered_connector(url)


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


def _resolve_optional_publish_target(args) -> tuple[Path | None, PublishTargetConfig | None]:
    target_repo = getattr(args, "target_repo", None) or os.environ.get("XFETCH_TARGET_REPO")
    repo_owner = getattr(args, "repo_owner", None) or os.environ.get("XFETCH_REPO_OWNER")
    repo_name = getattr(args, "repo_name", None) or os.environ.get("XFETCH_REPO_NAME")
    branch = getattr(args, "branch", None) or os.environ.get("XFETCH_BRANCH") or "main"
    content_subdir = getattr(args, "content_subdir", None) or os.environ.get("XFETCH_CONTENT_SUBDIR") or "content"
    site_subdir = getattr(args, "site_subdir", None) or os.environ.get("XFETCH_SITE_SUBDIR") or "site"

    values = [target_repo, repo_owner, repo_name]
    if not any(values):
        return None, None
    if not all(values):
        raise ValueError("Incomplete publish target configuration. Set target repo, repo owner, and repo name.")
    return Path(target_repo), PublishTargetConfig(
        repo_owner=repo_owner,
        repo_name=repo_name,
        branch=branch,
        content_subdir=content_subdir,
        site_subdir=site_subdir,
    )


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


def run_save(args) -> int:
    config = load_config(content_root=args.content_root)
    connector = pick_connector(args.url)
    if connector is None:
        return 2

    doc = connector.fetch(args.url)
    bundle_dir = write_bundle(doc, config)
    result = {
        "ok": True,
        "url": doc.canonical_url or doc.source_url,
        "title": doc.title,
        "source_type": doc.source_type,
        "bundle_dir": str(bundle_dir),
        "published": False,
        "publish_status": "not_configured",
        "public_url": None,
        "revision": None,
    }

    try:
        target_repo, publish_target = _resolve_optional_publish_target(args)
    except ValueError as exc:
        print(str(exc))
        return 2

    if target_repo and publish_target:
        if not (target_repo / ".git").exists():
            return 4
        sync_result, public_url = _render_and_sync(bundle_dir, target_repo, publish_target)
        _mark_publish_metadata(bundle_dir, sync_result.bundle_destination_dir, public_url, revision=None, published=True)
        revision = publish_repo(target_repo=target_repo, branch=publish_target.branch, commit_message=f"publish: {bundle_dir.name}")
        source_publish = _load_publish_json(bundle_dir / "publish.json")
        source_publish["revision"] = revision
        _write_publish_json(bundle_dir / "publish.json", source_publish)
        result.update(
            published=True,
            publish_status="published",
            public_url=public_url,
            revision=revision,
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        if result["published"]:
            print(result["public_url"])
        else:
            print(result["bundle_dir"])
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        return run_ingest(args)
    if args.command == "sync":
        return run_sync(args)
    if args.command == "publish":
        return run_publish(args)
    if args.command == "save":
        return run_save(args)
    return 0