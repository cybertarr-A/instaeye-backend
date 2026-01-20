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


def _extract_shortcode(insta_url: str) -> str:
    """
    Extract shortcode from /p/ or /reel/ URL
    """
    match = re.search(r"/(p|reel)/([^/]+)/?", insta_url)
    if not match:
        raise ReelResolveError("Invalid Instagram URL")
    return match.group(2)


def resolve_reel_video_url(insta_url: str) -> str:
    """
    Instagram URL → Direct MP4 URL
    """

    # -----------------------------------
    # 1️⃣ Try HTML (fast path)
    # -----------------------------------
    r = requests.get(insta_url, headers=HEADERS, timeout=15)
    if r.status_code != 200:
        raise ReelResolveError("Failed to fetch Instagram page")

    soup = BeautifulSoup(r.text, "html.parser")

    # ld+json
    for script in soup.find_all("script", type="application/ld+json"):
        if "contentUrl" in script.text:
            match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', script.text)
            if match:
                return match.group(1).replace("\\u0026", "&")

    # og:video
    meta = soup.find("meta", property="og:video")
    if meta and meta.get("content"):
        return meta["content"]

    # -----------------------------------
    # 2️⃣ JSON fallback (SnapInsta method)
    # -----------------------------------
    shortcode = _extract_shortcode(insta_url)

    json_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
    jr = requests.get(json_url, headers=HEADERS, timeout=15)

    if jr.status_code != 200:
        raise ReelResolveError("Instagram JSON endpoint blocked")

    data = jr.json()

    try:
        media = data["graphql"]["shortcode_media"]
        if media.get("is_video") and "video_url" in media:
            return media["video_url"]
    except Exception:
        pass

    raise ReelResolveError("Video URL not found")
