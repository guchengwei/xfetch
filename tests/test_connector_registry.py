from xfetch.connectors.registry import connector_registry, pick_connector
from xfetch.connectors.bilibili import BilibiliConnector
from xfetch.connectors.rss import RSSConnector
from xfetch.connectors.telegram import TelegramConnector
from xfetch.connectors.wechat import WeChatConnector
from xfetch.connectors.web import WebConnector
from xfetch.connectors.x import XConnector
from xfetch.connectors.xiaohongshu import XiaohongshuConnector
from xfetch.connectors.youtube import YouTubeConnector


def test_connector_registry_starts_with_x_then_rss_then_telegram_then_wechat_then_xiaohongshu_then_youtube_then_bilibili_then_web():
    registry = connector_registry()
    assert [type(connector) for connector in registry[:8]] == [XConnector, RSSConnector, TelegramConnector, WeChatConnector, XiaohongshuConnector, YouTubeConnector, BilibiliConnector, WebConnector]


def test_pick_connector_returns_x_connector_for_x_urls():
    connector = pick_connector("https://x.com/alice/status/123")
    assert isinstance(connector, XConnector)


def test_pick_connector_returns_rss_connector_for_feed_urls():
    connector = pick_connector("https://example.com/feed.xml")
    assert isinstance(connector, RSSConnector)


def test_pick_connector_returns_telegram_connector_for_telegram_urls():
    connector = pick_connector("https://t.me/ai_daily/123")
    assert isinstance(connector, TelegramConnector)


def test_pick_connector_returns_wechat_connector_for_wechat_urls():
    connector = pick_connector("https://mp.weixin.qq.com/s/example")
    assert isinstance(connector, WeChatConnector)


def test_pick_connector_returns_xiaohongshu_connector_for_xhs_urls():
    connector = pick_connector("https://www.xiaohongshu.com/explore/67b8e3f5000000000b00d8e2")
    assert isinstance(connector, XiaohongshuConnector)


def test_pick_connector_returns_youtube_connector_for_youtube_urls():
    connector = pick_connector("https://www.youtube.com/watch?v=abc123")
    assert isinstance(connector, YouTubeConnector)


def test_pick_connector_returns_bilibili_connector_for_bilibili_urls():
    connector = pick_connector("https://www.bilibili.com/video/BV1xx411c7mD")
    assert isinstance(connector, BilibiliConnector)


def test_pick_connector_returns_web_connector_for_generic_http_urls():
    connector = pick_connector("https://example.com/posts/123")
    assert isinstance(connector, WebConnector)


def test_pick_connector_returns_none_for_unsupported_schemes():
    assert pick_connector("mailto:alice@example.com") is None
