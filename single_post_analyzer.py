import os
import re
import requests
from typing import Dict, Any, List

# ----------------------------
# Environment Setup
# ----------------------------
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_BASE = "https://graph.facebook.com/v24.0"

if not ACCESS_TOKEN or not IG_USER_ID:
    raise RuntimeError("IG_ACCESS_TOKEN or IG_PARENT_USER_ID not set")

# ----------------------------
# Helpers
# ----------------------------
class IGError(Exception):
    pass


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = {**params, "access_token": ACCESS_TOKEN}
    resp = requests.get(url, params=params, timeout=30)

    if resp.status_code != 200:
        raise IGError(f"GET {url} -> {resp.status_code}: {resp.text}")

    return resp.json()


def extract_shortcode(post_url: str) -> str:
    match = re.search(r"/(p|reel)/([^/]+)/", post_url)
    if not match:
        raise IGError("Invalid Instagram post URL")
    return match.group(2)


def extract_hashtags(caption: str) -> List[str]:
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


# ----------------------------
# Resolve Shortcode → Media ID
# (OWN ACCOUNT ONLY)
# ----------------------------
def resolve_media_id_from_own_account(shortcode: str) -> str:
    """
    Finds media_id by scanning your own account media.
    No username, no business discovery.
    """
    url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    fields = "id,permalink"
    limit = 50  # increase if you have many posts

    data = _get(url, {"fields": fields, "limit": limit})

    for m in data.get("data", []):
        if shortcode in m.get("permalink", ""):
            return m["id"]

    raise IGError("Post not found in own account media")


# ----------------------------
# Fetch Single Post Details
# ----------------------------
def fetch_single_post(media_id: str) -> Dict[str, Any]:
    fields = (
        "id,caption,media_type,media_product_type,"
        "permalink,media_url,thumbnail_url,timestamp,"
        "like_count,comments_count,"
        "insights.metric(plays,reach,impressions,saved,shares)"
    )

    data = _get(f"{GRAPH_BASE}/{media_id}", {"fields": fields})

    caption = data.get("caption", "")
    hashtags = extract_hashtags(caption)

    insights = {}
    if "insights" in data and "data" in data["insights"]:
        for metric in data["insights"]["data"]:
            if metric.get("values"):
                insights[metric["name"]] = metric["values"][0].get("value", 0)

    return {
        "id": data.get("id"),
        "type": data.get("media_type"),
        "product_type": data.get("media_product_type"),
        "caption": caption,
        "hashtags": hashtags,
        "timestamp": data.get("timestamp"),
        "permalink": data.get("permalink"),
        "media_url": data.get("media_url"),
        "thumbnail_url": data.get("thumbnail_url"),
        "likes": data.get("like_count", 0),
        "comments": data.get("comments_count", 0),
        "insights": insights,
    }


# ----------------------------
# MAIN EXPORT FUNCTION
# ----------------------------
def analyze_single_post(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point (called from FastAPI)
    Expects:
      { "post_url": "https://www.instagram.com/p/..." }
    """
    post_url = body.get("post_url")
    if not post_url:
        raise IGError("post_url missing in request body")

    shortcode = extract_shortcode(post_url)
    media_id = resolve_media_id_from_own_account(shortcode)
    post = fetch_single_post(media_id)

    return {
        "post": post
    }
import os
import re
import requests
from typing import Dict, Any, List

# ----------------------------
# Environment Setup
# ----------------------------
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_BASE = "https://graph.facebook.com/v24.0"

if not ACCESS_TOKEN or not IG_USER_ID:
    raise RuntimeError("IG_ACCESS_TOKEN or IG_PARENT_USER_ID not set")

# ----------------------------
# Helpers
# ----------------------------
class IGError(Exception):
    pass


def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = {**params, "access_token": ACCESS_TOKEN}
    resp = requests.get(url, params=params, timeout=30)

    if resp.status_code != 200:
        raise IGError(f"GET {url} -> {resp.status_code}: {resp.text}")

    return resp.json()


def extract_shortcode(post_url: str) -> str:
    match = re.search(r"/(p|reel)/([^/]+)/", post_url)
    if not match:
        raise IGError("Invalid Instagram post URL")
    return match.group(2)


def extract_hashtags(caption: str) -> List[str]:
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


# ----------------------------
# Resolve Shortcode → Media ID
# (OWN ACCOUNT ONLY)
# ----------------------------
def resolve_media_id_from_own_account(shortcode: str) -> str:
    """
    Finds media_id by scanning your own account media.
    No username, no business discovery.
    """
    url = f"{GRAPH_BASE}/{IG_USER_ID}/media"
    fields = "id,permalink"
    limit = 50  # increase if you have many posts

    data = _get(url, {"fields": fields, "limit": limit})

    for m in data.get("data", []):
        if shortcode in m.get("permalink", ""):
            return m["id"]

    raise IGError("Post not found in own account media")


# ----------------------------
# Fetch Single Post Details
# ----------------------------
def fetch_single_post(media_id: str) -> Dict[str, Any]:
    fields = (
        "id,caption,media_type,media_product_type,"
        "permalink,media_url,thumbnail_url,timestamp,"
        "like_count,comments_count,"
        "insights.metric(plays,reach,impressions,saved,shares)"
    )

    data = _get(f"{GRAPH_BASE}/{media_id}", {"fields": fields})

    caption = data.get("caption", "")
    hashtags = extract_hashtags(caption)

    insights = {}
    if "insights" in data and "data" in data["insights"]:
        for metric in data["insights"]["data"]:
            if metric.get("values"):
                insights[metric["name"]] = metric["values"][0].get("value", 0)

    return {
        "id": data.get("id"),
        "type": data.get("media_type"),
        "product_type": data.get("media_product_type"),
        "caption": caption,
        "hashtags": hashtags,
        "timestamp": data.get("timestamp"),
        "permalink": data.get("permalink"),
        "media_url": data.get("media_url"),
        "thumbnail_url": data.get("thumbnail_url"),
        "likes": data.get("like_count", 0),
        "comments": data.get("comments_count", 0),
        "insights": insights,
    }


# ----------------------------
# MAIN EXPORT FUNCTION
# ----------------------------
def analyze_single_post(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entry point (called from FastAPI)
    Expects:
      { "post_url": "https://www.instagram.com/p/..." }
    """
    post_url = body.get("post_url")
    if not post_url:
        raise IGError("post_url missing in request body")

    shortcode = extract_shortcode(post_url)
    media_id = resolve_media_id_from_own_account(shortcode)
    post = fetch_single_post(media_id)

    return {
        "post": post
    }
