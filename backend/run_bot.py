"""Lightweight runner to start only the Discord bot.

Usage:
  - Ensure env vars: DISCORD_BOT_TOKEN, MONGO_URL, DB_NAME
  - Run: python backend/run_bot.py
"""
import os
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

import discord_bot

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("run_bot")


async def main():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME", "viewtracker_db")
    if not mongo_url:
        logger.error("MONGO_URL not set. Cannot start bot without MongoDB.")
        return
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    try:
        await discord_bot.start_bot(db)
        logger.info("Bot started. Press Ctrl+C to stop.")
        # Wait forever until cancelled
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    finally:
        await discord_bot.stop_bot()
        client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down.")
