# cdn_resolver.py
import os
import yt_dlp
from pathlib import Path
from typing import Dict, Any


class CDNResolveError(Exception):
    pass


# ----------------------------
# Cookies handling (Railway-safe)
# ----------------------------

COOKIES_PATH = Path("/app/secrets/cookies.txt")
COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)

cookies_env = os.getenv("INSTAGRAM_COOKIES")

if cookies_env:
    # Always overwrite to keep cookies fresh on redeploy
    COOKIES_PATH.write_text(cookies_env)


def resolve_instagram_cdn(reel_url: str) -> Dict[str, Any]:
    """
    Instagram Reel → CDN resolver.
    Anonymous-first, cookies-enabled when required.
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best",        # keep EXACT behavior
        "skip_download": True,
        "noplaylist": True,
    }

    # Attach cookies only if present
    if COOKIES_PATH.exists():
        ydl_opts["cookiefile"] = str(COOKIES_PATH)

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
                "used_cookies": COOKIES_PATH.exists(),
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
