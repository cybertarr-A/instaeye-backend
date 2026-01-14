import os
import uuid
import time
import subprocess
import requests
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ================= CONFIG =================

FFMPEG = "ffmpeg"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

if not PUBLIC_BASE_URL:
    raise RuntimeError("PUBLIC_BASE_URL env var not set")

TOKEN_TTL_SECONDS = 600  # 10 minutes

# In-memory token store (OK for now, Redis later)
EPHEMERAL_TOKENS: Dict[str, float] = {}

router = APIRouter()

# ================= MODELS =================

class SplitRequest(BaseModel):
    cdn_url: str

# ================= TOKEN UTILS =================

def create_token() -> str:
    token = str(uuid.uuid4())
    EPHEMERAL_TOKENS[token] = time.time() + TOKEN_TTL_SECONDS
    return token

def validate_token(token: str) -> bool:
    exp = EPHEMERAL_TOKENS.get(token)
    if not exp:
        return False
    if time.time() > exp:
        EPHEMERAL_TOKENS.pop(token, None)
        return False
    return True

# ================= MEDIA UTILS =================

def download_video(url: str) -> Path:
    tmp_video = Path("/tmp") / f"src_{uuid.uuid4()}.mp4"

    r = requests.get(url, stream=True, timeout=30)
    if r.status_code != 200:
        raise Exception("Video download failed")

    with open(tmp_video, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)

    return tmp_video

def split_media(video_path: Path) -> str:
    request_id = str(uuid.uuid4())
    job_dir = Path(f"/tmp/job_{request_id}")
    job_dir.mkdir(parents=True, exist_ok=True)

    intro_video = job_dir / "intro_5s_video.mp4"
    intro_audio = job_dir / "intro_5s_audio.wav"
    rest_video  = job_dir / "rest_video.mp4"
    rest_audio  = job_dir / "rest_audio.wav"

    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-t", "5", "-c", "copy", intro_video],
        check=True
    )

    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-ss", "5", "-c", "copy", rest_video],
        check=True
    )

    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-t", "5", "-vn",
         "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", intro_audio],
        check=True
    )

    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-ss", "5", "-vn",
         "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", rest_audio],
        check=True
    )

    return request_id

# ================= API =================

@router.post("/split-media-5s")
def split_media_api(req: SplitRequest):
    try:
        video_path = download_video(req.cdn_url)
        request_id = split_media(video_path)

        base = PUBLIC_BASE_URL.rstrip("/")

        return {
            "status": "ok",
            "request_id": request_id,

            # INTRO
            "intro_video_url": (
                f"{base}/ephemeral-media/{request_id}/intro_5s_video.mp4"
                f"?token={create_token()}"
            ),
            "intro_audio_url": (
                f"{base}/ephemeral-media/{request_id}/intro_5s_audio.wav"
                f"?token={create_token()}"
            ),

            # REST
            "rest_video_url": (
                f"{base}/ephemeral-media/{request_id}/rest_video.mp4"
                f"?token={create_token()}"
            ),
            "rest_audio_url": (
                f"{base}/ephemeral-media/{request_id}/rest_audio.wav"
                f"?token={create_token()}"
            ),

            "ttl_seconds": TOKEN_TTL_SECONDS
        }

    except Exception as e:
        raise HTTPException(500, str(e))

# ================= EPHEMERAL MEDIA =================

@router.get("/ephemeral-media/{request_id}/{filename}")
def serve_ephemeral_media(request_id: str, filename: str, token: str):
    if not validate_token(token):
        raise HTTPException(403, "Expired or invalid token")

    file_path = Path(f"/tmp/job_{request_id}") / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")

    if filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename
    )
