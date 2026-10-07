from __future__ import annotations

from datetime import datetime, timezone
import re
from urllib.parse import urlparse

from xfetch.article_html import visual_capture_status
from xfetch.backends.fxtwitter import (
    fetch_fxtwitter_json,
    fetch_oembed_json,
    fetch_vxtwitter_json,
    parse_fxtwitter_payload,
    parse_oembed_payload,
    status_text_is_thin,
)
from xfetch.backends.x_guest import fetch_guest_status_payload, fetch_x_api_status_payload, x_api_configured
from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument, derive_title, render_markdown


_X_URL_RE = re.compile(r"^https?://(?:www\.)?(?:x\.com|twitter\.com)/[^/]+/status/\d+", re.IGNORECASE)


def is_x_url(url: str) -> bool:
    return bool(_X_URL_RE.match(url))


def _handle_from_url(url: str) -> str:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) >= 3 and parts[1] == "status":
        return parts[0]
    return ""


class XConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return is_x_url(url)

    def fetch(self, url: str) -> NormalizedDocument:
        failures: list[tuple[str, Exception]] = []
        for backend, load in _status_loaders():
            if backend == "x-api" and not x_api_configured():
                continue
            try:
                raw = load(url)
            except Exception as exc:
                failures.append((backend, exc))
                continue
            if status_text_is_thin(str(raw.get("text") or "")):
                failures.append((backend, ValueError("X response was thin or truncated")))
                continue
            status = "partial" if raw.get("has_unpreserved_video") or backend == "oembed" else "complete"
            doc = self._normalize_raw(url, raw, backend=backend, capture_status=status)
            if failures:
                doc.metadata["fallback_from"] = failures[0][0]
                doc.metadata["fallback_error"] = type(failures[0][1]).__name__
            return doc
        if not failures:
            raise ValueError("X post could not be captured")
        detail = "; ".join(f"{name}: {type(exc).__name__}: {exc}" for name, exc in failures)
        raise ValueError(f"X post could not be captured ({detail})") from failures[-1][1]

    def normalize_payload(self, source_url: str, payload: dict) -> NormalizedDocument:
        raw = parse_fxtwitter_payload(payload)
        status = "partial" if raw.get("has_unpreserved_video") else "complete"
        return self._normalize_raw(source_url, raw, backend="fxtwitter", capture_status=status)

    def _normalize_raw(self, source_url: str, raw: dict, backend: str, capture_status: str) -> NormalizedDocument:
        text = raw["text"]
        screen_name = raw["screen_name"] or _handle_from_url(source_url)
        metadata = {
            "platform": "x",
            "tweet_id": raw["tweet_id"],
            "screen_name": screen_name,
            "display_name": raw["display_name"],
            "stats": raw["stats"],
            "raw_source": backend,
        }
        if raw.get("has_unpreserved_video"):
            metadata["unpreserved_media"] = ["video"]

        doc = NormalizedDocument(
            source_type="x",
            source_url=source_url,
            canonical_url=raw["canonical_url"] or source_url,
            external_id=raw["tweet_id"],
            title=derive_title(text, raw["tweet_id"]),
            author=raw["display_name"] or screen_name or "unknown",
            author_handle=screen_name or "unknown",
            created_at=raw["created_at"],
            language=raw["language"],
            text=text,
            markdown="",
            summary=None,
            assets=raw.get("assets", []),
            metadata=metadata,
            lineage={"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "connector": "x", "backend": backend, "runtime_version": "0.2.4"},
            capture_status=capture_status,
            content_kinds=["text", "images"] if raw.get("assets") else ["text"],
        )
        doc.markdown = render_markdown(doc, body=raw.get("markdown") or text)
        image_urls = [
            str(asset.get("url") or "")
            for asset in doc.assets
            if isinstance(asset, dict) and asset.get("url") and asset.get("type", "image") == "image"
        ]
        doc.capture_status = visual_capture_status(
            doc.markdown,
            image_urls,
            has_body=bool((text or "").strip() or (doc.markdown or "").strip()),
            status=doc.capture_status,
        )
        return doc


def _status_loaders():
    return (
        ("fxtwitter", lambda url: parse_fxtwitter_payload(fetch_fxtwitter_json(url))),
        ("vxtwitter", lambda url: parse_fxtwitter_payload(fetch_vxtwitter_json(url))),
        ("x-guest", lambda url: parse_fxtwitter_payload(fetch_guest_status_payload(url))),
        ("x-api", lambda url: parse_fxtwitter_payload(fetch_x_api_status_payload(url))),
        ("oembed", lambda url: parse_oembed_payload(fetch_oembed_json(url), source_url=url)),
    )
