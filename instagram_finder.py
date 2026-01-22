import os
import re
import requests
import traceback
from typing import List, Dict, Set, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"
GOOGLE_ENGINE = "google"

REQUEST_TIMEOUT = 30
INSTAGRAM_PROFILE_URL = "https://www.instagram.com/{}/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}

# --------------------------------------------------
# APP INIT
# --------------------------------------------------

app = FastAPI(
    title="Instagram Account Discovery API",
    version="2.0.0",
    description="Discover public Instagram accounts + follower counts"
)

# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class InstagramFinderRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)
    page: int = Field(default=0, ge=0)
    num_results: int = Field(default=10, ge=1, le=50)

# --------------------------------------------------
# UTILS
# --------------------------------------------------

def build_instagram_google_query(keywords: List[str]) -> str:
    block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({block})"


def normalize_instagram_url(url: str) -> str:
    return url.split("?")[0].rstrip("/")


def extract_username(profile_url: str) -> str:
    return profile_url.rstrip("/").split("/")[-1]


# --------------------------------------------------
# SERPAPI SEARCH
# --------------------------------------------------

def serpapi_search(query: str, page: int, num_results: int) -> Dict:
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY not configured")

    params = {
        "engine": GOOGLE_ENGINE,
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": num_results,
        "start": page * num_results
    }

    r = requests.get(SERPAPI_URL, params=params, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


# --------------------------------------------------
# FOLLOWER SCRAPER
# --------------------------------------------------

FOLLOWER_REGEX = re.compile(
    r'"edge_followed_by"\s*:\s*\{"count"\s*:\s*(\d+)'
)

def fetch_instagram_followers(username: str) -> Optional[int]:
    try:
        url = INSTAGRAM_PROFILE_URL.format(username)
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)

        if r.status_code != 200:
            return None

        match = FOLLOWER_REGEX.search(r.text)
        if not match:
            return None

        return int(match.group(1))

    except Exception:
        return None


# --------------------------------------------------
# RESULT NORMALIZER
# --------------------------------------------------

def extract_instagram_profiles(serp_data: Dict) -> List[Dict]:
    profiles: List[Dict] = []
    seen_users: Set[str] = set()

    for item in serp_data.get("organic_results", []):
        link = item.get("link", "")

        if "instagram.com/" not in link:
            continue

        clean_url = normalize_instagram_url(link)
        username = extract_username(clean_url)

        if username in seen_users:
            continue

        seen_users.add(username)

        followers = fetch_instagram_followers(username)

        profiles.append({
            "username": username,
            "profile_url": clean_url,
            "followers": followers,
            "title": item.get("title"),
            "snippet": item.get("snippet"),
            "source": "google_index"
        })

    return profiles


# --------------------------------------------------
# ROUTES
# --------------------------------------------------

@app.get("/")
def health():
    return {
        "status": "ok",
        "service": "instagram_finder",
        "version": "2.0.0"
    }


@app.post("/discover")
def discover_instagram_accounts(req: InstagramFinderRequest):
    try:
        query = build_instagram_google_query(req.keywords)

        serp_data = serpapi_search(
            query=query,
            page=req.page,
            num_results=req.num_results
        )

        accounts = extract_instagram_profiles(serp_data)

        return {
            "status": "success",
            "query_used": query,
            "page": req.page,
            "results": len(accounts),
            "accounts": accounts
        }

    except requests.HTTPError:
        traceback.print_exc()
        raise HTTPException(status_code=502, detail="SerpAPI request failed")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
