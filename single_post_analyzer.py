import os
import re
import requests
from typing import Dict, Any, List

GRAPH_BASE = "https://graph.facebook.com/v24.0"

ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")

if not ACCESS_TOKEN or not IG_USER_ID:
    raise RuntimeError("IG_ACCESS_TOKEN or IG_PARENT_USER_ID not set")


# =============================
# HELPERS
# =============================

class IGError(Exception):
    pass


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params["access_token"] = ACCESS_TOKEN
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        raise IGError(r.text)
    return r.json()


def extract_shortcode(url: str) -> str:
    match = re.search(r"/(p|reel)/([^/]+)/", url)
    if not match:
        raise IGError("Invalid Instagram post URL")
    return match.group(2)


def extract_hashtags(caption: str) -> List[str]:
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


# =============================
# SHORTCODE → MEDIA ID
# =============================

def resolve_media_id(shortcode: str) -> str:
    """
    Uses business_discovery to find the media_id
    """
    url = f"{GRAPH_BASE}/{IG_USER_ID}"
    params = {
        "fields": (
            f"business_discovery.username({IG_USER_ID}){{"
            f"media{{id,permalink}}"
            f"}}"
        )
    }

    data = _get(url, params)
    media = data.get("business_discovery", {}).get("media", {}).get("data", [])

    for m in media:
        if shortcode in m.get("permalink", ""):
            return m["id"]

    raise IGError("Post not accessible via Business Discovery")


# =============================
# FETCH SINGLE POST
# =============================

def fetch_single_post(media_id: str) -> Dict[str, Any]:
    fields = (
        "id,caption,media_type,media_product_type,"
        "permalink,media_url,thumbnail_url,timestamp,"
        "like_count,comments_count,"
        "insights.metric(plays,reach,impressions,saved,shares)"
    )

    data = _get(f"{GRAPH_BASE}/{media_id}", {"fields": fields})

    insights = {}
    for metric in data.get("insights", {}).get("data", []):
        if metric.get("values"):
            insights[metric["name"]] = metric["values"][0].get("value", 0)

    caption = data.get("caption", "")

    return {
        "id": data.get("id"),
        "type": data.get("media_type"),
        "product_type": data.get("media_product_type"),
        "caption": caption,
        "hashtags": extract_hashtags(caption),
        "timestamp": data.get("timestamp"),
        "permalink": data.get("permalink"),
        "media_url": data.get("media_url"),
        "thumbnail_url": data.get("thumbnail_url"),
        "likes": data.get("like_count", 0),
        "comments": data.get("comments_count", 0),
        "insights": insights
    }


# =============================
# MAIN ENTRY (FASTAPI CALLS THIS)
# =============================

def analyze_single_post(body: Dict[str, Any]) -> Dict[str, Any]:
    post_url = body.get("post_url")
    if not post_url:
        raise IGError("post_url missing")

    shortcode = extract_shortcode(post_url)
    media_id = resolve_media_id(shortcode)

    post = fetch_single_post(media_id)

    return {
        "status": "success",
        "post": post
    }
