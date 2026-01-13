import os, uuid, subprocess, requests

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ================= CONFIG =================

BASE = os.path.join(os.getcwd(), "storage")
VID = os.path.join(BASE, "videos")
OUT = os.path.join(BASE, "split")

for d in [VID, OUT]:
    os.makedirs(d, exist_ok=True)

FFMPEG = "ffmpeg"

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")  # set in Railway

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

    intro_video = f"{uid}_intro_5s_video.mp4"
    rest_video  = f"{uid}_rest_video.mp4"

    intro_audio = f"{uid}_intro_5s_audio.wav"
    rest_audio  = f"{uid}_rest_audio.wav"

    intro_video_p = os.path.join(OUT, intro_video)
    rest_video_p  = os.path.join(OUT, rest_video)
    intro_audio_p = os.path.join(OUT, intro_audio)
    rest_audio_p  = os.path.join(OUT, rest_audio)

    # first 5 sec video
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-t", "5", "-c", "copy", intro_video_p],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )

    # remaining video
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-ss", "5", "-c", "copy", rest_video_p],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )

    # first 5 sec audio
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-t", "5", "-vn",
         "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", intro_audio_p],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )

    # remaining audio
    subprocess.run(
        [FFMPEG, "-y", "-i", video_path, "-ss", "5", "-vn",
         "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", rest_audio_p],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )

    return {
        "intro_video": intro_video,
        "intro_audio": intro_audio,
        "rest_video": rest_video,
        "rest_audio": rest_audio
    }

# ================= API =================

@router.post("/split-media-5s")
def split_media_api(req: SplitRequest):

    try:
        video = download_video(req.cdn_url)
        files = split_media(video)

        if not PUBLIC_BASE_URL:
            raise Exception("PUBLIC_BASE_URL env var not set")

        return {
            "status": "ok",
            "intro_video_url": f"{PUBLIC_BASE_URL}/files/{files['intro_video']}",
            "intro_audio_url": f"{PUBLIC_BASE_URL}/files/{files['intro_audio']}",
            "rest_video_url":  f"{PUBLIC_BASE_URL}/files/{files['rest_video']}",
            "rest_audio_url":  f"{PUBLIC_BASE_URL}/files/{files['rest_audio']}",
        }

    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/files/{filename}")
def get_file(filename: str):
    path = os.path.join(OUT, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "File not found")
    return FileResponse(path)
