import os
import time
import json
import logging
import tempfile
import requests
from pathlib import Path
from typing import Optional, Dict, Any

from google import genai
from google.genai import types
from google.genai.errors import ClientError # Import for error handling
from pydantic import BaseModel, Field

# ============================
# CONFIGURATION
# ============================

# ✅ Gemini 2.0 Flash is multimodal (Video + Audio)
MODEL_NAME = "gemini-2.0-flash"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY is not set. Video analysis will fail.")

try:
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception as e:
    logging.error(f"Failed to initialize Gemini Client: {e}")
    client = None

# ============================
# SUPER-PROMPTS (SCHEMA)
# ============================

class DeepVideoAnalysis(BaseModel):
    # 1. Visual Analysis
    visual_hook_analysis: str = Field(..., description="Analyze the first 3 seconds (The Hook). Describe the visual movement, text overlays, or unexpected action that grabs attention. Is it a 'pattern interrupt'?")
    visual_pacing: str = Field(..., description="Describe the editing speed. Is it fast-paced (TikTok style) with quick cuts, or slow and cinematic? Does the visual pacing match the energy of the content?")
    
    # 2. Audio Analysis (New & Critical)
    audio_type: str = Field(..., description="Classify the audio: Trending Music, Original Voiceover, ASMR/Sound Effects, or Silence. Is the audio clear and high quality?")
    audio_engagement: str = Field(..., description="Listen closely. Does the audio 'beat' sync with the visual transitions? If there is a voiceover, is the tone energetic, calm, or robotic? How does the sound add emotional value?")
    
    # 3. Content Strategy
    content_purpose: str = Field(..., description="What is the goal? Education (How-to), Entertainment (Comedy/Skits), Inspiration, or Sales (Promo)? Who is the target audience?")
    call_to_action_detected: str = Field(..., description="Is there a specific Call to Action (CTA)? Examples: 'Link in bio', 'Follow for more', 'Read caption'. If none, is there an implied engagement bait?")
    
    # 4. Scoring & Improvement
    virality_score: int = Field(..., description="Score from 1-10 based on the 'Stop-Scroll' potential. High scores require strong hooks and high retention.")
    improvement_tip: str = Field(..., description="Provide ONE specific, actionable tip to improve this video. Examples: 'Add captions for silent viewers', 'Cut the dead air at 0:05', 'Use a trending audio track'.")

# ============================
# HELPER FUNCTIONS
# ============================

def download_video_temp(video_url: str) -> Path:
    """Downloads video to a temporary file."""
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    
    try:
        logging.info(f"⬇️ Downloading video from: {video_url}")
        with requests.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return Path(tmp_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise RuntimeError(f"Failed to download video: {e}")

# ============================
# MAIN ANALYZER FUNCTION
# ============================

def analyze_reel(video_url: str) -> Dict[str, Any]:
    """
    Performs a full deep-dive analysis of an Instagram Reel or TikTok video.
    Uploads the file to Gemini 2.0 Flash for native video+audio understanding.
    """
    video_path = None
    gemini_file = None

    if not client:
        return {"status": "error", "message": "Gemini API Key missing"}

    try:
        # 1. Download Video
        video_path = download_video_temp(video_url)

        # 2. Upload to Gemini (Native Video Support)
        logging.info("☁️ Uploading video to Gemini...")
        
        # ✅ FIXED: 'file=' is the correct argument
        gemini_file = client.files.upload(file=video_path)
        
        # 3. Poll for Processing
        logging.info(f"⏳ Waiting for video processing (URI: {gemini_file.uri})...")
        while gemini_file.state.name == "PROCESSING":
            time.sleep(1)
            gemini_file = client.files.get(name=gemini_file.name)
        
        if gemini_file.state.name == "FAILED":
            raise RuntimeError(f"Gemini processing failed: {gemini_file.error.message}")

        # 4. Analyze with Retry Logic
        logging.info(f"🤖 Analyzing with {MODEL_NAME} (Audio + Video)...")
        
        max_retries = 3
        retry_delay = 5  # Start with 5 seconds

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[
                        gemini_file,
                        # This prompt guides the model to use the schema definitions
                        "Watch this video carefully and LISTEN to the audio track. "
                        "Analyze the synchronization between sound and visuals. "
                        "Evaluate the hook, pacing, and overall engagement strategy based on the JSON schema."
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=DeepVideoAnalysis,
                        temperature=0.2 
                    )
                )

                # 5. Parse Results
                try:
                    analysis_data = response.parsed
                except:
                    analysis_data = json.loads(response.text)

                return {
                    "status": "success",
                    "video_url": video_url,
                    "data": analysis_data,
                    "model": MODEL_NAME
                }

            except ClientError as e:
                # ✅ FIXED: Catch 429 Rate Limit Errors
                if "429" in str(e) or getattr(e, 'code', 0) == 429:
                    if attempt < max_retries - 1:
                        logging.warning(f"⚠️ Rate Limit Hit (429). Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise e # Give up after retries
                else:
                    raise e # Raise other errors immediately

    except Exception as e:
        logging.error(f"❌ Analysis failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "trace": "See logs for details"
        }

    finally:
        # 6. Cleanup (Crucial for cost/storage management)
        if video_path and video_path.exists():
            try:
                video_path.unlink()
            except Exception:
                pass
                
        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
                logging.info("🧹 Gemini cloud file deleted")
            except Exception:
                pass

if __name__ == "__main__":
    # Local Test
    test_url = "https://www.w3schools.com/html/mov_bbb.mp4"
    result = analyze_reel(test_url)
    print(json.dumps(result, indent=2, default=str))
