import os
import cv2
import base64
import requests
import tempfile
from openai import OpenAI

# --------------------------------------------------
# OpenAI Client
# --------------------------------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------------------------------------
# Default prompt (used only if none is provided)
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
def download_video(video_url: str) -> str:
    response = requests.get(video_url, stream=True, timeout=60)
    response.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    for chunk in response.iter_content(chunk_size=1024 * 1024):
        if chunk:
            tmp.write(chunk)

    tmp.close()
    return tmp.name

# --------------------------------------------------
# Extract representative frame
# --------------------------------------------------
def extract_frame(video_path: str) -> str:
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        raise Exception("No frames found in video")

    frame_number = max(1, total_frames // 4)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = cap.read()
    cap.release()

    if not success:
        raise Exception("Failed to extract frame")

    img_path = video_path.replace(".mp4", ".jpg")
    cv2.imwrite(img_path, frame)
    return img_path

# --------------------------------------------------
# Analyze frame with OpenAI (prompt injected)
# --------------------------------------------------
def analyze_frame(image_path: str, prompt: str) -> str:
    with open(image_path, "rb") as img:
        img_b64 = base64.b64encode(img.read()).decode("utf-8")

    response = client.responses.create(
        model="gpt-4.1",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt
                    },
                    {
                        "type": "input_image",
                        "image_base64": img_b64
                    }
                ]
            }
        ]
    )

    return response.output_text

# --------------------------------------------------
# Main entry point (used by FastAPI / HTTP node)
# --------------------------------------------------
def analyze_reel(video_url: str, prompt: str | None = None) -> dict:
    """
    Analyze a reel using a dynamically provided prompt.
    """
    video_path = None
    frame_path = None

    try:
        video_path = download_video(video_url)
        frame_path = extract_frame(video_path)

        final_prompt = prompt.strip() if prompt else DEFAULT_PROMPT
        analysis = analyze_frame(frame_path, final_prompt)

        return {
            "video_url": video_url,
            "analysis": analysis,
            "prompt_used": final_prompt,
            "method": "openai_vision_frame_analysis"
        }

    finally:
        if video_path and os.path.exists(video_path):
            os.remove(video_path)
        if frame_path and os.path.exists(frame_path):
            os.remove(frame_path)
