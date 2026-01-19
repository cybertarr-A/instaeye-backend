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
    print("RAPIDAPI_KEY not set", file=sys.stderr)
    sys.exit(1)

# =========================
# HELPERS
# =========================

def normalize_instagram_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return urlunparse(parsed._replace(query="", fragment=""))


def extract_id_from_url(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    for i, p in enumerate(parts):
        if p in ("p", "reel", "tv") and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1]


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


def fetch_reel_video_url(post_url: str) -> str:
    r = requests.get(
        f"{RAPIDAPI_BASE_URL}/download",
        headers={
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": RAPIDAPI_HOST
        },
        params={"url": post_url},
        timeout=30
    )
    r.raise_for_status()

    data = r.json()
    video_url = extract_video_url(data)

    if not video_url:
        raise RuntimeError("No downloadable video found")

    return video_url


def upload_to_supabase(local_path: Path, video_id: str) -> str:
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise RuntimeError("Supabase credentials not configured")

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
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
    binary_mode = False

    args = sys.argv[1:]
    if not args:
        print("Instagram URL required", file=sys.stderr)
        sys.exit(1)

    if args[0] == "--binary":
        binary_mode = True
        args = args[1:]

    if not args:
        print("Instagram URL required", file=sys.stderr)
        sys.exit(1)

    raw_url = args[0]
    post_url = normalize_instagram_url(raw_url)
    video_id = extract_id_from_url(post_url)

    try:
        video_url = fetch_reel_video_url(post_url)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    # =========================
    # BINARY MODE (n8n)
    # =========================
    if binary_mode:
        r = requests.get(video_url, stream=True)
        r.raise_for_status()

        for chunk in r.iter_content(8192):
            if chunk:
                sys.stdout.buffer.write(chunk)

        return

    # =========================
    # SUPABASE MODE
    # =========================
    tmp_dir = Path("tmp/reels")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    local_path = tmp_dir / f"{video_id}.mp4"

    with requests.get(video_url, stream=True) as r:
        r.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)

    try:
        cdn_url = upload_to_supabase(local_path, video_id)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

    try:
        local_path.unlink()
    except Exception:
        pass

    print(json.dumps({
        "status": "ok",
        "video_id": video_id,
        "cdn_url": cdn_url
    }))


if __name__ == "__main__":
    main()
