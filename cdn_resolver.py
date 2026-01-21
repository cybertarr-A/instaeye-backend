# cdn_resolver.py
import yt_dlp
from typing import Dict, Any


class CDNResolveError(Exception):
    pass


def resolve_instagram_cdn(reel_url: str) -> Dict[str, Any]:
    """
    Minimal Instagram Reel → CDN resolver.
    Behavior intentionally matches the working local script.
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best",        # keep exactly
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(reel_url.strip(), download=False)

            if not info:
                raise CDNResolveError("No metadata returned by Instagram")

            cdn_url = info.get("url")
            if not cdn_url:
                raise CDNResolveError("No CDN URL found in metadata")

            return {
                "status": "ok",
                "cdn_url": cdn_url,
                "id": info.get("id"),
                "duration": info.get("duration"),
                "extractor": info.get("extractor"),
            }

    except Exception as e:
        msg = str(e).lower()

        # ---- classify Instagram rejections clearly ----
        if "login required" in msg or "cookies" in msg:
            raise CDNResolveError(
                "Instagram requires login (cookies needed)"
            )

        if "rate-limit" in msg or "try again later" in msg:
            raise CDNResolveError(
                "Instagram rate-limited this IP (cloud IP restriction)"
            )

        if "not available" in msg or "private" in msg:
            raise CDNResolveError(
                "Instagram content is private or unavailable"
            )

        # ---- unknown failure ----
        raise CDNResolveError(str(e))
