import os
import requests
from datetime import datetime, timedelta
from dateutil.parser import parse

# Instagram API credentials (Railway ENV VARS)
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PARENT_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_URL = "https://graph.facebook.com/v19.0"


# ----------------------------
# SAFETY CHECKS
# ----------------------------
if not ACCESS_TOKEN or not IG_PARENT_USER_ID:
    raise RuntimeError(
        "Missing IG_ACCESS_TOKEN or IG_PARENT_USER_ID in environment variables"
    )


# ----------------------------
# HELPERS
# ----------------------------
def get_media_insights(media_id: str):
    """Fetch plays, shares and saved metrics for a media."""
    url = f"{GRAPH_URL}/{media_id}/insights"
    params = {
        "metric": "video_views,shares,saved",
        "access_token": ACCESS_TOKEN,
    }

    r = requests.get(url, timeout=20)
    data = r.json()

    insights = {"plays": 0, "shares": 0, "saved": 0}

    if isinstance(data, dict) and "data" in data:
        for metric in data["data"]:
            name = metric.get("name")
            value = metric.get("values", [{}])[0].get("value", 0)

            if name == "video_views":
                insights["plays"] = value
            elif name == "shares":
                insights["shares"] = value
            elif name == "saved":
                insights["saved"] = value

    return insights


# ----------------------------
# CORE LOGIC
# ----------------------------
def fetch_top_posts_by_username(username: str, limit: int = 5):
    """
    Fetch top IG posts from the last 14 days.
    Returns either:
    - {"mode": "success", "posts": [...]}
    - {"mode": "restricted", "reason": "..."}
    """

    since_date = datetime.utcnow() - timedelta(days=14)
    since_ts = int(since_date.timestamp())

    url = f"{GRAPH_URL}/{IG_PARENT_USER_ID}"
    params = {
        "fields": (
            f"business_discovery.username({username})"
            "{media{id,media_type,caption,like_count,comments_count,timestamp,permalink}}"
        ),
        "access_token": ACCESS_TOKEN,
    }

    r = requests.get(url, timeout=20)
    data = r.json()

    # 🚫 ACCESS DENIED / NOT BUSINESS ACCOUNT
    if not isinstance(data, dict) or "business_discovery" not in data:
        return {
            "mode": "restricted",
            "reason": "instagram_permission_denied",
            "message": (
                "Username is not a Business/Creator account "
                "or not connected to this Instagram app."
            ),
        }

    media = data["business_discovery"].get("media", {}).get("data", [])
    recent_posts = []

    for post in media:
        post_time = parse(post["timestamp"])
        if post_time.timestamp() < since_ts:
            continue

        likes = post.get("like_count", 0)
        comments = post.get("comments_count", 0)
        engagement = likes + comments

        insights = {"plays": None, "shares": None, "saved": None}

        if post.get("media_type") in ("VIDEO", "REEL"):
            insights = get_media_insights(post["id"])
            engagement += insights["plays"] + insights["shares"]

        recent_posts.append(
            {
                "post_id": post["id"],
                "caption": post.get("caption", ""),
                "likes": likes,
                "comments": comments,
                "plays": insights["plays"],
                "shares": insights["shares"],
                "saved": insights["saved"],
                "engagement_score": engagement,
                "permalink": post["permalink"],
                "timestamp": post["timestamp"],
                "media_type": post.get("media_type"),
            }
        )

    recent_posts.sort(key=lambda x: x["engagement_score"], reverse=True)

    return {
        "mode": "success",
        "posts": recent_posts[:limit],
    }


# ----------------------------
# FASTAPI ENTRY POINT
# ----------------------------
def get_top_posts(username: str, limit: int = 5):
    """
    Stable response for FastAPI / n8n
    NEVER raises expected errors
    """

    result = fetch_top_posts_by_username(username, limit)

    if result["mode"] == "restricted":
        return {
            "status": "restricted",
            "username": username,
            "reason": result["reason"],
            "message": result["message"],
            "posts_returned": 0,
            "top_posts": [],
        }

    posts = result["posts"]

    return {
        "status": "success",
        "username": username,
        "posts_returned": len(posts),
        "top_posts": posts,
    }
