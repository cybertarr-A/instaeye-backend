import os
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any

# =====================================================
# CONFIG
# =====================================================
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_PARENT_USER_ID")
GRAPH_BASE = "https://graph.facebook.com/v24.0"

BATCH_SIZE = 10          # safe for IG Graph API
BATCH_DELAY = 4.0        # seconds
POST_LIMIT = 50          # fetch more to allow filtering
TOP_PER_ACCOUNT = 30
DAYS_LOOKBACK = 7

if not ACCESS_TOKEN or not IG_USER_ID:
    raise RuntimeError("❌ Missing IG_ACCESS_TOKEN or IG_PARENT_USER_ID")

# =====================================================
# ERRORS
# =====================================================
class IGError(Exception):
    pass

# =====================================================
# HELPERS
# =====================================================
def _get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = {**params, "access_token": ACCESS_TOKEN}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise IGError(r.text)
    return r.json()

def extract_hashtags(text: str) -> List[str]:
    return re.findall(r"#(\w+)", text or "")

def parse_ig_time(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def ai_analyze_content(media_url: str) -> str:
    return f"AI summary placeholder for {media_url.split('/')[-1]}" if media_url else ""

# =====================================================
# IMAGE FORMULA (CORE LOGIC)
# =====================================================
def compute_final_score(
    *,
    likes: int,
    comments: int,
    shares: int,
    views: int,
    avg_views_7d: float,
    followers: int
) -> Dict[str, float]:

    # Step 1 — VSR
    vsr = (
        (comments * 10) +
        (shares * 10) +
        (likes * 3) +
        (views * 0.1)
    )

    # Step 2 — VM
    vm = views / avg_views_7d if avg_views_7d > 0 else 1.0

    # Step 3 — FE
    fe = views / followers if followers > 0 else 0.0

    final_score = vsr * vm * fe

    return {
        "vsr": round(vsr, 2),
        "vm": round(vm, 4),
        "fe": round(fe, 6),
        "final_score": round(final_score, 2),
    }

# =====================================================
# RANK POSTS (LAST 7 DAYS ONLY)
# =====================================================
def rank_last_7_days_posts(
    media: List[Dict[str, Any]],
    *,
    followers: int
) -> List[Dict[str, Any]]:

    if not media:
        return []

    # average views from last 7 days only
    avg_views_7d = sum(m["insights"]["plays"] for m in media) / len(media)

    for m in media:
        views = m["insights"]["plays"]

        score = compute_final_score(
            likes=m["likes"],
            comments=m["comments"],
            shares=m["insights"].get("shares", 0),
            views=views,
            avg_views_7d=avg_views_7d,
            followers=followers
        )

        m["score_breakdown"] = score
        m["final_score"] = score["final_score"]

    media.sort(key=lambda x: x["final_score"], reverse=True)
    return media[:TOP_PER_ACCOUNT]

# =====================================================
# FETCH CREATOR (FILTER = LAST 7 DAYS)
# =====================================================
def fetch_creator(username: str) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{IG_USER_ID}"
    params = {
        "fields": (
            f"business_discovery.username({username}){{"
            f"id,username,followers_count,biography,"
            f"media.limit({POST_LIMIT}){{"
            f"id,caption,media_type,permalink,media_url,"
            f"timestamp,like_count,comments_count"
            f"}}}}"
        )
    }

    data = _get(url, params)
    bd = data.get("business_discovery")
    if not bd:
        raise IGError(f"No data for @{username}")

    followers = bd.get("followers_count", 1)
    raw_media = bd.get("media", {}).get("data", [])

    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)

    recent_media = []
    for m in raw_media:
        post_time = parse_ig_time(m["timestamp"])
        if post_time < cutoff:
            continue

        likes = m.get("like_count", 0)
        comments = m.get("comments_count", 0)

        # conservative insight estimation
        insights = {
            "plays": int((likes + comments) * 5),
            "shares": int(comments * 0.12),
        }

        recent_media.append({
            "id": m["id"],
            "username": username,
            "timestamp": m["timestamp"],
            "caption": m.get("caption", ""),
            "hashtags": extract_hashtags(m.get("caption", "")),
            "media_url": m.get("media_url"),
            "permalink": m.get("permalink"),
            "likes": likes,
            "comments": comments,
            "insights": insights,
            "ai_summary": ai_analyze_content(m.get("media_url")),
        })

    ranked = rank_last_7_days_posts(
        recent_media,
        followers=followers
    )

    return {
        "user": {
            "username": username,
            "followers": followers,
            "bio": bd.get("biography"),
        },
        "top_posts_last_7_days": ranked,
        "post_count": len(ranked)
    }

# =====================================================
# MAIN — 100 ACCOUNT SAFE SCAN
# =====================================================
def analyze_100_accounts(usernames: List[str]) -> Dict[str, Any]:
    results = []

    for i in range(0, len(usernames), BATCH_SIZE):
        batch = usernames[i:i + BATCH_SIZE]
        print(f"🚀 Batch {i//BATCH_SIZE + 1}")

        for username in batch:
            try:
                results.append(fetch_creator(username))
            except Exception as e:
                results.append({
                    "username": username,
                    "error": str(e)
                })

        if i + BATCH_SIZE < len(usernames):
            time.sleep(BATCH_DELAY)

    return {
        "accounts_scanned": len(usernames),
        "results": results,
        "successful": len([r for r in results if "top_posts_last_7_days" in r]),
        "failed": len([r for r in results if "error" in r]),
    }
