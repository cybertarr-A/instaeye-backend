import os
import re
import requests
from datetime import datetime
from typing import Dict, Any

GRAPH_BASE = "https://graph.facebook.com/v24.0"

# ----------------------------
# HELPERS
# ----------------------------
def extract_shortcode(url: str) -> str:
    match = re.search(r"/(p|reel)/([^/]+)/", url)
    if not match:
        raise ValueError("Invalid Instagram post URL")
    return match.group(2)

def validate_token(access_token: str) -> Dict[str, Any]:
    """
    Lightweight token validation using Graph API.
    """
    url = f"{GRAPH_BASE}/me"
    params = {
        "fields": "id,name",
        "access_token": access_token
    }

    r = requests.get(url, params=params, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Invalid access token: {r.text}")

    return r.json()

# ----------------------------
# MAIN TEST FUNCTION
# ----------------------------
def run_single_post_test(body: dict) -> dict:
    access_token = os.getenv("IG_ACCESS_TOKEN")
    if not access_token:
        raise RuntimeError("IG_ACCESS_TOKEN not set in environment")

    post_url = body.get("post_url")
    if not post_url:
        raise ValueError("post_url missing")

    shortcode = extract_shortcode(post_url)

    # 🔐 Validate token with IG
    token_info = validate_token(access_token)

    return {
        "mode": "single_post_token_test",
        "token_valid": True,
        "token_user": {
            "id": token_info.get("id"),
            "name": token_info.get("name")
        },
        "id": f"test_{shortcode}",
        "type": "VIDEO",
        "caption": "Workflow test with real IG access token",
        "hashtags": ["test", "instagram", "token"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "permalink": post_url,
        "media_url": "https://cdn.test/media.mp4",
        "thumbnail_url": "https://cdn.test/thumb.jpg",
        "likes": 100,
        "comments": 10,
        "insights": {
            "plays": 5000,
            "reach": 3800,
            "impressions": 6200,
            "saved": 55,
            "shares": 9
        },
        "ai_summary": "Token verified successfully. Ready for real post fetch."
    }
