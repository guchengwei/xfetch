from __future__ import annotations

from datetime import datetime, timezone
import re

from xfetch.backends.fxtwitter import fetch_fxtwitter_json, parse_fxtwitter_payload
from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument, derive_title, render_markdown


_X_URL_RE = re.compile(r"^https?://(?:www\.)?(?:x\.com|twitter\.com)/[^/]+/status/\d+", re.IGNORECASE)


def is_x_url(url: str) -> bool:
    return bool(_X_URL_RE.match(url))


class XConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return is_x_url(url)

    def fetch(self, url: str) -> NormalizedDocument:
        payload = fetch_fxtwitter_json(url)
        return self.normalize_payload(source_url=url, payload=payload)

    def normalize_payload(self, source_url: str, payload: dict) -> NormalizedDocument:
        raw = parse_fxtwitter_payload(payload)
        doc = NormalizedDocument(
            source_type="x",
            source_url=source_url,
            canonical_url=raw["canonical_url"] or source_url,
            external_id=raw["tweet_id"],
            title=derive_title(raw["text"], raw["tweet_id"]),
            author=raw["display_name"] or raw["screen_name"] or "unknown",
            author_handle=raw["screen_name"] or "unknown",
            created_at=raw["created_at"],
            language=raw["language"],
            text=raw["text"],
            markdown="",
            summary=None,
            assets=raw.get("media", []),
            metadata={
                "platform": "x",
                "tweet_id": raw["tweet_id"],
                "screen_name": raw["screen_name"],
                "display_name": raw["display_name"],
                "stats": raw["stats"],
                "raw_source": "fxtwitter",
            },
            lineage={
                "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "connector": "x",
                "backend": "fxtwitter",
                "runtime_version": "0.1.0",
            },
        )
        doc.markdown = render_markdown(doc)
        return doc
