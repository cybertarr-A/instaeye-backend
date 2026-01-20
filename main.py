from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Any
from urllib.parse import urlparse, urlunparse
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

from reel_resolver import resolve_reel_video_url, ReelResolveError

# ============================
# APP INIT
# ============================

app = FastAPI(title="InstaEye Backend", version="3.9.0")
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
    url: Optional[str] = None
    reel_url: Optional[str] = None
    media_url: Optional[str] = None
    video_url: Optional[str] = None

class ReelResolveRequest(BaseModel):
    reel_url: str

class ReelAudioRequest(BaseModel):
    media_url: str

class TopPostsRequest(BaseModel):
    username: str
    limit: int = 5

class IndustryAnalyzeRequest(BaseModel):
    keywords: List[str]
    news_api_key: Optional[str] = None

# ============================
# HELPERS
# ============================

def normalize_instagram_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment=""))

def extract_any_reel_url(req: ReelAnalyzeRequest) -> Optional[str]:
    return req.video_url or req.media_url or req.url or req.reel_url

# ============================
# ROUTES
# ============================

@app.get("/")
def home():
    return {
        "status": "InstaEye backend running",
        "mode": "stateless",
        "storage": "none",
        "version": app.version
    }

# ----------------------------
# Profile & Content Analysis
# ----------------------------

@app.post("/analyze")
def analyze_profile_api(req: AnalyzeProfilesRequest):
    return analyze_profiles(req.usernames)

@app.post("/generate-content-ideas")
def generate_ideas_api(req: ContentIdeasRequest):
    return generate_content(req.data)

@app.post("/top-posts")
def top_posts_api(req: TopPostsRequest):
    return get_top_posts(req.username, req.limit)

@app.post("/analyze-industry")
def analyze_industry_api(req: IndustryAnalyzeRequest):
    return analyze_industry(req.keywords, req.news_api_key)

# ----------------------------
# Media Analysis
# ----------------------------

@app.post("/analyze-image")
def analyze_image_api(req: ImageAnalyzeRequest):
    return analyze_image(req.media_url)

@app.post("/resolve-reel")
def resolve_reel_api(req: ReelResolveRequest):
    """
    SnapInsta-style resolver:
    Instagram Reel URL → Direct MP4 URL
    """
    try:
        clean_url = normalize_instagram_url(req.reel_url)
        video_url = resolve_reel_video_url(clean_url)

        return {
            "status": "ok",
            "video_url": video_url
        }

    except ReelResolveError as e:
        return {"status": "error", "message": str(e)}

    except Exception:
        return {
            "status": "error",
            "message": "Unexpected resolver failure",
            "trace": traceback.format_exc()
        }

@app.post("/analyze-reel")
def analyze_reel_api(req: ReelAnalyzeRequest):
    try:
        raw_url = extract_any_reel_url(req)
        if not raw_url:
            return {"status": "error", "message": "No reel URL provided"}

        clean_url = normalize_instagram_url(raw_url)

        # If Instagram URL → resolve first
        if "instagram.com" in clean_url:
            video_url = resolve_reel_video_url(clean_url)
        else:
            video_url = clean_url  # already direct CDN URL

        return analyze_reel(video_url)

    except Exception:
        return {
            "status": "error",
            "trace": traceback.format_exc()
        }

@app.post("/analyze-reel-audio")
def analyze_reel_audio_api(req: ReelAudioRequest):
    return process_audio(req.media_url)
