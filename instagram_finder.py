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

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")  # provider-specific

SERPAPI_URL = "https://serpapi.com/search.json"
REQUEST_TIMEOUT = 20

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

EXCLUDED_PATHS = {
    "p", "reel", "tv", "stories",
    "explore", "accounts", "direct",
    "about", "developer", "privacy",
    "terms", "blog"
}

# ============================
# MODELS
# ============================

class InstagramFinderRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)
    page: int = 0
    num_results: int = 10
    min_followers: Optional[int] = None  # 🔥 NEW FILTER

# ============================
# SERPAPI
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

# ============================
# DISCOVERY FILTER
# ============================

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

# ============================
# FOLLOWER ENRICHMENT (RAPIDAPI)
# ============================

def fetch_followers_rapidapi(username: str) -> Optional[int]:
    """
    Fetch follower count from RapidAPI provider.
    Provider response formats vary, so we normalize defensively.
    """
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST:
        return None

    try:
        url = f"https://{RAPIDAPI_HOST}/user"

        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST
        }

        params = {"username": username}

        r = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()

        data = r.json()

        # Try common fields safely
        for key in ("followers", "followers_count", "follower_count"):
            if key in data and isinstance(data[key], int):
                return data[key]

        # Some APIs nest data
        if "data" in data:
            for key in ("followers", "followers_count"):
                if key in data["data"]:
                    return data["data"][key]

        return None

    except Exception:
        return None

# ============================
# ROUTES
# ============================

@router.get("/")
def health():
    return {
        "status": "ok",
        "service": "instagram_finder",
        "enrichment": "rapidapi"
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

        if not username or username in seen:
            continue

        seen.add(username)

        followers = fetch_followers_rapidapi(username)

        # Optional minimum follower filter
        if req.min_followers and followers:
            if followers < req.min_followers:
                continue

        accounts.append({
            "username": username,
            "profile_url": f"https://instagram.com/{username}",
            "followers": followers
        })

    return {
        "status": "success",
        "count": len(accounts),
        "accounts": accounts
    }
