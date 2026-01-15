import os
import cv2
import uuid
import requests
import tempfile
from pathlib import Path
from openai import OpenAI
from supabase import create_client, Client

# --------------------------------------------------
# Clients
# --------------------------------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "temp-media")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase credentials missing")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --------------------------------------------------
# Default prompt
# --------------------------------------------------
DEFAULT_PROMPT = (
    "Analyze this Instagram Reel frame.\n\n"
    "Describe:\n"
    "- What is visibly happening\n"
    "- Any on-screen text or branding\n"
    "- Likely content category (education, promo, meme, lifestyle, etc.)\n"
    "- Whether there appears to be promotional intent\n\n"
    "Clearly distinguish what is directly visible from what is inferred.\n"
    "Do NOT assume audio or spoken dialogue unless visually implied."
)

# --------------------------------------------------
# Download video
# --------------------------------------------------
def download_video(video_url: str) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".mp4")[1])
    r = requests.get(video_url, stream=True, timeout=60)
    r.raise_for_status()

    with open(tmp, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)

    return tmp

# --------------------------------------------------
# Extract frame
# --------------------------------------------------
def extract_frame(video_path: Path) -> Path:
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise Exception("No frames found")

    frame_number = max(1, total_frames // 4)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = cap.read()
    cap.release()

    if not success:
        raise Exception("Failed to extract frame")

    img_path = video_path.with_suffix(".jpg")
    cv2.imwrite(str(img_path), frame)
    return img_path

# --------------------------------------------------
# Upload frame & return public URL
# --------------------------------------------------
def upload_frame_and_get_url(image_path: Path) -> str:
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

# --------------------------------------------------
# Analyze frame with OpenAI (URL-based)
# --------------------------------------------------
def analyze_frame(image_url: str, prompt: str) -> str:
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ],
    )

    return response.output_text

# --------------------------------------------------
# Main entry point
# --------------------------------------------------
def analyze_reel(video_url: str, prompt: str | None = None) -> dict:
    video_path = None
    frame_path = None

    try:
        video_path = download_video(video_url)
        frame_path = extract_frame(video_path)

        frame_url = upload_frame_and_get_url(frame_path)
        final_prompt = prompt.strip() if prompt else DEFAULT_PROMPT

        analysis = analyze_frame(frame_url, final_prompt)

        return {
            "video_url": video_url,
            "frame_url": frame_url,
            "analysis": analysis,
            "method": "openai_vision_frame_analysis",
        }

    finally:
        if video_path and video_path.exists():
            video_path.unlink()
        if frame_path and frame_path.exists():
            frame_path.unlink()
