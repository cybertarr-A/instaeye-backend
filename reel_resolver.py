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


def resolve_reel_video_url(reel_url: str) -> str:
    """
    Instagram Reel URL → direct MP4 CDN URL
    """

    response = requests.get(
        reel_url,
        headers=HEADERS,
        timeout=15,
        allow_redirects=True
    )

    if response.status_code != 200:
        raise ReelResolveError("Failed to fetch Instagram page")

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # 1. application/ld+json
    for script in soup.find_all("script", type="application/ld+json"):
        if "contentUrl" in script.text:
            match = re.search(r'"contentUrl"\s*:\s*"([^"]+)"', script.text)
            if match:
                return match.group(1).replace("\\u0026", "&")

    # 2. og:video
    meta = soup.find("meta", property="og:video")
    if meta and meta.get("content"):
        return meta["content"]

    # 3. regex fallback
    match = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
    if match:
        return match.group(1).replace("\\u0026", "&")

    raise ReelResolveError("Video URL not found")
