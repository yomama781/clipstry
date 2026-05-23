# Deploying ViewTracker to Railway

This deploys the **backend + Discord bot** as a single Railway service. The bot runs as a background task inside the FastAPI process, so one service is all you need.

## 1. Get a MongoDB connection string (free)

Railway's add-on Mongo is paid; the cheap/free path is **MongoDB Atlas**:

1. Go to https://www.mongodb.com/cloud/atlas → create a free shared cluster (M0, 512 MB, free forever).
2. **Database Access** → Add Database User → username + password.
3. **Network Access** → Add IP Address → "Allow Access from Anywhere" (`0.0.0.0/0`).
4. **Databases → Connect → Drivers** → copy the connection string. It looks like:
   ```
   mongodb+srv://USER:PASS@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority
   ```
   Replace `USER` and `PASS` with the credentials you created.

## 2. Push the code to GitHub

If you haven't yet:
1. In Emergent, click **GitHub** (top-right) → connect → push the project.

## 3. Create the Railway service

1. Go to https://railway.app → **New Project** → **Deploy from GitHub repo** → pick your repo.
2. Railway will start building. While it builds, click the service → **Settings**:
   - **Root Directory**: `backend`
   - **Start Command** is already in `railway.json` (auto-detected). If Railway asks, use: `uvicorn server:app --host 0.0.0.0 --port $PORT`
3. **Variables tab** — add these env vars:
   ```
   DISCORD_BOT_TOKEN=<paste your bot token>
   MONGO_URL=<paste the Atlas connection string from step 1>
   DB_NAME=viewtracker_db
   JWT_SECRET=<paste any long random string, e.g. openssl rand -hex 32>
   CORS_ORIGINS=*
   ```
4. Click **Deploy** (it usually redeploys automatically when you add vars).
5. Once it shows **Active**, open the deploy logs — you should see:
   ```
   Discord bot logged in as Clipstry Bot#2969 (id=...)
   ```
   That means your bot is live 24/7.

## 4. Get the public URL

Service **Settings → Networking → Generate Domain**. You'll get something like `viewtracker-production.up.railway.app`. That's your backend URL.

## 5. (Optional) Deploy the frontend separately

The Discord bot is the always-on piece — that's now handled. For the web dashboard:

- **Easiest**: Deploy `frontend/` to **Vercel** (free, instant). In Vercel project settings, set env var `REACT_APP_BACKEND_URL` to your Railway domain (with `https://`).
- Or push the React build to Netlify / Cloudflare Pages / Railway as a second service.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bot starts and immediately exits | DISCORD_BOT_TOKEN wrong — go to Discord Developer Portal → Bot → Reset Token, paste fresh value. |
| `pymongo.errors.ServerSelectionTimeoutError` | MONGO_URL wrong, or Atlas Network Access is not set to `0.0.0.0/0`. |
| Bot connects but slash commands missing | Wait 1 hour for Discord global command cache, or kick + re-invite the bot. |
| 429 rate-limit on startup | Happens after many restarts during testing — wait a few minutes, it auto-retries. |
| Healthcheck fails on `/api/` | Ensure `Root Directory` is `backend` and start command uses `$PORT` not `8001`. |

## Cost

- **Free trial**: $5 of credit, plenty for testing.
- **Hobby plan**: $5/month flat for unlimited services that stay within $5 of usage. A single small Python service usually fits well under that.
