import sys
import re
import requests
from bs4 import BeautifulSoup
import uuid
import os

# ============================
# CONFIG
# ============================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

DOWNLOAD_DIR = "/tmp/reels"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ============================
# HELPERS
# ============================

def normalize_instagram_url(url: str) -> str:
    """
    Remove query params, fragments, trailing slashes.
    Prevents random 404 / redirect issues.
    """
    return url.strip().split("?")[0].rstrip("/")


def extract_video_url(reel_url: str) -> str:
    """
    Resolve Instagram Reel URL -> direct MP4 CDN URL
    """

    response = requests.get(
        reel_url,
        headers=HEADERS,
        timeout=15,
        allow_redirects=True
    )
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # ----------------------------
    # Method 1: application/ld+json
    # ----------------------------
    for script in soup.find_all("script", type="application/ld+json"):
        if "contentUrl" in script.text:
            match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', script.text)
            if match:
                return match.group(1).replace("\\u0026", "&")

    # ----------------------------
    # Method 2: og:video meta tag
    # ----------------------------
    meta = soup.find("meta", property="og:video")
    if meta and meta.get("content"):
        return meta["content"]

    # ----------------------------
    # Method 3: regex fallback
    # ----------------------------
    match = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
    if match:
        return match.group(1).replace("\\u0026", "&")

    raise RuntimeError("Failed to resolve Instagram reel video URL")


# ============================
# MAIN (n8n entrypoint)
# ============================

def main():
    if len(sys.argv) < 2:
        print("ERROR: Reel URL missing", file=sys.stderr)
        sys.exit(1)

    reel_url = normalize_instagram_url(sys.argv[1])

    try:
        video_url = extract_video_url(reel_url)
    except Exception as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        sys.exit(2)

    filename = f"{uuid.uuid4()}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    try:
        with requests.get(video_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
    except Exception as e:
        print(f"ERROR: Download failed - {str(e)}", file=sys.stderr)
        sys.exit(3)

    # IMPORTANT:
    # n8n reads stdout → return ONLY the file path
    print(filepath)


if __name__ == "__main__":
    main()
