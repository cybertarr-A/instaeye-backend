import os
import uuid
import requests
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

if not RAPIDAPI_KEY:
    raise RuntimeError("RAPIDAPI_KEY not set")

client = OpenAI(api_key=OPENAI_API_KEY)

SHAZAM_RECOGNIZE_URL = "https://shazam-api6.p.rapidapi.com/shazam/recognize/"
SHAZAM_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "shazam-api6.p.rapidapi.com"
}

TMP_DIR = "/tmp"
os.makedirs(TMP_DIR, exist_ok=True)

# -----------------------------
# DOWNLOAD AUDIO FROM CDN
# -----------------------------

def download_audio(audio_url: str) -> str:
    audio_id = str(uuid.uuid4())
    audio_path = f"{TMP_DIR}/{audio_id}.audio"

    r = requests.get(audio_url, stream=True, timeout=60)
    r.raise_for_status()

    with open(audio_path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)

    if os.path.getsize(audio_path) < 15000:
        raise RuntimeError("Downloaded audio file too small")

    return audio_path

# -----------------------------
# SHAZAM SONG DETECTION (FILE MODE)
# -----------------------------

def detect_song_from_audio_file(audio_path: str) -> dict:
    with open(audio_path, "rb") as f:
        files = {"file": f}

        r = requests.post(
            SHAZAM_RECOGNIZE_URL,
            headers=SHAZAM_HEADERS,
            files=files,
            timeout=60
        )

    if r.status_code != 200:
        return {
            "status": "error",
            "code": r.status_code,
            "message": r.text
        }

    try:
        data = r.json()
    except Exception:
        return {"status": "error", "message": "Invalid Shazam response"}

    track = data.get("track") or data.get("result")

    if not track:
        return {"status": "no_match"}

    return {
        "status": "matched",
        "title": track.get("title"),
        "artist": track.get("subtitle") or track.get("artist"),
        "shazam_url": track.get("url")
    }

# -----------------------------
# OPENAI TRANSCRIPTION
# -----------------------------

def transcribe_audio(audio_path: str) -> str:
    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model="gpt-4o-mini-transcribe"
        )

    return transcription.text.strip()

# -----------------------------
# MAIN PIPELINE
# -----------------------------

def process_reel(audio_cdn_url: str) -> dict:
    audio_path = None

    try:
        # 1. Download audio
        audio_path = download_audio(audio_cdn_url)

        # 2. Detect song
        song = detect_song_from_audio_file(audio_path)

        # 3. Transcribe speech
        transcript = transcribe_audio(audio_path)

        return {
            "status": "success",
            "audio_url": audio_cdn_url,
            "song_detection": song,
            "transcript_text": transcript
        }

    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
