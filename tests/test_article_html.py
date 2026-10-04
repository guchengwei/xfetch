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


def test_article_local_header_and_aside_stay_in_the_capture():
    parser = ArticleHTMLParser("https://example.com/post", prefer_main=True)
    parser.feed(
        "<nav><p>Menu</p><img src=\"https://cdn.example.com/logo.png\" alt=\"Logo\"></nav>"
        "<article>"
        "<header><h1>Headline</h1><img alt=\"Hero\" src=\"/hero.jpg\"></header>"
        "<aside>Deck note.</aside>"
        "<p>Body.</p>"
        "</article>"
        "<footer><p>Footer</p></footer>"
    )
    parser.close()
    markdown = parser.markdown()
    assert markdown == "# Headline\n\n![Hero](https://example.com/hero.jpg)\n\nDeck note.\n\nBody."
    assert "Menu" not in markdown
    assert "Footer" not in markdown
    assert "logo.png" not in markdown
    assert [asset["url"] for asset in parser.captured_assets()] == ["https://example.com/hero.jpg"]


def test_header_wrapping_the_article_still_captures_the_article():
    parser = ArticleHTMLParser("https://example.com/post", prefer_main=True)
    parser.feed(
        "<header><p>Site title</p><article><h1>Headline</h1><p>Body.</p></article></header>"
        "<footer><p>Footer</p></footer>"
    )
    parser.close()
    assert parser.markdown() == "# Headline\n\nBody."
    assert "Site title" not in parser.markdown()
    assert "Footer" not in parser.markdown()


def test_preformatted_code_keeps_indentation():
    parser = ArticleHTMLParser("https://example.com/post")
    parser.feed(
        "<p>Before.</p>"
        "<pre><code>def answer():\n    return value\n</code></pre>"
        "<p>After.</p>"
    )
    parser.close()
    markdown = parser.markdown()
    assert "```\ndef answer():\n    return value\n```" in markdown
    assert markdown.index("Before.") < markdown.index("    return value") < markdown.index("After.")


def test_linked_image_is_a_standalone_image():
    parser = ArticleHTMLParser("https://example.com/post")
    parser.feed(
        "<p>Before.</p>"
        '<a href="/full?wx_fmt=jpeg"><img alt="Shot" data-src="/thumb.jpg"></a>'
        "<p>After.</p>"
    )
    parser.close()
    assert parser.markdown() == "Before.\n\n![Shot](https://example.com/thumb.jpg)\n\nAfter."
    assert "/full" not in parser.markdown()
    assert [asset["url"] for asset in parser.captured_assets()] == ["https://example.com/thumb.jpg"]


def test_link_text_closes_before_an_image():
    parser = ArticleHTMLParser("https://example.com/post")
    parser.feed('<p>See <a href="/docs">Read <img alt="Icon" src="/icon.png"> more</a> please.</p>')
    parser.close()
    markdown = parser.markdown()
    assert "See [Read](https://example.com/docs)" in markdown
    assert "![Icon](https://example.com/icon.png)" in markdown
    assert markdown.index("[Read](https://example.com/docs)") < markdown.index("icon.png")
    assert markdown.count("](") == 2


def test_fallback_page_keeps_four_images_and_article_keeps_all():
    many = "".join(f'<img alt="n{i}" src="/img-{i}.jpg">' for i in range(1, 6))
    fallback = ArticleHTMLParser("https://example.com/post", prefer_main=True)
    fallback.feed(f"<body><nav><img src=\"/logo.png\"></nav><p>Intro.</p>{many}</body>")
    fallback.close()
    assert [asset["url"] for asset in fallback.captured_assets()] == [
        f"https://example.com/img-{i}.jpg" for i in range(1, 5)
    ]
    assert "img-5.jpg" not in fallback.markdown()
    assert "logo.png" not in fallback.markdown()
    assert "Intro." in fallback.markdown()

    prose = (
        "This paragraph is long enough to show the main element is the article "
        "body rather than a gallery of cards."
    )
    article = ArticleHTMLParser("https://example.com/post", prefer_main=True)
    article.feed(f"<main><p>{prose}</p>{many}</main>")
    article.close()
    assert [asset["url"] for asset in article.captured_assets()] == [
        f"https://example.com/img-{i}.jpg" for i in range(1, 6)
    ]
    assert "img-5.jpg" in article.markdown()

    single = ArticleHTMLParser("https://example.com/post", prefer_main=True)
    single.feed(f"<article><p>Note.</p>{many}</article>")
    single.close()
    assert len(single.captured_assets()) == 5
    assert "img-5.jpg" in single.markdown()


def test_listing_pages_keep_four_images():
    many = "".join(f'<figure><img alt="n{i}" src="/shot-{i}.jpg"><figcaption>Shot {i}</figcaption></figure>' for i in range(1, 7))
    gallery = ArticleHTMLParser("https://example.com/gallery", prefer_main=True)
    gallery.feed(f"<main><h1>Gallery</h1>{many}</main>")
    gallery.close()
    assert [asset["url"] for asset in gallery.captured_assets()] == [
        f"https://example.com/shot-{i}.jpg" for i in range(1, 5)
    ]
    assert "shot-5.jpg" not in gallery.markdown()
    assert "Gallery" in gallery.markdown()
    assert "Shot 6" in gallery.markdown()

    cards = "".join(
        f'<article><h2>Card {i}</h2><p>A listed post with its own summary and picture.</p>'
        f'<img alt="c{i}" src="/card-{i}.jpg"></article>'
        for i in range(1, 7)
    )
    listing = ArticleHTMLParser("https://example.com/blog", prefer_main=True)
    listing.feed(f"<main>{cards}</main>")
    listing.close()
    assert [asset["url"] for asset in listing.captured_assets()] == [
        f"https://example.com/card-{i}.jpg" for i in range(1, 5)
    ]
    assert "card-5.jpg" not in listing.markdown()
    assert "Card 1" in listing.markdown()
    assert "Card 6" in listing.markdown()


def test_nested_lists_keep_their_indent():
    parser = ArticleHTMLParser("https://example.com/post")
    parser.feed("<ul><li>Parent<ul><li>Child</li></ul></li><li>Sibling</li></ul>")
    parser.close()
    assert parser.markdown() == "- Parent\n  - Child\n- Sibling"


def test_plain_or_linked_url_is_not_a_complete_visual_capture():
    image = "https://cdn.example.com/chart.jpg"
    assert visual_capture_status(f"See {image} for the chart.", [image], has_body=True) == "partial"
    assert visual_capture_status(f"See [chart]({image}).", [image], has_body=True) == "partial"
    assert visual_capture_status(f"Before.\n\n![]({image})\n\nAfter.", [image], has_body=True) == "complete"


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
