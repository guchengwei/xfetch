# -*- coding: utf-8 -*-
"""
Camofox client — thin stdlib wrapper for the Camofox REST API.

Camofox exposes a local HTTP API (default port 9377) that drives a browser
session. We use it to load Nitter pages and grab their accessibility snapshot
so we can parse reply threads without running Playwright.

No third-party deps — stdlib urllib only.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Optional

CAMOFOX_USER = "x-reader"


def camofox_available(port: int = 9377) -> bool:
    """Return True if Camofox is running and responding on *port*."""
    try:
        req = urllib.request.Request(
            f"http://localhost:{port}/tabs",
            headers={"User-Agent": CAMOFOX_USER},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def camofox_open_tab(url: str, session_key: str, port: int = 9377) -> Optional[str]:
    """
    POST /tabs to open *url* in a new Camofox tab.

    Returns the tab ID string, or None on failure.
    """
    payload = json.dumps({"url": url, "sessionKey": session_key, "userId": CAMOFOX_USER}).encode()
    req = urllib.request.Request(
        f"http://localhost:{port}/tabs",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": CAMOFOX_USER,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            return body.get("tabId") or body.get("id")
    except Exception:
        return None


def camofox_snapshot(tab_id: str, port: int = 9377) -> Optional[str]:
    """
    GET /tabs/{tab_id}/snapshot

    Returns the accessibility snapshot string, or None on failure.
    """
    req = urllib.request.Request(
        f"http://localhost:{port}/tabs/{tab_id}/snapshot?userId={CAMOFOX_USER}",
        headers={"User-Agent": CAMOFOX_USER},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            return body.get("snapshot") or body.get("content")
    except Exception:
        return None


def camofox_close_tab(tab_id: str, port: int = 9377) -> None:
    """DELETE /tabs/{tab_id} to close the tab. Best-effort; errors are swallowed."""
    req = urllib.request.Request(
        f"http://localhost:{port}/tabs/{tab_id}?userId={CAMOFOX_USER}",
        method="DELETE",
        headers={"User-Agent": CAMOFOX_USER},
    )
    try:
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass


def camofox_fetch_page(
    url: str,
    session_key: str,
    wait: float = 8.0,
    port: int = 9377,
) -> Optional[str]:
    """
    Open *url* in Camofox, wait for the page to settle, capture the
    accessibility snapshot, then close the tab.

    Returns the snapshot string, or None if any step fails.
    """
    tab_id = camofox_open_tab(url, session_key=session_key, port=port)
    if not tab_id:
        return None
    try:
        time.sleep(wait)
        return camofox_snapshot(tab_id, port=port)
    finally:
        camofox_close_tab(tab_id, port=port)
