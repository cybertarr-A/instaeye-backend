import os
import re
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, AnyUrl

# ==========================
# CONFIG
# ==========================
IG_OEMBED_TOKEN = os.getenv("IG_OEMBED_TOKEN")
OEMBED_URL = "https://graph.facebook.com/v18.0/instagram_oembed"

if not IG_OEMBED_TOKEN:
    raise RuntimeError("IG_OEMBED_TOKEN not set")

app = FastAPI(title="IG CDN Resolver", version="1.1")

# ==========================
# MODELS
# ==========================
class ResolveRequest(BaseModel):
    post_url: AnyUrl


# ==========================
# HELPERS
# ==========================
def extract_cdn(html: str):
    # handles jpg, png, mp4
    match = re.search(r'https://[^"]+\.(mp4|jpg|png)', html)
    return match.group(0) if match else None


# ==========================
# ROUTE
# ==========================
@app.post("/resolve")
def resolve(payload: ResolveRequest):
    params = {
        "url": str(payload.post_url),
        "access_token": IG_OEMBED_TOKEN
    }

    try:
        r = requests.get(OEMBED_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Instagram oEmbed failed")

    html = data.get("html")
    if not html:
        raise HTTPException(status_code=404, detail="Embed HTML missing")

    cdn_url = extract_cdn(html)

    return {
        "status": "ok",
        "post_url": payload.post_url,
        "cdn_url": cdn_url,
        "media_type": data.get("type"),
        "author": data.get("author_name")
    }
