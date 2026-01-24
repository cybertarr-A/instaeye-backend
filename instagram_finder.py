import os
import re
import asyncio
import aiohttp
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# ================================
# ROUTER
# ================================
router = APIRouter(
    prefix="/instagram",
    tags=["instagram-discovery-ranking"]
)

# ================================
# ENV CONFIG
# ================================
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PARENT_USER_ID = os.getenv("IG_PARENT_USER_ID")

GRAPH_BASE = "https://graph.facebook.com/v24.0"
SERPAPI_URL = "https://serpapi.com/search.json"

MAX_ACCOUNTS = 300
TOP_ACCOUNTS = 50
CONCURRENCY_LIMIT = 15

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

EXCLUDED_PATHS = {
    "p", "reel", "tv", "stories",
    "explore", "accounts", "direct",
    "about", "developer", "privacy",
    "terms", "blog"
}

# ================================
# MODELS
# ================================
class InstagramRankRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)
    min_followers: Optional[int] = None

# ================================
# HELPERS
# ================================
def build_query(keywords: List[str]) -> str:
    quoted = " OR ".join([f'"{k}"' for k in keywords])
    return f"site:instagram.com ({quoted})"



def extract_username(link: str) -> Optional[str]:
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

# ================================
# SERPAPI
# ================================
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

# ================================
# GRAPH API (BUSINESS DISCOVERY)
# ================================
async def fetch_graph_stats(session, username: str) -> Optional[Dict]:
    if not IG_ACCESS_TOKEN or not IG_PARENT_USER_ID:
        return None

    url = f"{GRAPH_BASE}/{IG_PARENT_USER_ID}"
    params = {
        "fields": (
            f"business_discovery.username({username}){{"
            f"username,followers_count,media_count"
            f"}}"
        ),
        "access_token": IG_ACCESS_TOKEN
    }

    async with session.get(url, params=params) as r:
        if r.status != 200:
            return None

        data = await r.json()
        return data.get("business_discovery")

# ================================
# SCORING
# ================================
def compute_score(followers: Optional[int], media_count: Optional[int]) -> float:
    if not followers:
        return 1.0
    return round((followers * 0.7) + ((media_count or 0) * 5), 2)

# ================================
# PIPELINE
# ================================
async def process_account(sem, session, username, min_followers):
    async with sem:
        graph = await fetch_graph_stats(session, username)

        if not graph:
            return {
                "username": username,
                "followers": None,
                "score": 1.0,
                "source": "fallback"
            }

        followers = graph.get("followers_count", 0)
        media_count = graph.get("media_count", 0)

        if min_followers and followers < min_followers:
            return None

        return {
            "username": username,
            "followers": followers,
            "media_count": media_count,
            "score": compute_score(followers, media_count),
            "source": "graph_api"
        }

# ================================
# ROUTE
# ================================
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

            for r in data.get("organic_results", []):
                u = extract_username(r.get("link", ""))
                if u and u not in discovered:
                    discovered.add(u)
                    usernames.append(u)

            if not data.get("organic_results"):
                break

        tasks = [
            process_account(sem, session, u, req.min_followers)
            for u in usernames
        ]

        results = [r for r in await asyncio.gather(*tasks) if r]

    ranked = sorted(results, key=lambda x: x["score"], reverse=True)

    return {
        "status": "success",
        "total_accounts": len(results),
        "top_accounts": ranked[:TOP_ACCOUNTS]
    }
