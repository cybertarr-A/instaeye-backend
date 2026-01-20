import sys
import yt_dlp
from pathlib import Path

COOKIE_FILE = Path("cookies.txt")

if not COOKIE_FILE.exists():
    print("cookies.txt not found", file=sys.stderr)
    sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Instagram URL required", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]

    ydl_opts = {
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": "-",              # stream to stdout (n8n)
        "cookiefile": str(COOKIE_FILE),
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
