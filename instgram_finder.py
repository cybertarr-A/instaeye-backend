import os
import requests
import traceback
from typing import List, Dict, Set

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"
GOOGLE_ENGINE = "google"

if not SERPAPI_KEY:
    print("⚠️ WARNING: SERPAPI_KEY not set (service will fail on requests)")

REQUEST_TIMEOUT = 30

# --------------------------------------------------
# APP INIT
# --------------------------------------------------

app = FastAPI(
    title="Instagram Account Discovery API",
    version="1.1.0",
    description="Discover public Instagram accounts via Google index (SerpAPI)"
)

# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class InstagramFinderRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)
    page: int = Field(default=0, ge=0)
    num_results: int = Field(default=10, ge=1, le=100)

# --------------------------------------------------
# UTILS
# --------------------------------------------------

def build_instagram_google_query(keywords: List[str]) -> str:
    """
    Example:
    site:instagram.com ("plumber" OR "plumbing")
    """
    block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({block})"


def normalize_instagram_url(url: str) -> str:
    """
    Cleans tracking params and trailing slashes
    """
    clean = url.split("?")[0].rstrip("/")
    return clean


def extract_username(profile_url: str) -> str:
    """
    Extracts username from Instagram profile URL
    """
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

    response = requests.get(
        SERPAPI_URL,
        params=params,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()
    return response.json()


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

        # Deduplicate by username
        if username in seen_users:
            continue

        seen_users.add(username)

        profiles.append({
            "username": username,
            "profile_url": clean_url,
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
        "version": "1.1.0"
    }


@app.post("/discover")
def discover_instagram_accounts(req: InstagramFinderRequest):
    """
    Discover public Instagram accounts using Google index via SerpAPI
    """

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
            "requested_results": req.num_results,
            "total_found": len(accounts),
            "accounts": accounts
        }

    except requests.HTTPError as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=502,
            detail="SerpAPI request failed"
        )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
