import os
import cv2
import uuid
import requests
import tempfile
import time
from pathlib import Path

from google import genai
from google.genai import types
from supabase import create_client, Client

# ==================================================
# Gemini Client (STABLE + SUPPORTED)
# ==================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=GEMINI_API_KEY)

# ✅ FIX: Remove "models/" prefix. The SDK adds this automatically.
MODEL_NAME = "gemini-1.5-pro"

# ==================================================
# Supabase
# ==================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "temp-media")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==================================================
# PROMPTS
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
# Helper: Download video
# ==================================================

def download_video(video_url: str) -> Path:
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    try:
        r = requests.get(video_url, stream=True, timeout=60)
        r.raise_for_status()
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
        return Path(tmp_path)
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise e

# ==================================================
# Helper: Extract representative frame
# ==================================================

def extract_frame(video_path: Path) -> Path:
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise RuntimeError("No frames found in video")

    # Capture frame at ~25% mark to avoid black intro frames
    frame_number = max(1, total_frames // 4)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = cap.read()
    cap.release()

    if not success:
        raise RuntimeError("Failed to extract frame")

    img_path = video_path.with_suffix(".jpg")
    cv2.imwrite(str(img_path), frame)
    return img_path

# ==================================================
# Helper: Upload frame to Supabase
# ==================================================

def upload_frame_to_supabase(image_path: Path) -> str:
    remote_path = f"frames/{uuid.uuid4()}.jpg"

    with open(image_path, "rb") as f:
        supabase.storage.from_(SUPABASE_BUCKET).upload(
            remote_path,
            f,
            {"content-type": "image/jpeg"},
        )

    return (
        f"{SUPABASE_URL}/storage/v1/object/public/"
        f"{SUPABASE_BUCKET}/{remote_path}"
    )

# ==================================================
# MAIN ENTRY
# ==================================================

def analyze_reel(video_url: str) -> dict:
    video_path = None
    frame_path = None
    gemini_file = None

    try:
        # 1. Download Video
        video_path = download_video(video_url)
        
        # 2. Extract Frame
        frame_path = extract_frame(video_path)
        
        # 3. Upload to Supabase (Public URL for your record)
        frame_url = upload_frame_to_supabase(frame_path)

        # 4. Upload to Gemini (ONCE)
        # We upload the local file directly to Gemini to save bandwidth
        print(f"Uploading frame to Gemini...")
        gemini_file = client.files.upload(
            file=frame_path,
            config={"mime_type": "image/jpeg"}
        )

        # Wait for file to be ready (usually instant for images, but good practice)
        while gemini_file.state.name == "PROCESSING":
            time.sleep(1)
            gemini_file = client.files.get(name=gemini_file.name)

        if gemini_file.state.name == "FAILED":
            raise RuntimeError("Gemini file upload failed")

        print(f"Gemini File Ready: {gemini_file.name}")

        # 5. Run All Prompts (Re-using the single uploaded file)
        results = {}
        for key, prompt_text in PROMPTS.items():
            try:
                print(f"Analyzing: {key}...")
                response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=[
                        prompt_text, 
                        gemini_file
                    ]
                )
                results[key] = response.text.strip()
            except Exception as e:
                print(f"Error on {key}: {e}")
                results[key] = f"[gemini_error] {str(e)}"

        return {
            "status": "success",
            "video_url": video_url,
            "frame_url": frame_url,
            "analyses": results,
            "analysis_count": len(results),
            "method": "multi_prompt_gemini_vision_optimized",
            "model": MODEL_NAME,
        }

    except Exception as e:
        return {
            "status": "error",
            "video_url": video_url,
            "error": str(e)
        }

    finally:
        # Cleanup Local Files
        if video_path and video_path.exists():
            video_path.unlink()
        if frame_path and frame_path.exists():
            frame_path.unlink()
            
        # Cleanup Gemini File (Save Cloud Storage)
        if gemini_file:
            try:
                client.files.delete(name=gemini_file.name)
                print("Gemini temporary file deleted.")
            except Exception:
                pass

# ==================================================
# EXAMPLE USAGE
# ==================================================

if __name__ == "__main__":
    # Test with a dummy video URL or one provided by your system
    test_url = "https://www.w3schools.com/html/mov_bbb.mp4" 
    result = analyze_reel(test_url)
    print(result)
