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
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

# ============================
# APP INIT
# ============================

app = FastAPI(
    title="InstaEye Backend",
    version="4.8.0",
    description="Instagram AI Video Grader (Gemini 2.0 Flash – Audio + Video)"
)

# ============================
# CONFIGURATION
# ============================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash"

if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY not set")

gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise RuntimeError(f"Video download failed: {e}")

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
# RESPONSE SCHEMA
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
# BASIC ROUTES
# ============================

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "InstaEye Backend",
        "model": MODEL_NAME
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

# ============================
# CORE ANALYSIS LOGIC
# ============================

def run_reel_analysis(url: str):
    video_path = None
    gemini_file = None

    if not gemini_client:
        raise HTTPException(status_code=500, detail="Gemini client not initialized")

    try:
        # Download
        video_path = download_video_temp(url)

        # Upload
        gemini_file = gemini_client.files.upload(file=video_path)

        # Wait for processing
        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = gemini_client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        # Gemini analysis
        response = gemini_client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                gemini_file,
                (
                    "AUDIO IS PRIMARY.\n\n"
                    "Analyze the video as follows:\n\n"
                    "AUDIO:\n"
                    "- Break audio into intro, middle, end\n"
                    "- Summarize what people are saying (paraphrased)\n"
                    "- Identify key spoken phrases\n"
                    "- Analyze first 3 seconds as audio hook\n"
                    "- Describe emotional delivery\n\n"
                    "VIDEO:\n"
                    "- Summarize visuals over time\n"
                    "- Analyze first 3 seconds visually\n"
                    "- Describe pacing and editing\n\n"
                    "STRATEGY:\n"
                    "- Explain audio-visual sync\n"
                    "- Identify content purpose and CTA\n"
                    "- Score retention from 1–10\n"
                    "- Give one improvement tip\n\n"
                    "Do NOT transcribe word-for-word.\n"
                    "Respond ONLY in valid JSON."
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=VideoGradeAV,
                temperature=0.2
            )
        )

        return response.parsed or json.loads(response.text)

    finally:
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except:
                pass

        if gemini_file:
            try:
                gemini_client.files.delete(name=gemini_file.name)
            except:
                pass

# ============================
# PRIMARY ENDPOINT
# ============================

@app.post("/analyze/reel/grade")
def analyze_reel_grade(req: ReelAnalyzeRequest):
    raw_url = extract_any_url(req)
    if not raw_url:
        raise HTTPException(status_code=400, detail="No video URL provided")

    url = normalize_url(raw_url)
    data = run_reel_analysis(url)

    return {
        "status": "success",
        "video_url": url,
        "model": MODEL_NAME,
        "data": data
    }

# ============================
# 🔁 BACKWARD-COMPAT ALIAS ROUTES
# ============================

@app.post("/analyze/reel")
@app.post("/analyze/video")
@app.post("/analyze-reel/grade")
@app.post("/get-one-video")
def analyze_reel_alias(req: ReelAnalyzeRequest):
    return analyze_reel_grade(req)
