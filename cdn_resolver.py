import os
import requests
from typing import Dict, Any

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
# Resolve media_id via Business Discovery
# ----------------------------
def resolve_media_id(username: str, post_url: str, limit: int = 25) -> str:
    """
    Resolve media_id for a recent post using Business Discovery.
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
        "Post not found in recent media (Business Discovery limitation)."
    )


# ----------------------------
# Fetch CDN URL only
# ----------------------------
def fetch_cdn_url(media_id: str) -> str:
    """
    Fetch ONLY the CDN media URL.
    """

    url = f"{GRAPH_BASE}/{media_id}"
    data = _get(url, {"fields": "media_url"})

    media_url = data.get("media_url")
    if not media_url:
        raise IGError("media_url not available for this post")

    return media_url


# ----------------------------
# PUBLIC FUNCTION
# ----------------------------
def get_post_cdn_url(username: str, post_url: str) -> Dict[str, Any]:
    """
    Input:
      - username (business/creator account)
      - post_url (recent post)

    Output:
      - CDN media URL only
    """

    try:
        media_id = resolve_media_id(username, post_url)
        cdn_url = fetch_cdn_url(media_id)

        return {
            "status": "success",
            "username": username,
            "post_url": post_url,
            "cdn_url": cdn_url
        }

    except Exception as e:
        return {
            "status": "error",
            "username": username,
            "post_url": post_url,
            "error": str(e)
        }
