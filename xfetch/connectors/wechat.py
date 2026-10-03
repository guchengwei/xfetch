from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import re
from urllib.request import Request

from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_WECHAT_URL_RE = re.compile(r"^https?://mp\.weixin\.qq\.com/", re.IGNORECASE)


class _WeChatContentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self._capture_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = {key.lower(): value for key, value in attrs}
        classes = attrs_dict.get("class", "") or ""
        if tag.lower() == "div" and "rich_media_content" in classes:
            self._capture_depth = 1
            return
        if self._capture_depth:
            self._capture_depth += 1
            if tag.lower() in {"p", "div", "section", "article", "br", "li", "h1", "h2", "h3"}:
                self._chunks.append("\n")

    def handle_endtag(self, tag):
        if self._capture_depth:
            if tag.lower() in {"p", "div", "section", "article", "li"}:
                self._chunks.append("\n")
            self._capture_depth -= 1

    def handle_data(self, data):
        if not self._capture_depth:
            return
        text = " ".join(unescape(data).split())
        if text:
            self._chunks.append(text)

    def text_content(self) -> str:
        text = " ".join(self._chunks)
        text = re.sub(r"\s*\n\s*", "\n", text)
        text = re.sub(r"\n{2,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()


def _fetch_html(url: str) -> tuple[str, str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        },
    )
    with urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    return html, final_url, content_type


def _extract_first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    return unescape(match.group(1).strip())


def _extract_images(html: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    assets: list[dict[str, str]] = []
    for match in re.finditer(r'data-src=["\'](https?://[^"\']+)["\']', html, re.IGNORECASE):
        url = match.group(1)
        if url not in seen:
            seen.add(url)
            assets.append({"url": url, "type": "image"})
    return assets


def _normalize_timestamp(raw_timestamp: str | None) -> str | None:
    if not raw_timestamp:
        return None
    try:
        ts = int(raw_timestamp)
    except ValueError:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _looks_blocked(html: str) -> bool:
    sentinels = (
        "Weixin Official Accounts Platform",
        "环境异常",
        "去验证",
        "访问过于频繁",
    )
    return any(value in html for value in sentinels)


class WeChatConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return bool(_WECHAT_URL_RE.match(url))

    def fetch(self, url: str) -> NormalizedDocument:
        html, canonical_url, content_type = _fetch_html(url)
        if _looks_blocked(html):
            raise ValueError("WeChat returned an anti-scraping verification page")

        parser = _WeChatContentParser()
        parser.feed(html)
        parser.close()
        text = parser.text_content()

        title = _extract_first(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']*)["\']', html)
        if not title:
            title = _extract_first(r'<h1[^>]*class=["\'][^"\']*rich_media_title[^"\']*["\'][^>]*>(.*?)</h1>', html)
        author = _extract_first(r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']*)["\']', html)
        account = _extract_first(r'var\s+nickname\s*=\s*["\']([^"\']+)["\']', html)
        if not account:
            account = _extract_first(r'<a[^>]*id=["\']js_name["\'][^>]*>(.*?)</a>', html)
        if not text:
            text = title or canonical_url
        assets = _extract_images(html)
        created_at = _normalize_timestamp(_extract_first(r'var\s+ct\s*=\s*["\']?(\d+)["\']?', html))
        title = title or text.splitlines()[0][:80]
        author = author or account or "unknown"
        author_handle = account or "unknown"
        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Account: {author_handle}\n- Author: {author}\n\n{text}\n"

        return NormalizedDocument(
            source_type="wechat",
            source_url=url,
            canonical_url=canonical_url,
            external_id=canonical_url.rstrip("/").split("/")[-1] or "wechat",
            title=title,
            author=author,
            author_handle=author_handle,
            created_at=created_at,
            language="zh",
            text=text,
            markdown=markdown,
            summary=None,
            assets=assets,
            metadata={"platform": "wechat", "account": account, "content_type": content_type},
            lineage={"connector": "wechat", "runtime_version": "0.2.1"},
            capture_status="complete" if parser.text_content() else "partial",
            content_kinds=["text", "images"] if assets else ["text"],
        )
