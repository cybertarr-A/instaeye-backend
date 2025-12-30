from fastapi import FastAPI, HTTPException
import subprocess
import tempfile
import requests
import os
import uuid

app = FastAPI()

def run(cmd):
    subprocess.run(cmd, shell=True, check=True)

@app.post("/analyze-audio")
def analyze_audio(payload: dict):
    media_url = payload.get("media_url")
    if not media_url:
        raise HTTPException(status_code=400, detail="media_url required")

    uid = uuid.uuid4().hex
    tmp_dir = tempfile.gettempdir()

    video_path = f"{tmp_dir}/{uid}.mp4"
    audio_path = f"{tmp_dir}/{uid}.wav"

    # Download video
    with requests.get(media_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(video_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

    # Extract audio
    run(f"ffmpeg -y -i {video_path} -ac 1 -ar 16000 {audio_path}")

    # Analyze loudness
    result = subprocess.run(
        f"ffmpeg -i {audio_path} -af astats -f null -",
        shell=True,
        stderr=subprocess.PIPE,
        text=True
    )

    stderr = result.stderr

    is_music = "Zero crossings" not in stderr
    rms = None

    for line in stderr.splitlines():
        if "Overall RMS level" in line:
            rms = float(line.split(":")[-1].strip())

    os.remove(video_path)
    os.remove(audio_path)

    return {
        "audio_type": "music-dominant" if is_music else "speech-dominant",
        "rms_db": rms,
        "hook_potential": "high" if rms and rms > -18 else "medium",
        "recommended_use": "viral/trend" if is_music else "educational/story"
    }
