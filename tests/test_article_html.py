from xfetch.article_html import ArticleHTMLParser, visual_capture_status


def test_article_html_keeps_blocks_images_and_lazy_sources():
    parser = ArticleHTMLParser("https://example.com/posts/1")
    parser.feed(
        "<p>Intro.</p>"
        "<h2>Overview</h2>"
        "<p>Before.</p>"
        '<img src="data:image/gif;base64,AAAA" data-src="/diagram.png" alt="Diagram">'
        "<p>After <strong>bold</strong> and <a href=\"/more?a=1&amp;b=2\">link</a>.</p>"
        "<ol><li>First</li><li>Second</li></ol>"
        "<script>secret()</script>"
        '<img width="1" height="1" src="https://cdn.example.com/pixel.gif">'
    )
    parser.close()
    markdown = parser.markdown()
    assert "Intro.\n\n## Overview\n\nBefore.\n\n![Diagram](https://example.com/diagram.png)\n\nAfter **bold** and [link](https://example.com/more?a=1&b=2)." in markdown
    assert "1. First\n2. Second" in markdown
    assert markdown.index("Before.") < markdown.index("diagram.png") < markdown.index("After **bold**")
    assert "secret" not in markdown
    assert "pixel.gif" not in markdown
    assert parser.captured_assets() == [{
        "url": "https://example.com/diagram.png",
        "type": "image",
        "source": "article_image",
        "alt": "Diagram",
    }]


def test_paragraphs_inside_list_items_stay_on_the_item_line():
    parser = ArticleHTMLParser("https://example.com/post")
    parser.feed("<ul><li><p>First point.</p></li><li><p>Second point.</p></li></ul>")
    parser.close()
    assert parser.markdown() == "- First point.\n- Second point."


def test_root_class_ignores_images_outside_the_article():
    parser = ArticleHTMLParser("https://mp.weixin.qq.com/s/example", root_class="rich_media_content")
    parser.feed(
        '<img data-src="https://mmbiz.qpic.cn/outside.jpg">'
        '<div class="rich_media_content js_underline_content"><p>Inside.</p>'
        '<img data-src="https://mmbiz.qpic.cn/inside.jpg"></div>'
        '<img data-src="https://mmbiz.qpic.cn/after.jpg">'
    )
    parser.close()
    assert parser.markdown() == "Inside.\n\n![](https://mmbiz.qpic.cn/inside.jpg)"
    assert [asset["url"] for asset in parser.captured_assets()] == ["https://mmbiz.qpic.cn/inside.jpg"]


def test_prefer_main_drops_chrome_and_keeps_article_order():
    parser = ArticleHTMLParser("https://example.com/post", prefer_main=True)
    parser.feed(
        "<nav><p>Menu</p><img src=\"https://cdn.example.com/logo.png\"></nav>"
        "<main><h3>Step</h3><p>Body.</p><img alt=\"Fig\" src=\"/fig.png\"></main>"
        "<footer><p>Footer</p></footer>"
    )
    parser.close()
    assert parser.markdown() == "### Step\n\nBody.\n\n![Fig](https://example.com/fig.png)"
    assert "Menu" not in parser.markdown()
    assert "Footer" not in parser.markdown()
    assert "logo.png" not in parser.markdown()


def test_text_only_flatten_is_not_a_complete_visual_capture():
    flattened = "Before.\nSection\nAfter."
    image = "https://cdn.example.com/chart.jpg"
    assert visual_capture_status(flattened, [image], has_body=True, status="complete") == "partial"
    placed = f"Before.\n\n![Chart]({image})\n\n## Section\n\nAfter."
    assert visual_capture_status(placed, [image], has_body=True, status="complete") == "complete"
    assert visual_capture_status(placed, [image], has_body=True, status="partial") == "partial"
    assert visual_capture_status("", [], has_body=False, status="complete") == "partial"
