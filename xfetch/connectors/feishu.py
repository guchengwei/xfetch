from __future__ import annotations

import json
import re
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, urlunsplit
from urllib.request import Request

from xfetch.connectors.base import BaseConnector
from xfetch.models import NormalizedDocument
from xfetch.net import safe_urlopen as urlopen


_FEISHU_URL_RE = re.compile(
    r"^https?://(?:[a-z0-9-]+\.)*(?:feishu\.cn|larksuite\.com|larkoffice\.com)/(?:wiki|docx)/[A-Za-z0-9]+",
    re.IGNORECASE,
)
_WIKI_TOKEN_RE = re.compile(r"/wiki/([A-Za-z0-9]+)")
_DOCX_TOKEN_RE = re.compile(r"/docx/([A-Za-z0-9]+)")
_DOCX_OBJ_TYPE = 22
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}
_UNPRESERVED = {"image": "images", "file": "files", "sheet": "sheets"}


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _canonical(url: str) -> str:
    parsed = urlparse(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _host_handle(url: str) -> str:
    host = (urlparse(url).hostname or "feishu").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _request(url: str, referer: str | None = None) -> Request:
    headers = dict(_HEADERS)
    if referer:
        headers["Referer"] = referer
    return Request(url, headers=headers)


def _read(url: str, cookie_jar, referer: str | None = None) -> tuple[bytes, str]:
    try:
        with urlopen(_request(url, referer), timeout=15, cookie_jar=cookie_jar) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raise ValueError(f"Feishu document is not publicly readable (HTTP {exc.code})") from exc


def _read_json(url: str, cookie_jar, referer: str | None = None) -> dict:
    raw, _content_type = _read(url, cookie_jar, referer)
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ValueError("Feishu document response was not JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Feishu document response was not JSON")
    code = payload.get("code")
    if code not in (0, None):
        detail = payload.get("msg") or code
        raise ValueError(f"Feishu document is not publicly readable ({detail})")
    return payload


def _inline_text(data: dict) -> str:
    payload = ((data.get("text") or {}).get("initialAttributedTexts") or {}).get("text") or {}
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""

    def sort_key(key: str):
        return (0, int(key)) if str(key).isdigit() else (1, str(key))

    return "".join(str(payload[key]) for key in sorted(payload, key=sort_key)).strip()


def _join_labels(labels: list[str]) -> str:
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def _render_table(data: dict, block_map: dict) -> str:
    rows = data.get("rows_id") or []
    cols = data.get("columns_id") or []
    cells = data.get("cell_set") or {}
    if not rows or not cols:
        return ""
    rendered = []
    for row_id in rows:
        values = []
        for col_id in cols:
            cell = cells.get(f"{row_id}{col_id}") or {}
            block_id = cell.get("block_id") if isinstance(cell, dict) else None
            text = _deep_text(block_id, block_map) if block_id else ""
            values.append(text.replace("|", "\\|").replace("\n", " "))
        rendered.append("| " + " | ".join(values) + " |")
    if not rendered:
        return ""
    separator = "| " + " | ".join("---" for _ in cols) + " |"
    return "\n".join([rendered[0], separator, *rendered[1:]])


def _deep_text(block_id: str, block_map: dict, seen: set[str] | None = None) -> str:
    if seen is None:
        seen = set()
    if not block_id or block_id in seen or block_id not in block_map:
        return ""
    seen.add(block_id)
    data = block_map[block_id].get("data") or {}
    parts = []
    own = _inline_text(data)
    if own:
        parts.append(own)
    for child in data.get("children") or []:
        child_text = _deep_text(child, block_map, seen)
        if child_text:
            parts.append(child_text)
    return " ".join(parts).strip()


def _render_list(kind: str, ids: list[str], block_map: dict, skipped: set[str], seen: set[str]) -> str:
    lines = []
    number = 0
    for block_id in ids:
        data = (block_map.get(block_id) or {}).get("data") or {}
        text = _inline_text(data)
        if kind == "bullet":
            line = f"- {text}".rstrip()
        else:
            if str(data.get("seq")) == "1" or number == 0:
                number = 1
            else:
                number += 1
            line = f"{number}. {text}".rstrip()
        child_body = _render_sequence(data.get("children") or [], block_map, skipped, seen)
        if child_body:
            indented = "\n".join(f"  {child_line}" for child_line in child_body.splitlines())
            line = f"{line}\n{indented}"
        lines.append(line)
    return "\n".join(lines)


def _render_block(block_id: str, block_map: dict, skipped: set[str], seen: set[str]) -> str:
    data = (block_map.get(block_id) or {}).get("data") or {}
    kind = str(data.get("type") or "")
    if kind in {"page", "table_cell"}:
        return ""
    if kind.startswith("heading") and kind[7:].isdigit():
        level = min(int(kind[7:]), 6)
        text = _inline_text(data)
        return f"{'#' * level} {text}".rstrip() if text else ""
    if kind == "text":
        return _inline_text(data)
    if kind == "divider":
        return "---"
    if kind == "table":
        return _render_table(data, block_map)
    if kind == "view":
        return _render_sequence(data.get("children") or [], block_map, skipped, seen)
    if kind == "file":
        skipped.add(kind)
        name = " ".join(str(((data.get("file") or {}).get("name")) or "attachment").split()) or "attachment"
        return f"File: {name}"
    if kind in _UNPRESERVED:
        skipped.add(kind)
        return ""
    text = _inline_text(data)
    nested = _render_sequence(data.get("children") or [], block_map, skipped, seen)
    if text and nested:
        return f"{text}\n\n{nested}"
    if text or nested:
        return text or nested
    if kind:
        skipped.add(kind)
    return ""


def _render_sequence(ids: list, block_map: dict, skipped: set[str], seen: set[str] | None = None) -> str:
    if seen is None:
        seen = set()
    parts: list[str] = []
    index = 0
    while index < len(ids):
        block_id = ids[index]
        if block_id in seen or block_id not in block_map:
            index += 1
            continue
        data = block_map[block_id].get("data") or {}
        kind = data.get("type")
        if kind in {"ordered", "bullet"}:
            group = []
            while index < len(ids):
                candidate_id = ids[index]
                if candidate_id in seen or candidate_id not in block_map:
                    break
                candidate = block_map[candidate_id].get("data") or {}
                if candidate.get("type") != kind:
                    break
                seen.add(candidate_id)
                group.append(candidate_id)
                index += 1
            rendered = _render_list(kind, group, block_map, skipped, seen)
            if rendered:
                parts.append(rendered)
            continue
        seen.add(block_id)
        rendered = _render_block(block_id, block_map, skipped, seen)
        if rendered:
            parts.append(rendered)
        index += 1
    return "\n\n".join(parts)


def _root_children(data: dict, block_map: dict) -> list:
    for block in block_map.values():
        payload = block.get("data") or {}
        if payload.get("type") == "page":
            return list(payload.get("children") or [])
    sequence = data.get("block_sequence") or []
    return [block_id for block_id in sequence if (block_map.get(block_id) or {}).get("data", {}).get("type") != "page"]


class FeishuConnector(BaseConnector):
    def can_handle(self, url: str) -> bool:
        return bool(_FEISHU_URL_RE.match(url))

    def fetch(self, url: str) -> NormalizedDocument:
        parsed = urlparse(url)
        wiki = _WIKI_TOKEN_RE.search(parsed.path or "")
        docx = _DOCX_TOKEN_RE.search(parsed.path or "")
        if not wiki and not docx:
            raise ValueError(f"Cannot extract Feishu document id from {url}")
        jar = CookieJar()
        _read(url, jar)
        origin = _origin(url)
        node_title = None
        if wiki:
            node = _read_json(
                f"{origin}/space/api/wiki/v2/tree/get_node/?{urlencode({'wiki_token': wiki.group(1)})}",
                jar,
                referer=url,
            )
            node_data = node.get("data") or {}
            obj_type = node_data.get("obj_type")
            if obj_type not in {_DOCX_OBJ_TYPE, str(_DOCX_OBJ_TYPE)}:
                raise ValueError(f"Feishu wiki node is not a document (obj_type {obj_type})")
            obj_token = node_data.get("obj_token")
            node_title = node_data.get("title")
            external_id = wiki.group(1)
        else:
            obj_token = docx.group(1)
            external_id = obj_token
        if not obj_token:
            raise ValueError("Feishu document is not publicly readable (missing document token)")
        client = _read_json(
            f"{origin}/space/api/docx/pages/client_vars?{urlencode({'id': obj_token})}",
            jar,
            referer=url,
        )
        data = client.get("data") or {}
        block_map = data.get("block_map") or {}
        if not isinstance(block_map, dict) or not block_map:
            raise ValueError("Feishu document did not include readable content")
        meta_map = data.get("meta_map") or {}
        meta = meta_map.get(obj_token) if isinstance(meta_map, dict) else None
        if not isinstance(meta, dict) and isinstance(meta_map, dict) and meta_map:
            meta = next(iter(meta_map.values()))
        if not isinstance(meta, dict):
            meta = {}
        title = meta.get("title") or node_title or external_id
        skipped: set[str] = set()
        body = _render_sequence(_root_children(data, block_map), block_map, skipped)
        text = body or title
        author = _host_handle(url)
        canonical_url = _canonical(url)
        markdown = f"# {title}\n\n- Source: {canonical_url}\n- Author: {author}\n\n{body}\n"
        metadata = {"platform": "feishu", "obj_token": obj_token}
        if data.get("has_more"):
            skipped.add("truncated")
        labels = [_UNPRESERVED[kind] for kind in ("image", "file", "sheet") if kind in skipped]
        limitations = []
        if labels:
            limitations.append(f"Feishu {_join_labels(labels)} were not preserved.")
        if "truncated" in skipped:
            limitations.append("Feishu returned a truncated document snapshot.")
        other = sorted(kind for kind in skipped if kind not in _UNPRESERVED and kind != "truncated")
        if other:
            limitations.append("Some Feishu blocks were not converted.")
        capture_status = "partial" if limitations else "complete"
        if limitations:
            metadata["capture_limitation"] = " ".join(limitations)
        return NormalizedDocument(
            source_type="feishu",
            source_url=url,
            canonical_url=canonical_url,
            external_id=external_id,
            title=title,
            author=author,
            author_handle=author,
            created_at=meta.get("create_time") if isinstance(meta.get("create_time"), str) else None,
            language=None,
            text=text,
            markdown=markdown,
            summary=None,
            assets=[],
            metadata=metadata,
            lineage={"connector": "feishu", "runtime_version": "0.2.2"},
            capture_status=capture_status,
            content_kinds=["text", "metadata"],
        )
