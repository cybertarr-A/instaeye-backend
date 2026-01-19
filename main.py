from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Any, Optional
import traceback
import os
import requests
import subprocess
from pathlib import Path
import json

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


# ============================
# CONFIG
# ============================

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"

REELS_DIR = Path("data/reels")
REELS_DIR.mkdir(parents=True, exist_ok=True)


# ============================
# APP INIT
# ============================

app = FastAPI(title="InstaEye Backend", version="1.6")

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

class InstagramDiscoveryRequest(BaseModel):
    keywords: List[str]
    page: int = 0
    num_results: int = 10

# 🔽 NEW: Reel Download
class ReelDownloadRequest(BaseModel):
    reel_url: str


# ============================
# HELPER FUNCTIONS
# ============================

def build_google_instagram_query(keywords: List[str]) -> str:
    block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({block})"


def serpapi_search(query: str, page: int, num_results: int) -> dict:
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY not set")

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": num_results,
        "start": page * num_results
    }

    response = requests.get(SERPAPI_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def extract_instagram_profiles(serp_data: dict) -> List[dict]:
    profiles = []

    for item in serp_data.get("organic_results", []):
        link = item.get("link", "")

        if "instagram.com" not in link:
            continue

        profiles.append({
            "profile_url": link.split("?")[0].rstrip("/"),
            "title": item.get("title"),
            "snippet": item.get("snippet")
        })

    return profiles


def download_instagram_reel(reel_url: str) -> dict:
    """
    Download Instagram reel using yt-dlp
    """

    output_template = str(REELS_DIR / "%(id)s.%(ext)s")

    command = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", output_template,
        reel_url
    ]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip())

    return {
        "status": "ok",
        "message": "Reel downloaded successfully"
    }


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


@app.post("/download-reel")
def download_reel_api(req: ReelDownloadRequest):
    try:
        return download_instagram_reel(req.reel_url)
    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "stage": "reel_download",
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


@app.post("/discover/instagram-accounts")
def discover_instagram_accounts(req: InstagramDiscoveryRequest):
    try:
        query = build_google_instagram_query(req.keywords)
        serp_data = serpapi_search(query, req.page, req.num_results)
        accounts = extract_instagram_profiles(serp_data)

        return {
            "status": "success",
            "query_used": query,
            "total_found": len(accounts),
            "accounts": accounts
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "stage": "instagram_discovery",
            "message": str(e)
        }
