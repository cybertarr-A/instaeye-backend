# cdn_resolver.py
import yt_dlp
from typing import Dict, Any


class CDNResolveError(Exception):
    pass


def _safe_int(value) -> int:
    """Convert None / non-int to 0 safely."""
    return value if isinstance(value, int) else 0


def resolve_instagram_cdn(reel_url: str) -> Dict[str, Any]:
    """
    Resolve Instagram Reel URL → direct CDN media URL (mp4).
    Metadata-only. No download.
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # Let yt-dlp decide best; we only read metadata
        "format": "bestvideo+bestaudio/best",
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(reel_url, download=False)

            if not info:
                raise CDNResolveError("No metadata returned")

            # ----------------------------
            # Fast path (preferred)
            # ----------------------------
            if info.get("url"):
                return {
                    "status": "ok",
                    "cdn_url": info["url"],
                    "id": info.get("id"),
                    "duration": info.get("duration"),
                    "extractor": info.get("extractor"),
                }

            # ----------------------------
            # Fallback: choose best format safely
            # ----------------------------
            formats = info.get("formats") or []
            if not formats:
                raise CDNResolveError("No formats found")

            best = max(
                formats,
                key=lambda f: (
                    _safe_int(f.get("height")),
                    _safe_int(f.get("tbr")),
                    _safe_int(f.get("filesize")),
                ),
            )

            cdn_url = best.get("url")
            if not cdn_url:
                raise CDNResolveError("Best format has no URL")

            return {
                "status": "ok",
                "cdn_url": cdn_url,
                "format_id": best.get("format_id"),
                "resolution": best.get("resolution"),
                "filesize": best.get("filesize"),
                "vcodec": best.get("vcodec"),
                "acodec": best.get("acodec"),
            }

    except Exception as e:
        raise CDNResolveError(str(e))
