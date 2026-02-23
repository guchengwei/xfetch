# -*- coding: utf-8 -*-
"""
X/Twitter fetcher — three-tier fallback:

1. FxTwitter public API (rich metadata: likes, views, quotes, X Articles)
   Augmented with Camofox-based reply fetching when Camofox is running.
2. Jina Reader (handles non-tweet X pages: profiles, etc.)
3. Playwright + saved session (handles login-required content)

Install browser tier: pip install "x-reader[browser]" && playwright install chromium
Save X session:       x-reader login twitter

Environment variables (optional):
  CAMOFOX_PORT       default 9377
  NITTER_INSTANCE    default nitter.net
"""

import os
import re
import subprocess
import tempfile
import requests
from loguru import logger
from typing import Dict, Any, List, Optional, Tuple

from x_reader.fetchers.jina import fetch_via_jina
from x_reader.fetchers.camofox_client import (
    camofox_available,
    camofox_fetch_page,
)

FXTWITTER_API = "https://api.fxtwitter.com/{username}/status/{tweet_id}"


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _parse_tweet_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (username, tweet_id) from an x.com status URL.
    Returns (None, None) for non-tweet URLs (profiles, search, etc.).
    """
    match = re.search(r'x\.com/(\w+)/status/(\d+)', url)
    if match:
        return match.group(1), match.group(2)
    return None, None


def _extract_author(url: str) -> str:
    """Extract @username from tweet URL (legacy helper, kept for Tier 2/3)."""
    match = re.search(r'x\.com/(\w+)/status', url)
    return f"@{match.group(1)}" if match else ""


def _is_tweet_url(url: str) -> bool:
    """Check if this is a direct tweet/status URL (vs profile or other X page)."""
    return _parse_tweet_url(url)[1] is not None


# ---------------------------------------------------------------------------
# Tier 1: FxTwitter
# ---------------------------------------------------------------------------

def _fetch_via_fxtwitter(url: str) -> Optional[Dict[str, Any]]:
    """
    Fetch tweet via the FxTwitter public API (no auth required).

    Returns a rich dict with engagement stats, quoted tweet, and article data,
    or None if the request fails or the tweet is not found.
    """
    username, tweet_id = _parse_tweet_url(url)
    if not tweet_id:
        return None

    api_url = FXTWITTER_API.format(username=username, tweet_id=tweet_id)
    try:
        resp = requests.get(api_url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"[Twitter] FxTwitter request failed ({e})")
        return None

    if data.get("code") != 200:
        logger.warning(f"[Twitter] FxTwitter returned code {data.get('code')}")
        return None

    tweet = data.get("tweet", {})

    result: Dict[str, Any] = {
        "text": tweet.get("text", ""),
        "author": tweet.get("author", {}).get("name", ""),
        "screen_name": tweet.get("author", {}).get("screen_name", ""),
        "likes": tweet.get("likes", 0),
        "retweets": tweet.get("retweets", 0),
        "views": tweet.get("views", 0),
        "bookmarks": tweet.get("bookmarks", 0),
        "replies_count": tweet.get("replies", 0),
        "lang": tweet.get("lang", ""),
        "created_at": tweet.get("created_at", ""),
        "url": url,
    }

    outer_media = _extract_media(tweet)
    if outer_media:
        result["media"] = outer_media

    # Quoted tweet — single level only
    if tweet.get("quote"):
        qt = tweet["quote"]
        result["quote"] = {
            "text": qt.get("text", ""),
            "author": qt.get("author", {}).get("name", ""),
            "screen_name": qt.get("author", {}).get("screen_name", ""),
            "url": qt.get("url", ""),
            "likes": qt.get("likes", 0),
            "retweets": qt.get("retweets", 0),
            "views": qt.get("views", 0),
        }
        quote_media = _extract_media(qt)
        if quote_media:
            result["quote"]["media"] = quote_media

    # X Article — extract full text from content blocks
    if tweet.get("article"):
        art = tweet["article"]
        blocks = art.get("content", {}).get("blocks", [])
        full_text = "\n\n".join(b["text"] for b in blocks if b.get("text"))
        result["article"] = {
            "title": art.get("title", ""),
            "full_text": full_text or art.get("preview_text", ""),
            "word_count": len(full_text.split()) if full_text else 0,
        }

    return result


# ---------------------------------------------------------------------------
# Media extraction
# ---------------------------------------------------------------------------

def _extract_media(tweet_data: dict) -> Optional[dict]:
    """Parse FxTwitter media field into a structured dict, or None if no media."""
    media = tweet_data.get("media") or {}
    videos = media.get("videos") or []
    photos = media.get("photos") or []
    result = {}
    if videos:
        best = videos[0]  # FxTwitter first = highest quality
        result.update({
            "type": "video",
            "video_url": best.get("url", ""),
            "thumbnail_url": best.get("thumbnail_url", ""),
            "duration": best.get("duration", 0),
        })
    if photos:
        result["photo_urls"] = [p.get("url", "") for p in photos]
        if "type" not in result:
            result["type"] = "photo"
    return result or None


def _transcribe_twitter_video(video_url: str) -> str:
    """
    Extract audio from a Twitter CDN mp4 URL and transcribe with mlx-whisper / Groq.

    Uses ffmpeg to copy the audio stream only — avoids downloading the full video.
    mlx-whisper processes audio in 30-second chunks internally, so no duration limit needed.
    Returns transcript string or empty string.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.m4a")
            cmd = ["ffmpeg", "-i", video_url, "-vn", "-acodec", "copy", "-y", audio_path]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0:
                logger.warning(f"[Twitter] ffmpeg audio extraction failed: {proc.stderr[:300]}")
                return ""
            logger.info(f"[Twitter] audio extracted: {os.path.getsize(audio_path) // 1024}KB")
            from x_reader.fetchers.whisper import transcribe_audio
            return transcribe_audio(audio_path)
    except Exception as e:
        logger.warning(f"[Twitter] Video transcription failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Replies via Camofox + Nitter
# ---------------------------------------------------------------------------

def _parse_stats_from_text(raw: str):
    """
    Parse engagement columns from a Nitter accessibility snapshot line.

    Nitter renders stats as trailing integer-like tokens.  We try two formats:
      3-column: replies / retweets / likes
      2-column: retweets / likes

    Returns (cleaned_text, replies, retweets, likes).
    """
    tokens = raw.strip().split()
    replies = retweets = likes = 0

    def _to_int(s: str) -> Optional[int]:
        s = s.replace(",", "").replace(".", "")
        return int(s) if s.isdigit() else None

    # Try to pull 3 trailing integers
    if len(tokens) >= 3:
        a, b, c = _to_int(tokens[-3]), _to_int(tokens[-2]), _to_int(tokens[-1])
        if a is not None and b is not None and c is not None:
            replies, retweets, likes = a, b, c
            clean = " ".join(tokens[:-3])
            return clean, replies, retweets, likes

    # Try 2 trailing integers
    if len(tokens) >= 2:
        b, c = _to_int(tokens[-2]), _to_int(tokens[-1])
        if b is not None and c is not None:
            retweets, likes = b, c
            clean = " ".join(tokens[:-2])
            return clean, replies, retweets, likes

    return raw.strip(), replies, retweets, likes


def _parse_replies_snapshot(snapshot: str, original_author: str) -> List[Dict[str, Any]]:
    """
    Walk a Camofox accessibility snapshot (one line per node) and extract reply dicts.

    Reply blocks are delimited by the "Replying to" marker that Nitter renders
    for each reply.  We look backward from that marker for author metadata and
    forward for the reply text + stats.
    """
    lines = snapshot.splitlines()
    replies: List[Dict[str, Any]] = []

    for i, line in enumerate(lines):
        if "Replying to" not in line:
            continue

        # --- backward scan for author info ---
        author_handle = ""
        author_name = ""
        tweet_id = ""
        time_ago = ""

        for j in range(i - 1, max(i - 20, -1), -1):
            prev = lines[j].strip()

            # Handle like: "- link: @handle" or "- text: @handle"
            handle_match = re.search(r'@(\w+)', prev)
            if handle_match and not author_handle:
                candidate = handle_match.group(1).lower()
                if candidate != original_author.lower():
                    author_handle = handle_match.group(1)

            # Tweet permalink: /user/status/ID
            id_match = re.search(r'/status/(\d+)', prev)
            if id_match and not tweet_id:
                tweet_id = id_match.group(1)

            # Time ago strings like "2h", "5m", "Jan 3"
            time_match = re.search(r'\b(\d+[hms]|\w+ \d+)\b', prev)
            if time_match and not time_ago:
                time_ago = time_match.group(1)

            # Author name (heading or strong text before handle)
            if not author_name and re.match(r'^- (heading|strong|text):', prev):
                candidate = re.sub(r'^- \w+:\s*', '', prev).strip()
                if candidate and not candidate.startswith('@') and len(candidate) < 60:
                    author_name = candidate

        # --- forward scan for reply text + stats ---
        reply_text = ""
        reply_likes = reply_retweets = reply_views = 0

        for k in range(i + 1, min(i + 30, len(lines))):
            nxt = lines[k].strip()
            if not nxt:
                continue
            # Stop at next "Replying to" block
            if "Replying to" in nxt:
                break
            # Look for the tweet text node
            if re.match(r'^- text:', nxt) and not reply_text:
                candidate = re.sub(r'^- text:\s*', '', nxt).strip()
                if len(candidate) > 10:
                    reply_text, _, reply_retweets, reply_likes = _parse_stats_from_text(candidate)

        if not reply_text and not author_handle:
            continue

        replies.append({
            "author": author_handle,
            "author_name": author_name,
            "text": reply_text,
            "likes": reply_likes,
            "retweets": reply_retweets,
            "views": reply_views,
            "tweet_id": tweet_id,
            "time_ago": time_ago,
        })

    return replies


def _fetch_replies_via_camofox(
    url: str,
    port: int = 9377,
    nitter_instance: str = "nitter.net",
) -> List[Dict[str, Any]]:
    """
    Load the Nitter equivalent of *url* through Camofox and parse reply dicts.
    Returns an empty list on any failure.
    """
    username, tweet_id = _parse_tweet_url(url)
    if not tweet_id:
        return []

    nitter_url = f"https://{nitter_instance}/{username}/status/{tweet_id}"
    logger.info(f"[Twitter] Fetching replies via Camofox: {nitter_url}")

    try:
        snapshot = camofox_fetch_page(
            nitter_url,
            session_key="x-reader-replies",
            wait=8.0,
            port=port,
        )
    except Exception as e:
        logger.warning(f"[Twitter] Camofox fetch failed ({e})")
        return []

    if not snapshot:
        logger.warning("[Twitter] Camofox returned empty snapshot")
        return []

    replies = _parse_replies_snapshot(snapshot, original_author=username)
    logger.info(f"[Twitter] Parsed {len(replies)} replies from Camofox snapshot")
    return replies


# ---------------------------------------------------------------------------
# Media enrichment (transcription + OCR)
# ---------------------------------------------------------------------------

def _enrich_with_media(result: dict) -> None:
    """
    Mutate result in-place: transcribe videos and OCR photos for the outer
    tweet and the quoted tweet. Replies are not processed.
    """
    targets = [result]
    if result.get("quote"):
        targets.append(result["quote"])

    for target in targets:
        media = target.get("media") or {}
        if media.get("type") == "video" and media.get("video_url"):
            t = _transcribe_twitter_video(media["video_url"])
            if t:
                target["transcript"] = t
        if media.get("photo_urls") and os.getenv("USE_LOCAL_OCR", "false").lower() == "true":
            from x_reader.fetchers.ocr import extract_text_from_image
            texts = [t for u in media["photo_urls"] if (t := extract_text_from_image(u))]
            if texts:
                target["ocr_text"] = "\n---\n".join(texts)


# ---------------------------------------------------------------------------
# Tier 3: Playwright
# ---------------------------------------------------------------------------

async def _fetch_via_playwright(url: str) -> Dict[str, Any]:
    """
    Fetch tweet via Playwright with X-specific DOM selectors.
    Uses saved login session if available (~/.x-reader/sessions/twitter.json).
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run:\n"
            '  pip install "x-reader[browser]"\n'
            "  playwright install chromium"
        )

    from x_reader.fetchers.browser import get_session_path
    from pathlib import Path

    session_path = get_session_path("twitter")
    has_session = Path(session_path).exists()
    if has_session:
        logger.info(f"Using saved X session: {session_path}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        context_kwargs = {}
        if has_session:
            context_kwargs["storage_state"] = session_path

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            **context_kwargs,
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            try:
                await page.wait_for_selector(
                    '[data-testid="tweetText"]', timeout=10_000
                )
            except Exception:
                pass

            tweet_text = await page.evaluate("""() => {
                const tweetEl = document.querySelector('[data-testid="tweetText"]');
                if (tweetEl) return tweetEl.innerText;

                const article = document.querySelector('article');
                if (article) return article.innerText;

                const main = document.querySelector('main');
                if (main) return main.innerText;

                return '';
            }""")

            title = await page.title()

            return {
                "text": (tweet_text or "").strip(),
                "title": (title or "").strip()[:200],
            }
        finally:
            await context.close()
            await browser.close()


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

async def fetch_twitter(url: str) -> Dict[str, Any]:
    """
    Fetch a tweet or X post with three-tier fallback.

    Args:
        url: Tweet URL (x.com or twitter.com)

    Returns:
        Dict with: text, author, screen_name, url, platform, and rich metadata
        fields when available (likes, retweets, views, bookmarks, replies_count,
        lang, created_at, quote, replies, article).
    """
    url = url.replace("twitter.com", "x.com")
    author = _extract_author(url)

    # Tier 1: FxTwitter (only for direct tweet/status URLs)
    if _parse_tweet_url(url)[1]:
        try:
            logger.info(f"[Twitter] Tier 1 — FxTwitter: {url}")
            result = _fetch_via_fxtwitter(url)
            has_content = bool(result and (result.get("text") or result.get("article")))
            if has_content:
                # Enrich with video transcription and photo OCR
                _enrich_with_media(result)
                # Augment with replies from Camofox if available
                port = int(os.getenv("CAMOFOX_PORT", "9377"))
                nitter = os.getenv("NITTER_INSTANCE", "nitter.net")
                if camofox_available(port):
                    replies = _fetch_replies_via_camofox(url, port=port, nitter_instance=nitter)
                    if replies:
                        result["replies"] = replies
                result["platform"] = "twitter"
                return result
            logger.warning("[Twitter] FxTwitter returned no content")
        except Exception as e:
            logger.warning(f"[Twitter] FxTwitter failed ({e})")

    # Tier 2: Jina Reader (handles profiles, threads, non-tweet pages)
    try:
        logger.info(f"[Twitter] Tier 2 — Jina: {url}")
        data = fetch_via_jina(url)
        content = data.get("content", "")
        title = data.get("title", "")
        jina_ok = (
            content
            and len(content.strip()) > 100
            and "not yet fully loaded" not in content.lower()
            and title.lower() not in ("x", "title: x", "")
        )
        if jina_ok:
            return {
                "text": content,
                "author": author,
                "screen_name": author.lstrip("@"),
                "url": url,
                "title": title,
                "platform": "twitter",
            }
        logger.warning("[Twitter] Jina returned unusable content")
    except Exception as e:
        logger.warning(f"[Twitter] Jina failed ({e})")

    # Tier 3: Playwright + session with X-specific extraction
    try:
        logger.info(f"[Twitter] Tier 3 — Playwright: {url}")
        data = await _fetch_via_playwright(url)
        content = data.get("text", "")
        if content and len(content.strip()) > 20:
            return {
                "text": content,
                "author": author,
                "screen_name": author.lstrip("@"),
                "url": url,
                "title": data.get("title", ""),
                "platform": "twitter",
            }
        logger.warning("[Twitter] Playwright returned empty content")
    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"[Twitter] All methods failed: {e}")

    raise RuntimeError(
        f"All Twitter fetch methods failed for: {url}\n"
        f"   Try: x-reader login twitter (to save session for browser fallback)\n"
        f"   Then retry: x-reader {url}"
    )
