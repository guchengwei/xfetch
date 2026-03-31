from __future__ import annotations

from datetime import datetime, timezone
import json
from urllib.parse import urlparse
import urllib.request


def build_fxtwitter_url(tweet_url: str) -> str:
    path = urlparse(tweet_url).path.strip("/")
    return f"https://api.fxtwitter.com/{path}"


def fetch_fxtwitter_json(tweet_url: str, timeout: int = 20) -> dict:
    url = build_fxtwitter_url(tweet_url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _normalize_created_at(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


def parse_fxtwitter_payload(payload: dict) -> dict:
    tweet = payload.get("tweet") or {}
    author = tweet.get("author") or {}
    canonical_url = tweet.get("url") or ""
    tweet_id = str(tweet.get("id") or "")
    return {
        "tweet_id": tweet_id,
        "canonical_url": canonical_url,
        "screen_name": author.get("screen_name") or "",
        "display_name": author.get("name") or "",
        "text": tweet.get("text") or "",
        "created_at": _normalize_created_at(tweet.get("created_at")),
        "language": tweet.get("lang") or None,
        "stats": {
            "likes": tweet.get("likes", 0),
            "retweets": tweet.get("retweets", 0),
            "replies": tweet.get("replies", 0),
            "views": tweet.get("views", 0),
        },
        "media": tweet.get("media", {}).get("all", []),
    }
