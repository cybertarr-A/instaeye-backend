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
AUDIO_PROMPT_VERSION = "v2.3-audio-psychoacoustic"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY is not set")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ============================
# AUDIO + VIDEO INTELLIGENCE SCHEMA
# ============================

class DeepVideoAnalysis(BaseModel):
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
# HELPER FUNCTIONS
# ============================

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
# MAIN ANALYZER
# ============================

def analyze_reel(video_url: str) -> Dict[str, Any]:
    video_path = None
    gemini_file = None

    if not client:
        return {"status": "error", "message": "Gemini client not initialized"}

    try:
        # 1. Download video
        video_path = download_video_temp(video_url)

        # 2. Upload to Gemini
        gemini_file = client.files.upload(file=video_path)

        # 3. Poll for processing
        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        # ============================
        # 🔊 AUDIO-FIRST MULTIMODAL PROMPT
        # ============================

        ANALYSIS_PROMPT = f"""
You are a senior expert in:
- Short-form video audio psychology
- Viral marketing hooks
- Audience retention mechanics

CRITICAL INSTRUCTION:
AUDIO is the PRIMARY signal. Visuals are SECONDARY.

Step 1 — AUDIO ANALYSIS (MOST IMPORTANT):
- Listen carefully to the entire audio timeline
- Break it into logical segments (intro, middle, ending)
- For each segment describe:
  • What is being said or heard
  • Tone, emotion, and energy
  • Psychological intent (hook, tension, authority, CTA)

Focus deeply on:
- Voice tone and confidence
- Speaking speed and urgency
- Emotional shifts
- Curiosity gaps and promises of value
- Scroll-stopping strength of the FIRST 3 SECONDS

Step 2 — VIDEO ANALYSIS:
- Summarize visuals chronologically
- Identify visual hooks in the first 3 seconds
- Describe pacing, motion, text overlays, and transitions

Step 3 — AUDIO ↔ VIDEO SYNC:
- Explain how audio reinforces visuals
- Note any mismatches or missed opportunities

Step 4 — STRATEGIC EVALUATION:
- Identify content purpose
- Detect CTA (spoken or visual)
- Judge retention potential honestly

Rules:
- Do NOT transcribe word-for-word
- Summarize intelligently
- Be precise, not generic
- Use marketing + psychology language
- Respond ONLY in valid JSON
- Strictly match the provided schema
- Prompt version: {AUDIO_PROMPT_VERSION}
"""

        # 4. Run Gemini analysis
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[gemini_file, ANALYSIS_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DeepVideoAnalysis,
                temperature=0.2
            )
        )

        analysis_data = response.parsed or json.loads(response.text)

        return {
            "status": "success",
            "video_url": video_url,
            "model": MODEL_NAME,
            "prompt_version": AUDIO_PROMPT_VERSION,
            "data": analysis_data
        }

    except ClientError as e:
        return {"status": "error", "message": str(e)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except Exception:
                pass

        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
            except Exception:
                pass

# ============================
# LOCAL TEST
# ============================

if __name__ == "__main__":
    test_url = "https://www.w3schools.com/html/mov_bbb.mp4"
    result = analyze_reel(test_url)
    print(json.dumps(result, indent=2, default=str))
