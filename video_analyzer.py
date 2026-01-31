import os
import time
import json
import logging
import tempfile
import requests
from pathlib import Path
from typing import Dict, Any, List

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
    raise RuntimeError("❌ GEMINI_API_KEY is not set")

client = genai.Client(api_key=GEMINI_API_KEY)

# ============================
# AUDIO + VIDEO INTELLIGENCE SCHEMA
# ============================

class DeepVideoAnalysis(BaseModel):
    # 🔊 AUDIO
    audio_timeline_summary: str
    spoken_content_summary: str

    what_people_are_saying: List[str]
    key_spoken_phrases: List[str]

    audio_hook_analysis: str
    audio_quality: str
    emotional_audio_impact: str

    # 🎥 VIDEO
    video_timeline_summary: str
    visual_hook_analysis: str
    visual_pacing: str

    # 🧠 STRATEGY
    audio_visual_sync: str
    content_purpose: str
    call_to_action_detected: str

    retention_score: int
    improvement_tip: str

# ============================
# INSTAGRAM CDN SAFE DOWNLOADER
# ============================

def download_video_temp(video_url: str) -> Path:
    """
    Downloads MP4 from Instagram CDN or normal URLs.
    Handles headers, redirects, and streaming safely.
    """

    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",

        # 🔥 REQUIRED FOR INSTAGRAM
        "Referer": "https://www.instagram.com/",
        "Range": "bytes=0-",
    }

    try:
        with requests.get(
            video_url,
            headers=headers,
            stream=True,
            timeout=60,
            allow_redirects=True,
        ) as r:

            if r.status_code not in (200, 206):
                raise RuntimeError(
                    f"Failed to fetch video "
                    f"(status={r.status_code})"
                )

            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

        return Path(tmp_path)

    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise RuntimeError(f"Instagram CDN download failed: {e}")

# ============================
# MAIN ANALYZER
# ============================

def analyze_reel(video_url: str) -> Dict[str, Any]:
    video_path = None
    gemini_file = None

    try:
        # 1. Download video (Instagram CDN safe)
        video_path = download_video_temp(video_url)

        # 2. Upload to Gemini
        gemini_file = client.files.upload(file=video_path)

        # 3. Poll until processed
        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        # ============================
        # AUDIO-FIRST PROMPT
        # ============================

        ANALYSIS_PROMPT = f"""
You are a senior expert in:
- Short-form video audio psychology
- Viral content hooks
- Audience retention analysis

CRITICAL RULE:
AUDIO is the PRIMARY signal. Visuals are SECONDARY.

STEP 1 — AUDIO (MOST IMPORTANT):
- Analyze full spoken audio timeline
- Break into intro, middle, ending
- Explain tone, intent, emotion

IMPORTANT:
Answer clearly:
"What are people actually saying?"

For `what_people_are_saying`:
- 5–10 paraphrased spoken thoughts
- Natural human language
- NOT verbatim transcription

STEP 2 — VISUALS:
- Chronological visual summary
- First 3-second hook analysis
- Pacing and scene flow

STEP 3 — AUDIO ↔ VIDEO:
- How audio supports or conflicts visuals

STEP 4 — STRATEGY:
- Content purpose
- CTA detection
- Honest retention score

RULES:
- No verbatim transcription
- No fluff
- Marketing + psychology language
- Respond ONLY valid JSON
- Match schema exactly
- Prompt version: {AUDIO_PROMPT_VERSION}
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[gemini_file, ANALYSIS_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DeepVideoAnalysis,
                temperature=0.2,
            ),
        )

        analysis_data = response.parsed or json.loads(response.text)

        return {
            "status": "success",
            "video_url": video_url,
            "model": MODEL_NAME,
            "prompt_version": AUDIO_PROMPT_VERSION,
            "data": analysis_data,
        }

    except ClientError as e:
        return {"status": "error", "message": str(e)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        # Cleanup temp video
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except Exception:
                pass

        # Cleanup Gemini file
        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
            except Exception:
                pass

# ============================
# LOCAL TEST
# ============================

if __name__ == "__main__":
    # ✅ Works with Instagram CDN URLs
    test_url = "https://scontent.cdninstagram.com/v/t66.30100-16/XXXXXXXX.mp4"

    result = analyze_reel(test_url)
    print(json.dumps(result, indent=2, default=str))
