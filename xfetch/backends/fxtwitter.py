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


def _normalize_entity_map(entity_map: object) -> dict[str, dict]:
    if isinstance(entity_map, dict):
        return {str(key): value for key, value in entity_map.items() if isinstance(value, dict)}
    if isinstance(entity_map, list):
        normalized: dict[str, dict] = {}
        for entry in entity_map:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            value = entry.get("value")
            if key is None or not isinstance(value, dict):
                continue
            normalized[str(key)] = value
        return normalized
    return {}



def _extract_block_text(block: dict, entity_map: dict[str, dict]) -> str:
    text = str(block.get("text") or "")
    normalized_text = " ".join(text.split()).strip()
    entity_ranges = block.get("entityRanges") or []

    markdown_parts: list[str] = []
    for entity_range in entity_ranges:
        if not isinstance(entity_range, dict):
            continue
        entity = entity_map.get(str(entity_range.get("key"))) or {}
        if entity.get("type") != "MARKDOWN":
            continue
        markdown = ((entity.get("data") or {}).get("markdown") or "").strip()
        if markdown:
            markdown_parts.append(markdown)

    parts: list[str] = []
    if normalized_text:
        parts.append(normalized_text)
    parts.extend(markdown_parts)
    return "\n\n".join(parts)



def _extract_article_text(article: dict | None) -> str:
    if not article:
        return ""

    parts: list[str] = []
    title = (article.get("title") or "").strip()
    preview_text = (article.get("preview_text") or "").strip()
    if title:
        parts.append(title)
    if preview_text and preview_text != title:
        parts.append(preview_text)

    content = article.get("content") or {}
    entity_map = _normalize_entity_map(content.get("entityMap"))
    for block in content.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        text = _extract_block_text(block, entity_map)
        if text:
            parts.append(text)

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if part not in seen:
            deduped.append(part)
            seen.add(part)
    return "\n\n".join(deduped)



def parse_fxtwitter_payload(payload: dict) -> dict:
    tweet = payload.get("tweet") or {}
    author = tweet.get("author") or {}
    canonical_url = tweet.get("url") or ""
    tweet_id = str(tweet.get("id") or "")
    raw_text = ((tweet.get("raw_text") or {}).get("text") or "").strip()
    article_text = _extract_article_text(tweet.get("article"))
    text = (tweet.get("text") or "").strip()
    if not text or text == raw_text:
        text = article_text or raw_text or text
    return {
        "tweet_id": tweet_id,
        "canonical_url": canonical_url,
        "screen_name": author.get("screen_name") or "",
        "display_name": author.get("name") or "",
        "text": text,
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
