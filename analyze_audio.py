import os
import uuid
import requests
import subprocess
import tempfile
import librosa
import numpy as np
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def download_video(media_url: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    r = requests.get(media_url, stream=True, timeout=30)
    r.raise_for_status()
    for chunk in r.iter_content(8192):
        tmp.write(chunk)
    tmp.close()
    return tmp.name

def extract_audio(video_path: str) -> str:
    audio_path = video_path.replace(".mp4", ".wav")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-ac", "1",
            "-ar", "44100",
            audio_path
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )
    return audio_path

def extract_features(audio_path: str) -> dict:
    y, sr = librosa.load(audio_path, sr=44100)
    duration = librosa.get_duration(y=y, sr=sr)
    rms = float(np.mean(librosa.feature.rms(y=y)))
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

    return {
        "duration_sec": round(duration, 2),
        "energy": round(rms, 4),
        "tempo_bpm": int(tempo)
    }

def analyze_audio_with_ai(features: dict) -> dict:
    prompt = f"""
Analyze this audio and infer music context.

Audio features:
- Duration: {features['duration_sec']} seconds
- Energy: {features['energy']}
- Tempo: {features['tempo_bpm']} BPM

Return strict JSON:
{{
  "music_present": true/false,
  "mood": "...",
  "genre": "...",
  "context": "..."
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return eval(response.choices[0].message.content)
