import os
import re
import requests
from typing import List, Dict, Optional
from openai import OpenAI

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

if not IG_ACCESS_TOKEN:
    raise RuntimeError("IG_ACCESS_TOKEN not set")

if not IG_USER_ID:
    raise RuntimeError("IG_USER_ID not set")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

client = OpenAI(api_key=OPENAI_API_KEY)

# --------------------------------------------------
# AI ANALYZER (already used elsewhere in your system)
# --------------------------------------------------

def ai_analyze_content(media_url: str) -> str:
    try:
        r = requests.get(media_url, timeout=20)
        r.raise_for_status()

        image_b64 = r.content.encode("base64") if False else None  # placeholder safety

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Analyze this Instagram post media and summarize "
                        "the content intent, tone, and category in 2–3 lines.\n\n"
                        f"Media URL: {media_url}"
                    ),
                }
            ],
            temperature=0.3,
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"AI analysis failed: {str(e)}"

# --------------------------------------------------
# UTIL: Extract shortcode
# --------------------------------------------------

def extract_shortcode(insta_url: str) -> Optional[str]:
    match = re.search(r"/(p|reel|tv)/([^/?#]+)/", insta_url)
    if not match:
        return None
    return match.group(2)

# --------------------------------------------------
# UTIL: Resolve shortcode → media ID
# --------------------------------------------------

def resolve_media_id(shortcode: str) -> Optional[Dict]:
    url = f"{GRAPH_API_BASE}/{IG_USER_ID}/media"
    params = {
        "fields": (
            "id,shortcode,media_type,permalink,media_url,"
            "thumbnail_url,like_count,comments_count,caption,timestamp"
        ),
        "access_token": IG_ACCESS_TOKEN,
        "limit": 50,
    }

    while True:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        for item in data.get("data", []):
            if item.get("shortcode") == shortcode:
                return item

        next_url = data.get("paging", {}).get("next")
        if not next_url:
            break

        url = next_url
        params = None

    return None

# --------------------------------------------------
# FETCH POST INSIGHTS
# --------------------------------------------------

def fetch_post_insights(media_id: str, media_type: str) -> Dict:
    if media_type in ("VIDEO", "REELS"):
        metrics = "impressions,reach,plays,saved,shares"
    else:
        metrics = "impressions,reach,saved"

    url = f"{GRAPH_API_BASE}/{media_id}/insights"
    params = {
        "metric": metrics,
        "access_token": IG_ACCESS_TOKEN,
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    insights = {}
    for item in data.get("data", []):
        insights[item["name"]] = item["values"][0]["value"]

    return insights

# --------------------------------------------------
# MAIN ANALYZER (instagram_analyzer-style)
# --------------------------------------------------

def analyze_posts(post_urls: List[str]) -> Dict:
    posts = []

    for url in post_urls:
        shortcode = extract_shortcode(url)

        if not shortcode:
            posts.append({
                "url": url,
                "status": "error",
                "message": "Invalid Instagram post URL",
            })
            continue

        m = resolve_media_id(shortcode)

        if not m:
            posts.append({
                "url": url,
                "shortcode": shortcode,
                "status": "not_found",
                "message": "Post not found for this account",
            })
            continue

        caption = m.get("caption", "")
        hashtags = [h for h in caption.split() if h.startswith("#")]

        try:
            insights = fetch_post_insights(m["id"], m["media_type"])
        except Exception as e:
            insights = {"error": str(e)}

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
            "ai_summary": ai_analyze_content(
                m.get("media_url") or m.get("thumbnail_url")
            ),
        })

    return {
        "status": "ok",
        "count": len(posts),
        "posts": posts,
    }
