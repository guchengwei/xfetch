import json

from xfetch.storage.render import _render_markdown_body, render_bundle_page


def test_render_bundle_page_writes_index_html(tmp_path):
    bundle_dir = tmp_path / "2026-03" / "x-123-alice"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "document.json").write_text(
        '{"title":"Hello","canonical_url":"https://x.com/alice/status/123","author_handle":"alice","created_at":"2026-03-31T00:00:00Z","text":"hello world"}',
        encoding="utf-8",
    )
    out_dir = tmp_path / "site"
    page = render_bundle_page(bundle_dir, out_dir, public_url="https://guchengwei.github.io/link-vault/d/x-123-alice/")
    html = page.read_text(encoding="utf-8")
    assert page == out_dir / "d" / "x-123-alice" / "index.html"
    assert "<title>Hello</title>" in html
    assert "rel=\"canonical\"" in html


def test_render_bundle_page_renders_common_markdown(tmp_path):
    bundle_dir = tmp_path / "2026-03" / "x-123-alice"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "assets").mkdir()
    (bundle_dir / "assets" / "image-01.jpg").write_bytes(b"img")
    markdown = "# Hello\n\n1. first\n2. [second](https://example.com/two)\n\n- alpha\n- beta\n\n> quoted\n\n![](assets/image-01.jpg)\n\n```python\nprint(123)\n```\n"
    (bundle_dir / "document.json").write_text(
        json.dumps({"title": "Hello", "canonical_url": "https://x.com/alice/status/123", "author_handle": "alice", "created_at": "2026-03-31T00:00:00Z", "text": "plain fallback", "markdown": markdown}),
        encoding="utf-8",
    )
    out_dir = tmp_path / "site"
    page = render_bundle_page(bundle_dir, out_dir)
    html = page.read_text(encoding="utf-8")
    assert "<ol>" in html and "</ol>" in html
    assert "<ul>" in html and "</ul>" in html
    assert '<a href="https://example.com/two">second</a>' in html
    assert "<blockquote>quoted</blockquote>" in html
    assert "<img" in html
    assert "<pre><code>" in html
    assert (page.parent / "assets" / "image-01.jpg").exists()


def test_nested_list_items_render_inside_their_parent():
    html = _render_markdown_body("- Parent\n  - Child\n- Sibling\n")
    assert "<li>Parent<ul>" in html.replace("\n", "")
    assert "<li>Child</li>" in html.replace("\n", "")
    assert html.replace("\n", "").index("Parent") < html.replace("\n", "").index("Child") < html.replace("\n", "").index("Sibling")
