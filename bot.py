"""
Clipstry Discord Bot — single-file edition.

Paste this entire file as `bot.py` into your hosting panel.

Required env vars (set them in the panel, not in the file):
  DISCORD_BOT_TOKEN   - Bot token from Discord Developer Portal
  MONGO_URL           - mongodb://... or mongodb+srv://... connection string
  DB_NAME             - e.g. viewtracker_db
  APIFY_API_TOKEN     - (optional) apify_api_... for reliable Instagram / X / TikTok

Required packages (the panel usually has a field for this — paste this line):
  discord.py httpx beautifulsoup4 lxml motor python-dotenv
"""
import os
import re
import json
import time
import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from motor.motor_asyncio import AsyncIOMotorClient
import discord
from discord import app_commands
from extra_commands import register_extra_commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("clipstry")

# ============================================================================
# CONFIG
# ============================================================================
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017").strip()
DB_NAME = os.environ.get("DB_NAME", "viewtracker_db").strip()
APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "").strip()

PLATFORMS = ("instagram", "tiktok", "twitter", "youtube")

VERIFIED_CREATOR_ROLE = "Verified Creator"
CAMPAIGN_MANAGER_ROLE = "Campaign Manager"
PLATFORM_ROLE = {
    "instagram": "Instagram Clipper",
    "tiktok": "TikTok Clipper",
    "twitter": "X Clipper",
    "youtube": "YouTube Clipper",
}
ROLE_COLOR = {
    "instagram": 0xE1306C,
    "tiktok": 0x000000,
    "twitter": 0x1DA1F2,
    "youtube": 0xFF0000,
    VERIFIED_CREATOR_ROLE: 0x002FA7,
}

APIFY_TIKTOK_ACTOR = "clockworks~tiktok-scraper"
APIFY_INSTAGRAM_ACTOR = "apify~instagram-scraper"
APIFY_TWITTER_PROFILE_ACTOR = "pratikdani~twitter-profile-scraper"
APIFY_TWITTER_TWEET_ACTOR = (
    "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest"
)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}

# TikWM free tier: 1 req/sec. Serialize through a lock with 1.2s spacing.
_TIKWM_LOCK = asyncio.Lock()
_TIKWM_MIN_GAP_S = 1.2
_tikwm_last = 0.0


# ============================================================================
# HELPERS
# ============================================================================
def normalize_handle(platform: str, raw: str) -> str:
    raw = raw.strip().lstrip("@")
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


def _tweet_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"/status(?:es)?/(\d+)", url)
    return m.group(1) if m else None


def make_code() -> str:
    return "VRFY-" + secrets.token_hex(3).upper()


# ============================================================================
# SCRAPERS — Apify-first for reliability
# ============================================================================
async def _fetch_html(url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as c:
            r = await c.get(url)
            return r.text if r.status_code < 400 else None
    except Exception as e:
        logger.warning("html fetch %s -> %s", url, e)
        return None


async def _apify_run(actor: str, payload: dict, timeout_s: int = 90) -> Optional[list]:
    if not APIFY_TOKEN:
        return None
    url = (
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
        f"?token={APIFY_TOKEN}&timeout={timeout_s}"
    )
    try:
        async with httpx.AsyncClient(timeout=timeout_s + 10) as c:
            r = await c.post(url, json=payload)
        if r.status_code >= 400:
            logger.warning("apify %s HTTP %s", actor, r.status_code)
            return None
        data = r.json()
        return data if isinstance(data, list) else None
    except Exception as e:
        logger.warning("apify %s err %s", actor, e)
        return None


async def _tikwm(path: str, params: dict) -> Optional[dict]:
    """Queued + retried TikWM helper. Returns the `data` field or None."""
    global _tikwm_last
    api = f"https://www.tikwm.com{path}"
    for attempt in range(3):
        async with _TIKWM_LOCK:
            gap = _TIKWM_MIN_GAP_S - (time.monotonic() - _tikwm_last)
            if gap > 0:
                await asyncio.sleep(gap)
            try:
                async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as c:
                    r = await c.get(api, params=params)
                _tikwm_last = time.monotonic()
                if r.status_code >= 400:
                    return None
                p = r.json()
            except Exception:
                _tikwm_last = time.monotonic()
                if attempt < 2:
                    await asyncio.sleep(1.5)
                    continue
                return None
        if p.get("code") == 0:
            return p.get("data") or {}
        if "limit" in (p.get("msg") or "").lower() and attempt < 2:
            await asyncio.sleep(1.5)
            continue
        return None
    return None


# ---- bio fetching ----
async def fetch_bio(platform: str, handle: str) -> Optional[str]:
    handle = normalize_handle(platform, handle)
    if platform == "tiktok":
        # Apify primary
        items = await _apify_run(APIFY_TIKTOK_ACTOR, {
            "profiles": [handle], "resultsPerPage": 1,
            "shouldDownloadVideos": False, "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
        })
        if items:
            sig = (items[0].get("authorMeta") or {}).get("signature")
            if isinstance(sig, str):
                return sig
        # TikWM fallback
        data = await _tikwm("/api/user/info", {"unique_id": handle})
        if data:
            return (data.get("user") or {}).get("signature") or data.get("signature") or ""

    if platform == "instagram":
        items = await _apify_run(APIFY_INSTAGRAM_ACTOR, {
            "directUrls": [f"https://www.instagram.com/{handle}/"],
            "resultsType": "details", "resultsLimit": 1,
        })
        if items:
            return items[0].get("biography") or items[0].get("bio") or ""

    if platform == "twitter":
        items = await _apify_run(APIFY_TWITTER_PROFILE_ACTOR, {
            "url": f"https://x.com/{handle}"
        })
        if items:
            it = items[0]
            return it.get("desc") or it.get("description") or it.get("bio") or ""

    # Fallback: scrape OG meta from public HTML (works decently for YouTube)
    html = await _fetch_html(profile_url(platform, handle))
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for prop in ("og:description", "twitter:description", "description"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            return tag["content"]
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "{}")
            if isinstance(d, dict) and d.get("description"):
                return d["description"]
        except Exception:
            pass
    return None


# ---- view counts ----
_VIEW_PATTERNS = [
    re.compile(r'"viewCount"\s*:\s*"?(\d+)"?'),
    re.compile(r'"playCount"\s*:\s*(\d+)'),
    re.compile(r'"video_view_count"\s*:\s*(\d+)'),
    re.compile(r'(\d[\d,\.]*)\s*(?:views|Views)'),
]


def _parse_views_from_html(html: str) -> Optional[int]:
    for pat in _VIEW_PATTERNS:
        m = pat.search(html)
        if m:
            try:
                return int(m.group(1).replace(",", "").replace(".", ""))
            except ValueError:
                continue
    return None


async def fetch_post_views(platform: str, post_url: str) -> Optional[int]:
    if platform == "tiktok":
        items = await _apify_run(APIFY_TIKTOK_ACTOR, {
            "postURLs": [post_url],
            "shouldDownloadVideos": False, "shouldDownloadCovers": False,
            "shouldDownloadSubtitles": False,
        })
        if items:
            v = items[0].get("playCount")
            if isinstance(v, int):
                return v
        data = await _tikwm("/api/", {"url": post_url, "hd": 0})
        if data:
            v = data.get("play_count")
            if isinstance(v, int):
                return v

    if platform == "instagram":
        items = await _apify_run(APIFY_INSTAGRAM_ACTOR, {
            "directUrls": [post_url], "resultsType": "posts", "resultsLimit": 1,
        })
        if items:
            for k in ("videoPlayCount", "videoViewCount", "playCount"):
                v = items[0].get(k)
                if isinstance(v, int):
                    return v

    if platform == "twitter":
        tid = _tweet_id_from_url(post_url)
        if tid:
            items = await _apify_run(APIFY_TWITTER_TWEET_ACTOR, {
                "tweetIDs": [tid], "maxItems": 20,
            })
            if items:
                for it in items:
                    if str(it.get("id")) == tid:
                        v = it.get("viewCount") or it.get("views")
                        if isinstance(v, int):
                            return v
                for it in items:
                    if str(it.get("id", "-1")) == "-1":
                        continue
                    v = it.get("viewCount") or it.get("views")
                    if isinstance(v, int) and v > 0:
                        return v

    html = await _fetch_html(post_url)
    return _parse_views_from_html(html) if html else None


# ============================================================================
# DISCORD ROLE HELPERS
# ============================================================================
async def _get_or_create_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    role = discord.utils.get(guild.roles, name=name)
    if role:
        return role
    try:
        return await guild.create_role(
            name=name,
            colour=discord.Colour(ROLE_COLOR.get(name, 0x808080)),
            mentionable=True,
            reason="Auto-created by Clipstry",
        )
    except discord.Forbidden:
        logger.warning("Missing Manage Roles in guild %s", guild.id)
        return None
    except Exception as e:
        logger.exception("create_role %s failed: %s", name, e)
        return None


async def grant_creator_roles(interaction: discord.Interaction, platform: str):
    """Assign per-platform + Verified Creator roles; strip any 'Unverified *' role."""
    granted, warnings = [], []
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        warnings.append("Run this in a server to receive your creator role.")
        return granted, warnings

    targets = [PLATFORM_ROLE.get(platform), VERIFIED_CREATOR_ROLE]
    to_add = []
    for name in targets:
        if not name:
            continue
        role = await _get_or_create_role(interaction.guild, name)
        if role is None:
            warnings.append(f"Couldn't create/find `{name}` (need **Manage Roles**).")
            continue
        if role >= interaction.guild.me.top_role:
            warnings.append(
                f"`{name}` sits above the bot's role — move the bot higher in role list."
            )
            continue
        if role not in interaction.user.roles:
            to_add.append(role)
        granted.append(name)

    if to_add:
        try:
            await interaction.user.add_roles(*to_add, reason="Social account verified")
        except discord.Forbidden:
            warnings.append("Bot lacks permission to assign roles.")

    # remove ANY "unverified *" role
    for r in [x for x in interaction.user.roles if "unverified" in x.name.lower()]:
        if r >= interaction.guild.me.top_role:
            warnings.append(f"Can't remove `{r.name}` — above bot's role.")
            continue
        try:
            await interaction.user.remove_roles(r, reason="Verified")
        except discord.Forbidden:
            warnings.append(f"Couldn't remove `{r.name}`.")

    return granted, warnings


def has_role(member: discord.Member, name: str) -> bool:
    return any(r.name == name for r in member.roles)


# ============================================================================
# BOT
# ============================================================================
intents = discord.Intents.default()
intents.message_content = True


class Clipstry(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.mongo = AsyncIOMotorClient(MONGO_URL)
        self.db = self.mongo[DB_NAME]

    async def setup_hook(self):
        register_commands(self.tree, self.db)
        register_extra_commands(
            self.tree,
            self.db,
            CAMPAIGN_MANAGER_ROLE,
            has_role,
            fetch_post_views,
            detect_platform_from_url,
            normalize_handle,
            APIFY_TOKEN,
            _apify_run,
        )

        try:
            # If you want immediate command registration for a single test guild,
            # set the GUILD_ID environment variable to the guild's ID (as an int).
            # When GUILD_ID is set we sync commands only to that guild (appears instantly).
            guild_id = os.environ.get("GUILD_ID")
            if guild_id:
                try:
                    gid = int(guild_id)
                    synced = await self.tree.sync(guild=discord.Object(id=gid))
                    logger.info("Synced %d slash commands to guild %s", len(synced), gid)
                except Exception as e:
                    logger.exception("guild sync failed: %s", e)
            else:
                synced = await self.tree.sync()
                logger.info("Synced %d global slash commands", len(synced))
        except Exception as e:
            logger.exception("sync failed: %s", e)

    async def on_ready(self):
        logger.info("Logged in as %s (id=%s)", self.user, self.user.id)


def register_commands(tree: app_commands.CommandTree, db):
    platform_choices = [app_commands.Choice(name=p, value=p) for p in PLATFORMS]

    async def active_campaign_autocomplete(interaction, current: str):
        q = {"status": "active"}
        if interaction.guild_id:
            q["guild_id"] = str(interaction.guild_id)
        if current:
            q["name"] = {"$regex": current, "$options": "i"}
        items = (
            await db.campaigns.find(q, {"_id": 0, "id": 1, "name": 1})
            .sort("created_at", -1).to_list(25)
        )
        return [
            app_commands.Choice(name=f"{c['name']} ({c['id'][:8]})", value=c["id"])
            for c in items
        ]

    @tree.command(name="verify", description="Start verifying a social media account")
    @app_commands.describe(platform="Which platform", handle="Your @handle or profile URL")
    @app_commands.choices(platform=platform_choices)
    async def verify_cmd(interaction, platform: app_commands.Choice[str], handle: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plat = platform.value
        norm = normalize_handle(plat, handle)
        existing = await db.social_accounts.find_one(
            {"discord_id": str(interaction.user.id), "platform": plat, "handle": norm},
            {"_id": 0},
        )
        if existing and existing.get("verified"):
            await interaction.followup.send(
                f"`{plat}/@{norm}` is already verified.", ephemeral=True
            )
            return
        code = existing["verification_code"] if existing else make_code()
        doc = {
            "id": existing["id"] if existing else secrets.token_hex(8),
            "discord_id": str(interaction.user.id),
            "user_id": None,
            "platform": plat,
            "handle": norm,
            "verification_code": code,
            "verified": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.social_accounts.update_one(
            {"discord_id": str(interaction.user.id), "platform": plat, "handle": norm},
            {"$set": doc}, upsert=True,
        )
        msg = (
            f"**Step 1.** Tap the code below to copy it (long-press on mobile), "
            f"then paste it **anywhere in your `{plat}` bio** for @{norm}:\n"
            f"```\n{code}\n```\n"
            f"**Step 2.** Run `/verify-check platform:{plat} handle:{norm}` to confirm."
        )
        await interaction.followup.send(msg, ephemeral=True)

    @tree.command(name="verify-check", description="Check your verification code is in your bio")
    @app_commands.describe(platform="Platform", handle="Your @handle")
    @app_commands.choices(platform=platform_choices)
    async def verify_check_cmd(interaction, platform: app_commands.Choice[str], handle: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plat = platform.value
        norm = normalize_handle(plat, handle)
        doc = await db.social_accounts.find_one(
            {"discord_id": str(interaction.user.id), "platform": plat, "handle": norm},
            {"_id": 0},
        )
        if not doc:
            await interaction.followup.send(
                "No pending verification. Use `/verify` first.", ephemeral=True
            )
            return
        bio = await fetch_bio(plat, norm)
        if bio is None:
            await interaction.followup.send(
                "Couldn't fetch your profile (private or platform blocked). Try again later.",
                ephemeral=True,
            )
            return
        if doc["verification_code"] in bio:
            await db.social_accounts.update_one(
                {"id": doc["id"]},
                {"$set": {"verified": True, "verified_at": datetime.now(timezone.utc).isoformat()}},
            )
            granted, warnings = await grant_creator_roles(interaction, plat)
            lines = [f"**VERIFIED** `{plat}/@{norm}`."]
            if granted:
                lines.append("Roles granted: " + ", ".join(f"`{g}`" for g in granted))
            for w in warnings:
                lines.append(":warning: " + w)
            lines.append("You can now submit posts with `/submit`.")
            await interaction.followup.send("\n".join(lines), ephemeral=True)
        else:
            await interaction.followup.send(
                f"Code `{doc['verification_code']}` not in your bio yet. Bio fetched:\n"
                f"```\n{bio[:300]}\n```",
                ephemeral=True,
            )

    @tree.command(name="create-campaign", description="Create a view-tracking campaign (Campaign Manager)")
    @app_commands.describe(
        name="Campaign name", goal_views="Target total views",
        payout="Payout amount in USD", description="Short description",
    )
    async def create_campaign_cmd(
        interaction, name: str, goal_views: int, payout: float,
        description: Optional[str] = "",
    ):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(
            interaction.user, CAMPAIGN_MANAGER_ROLE
        ):
            await interaction.followup.send(
                f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to create campaigns.",
                ephemeral=True,
            )
            return
        camp = {
            "id": secrets.token_hex(8),
            "name": name,
            "description": description or "",
            "goal_views": goal_views,
            "payout_cents": int(payout * 100),
            "status": "active",
            "creator_discord_id": str(interaction.user.id),
            "creator_user_id": None,
            "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
        }
        await db.campaigns.insert_one(camp)
        embed = discord.Embed(
            title=f"Campaign created: {name}",
            description=description or "Submit posts with `/submit`.",
            color=0x002FA7,
        )
        embed.add_field(name="Goal", value=f"{goal_views:,} views")
        embed.add_field(name="Payout", value=f"${payout:,.2f}")
        embed.add_field(name="ID", value=f"`{camp['id']}`", inline=False)
        await interaction.followup.send(embed=embed)

    @tree.command(name="end-campaign", description="End a campaign (Campaign Manager)")
    @app_commands.describe(campaign_id="Pick an active campaign")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def end_campaign_cmd(interaction, campaign_id: str):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(
            interaction.user, CAMPAIGN_MANAGER_ROLE
        ):
            await interaction.followup.send(
                f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to end campaigns.",
                ephemeral=True,
            )
            return
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return
        await db.campaigns.update_one(
            {"id": campaign_id},
            {"$set": {"status": "ended", "ended_at": datetime.now(timezone.utc).isoformat()}},
        )
        subs = await db.submissions.find({"campaign_id": campaign_id}, {"_id": 0}).to_list(2000)
        total = sum(s.get("current_views", 0) for s in subs)
        await interaction.followup.send(
            f"Campaign **{camp['name']}** ended. Total tracked views: **{total:,}** across {len(subs)} submissions."
        )

    @tree.command(name="submit", description="Submit a post URL to a campaign (Verified Creator)")
    @app_commands.describe(campaign_id="Pick a campaign", post_url="Public post URL")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def submit_cmd(interaction, campaign_id: str, post_url: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(
            interaction.user, VERIFIED_CREATOR_ROLE
        ):
            await interaction.followup.send(
                f"You need the **{VERIFIED_CREATOR_ROLE}** role to submit. "
                "Run `/verify` then `/verify-check` to earn it.",
                ephemeral=True,
            )
            return
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return
        if camp["status"] != "active":
            await interaction.followup.send("Campaign is not active.", ephemeral=True)
            return
        plat = detect_platform_from_url(post_url)
        if not plat:
            await interaction.followup.send(
                "Unsupported URL. Use Instagram / TikTok / Twitter/X / YouTube.",
                ephemeral=True,
            )
            return
        verified = await db.social_accounts.find_one(
            {"discord_id": str(interaction.user.id), "platform": plat, "verified": True},
            {"_id": 0},
        )
        if not verified:
            await interaction.followup.send(
                f"You must verify a {plat} account first via `/verify`.",
                ephemeral=True,
            )
            return
        views = await fetch_post_views(plat, post_url) or 0
        sub = {
            "id": secrets.token_hex(8),
            "campaign_id": campaign_id,
            "discord_id": str(interaction.user.id),
            "user_id": None,
            "social_account_id": verified["id"],
            "platform": plat,
            "post_url": post_url,
            "current_views": views,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        await db.submissions.insert_one(sub)
        await interaction.followup.send(
            f"Submitted to **{camp['name']}**. Current views: **{views:,}**.",
            ephemeral=True,
        )

    @tree.command(name="campaigns", description="List active campaigns in this server")
    async def campaigns_cmd(interaction):
        await interaction.response.defer(thinking=True)
        q = {"status": "active"}
        if interaction.guild_id:
            q["guild_id"] = str(interaction.guild_id)
        items = await db.campaigns.find(q, {"_id": 0}).to_list(25)
        if not items:
            await interaction.followup.send("No active campaigns.")
            return
        embed = discord.Embed(title="Active Campaigns", color=0x002FA7)
        for c in items:
            embed.add_field(
                name=c["name"],
                value=f"`{c['id']}` — goal {c['goal_views']:,} views — ${c['payout_cents']/100:,.2f}",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @tree.command(name="accounts", description="Show your verified social accounts")
    async def accounts_cmd(interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        items = await db.social_accounts.find(
            {"discord_id": str(interaction.user.id)}, {"_id": 0}
        ).to_list(50)
        if not items:
            await interaction.followup.send(
                "No accounts. Use `/verify` to add one.", ephemeral=True
            )
            return
        lines = [
            f"`{a['platform']}` @{a['handle']} — **{'VERIFIED' if a.get('verified') else 'PENDING'}**"
            for a in items
        ]
        await interaction.followup.send("\n".join(lines), ephemeral=True)


# ============================================================================
# ENTRY POINT
# ============================================================================
def main():
    if not DISCORD_BOT_TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN is not set.")
    bot = Clipstry()
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
