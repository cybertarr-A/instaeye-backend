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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY is not set")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ============================
# AUDIO + VIDEO INTELLIGENCE SCHEMA
# ============================

class DeepVideoAnalysis(BaseModel):
    # 1. AUDIO TIMELINE (PRIMARY)
    audio_timeline_summary: str = Field(
        ...,
        description=(
            "Chronologically summarize the AUDIO from start to end. "
            "Break into logical segments (intro, middle, ending). "
            "For each segment describe what is being said or heard, "
            "the tone/emotion, and the purpose (hook, explanation, CTA)."
        )
    )

    spoken_content_summary: str = Field(
        ...,
        description=(
            "Summarize what people are SAYING in the video. "
            "Capture the core spoken message clearly and concisely."
        )
    )

    key_spoken_phrases: List[str] = Field(
        ...,
        description=(
            "List the most important spoken phrases, commands, or sentences "
            "that stand out or are repeated."
        )
    )

    audio_hook_analysis: str = Field(
        ...,
        description=(
            "Analyze the FIRST 3 SECONDS of AUDIO. "
            "What is heard immediately? "
            "Explain why this does or does not stop scrolling."
        )
    )

    audio_quality: str = Field(
        ...,
        description=(
            "Evaluate audio clarity and quality. "
            "Consider mic quality, loudness balance, background noise, compression, and distortion."
        )
    )

    emotional_audio_impact: str = Field(
        ...,
        description=(
            "Describe the emotional journey conveyed through audio over time. "
            "Note any shifts in emotion."
        )
    )

    # 2. VIDEO TIMELINE (SECONDARY BUT DETAILED)
    video_timeline_summary: str = Field(
        ...,
        description=(
            "Chronologically summarize the VISUALS from start to end. "
            "Describe major scene changes, actions, text overlays, transitions, "
            "and visual pacing."
        )
    )

    visual_hook_analysis: str = Field(
        ...,
        description=(
            "Analyze the FIRST 3 SECONDS of VISUALS. "
            "Describe movement, framing, text, or pattern interrupts."
        )
    )

    visual_pacing: str = Field(
        ...,
        description=(
            "Describe the visual pacing. "
            "Is it fast-cut, moderate, or slow? "
            "Does pacing support retention?"
        )
    )

    # 3. AUDIO ↔ VIDEO RELATIONSHIP
    audio_visual_sync: str = Field(
        ...,
        description=(
            "Explain how audio and visuals work together. "
            "Are spoken words or beats synchronized with cuts, captions, or actions?"
        )
    )

    # 4. STRATEGY & ENGAGEMENT
    content_purpose: str = Field(
        ...,
        description=(
            "Identify the primary goal of the content: educate, entertain, persuade, motivate, or sell."
        )
    )

    call_to_action_detected: str = Field(
        ...,
        description=(
            "Identify any spoken or visual Call to Action. "
            "Examples: follow, comment, like, buy, watch till end."
        )
    )

    # 5. SCORING & IMPROVEMENT
    retention_score: int = Field(
        ...,
        description=(
            "Score from 1–10 based on overall retention potential. "
            "Consider audio hook strength, clarity, emotion, visual pacing, and sync."
        )
    )

    improvement_tip: str = Field(
        ...,
        description=(
            "Provide ONE specific, high-impact improvement tip. "
            "Can be audio-focused, visual-focused, or sync-focused."
        )
    )

# ============================
# HELPER FUNCTIONS
# ============================

def download_video_temp(video_url: str) -> Path:
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    try:
        logging.info(f"⬇️ Downloading video: {video_url}")
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
        logging.info("☁️ Uploading to Gemini...")
        gemini_file = client.files.upload(file=video_path)

        # 3. Poll for processing (every 2s)
        logging.info("⏳ Waiting for Gemini processing...")
        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        # 4. AUDIO + VIDEO ANALYSIS
        logging.info("🎧🎥 Running multimodal analysis...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                gemini_file,
                (
                    "LISTEN to the AUDIO carefully before analyzing visuals.\n\n"
                    "First:\n"
                    "- Understand what is being spoken\n"
                    "- Break audio into chronological segments\n"
                    "- Summarize meaning, tone, emotion, and intent\n\n"
                    "Then:\n"
                    "- Analyze visuals over time\n"
                    "- Describe hooks, pacing, scene changes, and text\n\n"
                    "Finally:\n"
                    "- Evaluate how audio and visuals work together\n"
                    "- Judge retention and engagement potential\n\n"
                    "Do NOT transcribe word-for-word.\n"
                    "Summarize intelligently.\n\n"
                    "Respond strictly using the provided JSON schema."
                )
            ],
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
            "data": analysis_data
        }

    except ClientError as e:
        return {"status": "error", "message": str(e)}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        # Cleanup local file
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except Exception:
                pass

        # Cleanup Gemini cloud file
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
