from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from hashlib import sha1
import json
import re
from urllib.request import Request

from xfetch.article_html import ArticleHTMLParser, visual_capture_status
from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_XHS_URL_RE = re.compile(r"^https?://(?:www\.)?(?:xiaohongshu\.com|xhslink\.com)/", re.IGNORECASE)
_NOTE_ID_RE = re.compile(r"(?:explore|discovery/item|notes?)/([a-f0-9]{24})", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def _note_body(text: str, image_urls: list[str], base_url: str) -> tuple[str, str, list[str]]:
    """Return plain text, markdown, and image URLs in visual order.

    Gallery images have no slot inside a plain caption, so they follow the
    paragraphs in imageList order. Images already placed in HTML stay there.
    """
    body = ""
    plain = text
    inline_urls: list[str] = []
    if _HTML_TAG_RE.search(text or ""):
        parser = ArticleHTMLParser(base_url)
        parser.feed(text)
        parser.close()
        body = parser.markdown()
        plain = parser.text() or text
        inline_urls = [asset["url"] for asset in parser.captured_assets()]
    if not body:
        paragraphs = [" ".join(line.split()) for line in (text or "").splitlines()]
        paragraphs = [line for line in paragraphs if line]
        body = "\n\n".join(paragraphs)
        plain = text
    extras = [url for url in image_urls if url and url not in body]
    if extras:
        gallery = "\n\n".join(f"![]({url})" for url in extras)
        body = f"{body}\n\n{gallery}" if body else gallery
    asset_urls = list(image_urls)
    for url in inline_urls:
        if url not in asset_urls:
            asset_urls.append(url)
    return plain, body, asset_urls


def _fetch_html(url: str) -> tuple[str, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    return html, final_url, content_type


def _extract_note_id(url: str) -> str | None:
    match = _NOTE_ID_RE.search(url)
    return match.group(1) if match else None


def _extract_initial_state(html: str) -> dict:
    if "登录后推荐更懂你的笔记" in html or "小红书 - 你的生活兴趣社区" in html:
        raise ValueError("Xiaohongshu returned a login wall; an authenticated fetch path is required")
    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?})\s*;</script>', html, re.DOTALL)
    if not match:
        match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?})\s*;', html, re.DOTALL)
    if not match:
        raise ValueError("Xiaohongshu initial state not found")
    raw = match.group(1).replace("undefined", "null")
    return json.loads(raw)


def _normalize_timestamp(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.endswith("Z"):
        return value
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    if ts > 10**12:
        ts = ts // 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def _parse_count(value) -> int:
    if isinstance(value, int):
        return value
    text = str(value or "0").strip()
    if not text:
        return 0
    if text.endswith("万"):
        return int(float(text[:-1]) * 10000)
    try:
        return int(float(text))
    except ValueError:
        return 0


class XiaohongshuConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return bool(_XHS_URL_RE.match(url))

    def fetch(self, url: str) -> NormalizedDocument:
        html, canonical_url, content_type = _fetch_html(url)
        state = _extract_initial_state(html)
        detail_map = state.get("note", {}).get("noteDetailMap", {}) or state.get("noteDetailMap", {})
        if not detail_map:
            raise ValueError("Xiaohongshu note detail map missing")
        note_id, wrapper = next(iter(detail_map.items()))
        note = wrapper.get("note", wrapper)
        note_id = _extract_note_id(canonical_url) or note_id or sha1(canonical_url.encode("utf-8")).hexdigest()[:12]
        user = note.get("user", {})
        author = user.get("nickname") or user.get("nick_name") or "unknown"
        author_handle = _slugify(author)
        title = unescape((note.get("title") or "").strip() or "Xiaohongshu note")
        raw_text = unescape((note.get("desc") or note.get("content") or title).strip())
        note_type = note.get("type", "")
        image_list = note.get("imageList", note.get("image_list", [])) or []
        image_urls: list[str] = []
        for item in image_list:
            image_url = item.get("urlDefault") or item.get("url") or item.get("url_default")
            if image_url and image_url not in image_urls:
                image_urls.append(image_url)
        text, markdown_body, image_urls = _note_body(raw_text, image_urls, canonical_url)
        assets = [{"url": image_url, "type": "image"} for image_url in image_urls]
        tags = [tag.get("name") for tag in (note.get("tagList", note.get("tag_list", [])) or []) if tag.get("name")]
        interact = note.get("interactInfo", note.get("interact_info", {})) or {}
        stats = {
            "likes": _parse_count(interact.get("likedCount", interact.get("liked_count", 0))),
            "favorites": _parse_count(interact.get("collectedCount", interact.get("collected_count", 0))),
            "comments": _parse_count(interact.get("commentCount", interact.get("comment_count", 0))),
            "shares": _parse_count(interact.get("shareCount", interact.get("share_count", 0))),
        }
        created_at = _normalize_timestamp(note.get("time") or note.get("createTime"))
        is_video = note_type == "video"
        metadata = {
            "platform": "xiaohongshu",
            "note_type": "video" if is_video else "image",
            "stats": stats,
            "content_type": content_type,
        }
        if is_video:
            metadata["unpreserved_media"] = ["video"]
        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Author: {author}\n- Type: {'video' if is_video else 'image'}\n\n{markdown_body}\n"
        capture_status = visual_capture_status(
            markdown,
            image_urls,
            has_body=bool(markdown_body.strip()),
            status="partial" if is_video else "complete",
        )

        return NormalizedDocument(
            source_type="xiaohongshu",
            source_url=url,
            canonical_url=canonical_url,
            external_id=note_id,
            title=title,
            author=author,
            author_handle=author_handle,
            created_at=created_at,
            language="zh",
            text=text,
            markdown=markdown,
            summary=None,
            tags=tags,
            assets=assets,
            metadata=metadata,
            lineage={"connector": "xiaohongshu", "runtime_version": "0.2.0"},
            capture_status=capture_status,
            content_kinds=["text", "images"] if assets else ["text"],
        )
