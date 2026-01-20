import os
import uvicorn
import requests
import yt_dlp
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# Get n8n URL from Environment Variable (Set this in Railway later)
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

class VideoRequest(BaseModel):
    url: str

def get_instagram_cdn_link(post_url):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        # 'cookies_from_browser': ('chrome',), # Optional: Only works locally
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"Processing: {post_url}")
            info = ydl.extract_info(post_url, download=False)
            
            video_url = info.get('url')
            
            # Fallback for some reel formats
            if not video_url:
                for f in info.get('formats', []):
                    if f.get('ext') == 'mp4':
                        video_url = f.get('url')
                        break
            
            return video_url, info.get('title'), info.get('uploader')

    except Exception as e:
        print(f"Extraction Error: {e}")
        return None, None, None

@app.get("/")
def home():
    return {"status": "running", "message": "Send POST request to /process with 'url'"}

@app.post("/process")
def process_video(request: VideoRequest):
    if not N8N_WEBHOOK_URL:
        raise HTTPException(status_code=500, detail="N8N_WEBHOOK_URL not set in env vars")

    cdn_link, caption, author = get_instagram_cdn_link(request.url)

    if not cdn_link:
        raise HTTPException(status_code=400, detail="Could not extract video. Link might be private or invalid.")

    # Send to n8n
    payload = {
        "video_url": cdn_link,
        "caption": caption,
        "author": author,
        "source": "railway_api"
    }
    
    try:
        n8n_res = requests.post(N8N_WEBHOOK_URL, json=payload)
        return {
            "status": "success", 
            "n8n_status": n8n_res.status_code, 
            "data": payload
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach n8n: {str(e)}")

if __name__ == "__main__":
    # Railway sets the PORT env var automatically
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
