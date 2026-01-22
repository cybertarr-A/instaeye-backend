import os
import io
import uuid
import shutil
import traceback
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

# ============================
# CONFIG
# ============================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

client = OpenAI(api_key=OPENAI_API_KEY)

AUDIO_TMP_DIR = "/tmp/audio"
os.makedirs(AUDIO_TMP_DIR, exist_ok=True)

# ============================
# ROUTER
# ============================

router = APIRouter(prefix="/audio", tags=["audio"])

# ============================
# REQUEST MODELS
# ============================

class AudioURLRequest(BaseModel):
    # Accepts BOTH "audio_url" and "URL"
    audio_url: str | None = Field(default=None, alias="URL")

    class Config:
        populate_by_name = True

# ============================
# ROUTES
# ============================

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Multipart audio upload transcription
    (n8n binary / manual upload)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid audio file type")

    audio_id = str(uuid.uuid4())
    audio_path = os.path.join(AUDIO_TMP_DIR, f"{audio_id}_{file.filename}")

    try:
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        with open(audio_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                file=audio_file,
                model="gpt-4o-transcribe"
            )

        return {
            "status": "ok",
            "text": result.text
        }

    except Exception:
        return {
            "status": "error",
            "message": "Audio transcription failed",
            "trace": traceback.format_exc()
        }

    finally:
        if os.path.exists(audio_path):
            os.remove(audio_path)


@router.post("/transcribe-url")
def transcribe_audio_from_url(req: AudioURLRequest):
    """
    CDN URL → stream → OpenAI
    NO file upload, NO /tmp write
    """
    try:
        if not req.audio_url:
            raise HTTPException(status_code=400, detail="audio_url or URL required")

        # Clean accidental "=" from n8n
        url = req.audio_url.lstrip("=")

        # Fetch CDN audio safely (handles Supabase + chunked transfer)
        r = requests.get(
            url,
            stream=True,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r.raise_for_status()

        # Rebuild audio stream correctly
        audio_buffer = io.BytesIO()
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                audio_buffer.write(chunk)

        audio_buffer.seek(0)

        # 🔥 CRITICAL: filename with extension
        audio_buffer.name = "audio.wav"

        # Optional sanity check
        if audio_buffer.getbuffer().nbytes < 10_000:
            raise RuntimeError("Downloaded audio is too small or invalid")

        result = client.audio.transcriptions.create(
            file=audio_buffer,
            model="gpt-4o-transcribe"
        )

        return {
            "status": "ok",
            "text": result.text
        }

    except Exception:
        return {
            "status": "error",
            "message": "CDN audio transcription failed",
            "trace": traceback.format_exc()
        }
