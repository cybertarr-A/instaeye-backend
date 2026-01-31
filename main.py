from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Any
from urllib.parse import urlparse, urlunparse
import traceback

# ============================
# CORE ANALYSIS MODULES
# ============================

from instagram_analyzer import analyze_100_accounts as analyze_profiles
from content_ideas import generate_content
from image_analyzer import analyze_image

from video_analyzer import analyze_reel as analyze_reel_full

from top_posts import get_top_posts
from trend_engine import analyze_industry
from audio_pipeline import process_audio

# ============================
# ROUTERS
# ============================

from media_splitter import router as split_router
from audio_transcriber import router as audio_router
from instagram_finder import router as instagram_finder_router

# ============================
# CDN RESOLVER + UPLOADER
# ============================

from cdn_resolver import resolve_instagram_cdn, CDNResolveError
from instagram_cdn_uploader import upload_instagram_video_cdn

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.6.4",
    description="Stateless Instagram intelligence backend (ranking, media, AI analysis)"
)

# ============================
# ROUTER REGISTRATION
# ============================

app.include_router(split_router)
app.include_router(audio_router)
app.include_router(instagram_finder_router)

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


class ReelResolveUploadRequest(BaseModel):
    url: str
    folder: Optional[str] = "reels"

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
# SYSTEM ROUTES
# ============================

@app.get("/", tags=["system"])
def home():
    return {
        "status": "ok",
        "service": "InstaEye backend",
        "version": app.version,
        "routes": {
            "profiles": ["/analyze", "/top-posts"],
            "media": [
                "/analyze-image",
                "/analyze/reel/full",
                "/analyze-reel-audio"
            ],
            "industry": ["/analyze-industry"],
            "resolver": [
                "/resolve/reel",
                "/resolve/reel/upload"
            ]
        }
    }


@app.get("/health", tags=["system"])
def health():
    return {"status": "healthy"}

# ============================
# PROFILE & CONTENT
# ============================

@app.post("/analyze", tags=["profiles"])
def analyze_profile_api(req: AnalyzeProfilesRequest):
    """
    Scans up to 100 accounts
    Filters last 7 days
    Returns Top 30 posts per account
    """
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

# ============================
# MEDIA ANALYSIS
# ============================

@app.post("/analyze-image", tags=["media"])
def analyze_image_api(req: ImageAnalyzeRequest):
    return analyze_image(req.media_url)


@app.post("/analyze/reel/full", tags=["media"])
def analyze_reel_full_api(req: ReelAnalyzeRequest):
    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No reel URL provided")

        return analyze_reel_full(normalize_url(raw_url))

    except Exception:
        return error_response(
            "Full video analyzer failed",
            traceback.format_exc()
        )


@app.post("/analyze-reel-audio", tags=["media"])
def analyze_reel_audio_api(req: ReelAudioRequest):
    return process_audio(req.media_url)

# ============================
# CDN RESOLVER ONLY
# ============================

@app.post("/resolve/reel", tags=["resolver"])
def resolve_reel_api(req: ReelResolveRequest):
    try:
        return resolve_instagram_cdn(normalize_url(req.url))

    except CDNResolveError as e:
        return error_response("CDN resolution failed", str(e))

    except Exception:
        return error_response(
            "Unexpected resolver error",
            traceback.format_exc()
        )

# ============================
# CDN RESOLVE + SUPABASE UPLOAD
# ============================

@app.post("/resolve/reel/upload", tags=["resolver"])
def resolve_and_upload_reel_api(req: ReelResolveUploadRequest):
    """
    Resolve Instagram Reel CDN
    Download video
    Upload to Supabase
    Return Supabase CDN URL
    """
    try:
        normalized_url = normalize_url(req.url)

        # Step 1: Resolve Instagram CDN
        resolved = resolve_instagram_cdn(normalized_url)

        cdn_url = resolved.get("video_cdn_url") or resolved.get("cdn_url")
        if not cdn_url:
            return error_response("No video CDN URL found")

        # Step 2: Upload to Supabase
        uploaded = upload_instagram_video_cdn(
            cdn_url=cdn_url,
            folder=req.folder
        )

        return {
            "status": "success",
            "instagram_url": normalized_url,
            "instagram_cdn": cdn_url,
            "supabase": uploaded
        }

    except CDNResolveError as e:
        return error_response("CDN resolution failed", str(e))

    except Exception:
        return error_response(
            "Resolve + upload failed",
            traceback.format_exc()
        )
