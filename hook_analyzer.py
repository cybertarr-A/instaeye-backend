import os, uuid, subprocess, requests, base64
import cv2
import numpy as np

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

# ================= CONFIG =================

BASE = os.path.join(os.getcwd(), "storage")
VID = os.path.join(BASE, "videos")
CLIP = os.path.join(BASE, "clips")
AUD = os.path.join(BASE, "audio")
FRM = os.path.join(BASE, "frames")

for d in [VID, CLIP, AUD, FRM]:
    os.makedirs(d, exist_ok=True)

FFMPEG = "ffmpeg"

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
RAPID_KEY = os.getenv("RAPIDAPI_KEY")

client = OpenAI(api_key=OPENAI_KEY)

SHAZAM_URL = "https://shazam-api6.p.rapidapi.com/shazam/recognize/"
SHAZAM_HEADERS = {
    "x-rapidapi-key": RAPID_KEY,
    "x-rapidapi-host": "shazam-api6.p.rapidapi.com"
}

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

router = APIRouter()

# ================= MODELS =================

class HookRequest(BaseModel):
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


def extract_5s_video(video):
    out = os.path.join(CLIP, f"clip_{uuid.uuid4()}.mp4")
    subprocess.run(
        [FFMPEG, "-y", "-i", video, "-t", "5", "-c:v", "copy", "-c:a", "copy", out],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
    return out


def extract_5s_audio(video):
    out = os.path.join(AUD, f"audio_{uuid.uuid4()}.wav")
    subprocess.run(
        [FFMPEG, "-y", "-i", video, "-t", "5",
         "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", out],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
    )
    return out


def extract_frames(video):
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    frames = []
    for sec in [0, 1, 2, 3, 4]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * sec))
        ok, frame = cap.read()
        if ok:
            p = os.path.join(FRM, f"{uuid.uuid4()}.jpg")
            cv2.imwrite(p, frame)
            frames.append(p)
    cap.release()
    return frames


def video_metrics(video):
    cap = cv2.VideoCapture(video)
    ret, prev = cap.read()
    if not ret:
        return {}

    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)

    motion = []
    brightness = []
    contrast = []
    face_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        diff = cv2.absdiff(prev_gray, gray)
        motion.append(np.mean(diff))

        brightness.append(np.mean(gray))
        contrast.append(np.std(gray))

        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        face_count += len(faces)

        prev_gray = gray

    cap.release()

    return {
        "motion_intensity": round(float(np.mean(motion)), 2),
        "avg_brightness": round(float(np.mean(brightness)), 2),
        "avg_contrast": round(float(np.mean(contrast)), 2),
        "face_detections": int(face_count)
    }


def transcribe_audio(audio):
    with open(audio, "rb") as f:
        tr = client.audio.transcriptions.create(
            file=f,
            model="gpt-4o-transcribe"
        )
    return tr.text.strip()


def shazam_detect(audio):
    with open(audio, "rb") as f:
        r = requests.post(SHAZAM_URL, headers=SHAZAM_HEADERS, files={"file": f})

    if r.status_code != 200:
        return None

    data = r.json()
    track = data.get("track")
    if not track:
        return None

    return {
        "title": track.get("title"),
        "artist": track.get("subtitle"),
        "genre": track.get("genres", {}).get("primary")
    }


def ai_hook_analysis(transcript, frames, metrics):
    imgs = []
    for f in frames:
        with open(f, "rb") as img:
            imgs.append({
                "type": "input_image",
                "image_base64": base64.b64encode(img.read()).decode()
            })

    prompt = f"""
You are analyzing first 5 seconds of a social media reel.

Transcript: {transcript}

Video metrics:
{metrics}

Score hook strength 0-100 and explain:
- emotional impact
- curiosity
- visual punch
- clarity

Return JSON only.
"""

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=[{
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}] + imgs
        }]
    )

    return res.output_text


# ================= API =================

@router.post("/analyze-hook")
def analyze_hook(req: HookRequest):

    try:
        video = download_video(req.cdn_url)
        clip = extract_5s_video(video)
        audio = extract_5s_audio(video)

        frames = extract_frames(clip)
        metrics = video_metrics(clip)

        transcript = transcribe_audio(audio)

        music = None
        if len(transcript) < 5:
            music = shazam_detect(audio)

        ai_analysis = ai_hook_analysis(transcript, frames, metrics)

        return {
            "status": "ok",
            "video_metrics": metrics,
            "transcript": transcript,
            "music_detected": music,
            "ai_hook_analysis": ai_analysis
        }

    except Exception as e:
        raise HTTPException(500, str(e))
