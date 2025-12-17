import os
import requests
from datetime import datetime, timedelta
from dateutil.parser import parse

# Instagram API credentials (use Railway ENV VARS)
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_PARENT_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_URL = "https://graph.facebook.com/v19.0"


def get_media_insights(media_id: str):
    """Fetch plays, shares and saved metrics for a media."""
    url = f"{GRAPH_URL}/{media_id}/insights"
    params = {
        "metric": "video_views,shares,saved",
        "access_token": ACCESS_TOKEN
    }

    response = requests.get(url, params=params)
    data = response.json()

    insights = {"plays": 0, "shares": 0, "saved": 0}

    if "data" in data:
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


def fetch_top_posts_by_username(username: str, limit: int = 5):
    """Fetch top IG posts from the last 14 days for a given username."""
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

    response = requests.get(url, params=params)
    data = response.json()

    if "business_discovery" not in data:
        raise Exception("Username not accessible. Must be a Business/Creator account connected to your IG app.")

    media = data["business_discovery"]["media"]["data"]

    recent_posts = []

    for post in media:
        post_time = parse(post["timestamp"])
        if post_time.timestamp() < since_timestamp:
            continue

        likes = post.get("like_count", 0)
        comments = post.get("comments_count", 0)
        engagement = likes + comments

        insights = {"plays": None, "shares": None, "saved": None}

        # For videos, fetch deeper insights
        if post.get("media_type") in ("VIDEO", "REEL"):
            insights = get_media_insights(post["id"])
            engagement += insights["plays"] + insights["shares"]

        recent_posts.append({
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
            "media_type": post.get("media_type")
        })

    # Sort posts by engagement
    recent_posts.sort(key=lambda x: x["engagement_score"], reverse=True)
    return recent_posts[:limit]


# ----------------------------
# MAIN ENTRY FOR FASTAPI
# ----------------------------
def get_top_posts(username: str, limit: int = 5):
    """
    Function used by main FastAPI app:
    Returns top posts structure expected by your n8n workflow
    """
    posts = fetch_top_posts_by_username(username, limit)
    return {
        "status": "success",
        "username": username,
        "posts_returned": len(posts),
        "top_posts": posts
    }
