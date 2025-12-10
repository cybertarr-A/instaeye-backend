from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Any, Optional

from instagram_analyzer import analyze_profiles
from content_ideas import generate_content
from image_analyzer import analyze_image
from video_analyzer import analyze_reel
from top_posts import get_top_posts
from trend_engine import analyze_industry
   # if this handles main IG analyze

app = FastAPI()

@app.get("/")
def home():
    return {"status": "InstaEye backend running"}

# 1️⃣ Main Instagram Analyzer (used at port 8080)
@app.post("/analyze")
def analyze_profile_api(data: dict):
    return analyze_profile(data)

# 2️⃣ Image Analyzer (9090)
@app.post("/analyze-image")
def analyze_image_api(data: dict):
    return analyze_image(data)

# 3️⃣ Reel/Video Analyzer (9092)
@app.post("/analyze-reel")
def analyze_reel_api(data: dict):
    return analyze_video(data)

# 4️⃣ Trend Industry Engine (7100)
@app.post("/analyze-industry")
def analyze_industry_api(data: dict):
    return analyze_trend(data)

# 5️⃣ Company Top Posts (7101)
@app.post("/top-posts")
def top_posts_api(data: dict):
    return get_top_posts(data)

# 6️⃣ AI Content Generator (5050)
@app.post("/generate-content-ideas")
def generate_ideas_api(data: dict):
    return generate_content(data)
