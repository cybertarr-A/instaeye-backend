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
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")

SERPAPI_URL = "https://serpapi.com/search.json"

MAX_ACCOUNTS = 500
TOP_ACCOUNTS = 100
DAYS_WINDOW = 30

CONCURRENCY_LIMIT = 20  # 🔥 controls parallelism safely

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
    block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({block})"


def extract_valid_instagram_username(link: str) -> Optional[str]:
    try:
        parsed = urlparse(link)
        if "instagram.com" not in parsed.netloc:
            return None

        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 1:
            return None

        username = parts[0]
        if username.lower() in EXCLUDED_PATHS:
            return None
        if not USERNAME_REGEX.match(username):
            return None

        return username
    except Exception:
        return None

# ==================================================
# ASYNC HTTP CLIENTS
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


async def fetch_posts(session, username: str) -> List[Dict]:
    try:
        since = int((datetime.utcnow() - timedelta(days=DAYS_WINDOW)).timestamp())
        async with session.get(
            f"https://{RAPIDAPI_HOST}/posts",
            headers={
                "X-RapidAPI-Key": RAPIDAPI_KEY,
                "X-RapidAPI-Host": RAPIDAPI_HOST
            },
            params={"username": username, "since": since}
        ) as r:
            r.raise_for_status()
            data = await r.json()
            return data.get("data", [])
    except Exception:
        return []

# ==================================================
# SCORING ENGINE (UNCHANGED LOGIC)
# ==================================================

def compute_vsr(likes, comments, shares, views):
    return likes * 0.5 + comments * 1.0 + shares * 1.5 + views * 0.1


def compute_vm(views, avg_views):
    return views / avg_views if avg_views else 1.0


def compute_fe(views, followers):
    return views / followers if followers else 0.0


def score_account(posts: List[Dict], followers: int) -> float:
    if not posts:
        return 0.0

    avg_views = sum(p.get("views", 0) for p in posts) / len(posts)

    scores = []
    for p in posts:
        vsr = compute_vsr(
            p.get("likes", 0),
            p.get("comments", 0),
            p.get("shares", 0),
            p.get("views", 0)
        )
        vm = compute_vm(p.get("views", 0), avg_views)
        fe = compute_fe(p.get("views", 0), followers)
        scores.append(vsr * vm * fe)

    return sum(scores) / len(scores)

# ==================================================
# PARALLEL ACCOUNT PIPELINE
# ==================================================

async def process_account(sem, session, username, min_followers):
    async with sem:
        followers = await fetch_followers(session, username)
        if min_followers and followers and followers < min_followers:
            return None

        posts = await fetch_posts(session, username)
        score = score_account(posts, followers or 0)

        return {
            "username": username,
            "followers": followers,
            "post_count": len(posts),
            "account_score": round(score, 4)
        }

# ==================================================
# ROUTES
# ==================================================

@router.post("/rank")
async def discover_and_rank(req: InstagramRankRequest):
    query = build_query(req.keywords)

    discovered: Set[str] = set()
    usernames: List[str] = []

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
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

        sem = asyncio.Semaphore(CONCURRENCY_LIMIT)

        tasks = [
            process_account(sem, session, u, req.min_followers)
            for u in usernames
        ]

        results = await asyncio.gather(*tasks)
        accounts = [r for r in results if r]

    ranked = sorted(accounts, key=lambda x: x["account_score"], reverse=True)

    return {
        "status": "success",
        "total_accounts": len(accounts),
        "top_accounts": ranked[:TOP_ACCOUNTS]
    }
