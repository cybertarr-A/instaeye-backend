import os
import uuid
import shutil
import traceback
from fastapi import APIRouter, UploadFile, File, HTTPException
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

router = APIRouter(
    prefix="/audio",
    tags=["audio"]
)

# ============================
# ROUTES
# ============================

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Mini audio transcriber.
    Designed for short audio (~5 seconds).
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid audio file type")

    audio_id = str(uuid.uuid4())
    audio_path = os.path.join(AUDIO_TMP_DIR, f"{audio_id}_{file.filename}")

    try:
        # Save audio temporarily
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Transcribe via OpenAI
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
