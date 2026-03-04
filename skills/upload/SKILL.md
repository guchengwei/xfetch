---
name: upload
description: "Use when user wants to archive/upload x-reader inbox items to GitHub. Runs scripts/upload_archive.py to push unprocessed inbox items to guchengwei/openclaw-content-archive repo and marks them as processed."
---

# x-reader Archive Upload Skill

> Upload unprocessed x-reader inbox items to `guchengwei/openclaw-content-archive` on GitHub.

## When to Use

- After reading content via `read_url` and it lands in the local inbox
- User says "archive this", "upload to archive", "save to openclaw"
- Periodic batch archiving of accumulated inbox items

## Pipeline

### Step 1: Dry Run (always first)

```bash
cd ~/projects/x-reader
python scripts/upload_archive.py --dry-run
```

This shows what would be uploaded without writing anything. Review the output:
- Confirms which items are unprocessed
- Shows the archive paths that would be created
- Detects duplicates (items already in index are skipped)

### Step 2: Upload

If dry run looks good:

```bash
cd ~/projects/x-reader
python scripts/upload_archive.py
```

Optional flags:
```bash
python scripts/upload_archive.py --limit 10   # cap batch size
python scripts/upload_archive.py --force       # re-upload even if SHA already in index
```

### Step 3: Verify

The script automatically:
1. Pushes all new items as a single atomic commit to the archive repo
2. Updates `.index.json` in the archive repo (content SHA dedup index)
3. Marks uploaded items as `"processed": true` in the local inbox JSON

Check the output for the commit SHA and file count.

## What the Script Does

- **Source**: Reads from `~/Library/Application Support/x-reader/unified_inbox.json`
- **Target repo**: `guchengwei/openclaw-content-archive`, branch `main`
- **Archive path**: `archive/web-scrapes/YYYY/MM/YYYYMMDD-HHMMSS--<kind>--<lang>--<slug>.md`
- **Dedup**: Uses content SHA256 to skip already-archived items (via `.index.json`)
- **Atomic commit**: All files + index update go in one commit via GitHub Git Data API

## Source Type → Archive Kind Mapping

| Source Type | Archive Kind |
|-------------|-------------|
| `manual` | `web` |
| `twitter` | `web-x` |
| `youtube` | `web-youtube` |
| `bilibili` | `web-bili` |
| `xhs` | `web-xhs` |
| `wechat` | `web-wechat` |
| `rss` | `web-rss` |
| `telegram` | `web-tg` |

## Requirements

- `gh` CLI authenticated (`gh auth status`)
- Local inbox file exists at the configured `INBOX_FILE` path
- x-reader `.env` loaded (the script loads it automatically from `~/projects/x-reader/.env`)

## Archive Repo

- **Repo**: `guchengwei/openclaw-content-archive`
- **Branch**: `main`
- **Index**: `.index.json` at repo root (SHA → archive path mapping)
