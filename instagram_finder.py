import os
import re
import requests
from typing import List, Dict, Set, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# ============================
# ROUTER
# ============================

router = APIRouter(
    prefix="/instagram",
    tags=["instagram-discovery"]
)

# ============================
# CONFIG
# ============================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"
REQUEST_TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}

FOLLOWER_REGEX = re.compile(
    r'"edge_followed_by"\s*:\s*\{"count"\s*:\s*(\d+)'
)

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

EXCLUDED_PATHS = {
    "p",
    "reel",
    "tv",
    "stories",
    "explore",
    "accounts",
    "direct",
    "about",
    "developer",
    "privacy",
    "terms",
    "blog"
}

# ============================
# MODELS
# ============================

class InstagramFinderRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)
    page: int = 0
    num_results: int = 10

# ============================
# HELPERS
# ============================

def build_query(keywords: List[str]) -> str:
    block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({block})"


def serpapi_search(query: str, page: int, num: int) -> Dict:
    if not SERPAPI_KEY:
        raise HTTPException(500, "SERPAPI_KEY not set")

    r = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google",
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": num,
            "start": page * num
        },
        timeout=REQUEST_TIMEOUT
    )
    r.raise_for_status()
    return r.json()


def extract_valid_instagram_username(link: str) -> Optional[str]:
    """
    Extract ONLY real Instagram profile usernames.
    Reject posts, reels, stories, explore pages, etc.
    """
    try:
        parsed = urlparse(link)

        if "instagram.com" not in parsed.netloc:
            return None

        parts = [p for p in parsed.path.split("/") if p]

        # Must be exactly /username
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


def fetch_followers(username: str) -> Optional[int]:
    try:
        r = requests.get(
            f"https://www.instagram.com/{username}/",
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )
        match = FOLLOWER_REGEX.search(r.text)
        return int(match.group(1)) if match else None
    except Exception:
        return None

# ============================
# ROUTES
# ============================

@router.get("/")
def health():
    return {
        "status": "ok",
        "service": "instagram_finder"
    }


@router.post("/discover")
def discover(req: InstagramFinderRequest):
    data = serpapi_search(
        build_query(req.keywords),
        req.page,
        req.num_results
    )

    seen: Set[str] = set()
    accounts = []

    for item in data.get("organic_results", []):
        link = item.get("link", "")
        username = extract_valid_instagram_username(link)

        if not username:
            continue

        if username in seen:
            continue

        seen.add(username)

        accounts.append({
            "username": username,
            "profile_url": f"https://instagram.com/{username}",
            "followers": fetch_followers(username)
        })

    return {
        "status": "success",
        "count": len(accounts),
        "accounts": accounts
    }
