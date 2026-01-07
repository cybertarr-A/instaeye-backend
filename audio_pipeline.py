import os
import uuid
import subprocess
import base64
import requests
from openai import OpenAI

# -----------------------------
# CONFIG
# -----------------------------

AUDIO_DIR = "storage/audio"
RAW_DIR = "storage/raw"
TRANSCRIPT_DIR = "storage/transcripts"
ANALYSIS_DIR = "storage/analysis"

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)
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
YTDLP_BIN = "yt-dlp"

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

def extract_audio(media_url: str, wav_path: str, raw_path: str):
    """
    1) Download MP4
    2) Extract WAV for transcription
    3) Extract RAW PCM for Shazam
    """

    tmp_mp4 = wav_path.replace(".wav", ".mp4")

    # Download video
    ytdlp_cmd = [
        YTDLP_BIN,
        "--no-playlist",
        "--force-ipv4",
        "-f", "best",
        "-o", tmp_mp4,
        media_url
    ]

    ytdlp = subprocess.run(ytdlp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if ytdlp.returncode != 0:
        raise RuntimeError("yt-dlp failed:\n" + ytdlp.stderr)

    # WAV for transcription (16k)
    ffmpeg_wav = [
        FFMPEG_BIN, "-y", "-i", tmp_mp4,
        "-vn", "-ac", "1", "-ar", "16000",
        wav_path
    ]

    if subprocess.run(ffmpeg_wav).returncode != 0:
        raise RuntimeError("ffmpeg wav extraction failed")

    # RAW PCM for Shazam (44.1k s16le)
    ffmpeg_raw = [
        FFMPEG_BIN, "-y", "-i", tmp_mp4,
        "-vn", "-ac", "1", "-ar", "44100",
        "-f", "s16le", "-t", "5",
        raw_path
    ]

    if subprocess.run(ffmpeg_raw).returncode != 0:
        raise RuntimeError("ffmpeg raw extraction failed")

    os.remove(tmp_mp4)


# -----------------------------
# SHAZAM SONG DETECTION
# -----------------------------

def detect_song(raw_audio_path: str) -> dict:
    with open(raw_audio_path, "rb") as f:
        b64_audio = base64.b64encode(f.read()).decode()

    url = "https://shazam.p.rapidapi.com/songs/v2/detect"

    headers = {
        "content-type": "text/plain",
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "shazam.p.rapidapi.com"
    }

    resp = requests.post(url, headers=headers, data=b64_audio, timeout=60)

    if resp.status_code != 200:
        return {"status": "error", "reason": resp.text}

    data = resp.json()
    track = data.get("track")

    if not track:
        return {"status": "no_match"}

    return {
        "status": "matched",
        "title": track.get("title"),
        "artist": track.get("subtitle"),
        "album": track.get("sections", [{}])[0].get("metadata", [{}])[0].get("text")
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
    raw_path = f"{RAW_DIR}/{uid}.raw"
    transcript_path = f"{TRANSCRIPT_DIR}/{uid}.txt"
    analysis_path = f"{ANALYSIS_DIR}/{uid}.json"

    # 1. Extract audio
    extract_audio(media_url, wav_path, raw_path)

    # 2. Detect song
    song = detect_song(raw_path)

    # 3. Transcribe speech
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
