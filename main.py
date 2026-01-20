from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Any
from pathlib import Path
from urllib.parse import urlparse, urlunparse
import subprocess
import traceback
import yt_dlp
import os
import requests 

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

app = FastAPI(title="InstaEye Backend", version="3.6.0")
app.include_router(split_router)

# N8N Webhook URL
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# --- COOKIE HANDLING (CRITICAL FIX) ---
COOKIE_FILE = Path("cookies.txt")
IG_COOKIES = os.getenv("IG_COOKIES") # Paste Netscape formatted cookies here in Railway

if IG_COOKIES:
    # Create the cookie file dynamically from the Env Var
    with open(COOKIE_FILE, "w") as f:
        f.write(IG_COOKIES)
    print("✅ Cookies loaded from Environment Variable.")
else:
    print("⚠️ No IG_COOKIES found. Public posts might fail due to rate limits.")

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

def get_instagram_cdn_info(post_url: str):
    """
    Extracts the direct video/CDN URL using yt-dlp with Headers & Cookies.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        # Spoof User Agent to look like a Mac using Chrome
        'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # Use cookies if the file exists (created from Env Var)
    if COOKIE_FILE.exists():
        ydl_opts['cookiefile'] = str(COOKIE_FILE)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting extraction for: {post_url}")
            info = ydl.extract_info(post_url, download=False)
            
            video_url = info.get('url')
            
            # Fallback: Check formats if main URL is missing
            if not video_url:
                for f in info.get('formats', []):
                    if f.get('ext') == 'mp4':
                        video_url = f.get('url')
                        break
            
            if not video_url:
                print("❌ yt-dlp returned metadata but NO video URL.")
                return None

            return {
                "cdn_url": video_url,
                "caption": info.get('title'),
                "author": info.get('uploader'),
                "video_id": info.get('id')
            }

    except Exception as e:
        print(f"❌ Extraction Error: {str(e)}")
        # Return the actual error to the API response for debugging
        return {"error": str(e)}

def download_with_ytdlp(insta_url: str, output_path: Path):
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bv*+ba/b",
        "-o", str(output_path),
        insta_url
    ]
    
    # Add cookies if available
    if COOKIE_FILE.exists():
        cmd.extend(["--cookies", str(COOKIE_FILE)])

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

@app.post("/get-reel-cdn")
def get_reel_cdn(req: ReelRequest):
    try:
        raw_url = req.url or req.reel_url or req.post_url
        if not raw_url:
            return {"status": "error", "message": "No URL provided"}

        clean_url = normalize_instagram_url(raw_url)
        
        # 1. Extract Info
        data = get_instagram_cdn_info(clean_url)
        
        # Check for specific error dictionary return
        if data and "error" in data:
            return {"status": "error", "message": f"yt-dlp error: {data['error']}"}

        if not data or not data.get("cdn_url"):
            return {"status": "error", "message": "Could not extract video URL (Login might be required)"}

        # 2. Send to n8n
        n8n_status = "skipped"
        if N8N_WEBHOOK_URL:
            payload = {
                "video_url": data["cdn_url"],
                "caption": data["caption"],
                "author": data["author"],
                "source": "instaeye_backend"
            }
            try:
                requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
                n8n_status = "sent"
            except Exception as e:
                print(f"Failed to send to n8n: {e}")
                n8n_status = "failed"

        return {
            "status": "ok",
            "n8n_status": n8n_status,
            "data": data
        }

    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# 🔹 Binary MP4 download
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
