import os, uuid, subprocess, shutil, requests
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
FFMPEG = "ffmpeg"

# ================= MODEL =================

class SplitRequest(BaseModel):
    cdn_url: str
    user_id: str

# ================= CORE =================

@router.post("/split-media-5s")
def split_media_5s(req: SplitRequest):
    request_id = str(uuid.uuid4())
    workdir = Path(f"/tmp/job_{request_id}")

    try:
        workdir.mkdir(parents=True, exist_ok=True)
        input_video = workdir / "input.mp4"

        # Stream download
        r = requests.get(req.cdn_url, stream=True, timeout=30)
        if r.status_code != 200:
            raise Exception("Video download failed")

        with open(input_video, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)

        # Split video
        subprocess.run([
            FFMPEG, "-y", "-i", str(input_video),
            "-t", "5", str(workdir / "hook_video.mp4")
        ], check=True)

        subprocess.run([
            FFMPEG, "-y", "-i", str(input_video),
            "-ss", "5", str(workdir / "rest_video.mp4")
        ], check=True)

        # Split audio
        subprocess.run([
            FFMPEG, "-y", "-i", str(input_video),
            "-t", "5", "-vn",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(workdir / "hook_audio.wav")
        ], check=True)

        subprocess.run([
            FFMPEG, "-y", "-i", str(input_video),
            "-ss", "5", "-vn",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(workdir / "rest_audio.wav")
        ], check=True)

        return {
            "request_id": request_id,
            "paths": {
                "hook_video": str(workdir / "hook_video.mp4"),
                "hook_audio": str(workdir / "hook_audio.wav"),
                "rest_video": str(workdir / "rest_video.mp4"),
                "rest_audio": str(workdir / "rest_audio.wav"),
            }
        }

    except Exception as e:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(500, str(e))
