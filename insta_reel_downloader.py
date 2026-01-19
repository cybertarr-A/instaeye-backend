import sys
import subprocess
import json
import os
from pathlib import Path

def run(cmd):
    process = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return process.returncode, process.stdout, process.stderr


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "status": "error",
            "message": "Instagram post URL required"
        }))
        sys.exit(1)

    post_url = sys.argv[1]

    output_dir = Path("data/reels")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(output_dir / "%(id)s.%(ext)s")

    command = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", output_template,
        post_url
    ]

    code, out, err = run(command)

    if code != 0:
        print(json.dumps({
            "status": "error",
            "message": "Download failed",
            "error": err.strip()
        }))
        sys.exit(1)

    print(json.dumps({
        "status": "ok",
        "message": "Reel downloaded successfully"
    }))


if __name__ == "__main__":
    main()
