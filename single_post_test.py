import sys
import json
import re
from datetime import datetime

def extract_shortcode(url: str) -> str:
    match = re.search(r"/(p|reel)/([^/]+)/", url)
    if not match:
        raise ValueError("Invalid Instagram post URL")
    return match.group(2)

def main():
    body = json.loads(sys.stdin.read())

    post_url = body.get("post_url")
    if not post_url:
        raise ValueError("post_url missing")

    shortcode = extract_shortcode(post_url)

    # MOCK RESULT (workflow test only)
    result = {
        "id": f"test_{shortcode}",
        "type": "VIDEO",
        "caption": "This is a test caption for workflow validation",
        "hashtags": ["test", "n8n", "workflow"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "permalink": post_url,
        "media_url": "https://cdn.test/media.mp4",
        "thumbnail_url": "https://cdn.test/thumb.jpg",
        "likes": 123,
        "comments": 9,
        "insights": {
            "plays": 4567,
            "reach": 3200,
            "impressions": 5100,
            "saved": 42,
            "shares": 7
        },
        "ai_summary": "Mock AI summary for workflow testing"
    }

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
