from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Any, Optional
import traceback

# ----------------------------
# Core modules
# ----------------------------

from instagram_analyzer import analyze_profiles
from content_ideas import generate_content
from image_analyzer import analyze_image
from video_analyzer import analyze_reel
from top_posts import get_top_posts
from trend_engine import analyze_industry
from audio_pipeline import process_audio
from media_splitter import router as split_router

# ----------------------------
# CDN resolvers
# ----------------------------

from cdn_resolver import get_post_cdn_url
from rapidapi_instagram_cdn import get_recent_cdns as rapidapi_cdn_resolver


# ============================
# APP INIT
# ============================

app = FastAPI(title="InstaEye Backend", version="1.3")

app.include_router(split_router)

# ============================
# REQUEST MODELS
# ============================

class AnalyzeProfilesRequest(BaseModel):
    usernames: List[str]

class ContentIdeasRequest(BaseModel):
    data: List[Any]

class ImageAnalyzeRequest(BaseModel):
    media_url: str

class ReelAnalyzeRequest(BaseModel):
    video_url: Optional[str] = None
    media_url: Optional[str] = None
    url: Optional[str] = None
    reel_url: Optional[str] = None

class ReelAudioRequest(BaseModel):
    media_url: str

class TopPostsRequest(BaseModel):
    username: str
    limit: int = 5

class IndustryAnalyzeRequest(BaseModel):
    keywords: List[str]
    news_api_key: Optional[str] = None

# 🔹 CDN request
class PostCDNRequest(BaseModel):
    username: str
    post_url: Optional[str] = None
    media_id: Optional[str] = None


# ============================
# ROUTES
# ============================

@app.get("/")
def home():
    return {"status": "InstaEye backend running"}


@app.post("/analyze")
def analyze_profile_api(req: AnalyzeProfilesRequest):
    return analyze_profiles(req.usernames)


@app.post("/analyze-image")
def analyze_image_api(req: ImageAnalyzeRequest):
    return analyze_image(req.media_url)


@app.post("/analyze-reel")
def analyze_reel_api(req: ReelAnalyzeRequest):
    url = req.video_url or req.media_url or req.url or req.reel_url
    if not url:
        return {"status": "error", "message": "No video URL provided"}
    return analyze_reel(url)


@app.post("/analyze-reel-audio")
def analyze_reel_audio_api(req: ReelAudioRequest):
    try:
        return process_audio(req.media_url)
    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "stage": "audio_pipeline",
            "message": str(e)
        }


@app.post("/analyze-industry")
def analyze_industry_api(req: IndustryAnalyzeRequest):
    return analyze_industry(req.keywords, req.news_api_key)


@app.post("/top-posts")
def top_posts_api(req: TopPostsRequest):
    return get_top_posts(req.username, req.limit)


@app.post("/generate-content-ideas")
def generate_ideas_api(req: ContentIdeasRequest):
    return generate_content(req.data)


# =====================================================
# ✅ CDN RESOLVER WITH RAPIDAPI FALLBACK
# =====================================================

@app.post("/resolve/post-cdn")
def resolve_post_cdn_api(req: PostCDNRequest):
    """
    Resolve CDN URL with priority:
    1) Official Instagram (Business Discovery / media_id)
    2) RapidAPI fallback (best-effort)
    """

    # ---- 1️⃣ Try OFFICIAL resolver first
    try:
        result = official_cdn_resolver(
            media_id=req.media_id,
            username=req.username,
            post_url=req.post_url
        )

        if result.get("status") == "success":
            result["resolver"] = "official"
            return result

    except Exception as e:
        print("Official resolver failed:", e)

    # ---- 2️⃣ RapidAPI fallback (username only)
    try:
        rapid = rapidapi_cdn_resolver(req.username, limit=1)

        if rapid.get("status") == "success" and rapid.get("cdn_urls"):
            return {
                "status": "success",
                "resolver": "rapidapi",
                "username": req.username,
                "cdn_url": rapid["cdn_urls"][0]
            }

        return rapid

    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "resolver": "none",
            "message": str(e)
        }
