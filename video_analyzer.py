import os
import cv2
import uuid
import requests
import tempfile
import json
import uvicorn
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from supabase import create_client, Client

# ==================================================
# CONFIGURATION
# ==================================================

app = FastAPI()

# Railway automatically sets the PORT env var, but we default to 8000
PORT = int(os.getenv("PORT", 8000))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "temp-media")

# Validation
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set!")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials missing!")

client = genai.Client(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
MODEL_NAME = "gemini-2.0-flash"

# ==================================================
# DATA MODELS
# ==================================================

class VideoRequest(BaseModel):
    video_url: str

class ReelAnalysis(BaseModel):
    visual_summary: str = Field(..., description="Describe exactly what is visible in the video.")
    content_category: str = Field(..., description="Classify content: Education, Entertainment, etc.")
    promotion_detection: str = Field(..., description="Is this promotional? Mention brands/logos.")
    hook_analysis: str = Field(..., description="Analyze the visual hook strength.")
    virality_potential: str = Field(..., description="Estimate viral potential (High/Medium/Low).")

# ==================================================
# HELPER FUNCTIONS
# ==================================================

def download_video(video_url: str) -> Path:
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        r = requests.get(video_url, stream=True, timeout=60)
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk: f.write(chunk)
        return Path(tmp_path)
    except Exception as e:
        if os.path.exists(tmp_path): os.unlink(tmp_path)
        raise e

def extract_frame(video_path: Path) -> Path:
    """Extracts a frame at 20% mark."""
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        raise ValueError("Video seems empty or corrupted.")
        
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(1, int(total_frames * 0.2)))
    success, frame = cap.read()
    cap.release()
    
    if not success:
        raise ValueError("Could not read frame from video.")
        
    img_path = video_path.with_suffix(".jpg")
    cv2.imwrite(str(img_path), frame)
    return img_path

def upload_to_supabase(image_path: Path) -> str:
    remote_path = f"frames/{uuid.uuid4()}.jpg"
    with open(image_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path, f, {"content-type": "image/jpeg"}
        )
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{remote_path}"

# ==================================================
# API ENDPOINTS
# ==================================================

@app.get("/")
def health_check():
    return {"status": "active", "service": "InstaEye Backend"}

@app.post("/analyze")
def analyze_reel_endpoint(request: VideoRequest):
    """
    Endpoint for n8n to call.
    Body: { "video_url": "https://..." }
    """
    video_path = None
    frame_path = None
    
    try:
        print(f"Processing: {request.video_url}")
        
        # 1. Download & Process
        video_path = download_video(request.video_url)
        frame_path = extract_frame(video_path)
        frame_url = upload_to_supabase(frame_path)
        
        # 2. Analyze with Gemini
        with open(frame_path, "rb") as f:
            image_bytes = f.read()
            
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                "Analyze this Instagram Reel frame based on the schema."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReelAnalysis,
                temperature=0.2
            )
        )
        
        # 3. Parse Response
        try:
            # Try parsing using the SDK's typed object first
            analysis = response.parsed
        except:
            # Fallback to standard JSON load
            analysis = json.loads(response.text)

        return {
            "status": "success",
            "frame_url": frame_url,
            "analysis": analysis
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup temp files
        if video_path and video_path.exists(): video_path.unlink()
        if frame_path and frame_path.exists(): frame_path.unlink()

# ==================================================
# RAILWAY ENTRY POINT
# ==================================================

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
