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

app = FastAPI(
    title="InstaEye Backend",
    version="3.9.2",
    description="Stateless Instagram intelligence backend"
)

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
    reel_url: Optional[str] = None
    url: Optional[str] = None
    media_url: Optional[str] = None

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
    """
    Strip query params, fragments, and trailing slashes.
    """
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment="")).rstrip("/")

def extract_any_reel_url(req: ReelAnalyzeRequest) -> Optional[str]:
    """
    Accept multiple field names for n8n / external flexibility.
    """
    return req.video_url or req.media_url or req.url or req.reel_url

def error_response(message: str, trace: Optional[str] = None):
    payload = {"status": "error", "message": message}
    if trace:
        payload["trace"] = trace
    return payload

# ============================
# ROUTES
# ============================

@app.get("/", tags=["system"])
def home():
    return {
        "status": "ok",
        "service": "InstaEye backend",
        "mode": "stateless",
        "storage": "none",
        "version": app.version
    }

# ----------------------------
# Profile & Content Analysis
# ----------------------------

@app.post("/analyze", tags=["profiles"])
def analyze_profile_api(req: AnalyzeProfilesRequest):
    return analyze_profiles(req.usernames)

@app.post("/generate-content-ideas", tags=["content"])
def generate_ideas_api(req: ContentIdeasRequest):
    return generate_content(req.data)

@app.post("/top-posts", tags=["profiles"])
def top_posts_api(req: TopPostsRequest):
    return get_top_posts(req.username, req.limit)

@app.post("/analyze-industry", tags=["industry"])
def analyze_industry_api(req: IndustryAnalyzeRequest):
    return analyze_industry(req.keywords, req.news_api_key)

# ----------------------------
# Media Analysis
# ----------------------------

@app.post("/analyze-image", tags=["media"])
def analyze_image_api(req: ImageAnalyzeRequest):
    return analyze_image(req.media_url)

@app.post("/resolve-reel", tags=["media"])
def resolve_reel_api(req: ReelResolveRequest):
    try:
        raw_url = req.reel_url or req.url or req.media_url
        if not raw_url:
            return error_response("No reel URL provided")

        clean_url = normalize_instagram_url(raw_url)
        video_url = resolve_reel_video_url(clean_url)

        return {
            "status": "ok",
            "video_url": video_url
        }

    except ReelResolveError as e:
        return error_response(str(e))

    except Exception:
        return error_response(
            "Unexpected resolver failure",
            traceback.format_exc()
        )

@app.post("/analyze-reel", tags=["media"])
def analyze_reel_api(req: ReelAnalyzeRequest):
    try:
        raw_url = extract_any_reel_url(req)
        if not raw_url:
            return error_response("No reel URL provided")

        clean_url = normalize_instagram_url(raw_url)

        # Instagram URL → resolve first
        if "instagram.com" in clean_url:
            video_url = resolve_reel_video_url(clean_url)
        else:
            video_url = clean_url  # already CDN URL

        return analyze_reel(video_url)

    except ReelResolveError as e:
        return error_response(str(e))

    except Exception:
        return error_response(
            "Unexpected reel analysis failure",
            traceback.format_exc()
        )

@app.post("/analyze-reel-audio", tags=["media"])
def analyze_reel_audio_api(req: ReelAudioRequest):
    return process_audio(req.media_url)
