from __future__ import annotations

from html import unescape
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument


_TELEGRAM_URL_RE = re.compile(r"^https?://(?:t\.me|telegram\.me)/", re.IGNORECASE)


def _fetch_html(url: str) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    return html, final_url, content_type


def _extract_meta(html: str, property_name: str) -> str | None:
    pattern = rf'<meta\s+property=["\']{re.escape(property_name)}["\']\s+content=["\']([^"\']*)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    if not match:
        return None
    return unescape(match.group(1).strip())


def _parse_channel_and_message(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    channel = parts[0] if parts else "unknown"
    message_id = parts[1] if len(parts) > 1 else None
    return channel, message_id


class TelegramConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return bool(_TELEGRAM_URL_RE.match(url))

    def fetch(self, url: str) -> NormalizedDocument:
        html, canonical_url, content_type = _fetch_html(url)
        channel, message_id = _parse_channel_and_message(canonical_url)
        title = _extract_meta(html, "og:title") or f"Telegram post {channel}"
        description = _extract_meta(html, "og:description") or title
        image = _extract_meta(html, "og:image")
        external_id = f"{channel}-{message_id}" if message_id else channel
        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Channel: {channel}\n\n{description}\n"
        assets = [{"url": image, "type": "image"}] if image else []

        return NormalizedDocument(
            source_type="telegram",
            source_url=url,
            canonical_url=canonical_url,
            external_id=external_id,
            title=title,
            author=channel,
            author_handle=channel,
            created_at=None,
            language=None,
            text=description,
            markdown=markdown,
            summary=None,
            assets=assets,
            metadata={
                "platform": "telegram",
                "channel": channel,
                "message_id": message_id,
                "content_type": content_type,
            },
            lineage={
                "connector": "telegram",
                "runtime_version": "0.1.0",
            },
        )
