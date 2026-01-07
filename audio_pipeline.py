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
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

FFMPEG_BIN = "ffmpeg"
YTDLP_BIN = "yt-dlp"

# 🔴 CHANGE THIS TO YOUR REAL HOST
SHAZAM_API_BASE = "https://YOUR_HOST"

# -----------------------------
# URL NORMALIZATION
# -----------------------------

def normalize_instagram_url(url: str) -> str:
    if "cdninstagram.com" in url:
        raise ValueError("Use canonical Instagram reel/post URL, not CDN")

    if "instagram.com" not in url:
        raise ValueError("Invalid Instagram URL")

    return url.split("?")[0]


# -----------------------------
# AUDIO EXTRACTION
# -----------------------------

def extract_audio(media_url: str, wav_path: str):
    tmp_mp4 = wav_path.replace(".wav", ".mp4")

    # Download reel
    ytdlp_cmd = [
        YTDLP_BIN,
        "--no-playlist",
        "--force-ipv4",
        "-f", "best",
        "-o", tmp_mp4,
        media_url
    ]

    subprocess.run(ytdlp_cmd, check=True)

    # Extract WAV (Shazam-friendly)
    ffmpeg_cmd = [
        FFMPEG_BIN, "-y",
        "-i", tmp_mp4,
        "-vn",
        "-ac", "1",
        "-ar", "44100",
        wav_path
    ]

    subprocess.run(ffmpeg_cmd, check=True)

    os.remove(tmp_mp4)


# -----------------------------
# SHAZAM SONG DETECTION (FILE UPLOAD)
# -----------------------------

def detect_song_from_audio(wav_path: str) -> dict:
    url = f"{SHAZAM_API_BASE}/shazam/recognize/"

    with open(wav_path, "rb") as f:
        files = {
            "file": ("audio.wav", f, "audio/wav")
        }

        response = requests.post(url, files=files, timeout=60)

    if response.status_code != 200:
        return {
            "status": "error",
            "code": response.status_code,
            "message": response.text
        }

    data = response.json()

    # Normalize common Shazam-style responses
    track = (
        data.get("track")
        or data.get("result")
        or data
    )

    if not track:
        return {"status": "no_match"}

    return {
        "status": "matched",
        "title": track.get("title") or track.get("track_name"),
        "artist": track.get("artist") or track.get("subtitle"),
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
    media_url = normalize_instagram_url(media_url)

    wav_path = f"{AUDIO_DIR}/{uid}.wav"
    transcript_path = f"{TRANSCRIPT_DIR}/{uid}.txt"
    analysis_path = f"{ANALYSIS_DIR}/{uid}.json"

    # 1. Extract audio
    extract_audio(media_url, wav_path)

    # 2. Detect song
    song = detect_song_from_audio(wav_path)

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
