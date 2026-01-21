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
from mini_video_analyzer import analyze_reel   # ✅ UPDATED IMPORT
from top_posts import get_top_posts
from trend_engine import analyze_industry
from audio_pipeline import process_audio
from media_splitter import router as split_router

# ----------------------------
# CDN Resolver (yt-dlp only)
# ----------------------------

from cdn_resolver import resolve_instagram_cdn, CDNResolveError

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.1.1",
    description="Stateless Instagram intelligence backend (resolver-isolated)"
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
    """
    Accepts:
    - direct CDN mp4 URL
    - Supabase temporary URL
    - local file path (internal pipeline)
    """
    video_url: Optional[str] = None
    media_url: Optional[str] = None
    url: Optional[str] = None


class ReelVisionAnalyzeRequest(BaseModel):
    """
    Explicit vision-only reel analysis (mini analyzer)
    """
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
        "mode": "stateless",
        "resolver": "isolated",
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


@app.post("/analyze-reel", tags=["media"])
def analyze_reel_api(req: ReelAnalyzeRequest):
    """
    Generic reel analysis entry.
    Can accept CDN, Supabase temp URL, or internal file path.
    """
    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No video URL provided")

        clean_url = normalize_url(raw_url)
        return analyze_reel(clean_url)

    except Exception:
        return error_response(
            "Reel analysis failed",
            traceback.format_exc()
        )


@app.post("/analyze/reel/vision", tags=["media"])
def analyze_reel_vision_api(req: ReelVisionAnalyzeRequest):
    """
    Vision-only, 3-prompt lightweight reel analyzer
    (mini_video_analyzer)
    """
    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No reel URL provided")

        clean_url = normalize_url(raw_url)
        return analyze_reel(clean_url)

    except Exception:
        return error_response(
            "Vision reel analysis failed",
            traceback.format_exc()
        )


@app.post("/analyze-reel-audio", tags=["media"])
def analyze_reel_audio_api(req: ReelAudioRequest):
    return process_audio(req.media_url)

# ----------------------------
# CDN RESOLVER (yt-dlp)
# ----------------------------

@app.post("/resolve/reel", tags=["resolver"])
def resolve_reel_api(req: ReelResolveRequest):
    try:
        clean_url = normalize_url(req.url)
        return resolve_instagram_cdn(clean_url)

    except CDNResolveError as e:
        return error_response("CDN resolution failed", str(e))

    except Exception:
        return error_response(
            "Unexpected resolver error",
            traceback.format_exc()
        )
