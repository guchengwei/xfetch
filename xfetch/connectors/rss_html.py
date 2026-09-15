"""Convert RSS HTML bodies to portable Markdown without flattening block order."""
from html.parser import HTMLParser
import re
from urllib.parse import quote, urljoin, urlparse


class RSSHTMLParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.parts: list[str] = []
        self.assets: list[dict] = []
        self.lists: list[int | None] = []
        self.links: list[str | None] = []
        self.skip = 0
        self.pre = False
        self.emphasis: list[tuple[str, int]] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if self.skip:
            return
        if tag in {"p", "div", "section", "figure", "figcaption", "blockquote"}:
            self.parts.append("\n\n")
        elif re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in {"ul", "ol"}:
            self.parts.append("\n\n")
            self.lists.append(0 if tag == "ol" else None)
        elif tag == "li":
            marker = "- "
            if self.lists and self.lists[-1] is not None:
                self.lists[-1] += 1
                marker = f"{self.lists[-1]}. "
            self.parts.append("\n" + "  " * max(0, len(self.lists) - 1) + marker)
        elif tag == "br":
            self.parts.append("\n\n")
        elif tag in {"strong", "b", "em", "i"}:
            self.emphasis.append((tag, len(self.parts)))
            self.parts.append("")
        elif tag == "pre":
            self.pre = True
            self.parts.append("\n\n```\n")
        elif tag == "code" and not self.pre:
            self.parts.append("`")
        elif tag == "a":
            url = urljoin(self.base_url, attrs.get("href") or "")
            safe = urlparse(url).scheme in {"http", "https", "mailto"}
            self.links.append(url if safe else None)
            if safe:
                self.parts.append("[")
        elif tag == "img":
            url = urljoin(self.base_url, attrs.get("src") or "")
            parsed = urlparse(url)
            if not attrs.get("src") or parsed.scheme not in {"http", "https"}:
                return
            if parsed.hostname == "medium.com" and parsed.path == "/_/stat":
                return
            # Parentheses otherwise terminate Markdown destinations early.
            url = quote(url, safe=":/%?#[]@!$&'*+,;=~")
            alt = (attrs.get("alt") or "Article image").replace("[", "").replace("]", "")
            self.parts.append(f"\n\n![{alt}]({url})\n\n")
            if not any(asset["url"] == url for asset in self.assets):
                self.assets.append({"url": url, "type": "image", "source": "article_image", "alt": alt})

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag in {"p", "div", "section", "figure", "figcaption", "blockquote"} or re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n")
        elif tag in {"ul", "ol"}:
            if self.lists:
                self.lists.pop()
            self.parts.append("\n\n")
        elif tag in {"strong", "b", "em", "i"} and self.emphasis:
            opening_tag, start = self.emphasis.pop()
            content = "".join(self.parts[start + 1:])
            # RSS sometimes wraps entire paragraphs in emphasis. Keep the
            # blocks readable instead of emitting invalid multiline markers.
            if opening_tag == tag and content.strip() and "\n" not in content:
                marker = "**" if tag in {"strong", "b"} else "*"
                self.parts[start] = marker
                self.parts.append(marker)
        elif tag == "pre":
            self.pre = False
            self.parts.append("\n```\n\n")
        elif tag == "code" and not self.pre:
            self.parts.append("`")
        elif tag == "a" and self.links:
            url = self.links.pop()
            if url:
                self.parts.append("](" + quote(url, safe=":/%?#[]@!$&'*+,;=~") + ")")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data if self.pre else re.sub(r"\s+", " ", data))

    def markdown(self):
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
