import sys
import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse, urlencode, urlunparse

# =========================
# CONFIG
# =========================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

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

def normalize_instagram_url(url: str) -> str:
    """
    Remove tracking params like ?igsh=...
    """
    parsed = urlparse(url.strip())
    clean = parsed._replace(query="", fragment="")
    return urlunparse(clean)


def extract_id_from_url(url: str) -> str:
    """
    Supports /p/, /reel/, /tv/
    """
    parts = urlparse(url).path.strip("/").split("/")
    for i, part in enumerate(parts):
        if part in ("p", "reel", "tv") and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]


def download_file(url: str, output_path: Path):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def extract_video_url(data: dict) -> str | None:
    """
    Handle multiple RapidAPI response shapes
    """
    return (
        data.get("video_url")
        or data.get("url")
        or (data.get("data") or {}).get("video_url")
        or (data.get("data") or {}).get("url")
        or (
            isinstance(data.get("data"), list)
            and data["data"]
            and data["data"][0].get("url")
        )
    )


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

    raw_url = sys.argv[1]
    post_url = normalize_instagram_url(raw_url)

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST
    }

    endpoint = f"{RAPIDAPI_BASE_URL}/download"
    params = {"url": post_url}

    try:
        response = requests.get(
            endpoint,
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

    video_url = extract_video_url(data)

    if not video_url:
        print(json.dumps({
            "status": "error",
            "message": "No downloadable video found in API response",
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
