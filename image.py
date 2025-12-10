import requests
import tempfile
import base64
import os
import cv2
from openai import OpenAI

# IMPORTANT:
# Move this API key into Railway ENV VARIABLES
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def download_raw(url: str) -> str:
    """Download media to a temporary file and return file path."""
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        for chunk in r.iter_content(chunk_size=8192):
            temp_file.write(chunk)
    temp_file.close()
    return temp_file.name


def extract_frame(video_path: str) -> str:
    """Extract first frame of a video and save it as image."""
    frame_path = video_path + ".jpg"
    cap = cv2.VideoCapture(video_path)
    success, frame = cap.read()

    if not success:
        raise RuntimeError("Could not read video")

    cv2.imwrite(frame_path, frame)
    cap.release()
    return frame_path


def image_to_base64(image_path: str) -> str:
    """Convert image to base64 string."""
    with open(image_path, "rb") as img:
        return base64.b64encode(img.read()).decode("utf-8")


def analyze_with_openai(image_path: str) -> str:
    """Send image to OpenAI Vision model and return summary."""
    base64_image = image_to_base64(image_path)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Analyze this content and summarise its meaning and intent."
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ],
        max_tokens=300
    )

    return response.choices[0].message.content


# ----------------------------
# MAIN FUNCTION FOR FASTAPI
# ----------------------------
def analyze_image(media_url: str) -> dict:
    """
    The main function called by the central FastAPI backend.
    Attempts video → extract frame, else treat directly as image.
    """

    temp_path = download_raw(media_url)

    # If video, extract first frame
    try:
        frame_path = extract_frame(temp_path)
    except:
        frame_path = temp_path  # treat as image

    summary = analyze_with_openai(frame_path)

    # cleanup temp files
    if os.path.exists(frame_path) and frame_path != temp_path:
        os.remove(frame_path)
    if os.path.exists(temp_path):
        os.remove(temp_path)

    return {
        "link": media_url,
        "summary": summary
    }
