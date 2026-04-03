from __future__ import annotations

from xfetch.connectors.bilibili import BilibiliConnector
from xfetch.connectors.rss import RSSConnector
from xfetch.connectors.telegram import TelegramConnector
from xfetch.connectors.wechat import WeChatConnector
from xfetch.connectors.web import WebConnector
from xfetch.connectors.x import XConnector
from xfetch.connectors.xiaohongshu import XiaohongshuConnector
from xfetch.connectors.youtube import YouTubeConnector


def connector_registry():
    return [XConnector(), RSSConnector(), TelegramConnector(), WeChatConnector(), XiaohongshuConnector(), YouTubeConnector(), BilibiliConnector(), WebConnector()]


def pick_connector(url: str):
    for connector in connector_registry():
        if connector.can_handle(url):
            return connector
    return None
