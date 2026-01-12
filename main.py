from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Any, Optional
import traceback

from instagram_analyzer import analyze_profiles
from content_ideas import generate_content
from image_analyzer import analyze_image
from video_analyzer import analyze_reel
from top_posts import get_top_posts
from trend_engine import analyze_industry

# 🔥 AUDIO PIPELINE
from audio_pipeline import process_reel

# 🔥 HOOK ANALYZER ROUTER (NEW)
from hook_analyzer import router as hook_router


app = FastAPI(title="InstaEye Backend", version="1.1")


# ============================
# REQUEST MODELS
# ============================

class AnalyzeProfilesRequest(BaseModel):
    usernames: List[str]


class ContentIdeasRequest(BaseModel):
    data: List[Any]


class ImageAnalyzeRequest(BaseModel):
    media_url: str


class ReelAnalyzeRequest(BaseModel):
    video_url: Optional[str] = None
    media_url: Optional[str] = None
    url: Optional[str] = None
    reel_url: Optional[str] = None


class ReelAudioRequest(BaseModel):
    media_url: str


class TopPostsRequest(BaseModel):
    username: str
    limit: int = 5


class IndustryAnalyzeRequest(BaseModel):
    keywords: List[str]
    news_api_key: Optional[str] = None


# ============================
# ROUTES
# ============================

@app.get("/")
def home():
    return {"status": "InstaEye backend running"}


# 1️⃣ Main Instagram Analyzer
@app.post("/analyze")
def analyze_profile_api(req: AnalyzeProfilesRequest):
    return analyze_profiles(req.usernames)


# 2️⃣ Image Analyzer
@app.post("/analyze-image")
def analyze_image_api(req: ImageAnalyzeRequest):
    return analyze_image(req.media_url)


# 3️⃣ Reel/Video Analyzer
@app.post("/analyze-reel")
def analyze_reel_api(req: ReelAnalyzeRequest):
    url = req.video_url or req.media_url or req.url or req.reel_url
    if not url:
        return {
            "status": "error",
            "message": "No video URL provided"
        }
    return analyze_reel(url)


# 🔥 3.5️⃣ Reel Audio → Transcript → Analysis
@app.post("/analyze-reel-audio")
def analyze_reel_audio_api(req: ReelAudioRequest):
    try:
        result = process_reel(req.media_url)
        return result

    except Exception as e:
        print("AUDIO PIPELINE ERROR:")
        traceback.print_exc()

        return {
            "status": "error",
            "stage": "audio_pipeline",
            "message": str(e)
        }


# 4️⃣ Trend Industry Engine
@app.post("/analyze-industry")
def analyze_industry_api(req: IndustryAnalyzeRequest):
    return analyze_industry(req.keywords, req.news_api_key)


# 5️⃣ Company Top Posts
@app.post("/top-posts")
def top_posts_api(req: TopPostsRequest):
    return get_top_posts(req.username, req.limit)


# 6️⃣ AI Content Generator
@app.post("/generate-content-ideas")
def generate_ideas_api(req: ContentIdeasRequest):
    return generate_content(req.data)


# ============================
# 🔥 HOOK ANALYZER ROUTES
# ============================

# This adds:
# POST /analyze-hook
# (from hook_analyzer.py)

app.include_router(hook_router)
