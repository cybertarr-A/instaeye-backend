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

# -----------------------------
# AUDIO EXTRACTION
# -----------------------------

def extract_audio(media_url: str, audio_path: str):
    """
    Extract audio from Instagram reel / video CDN URL
    """
    cmd = [
        "yt-dlp",
        "-f", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", audio_path,
        media_url
    ]

    subprocess.run(cmd, check=True)

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

    return transcription.text

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

    return response.choices[0].message.content

# -----------------------------
# FULL PIPELINE
# -----------------------------

def process_reel(media_url: str) -> dict:
    """
    Full pipeline:
    video URL → audio → transcript → analysis
    """
    uid = str(uuid.uuid4())

    audio_path = f"{AUDIO_DIR}/{uid}.mp3"
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
        "transcript_text": transcript_text,
        "analysis": analysis
    }
