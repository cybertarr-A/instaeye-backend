import os
import json
import requests
from typing import List, Dict, Any

# Get API key from Railway environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise Exception("Missing OPENAI_API_KEY environment variable")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def _extract_transcripts(data: List[Dict[str, Any]]) -> List[str]:
    """
    Pull transcript text if present in merged dataset.
    Keeps system backward-compatible.
    """
    transcripts = []

    for item in data:
        if not isinstance(item, dict):
            continue

        # Our normalized transcript object
        if item.get("source") == "reel_audio_transcript":
            text = item.get("transcript")
            if text and isinstance(text, str):
                transcripts.append(text.strip())

    return transcripts


def generate_content(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generates EXACTLY 10 viral content ideas based on merged analytics data,
    now enhanced with spoken-reel transcript intelligence (if available).
    """

    try:
        # ---- Extract transcript intelligence (NEW) ----
        transcripts = _extract_transcripts(data)

        transcript_block = ""
        if transcripts:
            joined = "\n\n---\n\n".join(transcripts[:3])  # limit noise
            transcript_block = f"""
IMPORTANT SPOKEN REEL TRANSCRIPTS:
These are real words spoken in high-performing reels.
Use them to identify hooks, narrative styles, pacing, and CTA language.

TRANSCRIPTS START:
{joined}
TRANSCRIPTS END
"""

        # ---- Reduce payload size (unchanged) ----
        data_snippet = json.dumps(data)[:12000]

        # ---- SYSTEM PROMPT (slightly upgraded) ----
        system_msg = f"""
You are a Senior Content Growth Analyst.

Your job:
Generate EXACTLY 10 Instagram Reel content ideas that can realistically rank.

Rules:
- Use real performance patterns from the dataset
- Prioritize SPOKEN hooks if transcripts are provided
- Strong first 3 seconds are critical
- Make 3 titles per idea
- Ideas should be practical, viral, and human-sounding

Output MUST follow this exact JSON shape:

{{
 "ideas": [
   {{
     "id": 1,
     "titles": ["..."],
     "script": "...",
     "description": "...",
     "hashtags": ["..."]
   }}
 ]
}}
"""

        # ---- USER PROMPT (enhanced but safe) ----
        user_msg = f"""
Analyze the dataset below and produce 10 highly-optimized,
viral-ready Instagram Reel ideas.

{transcript_block}

GENERAL PERFORMANCE DATA:
{data_snippet}

Return ONLY JSON. No explanation.
"""

        payload = {
            "model": "gpt-4.1-mini",
            "temperature": 0.95,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
        }

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.post(OPENAI_URL, json=payload, headers=headers, timeout=60)

        if response.status_code != 200:
            raise Exception(f"OpenAI Error: {response.text}")

        content = response.json()["choices"][0]["message"]["content"]

        # Enforce valid JSON
        return json.loads(content)

    except json.JSONDecodeError:
        raise Exception("OpenAI returned invalid JSON")
    except Exception as e:
        raise Exception(str(e))
