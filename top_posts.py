import os
import requests
from datetime import datetime, timedelta
from dateutil.parser import parse
from typing import Dict, Any, List

# Instagram API credentials (use Railway ENV VARS)
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PARENT_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_URL = "https://graph.facebook.com/v19.0"


def safe_json(response: requests.Response) -> Dict[str, Any]:
    """Safely parse JSON without crashing."""
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


def fetch_top_posts_by_username(username: str, limit: int = 5) -> Dict[str, Any]:
    """Fetch top IG posts from the last 14 days for a given username (safe)."""

    if not ACCESS_TOKEN or not IG_PARENT_USER_ID:
        return {
            "status": "error",
            "reason": "missing_env",
            "message": "Instagram API credentials are not configured."
        }

    since_date = datetime.utcnow() - timedelta(days=14)
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

    # Instagram Graph API error handling
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
            "message": (
                "Username is not a Business/Creator account "
                "or not connected to this Instagram app."
            )
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
        engagement = likes + comments

        insights = {"plays": 0, "shares": 0, "saved": 0}

        if post.get("media_type") in ("VIDEO", "REEL"):
            insights = get_media_insights(post["id"])
            engagement += insights["plays"] + insights["shares"]

        recent_posts.append({
            "post_id": post.get("id"),
            "caption": post.get("caption", ""),
            "likes": likes,
            "comments": comments,
            "plays": insights["plays"],
            "shares": insights["shares"],
            "saved": insights["saved"],
            "engagement_score": engagement,
            "permalink": post.get("permalink"),
            "timestamp": post.get("timestamp"),
            "media_type": post.get("media_type")
        })

    recent_posts.sort(key=lambda x: x["engagement_score"], reverse=True)

    return {
        "status": "success",
        "username": username,
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
