"""
extra_commands.py — Payment info + Campaign stats commands for Clipstry.

This file is self-contained. It does NOT require editing the indentation
of bot.py. You only need to make two tiny additions to bot.py (see
INSTALL_INSTRUCTIONS.txt).
"""

import discord
from discord import app_commands
from datetime import datetime, timezone


def register_extra_commands(tree: app_commands.CommandTree, db, CAMPAIGN_MANAGER_ROLE: str, has_role):
    """Adds /set-payment, /payment-info, /campaign-stats, /my-stats to the bot's command tree."""

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

    @tree.command(name="set-payment", description="Register or update your payout method")
    @app_commands.describe(
        method="How you want to be paid (e.g. PayPal, Venmo, CashApp, Zelle, Bank Transfer)",
        details="Your @handle, email, or payment details for that method",
    )
    async def set_payment_cmd(interaction, method: str, details: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await db.payment_info.update_one(
            {"discord_id": str(interaction.user.id)},
            {
                "$set": {
                    "discord_id": str(interaction.user.id),
                    "method": method,
                    "details": details,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )
        await interaction.followup.send(
            f"Payment method saved: **{method}** — `{details}`\n"
            "Only Campaign Managers can look this up via `/payment-info`.",
            ephemeral=True,
        )

    @tree.command(name="payment-info", description="View a creator's saved payout method (Campaign Manager)")
    @app_commands.describe(user="The creator whose payment info you want to see")
    async def payment_info_cmd(interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(
            interaction.user, CAMPAIGN_MANAGER_ROLE
        ):
            await interaction.followup.send(
                f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to view payment info.",
                ephemeral=True,
            )
            return

        info = await db.payment_info.find_one({"discord_id": str(user.id)}, {"_id": 0})
        if not info:
            await interaction.followup.send(
                f"{user.mention} hasn't set a payment method yet (`/set-payment`).",
                ephemeral=True,
            )
            return

        embed = discord.Embed(title=f"Payment info — {user.display_name}", color=0x002FA7)
        embed.add_field(name="Method", value=info["method"], inline=True)
        embed.add_field(name="Details", value=f"`{info['details']}`", inline=True)
        embed.set_footer(text=f"Last updated {info.get('updated_at', 'unknown')}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="campaign-stats", description="View detailed stats for a campaign (Campaign Manager)")
    @app_commands.describe(campaign_id="Pick a campaign")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def campaign_stats_cmd(interaction, campaign_id: str):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(
            interaction.user, CAMPAIGN_MANAGER_ROLE
        ):
            await interaction.followup.send(
                f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to view campaign stats.",
                ephemeral=True,
            )
            return

        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return

        subs = await db.submissions.find({"campaign_id": campaign_id}, {"_id": 0}).to_list(2000)
        total_views = sum(s.get("current_views", 0) for s in subs)
        unique_creators = {s["discord_id"] for s in subs}

        per_platform = {}
        for s in subs:
            p = s.get("platform", "unknown")
            per_platform[p] = per_platform.get(p, 0) + s.get("current_views", 0)

        embed = discord.Embed(
            title=f"Campaign Stats: {camp['name']}",
            description=camp.get("description") or "",
            color=0x002FA7,
        )
        embed.add_field(name="Status", value=camp["status"], inline=True)
        embed.add_field(name="Goal", value=f"{camp['goal_views']:,} views", inline=True)
        embed.add_field(name="Total Views", value=f"{total_views:,}", inline=True)
        embed.add_field(name="Submissions", value=str(len(subs)), inline=True)
        embed.add_field(name="Unique Creators", value=str(len(unique_creators)), inline=True)
        embed.add_field(
            name="Goal Progress",
            value=f"{(total_views / camp['goal_views'] * 100) if camp['goal_views'] else 0:.1f}%",
            inline=True,
        )

        if per_platform:
            embed.add_field(
                name="By Platform",
                value="\n".join(f"{p}: {v:,}" for p, v in sorted(per_platform.items(), key=lambda x: -x[1])),
                inline=False,
            )

        top = sorted(subs, key=lambda s: s.get("current_views", 0), reverse=True)[:10]
        if top:
            lines = []
            for s in top:
                lines.append(f"<@{s['discord_id']}> — {s.get('current_views', 0):,} views — {s['post_url']}")
            embed.add_field(name="Top Submissions", value="\n".join(lines)[:1024], inline=False)

        await interaction.followup.send(embed=embed)

    class MyStatsView(discord.ui.View):
        def __init__(self, db, has_role, CAMPAIGN_MANAGER_ROLE):
            super().__init__(timeout=180)
            self.db = db
            self.has_role = has_role
            self.CAMPAIGN_MANAGER_ROLE = CAMPAIGN_MANAGER_ROLE

        @discord.ui.button(label="Analytics", emoji="📈", style=discord.ButtonStyle.secondary)
        async def analytics_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True, thinking=True)
            uid = str(interaction.user.id)
            subs = await self.db.submissions.find({"discord_id": uid}, {"_id": 0}).to_list(2000)
            total_views = sum(s.get("current_views", 0) for s in subs)
            campaigns = {s["campaign_id"] for s in subs}

            embed = discord.Embed(title="📈 Your Analytics", color=0x002FA7)
            embed.add_field(name="Total Views", value=f"{total_views:,}", inline=True)
            embed.add_field(name="Submissions", value=str(len(subs)), inline=True)
            embed.add_field(name="Campaigns Joined", value=str(len(campaigns)), inline=True)

            if subs:
                per_platform = {}
                for s in subs:
                    p = s.get("platform", "unknown")
                    per_platform[p] = per_platform.get(p, 0) + s.get("current_views", 0)
                embed.add_field(
                    name="By Platform",
                    value="\n".join(f"{p}: {v:,}" for p, v in sorted(per_platform.items(), key=lambda x: -x[1])),
                    inline=False,
                )
            else:
                embed.description = "No submissions yet. Submit a clip to a campaign to see stats here."

            await interaction.followup.send(embed=embed, ephemeral=True)

        @discord.ui.button(label="Payouts", emoji="💰", style=discord.ButtonStyle.secondary)
        async def payouts_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True, thinking=True)
            uid = str(interaction.user.id)

            info = await self.db.payment_info.find_one({"discord_id": uid}, {"_id": 0})
            subs = await self.db.submissions.find({"discord_id": uid}, {"_id": 0}).to_list(2000)

            campaign_ids = list({s["campaign_id"] for s in subs})
            campaigns = await self.db.campaigns.find(
                {"id": {"$in": campaign_ids}}, {"_id": 0, "id": 1, "payout_rate": 1, "name": 1}
            ).to_list(100) if campaign_ids else []
            rate_by_campaign = {c["id"]: c.get("payout_rate", 0) for c in campaigns}
            name_by_campaign = {c["id"]: c.get("name", "Unknown") for c in campaigns}

            embed = discord.Embed(title="💰 Your Payouts", color=0x002FA7)

            if info:
                embed.add_field(name="Payment Method", value=f"{info['method']} — `{info['details']}`", inline=False)
            else:
                embed.add_field(
                    name="Payment Method",
                    value="Not set yet. Run `/set-payment` to add your payout details.",
                    inline=False,
                )

            if subs:
                lines = []
                total_est = 0.0
                per_campaign_views = {}
                for s in subs:
                    cid = s["campaign_id"]
                    per_campaign_views[cid] = per_campaign_views.get(cid, 0) + s.get("current_views", 0)
                for cid, views in per_campaign_views.items():
                    rate = rate_by_campaign.get(cid, 0) or 0
                    est = (views / 1000) * rate
                    total_est += est
                    lines.append(f"{name_by_campaign.get(cid, cid[:8])}: {views:,} views ≈ ${est:,.2f}")
                embed.add_field(name="Estimated Earnings by Campaign", value="\n".join(lines)[:1024], inline=False)
                embed.add_field(name="Estimated Total", value=f"${total_est:,.2f}", inline=False)
                embed.set_footer(text="Estimates only — confirm final payout with your Campaign Manager.")
            else:
                embed.description = "No submissions yet, so no payout estimate to show."

            await interaction.followup.send(embed=embed, ephemeral=True)

    @tree.command(name="my-stats", description="See your personal stats and payout panel")
    async def my_stats_cmd(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Manage Your Stats",
            description="Use the buttons below to view your performance and payout info.",
            color=0x002FA7,
        )
        embed.add_field(
            name="📈  Analytics",
            value="View your total views and performance metrics",
            inline=False,
        )
        embed.add_field(
            name="💰  Payouts",
            value="View your saved payment method and estimated earnings",
            inline=False,
        )
        view = MyStatsView(db, has_role, CAMPAIGN_MANAGER_ROLE)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
