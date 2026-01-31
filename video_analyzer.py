import os
import time
import json
import logging
import tempfile
import requests
from pathlib import Path
from typing import Dict, Any, List
from urllib.parse import urlparse

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from pydantic import BaseModel, Field

# ============================
# CONFIGURATION
# ============================

MODEL_NAME = "gemini-2.0-flash"
AUDIO_PROMPT_VERSION = "v2.4-human-spoken-content"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set")

client = genai.Client(api_key=GEMINI_API_KEY)

# ============================
# SCHEMA
# ============================

class DeepVideoAnalysis(BaseModel):
    audio_timeline_summary: str
    spoken_content_summary: str
    what_people_are_saying: List[str]
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
# HELPERS
# ============================

def is_instagram_cdn(url: str) -> bool:
    host = urlparse(url).netloc
    return "cdninstagram.com" in host or "fbcdn.net" in host


def download_video_temp(video_url: str) -> Path:
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    try:
        with requests.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return Path(tmp_path)

    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise RuntimeError(f"Video download failed: {e}")

# ============================
# MAIN ANALYZER
# ============================

def analyze_reel(video_url: str) -> Dict[str, Any]:
    video_path = None
    gemini_file = None

    try:
        # ============================
        # CASE 1: INSTAGRAM CDN URL
        # ============================
        if is_instagram_cdn(video_url):
            logging.info("Using Gemini remote video ingestion (CDN URL)")

            video_input = {
                "file_uri": video_url,
                "mime_type": "video/mp4",
            }

        # ============================
        # CASE 2: NORMAL MP4 URL
        # ============================
        else:
            video_path = download_video_temp(video_url)
            gemini_file = client.files.upload(file=video_path)
            video_input = gemini_file

            while gemini_file.state.name == "PROCESSING":
                time.sleep(2)
                gemini_file = client.files.get(name=gemini_file.name)

            if gemini_file.state.name == "FAILED":
                raise RuntimeError(gemini_file.error.message)

        # ============================
        # PROMPT (UNCHANGED)
        # ============================

        ANALYSIS_PROMPT = f"""
You are a senior expert in:
- Short-form video audio psychology
- Viral content hooks
- Audience retention analysis

CRITICAL RULE:
AUDIO is the PRIMARY signal. Visuals are SECONDARY.

STEP 1 — AUDIO (MOST IMPORTANT):
- Listen carefully to the full audio timeline
- Break audio into intro, middle, and ending
- Describe what is said, tone, emotion, and intent

VERY IMPORTANT:
You MUST clearly answer:
"What are people actually saying in this video?"

For the field `what_people_are_saying`:
- Write 5–10 paraphrased spoken lines
- Use natural human language
- Do NOT transcribe word-for-word

STEP 2 — VISUALS:
- Summarize visuals chronologically
- Analyze first 3-second visual hook
- Describe pacing and scene changes

STEP 3 — AUDIO ↔ VIDEO:
- Explain how audio supports or conflicts with visuals

STEP 4 — STRATEGY:
- Identify content purpose
- Detect CTA
- Score retention honestly

RULES:
- Respond ONLY in valid JSON
- Strictly match schema
- Prompt version: {AUDIO_PROMPT_VERSION}
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[video_input, ANALYSIS_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DeepVideoAnalysis,
                temperature=0.2,
            ),
        )

        return {
            "status": "success",
            "video_url": video_url,
            "model": MODEL_NAME,
            "prompt_version": AUDIO_PROMPT_VERSION,
            "data": response.parsed or json.loads(response.text),
        }

    except ClientError as e:
        return {"status": "error", "message": str(e)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        if video_path and video_path.exists():
            video_path.unlink(missing_ok=True)

        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
            except Exception:
                pass

# ============================
# TEST
# ============================

if __name__ == "__main__":
    test_url = "https://scontent-ams2-1.cdninstagram.com/....mp4"
    print(json.dumps(analyze_reel(test_url), indent=2))
