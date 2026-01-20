import sys
import yt_dlp
from pathlib import Path

COOKIE_FILE = Path("cookies.txt")  # optional but recommended

def main():
    if len(sys.argv) < 2:
        print("Instagram URL required", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]

    ydl_opts = {
        "quiet": True,
        "skip_download": True,      # ⬅ IMPORTANT
        "no_warnings": True,
    }

    # Use cookies if available
    if COOKIE_FILE.exists():
        ydl_opts["cookiefile"] = str(COOKIE_FILE)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"Error extracting info: {e}", file=sys.stderr)
        sys.exit(1)

    cdn_urls = []

    # Case 1: Single video
    if "url" in info:
        cdn_urls.append(info["url"])

    # Case 2: Multiple formats (common)
    for f in info.get("formats", []):
        if f.get("vcodec") != "none" and f.get("url"):
            cdn_urls.append(f["url"])

    # Deduplicate
    cdn_urls = list(dict.fromkeys(cdn_urls))

    if not cdn_urls:
        print("No CDN URLs found", file=sys.stderr)
        sys.exit(1)

    # Output as JSON-like lines (n8n-friendly)
    for i, u in enumerate(cdn_urls, 1):
        print(f"[{i}] {u}")

if __name__ == "__main__":
    main()
