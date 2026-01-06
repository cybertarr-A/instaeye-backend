import os
import uuid
import subprocess
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------

AUDIO_DIR = "storage/audio"
TRANSCRIPT_DIR = "storage/transcripts"
ANALYSIS_DIR = "storage/analysis"

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

FFMPEG_BIN = "ffmpeg"
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
    Reliable Instagram audio extraction:
    1) Download MP4 via yt-dlp (no postprocessing)
    2) Extract audio using ffmpeg directly
    """

    tmp_mp4 = audio_path.replace(".wav", ".mp4")

    # Step 1: Download video only
    ytdlp_cmd = [
        YTDLP_BIN,
        "--no-playlist",
        "--force-ipv4",
        "-f", "best",
        "-o", tmp_mp4,
        media_url
    ]

    ytdlp = subprocess.run(
        ytdlp_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if ytdlp.returncode != 0:
        raise RuntimeError(
            "yt-dlp download failed\n"
            f"STDERR:\n{ytdlp.stderr}"
        )

    # Step 2: Extract audio safely with ffmpeg
    ffmpeg_cmd = [
        FFMPEG_BIN,
        "-y",
        "-i", tmp_mp4,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        audio_path
    ]

    ffmpeg = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if ffmpeg.returncode != 0:
        raise RuntimeError(
            "ffmpeg audio extraction failed\n"
            f"STDERR:\n{ffmpeg.stderr}"
        )

    os.remove(tmp_mp4)


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
    Instagram reel/post URL → audio → transcript → analysis
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
