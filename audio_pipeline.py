import os
import uuid
import subprocess
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------

BASE_DIR = "storage"
AUDIO_DIR = f"{BASE_DIR}/audio"
TRANSCRIPT_DIR = f"{BASE_DIR}/transcripts"
ANALYSIS_DIR = f"{BASE_DIR}/analysis"

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

FFMPEG_PATH = "/usr/bin/ffmpeg"  # Docker / Railway
YTDLP_BIN = "yt-dlp"

# -----------------------------
# URL NORMALIZATION (CRITICAL)
# -----------------------------

def normalize_instagram_url(url: str) -> str:
    """
    Instagram CDN URLs are time-limited and WILL FAIL on servers.
    Force canonical reel/post URLs.
    """
    if "cdninstagram.com" in url:
        raise ValueError(
            "CDN URLs are not supported. "
            "Use a canonical Instagram URL like "
            "https://www.instagram.com/reel/XXXX/"
        )

    if "instagram.com" not in url:
        raise ValueError("Invalid Instagram URL")

    return url.split("?")[0]


# -----------------------------
# AUDIO EXTRACTION (FIXED)
# -----------------------------

def extract_audio(media_url: str, audio_path: str):
    """
    Extract audio as WAV using ffmpeg via yt-dlp.
    This avoids DASH fragment + codec detection issues.
    """

    # yt-dlp expects output TEMPLATE, not final filename
    output_template = audio_path.replace(".wav", ".%(ext)s")

    cmd = [
        YTDLP_BIN,
        "--no-playlist",
        "--force-ipv4",
        "--prefer-ffmpeg",
        "--ffmpeg-location", FFMPEG_PATH,
        "-f", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "-o", output_template,
        media_url
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "yt-dlp failed\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    if not os.path.exists(audio_path):
        raise RuntimeError("Audio extraction succeeded but WAV file not found")


# -----------------------------
# OPENAI TRANSCRIPTION
# -----------------------------

def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio using OpenAI Speech-to-Text
    """
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
    """
    Analyze transcript for reel intelligence
    """
    prompt = f"""
You are analyzing spoken content from an Instagram Reel.

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
    """
    Full pipeline:
    Instagram URL → WAV audio → transcript → analysis
    """
    uid = str(uuid.uuid4())

    media_url = normalize_instagram_url(media_url)

    audio_path = f"{AUDIO_DIR}/{uid}.wav"
    transcript_path = f"{TRANSCRIPT_DIR}/{uid}.txt"
    analysis_path = f"{ANALYSIS_DIR}/{uid}.json"

    # 1. Extract audio
    extract_audio(media_url, audio_path)

    # 2. Transcribe
    transcript_text = transcribe_audio(audio_path)
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # 3. Analyze
    analysis = analyze_transcript(transcript_text)
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(analysis)

    return {
        "status": "success",
        "audio_id": uid,
        "audio_format": "wav",
        "transcript_text": transcript_text,
        "analysis": analysis
    }
