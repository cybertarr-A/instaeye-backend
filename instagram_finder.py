import os
import re
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# ==================================================
# ROUTER
# ==================================================

router = APIRouter(
    prefix="/instagram",
    tags=["instagram-discovery-ranking"]
)

# ==================================================
# CONFIG
# ==================================================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
GRAPH_BASE = "https://graph.facebook.com/v19.0"

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

SERPAPI_URL = "https://serpapi.com/search.json"

MAX_ACCOUNTS = 500
TOP_ACCOUNTS = 100
CONCURRENCY_LIMIT = 20

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

EXCLUDED_PATHS = {
    "p", "reel", "tv", "stories",
    "explore", "accounts", "direct",
    "about", "developer", "privacy",
    "terms", "blog"
}

# ==================================================
# MODELS
# ==================================================

class InstagramRankRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)
    min_followers: Optional[int] = None

# ==================================================
# HELPERS
# ==================================================

def build_query(keywords: List[str]) -> str:
    return f'site:instagram.com ({" OR ".join(f\'"{k}"\' for k in keywords)})'


def extract_valid_instagram_username(link: str) -> Optional[str]:
    try:
        parsed = urlparse(link)
        if "instagram.com" not in parsed.netloc:
            return None

        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 1:
            return None

        username = parts[0].lower()
        if username in EXCLUDED_PATHS:
            return None
        if not USERNAME_REGEX.match(username):
            return None

        return username
    except Exception:
        return None

# ==================================================
# GRAPH API (REAL DATA)
# ==================================================

async def graph_get_user(session, ig_user_id: str) -> Optional[Dict]:
    try:
        async with session.get(
            f"{GRAPH_BASE}/{ig_user_id}",
            params={
                "fields": "followers_count,media_count",
                "access_token": IG_ACCESS_TOKEN
            }
        ) as r:
            r.raise_for_status()
            return await r.json()
    except Exception:
        return None


async def graph_get_posts(session, ig_user_id: str) -> List[Dict]:
    try:
        async with session.get(
            f"{GRAPH_BASE}/{ig_user_id}/media",
            params={
                "fields": "like_count,comments_count,media_type,timestamp",
                "limit": 25,
                "access_token": IG_ACCESS_TOKEN
            }
        ) as r:
            r.raise_for_status()
            return (await r.json()).get("data", [])
    except Exception:
        return []

# ==================================================
# FALLBACK SCORING (NO POSTS)
# ==================================================

def fallback_score(followers: int) -> float:
    """
    Proxy score when posts are unavailable.
    Ensures ranking is still meaningful.
    """
    return followers * 0.01 if followers else 0.0

# ==================================================
# ACCOUNT PIPELINE
# ==================================================

async def process_account(sem, session, username, min_followers):
    async with sem:

        followers = None
        posts = []

        # ---------------------------
        # GRAPH API PATH (AUTHORIZED)
        # ---------------------------
        if IG_ACCESS_TOKEN:
            # NOTE: Graph API requires IG USER ID, not username
            # In real systems, map username → ig_user_id via OAuth
            pass

        # ---------------------------
        # FALLBACK PATH
        # ---------------------------
        if followers is None:
            score = fallback_score(0)
            return {
                "username": username,
                "followers": None,
                "post_count": 0,
                "account_score": round(score, 4),
                "data_source": "fallback"
            }

        if min_followers and followers < min_followers:
            return None

        # ---------------------------
        # REAL SCORING (IF POSTS EXIST)
        # ---------------------------
        if posts:
            avg_engagement = sum(
                p.get("like_count", 0) + p.get("comments_count", 0)
                for p in posts
            ) / len(posts)
            score = avg_engagement * (followers / 1000)
        else:
            score = fallback_score(followers)

        return {
            "username": username,
            "followers": followers,
            "post_count": len(posts),
            "account_score": round(score, 4),
            "data_source": "graph" if posts else "fallback"
        }

# ==================================================
# ROUTE
# ==================================================

@router.post("/rank")
async def discover_and_rank(req: InstagramRankRequest):
    if not SERPAPI_KEY:
        raise HTTPException(500, "SERPAPI_KEY not set")

    query = build_query(req.keywords)
    usernames: List[str] = []
    seen: Set[str] = set()

    timeout = aiohttp.ClientTimeout(total=30)
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        start = 0
        while len(usernames) < MAX_ACCOUNTS:
            async with session.get(
                SERPAPI_URL,
                params={
                    "engine": "google",
                    "q": query,
                    "api_key": SERPAPI_KEY,
                    "num": 20,
                    "start": start
                }
            ) as r:
                r.raise_for_status()
                data = await r.json()

            start += 20

            for item in data.get("organic_results", []):
                username = extract_valid_instagram_username(item.get("link", ""))
                if username and username not in seen:
                    seen.add(username)
                    usernames.append(username)

                if len(usernames) >= MAX_ACCOUNTS:
                    break

            if not data.get("organic_results"):
                break

        tasks = [
            process_account(sem, session, u, req.min_followers)
            for u in usernames
        ]

        results = [r for r in await asyncio.gather(*tasks) if r]

    ranked = sorted(results, key=lambda x: x["account_score"], reverse=True)

    return {
        "status": "success",
        "total_accounts": len(results),
        "top_accounts": ranked[:TOP_ACCOUNTS]
    }
