"""ViewTracker backend pytest suite covering auth, social verification, campaigns, submissions, bot."""
import os
import secrets
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://owner-verify-bot.preview.emergentagent.com"
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def new_user(s):
    email = f"test_{secrets.token_hex(4)}@vt.dev"
    pw = "testpass123"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token"] and data["user"]["email"] == email
    return {"email": email, "password": pw, "token": data["token"], "id": data["user"]["id"]}


@pytest.fixture(scope="session")
def auth_headers(new_user):
    return {"Authorization": f"Bearer {new_user['token']}"}


@pytest.fixture(scope="session")
def second_user(s):
    email = f"test_{secrets.token_hex(4)}@vt.dev"
    pw = "testpass123"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return {"email": email, "password": pw, "token": r.json()["token"]}


# ---------- Auth ----------
class TestAuth:
    def test_register_duplicate(self, s, new_user):
        r = s.post(f"{API}/auth/register", json={"email": new_user["email"], "password": "testpass123"}, timeout=20)
        assert r.status_code == 409

    def test_login_success(self, s, new_user):
        r = s.post(f"{API}/auth/login", json={"email": new_user["email"], "password": new_user["password"]}, timeout=20)
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_invalid(self, s, new_user):
        r = s.post(f"{API}/auth/login", json={"email": new_user["email"], "password": "wrong"}, timeout=20)
        assert r.status_code == 401

    def test_me(self, s, auth_headers, new_user):
        r = s.get(f"{API}/auth/me", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert r.json()["email"] == new_user["email"]

    def test_me_no_token(self, s):
        r = s.get(f"{API}/auth/me", timeout=20)
        assert r.status_code in (401, 403)


# ---------- Social Verification ----------
class TestSocial:
    def test_start_verification(self, s, auth_headers):
        r = s.post(f"{API}/social/start-verification", headers=auth_headers,
                   json={"platform": "instagram", "handle": "@instagram"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["verification_code"].startswith("VRFY-")
        assert data["handle"] == "instagram"
        assert data["verified"] is False
        pytest.account_id = data["id"]
        pytest.account_code = data["verification_code"]

    def test_start_verification_idempotent(self, s, auth_headers):
        r = s.post(f"{API}/social/start-verification", headers=auth_headers,
                   json={"platform": "instagram", "handle": "instagram"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["verification_code"] == pytest.account_code
        assert r.json()["id"] == pytest.account_id

    def test_start_verification_bad_platform(self, s, auth_headers):
        r = s.post(f"{API}/social/start-verification", headers=auth_headers,
                   json={"platform": "myspace", "handle": "x"}, timeout=20)
        assert r.status_code == 400

    def test_list_accounts(self, s, auth_headers):
        r = s.get(f"{API}/social/accounts", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert any(a["id"] == pytest.account_id for a in r.json())

    def test_verify_account_meaningful_error(self, s, auth_headers):
        # Public IG bio won't contain our code; expect 400 or 502 - NOT 500
        r = s.post(f"{API}/social/verify/{pytest.account_id}", headers=auth_headers, timeout=60)
        assert r.status_code in (400, 502), f"Expected 400/502, got {r.status_code}: {r.text}"
        body = r.json()
        assert "detail" in body and isinstance(body["detail"], str) and len(body["detail"]) > 0

    def test_delete_account(self, s, auth_headers):
        # create a throwaway to delete
        r = s.post(f"{API}/social/start-verification", headers=auth_headers,
                   json={"platform": "tiktok", "handle": "throwaway123"}, timeout=20)
        aid = r.json()["id"]
        r2 = s.delete(f"{API}/social/accounts/{aid}", headers=auth_headers, timeout=20)
        assert r2.status_code == 200
        # verify removed
        r3 = s.delete(f"{API}/social/accounts/{aid}", headers=auth_headers, timeout=20)
        assert r3.status_code == 404


# ---------- Campaigns ----------
class TestCampaigns:
    def test_create_campaign(self, s, auth_headers):
        r = s.post(f"{API}/campaigns", headers=auth_headers,
                   json={"name": "TEST_Campaign", "description": "d", "goal_views": 1000, "payout_usd": 50.0}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_Campaign"
        assert data["goal_views"] == 1000
        assert data["payout_cents"] == 5000
        assert data["status"] == "active"
        pytest.campaign_id = data["id"]

    def test_list_campaigns_active_filter(self, s):
        r = s.get(f"{API}/campaigns?status=active", timeout=20)
        assert r.status_code == 200
        assert any(c["id"] == pytest.campaign_id for c in r.json())

    def test_get_single_campaign(self, s):
        r = s.get(f"{API}/campaigns/{pytest.campaign_id}", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "total_views" in data and "submission_count" in data

    def test_submit_unverified_account_rejected(self, s, auth_headers):
        r = s.post(f"{API}/campaigns/{pytest.campaign_id}/submissions", headers=auth_headers,
                   json={"post_url": "https://www.instagram.com/p/ABC123/", "social_account_id": pytest.account_id}, timeout=30)
        assert r.status_code == 400
        assert "not verified" in r.json()["detail"].lower()

    def test_list_submissions_leaderboard(self, s):
        r = s.get(f"{API}/campaigns/{pytest.campaign_id}/submissions", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_end_campaign_forbidden_for_other_user(self, s, second_user):
        r = s.post(f"{API}/campaigns/{pytest.campaign_id}/end",
                   headers={"Authorization": f"Bearer {second_user['token']}"}, timeout=20)
        assert r.status_code == 403

    def test_end_campaign_by_creator(self, s, auth_headers):
        r = s.post(f"{API}/campaigns/{pytest.campaign_id}/end", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert r.json()["status"] == "ended"

    def test_list_campaigns_ended_filter(self, s):
        r = s.get(f"{API}/campaigns?status=ended", timeout=20)
        assert r.status_code == 200
        assert any(c["id"] == pytest.campaign_id for c in r.json())


# ---------- Bot status ----------
class TestBot:
    def test_bot_status(self, s):
        r = s.get(f"{API}/bot/status", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("running") is True
        assert data.get("user")
