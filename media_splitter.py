import os, uuid, subprocess, requests

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ================= CONFIG =================

BASE = os.path.join(os.getcwd(), "storage")
VID = os.path.join(BASE, "videos")
OUT = os.path.join(BASE, "split")

for d in [VID, OUT]:
    os.makedirs(d, exist_ok=True)

FFMPEG = "ffmpeg"

router = APIRouter()

# ================= MODEL =================

class SplitRequest(BaseModel):
    cdn_url: str

# ================= UTILS =================

def download_video(url):
    path = os.path.join(VID, f"{uuid.uuid4()}.mp4")

    r = requests.get(url, stream=True, timeout=30)
    if r.status_code != 200:
        raise Exception("Video download failed")

    with open(path, "wb") as f:
        for c in r.iter_content(1024 * 1024):
            if c:
                f.write(c)

    return path


def split_media(video_path):

    uid = str(uuid.uuid4())

    intro_video = os.path.join(OUT, f"{uid}_intro_5s.mp4")
    rest_video  = os.path.join(OUT, f"{uid}_rest.mp4")

    intro_audio = os.path.join(OUT, f"{uid}_intro_5s.wav")
    rest_audio  = os.path.join(OUT, f"{uid}_rest.wav")

    # ---- first 5 sec video ----
    subprocess.run([
        FFMPEG, "-y",
        "-i", video_path,
        "-t", "5",
        "-c", "copy",
        intro_video
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # ---- remaining video ----
    subprocess.run([
        FFMPEG, "-y",
        "-i", video_path,
        "-ss", "5",
        "-c", "copy",
        rest_video
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # ---- first 5 sec audio ----
    subprocess.run([
        FFMPEG, "-y",
        "-i", video_path,
        "-t", "5",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        intro_audio
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # ---- remaining audio ----
    subprocess.run([
        FFMPEG, "-y",
        "-i", video_path,
        "-ss", "5",
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        rest_audio
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    return {
        "intro_video_5s": intro_video,
        "intro_audio_5s": intro_audio,
        "rest_video": rest_video,
        "rest_audio": rest_audio
    }

# ================= API =================

@router.post("/split-media-5s")
def split_media_api(req: SplitRequest):

    try:
        video = download_video(req.cdn_url)
        outputs = split_media(video)

        return {
            "status": "ok",
            **outputs
        }

    except Exception as e:
        raise HTTPException(500, str(e))
