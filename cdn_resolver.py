# cdn_resolver.py
import yt_dlp
from typing import Dict, Any

class CDNResolveError(Exception):
    pass


def resolve_instagram_cdn(reel_url: str) -> Dict[str, Any]:
    """
    Resolve Instagram Reel URL → direct CDN media URL (mp4).
    Metadata-only. No download.
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "bestvideo+bestaudio/best",
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(reel_url, download=False)

            if not info:
                raise CDNResolveError("No metadata returned")

            # yt-dlp sometimes nests formats
            if "url" in info:
                return {
                    "status": "ok",
                    "cdn_url": info["url"],
                    "extractor": info.get("extractor"),
                    "id": info.get("id"),
                    "duration": info.get("duration"),
                }

            formats = info.get("formats") or []
            if not formats:
                raise CDNResolveError("No formats found")

            best = max(
                formats,
                key=lambda f: (f.get("height", 0), f.get("tbr", 0))
            )

            return {
                "status": "ok",
                "cdn_url": best.get("url"),
                "format_id": best.get("format_id"),
                "resolution": best.get("resolution"),
                "filesize": best.get("filesize"),
            }

    except Exception as e:
        raise CDNResolveError(str(e))
