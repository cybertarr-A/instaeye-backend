import instaloader
import re
import os

DOWNLOAD_DIR = "/tmp/reels"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

L = instaloader.Instaloader(
    dirname_pattern=DOWNLOAD_DIR,
    download_comments=False,
    download_geotags=False,
    download_pictures=False,
    download_video_thumbnails=False,
    save_metadata=False,
    compress_json=False
)

# Optional login (Railway env vars)
USERNAME = os.getenv("IG_USERNAME")
PASSWORD = os.getenv("IG_PASSWORD")

if USERNAME and PASSWORD:
    try:
        L.login(USERNAME, PASSWORD)
    except Exception:
        pass


def download_reel(reel_url: str) -> str:
    """
    Download Instagram Reel and return MP4 file path
    """

    match = re.search(r"/reel/([^/]+)/?", reel_url)
    if not match:
        raise ValueError("Only Instagram /reel/ URLs are supported")

    shortcode = match.group(1)

    post = instaloader.Post.from_shortcode(L.context, shortcode)
    L.download_post(post, target=shortcode)

    video_path = os.path.join(DOWNLOAD_DIR, shortcode, f"{shortcode}.mp4")

    if not os.path.exists(video_path):
        raise RuntimeError("Reel video not found after download")

    return video_path
