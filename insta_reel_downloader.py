import sys
import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse, urlencode

# =========================
# CONFIG
# =========================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

# Fixed for this specific API
RAPIDAPI_HOST = "instagram-reels-downloader-api.p.rapidapi.com"
RAPIDAPI_BASE_URL = f"https://{RAPIDAPI_HOST}"

if not RAPIDAPI_KEY:
    print(json.dumps({
        "status": "error",
        "message": "RAPIDAPI_KEY not set"
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
            "message": "Instagram reel/post URL required"
        }))
        sys.exit(1)

    post_url = sys.argv[1].strip()

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }

    query = urlencode({"url": post_url})
    endpoint = f"{RAPIDAPI_BASE_URL}/download?{query}"

    try:
        response = requests.get(endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": "RapidAPI request failed",
            "error": str(e)
        }))
        sys.exit(1)

    # =========================
    # EXTRACT VIDEO URL
    # =========================
    # Typical response:
    # {
    #   "status": true,
    #   "data": {
    #       "video_url": "https://..."
    #   }
    # }

    video_url = (
        data.get("video_url")
        or (data.get("data") or {}).get("video_url")
        or (data.get("data") or {}).get("url")
    )

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
