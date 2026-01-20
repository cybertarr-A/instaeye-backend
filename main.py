from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Any
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import subprocess
import traceback
import yt_dlp

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
# APP INIT
# ============================

app = FastAPI(title="InstaEye Backend", version="3.3.0")
app.include_router(split_router)

COOKIE_FILE = Path("cookies.txt")
if not COOKIE_FILE.exists():
    raise RuntimeError("cookies.txt not found. Export Instagram cookies first.")

TMP_DIR = Path("tmp/reels")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# ============================
# REQUEST MODELS
# ============================

class ReelRequest(BaseModel):
    url: Optional[str] = None
    reel_url: Optional[str] = None
    post_url: Optional[str] = None

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

# ============================
# HELPERS
# ============================

def normalize_instagram_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment=""))

def extract_id_from_url(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    for i, p in enumerate(parts):
        if p in ("p", "reel", "tv") and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]

def extract_cdn_urls(insta_url: str) -> list[str]:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
        "cookiefile": str(COOKIE_FILE),
        "extract_flat": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(insta_url, download=False)

    urls = set()

    # 1️⃣ yt-dlp formats
    for f in info.get("formats", []):
        if f.get("vcodec") != "none" and f.get("url"):
            urls.add(f["url"])

    # 2️⃣ direct URL
    if info.get("url"):
        urls.add(info["url"])

    # 3️⃣ Instagram video_versions (most modern reels)
    video_versions = info.get("video_versions")
    if isinstance(video_versions, list):
        for v in video_versions:
            if isinstance(v, dict) and v.get("url"):
                urls.add(v["url"])

    # 4️⃣ DASH manifest (adaptive streams)
    dash = info.get("dash_manifest_url")
    if dash:
        urls.add(dash)

    return list(urls)

def download_with_ytdlp(insta_url: str, output_path: Path):
    cmd = [
        "yt-dlp",
        "--cookies", str(COOKIE_FILE),
        "--no-playlist",
        "-f", "bv*+ba/b",
        "-o", str(output_path),
        insta_url
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

# ============================
# ROUTES
# ============================

@app.get("/")
def home():
    return {"status": "InstaEye backend running"}

# 🔹 CDN URL EXTRACTION
@app.post("/get-reel-cdn")
def get_reel_cdn(req: ReelRequest):
    try:
        raw_url = req.url or req.reel_url or req.post_url
        if not raw_url:
            return {"status": "error", "message": "No URL provided"}

        clean_url = normalize_instagram_url(raw_url)
        video_id = extract_id_from_url(clean_url)
        cdn_urls = extract_cdn_urls(clean_url)

        if not cdn_urls:
            return {"status": "error", "message": "No CDN URLs found"}

        return {
            "status": "ok",
            "video_id": video_id,
            "cdn_urls": cdn_urls
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# 🔹 Binary MP4 download (optional, for n8n)
@app.post("/download-reel-file")
def download_reel_file(req: ReelRequest, background_tasks: BackgroundTasks):
    try:
        raw_url = req.url or req.reel_url or req.post_url
        if not raw_url:
            return {"status": "error", "message": "No URL provided"}

        clean_url = normalize_instagram_url(raw_url)
        video_id = extract_id_from_url(clean_url)
        output_path = TMP_DIR / f"{video_id}.mp4"

        download_with_ytdlp(clean_url, output_path)
        background_tasks.add_task(output_path.unlink)

        return FileResponse(
            path=output_path,
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
