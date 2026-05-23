"""Best-effort public scrapers for social bios and post view counts.

These rely on public unauthenticated HTML/JSON, so results are heuristic and
may break when platforms change their markup. The bot communicates the
limitation to users.
"""
import re
import json
import asyncio
import time
import logging
from typing import Optional, Tuple
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

PLATFORMS = ("instagram", "tiktok", "twitter", "youtube")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Apify is used as a more reliable fallback (paid, but free tier covers many
# requests/month). When the token is missing, the Apify path is skipped.
import os as _os
APIFY_TOKEN = _os.environ.get("APIFY_API_TOKEN", "").strip()
APIFY_TIKTOK_ACTOR = "clockworks~tiktok-scraper"
APIFY_INSTAGRAM_ACTOR = "apify~instagram-scraper"


async def _apify_run(actor: str, payload: dict, timeout_s: int = 90) -> Optional[list]:
    """Run an Apify actor synchronously and return its dataset items."""
    if not APIFY_TOKEN:
        return None
    url = (
        f"https://api.apify.com/v2/acts/{actor}"
        f"/run-sync-get-dataset-items?token={APIFY_TOKEN}&timeout={timeout_s}"
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_s + 10) as client:
            r = await client.post(url, json=payload)
        if r.status_code >= 400:
            logger.warning("Apify %s -> HTTP %s: %s", actor, r.status_code, r.text[:200])
            return None
        data = r.json()
        if isinstance(data, list):
            return data
        logger.warning("Apify %s returned non-list: %r", actor, data)
        return None
    except Exception as e:
        logger.warning("Apify %s error: %s", actor, e)
        return None


async def fetch_apify_tiktok_bio(handle: str) -> Optional[str]:
    handle = normalize_handle("tiktok", handle)
    items = await _apify_run(
        APIFY_TIKTOK_ACTOR,
        {
            "profiles": [handle],
            "resultsPerPage": 1,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
        },
    )
    if not items:
        return None
    sig = (items[0].get("authorMeta") or {}).get("signature")
    return sig if isinstance(sig, str) else ""


async def fetch_apify_tiktok_views(post_url: str) -> Optional[int]:
    items = await _apify_run(
        APIFY_TIKTOK_ACTOR,
        {
            "postURLs": [post_url],
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
        },
    )
    if not items:
        return None
    pc = items[0].get("playCount")
    return pc if isinstance(pc, int) else None


async def fetch_apify_instagram_bio(handle: str) -> Optional[str]:
    handle = normalize_handle("instagram", handle)
    items = await _apify_run(
        APIFY_INSTAGRAM_ACTOR,
        {
            "directUrls": [f"https://www.instagram.com/{handle}/"],
            "resultsType": "details",
            "resultsLimit": 1,
        },
    )
    if not items:
        return None
    item = items[0]
    return item.get("biography") or item.get("bio") or ""


async def fetch_apify_instagram_views(post_url: str) -> Optional[int]:
    items = await _apify_run(
        APIFY_INSTAGRAM_ACTOR,
        {
            "directUrls": [post_url],
            "resultsType": "posts",
            "resultsLimit": 1,
        },
    )
    if not items:
        return None
    item = items[0]
    # IG reels use "videoViewCount", posts use "videoPlayCount", carousels lack views
    for key in ("videoPlayCount", "videoViewCount", "playCount"):
        v = item.get(key)
        if isinstance(v, int):
            return v
    return None


# TikWM enforces 1 request/second on the free tier. We serialize all calls
# through a single lock + minimum 1.2s spacing so concurrent submissions queue
# up instead of failing.
_TIKWM_LOCK = asyncio.Lock()
_TIKWM_MIN_GAP_S = 1.2
_tikwm_last_call_at = 0.0


def normalize_handle(platform: str, raw: str) -> str:
    raw = raw.strip().lstrip("@")
    # Strip any URL formatting
    if "/" in raw:
        raw = raw.rstrip("/").split("/")[-1]
    return raw


def profile_url(platform: str, handle: str) -> str:
    handle = normalize_handle(platform, handle)
    return {
        "instagram": f"https://www.instagram.com/{handle}/",
        "tiktok": f"https://www.tiktok.com/@{handle}",
        "twitter": f"https://x.com/{handle}",
        "youtube": (
            f"https://www.youtube.com/@{handle}"
            if not handle.startswith("UC")
            else f"https://www.youtube.com/channel/{handle}"
        ),
    }[platform]


async def _fetch(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(
            headers=HEADERS, timeout=15.0, follow_redirects=True
        ) as client:
            r = await client.get(url)
            if r.status_code >= 400:
                logger.warning("Fetch %s -> %s", url, r.status_code)
                return None
            return r.text
    except Exception as e:
        logger.warning("Fetch error for %s: %s", url, e)
        return None


async def fetch_tiktok_bio(handle: str) -> Optional[str]:
    """Fetch a TikTok bio via the TikWM user-info endpoint (no auth needed)."""
    global _tikwm_last_call_at
    api = "https://www.tikwm.com/api/user/info"
    handle = normalize_handle("tiktok", handle)
    for attempt in range(3):
        async with _TIKWM_LOCK:
            wait = _TIKWM_MIN_GAP_S - (time.monotonic() - _tikwm_last_call_at)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
                    r = await client.get(api, params={"unique_id": handle})
                _tikwm_last_call_at = time.monotonic()
                payload = r.json()
            except Exception as e:
                _tikwm_last_call_at = time.monotonic()
                logger.warning("TikWM user/info error: %s", e)
                if attempt < 2:
                    await asyncio.sleep(1.5)
                    continue
                return None
        if payload.get("code") == 0:
            data = payload.get("data") or {}
            # The bio lives under data.user.signature
            user = data.get("user") or {}
            sig = user.get("signature")
            if isinstance(sig, str):
                return sig
            # Some responses put signature one level up
            sig = data.get("signature")
            if isinstance(sig, str):
                return sig
            return ""  # empty bio is a valid response
        msg = (payload.get("msg") or "").lower()
        if "limit" in msg and attempt < 2:
            await asyncio.sleep(1.5)
            continue
        logger.warning("TikWM user/info failed: %s", payload.get("msg"))
        return None
    return None


async def fetch_bio(platform: str, handle: str) -> Optional[str]:
    """Return the bio/description text for a public profile."""
    if platform == "tiktok":
        bio = await fetch_tiktok_bio(handle)
        if bio:
            return bio
        # TikWM blocked/empty -> Apify fallback
        bio = await fetch_apify_tiktok_bio(handle)
        if bio is not None:
            return bio
        # Fall through to HTML scrape as a last resort.

    if platform == "instagram":
        # Instagram blocks server IPs from HTML scrapes almost always; go to
        # Apify first.
        bio = await fetch_apify_instagram_bio(handle)
        if bio is not None:
            return bio

    url = profile_url(platform, handle)
    html = await _fetch(url)
    if not html:
        return None

    # Strategy: scrape OG description meta tag (works for IG, TikTok, YouTube,
    # Twitter snapshots). For Twitter without auth this is limited - fall
    # back to syndication endpoint.
    soup = BeautifulSoup(html, "lxml")
    for prop in ("og:description", "twitter:description", "description"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            return tag["content"]

    # JSON-LD fallback
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, dict) and data.get("description"):
                return data["description"]
        except Exception:
            pass

    return None


VIEW_PATTERNS = [
    re.compile(r'"viewCount"\s*:\s*"?(\d+)"?'),
    re.compile(r'"playCount"\s*:\s*(\d+)'),
    re.compile(r'"video_view_count"\s*:\s*(\d+)'),
    re.compile(r'"view_count"\s*:\s*(\d+)'),
    re.compile(r'(\d[\d,\.]*)\s*(?:views|Views)'),
]


def _parse_views(html: str) -> Optional[int]:
    for pat in VIEW_PATTERNS:
        m = pat.search(html)
        if m:
            raw = m.group(1).replace(",", "").replace(".", "")
            try:
                return int(raw)
            except ValueError:
                continue
    return None


async def fetch_tiktok_views(post_url: str) -> Optional[int]:
    """Use the free TikWM endpoint to get accurate TikTok play counts.

    Serialized through a global lock with 1.2s spacing so we never exceed the
    free-tier 1 req/sec limit. Retries up to 3 times on transient errors.
    """
    global _tikwm_last_call_at
    api = "https://www.tikwm.com/api/"

    for attempt in range(3):
        async with _TIKWM_LOCK:
            now = time.monotonic()
            wait = _TIKWM_MIN_GAP_S - (now - _tikwm_last_call_at)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as client:
                    r = await client.get(api, params={"url": post_url, "hd": 0})
                _tikwm_last_call_at = time.monotonic()
                if r.status_code >= 400:
                    logger.warning("TikWM HTTP %s for %s", r.status_code, post_url)
                    if r.status_code in (429, 503) and attempt < 2:
                        await asyncio.sleep(2)
                        continue
                    return None
                payload = r.json()
            except Exception as e:
                _tikwm_last_call_at = time.monotonic()
                logger.warning("TikWM request error: %s", e)
                if attempt < 2:
                    await asyncio.sleep(1.5)
                    continue
                return None

        if payload.get("code") == 0:
            data = payload.get("data") or {}
            views = data.get("play_count")
            if isinstance(views, int):
                return views
            return None
        msg = (payload.get("msg") or "").lower()
        if "limit" in msg and attempt < 2:
            logger.info("TikWM rate-limited, retry %d/3", attempt + 2)
            await asyncio.sleep(1.5)
            continue
        logger.warning("TikWM API error: %s", payload.get("msg"))
        return None
    return None


async def fetch_post_views(platform: str, post_url: str) -> Optional[int]:
    if platform == "tiktok":
        views = await fetch_tiktok_views(post_url)
        if views is not None:
            return views
        # TikWM blocked -> Apify fallback
        views = await fetch_apify_tiktok_views(post_url)
        if views is not None:
            return views

    if platform == "instagram":
        views = await fetch_apify_instagram_views(post_url)
        if views is not None:
            return views

    html = await _fetch(post_url)
    if not html:
        return None
    return _parse_views(html)


def detect_platform_from_url(url: str) -> Optional[str]:
    url = url.lower()
    if "instagram.com" in url:
        return "instagram"
    if "tiktok.com" in url:
        return "tiktok"
    if "twitter.com" in url or "x.com" in url:
        return "twitter"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    return None
