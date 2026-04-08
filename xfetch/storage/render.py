from __future__ import annotations

import html
import json
from pathlib import Path
import re
import shutil

_IMAGE_LINE_RE = re.compile(r"^!\[(?P<alt>.*?)\]\((?P<src>[^)]+)\)$")
_HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+(?P<text>.+)$")


def _copy_site_assets(bundle_dir: Path, page_dir: Path) -> None:
    source_assets = bundle_dir / "assets"
    if not source_assets.exists():
        return
    target_assets = page_dir / "assets"
    if target_assets.exists():
        shutil.rmtree(target_assets)
    shutil.copytree(source_assets, target_assets)



def _site_asset_path(src: str) -> str:
    if src.startswith("assets/"):
        return src
    return src


def _flush_paragraph(lines: list[str], chunks: list[str]) -> None:
    if not lines:
        return
    paragraph = html.escape("\n".join(lines)).replace("\n", "<br>\n")
    chunks.append(f"<p>{paragraph}</p>")
    lines.clear()


def _render_markdown_body(markdown: str) -> str:
    chunks: list[str] = []
    paragraph_lines: list[str] = []
    code_lines: list[str] = []
    in_code_block = False

    for line in markdown.splitlines():
        if line.startswith("```"):
            _flush_paragraph(paragraph_lines, chunks)
            if in_code_block:
                code_html = html.escape("\n".join(code_lines))
                chunks.append(f"<pre><code>{code_html}</code></pre>")
                code_lines.clear()
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            _flush_paragraph(paragraph_lines, chunks)
            continue

        image_match = _IMAGE_LINE_RE.match(stripped)
        if image_match:
            _flush_paragraph(paragraph_lines, chunks)
            alt = html.escape(image_match.group("alt"))
            src = html.escape(_site_asset_path(image_match.group("src")))
            chunks.append(f'<p><img src="{src}" alt="{alt}"></p>')
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            _flush_paragraph(paragraph_lines, chunks)
            level = len(heading_match.group("level"))
            text = html.escape(heading_match.group("text"))
            chunks.append(f"<h{level}>{text}</h{level}>")
            continue

        paragraph_lines.append(line)

    _flush_paragraph(paragraph_lines, chunks)
    if code_lines:
        code_html = html.escape("\n".join(code_lines))
        chunks.append(f"<pre><code>{code_html}</code></pre>")
    return "\n".join(chunks)


def render_bundle_page(bundle_dir: Path, site_root: Path, public_url: str | None = None) -> Path:
    bundle_dir = Path(bundle_dir)
    site_root = Path(site_root)
    document = json.loads((bundle_dir / "document.json").read_text(encoding="utf-8"))
    slug = bundle_dir.name
    page_path = site_root / "d" / slug / "index.html"
    page_path.parent.mkdir(parents=True, exist_ok=True)

    title = html.escape(document.get("title") or slug)
    canonical_url = document.get("canonical_url") or ""
    author_handle = document.get("author_handle") or "unknown"
    created_at = document.get("created_at") or "unknown"
    markdown_source = document.get("markdown") or ""
    if markdown_source:
        rendered_body = _render_markdown_body(markdown_source)
    else:
        body_source = document.get("text") or ""
        escaped_body = html.escape(body_source).replace("\n", "<br>\n")
        rendered_body = f"<div>{escaped_body}</div>"
    _copy_site_assets(bundle_dir, page_path.parent)
    canonical_tag = f'<link rel="canonical" href="{html.escape(public_url)}">\n' if public_url else ""

    rendered = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{title}</title>\n"
        f"  {canonical_tag}"
        "</head>\n"
        "<body>\n"
        f"  <h1>{title}</h1>\n"
        f'  <p>Source: <a href="{html.escape(canonical_url)}">{html.escape(canonical_url)}</a></p>\n'
        f"  <p>Author: @{html.escape(author_handle)}</p>\n"
        f"  <p>Created: {html.escape(created_at)}</p>\n"
        f"  <div>{rendered_body}</div>\n"
        "</body>\n"
        "</html>\n"
    )
    page_path.write_text(rendered, encoding="utf-8")
    return page_path
