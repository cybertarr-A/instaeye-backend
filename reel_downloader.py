import sys
import re
import requests
from bs4 import BeautifulSoup
import uuid
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9"
}

DOWNLOAD_DIR = "/tmp/reels"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def extract_video_url(reel_url: str) -> str:
    r = requests.get(reel_url, headers=HEADERS, timeout=15)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # ld+json method
    for script in soup.find_all("script", type="application/ld+json"):
        if "contentUrl" in script.text:
            match = re.search(r'"contentUrl":"([^"]+)"', script.text)
            if match:
                return match.group(1).replace("\\u0026", "&")

    # fallback regex
    match = re.search(r'"video_url":"([^"]+)"', r.text)
    if match:
        return match.group(1).replace("\\u0026", "&")

    raise RuntimeError("Video URL not found")


def main():
    if len(sys.argv) < 2:
        print("ERROR: Reel URL missing")
        sys.exit(1)

    reel_url = sys.argv[1]

    video_url = extract_video_url(reel_url)

    filename = f"{uuid.uuid4()}.mp4"
    filepath = os.path.join(DOWNLOAD_DIR, filename)

    with requests.get(video_url, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)

    # IMPORTANT: n8n reads stdout
    print(filepath)


if __name__ == "__main__":
    main()
