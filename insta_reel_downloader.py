import sys
import subprocess

def main():
    if len(sys.argv) < 2:
        print("Instagram URL required", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bv*+ba/b",
        "-o", "-",          # stream to stdout
        url
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        for chunk in iter(lambda: process.stdout.read(8192), b""):
            sys.stdout.buffer.write(chunk)
    except BrokenPipeError:
        pass

    process.wait()

    if process.returncode != 0:
        err = process.stderr.read().decode(errors="ignore")
        print(err, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
