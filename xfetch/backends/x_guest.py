"""X post lookup that does not require a user token.

FxTwitter and VxTwitter are preferred when they respond. When they are blocked,
the public web guest token can still read TweetResultByRestId, including X
Article title, DraftJS body, and media. ``XFETCH_X_BEARER_TOKEN`` is an optional
official API fallback for the same post when that guest query fails.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlencode, urlparse
from urllib.request import Request

from xfetch.net import safe_urlopen


# Public bearer embedded in X's web client. Not a user credential.
_PUBLIC_WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
# Verified against a live Article post on 2026-10-07. A 404 means the id rotated.
_TWEET_RESULT_QUERY_ID = "Xl5pC_lBk_gcO2ItU39DQw"
_X_API_TOKEN_ENV = "XFETCH_X_BEARER_TOKEN"
_STATUS_ID_RE = re.compile(r"/status/(\d+)")

_GUEST_FEATURES = {
    "articles_preview_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "view_counts_everywhere_api_enabled": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "verified_phone_label_enabled": False,
    "rweb_video_screen_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}
_ARTICLE_FIELD_TOGGLES = {
    "withArticleRichContentState": True,
    "withArticlePlainText": True,
    "withArticleSummaryText": True,
}


def x_api_configured() -> bool:
    return bool(os.environ.get(_X_API_TOKEN_ENV, "").strip())


def status_id_from_url(tweet_url: str) -> str:
    match = _STATUS_ID_RE.search(urlparse(tweet_url).path)
    if not match:
        raise ValueError("X URL has no status id")
    return match.group(1)


def _read_json(request: Request, timeout: int) -> dict:
    with safe_urlopen(request, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode())
    if not isinstance(payload, dict):
        raise ValueError("X response was not a JSON object")
    return payload


def _activate_guest_token(timeout: int) -> str:
    request = Request(
        "https://api.twitter.com/1.1/guest/activate.json",
        data=b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {_PUBLIC_WEB_BEARER}",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    payload = _read_json(request, timeout)
    token = str(payload.get("guest_token") or "").strip()
    if not token:
        raise ValueError("X guest activate did not return a guest token")
    return token


def fetch_guest_graphql(tweet_url: str, timeout: int = 20) -> dict:
    tweet_id = status_id_from_url(tweet_url)
    guest_token = _activate_guest_token(timeout)
    variables = {
        "tweetId": tweet_id,
        "includePromotedContent": False,
        "withBirdwatchNotes": False,
        "withVoice": False,
        "withCommunity": False,
    }
    query = urlencode(
        {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(_GUEST_FEATURES, separators=(",", ":")),
            "fieldToggles": json.dumps(_ARTICLE_FIELD_TOGGLES, separators=(",", ":")),
        }
    )
    endpoint = f"https://api.x.com/graphql/{_TWEET_RESULT_QUERY_ID}/TweetResultByRestId?{query}"
    request = Request(
        endpoint,
        headers={
            "Authorization": f"Bearer {_PUBLIC_WEB_BEARER}",
            "x-guest-token": guest_token,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    return _read_json(request, timeout)


def _plain_text_blocks(plain: str) -> list[dict]:
    chunks = [part.strip() for part in re.split(r"\n\s*\n", plain) if part.strip()]
    if not chunks and plain.strip():
        chunks = [plain.strip()]
    return [{"type": "unstyled", "text": chunk} for chunk in chunks]


def _unwrap_tweet_result(result: dict) -> dict:
    if result.get("__typename") == "TweetWithVisibilityResults" and isinstance(result.get("tweet"), dict):
        return result["tweet"]
    return result


def _article_from_graphql(article_result: dict) -> dict | None:
    if not article_result:
        return None
    content = article_result.get("content_state") if isinstance(article_result.get("content_state"), dict) else {}
    blocks = content.get("blocks") or []
    entity_map = content.get("entityMap") or []
    if not blocks:
        plain = str(article_result.get("plain_text") or article_result.get("preview_text") or "")
        blocks = _plain_text_blocks(plain)
        entity_map = []
    return {
        "title": article_result.get("title") or "",
        "preview_text": article_result.get("preview_text") or "",
        "content": {"blocks": blocks, "entityMap": entity_map},
        "media_entities": article_result.get("media_entities") or [],
        "cover_media": article_result.get("cover_media") or {},
    }


def guest_response_to_status_payload(payload: dict) -> dict:
    result = ((payload.get("data") or {}).get("tweetResult") or {}).get("result") or {}
    if not isinstance(result, dict) or not result:
        errors = payload.get("errors")
        detail = ""
        if isinstance(errors, list) and errors:
            detail = str((errors[0] or {}).get("message") or "")
        raise ValueError(detail or "X guest response did not include a post")
    result = _unwrap_tweet_result(result)
    legacy = result.get("legacy") or {}
    user_legacy = ((((result.get("core") or {}).get("user_results") or {}).get("result") or {}).get("legacy") or {})
    screen_name = str(user_legacy.get("screen_name") or "")
    tweet_id = str(result.get("rest_id") or legacy.get("id_str") or "")
    full_text = str(legacy.get("full_text") or "").strip()
    article_result = ((result.get("article") or {}).get("article_results") or {}).get("result") or {}
    views = result.get("views") or {}
    view_count = views.get("count")
    try:
        views_value = int(view_count)
    except (TypeError, ValueError):
        views_value = 0
    canonical = f"https://x.com/{screen_name}/status/{tweet_id}" if screen_name and tweet_id else ""
    note = ((result.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}
    note_text = str((note.get("text") or "")).strip()
    if note_text and (not full_text or full_text == note_text[: len(full_text)]):
        full_text = note_text
    return {
        "tweet": {
            "id": tweet_id,
            "url": canonical,
            "text": full_text,
            "raw_text": {"text": full_text},
            "created_at": legacy.get("created_at"),
            "lang": legacy.get("lang"),
            "likes": legacy.get("favorite_count", 0),
            "retweets": legacy.get("retweet_count", 0),
            "replies": legacy.get("reply_count", 0),
            "views": views_value,
            "author": {"screen_name": screen_name, "name": user_legacy.get("name") or ""},
            "article": _article_from_graphql(article_result if isinstance(article_result, dict) else {}),
            "media": {"all": []},
        }
    }


def fetch_guest_status_payload(tweet_url: str, timeout: int = 20) -> dict:
    return guest_response_to_status_payload(fetch_guest_graphql(tweet_url, timeout=timeout))


def _article_from_x_api(article: dict, media_by_key: dict[str, dict]) -> dict | None:
    if not article:
        return None
    content = article.get("content_state") if isinstance(article.get("content_state"), dict) else {}
    if not content and isinstance(article.get("content"), dict):
        content = article["content"]
    blocks = content.get("blocks") or []
    entity_map = content.get("entityMap") or content.get("entities") or []
    if not blocks:
        plain = str(article.get("plain_text") or article.get("preview_text") or "")
        blocks = _plain_text_blocks(plain)
        entity_map = []
    cover = article.get("cover_media") if isinstance(article.get("cover_media"), dict) else {}
    cover_url = str(article.get("cover_media_url") or "").strip()
    if not cover and cover_url:
        cover = {"media_info": {"__typename": "ApiImage", "original_img_url": cover_url}}
    media_key = str(article.get("cover_media_key") or cover.get("media_key") or "")
    if media_key and media_key in media_by_key and not _media_url(cover):
        photo = media_by_key[media_key]
        photo_url = str(photo.get("url") or photo.get("preview_image_url") or "")
        if photo_url:
            cover = {"media_id": media_key, "media_info": {"__typename": "ApiImage", "original_img_url": photo_url}}
    return {
        "title": article.get("title") or "",
        "preview_text": article.get("preview_text") or "",
        "content": {"blocks": blocks, "entityMap": entity_map},
        "media_entities": article.get("media_entities") or [],
        "cover_media": cover or {},
    }


def _media_url(media: dict | None) -> str:
    if not isinstance(media, dict):
        return ""
    info = media.get("media_info") or {}
    return str(info.get("original_img_url") or media.get("url") or "")


def x_api_response_to_status_payload(payload: dict) -> dict:
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict) or not data.get("id"):
        raise ValueError("X API response did not include a post")
    includes = payload.get("includes") or {}
    users = {
        str(user.get("id")): user
        for user in (includes.get("users") or [])
        if isinstance(user, dict) and user.get("id")
    }
    author = users.get(str(data.get("author_id") or "")) or {}
    media_by_key = {
        str(item.get("media_key")): item
        for item in (includes.get("media") or [])
        if isinstance(item, dict) and item.get("media_key")
    }
    article = data.get("article") if isinstance(data.get("article"), dict) else {}
    note_text = str((data.get("note_tweet") or {}).get("text") or "").strip()
    text = note_text or str(data.get("text") or "").strip()
    metrics = data.get("public_metrics") or {}
    photos = []
    for item in media_by_key.values():
        if str(item.get("type") or "").lower() != "photo":
            continue
        url = str(item.get("url") or "").strip()
        if url:
            photos.append({"id": str(item.get("media_key") or ""), "type": "photo", "url": url})
    screen_name = str(author.get("username") or "")
    tweet_id = str(data.get("id") or "")
    return {
        "tweet": {
            "id": tweet_id,
            "url": f"https://x.com/{screen_name}/status/{tweet_id}" if screen_name and tweet_id else "",
            "text": text,
            "raw_text": {"text": str(data.get("text") or "").strip()},
            "created_at": data.get("created_at"),
            "lang": data.get("lang"),
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "replies": metrics.get("reply_count", 0),
            "views": metrics.get("impression_count", 0),
            "author": {"screen_name": screen_name, "name": author.get("name") or ""},
            "article": _article_from_x_api(article, media_by_key),
            "media": {"photos": photos, "all": photos},
        }
    }


def fetch_x_api_status_payload(tweet_url: str, timeout: int = 20) -> dict:
    token = os.environ.get(_X_API_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(f"{_X_API_TOKEN_ENV} is not set")
    tweet_id = status_id_from_url(tweet_url)
    query = urlencode(
        {
            "tweet.fields": "article,created_at,lang,public_metrics,entities,note_tweet,attachments",
            "expansions": "author_id,attachments.media_keys",
            "user.fields": "name,username",
            "media.fields": "url,preview_image_url,type,alt_text",
        }
    )
    request = Request(
        f"https://api.x.com/2/tweets/{tweet_id}?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "xfetch",
            "Accept": "application/json",
        },
    )
    return x_api_response_to_status_payload(_read_json(request, timeout))
