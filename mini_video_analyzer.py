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
# PROMPT SET (REDUCED TO 3)
# --------------------------------------------------
PROMPTS = {
    "visual_summary": (
        "Describe exactly what is visible in this Instagram Reel frame. "
        "Mention people, actions, objects, text overlays, and environment. "
        "Do not infer intent or emotions."
    ),
    "promotion_detection": (
        "Determine whether this content appears promotional or monetized. "
        "Look for branding, products, logos, discount text, or calls to action."
    ),
    "virality_potential": (
        "Estimate the viral potential of this reel based on visuals alone. "
        "Explain what could help or limit its reach."
    ),
}

# --------------------------------------------------
# Download video
# --------------------------------------------------
def download_video(video_url: str) -> Path:
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)

    r = requests.get(video_url, stream=True, timeout=45)
    r.raise_for_status()

    with open(tmp_path, "wb") as f:
        for chunk in r.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)

    return Path(tmp_path)

# --------------------------------------------------
# Extract representative frame
# --------------------------------------------------
def extract_frame(video_path: Path) -> Path:
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise RuntimeError("No frames found in video")

    frame_number = max(1, total_frames // 4)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = cap.read()
    cap.release()

    if not success:
        raise RuntimeError("Failed to extract frame")

    img_path = video_path.with_suffix(".jpg")
    cv2.imwrite(str(img_path), frame)
    return img_path

# --------------------------------------------------
# Upload frame to Supabase
# --------------------------------------------------
def upload_frame(image_path: Path) -> str:
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
# OpenAI Vision Analysis
# --------------------------------------------------
def run_prompt(image_url: str, prompt: str) -> str:
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
        timeout=30,  # Railway-safe
    )

    return response.output_text.strip()

# --------------------------------------------------
# MAIN ENTRY
# --------------------------------------------------
def analyze_reel(video_url: str) -> dict:
    video_path = None
    frame_path = None

    try:
        video_path = download_video(video_url)
        frame_path = extract_frame(video_path)
        frame_url = upload_frame(frame_path)

        analyses = {
            key: run_prompt(frame_url, prompt)
            for key, prompt in PROMPTS.items()
        }

        return {
            "status": "success",
            "video_url": video_url,
            "frame_url": frame_url,
            "analyses": analyses,
            "analysis_count": len(analyses),
            "method": "3_prompt_openai_vision",
        }

    finally:
        if video_path and video_path.exists():
            video_path.unlink()
        if frame_path and frame_path.exists():
            frame_path.unlink()
