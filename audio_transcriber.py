import os
import io
import traceback
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI

# ============================
# CONFIG
# ============================

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

client = OpenAI(api_key=OPENAI_API_KEY)

router = APIRouter(prefix="/audio", tags=["audio"])

# ============================
# REQUEST MODEL
# ============================

class AudioURLRequest(BaseModel):
    audio_url: str

# ============================
# ROUTE
# ============================

@router.post("/transcribe-url")
def transcribe_audio_from_url(req: AudioURLRequest):
    try:
        r = requests.get(
            req.audio_url,
            stream=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r.raise_for_status()

        audio_bytes = io.BytesIO(r.content)
        audio_bytes.name = "audio.mp3"  # required by OpenAI SDK

        result = client.audio.transcriptions.create(
            file=audio_bytes,
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
