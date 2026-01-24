import os
import re
import asyncio
import aiohttp
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
    quoted = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({quoted})"


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
# ASYNC FETCHERS
# ==================================================

async def serpapi_search(session, query: str, start: int) -> Dict:
    if not SERPAPI_KEY:
        raise HTTPException(500, "SERPAPI_KEY not set")

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
        return await r.json()


async def fetch_followers(session, username: str) -> Optional[int]:
    """
    Uses RapidAPI if available.
    Safe: returns None if provider does not support it.
    """
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
        return None

    try:
        async with session.get(
            f"https://{RAPIDAPI_HOST}/statistics",
            headers={
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": RAPIDAPI_HOST
            },
            params={"username": username}
        ) as r:
            r.raise_for_status()
            data = await r.json()
            return data.get("data", {}).get("usersCount")
    except Exception:
        return None

# ==================================================
# SCORING (FALLBACK-FIRST, SAFE)
# ==================================================

def fallback_score(followers: Optional[int]) -> float:
    """
    Ensures non-zero ranking even without post data.
    """
    if not followers:
        return 1.0
    return followers * 0.01


# ==================================================
# ACCOUNT PIPELINE
# ==================================================

async def process_account(sem, session, username, min_followers):
    async with sem:
        followers = await fetch_followers(session, username)

        if min_followers and followers and followers < min_followers:
            return None

        score = fallback_score(followers)

        return {
            "username": username,
            "followers": followers,
            "post_count": 0,
            "account_score": round(score, 4),
            "data_source": "rapidapi" if followers is not None else "fallback"
        }

# ==================================================
# ROUTE
# ==================================================

@router.post("/rank")
async def discover_and_rank(req: InstagramRankRequest):
    query = build_query(req.keywords)

    discovered: Set[str] = set()
    usernames: List[str] = []

    timeout = aiohttp.ClientTimeout(total=30)
    sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        start = 0
        while len(usernames) < MAX_ACCOUNTS:
            data = await serpapi_search(session, query, start)
            start += 20

            for item in data.get("organic_results", []):
                username = extract_valid_instagram_username(item.get("link", ""))
                if username and username not in discovered:
                    discovered.add(username)
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
