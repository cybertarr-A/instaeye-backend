import sys
import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse

# =========================
# CONFIG
# =========================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST")  # e.g. instagram-downloader-api.p.rapidapi.com
RAPIDAPI_ENDPOINT = os.getenv("RAPIDAPI_ENDPOINT")  
# e.g. https://instagram-downloader-api.p.rapidapi.com/index

if not RAPIDAPI_KEY or not RAPIDAPI_HOST or not RAPIDAPI_ENDPOINT:
    print(json.dumps({
        "status": "error",
        "message": "RapidAPI configuration missing (KEY / HOST / ENDPOINT)"
    }))
    sys.exit(1)


# =========================
# HELPERS
# =========================

def extract_id_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1]


def download_file(url: str, output_path: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


# =========================
# MAIN
# =========================

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "status": "error",
            "message": "Instagram post URL required"
        }))
        sys.exit(1)

    post_url = sys.argv[1].strip()

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }

    params = {
        "url": post_url
    }

    try:
        response = requests.get(
            RAPIDAPI_ENDPOINT,
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": "RapidAPI request failed",
            "error": str(e)
        }))
        sys.exit(1)

    # 🔍 Try to extract video URL (generic logic)
    media_items = data.get("media") or data.get("data") or []

    video_url = None
    for item in media_items:
        if item.get("type") == "video" or item.get("extension") == "mp4":
            video_url = item.get("url")
            break

    if not video_url:
        print(json.dumps({
            "status": "error",
            "message": "No downloadable video found",
            "raw_response": data
        }))
        sys.exit(1)

    # =========================
    # SAVE FILE
    # =========================

    output_dir = Path("data/reels")
    output_dir.mkdir(parents=True, exist_ok=True)

    video_id = extract_id_from_url(post_url)
    output_path = output_dir / f"{video_id}.mp4"

    try:
        download_file(video_url, output_path)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": "Failed to download video file",
            "error": str(e)
        }))
        sys.exit(1)

    print(json.dumps({
        "status": "ok",
        "message": "Reel downloaded successfully via RapidAPI",
        "file": str(output_path)
    }))


if __name__ == "__main__":
    main()
