import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

class ReelResolveError(Exception):
    pass


def resolve_reel_video_url(insta_url: str) -> str:
    """
    Resolve ONLY Instagram /reel/ URLs → direct MP4 CDN URL
    """

    # ----------------------------
    # 1️⃣ Enforce /reel/ contract
    # ----------------------------
    if "/reel/" not in insta_url:
        raise ReelResolveError(
            "Only Instagram /reel/ URLs are supported. "
            "Please provide a /reel/ link, not /p/."
        )

    # ----------------------------
    # 2️⃣ Fetch HTML
    # ----------------------------
    r = requests.get(insta_url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        raise ReelResolveError("Failed to fetch Instagram reel page")

    soup = BeautifulSoup(r.text, "html.parser")

    # ----------------------------
    # 3️⃣ Extract video URL
    # ----------------------------

    # ld+json (best case)
    for script in soup.find_all("script", type="application/ld+json"):
        if "contentUrl" in script.text:
            match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', script.text)
            if match:
                return match.group(1).replace("\\u0026", "&")

    # og:video fallback
    meta = soup.find("meta", property="og:video")
    if meta and meta.get("content"):
        return meta["content"]

    raise ReelResolveError(
        "Unable to extract video from this Reel. "
        "The Reel may be restricted or unavailable."
    )
