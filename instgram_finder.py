import os
import requests
import traceback
from typing import List, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"
GOOGLE_ENGINE = "google"

if not SERPAPI_KEY:
    print("⚠️ WARNING: SERPAPI_KEY not set")

# --------------------------------------------------
# APP INIT
# --------------------------------------------------

app = FastAPI(
    title="Instagram Finder",
    version="1.0.0"
)

# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class InstagramFinderRequest(BaseModel):
    keywords: List[str]
    page: int = 0
    num_results: int = 10


# --------------------------------------------------
# QUERY BUILDER
# --------------------------------------------------

def build_instagram_google_query(keywords: List[str]) -> str:
    """
    site:instagram.com ("plumber" OR "plumbing")
    """
    block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({block})"


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
        timeout=30
    )

    response.raise_for_status()
    return response.json()


# --------------------------------------------------
# RESULT NORMALIZER
# --------------------------------------------------

def extract_instagram_profiles(serp_data: Dict) -> List[Dict]:
    profiles = []

    for item in serp_data.get("organic_results", []):
        link = item.get("link", "")

        if "instagram.com" not in link:
            continue

        profiles.append({
            "profile_url": link.split("?")[0].rstrip("/"),
            "title": item.get("title"),
            "snippet": item.get("snippet")
        })

    return profiles


# --------------------------------------------------
# ROUTES
# --------------------------------------------------

@app.get("/")
def health():
    return {"status": "instagram_finder running"}


@app.post("/discover")
def discover_instagram_accounts(req: InstagramFinderRequest):
    """
    Discover Instagram accounts using Google index via SerpAPI
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
            "total_found": len(accounts),
            "accounts": accounts
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
