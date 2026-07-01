"""
extra_commands.py — Payment info + Campaign stats + Stats panel for Clipstry.
"""

import discord
from discord import app_commands
from datetime import datetime, timezone

POWERED_BY = "Powered by ❤️ & ☕ | www.clipstry.lovable.app"


def register_extra_commands(tree: app_commands.CommandTree, db, CAMPAIGN_MANAGER_ROLE: str, has_role):

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

    # ── /set-payment ────────────────────────────────────────────────────────
    @tree.command(name="set-payment", description="Register or update your payout method")
    @app_commands.describe(
        method="How you want to be paid (e.g. PayPal, Venmo, CashApp, Zelle, Bank Transfer)",
        details="Your @handle, email, or payment details for that method",
    )
    async def set_payment_cmd(interaction, method: str, details: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        await db.payment_info.update_one(
            {"discord_id": str(interaction.user.id)},
            {"$set": {
                "discord_id": str(interaction.user.id),
                "method": method,
                "details": details,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        await interaction.followup.send(
            f"Payment method saved: **{method}** — `{details}`\n"
            "Only Campaign Managers can look this up via `/payment-info`.",
            ephemeral=True,
        )

    # ── /payment-info ────────────────────────────────────────────────────────
    @tree.command(name="payment-info", description="View a creator's saved payout method (Campaign Manager)")
    @app_commands.describe(user="The creator whose payment info you want to see")
    async def payment_info_cmd(interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, CAMPAIGN_MANAGER_ROLE):
            await interaction.followup.send(f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to view payment info.", ephemeral=True)
            return
        info = await db.payment_info.find_one({"discord_id": str(user.id)}, {"_id": 0})
        if not info:
            await interaction.followup.send(f"{user.mention} hasn't set a payment method yet (`/set-payment`).", ephemeral=True)
            return
        embed = discord.Embed(title=f"Payment info — {user.display_name}", color=0x002FA7)
        embed.add_field(name="Method", value=info["method"], inline=True)
        embed.add_field(name="Details", value=f"`{info['details']}`", inline=True)
        embed.set_footer(text=f"Last updated {info.get('updated_at', 'unknown')}")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /campaign-stats ──────────────────────────────────────────────────────
    @tree.command(name="campaign-stats", description="View detailed stats for a campaign (Campaign Manager)")
    @app_commands.describe(campaign_id="Pick a campaign")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def campaign_stats_cmd(interaction, campaign_id: str):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, CAMPAIGN_MANAGER_ROLE):
            await interaction.followup.send(f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to view campaign stats.", ephemeral=True)
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
            lines = [f"<@{s['discord_id']}> — {s.get('current_views', 0):,} views — {s['post_url']}" for s in top]
            field_text = "\n".join(lines)
            if len(field_text) > 1024:
                field_text = field_text[:1000] + "\n...(truncated)"
            embed.add_field(name="Top Submissions", value=field_text, inline=False)
        await interaction.followup.send(embed=embed)

    # ── /payout-summary ──────────────────────────────────────────────────────
    @tree.command(name="payout-summary", description="Ready-to-pay breakdown for a campaign (Campaign Manager)")
    @app_commands.describe(campaign_id="Pick a campaign")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def payout_summary_cmd(interaction: discord.Interaction, campaign_id: str):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, CAMPAIGN_MANAGER_ROLE):
            await interaction.followup.send(f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to view payout summaries.", ephemeral=True)
            return
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return
        rate = camp.get("payout_rate", 0) or 0
        subs = await db.submissions.find({"campaign_id": campaign_id}, {"_id": 0}).to_list(2000)
        if not subs:
            await interaction.followup.send("No submissions for this campaign yet.", ephemeral=True)
            return
        per_creator_views = {}
        for s in subs:
            uid = s["discord_id"]
            per_creator_views[uid] = per_creator_views.get(uid, 0) + s.get("current_views", 0)
        creator_ids = list(per_creator_views.keys())
        payment_docs = await db.payment_info.find({"discord_id": {"$in": creator_ids}}, {"_id": 0}).to_list(len(creator_ids))
        payment_by_id = {p["discord_id"]: p for p in payment_docs}
        paid_docs = await db.payouts.find({"campaign_id": campaign_id, "discord_id": {"$in": creator_ids}}, {"_id": 0}).to_list(len(creator_ids))
        paid_by_id = {p["discord_id"]: p for p in paid_docs}
        rows = []
        total_owed = 0.0
        total_paid = 0.0
        for uid, views in sorted(per_creator_views.items(), key=lambda x: -x[1]):
            amount = (views / 1000) * rate
            total_owed += amount
            pay_info = payment_by_id.get(uid)
            method_str = f"{pay_info['method']} `{pay_info['details']}`" if pay_info else "⚠️ not set"
            paid = paid_by_id.get(uid)
            if paid:
                total_paid += paid.get("amount", 0)
                status = f"✅ Paid ${paid.get('amount', 0):,.2f}"
            else:
                status = "❌ Unpaid"
            rows.append(f"<@{uid}> — {views:,} views — ${amount:,.2f} — {method_str} — {status}")
        embed = discord.Embed(
            title=f"Payout Summary: {camp['name']}",
            description=f"Rate: ${rate:,.2f} / 1,000 views",
            color=0x002FA7,
        )
        embed.add_field(name="Total Estimated Payout", value=f"${total_owed:,.2f}", inline=True)
        embed.add_field(name="Total Already Paid", value=f"${total_paid:,.2f}", inline=True)
        embed.add_field(name="Remaining", value=f"${(total_owed - total_paid):,.2f}", inline=True)
        chunk, chunk_len, field_count = [], 0, 0
        for row in rows:
            if chunk_len + len(row) + 1 > 1000 or field_count >= 24:
                embed.add_field(name="Creators" if field_count == 0 else "\u200b", value="\n".join(chunk), inline=False)
                chunk, chunk_len = [], 0
                field_count += 1
            chunk.append(row)
            chunk_len += len(row) + 1
        if chunk and field_count < 24:
            embed.add_field(name="Creators" if field_count == 0 else "\u200b", value="\n".join(chunk), inline=False)
        await interaction.followup.send(embed=embed)

    # ── /mark-paid ──────────────────────────────────────────────────────────
    @tree.command(name="mark-paid", description="Mark a creator as paid for a campaign (Campaign Manager)")
    @app_commands.describe(campaign_id="Pick a campaign", user="The creator you paid", amount="Amount paid (USD)")
    @app_commands.autocomplete(campaign_id=active_campaign_autocomplete)
    async def mark_paid_cmd(interaction: discord.Interaction, campaign_id: str, user: discord.Member, amount: float):
        await interaction.response.defer(thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, CAMPAIGN_MANAGER_ROLE):
            await interaction.followup.send(f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to mark payouts.", ephemeral=True)
            return
        camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
        if not camp:
            await interaction.followup.send("Campaign not found.", ephemeral=True)
            return
        await db.payouts.update_one(
            {"campaign_id": campaign_id, "discord_id": str(user.id)},
            {"$set": {
                "campaign_id": campaign_id,
                "discord_id": str(user.id),
                "amount": amount,
                "paid_by": str(interaction.user.id),
                "paid_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        await interaction.followup.send(f"✅ Marked {user.mention} as paid **${amount:,.2f}** for **{camp['name']}**.")

    # ── Analytics sub-view (View Your Clips + Hide from Leaderboard) ─────────
    class AnalyticsView(discord.ui.View):
        def __init__(self, db, uid):
            super().__init__(timeout=180)
            self.db = db
            self.uid = uid

        @discord.ui.button(label="View Your Clips", emoji="🎬", style=discord.ButtonStyle.secondary)
        async def view_clips_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True, thinking=True)
            subs = await self.db.submissions.find({"discord_id": self.uid}, {"_id": 0}).to_list(50)
            if not subs:
                await interaction.followup.send("You haven't submitted any clips yet.", ephemeral=True)
                return
            lines = []
            for s in subs:
                views = s.get("current_views", 0)
                status = s.get("status", "pending")
                lines.append(f"**{status.upper()}** — {views:,} views — {s['post_url']}")
            embed = discord.Embed(title="🎬 Your Clips", color=0x002FA7)
            embed.description = "\n".join(lines)[:4096]
            embed.set_footer(text=POWERED_BY)
            await interaction.followup.send(embed=embed, ephemeral=True)

        @discord.ui.button(label="Hide name from Leaderboard", emoji="🔒", style=discord.ButtonStyle.danger)
        async def hide_leaderboard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True, thinking=True)
            doc = await self.db.leaderboard_prefs.find_one({"discord_id": self.uid}, {"_id": 0})
            currently_hidden = doc.get("hidden", False) if doc else False
            new_hidden = not currently_hidden
            await self.db.leaderboard_prefs.update_one(
                {"discord_id": self.uid},
                {"$set": {"discord_id": self.uid, "hidden": new_hidden}},
                upsert=True,
            )
            label = "shown on" if not new_hidden else "hidden from"
            await interaction.followup.send(
                f"✅ Your name is now **{label}** the leaderboard.",
                ephemeral=True,
            )

    # ── Stats panel views ────────────────────────────────────────────────────
    class StatsPanelView(discord.ui.View):
        def __init__(self, db):
            super().__init__(timeout=None)  # persistent view
            self.db = db

        @discord.ui.button(label="Analytics", emoji="📈", style=discord.ButtonStyle.secondary, custom_id="stats_panel:analytics")
        async def analytics_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.defer(ephemeral=True, thinking=True)
            uid = str(interaction.user.id)
            subs = await self.db.submissions.find({"discord_id": uid}, {"_id": 0}).to_list(2000)
            total_views = sum(s.get("current_views", 0) for s in subs)
            campaigns_joined = len({s["campaign_id"] for s in subs})
            approved = sum(1 for s in subs if s.get("status") == "approved")
            denied = sum(1 for s in subs if s.get("status") == "denied")

            # Leaderboard rank
            all_creators = await self.db.submissions.aggregate([
                {"$group": {"_id": "$discord_id", "total": {"$sum": "$current_views"}}},
                {"$sort": {"total": -1}}
            ]).to_list(10000)
            rank = next((i + 1 for i, c in enumerate(all_creators) if c["_id"] == uid), None)
            rank_display = str(rank) if rank else "N/A"

            # Total earned across all campaigns
            paid_doc = await self.db.payouts.find({"discord_id": uid}, {"_id": 0}).to_list(100)
            total_earned = sum(p.get("amount", 0) for p in paid_doc)

            embed = discord.Embed(
                title="All-time Clipping Analytics",
                color=0x57F287,
            )
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.add_field(name="🚀 Leaderboard", value=rank_display, inline=False)
            embed.add_field(name="🪙 Total Earned", value=f"${total_earned:,.2f}", inline=False)
            embed.add_field(name="🔥 Campaigns Joined", value=str(campaigns_joined), inline=False)
            embed.add_field(name="📈 Total Views", value=f"{total_views:,}", inline=False)
            embed.add_field(name="✅ Clips Approved", value=str(approved), inline=False)
            embed.add_field(name="❌ Clips Denied", value=str(denied), inline=False)
            embed.set_footer(text=POWERED_BY)

            view = AnalyticsView(self.db, uid)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        @discord.ui.button(label="Payouts", emoji="💰", style=discord.ButtonStyle.secondary, custom_id="stats_panel:payouts")
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

            embed = discord.Embed(title="💰 Your Payouts", color=0x57F287)
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            if info:
                embed.add_field(name="Payment Method", value=f"{info['method']} — `{info['details']}`", inline=False)
            else:
                embed.add_field(name="Payment Method", value="Not set yet. Run `/set-payment` to add your payout details.", inline=False)
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
                field_text = "\n".join(lines)
                if len(field_text) > 1024:
                    field_text = field_text[:1000] + "\n...(truncated)"
                embed.add_field(name="Estimated Earnings by Campaign", value=field_text, inline=False)
                embed.add_field(name="Estimated Total", value=f"${total_est:,.2f}", inline=False)
                embed.set_footer(text=f"Estimates only — confirm with your Campaign Manager.\n{POWERED_BY}")
            else:
                embed.description = "No submissions yet, so no payout estimate to show."
                embed.set_footer(text=POWERED_BY)
            await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /my-stats ───────────────────────────────────────────────────────────
    @tree.command(name="my-stats", description="See your personal stats and payout panel")
    async def my_stats_cmd(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Manage Your Stats",
            description="Use the buttons below to view your clipping performance and payout info.",
            color=0x57F287,
        )
        embed.add_field(name="📈  Analytics", value="View your total views, earnings, and performance metrics", inline=False)
        embed.add_field(name="💰  Payouts", value="View your saved payment method and estimated earnings", inline=False)
        embed.set_footer(text=POWERED_BY)
        view = StatsPanelView(db)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ── /setup-stats-panel ───────────────────────────────────────────────────
    @tree.command(name="setup-stats-panel", description="Post the stats panel in a channel (Campaign Manager)")
    @app_commands.describe(channel="The channel to post the stats panel in")
    async def setup_stats_panel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, CAMPAIGN_MANAGER_ROLE):
            await interaction.followup.send(f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to set up the stats panel.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📊 Clipstry Stats Panel",
            description=(
                "Click **Analytics** to see your all-time clipping stats — "
                "your leaderboard rank, total views, clips approved/denied, and total earned.\n\n"
                "Click **Payouts** to see your saved payment method and estimated earnings per campaign.\n\n"
                "All responses are private — only you can see them."
            ),
            color=0x57F287,
        )
        embed.set_footer(text=POWERED_BY)

        view = StatsPanelView(db)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Stats panel posted in {channel.mention}!", ephemeral=True)


    # ── Leaderboard helpers ──────────────────────────────────────────────────
    def format_views(n: int) -> str:
        if n >= 1_000_000_000:
            return f"{n / 1_000_000_000:.1f}B"
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}K"
        return str(n)

    async def build_leaderboard_embed(page: int) -> discord.Embed:
        per_page = 10
        offset = page * per_page

        # Aggregate all-time views per creator
        all_creators = await db.submissions.aggregate([
            {"$group": {"_id": "$discord_id", "total": {"$sum": "$current_views"}}},
            {"$sort": {"total": -1}}
        ]).to_list(10000)

        # Get hidden prefs
        hidden_docs = await db.leaderboard_prefs.find({"hidden": True}, {"_id": 0, "discord_id": 1}).to_list(10000)
        hidden_ids = {d["discord_id"] for d in hidden_docs}

        total = len(all_creators)
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        slice_ = all_creators[offset: offset + per_page]

        medals = {0: "🥇", 1: "🥈", 2: "🥉"}
        lines = []
        for i, entry in enumerate(slice_):
            global_rank = offset + i
            uid = entry["_id"]
            views = format_views(entry["total"])
            if uid in hidden_ids:
                name = "Hidden"
            else:
                name = f"<@{uid}>"
            rank_str = medals.get(global_rank, f"{global_rank + 1}.")
            lines.append(f"{rank_str} **{name}: {views} Views**" if global_rank < 3 else f"{rank_str} **{name}: {views} Views**")

        embed = discord.Embed(
            title="Top Clippers All Time 📈",
            description="\n".join(lines) if lines else "No clippers yet.",
            color=0x57F287,
        )
        embed.set_footer(text=f"Page {page + 1}/{total_pages} • {POWERED_BY}")
        return embed, total_pages

    class LeaderboardView(discord.ui.View):
        def __init__(self, db, page: int = 0, total_pages: int = 1, persistent: bool = False):
            super().__init__(timeout=None if persistent else 180)
            self.db = db
            self.page = page
            self.total_pages = total_pages
            self._update_buttons()

        def _update_buttons(self):
            for item in self.children:
                if hasattr(item, "custom_id"):
                    if item.custom_id == "lb:prev":
                        item.disabled = self.page <= 0
                    elif item.custom_id == "lb:next":
                        item.disabled = self.page >= self.total_pages - 1

        @discord.ui.button(label="Previous", emoji="«", style=discord.ButtonStyle.secondary, custom_id="lb:prev")
        async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = max(0, self.page - 1)
            embed, self.total_pages = await build_leaderboard_embed(self.page)
            self._update_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

        @discord.ui.button(label="Next", emoji="»", style=discord.ButtonStyle.success, custom_id="lb:next")
        async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
            self.page = min(self.total_pages - 1, self.page + 1)
            embed, self.total_pages = await build_leaderboard_embed(self.page)
            self._update_buttons()
            await interaction.response.edit_message(embed=embed, view=self)

    # ── /leaderboard ─────────────────────────────────────────────────────────
    @tree.command(name="leaderboard", description="View the all-time top clippers leaderboard")
    async def leaderboard_cmd(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        embed, total_pages = await build_leaderboard_embed(0)
        view = LeaderboardView(db, page=0, total_pages=total_pages)
        await interaction.followup.send(embed=embed, view=view)

    # ── /setup-leaderboard-panel ─────────────────────────────────────────────
    @tree.command(name="setup-leaderboard-panel", description="Post the live leaderboard in a channel (Campaign Manager)")
    @app_commands.describe(channel="The channel to post the leaderboard in")
    async def setup_leaderboard_panel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not isinstance(interaction.user, discord.Member) or not has_role(interaction.user, CAMPAIGN_MANAGER_ROLE):
            await interaction.followup.send(f"You need the **{CAMPAIGN_MANAGER_ROLE}** role to set up the leaderboard panel.", ephemeral=True)
            return
        embed, total_pages = await build_leaderboard_embed(0)
        view = LeaderboardView(db, page=0, total_pages=total_pages, persistent=True)
        await channel.send(embed=embed, view=view)
        await interaction.followup.send(f"✅ Leaderboard panel posted in {channel.mention}!", ephemeral=True)
