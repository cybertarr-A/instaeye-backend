import os
import uuid
import subprocess
import requests
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

# ================= CONFIG =================

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
TMP_DIR = Path("/tmp")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "temp-media")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

router = APIRouter()

# ================= MODELS =================

class SplitRequest(BaseModel):
    cdn_url: str
    user_id: str | None = None

# ================= UTILS =================

def download_video(url: str) -> Path:
    tmp_video = TMP_DIR / f"src_{uuid.uuid4()}.mp4"

    r = requests.get(url, stream=True, timeout=60)
    if r.status_code != 200:
        raise Exception(f"Video download failed: {r.status_code}")

    with open(tmp_video, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)

    return tmp_video


def has_audio(video_path: Path) -> bool:
    result = subprocess.run(
        [
            FFPROBE,
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=index",
            "-of", "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def run_ffmpeg(cmd: list):
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def upload_and_get_public_url(local_path: Path, remote_path: str) -> str:
    content_type = "audio/wav" if remote_path.endswith(".wav") else "video/mp4"

    with open(local_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path,
            f,
            {
                "content-type": content_type,
                "upsert": True,
            },
        )

    return (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{remote_path}"
    )

# ================= SPLITTER =================

def split_media(video_path: Path, request_id: str) -> dict:
    job_dir = TMP_DIR / f"job_{request_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    intro_video = job_dir / "intro_5s_video.mp4"
    rest_video  = job_dir / "rest_video.mp4"
    intro_audio = job_dir / "intro_5s_audio.wav"
    rest_audio  = job_dir / "rest_audio.wav"

    # -------- VIDEO --------

    run_ffmpeg([
        FFMPEG, "-y",
        "-i", str(video_path),
        "-t", "5",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-an",
        str(intro_video)
    ])

    run_ffmpeg([
        FFMPEG, "-y",
        "-i", str(video_path),
        "-ss", "5",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-an",
        str(rest_video)
    ])

    audio_exists = has_audio(video_path)

    audio_urls = {}

    # -------- AUDIO (SAFE) --------

    if audio_exists:
        run_ffmpeg([
            FFMPEG, "-y",
            "-i", str(video_path),
            "-map", "0:a:0?",
            "-t", "5",
            "-ac", "1",
            "-ar", "16000",
            str(intro_audio)
        ])

        run_ffmpeg([
            FFMPEG, "-y",
            "-i", str(video_path),
            "-map", "0:a:0?",
            "-ss", "5",
            "-ac", "1",
            "-ar", "16000",
            str(rest_audio)
        ])

        audio_urls = {
            "intro_audio_url": upload_and_get_public_url(
                intro_audio, f"{request_id}/intro_5s_audio.wav"
            ),
            "rest_audio_url": upload_and_get_public_url(
                rest_audio, f"{request_id}/rest_audio.wav"
            ),
        }

    # -------- UPLOAD VIDEO --------

    result = {
        "intro_video_url": upload_and_get_public_url(
            intro_video, f"{request_id}/intro_5s_video.mp4"
        ),
        "rest_video_url": upload_and_get_public_url(
            rest_video, f"{request_id}/rest_video.mp4"
        ),
        **audio_urls,
    }

    # -------- CLEANUP --------
    try:
        video_path.unlink(missing_ok=True)
    except Exception:
        pass

    return result

# ================= API =================

@router.post("/split-media-5s")
def split_media_api(req: SplitRequest):
    try:
        request_id = str(uuid.uuid4())

        video_path = download_video(req.cdn_url)
        urls = split_media(video_path, request_id)

        return {
            "status": "ok",
            "request_id": request_id,
            **urls,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
