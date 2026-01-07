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

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

if not RAPIDAPI_KEY:
    raise RuntimeError("RAPIDAPI_KEY is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

FFMPEG_BIN = "ffmpeg"

# RapidAPI Shazam endpoint
SHAZAM_RECOGNIZE_URL = "https://shazam-api6.p.rapidapi.com/shazam/recognize/"

# -----------------------------
# AUDIO EXTRACTION FROM CDN URL
# -----------------------------

def extract_audio_from_url(media_url: str, wav_path: str):
    """
    Extract audio directly from CDN MP4 URL (no yt-dlp, no scraping)
    """
    ffmpeg_cmd = [
        FFMPEG_BIN, "-y",
        "-i", media_url,
        "-vn",
        "-ac", "1",
        "-ar", "44100",
        wav_path
    ]

    subprocess.run(ffmpeg_cmd, check=True)


# -----------------------------
# SHAZAM SONG DETECTION (AUDIO URL MODE)
# -----------------------------

def detect_song_from_audio_url(media_url: str) -> dict:
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "shazam-api6.p.rapidapi.com"
    }

    params = {"url": media_url}

    r = requests.get(
        SHAZAM_RECOGNIZE_URL,
        headers=headers,
        params=params,
        timeout=60
    )

    if r.status_code != 200:
        return {
            "status": "error",
            "code": r.status_code,
            "message": r.text
        }

    data = r.json()

    track = data.get("track") or data.get("result") or data

    if not track:
        return {"status": "no_match"}

    return {
        "status": "matched",
        "title": track.get("title"),
        "artist": track.get("subtitle") or track.get("artist"),
        "raw": data
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
# OPENAI ANALYSIS
# -----------------------------

def analyze_transcript(transcript_text: str) -> str:
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

    wav_path = f"{AUDIO_DIR}/{uid}.wav"
    transcript_path = f"{TRANSCRIPT_DIR}/{uid}.txt"
    analysis_path = f"{ANALYSIS_DIR}/{uid}.json"

    # 1. Extract audio from CDN
    extract_audio_from_url(media_url, wav_path)

    # 2. Detect song via Shazam URL endpoint
    song = detect_song_from_audio_url(media_url)

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
