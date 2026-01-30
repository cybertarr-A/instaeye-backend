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
# 1. Configuration
# ==================================================

MODEL_NAME = "gemini-2.0-flash"

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
# 2. Prompts Dictionary (Your Custom Prompts)
# ==================================================

PROMPTS = {
    "visual_summary": (
        "Describe exactly what is visible in this Instagram Reel frame. "
        "Mention people, actions, objects, text overlays, and environment. "
        "Do not infer audio, speech, intent, or emotions."
    ),
    "content_category": (
        "Classify this content based only on visuals into categories such as "
        "education, promotion, entertainment, lifestyle, meme, or news. "
        "Explain briefly."
    ),
    "promotion_detection": (
        "Determine whether this content appears promotional or monetized "
        "based on visible branding, products, logos, or calls to action."
    ),
    "hook_analysis": (
        "Analyze how strong the visual hook is in the opening moment of this frame. "
        "Explain what would make a viewer stop scrolling."
    ),
    "virality_potential": (
        "Estimate the viral potential based on visuals alone. "
        "Explain strengths and weaknesses."
    ),
}

# ==================================================
# 3. Output Schema (Mapped to Your Prompts)
# ==================================================

class ReelAnalysis(BaseModel):
    # We use your exact prompt text as the description for each field
    visual_summary: str = Field(..., description=PROMPTS["visual_summary"])
    content_category: str = Field(..., description=PROMPTS["content_category"])
    promotion_detection: str = Field(..., description=PROMPTS["promotion_detection"])
    hook_analysis: str = Field(..., description=PROMPTS["hook_analysis"])
    virality_potential: str = Field(..., description=PROMPTS["virality_potential"])

# ==================================================
# 4. Helper Functions
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
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise RuntimeError("No frames found in video")

    # Capture at 20% mark
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
    remote_path = f"frames/{uuid.uuid4()}.jpg"
    with open(image_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path,
            f,
            {"content-type": "image/jpeg"},
        )
    return f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{remote_path}"

# ==================================================
# 5. Main Logic
# ==================================================

def analyze_reel(video_url: str) -> dict:
    video_path = None
    frame_path = None

    try:
        print(f"⬇️ Downloading: {video_url}...")
        video_path = download_video(video_url)
        frame_path = extract_frame(video_path)
        frame_url = upload_frame_to_supabase(frame_path)

        with open(frame_path, "rb") as f:
            image_bytes = f.read()

        print(f"🤖 Analyzing with Gemini ({MODEL_NAME})...")
        
        # We send one request, but the Schema ensures all 5 prompts are answered
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                "Analyze this image frame according to the defined schema instructions."
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ReelAnalysis, 
                temperature=0.2
            )
        )

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
        return {"status": "error", "error": str(e)}

    finally:
        if video_path and video_path.exists(): video_path.unlink()
        if frame_path and frame_path.exists(): frame_path.unlink()

if __name__ == "__main__":
    test_url = "https://www.w3schools.com/html/mov_bbb.mp4"
    result = analyze_reel(test_url)
    
    print("\n--- GEMINI ANALYSIS ---")
    if result["status"] == "success":
        # Dump using Pydantic's model_dump if available, else standard json
        data = result["data"]
        output_dict = data.model_dump() if hasattr(data, "model_dump") else data
        print(json.dumps(output_dict, indent=2))
    else:
        print(result)
