import os
import cv2
import base64
import requests
import tempfile
from openai import OpenAI

# Read OpenAI key from Railway environment, not hardcoded
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def download_video(video_url: str) -> str:
    """Download a video from URL into a temp .mp4 file."""
    response = requests.get(video_url, stream=True)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")

    for chunk in response.iter_content(chunk_size=1024):
        if chunk:
            tmp.write(chunk)

    tmp.close()
    return tmp.name


def extract_frame(video_path: str, frame_number: int = 30) -> str:
    """Extract frame #30 from the video and save as .jpg."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = cap.read()
    if not success:
        raise Exception("Failed to extract frame")

    img_path = video_path.replace(".mp4", ".jpg")
    cv2.imwrite(img_path, frame)
    cap.release()
    return img_path


def analyze_frame(image_path: str) -> str:
    """Send extracted frame to OpenAI Vision model."""
    with open(image_path, "rb") as img:
        img_b64 = base64.b64encode(img.read()).decode("utf-8")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Analyze this Instagram Reel frame and describe "
                            "what the video is about. Identify any promotional "
                            "Identify the music/Audio context of the reel"
                            "intent or visible links. also analyze what is people are saying in the video and what is the audio/music and analyze them too"
                        )
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}"
                        }
                    }
                ]
            }
        ]
    )

    return response.choices[0].message.content


# ----------------------------
# MAIN ENTRY POINT FOR FASTAPI
# ----------------------------
def analyze_reel(video_url: str) -> dict:
    """
    Master function used by the main FastAPI server.
    Attempts to analyze the reel by extracting a frame and describing it.
    """
    try:
        video_path = download_video(video_url)
        frame_path = extract_frame(video_path)

        analysis = analyze_frame(frame_path)

        return {
            "video_url": video_url,
            "analysis": analysis
        }

    finally:
        # Clean temp files
        if "video_path" in locals() and os.path.exists(video_path):
            os.remove(video_path)
        if "frame_path" in locals() and os.path.exists(frame_path):
            os.remove(frame_path)
