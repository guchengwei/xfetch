from __future__ import annotations

import html
import json
from pathlib import Path


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
    body_source = document.get("text") or document.get("markdown") or ""
    text = html.escape(body_source).replace("\n", "<br>\n")
    canonical_tag = f'<link rel="canonical" href="{html.escape(public_url)}">\n' if public_url else ""

    rendered = (
        "<!DOCTYPE html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <title>{title}</title>\n"
        f"  {canonical_tag}"
        "</head>\n"
        "<body>\n"
        f"  <h1>{title}</h1>\n"
        f"  <p>Source: <a href=\"{html.escape(canonical_url)}\">{html.escape(canonical_url)}</a></p>\n"
        f"  <p>Author: @{html.escape(author_handle)}</p>\n"
        f"  <p>Created: {html.escape(created_at)}</p>\n"
        f"  <div>{text}</div>\n"
        "</body>\n"
        "</html>\n"
    )
    page_path.write_text(rendered, encoding="utf-8")
    return page_path
