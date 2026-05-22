"""ViewTracker backend - JWT auth + campaigns + social verification + bot."""
import os
import secrets
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from auth import (  # noqa: E402
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from scrapers import (  # noqa: E402
    PLATFORMS,
    fetch_bio,
    fetch_post_views,
    detect_platform_from_url,
    normalize_handle,
    profile_url,
)
import discord_bot  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
logger = logging.getLogger("server")

mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]


@asynccontextmanager
async def lifespan(app: FastAPI):
    await discord_bot.start_bot(db)
    yield
    await discord_bot.stop_bot()
    mongo_client.close()


app = FastAPI(lifespan=lifespan)
api = APIRouter(prefix="/api")

# ===== Models =====
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    discord_id: Optional[str] = None
    created_at: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


class StartVerifyIn(BaseModel):
    platform: str
    handle: str


class SocialAccountOut(BaseModel):
    id: str
    platform: str
    handle: str
    profile_url: str
    verification_code: str
    verified: bool
    created_at: str
    verified_at: Optional[str] = None


class CampaignIn(BaseModel):
    name: str
    description: Optional[str] = ""
    goal_views: int = Field(gt=0)
    payout_usd: float = Field(ge=0)


class CampaignOut(BaseModel):
    id: str
    name: str
    description: str
    goal_views: int
    payout_cents: int
    status: str
    creator_discord_id: Optional[str] = None
    creator_user_id: Optional[str] = None
    created_at: str
    ended_at: Optional[str] = None
    total_views: int = 0
    submission_count: int = 0


class SubmissionIn(BaseModel):
    post_url: str
    social_account_id: str


class SubmissionOut(BaseModel):
    id: str
    campaign_id: str
    user_id: Optional[str]
    discord_id: Optional[str]
    social_account_id: str
    platform: str
    post_url: str
    current_views: int
    last_checked: str
    created_at: str


# ===== Helpers =====
def make_code() -> str:
    return "VRFY-" + secrets.token_hex(3).upper()


def _strip_id(d: dict) -> dict:
    d.pop("_id", None)
    return d


async def _campaign_with_stats(camp: dict) -> dict:
    subs = await db.submissions.find({"campaign_id": camp["id"]}, {"_id": 0}).to_list(5000)
    camp["total_views"] = sum(s.get("current_views", 0) for s in subs)
    camp["submission_count"] = len(subs)
    return camp


# ===== Auth =====
@api.post("/auth/register", response_model=AuthOut)
async def register(body: RegisterIn):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(409, "Email already registered")
    uid = secrets.token_hex(8)
    doc = {
        "id": uid,
        "email": body.email.lower(),
        "password_hash": hash_password(body.password),
        "discord_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(uid, doc["email"])
    return AuthOut(
        token=token,
        user=UserOut(id=uid, email=doc["email"], discord_id=None, created_at=doc["created_at"]),
    )


@api.post("/auth/login", response_model=AuthOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token(user["id"], user["email"])
    return AuthOut(
        token=token,
        user=UserOut(
            id=user["id"],
            email=user["email"],
            discord_id=user.get("discord_id"),
            created_at=user["created_at"],
        ),
    )


@api.get("/auth/me", response_model=UserOut)
async def me(current=Depends(get_current_user)):
    user = await db.users.find_one({"id": current["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(404, "User not found")
    return UserOut(
        id=user["id"],
        email=user["email"],
        discord_id=user.get("discord_id"),
        created_at=user["created_at"],
    )


# ===== Social Verification =====
@api.post("/social/start-verification", response_model=SocialAccountOut)
async def start_verification(body: StartVerifyIn, current=Depends(get_current_user)):
    plat = body.platform.lower()
    if plat not in PLATFORMS:
        raise HTTPException(400, f"Platform must be one of {PLATFORMS}")
    handle = normalize_handle(plat, body.handle)
    if not handle:
        raise HTTPException(400, "Invalid handle")

    existing = await db.social_accounts.find_one(
        {"user_id": current["user_id"], "platform": plat, "handle": handle}, {"_id": 0}
    )
    if existing and existing.get("verified"):
        return SocialAccountOut(profile_url=profile_url(plat, handle), **existing)

    if existing:
        return SocialAccountOut(profile_url=profile_url(plat, handle), **existing)

    doc = {
        "id": secrets.token_hex(8),
        "user_id": current["user_id"],
        "discord_id": None,
        "platform": plat,
        "handle": handle,
        "verification_code": make_code(),
        "verified": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verified_at": None,
    }
    await db.social_accounts.insert_one(doc)
    _strip_id(doc)
    return SocialAccountOut(profile_url=profile_url(plat, handle), **doc)


@api.post("/social/verify/{account_id}", response_model=SocialAccountOut)
async def verify_account(account_id: str, current=Depends(get_current_user)):
    acc = await db.social_accounts.find_one(
        {"id": account_id, "user_id": current["user_id"]}, {"_id": 0}
    )
    if not acc:
        raise HTTPException(404, "Account not found")
    if acc["verified"]:
        return SocialAccountOut(profile_url=profile_url(acc["platform"], acc["handle"]), **acc)
    bio = await fetch_bio(acc["platform"], acc["handle"])
    if bio is None:
        raise HTTPException(
            502,
            "Couldn't fetch the profile right now (the platform may be blocking us or the profile is private). Try again in a minute.",
        )
    if acc["verification_code"] not in bio:
        raise HTTPException(
            400,
            f"Code not found in bio yet. We pulled: \"{bio[:200]}\"",
        )
    await db.social_accounts.update_one(
        {"id": account_id},
        {"$set": {"verified": True, "verified_at": datetime.now(timezone.utc).isoformat()}},
    )
    acc["verified"] = True
    acc["verified_at"] = datetime.now(timezone.utc).isoformat()
    return SocialAccountOut(profile_url=profile_url(acc["platform"], acc["handle"]), **acc)


@api.get("/social/accounts", response_model=List[SocialAccountOut])
async def list_accounts(current=Depends(get_current_user)):
    items = await db.social_accounts.find({"user_id": current["user_id"]}, {"_id": 0}).to_list(200)
    return [
        SocialAccountOut(profile_url=profile_url(a["platform"], a["handle"]), **a) for a in items
    ]


@api.delete("/social/accounts/{account_id}")
async def delete_account(account_id: str, current=Depends(get_current_user)):
    res = await db.social_accounts.delete_one(
        {"id": account_id, "user_id": current["user_id"]}
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Account not found")
    return {"ok": True}


# ===== Campaigns =====
@api.post("/campaigns", response_model=CampaignOut)
async def create_campaign(body: CampaignIn, current=Depends(get_current_user)):
    doc = {
        "id": secrets.token_hex(8),
        "name": body.name,
        "description": body.description or "",
        "goal_views": body.goal_views,
        "payout_cents": int(body.payout_usd * 100),
        "status": "active",
        "creator_user_id": current["user_id"],
        "creator_discord_id": None,
        "guild_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
    }
    await db.campaigns.insert_one(doc)
    _strip_id(doc)
    return CampaignOut(**(await _campaign_with_stats(doc)))


@api.get("/campaigns", response_model=List[CampaignOut])
async def list_campaigns(status: Optional[str] = None):
    q = {}
    if status:
        q["status"] = status
    items = await db.campaigns.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [CampaignOut(**(await _campaign_with_stats(c))) for c in items]


@api.get("/campaigns/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign_id: str):
    camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(404, "Campaign not found")
    return CampaignOut(**(await _campaign_with_stats(camp)))


@api.post("/campaigns/{campaign_id}/end", response_model=CampaignOut)
async def end_campaign(campaign_id: str, current=Depends(get_current_user)):
    camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(404, "Campaign not found")
    if camp.get("creator_user_id") != current["user_id"]:
        raise HTTPException(403, "Only the creator can end this campaign")
    await db.campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": "ended", "ended_at": datetime.now(timezone.utc).isoformat()}},
    )
    camp["status"] = "ended"
    camp["ended_at"] = datetime.now(timezone.utc).isoformat()
    return CampaignOut(**(await _campaign_with_stats(camp)))


# ===== Submissions =====
@api.post("/campaigns/{campaign_id}/submissions", response_model=SubmissionOut)
async def submit(campaign_id: str, body: SubmissionIn, current=Depends(get_current_user)):
    camp = await db.campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(404, "Campaign not found")
    if camp["status"] != "active":
        raise HTTPException(400, "Campaign is not active")
    plat = detect_platform_from_url(body.post_url)
    if not plat:
        raise HTTPException(400, "Unsupported URL")
    acc = await db.social_accounts.find_one(
        {"id": body.social_account_id, "user_id": current["user_id"]}, {"_id": 0}
    )
    if not acc:
        raise HTTPException(404, "Social account not found")
    if not acc["verified"]:
        raise HTTPException(400, "Account is not verified")
    if acc["platform"] != plat:
        raise HTTPException(400, f"Account is for {acc['platform']} but URL is {plat}")
    views = await fetch_post_views(plat, body.post_url) or 0
    doc = {
        "id": secrets.token_hex(8),
        "campaign_id": campaign_id,
        "user_id": current["user_id"],
        "discord_id": None,
        "social_account_id": acc["id"],
        "platform": plat,
        "post_url": body.post_url,
        "current_views": views,
        "last_checked": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.submissions.insert_one(doc)
    _strip_id(doc)
    return SubmissionOut(**doc)


@api.get("/campaigns/{campaign_id}/submissions", response_model=List[SubmissionOut])
async def list_submissions(campaign_id: str):
    items = await db.submissions.find({"campaign_id": campaign_id}, {"_id": 0}).to_list(1000)
    items.sort(key=lambda x: x.get("current_views", 0), reverse=True)
    return [SubmissionOut(**s) for s in items]


@api.post("/submissions/{submission_id}/refresh", response_model=SubmissionOut)
async def refresh_submission(submission_id: str, current=Depends(get_current_user)):
    sub = await db.submissions.find_one(
        {"id": submission_id, "user_id": current["user_id"]}, {"_id": 0}
    )
    if not sub:
        raise HTTPException(404, "Submission not found")
    views = await fetch_post_views(sub["platform"], sub["post_url"]) or sub.get("current_views", 0)
    await db.submissions.update_one(
        {"id": submission_id},
        {"$set": {"current_views": views, "last_checked": datetime.now(timezone.utc).isoformat()}},
    )
    sub["current_views"] = views
    sub["last_checked"] = datetime.now(timezone.utc).isoformat()
    return SubmissionOut(**sub)


# ===== Status =====
@api.get("/")
async def root():
    return {"name": "ViewTracker", "ok": True}


@api.get("/bot/status")
async def bot_status():
    return discord_bot.bot_status()


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
