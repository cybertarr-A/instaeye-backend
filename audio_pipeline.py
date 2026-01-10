import os
import uuid
import subprocess
import requests
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------

BASE_DIR = os.getcwd()

AUDIO_DIR = os.path.join(BASE_DIR, "storage/audio")
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "storage/transcripts")
ANALYSIS_DIR = os.path.join(BASE_DIR, "storage/analysis")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

FFMPEG_BIN = "ffmpeg"

# RapidAPI Shazam endpoint
SHAZAM_RECOGNIZE_URL = "https://shazam-api6.p.rapidapi.com/shazam/recognize/"

SHAZAM_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY or "",
    "X-RapidAPI-Host": "shazam-api6.p.rapidapi.com"
}

# -----------------------------
# AUDIO EXTRACTION FROM CDN URL
# -----------------------------

def extract_audio_from_url(media_url: str, wav_path: str):
    ffmpeg_cmd = [
        FFMPEG_BIN, "-y",
        "-i", media_url,
        "-vn",
        "-ac", "1",
        "-ar", "44100",
        wav_path
    ]

    proc = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr}")

    if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 15000:
        raise RuntimeError("Audio extraction failed or file too small")


# -----------------------------
# SHAZAM SONG DETECTION
# -----------------------------

def detect_song_from_audio_file(wav_path: str) -> dict:
    if not RAPIDAPI_KEY:
        return {"status": "error", "message": "RAPIDAPI_KEY not set"}

    with open(wav_path, "rb") as f:
        files = {
            "file": ("audio.wav", f, "audio/wav")
        }

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
        return {"status": "error", "message": "Shazam returned non-JSON response"}

    track = data.get("track") or data.get("result")

    if not track or not isinstance(track, dict):
        return {"status": "no_match", "raw": data}

    return {
        "status": "matched",
        "title": track.get("title"),
        "artist": track.get("subtitle") or track.get("artist"),
        "shazam_url": track.get("url"),
    }


# -----------------------------
# OPENAI TRANSCRIPTION
# -----------------------------

def transcribe_audio(audio_path: str) -> str:
    if not client:
        return ""

    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model="gpt-4o-mini-transcribe"
        )
    return transcription.text.strip()


# -----------------------------
# OPENAI ANALYSIS
# -----------------------------

def analyze_transcript(transcript_text: str) -> str:
    if not client or not transcript_text:
        return "{}"

    prompt = f"""
Return STRICT JSON with:
- topic
- emotional_tone
- hook_strength (1-10)
- virality_score (1-10)
- call_to_action
- short_summary (max 2 lines)

Transcript:
{transcript_text}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return response.choices[0].message.content.strip()


# -----------------------------
# FULL PIPELINE
# -----------------------------

def process_reel(media_url: str) -> dict:
    uid = str(uuid.uuid4())

    wav_path = os.path.join(AUDIO_DIR, f"{uid}.wav")
    transcript_path = os.path.join(TRANSCRIPT_DIR, f"{uid}.txt")
    analysis_path = os.path.join(ANALYSIS_DIR, f"{uid}.json")

    # 1. Extract audio
    extract_audio_from_url(media_url, wav_path)

    # 2. Shazam detection
    song = detect_song_from_audio_file(wav_path)

    # 3. Transcribe
    transcript_text = transcribe_audio(wav_path)
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # 4. Analyze
    analysis = analyze_transcript(transcript_text)
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(analysis)

    return {
        "status": "success",
        "audio_id": uid,
        "song_detection": song,
        "transcript_text": transcript_text,
        "analysis": analysis
    }
