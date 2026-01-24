import os
import re
import requests
from typing import List, Dict, Any, Optional, Set
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

ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

GRAPH_BASE = "https://graph.facebook.com/v24.0"
SERPAPI_URL = "https://serpapi.com/search.json"

MAX_ACCOUNTS = 100   # Graph API practical limit
TOP_ACCOUNTS = 50

USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

EXCLUDED_PATHS = {
    "p", "reel", "tv", "stories",
    "explore", "accounts", "direct",
    "about", "developer", "privacy",
    "terms", "blog"
}

if not ACCESS_TOKEN or not IG_USER_ID:
    raise RuntimeError("IG_ACCESS_TOKEN and IG_PARENT_USER_ID must be set")

# ==================================================
# MODELS
# ==================================================

class InstagramRankRequest(BaseModel):
    keywords: List[str] = Field(..., min_items=1)

# ==================================================
# HELPERS
# ==================================================

def build_query(keywords: List[str]) -> str:
    quoted = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({quoted})"


def extract_username(link: str) -> Optional[str]:
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


def graph_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params["access_token"] = ACCESS_TOKEN
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise HTTPException(400, r.text)
    return r.json()

# ==================================================
# GRAPH API BUSINESS DISCOVERY
# ==================================================

def fetch_creator(username: str, limit: int = 25) -> Dict[str, Any]:
    fields = (
        f"business_discovery.username({username}){{"
        f"id,username,name,profile_picture_url,followers_count,"
        f"media_count,biography,website,"
        f"media.limit({limit}){{"
        f"id,caption,media_type,media_product_type,"
        f"permalink,media_url,timestamp,like_count,comments_count"
        f"}}}}"
    )

    data = graph_get(
        f"{GRAPH_BASE}/{IG_USER_ID}",
        {"fields": fields}
    )

    bd = data.get("business_discovery")
    if not bd:
        raise HTTPException(404, f"No data for @{username}")

    followers = bd.get("followers_count", 1)
    media = bd.get("media", {}).get("data", [])

    # Engagement calculation (realistic + legal)
    engagement_total = sum(
        m.get("like_count", 0) + m.get("comments_count", 0)
        for m in media
    )

    engagement_rate = round(
        (engagement_total / followers) * 100, 3
    ) if followers else 0

    return {
        "username": bd.get("username"),
        "followers": followers,
        "engagement_rate": engagement_rate,
        "post_count": len(media),
        "media": media
    }

# ==================================================
# SCORING
# ==================================================

def score_account(user: Dict[str, Any]) -> float:
    followers = user["followers"]
    er = user["engagement_rate"]
    posts = user["post_count"]

    # Balanced ranking formula
    return round(
        (followers * 0.001) +
        (er * 10) +
        (posts * 0.5),
        4
    )

# ==================================================
# ROUTE
# ==================================================

@router.post("/rank")
def discover_and_rank(req: InstagramRankRequest):
    if not SERPAPI_KEY:
        raise HTTPException(500, "SERPAPI_KEY not set")

    query = build_query(req.keywords)

    # ---- Discovery ----
    serp = requests.get(
        SERPAPI_URL,
        params={
            "engine": "google",
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": 100
        },
        timeout=30
    ).json()

    discovered: Set[str] = set()
    usernames: List[str] = []

    for item in serp.get("organic_results", []):
        u = extract_username(item.get("link", ""))
        if u and u not in discovered:
            discovered.add(u)
            usernames.append(u)
        if len(usernames) >= MAX_ACCOUNTS:
            break

    # ---- Graph API Fetch ----
    accounts = []
    for u in usernames:
        try:
            user = fetch_creator(u)
            score = score_account(user)

            accounts.append({
                "username": u,
                "followers": user["followers"],
                "engagement_rate": user["engagement_rate"],
                "post_count": user["post_count"],
                "account_score": score,
                "data_source": "graph_api"
            })

        except Exception as e:
    accounts.append({
        "username": u,
        "error": str(e),
        "data_source": "graph_api_failed"
    })

    ranked = sorted(accounts, key=lambda x: x["account_score"], reverse=True)

    return {
        "status": "success",
        "total_accounts": len(accounts),
        "top_accounts": ranked[:TOP_ACCOUNTS]
    }
