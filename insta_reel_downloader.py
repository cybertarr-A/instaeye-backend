import sys
import json
import os
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from supabase import create_client, Client

# =========================
# CONFIG
# =========================

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

RAPIDAPI_HOST = "instagram-reels-downloader-api.p.rapidapi.com"
RAPIDAPI_BASE_URL = f"https://{RAPIDAPI_HOST}"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "reels")

if not RAPIDAPI_KEY:
    print(json.dumps({"status": "error", "message": "RAPIDAPI_KEY not set"}))
    sys.exit(1)

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print(json.dumps({"status": "error", "message": "Supabase credentials not set"}))
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# =========================
# HELPERS
# =========================

def normalize_instagram_url(url: str) -> str:
    parsed = urlparse(url.strip())
    clean = parsed._replace(query="", fragment="")
    return urlunparse(clean)


def extract_id_from_url(url: str) -> str:
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


def extract_video_url(data: dict):
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


def upload_to_supabase(local_path: Path, video_id: str) -> str:
    remote_path = f"{video_id}.mp4"

    with open(local_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path,
            f,
            file_options={"content-type": "video/mp4", "upsert": True}
        )

    return (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{remote_path}"
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

    try:
        response = requests.get(
            f"{RAPIDAPI_BASE_URL}/download",
            headers=headers,
            params={"url": post_url},
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
            "message": "No downloadable video found",
            "raw_response": data
        }))
        sys.exit(1)

    # =========================
    # DOWNLOAD LOCALLY
    # =========================

    output_dir = Path("data/reels")
    output_dir.mkdir(parents=True, exist_ok=True)

    video_id = extract_id_from_url(post_url)
    local_path = output_dir / f"{video_id}.mp4"

    try:
        download_file(video_url, local_path)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": "Failed to download video file",
            "error": str(e)
        }))
        sys.exit(1)

    # =========================
    # UPLOAD TO SUPABASE
    # =========================

    try:
        cdn_url = upload_to_supabase(local_path, video_id)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": "Failed to upload to Supabase",
            "error": str(e)
        }))
        sys.exit(1)

    # Optional cleanup
    try:
        local_path.unlink()
    except Exception:
        pass

    print(json.dumps({
        "status": "ok",
        "message": "Reel downloaded and uploaded to Supabase",
        "video_id": video_id,
        "cdn_url": cdn_url
    }))


if __name__ == "__main__":
    main()
