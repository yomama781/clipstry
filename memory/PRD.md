# ViewTracker — Discord Bot for Social Campaigns

## Problem Statement
"A bot that tracks social media views and verifies that the account they said they own is actually theirs by putting a code in bio that the bot gives them and verifies that they did put that code they were given in their bio proving they actually own the social media account and also a /create-campaign command and /end-campaign command."

## Architecture
- **Backend**: FastAPI (port 8001) with MongoDB. Discord.py bot runs as a background task on FastAPI lifespan startup, sharing the same Mongo client.
- **Frontend**: React (CRA + Tailwind) — Swiss-Brutalist design system.
- **Auth**: JWT email/password (bcrypt).
- **Bot**: discord.py 2.7, 7 global slash commands.
- **Scraping**: httpx + BeautifulSoup, OG meta + JSON-LD fallback. Best-effort (public bios + view counts).

## User Personas
1. **Creator** — has TikTok/IG/X/YouTube accounts, wants to join campaigns and earn payouts based on views.
2. **Sponsor/Org** — runs Discord server, launches view-driven promo campaigns with a payout pool.

## Core Requirements (static)
- Bio-code verification: bot issues a `VRFY-XXXXXX` code, user pastes in bio, bot scrapes bio to confirm.
- `/create-campaign` and `/end-campaign` slash commands.
- Track views on submitted posts.
- Multi-platform: Instagram, TikTok, Twitter/X, YouTube.

## Implemented (2026-05-22)
- JWT auth: register / login / me.
- Social verification: start-verification → code, verify → bio scrape, list, delete.
- Campaigns: create, list (with status filter), get, end (creator-only).
- Submissions: submit (requires verified account on matching platform), list (leaderboard), refresh views.
- Discord bot slash commands: /verify, /verify-check, /create-campaign, /end-campaign, /submit, /campaigns, /accounts. Synced globally; bot connects on startup.
- Web dashboard: Landing, Login, Register, Dashboard (verify wizard + accounts + campaigns), Campaigns list (with filter + progress bars), Campaign Detail (leaderboard + submit form + end button), Create Campaign, Bot Commands reference page.
- Bot status endpoint: GET /api/bot/status.
- Backend test suite: 20/20 passing (auth, social, campaigns, submissions, bot status).

## Backlog
### P0
- Web ↔ Discord identity linking (currently Discord users and web users are separate; add `/link` command + dashboard step so a single user owns both).
- Periodic re-scrape of submission views (cron / background scheduler) so leaderboards update without manual refresh.

### P1
- Per-creator payout calculation (proportional share by views).
- Twitter/X scraping improvements — currently limited without auth (consider syndication endpoint or NITTER mirror).
- Rate limiting on /auth and /verify endpoints.
- Stale-views indicator in UI when scrape fails.

### P2
- CSV export of campaign results.
- Discord rich embeds + ephemeral progress updates.
- Multi-creator role-based campaign management.
