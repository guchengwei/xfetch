from xfetch.storage.render import render_bundle_page


def test_render_bundle_page_writes_index_html(tmp_path):
    bundle_dir = tmp_path / "2026-03" / "x-123-alice"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "document.json").write_text(
        '{"title":"Hello","canonical_url":"https://x.com/alice/status/123","author_handle":"alice","created_at":"2026-03-31T00:00:00Z","text":"hello world"}',
        encoding="utf-8",
    )
    out_dir = tmp_path / "site"
    page = render_bundle_page(bundle_dir, out_dir, public_url="https://guchengwei.github.io/link-vault/d/x-123-alice/")
    assert page == out_dir / "d" / "x-123-alice" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert "<title>Hello</title>" in html
    assert "rel=\"canonical\"" in html


def test_render_bundle_page_renders_markdown_images_and_code_blocks(tmp_path):
    bundle_dir = tmp_path / "2026-03" / "x-123-alice"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "assets").mkdir()
    (bundle_dir / "assets" / "image-01.jpg").write_bytes(b"img")
    (bundle_dir / "document.json").write_text(
        '{"title":"Hello","canonical_url":"https://x.com/alice/status/123","author_handle":"alice","created_at":"2026-03-31T00:00:00Z","text":"plain fallback","markdown":"# Hello\\n\\nBefore image\\n\\n![](assets/image-01.jpg)\\n\\n```python\\nprint(123)\\n```\\n"}',
        encoding="utf-8",
    )
    out_dir = tmp_path / "site"
    page = render_bundle_page(bundle_dir, out_dir, public_url="https://guchengwei.github.io/link-vault/d/x-123-alice/")
    html = page.read_text(encoding="utf-8")
    assert 'assets/image-01.jpg' in html
    assert "<img" in html
    assert "<pre><code>" in html
    assert (page.parent / "assets" / "image-01.jpg").exists()
