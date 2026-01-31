import os
import time
import json
import logging
import tempfile
import subprocess
import requests
from pathlib import Path
from typing import Dict, Any, List

from google import genai
from google.genai import types
from google.genai.errors import ClientError
from pydantic import BaseModel

# ============================
# CONFIG
# ============================

MODEL_NAME = "gemini-2.0-flash"
AUDIO_PROMPT_VERSION = "v2.4-human-spoken-content"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing")

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
# DOWNLOADERS
# ============================

def try_direct_download(url: str, out: Path) -> bool:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.instagram.com/",
        "Range": "bytes=0-",
    }

    r = requests.get(
        url,
        headers=headers,
        stream=True,
        timeout=30,
        allow_redirects=True,
    )

    if r.status_code not in (200, 206):
        return False

    with open(out, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    return True


def yt_dlp_download(url: str, out: Path):
    cmd = [
        "yt-dlp",
        "-f", "best",
        "-o", str(out),
        "--no-playlist",
        "--quiet",
        url,
    ]

    subprocess.run(cmd, check=True)


def download_video_temp(video_url: str) -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    tmp_path = Path(tmp)

    try:
        # 1️⃣ Try direct CDN
        if try_direct_download(video_url, tmp_path):
            return tmp_path

        # 2️⃣ Fallback: yt-dlp (REAL FIX)
        yt_dlp_download(video_url, tmp_path)
        return tmp_path

    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"Video download failed: {e}")

# ============================
# ANALYZER
# ============================

def analyze_reel(video_url: str) -> Dict[str, Any]:
    video_path = None
    gemini_file = None

    try:
        video_path = download_video_temp(video_url)

        gemini_file = client.files.upload(file=video_path)

        while gemini_file.state.name == "PROCESSING":
            time.sleep(2)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError(gemini_file.error.message)

        prompt = f"""
AUDIO-FIRST viral analysis.
No transcription. Paraphrase only.
Respond ONLY valid JSON.
Schema enforced.
Prompt version: {AUDIO_PROMPT_VERSION}
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[gemini_file, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DeepVideoAnalysis,
                temperature=0.2,
            ),
        )

        return {
            "status": "success",
            "video_url": video_url,
            "data": response.parsed or json.loads(response.text),
        }

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
    url = "https://www.instagram.com/reel/DTtUSGgkq0k/"
    print(json.dumps(analyze_reel(url), indent=2))
