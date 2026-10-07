from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_BILIBILI_URL_RE = re.compile(r"^https?://(?:www\.)?(?:bilibili\.com|b23\.tv)/", re.IGNORECASE)
_BV_RE = re.compile(r"(BV[0-9A-Za-z]+)")
_API_URL = "https://api.bilibili.com/x/web-interface/view"
_PLAYER_API_URL = "https://api.bilibili.com/x/player/v2"
_OPUS_API_URL = "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/detail"
_OPUS_RE = re.compile(r"/opus/(\d+)")
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


def _extract_opus_id(url: str) -> str | None:
    match = _OPUS_RE.search(urlparse(url).path)
    return match.group(1) if match else None


def _resolve_b23_url(url: str) -> str:
    request = Request(url, headers=_HEADERS)
    with urlopen(request, timeout=10) as response:
        return response.geturl()


def _fetch_json(url: str, timeout: int = 10, cookie_jar=None) -> tuple[dict, str]:
    request = Request(url, headers=_HEADERS)
    kwargs = {"timeout": timeout}
    if cookie_jar is not None:
        kwargs["cookie_jar"] = cookie_jar
    with urlopen(request, **kwargs) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
        content_type = response.headers.get("Content-Type", "application/json")
    return payload, content_type


def _prime_bilibili_cookies(url: str, cookie_jar) -> None:
    request = Request(url, headers=_HEADERS)
    try:
        with urlopen(request, timeout=10, cookie_jar=cookie_jar) as response:
            response.read()
    except (OSError, ValueError):
        return


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


def _https_url(value: str) -> str:
    if value.startswith("//"):
        return "https:" + value
    if value.startswith("http://"):
        return "https://" + value[len("http://"):]
    return value


def _opus_words(nodes) -> str:
    parts: list[str] = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        word = node.get("word") or {}
        if isinstance(word, dict) and word.get("words"):
            parts.append(str(word["words"]))
            continue
        rich = node.get("rich") or {}
        if not isinstance(rich, dict):
            continue
        label = str(rich.get("text") or "").strip()
        jump = _https_url(str(rich.get("jump_url") or "").strip())
        if label and jump.startswith("https://") and label != jump:
            parts.append(f"[{label}]({jump})")
        elif label:
            parts.append(label)
        elif jump.startswith("https://"):
            parts.append(jump)
    return "".join(parts).strip()


def _render_opus_paragraphs(paragraphs: list) -> tuple[str, str, list[dict], bool]:
    chunks: list[str] = []
    plain: list[str] = []
    assets: list[dict] = []
    skipped = False
    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            skipped = True
            continue
        kind = paragraph.get("para_type")
        if kind in {1, 4}:
            nodes = (paragraph.get("text") or {}).get("nodes") or []
            text = _opus_words(nodes)
            if any(isinstance(node, dict) and (node.get("formula") or node.get("user")) for node in nodes):
                skipped = True
            if not text:
                if any(isinstance(node, dict) and node.get("formula") for node in nodes):
                    skipped = True
                continue
            font = ""
            if nodes and isinstance(nodes[0], dict):
                font = str(((nodes[0].get("word") or {}).get("font_level")) or "")
            rendered = f"## {text}" if font == "xxLarge" else text
            chunks.append(rendered)
            plain.append(text)
        elif kind == 2:
            pics = (paragraph.get("pic") or {}).get("pics") or []
            images = []
            for pic in pics:
                if not isinstance(pic, dict):
                    continue
                image_url = _https_url(str(pic.get("url") or ""))
                if not image_url.startswith("https://"):
                    continue
                images.append(f"![]({image_url})")
                assets.append({"url": image_url, "type": "image", "width": pic.get("width"), "height": pic.get("height")})
            if images:
                chunks.append("\n\n".join(images))
            elif pics:
                skipped = True
        elif kind == 5:
            listing = paragraph.get("list") or {}
            ordered = listing.get("theme") == "arabic_num" or listing.get("style") == 1
            try:
                number = int(listing.get("start") or 1)
            except (TypeError, ValueError):
                number = 1
            lines = []
            for item in listing.get("items") or []:
                if not isinstance(item, dict):
                    skipped = True
                    continue
                text = _opus_words(item.get("nodes"))
                if ordered:
                    lines.append(f"{number}. {text}".rstrip())
                    number += 1
                else:
                    lines.append(f"- {text}".rstrip())
            if lines:
                chunks.append("\n".join(lines))
                plain.append("\n".join(lines))
            else:
                skipped = True
        else:
            skipped = True
    markdown = "\n\n".join(chunk for chunk in chunks if chunk.strip())
    text = "\n\n".join(part for part in plain if part.strip())
    return markdown, text, assets, skipped


def _fetch_opus_document(url: str, opus_id: str) -> NormalizedDocument:
    jar = CookieJar()
    _prime_bilibili_cookies(url, jar)
    query_url = f"{_OPUS_API_URL}?{urlencode({'id': opus_id, 'features': 'html'})}"
    payload, content_type = _fetch_json(query_url, cookie_jar=jar)
    code = payload.get("code")
    if code != 0:
        message = payload.get("message") or code
        if code == -352:
            raise ValueError(f"Bilibili risk control blocked opus {opus_id} ({message})")
        raise ValueError(f"Bilibili API error: {message}")
    item = (payload.get("data") or {}).get("item") or {}
    modules = item.get("modules") or []
    if isinstance(modules, dict):
        modules = [modules]
    author_module = {}
    paragraphs: list = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        if module.get("module_author"):
            author_module = module["module_author"] or {}
        content = module.get("module_content") or {}
        if content.get("paragraphs"):
            paragraphs = content["paragraphs"]
    basic = item.get("basic") or {}
    title = basic.get("title") or f"Bilibili opus {opus_id}"
    author = author_module.get("name") or "unknown"
    created_at = None
    pub_ts = author_module.get("pub_ts")
    if pub_ts:
        try:
            created_at = datetime.fromtimestamp(int(pub_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError, OSError):
            created_at = None
    body, text, assets, skipped = _render_opus_paragraphs(paragraphs)
    if not text and not assets:
        raise ValueError(f"Bilibili opus {opus_id} did not include article content")
    canonical_url = f"https://www.bilibili.com/opus/{opus_id}"
    markdown = f"# {title}\n\n- Source: {canonical_url}\n- Author: {author}\n\n{body}\n"
    content_kinds = ["text", "metadata"] + (["images"] if assets else [])
    metadata = {"platform": "bilibili", "content_type": content_type, "opus_id": opus_id}
    capture_status = "complete"
    if skipped:
        capture_status = "partial"
        metadata["capture_limitation"] = "Some Bilibili opus blocks were not converted."
    return NormalizedDocument(
        source_type="bilibili",
        source_url=url,
        canonical_url=canonical_url,
        external_id=opus_id,
        title=title,
        author=author,
        author_handle=_slugify(author),
        created_at=created_at,
        language="zh",
        text=text or title,
        markdown=markdown,
        summary=None,
        assets=assets,
        metadata=metadata,
        lineage={"connector": "bilibili", "runtime_version": "0.2.4"},
        capture_status=capture_status,
        content_kinds=content_kinds,
    )


class BilibiliConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return bool(_BILIBILI_URL_RE.match(url))

    def fetch(self, url: str) -> NormalizedDocument:
        opus_id = _extract_opus_id(url)
        if opus_id:
            return _fetch_opus_document(url, opus_id)
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
            lineage={"connector": "bilibili", "runtime_version": "0.2.4"},
            capture_status=capture_status,
            content_kinds=content_kinds,
        )
