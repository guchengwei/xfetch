from __future__ import annotations

from html import unescape
import json
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_YOUTUBE_HOST_RE = re.compile(r"(?:^|\.)(?:youtube\.com|youtu\.be)$", re.IGNORECASE)
_PLAYER_RESPONSE_RE = re.compile(
    r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*|window\["ytInitialPlayerResponse"\]\s*=\s*'
)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def _extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "youtu.be" in host:
        value = parsed.path.strip("/")
        return value or None
    qs = parse_qs(parsed.query)
    if qs.get("v"):
        return qs["v"][0]
    match = re.search(r"/(?:embed|shorts|live)/([^/?#]+)", parsed.path)
    return match.group(1) if match else None


def _fetch_html(url: str) -> tuple[str, str, str]:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    return html, final_url, content_type


def _extract_meta(html: str, attr_name: str, attr_value: str) -> str | None:
    pattern = rf'<meta\s+(?:name|property)=["\']{re.escape(attr_value)}["\']\s+content=["\']([^"\']*)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    return unescape(match.group(1).strip()) if match else None


def _extract_player_response(html: str) -> dict | None:
    match = _PLAYER_RESPONSE_RE.search(html)
    if not match:
        return None
    start = html.find("{", match.end())
    if start < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(html[start:])[0]
    except json.JSONDecodeError:
        return None


def _caption_tracks(player_response: dict | None) -> list[dict]:
    if not player_response:
        return []
    return (
        player_response.get("captions", {})
        .get("playerCaptionsTracklistRenderer", {})
        .get("captionTracks", [])
    ) or []


def _select_caption_track(tracks: list[dict]) -> dict | None:
    if not tracks:
        return None
    return next((track for track in tracks if track.get("kind") != "asr"), tracks[0])


def _fetch_transcript(track: dict) -> str:
    base_url = track.get("baseUrl")
    if not base_url:
        raise ValueError("caption track has no baseUrl")
    separator = "&" if "?" in base_url else "?"
    request = Request(f"{base_url}{separator}fmt=json3", headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=15) as response:
        body = response.read().decode("utf-8", errors="replace")
    if not body.strip():
        raise ValueError("empty caption response")

    payload = json.loads(body)
    lines = []
    for event in payload.get("events", []):
        text = "".join(str(segment.get("utf8", "")) for segment in event.get("segs") or [])
        text = unescape(text).strip()
        if text:
            lines.append(text)
    transcript = "\n".join(lines).strip()
    if not transcript:
        raise ValueError("caption response has no transcript text")
    return transcript


class YouTubeConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        parsed = urlparse(url)
        return bool(
            parsed.scheme in {"http", "https"}
            and _YOUTUBE_HOST_RE.search(parsed.netloc)
            and _extract_video_id(url)
        )

    def fetch(self, url: str) -> NormalizedDocument:
        html, canonical_url, content_type = _fetch_html(url)
        video_id = _extract_video_id(canonical_url) or _extract_video_id(url)
        if not video_id:
            raise ValueError(f"Cannot extract YouTube video ID from {url}")
        title = _extract_meta(html, "property", "og:title") or f"YouTube video {video_id}"
        author = _extract_meta(html, "name", "author") or "unknown"
        description = _extract_meta(html, "property", "og:description") or title
        image = _extract_meta(html, "property", "og:image")
        author_handle = _slugify(author)
        assets = [{"url": image, "type": "image"}] if image else []

        tracks = _caption_tracks(_extract_player_response(html))
        track = _select_caption_track(tracks)
        transcript = None
        transcript_error = None
        if track:
            try:
                transcript = _fetch_transcript(track)
            except (OSError, ValueError) as exc:
                transcript_error = str(exc)

        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Author: {author}\n\n{description}\n"
        text = description
        if transcript:
            markdown += f"\n## Transcript\n\n{transcript}\n"
            text = f"{description}\n\n{transcript}"

        metadata = {
            "platform": "youtube",
            "content_type": content_type,
            "has_transcript": bool(transcript),
            "transcript_available": bool(tracks),
        }
        if track:
            metadata["transcript_language"] = track.get("languageCode")
            metadata["transcript_kind"] = "auto" if track.get("kind") == "asr" else "manual"
        if transcript_error:
            metadata["transcript_capture_error"] = transcript_error

        content_kinds = ["metadata", "thumbnail"] if image else ["metadata"]
        capture_status = "metadata_only"
        if transcript:
            capture_status = "partial"
            content_kinds = ["text", "transcript", "metadata"] + (["thumbnail"] if image else [])
            metadata["unpreserved_media"] = ["video"]

        return NormalizedDocument(
            source_type="youtube",
            source_url=url,
            canonical_url=canonical_url,
            external_id=video_id,
            title=title,
            author=author,
            author_handle=author_handle,
            created_at=None,
            language=track.get("languageCode") if transcript and track else None,
            text=text,
            markdown=markdown,
            summary=None,
            assets=assets,
            metadata=metadata,
            lineage={"connector": "youtube", "runtime_version": "0.2.3"},
            capture_status=capture_status,
            content_kinds=content_kinds,
        )
