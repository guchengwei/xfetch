#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload unprocessed x-reader inbox items to the openclaw-content-archive repo.

Usage:
    python scripts/upload_archive.py            # upload all unprocessed
    python scripts/upload_archive.py --dry-run  # show what would upload
    python scripts/upload_archive.py --limit 5  # cap batch size
    python scripts/upload_archive.py --force     # re-upload even if SHA in index
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────

def load_dotenv(path: Path) -> dict:
    env = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, val = line.partition('=')
                env[key.strip()] = val.strip()
    except FileNotFoundError:
        pass
    return env


SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
env = load_dotenv(PROJECT_DIR / '.env')

INBOX_FILE = env.get('INBOX_FILE', str(PROJECT_DIR / 'unified_inbox.json'))
ARCHIVE_REPO = env.get('ARCHIVE_REPO', 'guchengwei/openclaw-content-archive')
ARCHIVE_BRANCH = env.get('ARCHIVE_BRANCH', 'main')


# ── Source type → archive kind ───────────────────────────────────────────────

KIND_MAP = {
    'manual':   'web',
    'twitter':  'web-x',
    'youtube':  'web-youtube',
    'bilibili': 'web-bili',
    'xhs':      'web-xhs',
    'wechat':   'web-wechat',
    'rss':      'web-rss',
    'telegram': 'web-tg',
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def slugify(title: str, max_len: int = 60) -> str:
    """
    Lowercase slug. Chinese/CJK characters kept as-is.
    Spaces → hyphens; strip most punctuation.
    """
    title = unicodedata.normalize('NFKC', title)
    title = title.lower()
    title = re.sub(r'[\s_/\\]+', '-', title)
    # Keep word chars, CJK ranges, and hyphens
    title = re.sub(
        r'[^\w\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff-]',
        '',
        title,
    )
    title = re.sub(r'-+', '-', title).strip('-')
    return title[:max_len]


def parse_timestamp(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return datetime.now()


def make_filename(item: dict, kind: str) -> str:
    dt = parse_timestamp(item.get('fetched_at', ''))
    ts_str = dt.strftime('%Y%m%d-%H%M%S')
    extra = item.get('extra') or {}
    lang = extra.get('language') or extra.get('lang') or 'unknown'
    title = item.get('title') or 'untitled'
    slug = slugify(title) or 'untitled'
    return f"{ts_str}--{kind}--{lang}--{slug}.md"


def make_archive_path(item: dict, filename: str) -> str:
    dt = parse_timestamp(item.get('fetched_at', ''))
    return f"archive/web-scrapes/{dt.strftime('%Y')}/{dt.strftime('%m')}/{filename}"


def make_markdown(item: dict, kind: str, content_sha: str) -> str:
    title = item.get('title') or 'Untitled'
    source_name = item.get('source_name') or ''
    url = item.get('url') or ''
    fetched_at = item.get('fetched_at') or ''
    item_id = item.get('id') or ''
    content = item.get('content') or ''
    extra = item.get('extra') or {}

    lines = [
        f"# Archive: {title}",
        "",
        "## Metadata",
        f"- kind: `{kind}`",
        f"- source_name: `{source_name}`",
        f"- source_url: `{url}`",
        f"- fetched_at: `{fetched_at}`",
        f"- content_sha256: `{content_sha}`",
        f"- x_reader_id: `{item_id}`",
    ]

    extra_fields = {
        'author':     extra.get('author'),
        'likes':      extra.get('likes'),
        'retweets':   extra.get('retweets'),
        'view_count': extra.get('view_count'),
        'bvid':       extra.get('bvid'),
    }
    present = {k: v for k, v in extra_fields.items() if v is not None}
    if present:
        lines += ["", "## Extra"]
        for k, v in present.items():
            lines.append(f"- {k}: {v}")

    lines += ["", "## Content", "", content]
    return "\n".join(lines)


# ── GitHub Git Data API ───────────────────────────────────────────────────────

def gh_api(method: str, path: str, body: dict = None) -> dict:
    cmd = ['gh', 'api', '--method', method, path]
    if body:
        cmd += ['--input', '-']
    result = subprocess.run(
        cmd,
        input=json.dumps(body).encode('utf-8') if body else None,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api {method} {path} failed:\n{result.stderr.decode()}")
    return json.loads(result.stdout)


def create_blob(repo: str, content: str) -> str:
    encoded = base64.b64encode(content.encode('utf-8')).decode('ascii')
    resp = gh_api('POST', f'/repos/{repo}/git/blobs', {
        'content': encoded,
        'encoding': 'base64',
    })
    return resp['sha']


def get_head_commit(repo: str, branch: str) -> tuple:
    """Returns (commit_sha, tree_sha)."""
    ref = gh_api('GET', f'/repos/{repo}/git/refs/heads/{branch}')
    commit_sha = ref['object']['sha']
    commit = gh_api('GET', f'/repos/{repo}/git/commits/{commit_sha}')
    return commit_sha, commit['tree']['sha']


def create_tree(repo: str, base_tree: str, blobs: list) -> str:
    tree_items = [
        {'path': b['path'], 'mode': '100644', 'type': 'blob', 'sha': b['sha']}
        for b in blobs
    ]
    resp = gh_api('POST', f'/repos/{repo}/git/trees', {
        'base_tree': base_tree,
        'tree': tree_items,
    })
    return resp['sha']


def create_commit(repo: str, message: str, tree_sha: str, parent_sha: str) -> str:
    resp = gh_api('POST', f'/repos/{repo}/git/commits', {
        'message': message,
        'tree': tree_sha,
        'parents': [parent_sha],
    })
    return resp['sha']


def update_ref(repo: str, branch: str, commit_sha: str):
    gh_api('PATCH', f'/repos/{repo}/git/refs/heads/{branch}', {'sha': commit_sha})


def load_index(repo: str) -> dict:
    try:
        resp = gh_api('GET', f'/repos/{repo}/contents/.index.json')
        raw = base64.b64decode(resp['content']).decode('utf-8')
        return json.loads(raw)
    except Exception as e:
        print(f"Warning: could not load .index.json ({e}), starting fresh")
        return {}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Upload x-reader inbox to openclaw archive')
    parser.add_argument('--dry-run', action='store_true', help='Show what would upload, no writes')
    parser.add_argument('--limit', type=int, default=None, help='Max items per run')
    parser.add_argument('--force', action='store_true', help='Re-upload even if SHA already in index')
    args = parser.parse_args()

    # Load inbox
    inbox_path = Path(INBOX_FILE)
    if not inbox_path.exists():
        print(f"Inbox not found: {inbox_path}")
        sys.exit(1)

    with open(inbox_path, encoding='utf-8') as f:
        inbox: list = json.load(f)

    unprocessed = [item for item in inbox if not item.get('processed')]
    print(f"Inbox: {len(inbox)} total, {len(unprocessed)} unprocessed")

    if not unprocessed:
        print("Nothing to upload.")
        return

    # Load existing dedup index
    print(f"Loading index from {ARCHIVE_REPO}...")
    index = load_index(ARCHIVE_REPO)
    existing_shas = set(index.keys())

    # Determine candidates
    to_upload = []
    for item in unprocessed:
        content_sha = sha256(item.get('content') or '')
        if content_sha in existing_shas and not args.force:
            print(f"  SKIP (dup): {item.get('title', '')[:70]}")
            continue
        to_upload.append((item, content_sha))

    if args.limit:
        to_upload = to_upload[:args.limit]

    if not to_upload:
        print("No new items to upload.")
        return

    print(f"\nPreparing {len(to_upload)} item(s):")

    file_entries = []
    for item, content_sha in to_upload:
        source_type = item.get('source_type') or 'manual'
        kind = KIND_MAP.get(source_type, 'web')
        filename = make_filename(item, kind)
        archive_path = make_archive_path(item, filename)
        md_content = make_markdown(item, kind, content_sha)
        file_entries.append({
            'path': archive_path,
            'content': md_content,
            'item': item,
            'content_sha': content_sha,
        })
        print(f"  + {archive_path}")

    if args.dry_run:
        print("\nDry run complete — no files written.")
        return

    # Build updated index
    new_index = dict(index)
    for entry in file_entries:
        new_index[entry['content_sha']] = entry['path']

    # Git Data API: atomic commit
    print(f"\nFetching HEAD of {ARCHIVE_REPO}/{ARCHIVE_BRANCH}...")
    parent_sha, base_tree = get_head_commit(ARCHIVE_REPO, ARCHIVE_BRANCH)

    print("Creating blobs...")
    blobs = []
    for entry in file_entries:
        blob_sha = create_blob(ARCHIVE_REPO, entry['content'])
        blobs.append({'path': entry['path'], 'sha': blob_sha})
        print(f"  blob {blob_sha[:8]}  {entry['path']}")

    index_blob_sha = create_blob(ARCHIVE_REPO, json.dumps(new_index, indent=2, ensure_ascii=False))
    blobs.append({'path': '.index.json', 'sha': index_blob_sha})
    print(f"  blob {index_blob_sha[:8]}  .index.json")

    print("Creating tree...")
    new_tree = create_tree(ARCHIVE_REPO, base_tree, blobs)

    n = len(file_entries)
    commit_msg = f"archive: add {n} x-reader item{'s' if n != 1 else ''}\n\nUploaded via upload_archive.py"
    print("Creating commit...")
    new_commit = create_commit(ARCHIVE_REPO, commit_msg, new_tree, parent_sha)

    print("Advancing ref...")
    update_ref(ARCHIVE_REPO, ARCHIVE_BRANCH, new_commit)

    print(f"\nDone. Commit: {new_commit}")
    print(f"Pushed {n} file(s) to {ARCHIVE_REPO}")

    # Mark uploaded items as processed locally
    uploaded_ids = {entry['item']['id'] for entry in file_entries}
    for item in inbox:
        if item.get('id') in uploaded_ids:
            item['processed'] = True

    with open(inbox_path, 'w', encoding='utf-8') as f:
        json.dump(inbox, f, ensure_ascii=False, indent=2)

    print(f"Marked {n} item(s) as processed in {inbox_path}")


if __name__ == '__main__':
    main()
