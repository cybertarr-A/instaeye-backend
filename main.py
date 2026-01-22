from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Any
from urllib.parse import urlparse, urlunparse
import traceback

# ----------------------------
# Core analysis modules
# ----------------------------

from instagram_analyzer import analyze_profiles
from content_ideas import generate_content
from image_analyzer import analyze_image
from mini_video_analyzer import analyze_reel
from top_posts import get_top_posts
from trend_engine import analyze_industry
from audio_pipeline import process_audio
from media_splitter import router as split_router

# ----------------------------
# Audio Transcriber
# ----------------------------

from audio_transcriber import router as audio_router

# ----------------------------
# Instagram Discovery (SerpAPI + followers)
# ----------------------------

from instagram_finder import router as instagram_finder_router

# ----------------------------
# CDN Resolver
# ----------------------------

from cdn_resolver import resolve_instagram_cdn, CDNResolveError

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.3.0",
    description="Stateless Instagram intelligence backend (router-based)"
)

# ============================
# ROUTERS
# ============================

app.include_router(split_router)
app.include_router(audio_router)
app.include_router(instagram_finder_router)  # ✅ FIXES 404
# (instagram finder now lives at /instagram/*)

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


class ReelVisionAnalyzeRequest(BaseModel):
    video_url: Optional[str] = None
    media_url: Optional[str] = None
    url: Optional[str] = None


class ReelAudioRequest(BaseModel):
    media_url: str


class TopPostsRequest(BaseModel):
    username: str
    limit: int = 5


class IndustryAnalyzeRequest(BaseModel):
    keywords: List[str]
    news_api_key: Optional[str] = None


class ReelResolveRequest(BaseModel):
    url: str

# ============================
# HELPERS
# ============================

def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment="")).rstrip("/")


def extract_any_url(req) -> Optional[str]:
    return req.video_url or req.media_url or req.url


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
        "version": app.version,
        "modules": [
            "profile-analysis",
            "content-ideas",
            "media-analysis",
            "audio-transcription",
            "cdn-resolver",
            "instagram-discovery"
        ]
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


@app.post("/analyze-reel", tags=["media"])
def analyze_reel_api(req: ReelAnalyzeRequest):
    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No video URL provided")

        return analyze_reel(normalize_url(raw_url))

    except Exception:
        return error_response("Reel analysis failed", traceback.format_exc())


@app.post("/analyze/reel/vision", tags=["media"])
def analyze_reel_vision_api(req: ReelVisionAnalyzeRequest):
    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No reel URL provided")

        return analyze_reel(normalize_url(raw_url))

    except Exception:
        return error_response("Vision reel analysis failed", traceback.format_exc())


@app.post("/analyze-reel-audio", tags=["media"])
def analyze_reel_audio_api(req: ReelAudioRequest):
    return process_audio(req.media_url)

# ----------------------------
# CDN Resolver
# ----------------------------

@app.post("/resolve/reel", tags=["resolver"])
def resolve_reel_api(req: ReelResolveRequest):
    try:
        return resolve_instagram_cdn(normalize_url(req.url))

    except CDNResolveError as e:
        return error_response("CDN resolution failed", str(e))

    except Exception:
        return error_response("Unexpected resolver error", traceback.format_exc())
