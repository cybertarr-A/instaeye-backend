import os
import re
import requests
from typing import Dict, Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ----------------------------
# App Init (IMPORTANT)
# ----------------------------
app = FastAPI(title="Single Post Analyzer", version="1.0.0")

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
# Request Model (n8n-safe)
# ----------------------------
class PostAnalyzeRequest(BaseModel):
    post_url: str


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


def extract_shortcode(post_url: str) -> str:
    parsed = urlparse(post_url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2:
        return parts[1]
    raise IGError("Invalid Instagram post URL")


# ----------------------------
# Resolve URL → Media ID
# ----------------------------
def resolve_media_id_from_url(post_url: str) -> str:
    oembed_url = "https://graph.facebook.com/v24.0/instagram_oembed"

    data = _get(
        oembed_url,
        {
            "url": post_url,
            "fields": "media_id"
        }
    )

    media_id = data.get("media_id")
    if not media_id:
        raise IGError("Unable to resolve media_id from URL")

    return media_id


# ----------------------------
# Fetch Media + Insights
# ----------------------------
def fetch_single_media(media_id: str) -> Dict[str, Any]:
    fields = (
        "id,caption,media_type,media_product_type,permalink,"
        "media_url,thumbnail_url,timestamp,like_count,comments_count,"
        "insights.metric(plays,reach,impressions,saved,shares,total_interactions)"
    )

    url = f"{GRAPH_BASE}/{media_id}"
    data = _get(url, {"fields": fields})

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


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze/post")
def analyze_single_post(req: PostAnalyzeRequest):
    try:
        media_id = resolve_media_id_from_url(req.post_url)
        media_data = fetch_single_media(media_id)

        return {
            "status": "success",
            "post_url": req.post_url,
            "media": media_data
        }

    except IGError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
