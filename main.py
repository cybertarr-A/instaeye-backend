from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Any, Optional
import traceback
import os
import requests
from pathlib import Path
from urllib.parse import urlparse

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

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")
RAPIDAPI_ENDPOINT = os.getenv("RAPIDAPI_ENDPOINT")

REELS_DIR = Path("data/reels")
REELS_DIR.mkdir(parents=True, exist_ok=True)


# ============================
# APP INIT
# ============================

app = FastAPI(title="InstaEye Backend", version="1.7.0")
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

# ✅ RapidAPI downloader schema
class ReelDownloadRequest(BaseModel):
    reel_url: Optional[str] = None
    post_url: Optional[str] = None
    url: Optional[str] = None


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


def extract_id_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1]


def download_file(url: str, output_path: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def download_reel_via_rapidapi(post_url: str) -> dict:
    if not RAPIDAPI_KEY or not RAPIDAPI_HOST or not RAPIDAPI_ENDPOINT:
        raise RuntimeError("RapidAPI configuration missing")

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }

    params = {
        "url": post_url.strip()
    }

    response = requests.get(
        RAPIDAPI_ENDPOINT,
        headers=headers,
        params=params,
        timeout=30
    )
    response.raise_for_status()

    data = response.json()

    media_items = data.get("media") or data.get("data") or []
    video_url = None

    for item in media_items:
        if item.get("type") == "video" or item.get("extension") == "mp4":
            video_url = item.get("url")
            break

    if not video_url:
        raise RuntimeError("No downloadable video found from RapidAPI")

    video_id = extract_id_from_url(post_url)
    output_path = REELS_DIR / f"{video_id}.mp4"

    download_file(video_url, output_path)

    return {
        "status": "ok",
        "message": "Reel downloaded successfully via RapidAPI",
        "file": str(output_path)
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
    return analyze_reel(url.strip())


@app.post("/analyze-reel-audio")
def analyze_reel_audio_api(req: ReelAudioRequest):
    try:
        return process_audio(req.media_url.strip())
    except Exception as e:
        traceback.print_exc()
        return {
            "status": "error",
            "stage": "audio_pipeline",
            "message": str(e)
        }


# ✅ RapidAPI-powered reel downloader
@app.post("/download-reel")
def download_reel_api(req: ReelDownloadRequest):
    try:
        url = req.reel_url or req.post_url or req.url
        if not url:
            return {
                "status": "error",
                "stage": "reel_download",
                "message": "No reel/post URL provided"
            }

        return download_reel_via_rapidapi(url)

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
