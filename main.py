import os
import time
import json
import logging
import traceback
import tempfile
import requests
from pathlib import Path
from typing import Optional, List, Any
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI
from pydantic import BaseModel, Field

from google import genai
from google.genai import types
from supabase import create_client, Client

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.7.0",
    description="Instagram AI Video Grader (Gemini 2.0 Flash – Audio + Video)"
)

# ============================
# CONFIGURATION
# ============================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
supabase: Optional[Client] = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY else None
)

# ============================
# HELPERS
# ============================

def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment="")).rstrip("/")

def download_video_temp(video_url: str) -> Path:
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with requests.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return Path(tmp_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

# ============================
# REQUEST MODELS
# ============================

class ReelAnalyzeRequest(BaseModel):
    video_url: Optional[str] = None
    media_url: Optional[str] = None
    url: Optional[str] = None

def extract_any_url(req: ReelAnalyzeRequest) -> Optional[str]:
    return req.video_url or req.media_url or req.url

# ============================
# AUDIO + VIDEO SCHEMA
# ============================

class VideoGradeAV(BaseModel):
    audio_timeline_summary: str
    spoken_content_summary: str
    key_spoken_phrases: List[str]
    audio_hook_analysis: str
    audio_quality: str
    emotional_audio_impact: str

    video_timeline_summary: str
    visual_hook_analysis: str
    visual_pacing: str

    audio_visual_sync: str
    content_purpose: str
    call_to_action_detected: str

    retention_score: int
    improvement_tip: str

# ============================
# ROUTES
# ============================

@app.get("/")
def home():
    return {
        "status": "ok",
        "service": "InstaEye Backend",
        "model": MODEL_NAME
    }

# ============================
# AI VIDEO GRADER (FIXED)
# ============================

@app.post("/analyze/reel/grade")
def analyze_reel_grader_api(req: ReelAnalyzeRequest):
    video_path = None
    gemini_file = None

    try:
        raw_url = extract_any_url(req)
        if not raw_url:
            return {"status": "error", "message": "No video URL provided"}

        if not gemini_client:
            return {"status": "error", "message": "Gemini client not initialized"}

        url = normalize_url(raw_url)

        # 1. Download
        video_path = download_video_temp(url)

        # 2. Upload
        gemini_file = gemini_client.files.upload(file=video_path)

        # 3. Wait for processing
        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = gemini_client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        # 4. AUDIO + VIDEO ANALYSIS
        response = gemini_client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                gemini_file,
                (
                    "LISTEN to the AUDIO FIRST.\n\n"
                    "AUDIO TASKS:\n"
                    "- Break audio into chronological segments\n"
                    "- Summarize what is being said\n"
                    "- Identify key spoken phrases\n"
                    "- Analyze first 3 seconds of audio as a hook\n"
                    "- Describe emotional tone and delivery\n\n"
                    "VIDEO TASKS:\n"
                    "- Summarize visuals over time\n"
                    "- Analyze first 3 seconds visually\n"
                    "- Describe pacing and editing\n\n"
                    "SYNC & STRATEGY:\n"
                    "- Explain how audio and visuals work together\n"
                    "- Identify content purpose and CTA\n"
                    "- Score retention from 1–10\n"
                    "- Suggest one improvement\n\n"
                    "Do NOT transcribe word-for-word.\n"
                    "Respond strictly using the JSON schema."
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoGradeAV,
                temperature=0.2
            )
        )

        analysis_data = response.parsed or json.loads(response.text)

        return {
            "status": "success",
            "video_url": url,
            "model": MODEL_NAME,
            "data": analysis_data
        }

    except Exception:
        return {
            "status": "error",
            "message": "Video grading failed",
            "trace": traceback.format_exc()
        }

    finally:
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except:
                pass

        if gemini_file and gemini_client:
            try:
                gemini_client.files.delete(name=gemini_file.name)
            except:
                pass
