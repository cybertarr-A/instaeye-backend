import os
import uuid
import subprocess
import base64
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
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not all([OPENAI_API_KEY, RAPIDAPI_KEY, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET]):
    raise RuntimeError("Missing required environment variables")

client = OpenAI(api_key=OPENAI_API_KEY)

FFMPEG_BIN = "ffmpeg"

# RapidAPI Shazam endpoint
SHAZAM_RECOGNIZE_URL = "https://shazam-api6.p.rapidapi.com/shazam/recognize/"

SHAZAM_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
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

    proc = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr}")


# -----------------------------
# SHAZAM SONG DETECTION (POST FILE)
# -----------------------------

def detect_song_from_audio_file(wav_path: str) -> dict:
    with open(wav_path, "rb") as f:
        files = {"file": ("audio.wav", f, "audio/wav")}

        r = requests.post(
            SHAZAM_RECOGNIZE_URL,
            headers=SHAZAM_HEADERS,
            files=files,
            timeout=60
        )

    if r.status_code != 200:
        return {"status": "error", "code": r.status_code, "message": r.text}

    data = r.json()
    track = data.get("track") or data.get("result") or data

    if not track:
        return {"status": "no_match"}

    return {
        "status": "matched",
        "title": track.get("title"),
        "artist": track.get("subtitle") or track.get("artist"),
        "shazam_url": track.get("url"),
    }


# -----------------------------
# SPOTIFY AUTH
# -----------------------------

def get_spotify_access_token() -> str:
    auth = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()

    r = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {auth}"},
        data={"grant_type": "client_credentials"},
        timeout=30
    )

    r.raise_for_status()
    return r.json()["access_token"]


# -----------------------------
# SPOTIFY SEARCH
# -----------------------------

def find_spotify_track(title: str, artist: str) -> dict:
    token = get_spotify_access_token()

    query = f"track:{title} artist:{artist}"

    r = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "type": "track", "limit": 1},
        timeout=30
    )

    if r.status_code != 200:
        return {"status": "error", "message": r.text}

    items = r.json().get("tracks", {}).get("items", [])

    if not items:
        return {"status": "not_found"}

    track = items[0]

    return {
        "status": "found",
        "spotify_url": track["external_urls"]["spotify"],
        "preview_url": track.get("preview_url"),
        "album_art": track["album"]["images"][0]["url"] if track["album"]["images"] else None
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

    wav_path = os.path.join(AUDIO_DIR, f"{uid}.wav")
    transcript_path = os.path.join(TRANSCRIPT_DIR, f"{uid}.txt")
    analysis_path = os.path.join(ANALYSIS_DIR, f"{uid}.json")

    # 1. Extract audio
    extract_audio_from_url(media_url, wav_path)

    # 2. Shazam detection
    song = detect_song_from_audio_file(wav_path)

    # 3. Spotify enrichment
    spotify = None
    if song.get("status") == "matched":
        spotify = find_spotify_track(song["title"], song["artist"])

    # 4. Transcribe
    transcript_text = transcribe_audio(wav_path)
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # 5. Analyze
    analysis = analyze_transcript(transcript_text)
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(analysis)

    return {
        "status": "success",
        "audio_id": uid,
        "song_detection": song,
        "spotify": spotify,
        "transcript_text": transcript_text,
        "analysis": analysis
    }
