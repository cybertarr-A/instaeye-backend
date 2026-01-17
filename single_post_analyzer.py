import os
import re
import requests
from typing import Dict, Any, Optional

# ----------------------------
# Environment Setup
# ----------------------------
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_BASE = "https://graph.facebook.com/v24.0"

if not ACCESS_TOKEN or not IG_USER_ID:
    print("⚠️ WARNING: IG_ACCESS_TOKEN or IG_PARENT_USER_ID not set.")


# ----------------------------
# Errors
# ----------------------------
class IGError(Exception):
    pass


# ----------------------------
# HTTP Helper
# ----------------------------
def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = {**params, "access_token": ACCESS_TOKEN}
    resp = requests.get(url, params=params, timeout=30)

    if resp.status_code != 200:
        raise IGError(f"GET {url} -> {resp.status_code}: {resp.text}")

    return resp.json()


# ----------------------------
# Utilities
# ----------------------------
def extract_hashtags(caption: str):
    if not caption:
        return []
    return re.findall(r"#(\w+)", caption)


# ----------------------------
# Business Discovery: Resolve media_id by permalink
# ----------------------------
def resolve_media_id_via_business_discovery(
    username: str,
    post_url: str,
    limit: int = 25
) -> str:
    """
    Fetch recent media via Business Discovery and
    match permalink to resolve media_id.
    """

    url = f"{GRAPH_BASE}/{IG_USER_ID}"
    fields = (
        f"business_discovery.username({username}){{"
        f"media.limit({limit}){{id,permalink}}"
        f"}}"
    )

    data = _get(url, {"fields": fields})
    bd = data.get("business_discovery")

    if not bd or "media" not in bd:
        raise IGError(f"Business Discovery not available for @{username}")

    for media in bd["media"].get("data", []):
        if media.get("permalink") == post_url:
            return media["id"]

    raise IGError(
        "Post not found in recent media. "
        "Instagram only allows access to recent posts via Business Discovery."
    )


# ----------------------------
# Fetch Public Media Data
# ----------------------------
def fetch_public_media(media_id: str) -> Dict[str, Any]:
    """
    Fetch public fields only (allowed for other users).
    """
    fields = (
        "id,caption,media_type,media_product_type,permalink,"
        "media_url,thumbnail_url,timestamp,like_count,comments_count"
    )

    url = f"{GRAPH_BASE}/{media_id}"
    data = _get(url, {"fields": fields})

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
        "engagement": {
            "likes": data.get("like_count", 0),
            "comments": data.get("comments_count", 0),
            "total": data.get("like_count", 0) + data.get("comments_count", 0)
        }
    }


# ----------------------------
# PUBLIC FUNCTION
# ----------------------------
def analyze_single_post(
    username: str,
    post_url: str
) -> Dict[str, Any]:
    """
    Analyze a specific post from another user using Business Discovery.
    """

    try:
        media_id = resolve_media_id_via_business_discovery(username, post_url)
        media_data = fetch_public_media(media_id)

        return {
            "status": "success",
            "username": username,
            "post_url": post_url,
            "media": media_data
        }

    except Exception as e:
        return {
            "status": "error",
            "username": username,
            "post_url": post_url,
            "error": str(e)
        }
