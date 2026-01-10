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

SHAZAM_RECOGNIZE_URL = "https://shazam-api6.p.rapidapi.com/shazam/recognize/"
SHAZAM_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "shazam-api6.p.rapidapi.com"
}

# -----------------------------
# AUDIO EXTRACTION (MP3)
# -----------------------------

def extract_audio_mp3_from_url(media_url: str, mp3_path: str):
    ffmpeg_cmd = [
        FFMPEG_BIN, "-y",
        "-i", media_url,
        "-vn",
        "-ac", "1",
        "-ar", "44100",
        "-codec:a", "libmp3lame",
        mp3_path
    ]

    proc = subprocess.run(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{proc.stderr}")

    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 15000:
        raise RuntimeError("Audio extraction failed or file too small")


# -----------------------------
# TEMP FILE UPLOAD (PUBLIC URL)
# -----------------------------

def upload_temp_audio(mp3_path: str) -> str:
    with open(mp3_path, "rb") as f:
        r = requests.post("https://file.io", files={"file": f}, timeout=60)

    if r.status_code != 200 or not r.json().get("success"):
        raise RuntimeError("Temp upload failed")

    return r.json()["link"]


# -----------------------------
# SHAZAM SONG DETECTION (URL MODE)
# -----------------------------

def detect_song_from_audio_url(audio_url: str) -> dict:
    params = {"url": audio_url}

    r = requests.get(
        SHAZAM_RECOGNIZE_URL,
        headers=SHAZAM_HEADERS,
        params=params,
        timeout=60
    )

    if r.status_code != 200:
        return {"status": "error", "code": r.status_code, "message": r.text}

    data = r.json()
    track = data.get("track") or data.get("result") or data

    if not isinstance(track, dict):
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

    mp3_path = os.path.join(AUDIO_DIR, f"{uid}.mp3")
    transcript_path = os.path.join(TRANSCRIPT_DIR, f"{uid}.txt")
    analysis_path = os.path.join(ANALYSIS_DIR, f"{uid}.json")

    # 1. Extract audio
    extract_audio_mp3_from_url(media_url, mp3_path)

    # 2. Upload to temp public URL
    audio_url = upload_temp_audio(mp3_path)

    # 3. Shazam detection
    song = detect_song_from_audio_url(audio_url)

    # 4. Spotify enrichment
    spotify = None
    if song.get("status") == "matched":
        spotify = find_spotify_track(song["title"], song["artist"])

    # 5. Transcribe
    transcript_text = transcribe_audio(mp3_path)
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    # 6. Analyze
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
