from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import json
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from xfetch.article_html import ArticleHTMLParser, markdown_contains_image
from xfetch.net import safe_urlopen


def build_fxtwitter_url(tweet_url: str) -> str:
    path = urlparse(tweet_url).path.strip("/")
    return f"https://api.fxtwitter.com/{path}"


def fetch_fxtwitter_json(tweet_url: str, timeout: int = 20) -> dict:
    req = Request(build_fxtwitter_url(tweet_url), headers={"User-Agent": "Mozilla/5.0"})
    with safe_urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_oembed_json(tweet_url: str, timeout: int = 10) -> dict:
    endpoint = "https://publish.twitter.com/oembed?" + urlencode({"url": tweet_url, "omit_script": "true"})
    req = Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
    with safe_urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def parse_oembed_payload(payload: dict, source_url: str) -> dict:
    fragment = str(payload.get("html") or "")
    match = re.search(r"<p[^>]*>(.*?)</p>", fragment, re.IGNORECASE | re.DOTALL)
    inner = match.group(1) if match else fragment
    plain = re.sub(r"<br\s*/?>", "\n", inner, flags=re.IGNORECASE)
    text = unescape(re.sub(r"<[^>]+>", "", plain)).strip()
    if not text or text.endswith("…") or text.endswith("...") or ("https://t.co/" in text and len(text) < 80):
        raise ValueError("X oEmbed returned thin or truncated content")
    parser = ArticleHTMLParser(source_url)
    parser.feed(f"<article>{inner}</article>")
    parser.close()
    markdown = parser.markdown() or text
    status_match = re.search(r"/status/(\d+)", source_url)
    return {
        "tweet_id": status_match.group(1) if status_match else "x",
        "canonical_url": source_url,
        "screen_name": "",
        "display_name": str(payload.get("author_name") or ""),
        "text": text,
        "markdown": markdown,
        "created_at": None,
        "language": None,
        "stats": {},
        "assets": [
            {"url": asset["url"], "type": "image", "source": "article_image"}
            for asset in parser.captured_assets()
        ],
        "has_unpreserved_video": False,
    }


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
            if key is not None and isinstance(value, dict):
                normalized[str(key)] = value
        return normalized
    return {}


def _extract_media_url(media_entry: dict | None) -> str:
    if not media_entry:
        return ""
    media_info = media_entry.get("media_info") or {}
    return media_info.get("original_img_url") or media_info.get("url") or media_entry.get("url") or ""


def _article_media_map(article: dict) -> dict[str, str]:
    media_map: dict[str, str] = {}
    for media_entry in article.get("media_entities") or []:
        if not isinstance(media_entry, dict):
            continue
        media_id = str(media_entry.get("media_id") or "").strip()
        media_url = _extract_media_url(media_entry)
        if media_id and media_url:
            media_map[media_id] = media_url
    cover_media = article.get("cover_media") or {}
    cover_media_id = str(cover_media.get("media_id") or "").strip()
    cover_media_url = _extract_media_url(cover_media)
    if cover_media_id and cover_media_url:
        media_map.setdefault(cover_media_id, cover_media_url)
    return media_map


def _is_list_item(text: str) -> bool:
    first = text.splitlines()[0] if text else ""
    return bool(re.match(r"[ \t]*(?:[-*+]|\d+[.)]) ", first))


def _join_markdown_blocks(parts: list[str]) -> str:
    chunks: list[str] = []
    for part in parts:
        if not part:
            continue
        if chunks and _is_list_item(chunks[-1]) and _is_list_item(part):
            chunks[-1] = f"{chunks[-1]}\n{part}"
        else:
            chunks.append(part)
    return "\n\n".join(chunks)


def _append_deduped(parts: list[str], seen: set[str], value: str) -> None:
    cleaned = value.strip()
    if cleaned and cleaned not in seen:
        parts.append(cleaned)
        seen.add(cleaned)


def _append_asset_deduped(assets: list[dict], seen_urls: set[str], asset: dict) -> None:
    url = str(asset.get("url") or "").strip()
    if url and url not in seen_urls:
        assets.append(asset)
        seen_urls.add(url)


_BLOCK_PREFIX = {
    "header-one": "# ",
    "header-two": "## ",
    "header-three": "### ",
    "header-four": "#### ",
    "header-five": "##### ",
    "header-six": "###### ",
    "unordered-list-item": "- ",
}


def _format_block_markdown(block_type: str, markdown: str, list_index: int) -> str:
    if not markdown:
        return markdown
    if block_type == "ordered-list-item":
        return f"{list_index}. {markdown}"
    if block_type == "blockquote":
        return "\n".join(f"> {line}" if line else ">" for line in markdown.splitlines())
    if block_type == "code-block" and not markdown.lstrip().startswith("```"):
        return f"```\n{markdown}\n```"
    prefix = _BLOCK_PREFIX.get(block_type, "")
    return f"{prefix}{markdown}" if prefix else markdown


def _extract_block_parts(block: dict, entity_map: dict[str, dict], media_map: dict[str, str]) -> tuple[str, str, list[dict]]:
    text_value = str(block.get("text") or "")
    block_type = str(block.get("type") or "unstyled")
    if block_type == "code-block":
        normalized_text = text_value.strip("\n")
    else:
        normalized_text = " ".join(text_value.split()).strip()
    entity_ranges = block.get("entityRanges") or []
    text_parts: list[str] = [normalized_text] if normalized_text else []
    markdown_parts: list[str] = [normalized_text] if normalized_text else []
    assets: list[dict] = []
    asset_urls: set[str] = set()

    for entity_range in entity_ranges:
        if not isinstance(entity_range, dict):
            continue
        entity = entity_map.get(str(entity_range.get("key"))) or {}
        entity_type = entity.get("type")
        if entity_type == "MARKDOWN":
            markdown = ((entity.get("data") or {}).get("markdown") or "").strip()
            if markdown:
                text_parts.append(markdown)
                markdown_parts.append(markdown)
        if entity_type == "MEDIA":
            for media_item in ((entity.get("data") or {}).get("mediaItems") or []):
                if not isinstance(media_item, dict):
                    continue
                media_id = str(media_item.get("mediaId") or media_item.get("media_id") or "").strip()
                media_url = media_map.get(media_id)
                if media_url:
                    markdown_parts.append(f"![]({media_url})")
                    _append_asset_deduped(
                        assets,
                        asset_urls,
                        {"url": media_url, "type": "image", "source": "article_inline", "media_id": media_id},
                    )
    return "\n\n".join(text_parts), "\n\n".join(markdown_parts), assets


def _media_info_is_video(media_entry: dict | None) -> bool:
    if not isinstance(media_entry, dict):
        return False
    media_info = media_entry.get("media_info") or {}
    typename = str(media_info.get("__typename") or "").lower()
    media_type = str(media_info.get("type") or media_entry.get("type") or "").lower()
    return typename in {"apivideo", "apigif"} or media_type in {"video", "animated_gif", "gif"}


def _article_has_video(article: dict | None) -> bool:
    if not article:
        return False
    if _media_info_is_video(article.get("cover_media")):
        return True
    return any(_media_info_is_video(item) for item in (article.get("media_entities") or []))


def _extract_article_content(article: dict | None) -> tuple[str, str, list[dict]]:
    if not article:
        return "", "", []
    text_parts: list[str] = []
    markdown_parts: list[str] = []
    seen_text: set[str] = set()
    seen_markdown: set[str] = set()
    assets: list[dict] = []
    asset_urls: set[str] = set()
    title = (article.get("title") or "").strip()
    preview_text = (article.get("preview_text") or "").strip()
    if title:
        _append_deduped(text_parts, seen_text, title)
        _append_deduped(markdown_parts, seen_markdown, title)
    if preview_text and preview_text != title:
        _append_deduped(text_parts, seen_text, preview_text)
        _append_deduped(markdown_parts, seen_markdown, preview_text)

    content = article.get("content") or {}
    entity_map = _normalize_entity_map(content.get("entityMap"))
    media_map = _article_media_map(article)
    list_index = 0
    for block in content.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "unstyled")
        if block_type == "ordered-list-item":
            list_index += 1
        else:
            list_index = 0
        block_text, block_markdown, block_assets = _extract_block_parts(block, entity_map, media_map)
        block_markdown = _format_block_markdown(block_type, block_markdown, list_index)
        if block_text:
            _append_deduped(text_parts, seen_text, block_text)
        if block_markdown:
            _append_deduped(markdown_parts, seen_markdown, block_markdown)
        for asset in block_assets:
            _append_asset_deduped(assets, asset_urls, asset)
    return "\n\n".join(text_parts), _join_markdown_blocks(markdown_parts), assets


def _extract_tweet_media(tweet: dict) -> tuple[list[dict], bool]:
    media = tweet.get("media") or {}
    assets: list[dict] = []
    seen_urls: set[str] = set()
    has_video = bool(media.get("videos"))

    for item in media.get("photos") or []:
        if not isinstance(item, dict):
            continue
        media_type = str(item.get("type") or "photo").lower()
        if media_type == "gif":
            has_video = True
            continue
        url = str(item.get("url") or "").strip()
        if url:
            _append_asset_deduped(
                assets,
                seen_urls,
                {"url": url, "type": "image", "source": "tweet_media", "media_id": str(item.get("id") or "")},
            )

    for item in media.get("all") or []:
        if not isinstance(item, dict):
            continue
        media_type = str(item.get("type") or "").lower()
        if media_type in {"video", "gif", "animated_gif"}:
            has_video = True
            continue
        if media_type not in {"photo", "mosaic_photo"}:
            continue
        url = str(item.get("url") or "").strip()
        if url:
            _append_asset_deduped(
                assets,
                seen_urls,
                {"url": url, "type": "image", "source": "tweet_media", "media_id": str(item.get("id") or "")},
            )

    external = media.get("external") or {}
    if isinstance(external, dict) and str(external.get("type") or "").lower() == "video":
        has_video = True

    return assets, has_video


def parse_fxtwitter_payload(payload: dict) -> dict:
    tweet = payload.get("tweet") or {}
    author = tweet.get("author") or {}
    canonical_url = tweet.get("url") or ""
    tweet_id = str(tweet.get("id") or "")
    raw_text = ((tweet.get("raw_text") or {}).get("text") or "").strip()
    article = tweet.get("article")
    article_text, article_markdown, article_assets = _extract_article_content(article)
    tweet_assets, tweet_has_video = _extract_tweet_media(tweet)
    text = (tweet.get("text") or "").strip()
    if not text or text == raw_text:
        text = article_text or raw_text or text
    markdown = article_markdown or text
    attached: list[str] = []
    for asset in tweet_assets:
        url = str(asset.get("url") or "").strip()
        if url and not markdown_contains_image(markdown, url) and url not in attached:
            attached.append(url)
    if attached:
        gallery = "\n\n".join(f"![]({url})" for url in attached)
        markdown = f"{markdown.rstrip()}\n\n{gallery}" if markdown.strip() else gallery

    assets: list[dict] = []
    seen_urls: set[str] = set()
    for asset in [*article_assets, *tweet_assets]:
        _append_asset_deduped(assets, seen_urls, asset)

    return {
        "tweet_id": tweet_id,
        "canonical_url": canonical_url,
        "screen_name": author.get("screen_name") or "",
        "display_name": author.get("name") or "",
        "text": text,
        "markdown": markdown,
        "created_at": _normalize_created_at(tweet.get("created_at")),
        "language": tweet.get("lang") or None,
        "stats": {"likes": tweet.get("likes", 0), "retweets": tweet.get("retweets", 0), "replies": tweet.get("replies", 0), "views": tweet.get("views", 0)},
        "assets": assets,
        "has_unpreserved_video": tweet_has_video or _article_has_video(article),
    }
