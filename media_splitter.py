import os
import uuid
import subprocess
import requests
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ================= CONFIG =================

FFMPEG = "ffmpeg"
router = APIRouter()

# ================= MODEL =================

class SplitRequest(BaseModel):
    cdn_url: str
    user_id: str

# ================= CORE =================

@router.post("/split-media-5s")
def split_media_api(req: SplitRequest):

    request_id = str(uuid.uuid4())
    workdir = Path(f"/tmp/job_{request_id}")

    try:
        # create isolated temp workspace
        workdir.mkdir(parents=True, exist_ok=True)

        input_video = workdir / "input.mp4"

        # ---------- STREAM DOWNLOAD ----------
        r = requests.get(req.cdn_url, stream=True, timeout=30)
        if r.status_code != 200:
            raise Exception("Video download failed")

        with open(input_video, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

        # ---------- SPLIT VIDEO ----------
        subprocess.run(
            [FFMPEG, "-y", "-i", str(input_video), "-t", "5",
             str(workdir / "intro_5s_video.mp4")],
            check=True
        )

        subprocess.run(
            [FFMPEG, "-y", "-i", str(input_video), "-ss", "5",
             str(workdir / "rest_video.mp4")],
            check=True
        )

        # ---------- SPLIT AUDIO ----------
        subprocess.run(
            [FFMPEG, "-y", "-i", str(input_video), "-t", "5", "-vn",
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             str(workdir / "intro_5s_audio.wav")],
            check=True
        )

        subprocess.run(
            [FFMPEG, "-y", "-i", str(input_video), "-ss", "5", "-vn",
             "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
             str(workdir / "rest_audio.wav")],
            check=True
        )

        # ---------- RETURN INTERNAL PATHS ONLY ----------
        return {
            "status": "ok",
            "request_id": request_id,
            "paths": {
                "intro_video": str(workdir / "intro_5s_video.mp4"),
                "intro_audio": str(workdir / "intro_5s_audio.wav"),
                "rest_video":  str(workdir / "rest_video.mp4"),
                "rest_audio":  str(workdir / "rest_audio.wav"),
            }
        }

    except Exception as e:
        # hard cleanup on failure
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, str(e))
