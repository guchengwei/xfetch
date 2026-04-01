#!/bin/bash
set -euo pipefail

REPO_DIR="/Users/zion/x-tweet-fetcher"
ENV_FILE="/Users/zion/.config/xfetch/telegram-bot.env"
LOG_DIR="/Users/zion/.local/state/xfetch"
mkdir -p "$LOG_DIR"

if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
fi

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required in $ENV_FILE}"
: "${XFETCH_TARGET_REPO:=/Users/zion/link-vault-publish}"
: "${XFETCH_REPO_OWNER:=guchengwei}"
: "${XFETCH_REPO_NAME:=link-vault}"
: "${XFETCH_CONTENT_ROOT:=/Users/zion/x-tweet-fetcher/content-out}"
: "${XFETCH_BRANCH:=main}"
: "${XFETCH_CONTENT_SUBDIR:=content}"
: "${XFETCH_SITE_SUBDIR:=site}"

cd "$REPO_DIR"
exec /Users/zion/miniconda3/bin/python -m xfetch telegram-bot \
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
