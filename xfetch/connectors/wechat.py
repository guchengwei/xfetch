from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import re
from urllib.request import Request

from xfetch.article_html import ArticleHTMLParser, visual_capture_status
from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_WECHAT_URL_RE = re.compile(r"^https?://mp\.weixin\.qq\.com/", re.IGNORECASE)


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

        body_parser = ArticleHTMLParser(canonical_url, root_class="rich_media_content")
        body_parser.feed(html)
        body_parser.close()
        captured_body = body_parser.markdown()
        captured_text = body_parser.text()

        title = _extract_first(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']*)["\']', html)
        if not title:
            title = _extract_first(r'<h1[^>]*class=["\'][^"\']*rich_media_title[^"\']*["\'][^>]*>(.*?)</h1>', html)
        author = _extract_first(r'<meta\s+name=["\']author["\']\s+content=["\']([^"\']*)["\']', html)
        account = _extract_first(r'var\s+nickname\s*=\s*["\']([^"\']+)["\']', html)
        if not account:
            account = _extract_first(r'<a[^>]*id=["\']js_name["\'][^>]*>(.*?)</a>', html)
        text = captured_text or title or canonical_url
        assets = [{"url": item["url"], "type": "image"} for item in body_parser.captured_assets()]
        created_at = _normalize_timestamp(_extract_first(r'var\s+ct\s*=\s*["\']?(\d+)["\']?', html))
        title = title or text.splitlines()[0][:80]
        author = author or account or "unknown"
        author_handle = account or "unknown"
        markdown_body = captured_body or text
        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Account: {author_handle}\n- Author: {author}\n\n{markdown_body}\n"
        capture_status = visual_capture_status(
            markdown,
            [item["url"] for item in assets],
            has_body=bool(captured_body.strip()),
            status="complete",
        )

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
            lineage={"connector": "wechat", "runtime_version": "0.2.2"},
            capture_status=capture_status,
            content_kinds=["text", "images"] if assets else ["text"],
        )
