# cdn_resolver.py
import yt_dlp
from typing import Dict, Any


class CDNResolveError(Exception):
    pass


def resolve_instagram_cdn(reel_url: str) -> Dict[str, Any]:
    """
    Minimal Instagram Reel → CDN resolver.
    Mirrors the working local script behavior.
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best",          # EXACTLY like your working script
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(reel_url, download=False)

            if not info:
                raise CDNResolveError("No metadata returned")

            cdn_url = info.get("url")
            if not cdn_url:
                raise CDNResolveError("No CDN URL found")

            return {
                "status": "ok",
                "cdn_url": cdn_url,
                "id": info.get("id"),
                "duration": info.get("duration"),
                "extractor": info.get("extractor"),
            }

    except Exception as e:
        raise CDNResolveError(str(e))
