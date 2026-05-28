"""Discord bot exposing slash commands for campaigns and verification."""
import os
import logging
import asyncio
import secrets
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorDatabase

from scrapers import (
    APIFY_TOKEN,
    PLATFORMS,
    fetch_bio,
    fetch_post_views,
    detect_platform_from_url,
    normalize_handle,
)

logger = logging.getLogger("discord_bot")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()

VERIFIED_CREATOR_ROLE = "Verified Creator"
UNVERIFIED_ROLE = "Unverified Clipper"
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


async def _get_or_create_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    """Look up a role by name, creating it (with a thematic colour) if missing."""
    role = discord.utils.get(guild.roles, name=name)
    if role is not None:
        return role
    try:
        colour_int = ROLE_COLOR.get(name, 0x808080)
        return await guild.create_role(
            name=name,
            colour=discord.Colour(colour_int),
            mentionable=True,
            reason="Auto-created by ViewTracker on verification",
        )
    except discord.Forbidden:
        logger.warning("Missing Manage Roles permission in guild %s", guild.id)
        return None
    except Exception as e:
        logger.exception("Failed to create role %s: %s", name, e)
        return None


async def grant_creator_roles(
    interaction: discord.Interaction, platform: str
) -> tuple[list[str], list[str]]:
    """Assign the platform-specific role + 'Verified Creator' umbrella role.

    Returns (granted_role_names, warnings).
    """
    granted: list[str] = []
    warnings: list[str] = []
    if interaction.guild is None or not isinstance(interaction.user, discord.Member):
        warnings.append("Run this in a server to receive your creator role.")
        return granted, warnings

    target_names = [PLATFORM_ROLE.get(platform), VERIFIED_CREATOR_ROLE]
    roles_to_add: list[discord.Role] = []
    for name in target_names:
        if not name:
            continue
        role = await _get_or_create_role(interaction.guild, name)
        if role is None:
            warnings.append(
                f"Could not create/find `{name}` (bot needs **Manage Roles**)."
            )
            continue
        if role >= interaction.guild.me.top_role:
            warnings.append(
                f"`{name}` is positioned above the bot's role — move the bot's role higher in Server Settings → Roles."
            )
            continue
        if role not in interaction.user.roles:
            roles_to_add.append(role)
        granted.append(name)

    if roles_to_add:
        try:
            await interaction.user.add_roles(*roles_to_add, reason="Social account verified")
        except discord.Forbidden:
            warnings.append("Bot lacks permission to assign roles.")
        except Exception as e:
            logger.exception("add_roles failed: %s", e)
            warnings.append(f"Role assignment error: {e}")

    # Remove any "unverified ..." role (case-insensitive match) if present.
    unverified_roles = [
        r for r in interaction.user.roles if "unverified" in r.name.lower()
    ]
    for unverified in unverified_roles:
        if unverified >= interaction.guild.me.top_role:
            warnings.append(
                f"Can't remove `{unverified.name}` — it sits above the bot's role."
            )
            continue
        try:
            await interaction.user.remove_roles(
                unverified, reason="User verified a social account"
            )
            logger.info("Removed role %s from %s", unverified.name, interaction.user)
        except discord.Forbidden:
            warnings.append(
                f"Couldn't remove `{unverified.name}` (bot needs Manage Roles)."
            )
        except Exception as e:
            logger.exception("remove_roles failed: %s", e)
            warnings.append(f"Could not remove `{unverified.name}`: {e}")
    if not unverified_roles:
        logger.info(
            "No unverified-* role on %s; user roles: %s",
            interaction.user,
            [r.name for r in interaction.user.roles],
        )

    return granted, warnings


def has_verified_creator_role(member: discord.Member) -> bool:
    return any(r.name == VERIFIED_CREATOR_ROLE for r in member.roles)


def has_campaign_manager_role(member: discord.Member) -> bool:
    return any(r.name == CAMPAIGN_MANAGER_ROLE for r in member.roles)


intents = discord.Intents.default()
intents.message_content = True


class ViewTrackerBot(discord.Client):
    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(intents=intents)
        self.db = db
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        register_commands(self.tree, self.db)
        try:
            synced = await self.tree.sync()
            logger.info("Synced %d global slash commands", len(synced))
        except Exception as e:
            logger.exception("Slash sync failed: %s", e)

    async def on_ready(self):
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="future of clipping - signed by the goat 1144",
            )
        )
        logger.info("Discord bot logged in as %s (id=%s)", self.user, self.user.id)


def make_code() -> str:
    return "VRFY-" + secrets.token_hex(3).upper()


def register_commands(tree: app_commands.CommandTree, db: AsyncIOMotorDatabase):
    platform_choices = [app_commands.Choice(name=p, value=p) for p in PLATFORMS]

    async def _campaign_choices(query: dict, current: str, limit: int = 25):
        """Return up to 25 Discord autocomplete choices matching `current`."""
        if current:
            query = {**query, "name": {"$regex": current, "$options": "i"}}
        items = (
            await db.campaigns.find(query, {"_id": 0, "id": 1, "name": 1})
            .sort("created_at", -1)
            .to_list(limit)
        )
        return [
            app_commands.Choice(name=f"{c['name']} ({c['id'][:8]})", value=c["id"])
            for c in items
        ]

    async def active_campaign_autocomplete(
        interaction: discord.Interaction, current: str
    ):
        q = {"status": "active"}
        if interaction.guild_id:
            q["guild_id"] = str(interaction.guild_id)
        return await _campaign_choices(q, current)

    async def my_active_campaign_autocomplete(
        interaction: discord.Interaction, current: str
    ):
        q = {
            "status": "active",
            "creator_discord_id": str(interaction.user.id),
        }
        return await _campaign_choices(q, current)

    view_tracker_action_choices = [
        app_commands.Choice(name="link", value="link"),
        app_commands.Choice(name="unlink", value="unlink"),
        app_commands.Choice(name="status", value="status"),
    ]

    review_channel_action_choices = [
        app_commands.Choice(name="link", value="link"),
        app_commands.Choice(name="unlink", value="unlink"),
        app_commands.Choice(name="status", value="status"),
    ]

    async def _tracker_total_views(
        campaign_id: Optional[str] = None, guild_id: Optional[str] = None
    ) -> int:
        match = {"status": "accepted"}
        if guild_id:
            match["guild_id"] = guild_id
        elif campaign_id:
            match["campaign_id"] = campaign_id
        else:
            return 0
        agg = await db.submissions.aggregate(
            [
                {"$match": match},
                {"$group": {"_id": None, "total": {"$sum": "$current_views"}}},
            ]
        ).to_list(1)
        return int(agg[0]["total"]) if agg else 0

    async def _refresh_view_tracker_channel(
        interaction: discord.Interaction, config: dict
    ):
        if interaction.guild is None:
            return
        if not config.get("channel_id"):
            return
        channel = interaction.guild.get_channel(int(config["channel_id"]))
        if not isinstance(channel, discord.VoiceChannel):
            return
        views = await _tracker_total_views(
            campaign_id=config.get("campaign_id"), guild_id=config.get("guild_id")
        )
        prefix = config.get("channel_name_prefix") or channel.name.split(" | ")[0]
        new_name = f"{prefix} | {views:,} views"
        if channel.name != new_name:
            try:
                await channel.edit(name=new_name, reason="Update view tracker count")
            except Exception as e:
                logger.warning("Failed to update view tracker channel name: %s", e)

    async def _refresh_all_view_tracker_channels(
        interaction: discord.Interaction, guild_id: str
    ):
        if interaction.guild is None:
            return
        configs = await db.view_trackers.find({"guild_id": guild_id}).to_list(50)
        for config in configs:
            await _refresh_view_tracker_channel(interaction, config)

    async def _get_review_channel(
        interaction: discord.Interaction, campaign_id: str
    ) -> Optional[discord.TextChannel]:
        if interaction.guild is None:
            return None
        config = await db.view_trackers.find_one(
            {"campaign_id": campaign_id}, {"_id": 0, "review_channel_id": 1}
        )
        if not config or not config.get("review_channel_id"):
            return None
        channel = interaction.guild.get_channel(int(config["review_channel_id"]))
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _notify_submitter(
        interaction: discord.Interaction, discord_id: str, accepted: bool, campaign_name: str, post_url: str
    ):
        try:
            user = await interaction.client.fetch_user(int(discord_id))
            if accepted:
                await user.send(
                    f"Your submission for campaign **{campaign_name}** has been accepted.\n"
                    f"Post: {post_url}"
                )
            else:
                await user.send(
                    f"Your submission for campaign **{campaign_name}** has been denied.\n"
                    f"Post: {post_url}"
                )
        except Exception as e:
            logger.warning("Failed to notify submitter %s: %s", discord_id, e)

    class ReviewView(discord.ui.View):
        def __init__(self, submission_id: str, submitter_id: str, campaign_name: str, campaign_id: str):
            super().__init__(timeout=None)
            self.submission_id = submission_id
            self.submitter_id = submitter_id
            self.campaign_name = campaign_name
            self.campaign_id = campaign_id
            accept = discord.ui.Button(label="Accept", style=discord.ButtonStyle.success)
            deny = discord.ui.Button(label="Deny", style=discord.ButtonStyle.danger)
            accept.callback = self.accept
            deny.callback = self.deny
            self.add_item(accept)
            self.add_item(deny)

        async def accept(self, interaction: discord.Interaction):
            if not isinstance(interaction.user, discord.Member) or not has_campaign_manager_role(
                interaction.user
            ):
                await interaction.response.send_message(
                    "Only members with the Campaign Manager role can review submissions.",
                    ephemeral=True,
                )
                return
            # Defer immediately to acknowledge the interaction and avoid the
            # "interaction failed" message if DB/network calls are slow.
            await interaction.response.defer(ephemeral=True)

            sub = await db.submissions.find_one({"id": self.submission_id}, {"_id": 0})
            if not sub:
                await interaction.followup.send("Submission not found.", ephemeral=True)
                return
            if sub.get("status") != "pending":
                await interaction.followup.send(
                    "This submission has already been reviewed.", ephemeral=True
                )
                return
            await db.submissions.update_one(
                {"id": self.submission_id},
                {"$set": {"status": "accepted", "reviewed_at": datetime.now(timezone.utc).isoformat()}},
            )
            try:
                await interaction.message.edit(
                    content=f"✅ Submission accepted by {interaction.user.display_name}.",
                    embed=None,
                    view=None,
                )
            except Exception:
                # Best-effort: if editing the message fails, still proceed.
                logger.exception("Failed to edit submission review message after accept")
            await _notify_submitter(
                interaction,
                self.submitter_id,
                True,
                self.campaign_name,
                sub["post_url"],
            )
            if interaction.guild_id is not None:
                await _refresh_all_view_tracker_channels(interaction, str(interaction.guild_id))

        async def deny(self, interaction: discord.Interaction):
            if not isinstance(interaction.user, discord.Member) or not has_campaign_manager_role(
                interaction.user
            ):
                await interaction.response.send_message(
                    "Only members with the Campaign Manager role can review submissions.",
                    ephemeral=True,
                )
                return
            await interaction.response.defer(ephemeral=True)

            sub = await db.submissions.find_one({"id": self.submission_id}, {"_id": 0})
            if not sub:
                await interaction.followup.send("Submission not found.", ephemeral=True)
                return
            if sub.get("status") != "pending":
                await interaction.followup.send(
                    "This submission has already been reviewed.", ephemeral=True
                )
                return
            await db.submissions.update_one(
                {"id": self.submission_id},
                {"$set": {"status": "denied", "reviewed_at": datetime.now(timezone.utc).isoformat()}},
            )
            try:
                await interaction.message.edit(
                    content=f"❌ Submission denied by {interaction.user.display_name}.",
                    embed=None,
                    view=None,
                )
            except Exception:
                logger.exception("Failed to edit submission review message after deny")
            await _notify_submitter(
                interaction,
                self.submitter_id,
                False,
                self.campaign_name,
                sub["post_url"],
            )

    payment_method_choices = [
        app_commands.Choice(name="PayPal", value="paypal"),
        app_commands.Choice(name="Solana", value="solana"),
    ]

    @tree.command(name="verify", description="Start verification of a social media account")
    @app_commands.describe(
        platform="Which platform", handle="Your @handle or profile URL"
    )
    @app_commands.choices(platform=platform_choices)
    async def verify_cmd(
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        handle: str,
    ):
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
            {"$set": doc},
            upsert=True,
        )
        msg = (
            f"**Step 1.** Tap the code below to copy it (long-press on mobile), "
            f"then paste it **anywhere in your `{plat}` bio** for @{norm}:\n"
            f"```\n{code}\n```\n"
            f"**Step 2.** Run `/verify-check platform:{plat} handle:{norm}` to confirm."
        )
        await interaction.followup.send(msg, ephemeral=True)

    @tree.command(name="verify-check", description="Check that your verification code is in your bio (TikTok uses Apify first)")
    @app_commands.describe(platform="Platform", handle="Your @handle")
    @app_commands.choices(platform=platform_choices)
    async def verify_check_cmd(
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        handle: str,
    ):
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
        try:
            bio = await asyncio.wait_for(fetch_bio(plat, norm), timeout=12.0)
        except asyncio.TimeoutError:
            logger.warning("fetch_bio timed out for %s @%s", plat, norm)
            bio = None
        if bio is None:
            if plat == "tiktok":
                msg = (
                    "Couldn't fetch your TikTok profile. "
                    "This verification checks TikTok bios via Apify first, so make sure your profile is public and try again later."
                )
                if not APIFY_TOKEN:
                    msg += (
                        "\n\nAlso, APIFY_API_TOKEN is not configured for this server, "
                        "so TikTok bio fetching may be limited."
                    )
            else:
                msg = "Couldn't fetch your profile (private or platform blocked the request). Try again later."
            await interaction.followup.send(msg, ephemeral=True)
            return
        code = doc["verification_code"]
        if code in bio:
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
                f"Code `{code}` not found in your bio yet. Bio fetched:\n```\n{bio[:300]}\n```",
                ephemeral=True,
            )

    @tree.command(name="create-campaign", description="Create a new view-tracking campaign")
    @app_commands.describe(
        name="Campaign name",
        goal_views="Target total views",
        payout="Payout amount in USD",
        description="Short description",
    )
    async def create_campaign_cmd(
        interaction: discord.Interaction,
        name: str,
        goal_views: int,
        payout: float,
        description: Optional[str] = "",
    ):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_campaign_manager_role(
            interaction.user
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

    @tree.command(name="end-campaign", description="End a campaign (Campaign Manager only)")
    @app_commands.describe(campaign_id="Pick an active campaign")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def end_campaign_cmd(interaction: discord.Interaction, campaign_id: str):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_campaign_manager_role(
            interaction.user
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
        subs = await db.submissions.find({"campaign_id": campaign_id}, {"_id": 0}).to_list(1000)
        total = sum(s.get("current_views", 0) for s in subs)
        await interaction.followup.send(
            f"Campaign **{camp['name']}** ended. Total tracked views: **{total:,}** across {len(subs)} submissions."
        )

    @tree.command(name="submit", description="Submit a post URL to a campaign")
    @app_commands.describe(
        campaign_id="Pick a campaign", post_url="Public post URL"
    )
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def submit_cmd(
        interaction: discord.Interaction, campaign_id: str, post_url: str
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_verified_creator_role(
            interaction.user
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
            {
                "discord_id": str(interaction.user.id),
                "platform": plat,
                "verified": True,
            },
            {"_id": 0},
        )
        if not verified:
            await interaction.followup.send(
                f"You must verify a {plat} account first via `/verify`.",
                ephemeral=True,
            )
            return
        try:
            views = await asyncio.wait_for(fetch_post_views(plat, post_url), timeout=12.0)
            views = views or 0
        except asyncio.TimeoutError:
            logger.warning("fetch_post_views timed out for %s", post_url)
            views = 0
        sub = {
            "id": secrets.token_hex(8),
            "campaign_id": campaign_id,
            "discord_id": str(interaction.user.id),
            "user_id": None,
            "social_account_id": verified["id"],
            "platform": plat,
            "post_url": post_url,
            "current_views": views,
            "status": "pending",
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.submissions.insert_one(sub)
        await interaction.followup.send(
            "Your video has been submitted and the Clipstry team will review it shortly.",
            ephemeral=True,
        )
        review_channel = await _get_review_channel(interaction, campaign_id)
        embed = discord.Embed(
            title="New submission pending review",
            description=(
                f"**Campaign:** {camp['name']}\n"
                f"**Submitted by:** {interaction.user.mention}\n"
                f"**Platform:** {plat}\n"
                f"**URL:** {post_url}\n"
                f"**Current views:** {views:,}"
            ),
            color=0x002FA7,
        )
        view = ReviewView(
            submission_id=sub["id"],
            submitter_id=sub["discord_id"],
            campaign_name=camp["name"],
            campaign_id=campaign_id,
        )
        if review_channel is not None:
            await review_channel.send(embed=embed, view=view)
        elif interaction.channel is not None:
            await interaction.channel.send(embed=embed, view=view)
            await interaction.followup.send(
                "No review channel is configured for this campaign, so the submission was posted here.",
                ephemeral=True,
            )

    @tree.command(
        name="view-tracker",
        description="Link a voice channel to a campaign and track its view total",
    )
    @app_commands.describe(
        action="Link, unlink, or show the tracked channel",
        campaign_id="Pick a campaign",
        channel="Voice channel to track",
    )
    @app_commands.choices(action=view_tracker_action_choices)
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def view_tracker_cmd(
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        campaign_id: str,
        channel: Optional[discord.VoiceChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_campaign_manager_role(
            interaction.user
        ):
            await interaction.followup.send(
                f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to manage view tracking.",
                ephemeral=True,
            )
            return
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return
        if action.value == "link":
            if channel is None:
                await interaction.followup.send(
                    "Please choose a voice channel to link.", ephemeral=True
                )
                return
            prefix = channel.name.split(" | ")[0]
            total_views = await _tracker_total_views(guild_id=str(interaction.guild_id))
            new_name = f"{prefix} | {total_views:,} views"
            try:
                await channel.edit(name=new_name, reason="Set view tracker channel")
            except Exception as e:
                logger.warning("Failed to edit voice channel name: %s", e)
                await interaction.followup.send(
                    "Could not update that voice channel. Make sure the bot has Manage Channels.",
                    ephemeral=True,
                )
                return
            await db.view_trackers.update_one(
                {"campaign_id": campaign_id},
                {
                    "$set": {
                        "campaign_id": campaign_id,
                        "guild_id": str(interaction.guild_id),
                        "channel_id": str(channel.id),
                        "channel_name_prefix": prefix,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )
            await interaction.followup.send(
                f"Linked voice channel `{channel.name}` to campaign **{camp['name']}**.",
                ephemeral=True,
            )
            return

        if action.value == "unlink":
            config = await db.view_trackers.find_one({"campaign_id": campaign_id}, {"_id": 0})
            if not config:
                await interaction.followup.send(
                    "No view tracker channel is linked to that campaign.", ephemeral=True
                )
                return
            channel_obj = interaction.guild.get_channel(int(config["channel_id"]))
            if isinstance(channel_obj, discord.VoiceChannel):
                try:
                    await channel_obj.edit(
                        name=config.get("channel_name_prefix", channel_obj.name.split(" | ")[0]),
                        reason="Unlink view tracker channel",
                    )
                except Exception as e:
                    logger.warning("Failed to restore voice channel name: %s", e)
            await db.view_trackers.delete_one({"campaign_id": campaign_id})
            await interaction.followup.send(
                f"Unlinked view tracker channel from campaign **{camp['name']}**.",
                ephemeral=True,
            )
            return

        config = await db.view_trackers.find_one({"campaign_id": campaign_id}, {"_id": 0})
        if not config:
            await interaction.followup.send(
                "No view tracker channel is linked to that campaign.", ephemeral=True
            )
            return
        channel_obj = interaction.guild.get_channel(int(config["channel_id"]))
        if not isinstance(channel_obj, discord.VoiceChannel):
            await interaction.followup.send(
                "The linked channel is not available or is not a voice channel.", ephemeral=True
            )
            return
        views = await _tracker_total_views(guild_id=str(interaction.guild_id))
        await interaction.followup.send(
            f"Campaign **{camp['name']}** is linked to `{channel_obj.name}` with {views:,} total accepted views across all campaigns.",
            ephemeral=True,
        )

    @tree.command(
        name="review-channel",
        description="Link a campaign to a review channel for submission moderation",
    )
    @app_commands.describe(
        action="Link, unlink, or show the review channel",
        campaign_id="Pick a campaign",
        channel="Text channel to send submissions to",
    )
    @app_commands.choices(action=review_channel_action_choices)
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def review_channel_cmd(
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        campaign_id: str,
        channel: Optional[discord.TextChannel] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_campaign_manager_role(
            interaction.user
        ):
            await interaction.followup.send(
                f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to manage review channels.",
                ephemeral=True,
            )
            return
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return
        if action.value == "link":
            if channel is None:
                await interaction.followup.send(
                    "Please choose a text channel to link.", ephemeral=True
                )
                return
            await db.view_trackers.update_one(
                {"campaign_id": campaign_id},
                {
                    "$set": {
                        "campaign_id": campaign_id,
                        "guild_id": str(interaction.guild_id),
                        "review_channel_id": str(channel.id),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )
            await interaction.followup.send(
                f"Linked review channel {channel.mention} to campaign **{camp['name']}**.",
                ephemeral=True,
            )
            return
        if action.value == "unlink":
            config = await db.view_trackers.find_one(
                {"campaign_id": campaign_id}, {"_id": 0, "review_channel_id": 1}
            )
            if not config or not config.get("review_channel_id"):
                await interaction.followup.send(
                    "No review channel is linked to that campaign.", ephemeral=True
                )
                return
            await db.view_trackers.update_one(
                {"campaign_id": campaign_id},
                {"$unset": {"review_channel_id": ""}},
            )
            await interaction.followup.send(
                f"Unlinked the review channel from campaign **{camp['name']}**.",
                ephemeral=True,
            )
            return
        config = await db.view_trackers.find_one(
            {"campaign_id": campaign_id}, {"_id": 0, "review_channel_id": 1}
        )
        if not config or not config.get("review_channel_id"):
            await interaction.followup.send(
                "No review channel is linked to that campaign.", ephemeral=True
            )
            return
        channel_obj = interaction.guild.get_channel(int(config["review_channel_id"]))
        if not isinstance(channel_obj, discord.TextChannel):
            await interaction.followup.send(
                "The linked channel is not available or is not a text channel.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(
            f"Campaign **{camp['name']}** is linked to {channel_obj.mention} for submissions.",
            ephemeral=True,
        )

    @tree.command(name="campaigns", description="List active campaigns in this server")
    async def campaigns_cmd(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        query = {"status": "active"}
        if interaction.guild_id:
            query["guild_id"] = str(interaction.guild_id)
        items = await db.campaigns.find(query, {"_id": 0}).to_list(25)
        if not items:
            await interaction.followup.send("No active campaigns.")
            return
        embed = discord.Embed(title="Active Campaigns", color=0x002FA7)
        for c in items:
            embed.add_field(
                name=c["name"],
                value=(
                    f"`{c['id']}` — goal {c['goal_views']:,} views — "
                    f"${c['payout_cents']/100:,.2f}"
                ),
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    @tree.command(name="payment-method", description="Set your payout payment method")
    @app_commands.describe(
        method="Pick PayPal or Solana",
        address="PayPal email or Solana wallet address",
    )
    @app_commands.choices(method=payment_method_choices)
    async def payment_method_cmd(
        interaction: discord.Interaction,
        method: app_commands.Choice[str],
        address: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(
                "This command must be used in a server or with a Discord member.",
                ephemeral=True,
            )
            return
        value = address.strip()
        if method.value == "paypal":
            if "@" not in value or "." not in value:
                await interaction.followup.send(
                    "Please provide a valid PayPal email address.",
                    ephemeral=True,
                )
                return
        elif method.value == "solana":
            if len(value) < 32 or len(value) > 64:
                await interaction.followup.send(
                    "Please provide a valid Solana wallet address.",
                    ephemeral=True,
                )
                return
        doc = {
            "id": secrets.token_hex(8),
            "discord_id": str(interaction.user.id),
            "method": method.value,
            "address": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.payment_methods.update_one(
            {"discord_id": str(interaction.user.id), "method": method.value},
            {"$set": doc},
            upsert=True,
        )
        await interaction.followup.send(
            f"Saved payment method **{method.name}**: `{value}`. Use `/manage-payment-methods` to view or remove your methods.",
            ephemeral=True,
        )

    @tree.command(name="manage-payment-methods", description="View or remove your saved payout methods")
    @app_commands.describe(
        action="View or remove saved methods",
        method="Payment method to remove",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="view", value="view"),
            app_commands.Choice(name="remove", value="remove"),
        ],
        method=payment_method_choices,
    )
    async def manage_payment_methods_cmd(
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        method: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        uid = str(interaction.user.id)
        if action.value == "remove":
            if not method:
                await interaction.followup.send(
                    "Please choose the payment method to remove.",
                    ephemeral=True,
                )
                return
            result = await db.payment_methods.delete_one(
                {"discord_id": uid, "method": method.value}
            )
            if result.deleted_count:
                await interaction.followup.send(
                    f"Removed your `{method.name}` payment method.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"No saved `{method.name}` payment method found.",
                    ephemeral=True,
                )
            return

        items = await db.payment_methods.find({"discord_id": uid}, {"_id": 0}).to_list(25)
        if not items:
            await interaction.followup.send(
                "No saved payment methods. Add one with `/payment-method`.",
                ephemeral=True,
            )
            return
        lines = [
            "**Saved payment methods:**",
        ]
        for item in items:
            lines.append(f"**{item['method'].title()}** — `{item['address']}`")
        lines.append(
            "\nTo remove one, use `/manage-payment-methods action:remove method:<method>`."
        )
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @tree.command(name="accounts", description="Show your verified social accounts")
    async def accounts_cmd(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        items = await db.social_accounts.find(
            {"discord_id": str(interaction.user.id)}, {"_id": 0}
        ).to_list(50)
        if not items:
            await interaction.followup.send(
                "No accounts. Use `/verify` to add one.", ephemeral=True
            )
            return
        lines = []
        for a in items:
            mark = "VERIFIED" if a.get("verified") else "PENDING"
            lines.append(f"`{a['platform']}` @{a['handle']} — **{mark}**")
        await interaction.followup.send("\n".join(lines), ephemeral=True)


_bot_task: Optional[asyncio.Task] = None
_bot_instance: Optional[ViewTrackerBot] = None


async def start_bot(db: AsyncIOMotorDatabase):
    global _bot_task, _bot_instance
    if not TOKEN:
        logger.warning("DISCORD_BOT_TOKEN not set; bot will not connect.")
        return
    _bot_instance = ViewTrackerBot(db)

    async def _runner():
        try:
            await _bot_instance.start(TOKEN)
        except Exception as e:
            logger.exception("Discord bot crashed: %s", e)

    _bot_task = asyncio.create_task(_runner())


async def stop_bot():
    global _bot_task, _bot_instance
    if _bot_instance is not None:
        try:
            await _bot_instance.close()
        except Exception:
            pass
    if _bot_task is not None:
        _bot_task.cancel()


def bot_status() -> dict:
    if _bot_instance is None:
        return {"running": False, "user": None}
    return {
        "running": _bot_instance.is_ready(),
        "user": str(_bot_instance.user) if _bot_instance.user else None,
    }
