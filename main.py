import os
import time
import uuid
import json
import logging
import traceback
import tempfile
import requests
from pathlib import Path
from typing import Optional, List, Any
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ============================
# EXTERNAL LIBRARIES
# ============================
from google import genai
from google.genai import types
from supabase import create_client, Client

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.6.0",
    description="Stateless Instagram intelligence backend (Gemini 2.0 Flash Video Grader)"
)

# ============================
# CONFIGURATION & CLIENTS
# ============================

# Gemini Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"  # Using Flash for speed and video capability

if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY not set! Video grading will fail.")

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "temp-media")

# Initialize Clients
try:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    supabase: Optional[Client] = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
except Exception as e:
    logging.error(f"Failed to initialize clients: {e}")
    gemini_client = None
    supabase = None

# ============================
# CORE MODULES (ROBUST IMPORT)
# ============================
# We wrap imports in try/except so the app doesn't crash if a file is broken

analyze_profiles = None
generate_content = None
analyze_image = None
analyze_reel_mini = None
analyze_reel_full = None
get_top_posts = None
analyze_industry = None
process_audio = None
resolve_instagram_cdn = None

try:
    # Essential imports
    from instagram_analyzer import analyze_profiles
    from content_ideas import generate_content
    from image_analyzer import analyze_image
    
    # 🔥 Legacy Video Analyzers (Import safely)
    try:
        from mini_video_analyzer import analyze_reel as analyze_reel_mini
    except ImportError:
        logging.warning("mini_video_analyzer not found or invalid.")

    try:
        from video_analyzer import analyze_reel as analyze_reel_full
    except ImportError:
        logging.warning("video_analyzer.analyze_reel not found. Legacy full analysis disabled.")
    
    from top_posts import get_top_posts
    from trend_engine import analyze_industry
    from audio_pipeline import process_audio
    
    # Routers
    from media_splitter import router as split_router
    from audio_transcriber import router as audio_router
    from instagram_finder import router as instagram_finder_router
    from cdn_resolver import resolve_instagram_cdn, CDNResolveError

    # Register Routers
    app.include_router(split_router)
    app.include_router(audio_router)
    app.include_router(instagram_finder_router)

except ImportError as e:
    logging.warning(f"⚠️ Some core modules failed to load: {e}. Running in partial mode.")

# ============================
# DATA MODELS
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

# --- New Grading Models ---
class VideoGrade(BaseModel):
    visual_summary: str = Field(..., description="Describe exactly what happens in the video. Mention people, actions, objects, text overlays, and environment.")
    content_category: str = Field(..., description="Classify content: Education, Promotion, Entertainment, Lifestyle, Meme, or News.")
    promotion_detection: str = Field(..., description="Is this promotional? Mention specific brands, logos, or calls to action visible.")
    hook_analysis: str = Field(..., description="Analyze the first 3 seconds. Is the visual hook strong enough to stop scrolling? Why?")
    virality_potential: str = Field(..., description="Estimate viral potential (High/Medium/Low) based on pacing, visuals, and engagement factors.")

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

def download_video_temp(video_url: str) -> Path:
    """Downloads video to a temp file for processing."""
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with requests.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return Path(tmp_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise e

# ============================
# SYSTEM ROUTES
# ============================

@app.get("/", tags=["system"])
def home():
    return {
        "status": "ok",
        "service": "InstaEye Backend",
        "version": app.version,
        "features": {
            "gemini_grader": "active",
            "legacy_analyzers": "active" if analyze_reel_full else "inactive"
        }
    }

# ============================
# NEW: AI VIDEO GRADER
# ============================

@app.post("/analyze/reel/grade", tags=["media"])
def analyze_reel_grader_api(req: ReelAnalyzeRequest):
    """
    Full AI Video Grader using Gemini 2.0 Flash.
    """
    video_path = None
    gemini_file = None

    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return error_response("No reel URL provided")
        
        url = normalize_url(raw_url)
        
        if not gemini_client:
            return error_response("Gemini Client not initialized. Check API Key.")

        # Download
        print(f"⬇️ Downloading: {url}")
        video_path = download_video_temp(url)

        # Upload
        print("☁️ Uploading to Gemini...")
        gemini_file = gemini_client.files.upload(path=video_path)
        
        # Wait
        print("⏳ Waiting for processing...")
        while gemini_file.state.name == "PROCESSING":
            time.sleep(1)
            gemini_file = gemini_client.files.get(name=gemini_file.name)
        
        if gemini_file.state.name == "FAILED":
            raise RuntimeError(f"Gemini processing failed: {gemini_file.error.message}")

        # Analyze
        print(f"🤖 Analyzing with {MODEL_NAME}...")
        response = gemini_client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                gemini_file,
                "Watch this entire video and grade it based on the visual and content criteria provided."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoGrade,
                temperature=0.2
            )
        )

        # Parse
        try:
            analysis_data = response.parsed
        except:
            analysis_data = json.loads(response.text)

        return {
            "status": "success",
            "video_url": url,
            "data": analysis_data,
            "model": MODEL_NAME
        }

    except Exception as e:
        return error_response("Video Grader Failed", traceback.format_exc())

    finally:
        if video_path and video_path.exists():
            try: video_path.unlink()
            except: pass
        if gemini_file and gemini_client:
            try: gemini_client.files.delete(name=gemini_file.name)
            except: pass

# ============================
# LEGACY ROUTES (SAFE MODE)
# ============================

@app.post("/analyze", tags=["profiles"])
def analyze_profile_api(req: AnalyzeProfilesRequest):
    if not analyze_profiles: return error_response("Module not loaded")
    return analyze_profiles(req.usernames)

@app.post("/generate-content-ideas", tags=["content"])
def generate_ideas_api(req: ContentIdeasRequest):
    if not generate_content: return error_response("Module not loaded")
    return generate_content(req.data)

@app.post("/top-posts", tags=["profiles"])
def top_posts_api(req: TopPostsRequest):
    if not get_top_posts: return error_response("Module not loaded")
    return get_top_posts(req.username, req.limit)

@app.post("/analyze-industry", tags=["industry"])
def analyze_industry_api(req: IndustryAnalyzeRequest):
    if not analyze_industry: return error_response("Module not loaded")
    return analyze_industry(req.keywords, req.news_api_key)

@app.post("/analyze-image", tags=["media"])
def analyze_image_api(req: ImageAnalyzeRequest):
    if not analyze_image: return error_response("Module not loaded")
    return analyze_image(req.media_url)

@app.post("/analyze/reel/mini", tags=["media"])
def analyze_reel_mini_api(req: ReelAnalyzeRequest):
    if not analyze_reel_mini: return error_response("Mini analyzer not loaded")
    try:
        raw_url = extract_any_url(req)
        return analyze_reel_mini(normalize_url(raw_url)) if raw_url else error_response("No URL")
    except Exception:
        return error_response("Mini analyzer failed", traceback.format_exc())

@app.post("/analyze/reel/full", tags=["media"])
def analyze_reel_full_api(req: ReelAnalyzeRequest):
    # Safe check if module loaded
    if not analyze_reel_full:
        return error_response("Legacy Full Analyzer failed to load. Use /analyze/reel/grade instead.")
        
    try:
        raw_url = extract_any_url(req)
        return analyze_reel_full(normalize_url(raw_url)) if raw_url else error_response("No URL")
    except Exception:
        return error_response("Full analyzer failed", traceback.format_exc())

@app.post("/analyze-reel-audio", tags=["media"])
def analyze_reel_audio_api(req: ReelAudioRequest):
    if not process_audio: return error_response("Module not loaded")
    return process_audio(req.media_url)

@app.post("/resolve/reel", tags=["resolver"])
def resolve_reel_api(req: ReelResolveRequest):
    if not resolve_instagram_cdn: return error_response("Module not loaded")
    try:
        return resolve_instagram_cdn(normalize_url(req.url))
    except CDNResolveError as e:
        return error_response("CDN resolution failed", str(e))
    except Exception:
        return error_response("Resolver error", traceback.format_exc())
