import os
import time
import json
import logging
import tempfile
import requests
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from google import genai
from google.genai import types

# ======================================================
# APP INIT
# ======================================================

app = FastAPI(
    title="InstaEye Backend",
    version="5.0.0",
    description="Unified API Gateway for InstaEye AI System"
)

# ======================================================
# CONFIG
# ======================================================

MODEL_NAME = "gemini-2.0-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY not set")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ======================================================
# HELPERS
# ======================================================

def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment="")).rstrip("/")

def download_video_temp(video_url: str) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        with requests.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        return Path(tmp)
    except Exception as e:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise RuntimeError(f"Download failed: {e}")

# ======================================================
# REQUEST MODELS
# ======================================================

class VideoRequest(BaseModel):
    video_url: Optional[str] = None
    media_url: Optional[str] = None
    url: Optional[str] = None

class ImageRequest(BaseModel):
    image_url: str

class IndustryRequest(BaseModel):
    keywords: List[str]

class ContentIdeaRequest(BaseModel):
    analysis_data: dict
    brand_tone: Optional[str] = None

def extract_url(req: VideoRequest) -> str:
    return req.video_url or req.media_url or req.url

# ======================================================
# RESPONSE SCHEMAS
# ======================================================

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

# ======================================================
# CORE ANALYSIS FUNCTIONS (SHARED)
# ======================================================

def run_video_analysis(url: str, mode: str):
    video_path = None
    gemini_file = None

    if not gemini_client:
        raise HTTPException(500, "Gemini not initialized")

    try:
        video_path = download_video_temp(url)
        gemini_file = gemini_client.files.upload(file=video_path)

        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = gemini_client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        PROMPTS = {
            "grade": "AUDIO FIRST. Grade retention, hook, pacing. Return JSON.",
            "deep": "Deep audio-first analysis. What are people saying? Why it works. JSON.",
            "mini": "Fast hook-only analysis. First 5 seconds. JSON."
        }

        response = gemini_client.models.generate_content(
            model=MODEL_NAME,
            contents=[gemini_file, PROMPTS[mode]],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoGradeAV if mode == "grade" else None,
                temperature=0.2
            )
        )

        return response.parsed or json.loads(response.text)

    finally:
        if video_path and video_path.exists():
            video_path.unlink(missing_ok=True)
        if gemini_file:
            gemini_client.files.delete(name=gemini_file.name)

# ======================================================
# BASE ROUTES
# ======================================================

@app.get("/")
def root():
    return {"status": "ok", "service": "InstaEye"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# ======================================================
# VIDEO ENDPOINTS
# ======================================================

@app.post("/analyze/reel/grade")
def reel_grade(req: VideoRequest):
    url = extract_url(req)
    if not url:
        raise HTTPException(400, "Missing video URL")
    return run_video_analysis(normalize_url(url), "grade")

@app.post("/analyze/reel")
def reel_deep(req: VideoRequest):
    url = extract_url(req)
    if not url:
        raise HTTPException(400, "Missing video URL")
    return run_video_analysis(normalize_url(url), "deep")

@app.post("/analyze/reel/mini")
def reel_mini(req: VideoRequest):
    url = extract_url(req)
    if not url:
        raise HTTPException(400, "Missing video URL")
    return run_video_analysis(normalize_url(url), "mini")

# ======================================================
# IMAGE ANALYSIS
# ======================================================

@app.post("/analyze/image")
def analyze_image(req: ImageRequest):
    return {
        "status": "success",
        "insight": "Image analysis placeholder (wire existing script here)"
    }

# ======================================================
# INDUSTRY / TREND ANALYSIS
# ======================================================

@app.post("/analyze/industry")
def analyze_industry(req: IndustryRequest):
    return {
        "status": "success",
        "keywords": req.keywords,
        "trend_summary": "Industry trend analysis placeholder"
    }

# ======================================================
# CONTENT IDEA GENERATION
# ======================================================

@app.post("/generate/content-ideas")
def generate_content(req: ContentIdeaRequest):
    return {
        "status": "success",
        "ideas": [
            "Hook-based reel using curiosity gap",
            "Authority-style explainer with fast pacing"
        ],
        "brand_tone": req.brand_tone or "neutral"
    }

# ======================================================
# BACKWARD-COMPAT ALIASES (n8n SAFE)
# ======================================================

@app.post("/get-one-video")
@app.post("/analyze-reel/grade")
def alias_reel(req: VideoRequest):
    return reel_grade(req)
