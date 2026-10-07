from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request
from urllib.error import HTTPError

from xfetch.article_html import ArticleHTMLParser
from xfetch.connectors.base import BaseConnector
from xfetch.connectors.x import is_x_url
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


def _is_feed_url(url: str) -> bool:
    lowered = url.lower()
    return lowered.endswith(".xml") or "/feed" in lowered or "/rss" in lowered or "/atom" in lowered


class _HTMLDocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.author = None
        self.canonical_url = None
        self.description = None
        self.open_graph_title = None
        self.open_graph_image = None
        self.open_graph_image_width = None
        self.open_graph_image_height = None
        self._in_title = False
        self._skip_depth = 0
        self._main_depth = 0
        self._chunks: list[str] = []
        self._main_chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        lowered = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs}
        if lowered == "title":
            self._in_title = True
        if lowered in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if lowered in {"article", "main"}:
            self._main_depth += 1
        if lowered == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"author", "article:author"} and attrs_dict.get("content"):
                self.author = attrs_dict["content"].strip()
            if name in {"description", "og:description", "twitter:description"} and attrs_dict.get("content"):
                self.description = self.description or attrs_dict["content"].strip()
            if name == "og:title" and attrs_dict.get("content"):
                self.open_graph_title = attrs_dict["content"].strip()
            if name in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"} and attrs_dict.get("content"):
                self.open_graph_image = self.open_graph_image or attrs_dict["content"].strip()
            if name == "og:image:width" and attrs_dict.get("content"):
                self.open_graph_image_width = attrs_dict["content"].strip()
            if name == "og:image:height" and attrs_dict.get("content"):
                self.open_graph_image_height = attrs_dict["content"].strip()
        if lowered == "link":
            rel = (attrs_dict.get("rel") or "").lower()
            if "canonical" in rel and attrs_dict.get("href"):
                self.canonical_url = attrs_dict["href"].strip()
        if lowered in {"p", "div", "section", "article", "main", "br", "li", "h1", "h2", "h3", "h4"}:
            self._append("\n")

    def handle_endtag(self, tag):
        lowered = tag.lower()
        if lowered == "title":
            self._in_title = False
        if lowered in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if lowered in {"p", "div", "section", "article", "main", "li", "h1", "h2", "h3", "h4"}:
            self._append("\n")
        if lowered in {"article", "main"} and self._main_depth:
            self._main_depth -= 1

    def handle_data(self, data):
        text = unescape(data)
        if self._in_title:
            self.title += text
        if self._skip_depth:
            return
        collapsed = " ".join(text.split())
        if collapsed:
            self._append(collapsed)

    def _append(self, value: str) -> None:
        self._chunks.append(value)
        if self._main_depth:
            self._main_chunks.append(value)

    @staticmethod
    def _clean(chunks: list[str]) -> str:
        text = " ".join(chunks)
        text = re.sub(r"\s*\n\s*", "\n", text)
        text = re.sub(r"\n{2,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    def text_content(self) -> str:
        main = self._clean(self._main_chunks)
        return main or self._clean(self._chunks)


def _fetch_url(url: str) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": "xfetch/0.2.4"})
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    return body, final_url, content_type


def _domain_handle(url: str) -> str:
    return urlparse(url).netloc.lower() or "unknown"


def _error_body(exc: HTTPError, limit: int = 8192) -> str:
    try:
        raw = exc.read(limit)
    except Exception:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw or "")


def _is_zhihu_host(hostname: str | None) -> bool:
    host = (hostname or "").lower().rstrip(".")
    return host == "zhihu.com" or host.endswith(".zhihu.com")


class WebConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        if not url.lower().startswith(("http://", "https://")):
            return False
        if is_x_url(url) or _is_feed_url(url):
            return False
        return True

    def fetch(self, url: str) -> NormalizedDocument:
        try:
            html, fetched_url, content_type = _fetch_url(url)
        except HTTPError as exc:
            parsed = urlparse(url)
            if exc.code == 403 and _is_zhihu_host(parsed.hostname):
                body = _error_body(exc)
                if "zh-zse-ck" in body or "static.zhihu.com/zse-ck" in body:
                    raise ValueError(
                        f"Zhihu blocked automated access to {url} (HTTP 403, zse-ck anti-bot challenge). "
                        "xfetch cannot capture Zhihu articles without a browser session; nothing was saved."
                    ) from exc
            match = re.fullmatch(r"/(@[A-Za-z0-9_.-]+)/[^/]+-([a-f0-9]{12})/?", parsed.path)
            if exc.code != 403 or parsed.hostname not in {"medium.com", "www.medium.com"} or not match:
                raise
            from xfetch.connectors.rss import RSSConnector
            feed_url = f"https://medium.com/feed/{match[1]}"
            doc = RSSConnector().fetch(feed_url, entry_id=f"https://medium.com/p/{match[2]}")
            doc.source_url = url
            doc.metadata.update({"fallback": "medium_rss", "feed_url": feed_url,
                                 "capture_limitation": "Captured public RSS content; completeness against the blocked article page is unverified."})
            if doc.capture_status == "complete":
                doc.capture_status = "partial"
            return doc
        parser = _HTMLDocumentParser()
        parser.feed(html)
        parser.close()

        canonical_url = urljoin(fetched_url, parser.canonical_url) if parser.canonical_url else fetched_url
        title = " ".join((parser.open_graph_title or parser.title).split()) or urlparse(canonical_url).path.strip("/") or canonical_url
        author_handle = _domain_handle(canonical_url)
        author = parser.author or author_handle
        body_parser = ArticleHTMLParser(fetched_url, prefer_main=True)
        body_parser.feed(html)
        body_parser.close()
        markdown_body = body_parser.markdown()
        text = body_parser.text() or parser.text_content() or title
        if not markdown_body:
            markdown_body = text
        external_id = sha1(canonical_url.encode("utf-8")).hexdigest()[:12]
        fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Author: {author}\n\n{markdown_body}\n"
        assets: list[dict] = []
        seen_urls: set[str] = set()
        if parser.open_graph_image:
            image_url = urljoin(fetched_url, parser.open_graph_image)
            assets.append(
                {
                    "url": image_url,
                    "type": "image",
                    "source": "open_graph",
                    "width": parser.open_graph_image_width,
                    "height": parser.open_graph_image_height,
                }
            )
            seen_urls.add(image_url)
        for asset in body_parser.captured_assets():
            image_url = asset["url"]
            if image_url in seen_urls or not image_url.startswith(("http://", "https://")):
                continue
            assets.append(asset)
            seen_urls.add(image_url)

        return NormalizedDocument(
            source_type="web",
            source_url=url,
            canonical_url=canonical_url,
            external_id=external_id,
            title=title,
            author=author,
            author_handle=author_handle,
            created_at=None,
            language=None,
            text=text,
            markdown=markdown,
            summary=parser.description,
            assets=assets,
            metadata={"platform": "web", "content_type": content_type, "description": parser.description},
            lineage={"fetched_at": fetched_at, "connector": "web", "runtime_version": "0.2.4"},
            capture_status="partial",
            content_kinds=["text", "metadata"] + (["images"] if assets else []),
        )
