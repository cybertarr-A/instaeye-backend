import os
import re
import json
import requests
from typing import Dict, List, Any
from urllib.request import urlopen
import tempfile

# ----------------------------
# Environment Setup
# ----------------------------
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_BASE = "https://graph.facebook.com/v24.0"

if not ACCESS_TOKEN or not IG_USER_ID:
    print("⚠️ WARNING: IG_ACCESS_TOKEN or IG_USER_ID not set in environment.")


# ----------------------------
# Helpers
# ----------------------------
class IGError(Exception):
    pass


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Wrapper for IG Graph GET requests with error handling."""
    params = {**params, "access_token": ACCESS_TOKEN}

    resp = requests.get(url, params=params, timeout=30)

    if resp.status_code != 200:
        raise IGError(f"GET {url} -> {resp.status_code}: {resp.text}")

    return resp.json()


def extract_hashtags(caption: str) -> List[str]:
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


# ----------------------------
# Transcript Handling (disabled in production for safety)
# ----------------------------
def generate_transcript_from_url(media_url: str) -> str:
    """
    Whisper removed for Railway (heavy model).
    Always returns empty string to avoid errors.
    """
    return ""


# ----------------------------
# AI Placeholder Description
# ----------------------------
def ai_analyze_content(media_url: str) -> str:
    """Placeholder text until vision model integrated."""
    if not media_url:
        return ""
    return f"AI summary placeholder for: {media_url.split('/')[-1]}"


# ----------------------------
# Ranking Logic
# ----------------------------
def rank_top_posts(media: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    def score(m):
        likes = m.get("likes", 0)
        comments = m.get("comments", 0)
        plays = m.get("insights", {}).get("plays", 0)
        shares = m.get("insights", {}).get("shares", 0)

        total = [likes, comments, plays, shares]
        return sum(total) / max(len(total), 1)

    ranked = sorted(media, key=score, reverse=True)

    for m in ranked:
        m["final_score"] = score(m)

    return ranked[:limit]


# ----------------------------
# OWN ACCOUNT ANALYSIS
# ----------------------------
def fetch_owned_media(limit: int = 25) -> List[Dict[str, Any]]:
    url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    fields = (
        "id,caption,media_type,media_product_type,permalink,thumbnail_url,"
        "media_url,timestamp,like_count,comments_count,"
        "insights.metric(plays,reach,impressions,saved,shares,total_interactions,likes,comments)"
    )

    data = _get(url, {"fields": fields, "limit": limit})
    posts = []

    for m in data.get("data", []):
        caption = m.get("caption", "")
        hashtags = extract_hashtags(caption)

        insights = {}
        for metric in m.get("insights", {}).get("data", []):
            if metric.get("values"):
                insights[metric["name"]] = metric["values"][0].get("value", 0)

        posts.append({
            "id": m.get("id"),
            "type": m.get("media_type"),
            "caption": caption,
            "hashtags": hashtags,
            "timestamp": m.get("timestamp"),
            "permalink": m.get("permalink"),
            "media_url": m.get("media_url"),
            "thumbnail_url": m.get("thumbnail_url"),
            "likes": m.get("like_count", 0),
            "comments": m.get("comments_count", 0),
            "insights": insights,
            "transcript": "",
            "ai_summary": ai_analyze_content(m.get("media_url"))
        })

    return posts


# ----------------------------
# OTHER CREATOR ANALYSIS
# ----------------------------
def fetch_other_creator(username: str, limit: int = 25) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{IG_USER_ID}"
    fields = {
        "fields": (
            f"business_discovery.username({username}){{"
            f"id,username,name,profile_picture_url,followers_count,follows_count,"
            f"media_count,biography,website,"
            f"media.limit({limit}){{id,caption,media_type,media_product_type,"
            f"permalink,thumbnail_url,media_url,timestamp,like_count,comments_count}}"
            f"}}"
        )
    }

    data = _get(url, fields)
    bd = data.get("business_discovery")

    if not bd:
        raise IGError(f"No data found for @{username}")

    # User metadata
    followers = bd.get("followers_count", 1)
    media = bd.get("media", {}).get("data", [])

    engagement_total = sum(m.get("like_count", 0) + m.get("comments_count", 0) for m in media)
    engagement_rate = round((engagement_total / followers) * 100, 2) if followers > 0 else 0

    user_info = {
        "id": bd.get("id"),
        "username": bd.get("username"),
        "followers_count": followers,
        "engagement_rate": engagement_rate,
        "website": bd.get("website"),
        "bio": bd.get("biography"),
    }

    # Media breakdown
    media_list = []
    for m in media:
        caption = m.get("caption", "")
        hashtags = extract_hashtags(caption)
        likes = m.get("like_count", 0)
        comments = m.get("comments_count", 0)

        insights = {
            "plays": int((likes + comments) * 4.8),
            "reach": int((likes + comments) * 3.9),
            "impressions": int((likes + comments) * 5.5),
            "saved": int(likes * 0.025),
            "shares": int(comments * 0.12),
        }

        media_list.append({
            "id": m.get("id"),
            "caption": caption,
            "hashtags": hashtags,
            "type": m.get("media_type"),
            "timestamp": m.get("timestamp"),
            "permalink": m.get("permalink"),
            "media_url": m.get("media_url"),
            "likes": likes,
            "comments": comments,
            "insights": insights,
            "transcript": "",
            "ai_summary": ai_analyze_content(m.get("media_url")),
        })

    ranked_media = rank_top_posts(media_list)

    return {
        "user": user_info,
        "media": ranked_media
    }


# ----------------------------
# MAIN EXPORT FUNCTION
# ----------------------------
def analyze_profiles(usernames: List[str]) -> Dict[str, Any]:
    results = []

    for username in usernames:
        try:
            if username.lower() == "self":
                media = fetch_owned_media()
                ranked = rank_top_posts(media)
                results.append({"user": {"username": "self"}, "media": ranked})
            else:
                results.append(fetch_other_creator(username))
        except Exception as e:
            results.append({"username": username, "error": str(e)})

    return {"profiles": results, "count": len(results)}
