import os
import uuid
import requests
from pathlib import Path
from supabase import create_client, Client

# =========================
# CONFIG (Railway-safe)
# =========================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "videos")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials not set")

TMP_DIR = Path("/tmp")
TMP_DIR.mkdir(exist_ok=True)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# CORE FUNCTION
# =========================

def upload_instagram_video_cdn(
    cdn_url: str,
    folder: str = "instagram"
) -> dict:
    """
    Download Instagram Reel/Video from CDN
    Upload to Supabase
    Return Supabase public CDN URL
    """

    if ".mp4" not in cdn_url:
        raise ValueError("Only Instagram video CDN URLs (.mp4) are supported")

    video_id = str(uuid.uuid4())
    filename = f"{video_id}.mp4"

    local_path = TMP_DIR / filename
    supabase_path = f"{folder}/{filename}"

    # -------------------------
    # Download (streamed)
    # -------------------------
    response = requests.get(
        cdn_url,
        stream=True,
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
        }
    )
    response.raise_for_status()

    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                f.write(chunk)

    # -------------------------
    # Upload to Supabase
    # -------------------------
    with open(local_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            supabase_path,
            f,
            file_options={
                "content-type": "video/mp4",
                "cache-control": "3600",
                "upsert": False
            }
        )

    # -------------------------
    # Public CDN URL
    # -------------------------
    public_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(
        supabase_path
    )

    # Cleanup
    try:
        local_path.unlink()
    except Exception:
        pass

    return {
        "status": "success",
        "original_instagram_cdn": cdn_url,
        "supabase_path": supabase_path,
        "supabase_cdn_url": public_url
    }
