import os
import cv2
import uuid
import requests
import tempfile
import json
import time
from pathlib import Path

from google import genai
from google.genai import types
from supabase import create_client, Client
from pydantic import BaseModel, Field

# ==================================================
# 1. Configuration & Clients
# ==================================================

# ✅ FIX: Use "gemini-1.5-flash" for best availability and speed with vision
MODEL_NAME = "gemini-1.5-flash"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=GEMINI_API_KEY)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "temp-media")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================================================
# 2. Define Output Structure (Schema)
# ==================================================

class ReelAnalysis(BaseModel):
    visual_summary: str = Field(..., description="Describe exactly what is visible: people, actions, objects, text.")
    content_category: str = Field(..., description="Classify into: Education, Entertainment, Lifestyle, Promo, etc.")
    is_promotional: bool = Field(..., description="True if the content appears monetized or sells a product.")
    hook_strength: str = Field(..., description="Analyze the visual hook. strong/medium/weak and why.")
    virality_score: int = Field(..., description="Score from 1-10 based on visual appeal.")

# ==================================================
# 3. Helper Functions
# ==================================================

def download_video(video_url: str) -> Path:
    """Downloads video to a temp file."""
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
    """Extracts a representative frame from the video."""
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise RuntimeError("No frames found in video")

    # Capture at 20% to avoid black intro frames
    frame_number = max(1, int(total_frames * 0.2))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    success, frame = cap.read()
    cap.release()

    if not success:
        raise RuntimeError("Failed to extract frame")

    img_path = video_path.with_suffix(".jpg")
    cv2.imwrite(str(img_path), frame)
    return img_path

def upload_frame_to_supabase(image_path: Path) -> str:
    """Uploads the extracted frame to Supabase Storage."""
    remote_path = f"frames/{uuid.uuid4()}.jpg"
    with open(image_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path,
            f,
            {"content-type": "image/jpeg"},
        )
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{remote_path}"

# ==================================================
# 4. Main Analysis Logic
# ==================================================

def analyze_reel(video_url: str) -> dict:
    video_path = None
    frame_path = None

    try:
        print(f"⬇️ Downloading: {video_url}...")
        video_path = download_video(video_url)
        
        print("📸 Extracting frame...")
        frame_path = extract_frame(video_path)
        
        print("☁️ Uploading frame to Supabase...")
        frame_url = upload_frame_to_supabase(frame_path)

        # Read image bytes for Gemini
        with open(frame_path, "rb") as f:
            image_bytes = f.read()

        print(f"🤖 Analyzing with Gemini ({MODEL_NAME})...")
        
        # ✅ FIX: Direct byte upload + Structured JSON Response
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                "Analyze this Instagram Reel frame. Be specific and concise."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReelAnalysis, # Enforces the Pydantic schema
                temperature=0.2
            )
        )

        # Parse the result
        # The SDK now returns a parsed object if a schema is provided, 
        # or we can parse the text manually if needed.
        try:
            analysis_data = response.parsed
        except:
            analysis_data = json.loads(response.text)

        return {
            "status": "success",
            "video_url": video_url,
            "frame_url": frame_url,
            "data": analysis_data, 
            "model": MODEL_NAME
        }

    except Exception as e:
        print(f"❌ Error: {e}")
        return {
            "status": "error",
            "video_url": video_url,
            "error": str(e)
        }

    finally:
        # Cleanup
        if video_path and video_path.exists(): video_path.unlink()
        if frame_path and frame_path.exists(): frame_path.unlink()

# ==================================================
# Execution
# ==================================================

if __name__ == "__main__":
    # Test Video
    test_url = "https://www.w3schools.com/html/mov_bbb.mp4"
    
    result = analyze_reel(test_url)
    
    # Pretty print the output
    print("\n--- FINAL RESULT ---")
    if result["status"] == "success":
        # Convert Pydantic object to dict for printing if necessary
        data = result["data"]
        if hasattr(data, "model_dump"):
            print(json.dumps(data.model_dump(), indent=2))
        else:
            print(json.dumps(data, indent=2))
        print(f"\nFrame Reference: {result['frame_url']}")
    else:
        print(result)
