from __future__ import annotations

import json
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_BILIBILI_URL_RE = re.compile(r"^https?://(?:www\.)?(?:bilibili\.com|b23\.tv)/", re.IGNORECASE)
_BV_RE = re.compile(r"(BV[0-9A-Za-z]+)")
_API_URL = "https://api.bilibili.com/x/web-interface/view"
_PLAYER_API_URL = "https://api.bilibili.com/x/player/v2"
_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.bilibili.com/",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def _extract_bvid(url: str) -> str | None:
    match = _BV_RE.search(url)
    return match.group(1) if match else None


def _resolve_b23_url(url: str) -> str:
    request = Request(url, headers=_HEADERS)
    with urlopen(request, timeout=10) as response:
        return response.geturl()


def _fetch_json(url: str, timeout: int = 10) -> tuple[dict, str]:
    request = Request(url, headers=_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
        content_type = response.headers.get("Content-Type", "application/json")
    return payload, content_type


def _fetch_api_payload(bvid: str) -> tuple[dict, str]:
    query_url = f"{_API_URL}?{urlencode({'bvid': bvid})}"
    return _fetch_json(query_url)


def _fetch_subtitle_track(bvid: str, cid: int | str) -> tuple[dict | None, bool]:
    query_url = f"{_PLAYER_API_URL}?{urlencode({'bvid': bvid, 'cid': cid})}"
    payload, _content_type = _fetch_json(query_url)
    if payload.get("code") != 0:
        raise ValueError(f"Bilibili player API error: {payload.get('message')}")
    subtitle = payload.get("data", {}).get("subtitle", {}) or {}
    tracks = subtitle.get("subtitles", []) or []
    track = next((item for item in tracks if item.get("subtitle_url")), None)
    return track, bool(subtitle.get("need_login_subtitle"))


def _fetch_subtitle_text(track: dict) -> str:
    subtitle_url = track.get("subtitle_url")
    if not subtitle_url:
        raise ValueError("subtitle track has no subtitle_url")
    if subtitle_url.startswith("//"):
        subtitle_url = f"https:{subtitle_url}"
    payload, _content_type = _fetch_json(subtitle_url)
    transcript = "\n".join(
        str(item.get("content", "")).strip()
        for item in payload.get("body", [])
        if str(item.get("content", "")).strip()
    ).strip()
    if not transcript:
        raise ValueError("subtitle response has no transcript text")
    return transcript


class BilibiliConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return bool(_BILIBILI_URL_RE.match(url))

    def fetch(self, url: str) -> NormalizedDocument:
        resolved_url = url
        if urlparse(url).hostname in {"b23.tv", "www.b23.tv"} and not _extract_bvid(url):
            resolved_url = _resolve_b23_url(url)
        bvid = _extract_bvid(resolved_url)
        if not bvid:
            raise ValueError(f"Cannot extract Bilibili BV ID from {url}")

        payload, content_type = _fetch_api_payload(bvid)
        if payload.get("code") != 0:
            raise ValueError(f"Bilibili API error: {payload.get('message')}")
        data = payload.get("data", {})
        title = data.get("title") or f"Bilibili video {bvid}"
        description = data.get("desc") or title
        author = data.get("owner", {}).get("name") or "unknown"
        cover = data.get("pic")
        canonical_url = f"https://www.bilibili.com/video/{bvid}"
        assets = [{"url": cover, "type": "image"}] if cover else []

        track = None
        transcript = None
        transcript_error = None
        transcript_requires_login = False
        cid = data.get("cid")
        if cid:
            try:
                track, transcript_requires_login = _fetch_subtitle_track(bvid, cid)
                if track:
                    transcript = _fetch_subtitle_text(track)
            except (OSError, ValueError) as exc:
                transcript_error = str(exc)

        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Author: {author}\n\n{description}\n"
        text = description
        if transcript:
            markdown += f"\n## Transcript\n\n{transcript}\n"
            text = f"{description}\n\n{transcript}"

        metadata = {
            "platform": "bilibili",
            "content_type": content_type,
            "duration": data.get("duration", 0),
            "view_count": data.get("stat", {}).get("view", 0),
            "has_transcript": bool(transcript),
            "transcript_available": bool(track),
        }
        if cid:
            metadata["cid"] = cid
        if track:
            metadata["transcript_language"] = track.get("lan")
            metadata["transcript_language_name"] = track.get("lan_doc")
        if transcript_requires_login:
            metadata["transcript_requires_login"] = True
        if transcript_error:
            metadata["transcript_capture_error"] = transcript_error

        content_kinds = ["metadata", "thumbnail"] if cover else ["metadata"]
        capture_status = "metadata_only"
        if transcript:
            capture_status = "partial"
            content_kinds = ["text", "transcript", "metadata"] + (["thumbnail"] if cover else [])
            metadata["unpreserved_media"] = ["video"]

        return NormalizedDocument(
            source_type="bilibili",
            source_url=url,
            canonical_url=canonical_url,
            external_id=bvid,
            title=title,
            author=author,
            author_handle=_slugify(author),
            created_at=None,
            language=track.get("lan") if transcript and track else "zh",
            text=text,
            markdown=markdown,
            summary=None,
            assets=assets,
            metadata=metadata,
            lineage={"connector": "bilibili", "runtime_version": "0.2.1"},
            capture_status=capture_status,
            content_kinds=content_kinds,
        )
