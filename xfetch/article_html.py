"""Convert article HTML to Markdown without flattening block order or image position."""
from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse


_SKIP_TAGS = {"script", "style", "noscript", "head"}
_CHROME_TAGS = {"nav", "header", "footer", "aside"}
_BLOCK_TAGS = {"p", "div", "section", "article", "main", "figure", "figcaption", "blockquote", "tr", "table"}
_LIST_TRANSPARENT_TAGS = {"p", "div", "section", "figure", "figcaption"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Generic pages with no article/main used to keep four images. A real article body is not capped.
_FALLBACK_IMAGE_LIMIT = 4
_IMAGE_LINE_RE = re.compile(r"^!\[[^\]]*\]\([^)]*\)$")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def _markdown_destination(url: str) -> str:
    # Parentheses and whitespace terminate a Markdown destination. Leave query
    # strings alone so signed image URLs still download.
    return (
        url.replace("\\", "%5C")
        .replace("\r", "")
        .replace("\n", "")
        .replace(" ", "%20")
        .replace("(", "%28")
        .replace(")", "%29")
    )


def _absolute_http_url(base_url: str, raw: str) -> str | None:
    value = (raw or "").strip()
    if not value or value.startswith("data:"):
        return None
    if value.startswith("//"):
        value = "https:" + value
    url = urljoin(base_url, value)
    if urlparse(url).scheme not in {"http", "https"}:
        return None
    return _markdown_destination(url)


def _image_candidate(attrs: dict[str, str]) -> str:
    for key in ("data-src", "data-original", "data-lazy-src"):
        value = (attrs.get(key) or "").strip()
        if value and not value.startswith("data:"):
            return value
    return (attrs.get("src") or "").strip()


def _is_tiny(width: str, height: str) -> bool:
    try:
        return int(width) <= 1 and int(height) <= 1
    except (TypeError, ValueError):
        return False


def markdown_to_text(markdown: str) -> str:
    lines: list[str] = []
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if _IMAGE_LINE_RE.match(stripped):
            continue
        stripped = _HEADING_RE.sub("", stripped)
        stripped = _LINK_RE.sub(r"\1", stripped)
        stripped = stripped.replace("**", "")
        stripped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", stripped)
        stripped = stripped.replace("`", "")
        lines.append(stripped)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def visual_capture_status(
    markdown: str,
    image_urls: list[str],
    *,
    has_body: bool,
    status: str = "complete",
) -> str:
    """A text-only flatten is not a complete visual capture when images belong in the body."""
    if status != "complete":
        return status
    urls = [url for url in image_urls if url]
    if urls and not all(url in (markdown or "") for url in urls):
        return "partial"
    if not has_body and not urls:
        return "partial"
    return "complete"


class ArticleHTMLParser(HTMLParser):
    """HTML-to-Markdown parser for article bodies.

    `root_class` captures only that element (WeChat `rich_media_content`).
    `prefer_main` keeps `article`/`main` when present and ignores page chrome.
    """

    def __init__(self, base_url: str, *, root_class: str | None = None, prefer_main: bool = False):
        super().__init__()
        self.base_url = base_url
        self.root_class = root_class
        self.prefer_main = prefer_main
        self._inside = root_class is None
        self._depth = 0
        self._skip = 0
        self._chrome = 0
        self._main_depth = 0
        self._pre = False
        self._parts: list[str] = []
        self._assets: list[dict] = []
        self._main_parts: list[str] = []
        self._main_assets: list[dict] = []
        self._page_parts: list[str] = []
        self._page_assets: list[dict] = []
        self._lists: list[int | None] = []
        self._links: list[str | None] = []
        self._emphasis: list[tuple[str, list[str], int]] = []
        self._pending_marker = False

    def _outside_chrome(self) -> bool:
        # Page chrome only. A header or aside inside article/main is article content,
        # including when a site header wraps the article.
        return bool(self._chrome) and self._main_depth == 0

    def _current(self) -> tuple[list[str], list[dict]] | None:
        if not self._inside or self._skip or self._outside_chrome():
            return None
        if self.prefer_main and self._main_depth:
            return self._main_parts, self._main_assets
        if self.prefer_main:
            return self._page_parts, self._page_assets
        return self._parts, self._assets

    def _append(self, value: str) -> None:
        current = self._current()
        if current is None:
            return
        if value.strip():
            self._pending_marker = False
        current[0].append(value)

    def _append_block(self, tag: str, *, opening: bool) -> None:
        if self._lists and tag in _LIST_TRANSPARENT_TAGS:
            if opening and not self._pending_marker:
                self._append("\n")
            return
        self._append("\n\n")

    def _close_root(self) -> None:
        if not self.root_class:
            return
        self._depth -= 1
        if self._depth <= 0:
            self._inside = False
            self._depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = {key.lower(): value or "" for key, value in attrs}
        if self.root_class and not self._inside:
            classes = (attrs.get("class") or "").split()
            if self.root_class in classes:
                self._inside = True
                self._depth = 1
            return
        if self.root_class and tag not in _VOID_TAGS:
            self._depth += 1
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if self.prefer_main and tag in {"article", "main"}:
            self._main_depth += 1
        if self.prefer_main and tag in _CHROME_TAGS and self._main_depth == 0:
            self._chrome += 1
            return
        if self._outside_chrome():
            return

        if tag in _BLOCK_TAGS:
            self._append_block(tag, opening=True)
        elif re.fullmatch(r"h[1-6]", tag):
            self._append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in {"ul", "ol"}:
            self._append("\n\n")
            self._lists.append(0 if tag == "ol" else None)
        elif tag == "li":
            marker = "- "
            if self._lists and self._lists[-1] is not None:
                self._lists[-1] += 1
                marker = f"{self._lists[-1]}. "
            self._append("\n" + "  " * max(0, len(self._lists) - 1) + marker)
            self._pending_marker = True
        elif tag == "br":
            self._append("\n\n")
        elif tag in {"strong", "b", "em", "i"}:
            current = self._current()
            if current is not None:
                self._emphasis.append((tag, current[0], len(current[0])))
                current[0].append("")
        elif tag == "pre":
            self._pre = True
            self._append("\n\n```\n")
        elif tag == "code" and not self._pre:
            self._append("`")
        elif tag == "a":
            url = _absolute_http_url(self.base_url, attrs.get("href") or "")
            if url is None and (attrs.get("href") or "").startswith("mailto:"):
                url = _markdown_destination(attrs.get("href") or "")
            self._links.append(url)
            if url:
                self._append("[")
        elif tag == "img":
            self._append_image(attrs)

    def _link_label_end(self, parts: list[str]) -> int | None:
        """Index just after the open link's label, or None when no link is open."""
        if not self._links or not self._links[-1]:
            return None
        end = len(parts)
        while end > 0 and not parts[end - 1].strip():
            end -= 1
        return end

    def _suppress_image_only_link(self, parts: list[str]) -> None:
        """Drop an anchor whose only content is this image so it does not become `[](url)`."""
        end = self._link_label_end(parts)
        if end is None:
            return
        if end > 0 and parts[end - 1] == "[":
            del parts[end - 1 :]
            self._links[-1] = None

    def _close_link_before_image(self, parts: list[str]) -> None:
        """A linked image is not `[` + image block + `](url)`. Close any text link first."""
        end = self._link_label_end(parts)
        if end is None:
            return
        url = self._links[-1]
        self._links[-1] = None
        if end > 0 and parts[end - 1] == "[":
            del parts[end - 1 :]
            return
        if end < len(parts):
            del parts[end:]
        if parts:
            parts[-1] = parts[-1].rstrip()
        parts.append("](" + url + ")")

    def _fallback_image_capped(self, url: str) -> bool:
        if not self.prefer_main or self._main_depth:
            return False
        if any(asset["url"] == url for asset in self._page_assets):
            return False
        return len(self._page_assets) >= _FALLBACK_IMAGE_LIMIT

    def _append_image(self, attrs: dict[str, str]) -> None:
        url = _absolute_http_url(self.base_url, _image_candidate(attrs))
        if not url:
            return
        width = (attrs.get("width") or "").strip()
        height = (attrs.get("height") or "").strip()
        if width and height and _is_tiny(width, height):
            return
        current = self._current()
        if current is None:
            return
        parts, assets = current
        if self._fallback_image_capped(url):
            self._suppress_image_only_link(parts)
            return
        alt = " ".join((attrs.get("alt") or "").replace("[", "").replace("]", "").split())
        self._close_link_before_image(parts)
        self._append(f"\n\n![{alt}]({url})\n\n")
        if any(asset["url"] == url for asset in assets):
            return
        asset: dict[str, str] = {"url": url, "type": "image", "source": "article_image", "alt": alt}
        if width:
            asset["width"] = width
        if height:
            asset["height"] = height
        assets.append(asset)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _VOID_TAGS:
            return
        if self.root_class and not self._inside:
            return
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
            self._close_root()
            return
        if self._skip:
            self._close_root()
            return
        if self._outside_chrome():
            if tag in _CHROME_TAGS and self._chrome:
                self._chrome -= 1
            self._close_root()
            return

        if tag in _BLOCK_TAGS:
            self._append_block(tag, opening=False)
        elif re.fullmatch(r"h[1-6]", tag):
            self._append("\n\n")
        elif tag in {"ul", "ol"}:
            if self._lists:
                self._lists.pop()
            self._append("\n\n")
        elif tag in {"strong", "b", "em", "i"} and self._emphasis:
            opening_tag, parts, start = self._emphasis.pop()
            content = "".join(parts[start + 1 :])
            if opening_tag == tag and content.strip() and "\n" not in content:
                marker = "**" if tag in {"strong", "b"} else "*"
                parts[start] = marker
                parts.append(marker)
        elif tag == "pre":
            self._pre = False
            current = self._current()
            if current and current[0] and current[0][-1].endswith("\n"):
                # The preformatted text already ends on a line break.
                current[0].append("```\n\n")
            else:
                self._append("\n```\n\n")
        elif tag == "code" and not self._pre:
            self._append("`")
        elif tag == "a" and self._links:
            url = self._links.pop()
            if url:
                self._append("](" + url + ")")

        if self.prefer_main and tag in {"article", "main"} and self._main_depth:
            self._main_depth -= 1
        self._close_root()

    def handle_data(self, data):
        if not self._inside or self._skip or self._outside_chrome():
            return
        if not self._pre:
            data = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", data)
        text = data if self._pre else re.sub(r"\s+", " ", data)
        if text:
            self._append(text)

    def _selected(self) -> tuple[list[str], list[dict]]:
        if self.prefer_main and any(part.strip() for part in self._main_parts):
            return self._main_parts, self._main_assets
        if self.prefer_main:
            return self._page_parts, self._page_assets
        return self._parts, self._assets

    def markdown(self) -> str:
        parts, _assets = self._selected()
        lines = "".join(parts).split("\n")
        normalized: list[str] = []
        in_fence = False
        blank_run = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_fence = not in_fence
                normalized.append(stripped)
                blank_run = 0
                continue
            if in_fence:
                normalized.append(line)
                blank_run = 0
                continue
            if not stripped:
                blank_run += 1
                if blank_run == 1:
                    normalized.append("")
                continue
            blank_run = 0
            normalized.append(stripped)
        return "\n".join(normalized).strip()

    def captured_assets(self) -> list[dict]:
        _parts, assets = self._selected()
        return assets

    def text(self) -> str:
        return markdown_to_text(self.markdown())
