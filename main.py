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
from instaloader_worker import download_reel

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.0.0",
    description="Stateless Instagram intelligence backend (resolver-free)"
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
    - local file URL (from instaloader / yt-dlp)
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

class ReelDownloadRequest(BaseModel):
    reel_url: str


# ============================
# HELPERS
# ============================

def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment="")).rstrip("/")

def extract_any_url(req: ReelAnalyzeRequest) -> Optional[str]:
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
        "resolver": "disabled",
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
    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No video URL provided")

        clean_url = normalize_url(raw_url)

        # IMPORTANT:
        # At this stage we expect:
        # - CDN mp4 URL
        # - local file path
        # - temporary Supabase URL
        return analyze_reel(clean_url)

    except Exception:
        return error_response(
            "Reel analysis failed",
            traceback.format_exc()
        )
        
@app.post("/download-reel", tags=["media"])
def download_reel_api(req: ReelDownloadRequest):
    try:
        path = download_reel(req.reel_url)
        return {"status": "ok", "file_path": path}
    except Exception as e:
        return error_response(str(e))

@app.post("/analyze-reel-audio", tags=["media"])
def analyze_reel_audio_api(req: ReelAudioRequest):
    return process_audio(req.media_url)
