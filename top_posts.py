import os
import requests
from datetime import datetime, timedelta
from dateutil.parser import parse
from typing import Dict, Any, List

# ----------------------------
# Instagram API credentials (use Railway ENV VARS)
# ----------------------------
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PARENT_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_URL = "https://graph.facebook.com/v19.0"


# ----------------------------
# Helpers
# ----------------------------
def safe_json(response: requests.Response) -> Dict[str, Any]:
    try:
        return response.json()
    except Exception:
        return {}


def get_media_insights(media_id: str) -> Dict[str, int]:
    """Fetch plays, shares and saved metrics for a media (safe)."""
    url = f"{GRAPH_URL}/{media_id}/insights"
    params = {
        "metric": "video_views,shares,saved",
        "access_token": ACCESS_TOKEN
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = safe_json(response)
    except Exception:
        return {"plays": 0, "shares": 0, "saved": 0}

    insights = {"plays": 0, "shares": 0, "saved": 0}

    for metric in data.get("data", []):
        name = metric.get("name")
        value = metric.get("values", [{}])[0].get("value", 0)

        if name == "video_views":
            insights["plays"] = value
        elif name == "shares":
            insights["shares"] = value
        elif name == "saved":
            insights["saved"] = value

    return insights


def get_follower_count(username: str) -> int:
    url = f"{GRAPH_URL}/{IG_PARENT_USER_ID}"
    params = {
        "fields": f"business_discovery.username({username}){{followers_count}}",
        "access_token": ACCESS_TOKEN
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        data = safe_json(r)
        return data.get("business_discovery", {}).get("followers_count", 0)
    except Exception:
        return 0


def compute_final_score(post: Dict[str, Any], avg_views_30d: float, followers: int) -> float:
    likes = post["likes"]
    comments = post["comments"]
    shares = post["shares"]
    views = post["plays"]

    # Step 1 — VSR
    vsr = (comments * 10) + (shares * 10) + (likes * 3) + (views * 0.1)

    # Step 2 — VM
    if avg_views_30d > 0:
        vm = views / avg_views_30d
    else:
        vm = 1

    # Step 3 — FE
    if followers > 0:
        fe = views / followers
    else:
        fe = 0

    return round(vsr * vm * fe, 4)


# ----------------------------
# Core Logic
# ----------------------------
def fetch_top_posts_by_username(username: str, limit: int = 5) -> Dict[str, Any]:
    """Fetch top IG posts from the last 30 days ranked by Final Engagement Score."""

    if not ACCESS_TOKEN or not IG_PARENT_USER_ID:
        return {
            "status": "error",
            "reason": "missing_env",
            "message": "Instagram API credentials are not configured."
        }

    since_date = datetime.utcnow() - timedelta(days=30)
    since_timestamp = int(since_date.timestamp())

    url = f"{GRAPH_URL}/{IG_PARENT_USER_ID}"
    params = {
        "fields": (
            f"business_discovery.username({username})"
            "{media{id,media_type,caption,like_count,comments_count,timestamp,permalink}}"
        ),
        "access_token": ACCESS_TOKEN
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        data = safe_json(response)
    except Exception as e:
        return {
            "status": "error",
            "reason": "request_failed",
            "message": str(e)
        }

    if "error" in data:
        return {
            "status": "error",
            "reason": "graph_api_error",
            "message": data["error"].get("message", "Unknown Graph API error"),
            "code": data["error"].get("code"),
            "subcode": data["error"].get("error_subcode")
        }

    if "business_discovery" not in data:
        return {
            "status": "error",
            "reason": "business_discovery_unavailable",
            "message": "Account must be Business/Creator and connected to this app."
        }

    media = data.get("business_discovery", {}).get("media", {}).get("data", [])
    recent_posts: List[Dict[str, Any]] = []

    for post in media:
        try:
            post_time = parse(post["timestamp"])
        except Exception:
            continue

        if post_time.timestamp() < since_timestamp:
            continue

        likes = post.get("like_count", 0)
        comments = post.get("comments_count", 0)

        insights = {"plays": 0, "shares": 0, "saved": 0}

        if post.get("media_type") in ("VIDEO", "REEL"):
            insights = get_media_insights(post["id"])

        recent_posts.append({
            "post_id": post.get("id"),
            "caption": post.get("caption", ""),
            "likes": likes,
            "comments": comments,
            "plays": insights["plays"],
            "shares": insights["shares"],
            "saved": insights["saved"],
            "permalink": post.get("permalink"),
            "timestamp": post.get("timestamp"),
            "media_type": post.get("media_type")
        })

    # ---- Average views (last 30 days) ----
    view_samples = [p["plays"] for p in recent_posts if p["plays"] > 0]
    avg_views_30d = sum(view_samples) / len(view_samples) if view_samples else 0

    # ---- Followers ----
    followers = get_follower_count(username)

    # ---- Final Score ----
    for p in recent_posts:
        p["final_score"] = compute_final_score(p, avg_views_30d, followers)

    # ---- Sort by Final Engagement Score ----
    recent_posts.sort(key=lambda x: x["final_score"], reverse=True)

    return {
        "status": "success",
        "username": username,
        "followers": followers,
        "avg_views_30d": round(avg_views_30d, 2),
        "posts_returned": min(len(recent_posts), limit),
        "top_posts": recent_posts[:limit]
    }


# ----------------------------
# MAIN ENTRY FOR FASTAPI
# ----------------------------
def get_top_posts(username: str, limit: int = 5) -> Dict[str, Any]:
    """
    FastAPI-safe entry:
    - NEVER raises raw Exception
    - ALWAYS returns JSON
    """
    return fetch_top_posts_by_username(username, limit)
