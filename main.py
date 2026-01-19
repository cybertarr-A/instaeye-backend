from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Any, Optional
import traceback
import os
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from supabase import create_client, Client

# ----------------------------
# Core modules (unchanged)
# ----------------------------

from instagram_analyzer import analyze_profiles
from content_ideas import generate_content
from image_analyzer import analyze_image
from video_analyzer import analyze_reel
from top_posts import get_top_posts
from trend_engine import analyze_industry
from audio_pipeline import process_audio
from media_splitter import router as split_router


# ============================
# CONFIG
# ============================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

RAPIDAPI_HOST = "instagram-reels-downloader-api.p.rapidapi.com"
RAPIDAPI_BASE_URL = f"https://{RAPIDAPI_HOST}"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "reels")

REELS_DIR = Path("data/reels")
REELS_DIR.mkdir(parents=True, exist_ok=True)

if not RAPIDAPI_KEY:
    raise RuntimeError("RAPIDAPI_KEY not set")


# ============================
# LAZY SUPABASE
# ============================

def get_supabase_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "Supabase credentials not configured. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# ============================
# APP INIT
# ============================

app = FastAPI(title="InstaEye Backend", version="2.0.0")
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

class ReelDownloadRequest(BaseModel):
    reel_url: Optional[str] = None
    post_url: Optional[str] = None
    url: Optional[str] = None


# ============================
# HELPERS
# ============================

def normalize_instagram_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment=""))


def extract_id_from_url(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    for i, part in enumerate(parts):
        if part in ("p", "reel", "tv") and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]


def extract_video_url(data: dict) -> Optional[str]:
    return (
        data.get("video_url")
        or data.get("url")
        or (data.get("data") or {}).get("video_url")
        or (data.get("data") or {}).get("url")
        or (
            isinstance(data.get("data"), list)
            and data["data"]
            and data["data"][0].get("url")
        )
    )


def download_file(url: str, output_path: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)


def upload_to_supabase(local_path: Path, video_id: str) -> str:
    supabase = get_supabase_client()
    remote_path = f"{video_id}.mp4"

    with open(local_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path,
            f,
            file_options={"content-type": "video/mp4", "upsert": True}
        )

    return (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{remote_path}"
    )


def fetch_and_download_reel(raw_url: str) -> tuple[str, Path]:
    post_url = normalize_instagram_url(raw_url)

    r = requests.get(
        f"{RAPIDAPI_BASE_URL}/download",
        headers={
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": RAPIDAPI_HOST
        },
        params={"url": post_url},
        timeout=30
    )
    r.raise_for_status()

    data = r.json()
    video_url = extract_video_url(data)
    if not video_url:
        raise RuntimeError("No downloadable video found")

    video_id = extract_id_from_url(post_url)
    local_path = REELS_DIR / f"{video_id}.mp4"
    download_file(video_url, local_path)

    return video_id, local_path


# ============================
# ROUTES
# ============================

@app.get("/")
def home():
    return {"status": "InstaEye backend running"}


# 🔹 CDN MODE (Supabase)
@app.post("/download-reel")
def download_reel_api(req: ReelDownloadRequest):
    try:
        url = req.reel_url or req.post_url or req.url
        if not url:
            return {"status": "error", "message": "No URL provided"}

        video_id, local_path = fetch_and_download_reel(url)
        cdn_url = upload_to_supabase(local_path, video_id)

        local_path.unlink(missing_ok=True)

        return {
            "status": "ok",
            "video_id": video_id,
            "cdn_url": cdn_url
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# 🔹 BINARY MODE (n8n file)
@app.post("/download-reel-file")
def download_reel_file(
    req: ReelDownloadRequest,
    background_tasks: BackgroundTasks
):
    try:
        url = req.reel_url or req.post_url or req.url
        if not url:
            return {"status": "error", "message": "No URL provided"}

        video_id, local_path = fetch_and_download_reel(url)
        background_tasks.add_task(local_path.unlink)

        return FileResponse(
            path=local_path,
            media_type="video/mp4",
            filename=f"{video_id}.mp4"
        )

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


# ----------------------------
# Existing routes (unchanged)
# ----------------------------

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
    return process_audio(req.media_url)

@app.post("/top-posts")
def top_posts_api(req: TopPostsRequest):
    return get_top_posts(req.username, req.limit)

@app.post("/generate-content-ideas")
def generate_ideas_api(req: ContentIdeasRequest):
    return generate_content(req.data)

@app.post("/analyze-industry")
def analyze_industry_api(req: IndustryAnalyzeRequest):
    return analyze_industry(req.keywords, req.news_api_key)
