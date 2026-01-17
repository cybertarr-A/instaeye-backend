import os
import requests
from typing import Dict, Any, List

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "instagram-statistics-api.p.rapidapi.com"
BASE_URL = "https://instagram-statistics-api.p.rapidapi.com"

if not RAPIDAPI_KEY:
    raise RuntimeError("RAPIDAPI_KEY not set")

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_HOST
}


class RapidAPIError(Exception):
    pass


def _get(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}{endpoint}"
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)

    if resp.status_code != 200:
        raise RapidAPIError(f"{resp.status_code}: {resp.text}")

    return resp.json()


# -----------------------------------------
# Fetch recent post CDN URLs by username
# -----------------------------------------

def get_recent_cdns(username: str, limit: int = 5) -> Dict[str, Any]:
    """
    Best-effort recent post CDN resolver via RapidAPI.
    Public accounts only.
    """

    try:
        # Endpoint used by this provider
        data = _get(
            "/user/media",
            {
                "username": username,
                "limit": limit
            }
        )

        posts = data.get("data") or data.get("items") or []

        cdn_urls: List[str] = []

        for post in posts:
            # Common fields returned by this API
            if "video_url" in post:
                cdn_urls.append(post["video_url"])

            elif "image_url" in post:
                cdn_urls.append(post["image_url"])

            elif "display_url" in post:
                cdn_urls.append(post["display_url"])

            elif "carousel_media" in post:
                for item in post["carousel_media"]:
                    if "display_url" in item:
                        cdn_urls.append(item["display_url"])

        if not cdn_urls:
            raise RapidAPIError("No CDN URLs found")

        return {
            "status": "success",
            "source": "rapidapi",
            "username": username,
            "count": len(cdn_urls),
            "cdn_urls": cdn_urls
        }

    except Exception as e:
        return {
            "status": "error",
            "source": "rapidapi",
            "username": username,
            "error": str(e)
        }
