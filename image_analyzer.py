import os
import tempfile
import base64
import requests
import cv2

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
# model choice — change if needed
OPENAI_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")  # fallback to gpt-4o

if not OPENAI_API_KEY:
    raise Exception("Missing OPENAI_API_KEY environment variable")


def download_raw(url: str) -> str:
    """Download media to a temporary file and return filepath."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tmp")
    for chunk in resp.iter_content(chunk_size=8192):
        if chunk:
            tmp.write(chunk)
    tmp.close()
    return tmp.name


def extract_frame(video_path: str) -> str:
    """Try extracting the first readable frame from a video; return image path."""
    img_path = video_path + ".jpg"
    cap = cv2.VideoCapture(video_path)
    success, frame = cap.read()
    cap.release()

    if not success or frame is None:
        raise RuntimeError("Failed to read frame from video")

    # write as jpg
    cv2.imwrite(img_path, frame)
    return img_path


def image_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def call_openai_with_image_b64(image_b64: str) -> str:
    """
    Sends an image (as data URL) to OpenAI chat completions and returns assistant text.
    This uses the generic chat completions endpoint with an image data URL embedded in the message content.
    """
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "You are an image analysis assistant. Provide a short summary."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this image and summarise its meaning, intent, and any visible promotional elements."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }
        ],
        "max_tokens": 400,
        "temperature": 0.0
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = requests.post(OPENAI_CHAT_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    body = resp.json()

    # best-effort extraction of assistant text
    try:
        return body["choices"][0]["message"]["content"]
    except Exception:
        # fallback: return raw JSON if format unexpected
        return str(body)


def analyze_image(media_url: str) -> dict:
    """
    Main function to call from main.py.
    Accepts: media_url (image or video)
    Returns: { "link": media_url, "summary": "..." }
    """

    temp_files = []
    try:
        tmp = download_raw(media_url)
        temp_files.append(tmp)

        # decide if video (very crude: check extension or try frame extraction)
        lower = media_url.lower()
        is_video_ext = lower.endswith((".mp4", ".mov", ".mkv", ".webm", ".avi"))

        if is_video_ext:
            try:
                img_path = extract_frame(tmp)
            except Exception:
                # if frame extraction fails, try treating file as an image
                img_path = tmp
        else:
            # assume image
            img_path = tmp

        # ensure we have a jpg/png path for base64; convert if needed
        # If img_path isn't a JPG, we still open it and re-encode via OpenCV to JPG
        try:
            # try to re-encode as jpg to ensure correct mime and smaller size
            img = cv2.imread(img_path)
            if img is None:
                raise RuntimeError("cv2 failed to read image for encoding")
            jpg_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            jpg_path = jpg_tmp.name
            jpg_tmp.close()
            cv2.imencode(".jpg", img)[1].tofile(jpg_path)
            temp_files.append(jpg_path)
            image_for_b64 = jpg_path
        except Exception:
            # fallback to original file
            image_for_b64 = img_path

        image_b64 = image_to_base64(image_for_b64)
        summary = call_openai_with_image_b64(image_b64)

        return {"link": media_url, "summary": summary}

    finally:
        # cleanup all temp files we created
        for p in temp_files:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
