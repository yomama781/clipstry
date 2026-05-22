"""Best-effort public scrapers for social bios and post view counts.

These rely on public unauthenticated HTML/JSON, so results are heuristic and
may break when platforms change their markup. The bot communicates the
limitation to users.
"""
import re
import json
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


async def fetch_bio(platform: str, handle: str) -> Optional[str]:
    """Return the bio/description text for a public profile."""
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


async def fetch_post_views(platform: str, post_url: str) -> Optional[int]:
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
