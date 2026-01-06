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
    Pull transcript_text if present in merged dataset.
    Keeps system backward-compatible.
    """
    transcripts = []

    for item in data:
        if not isinstance(item, dict):
            continue

        if item.get("source") == "reel_audio_transcript":
            text = item.get("transcript_text") or item.get("transcript")
            if text and isinstance(text, str):
                transcripts.append(text.strip())

    return transcripts


def generate_content(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generates EXACTLY 10 viral content ideas by analyzing
    the FULL merged dataset coming from the Merge node.
    """

    try:
        # ---- Extract spoken audio intelligence (if present) ----
        transcripts = _extract_transcripts(data)

        transcript_block = ""
        if transcripts:
            joined = "\n\n---\n\n".join(transcripts[:3])
            transcript_block = f"""
SPOKEN AUDIO INTELLIGENCE (transcript_text):

The following text comes from REAL SPOKEN AUDIO extracted from Instagram Reels.
This is NOT caption text.

Use it to infer:
- Spoken hook phrasing
- Verbal pacing and rhythm
- Emotional tone in voice
- CTA language that is actually said

TRANSCRIPT_TEXT START:
{joined}
TRANSCRIPT_TEXT END
"""

        # ---- Include FULL merged dataset (not just snippets) ----
        data_snippet = json.dumps(data)[:12000]

        # ---- SYSTEM PROMPT (MERGE-NODE AWARE) ----
        system_msg = f"""
You are a Senior Instagram Growth Intelligence Engine.

You receive a MERGED dataset from an automation workflow.
The dataset may include:
- Post-level performance metrics (likes, shares, plays, reach, engagement_rate)
- Captions, hashtags, posting times
- Video analysis (structure, pacing, format)
- Image analysis (visual theme, emotion, composition)
- Audio analysis with transcript_text (spoken words)
- Industry and niche trend analysis
- Brand and audience persona context

Your task is to analyze ALL of this data holistically
before generating any ideas.

Core priorities:
1. What patterns actually correlate with high performance
2. Spoken audio hooks and phrasing if transcript_text exists
3. Repeated emotional, narrative, and structural patterns
4. Visual vs audio dominance
5. Alignment with audience intent and niche trends

Do NOT summarize the data.
Do NOT describe the dataset.
USE it to infer what the algorithm is rewarding.
"""

        # ---- USER PROMPT (FORCE FULL-MERGE ANALYSIS) ----
        user_msg = f"""
Analyze the FULL merged dataset below.

Your goal:
Infer what type of content is currently winning
for THIS niche, THIS audience, and THIS data.

If transcript_text is present:
- Treat it as ground-truth spoken language
- Optimize hooks for how they SOUND, not how they read

{transcript_block}

MERGED DATASET:
{data_snippet}

After analysis, generate EXACTLY 10 Instagram Reel ideas.

Each idea MUST include:
- 3 spoken-style titles
- A short spoken-first script
- A description aligned with inferred intent
- Relevant hashtags based on detected patterns

Return ONLY valid JSON in this format:

{{
  "ideas": [
    {{
      "id": 1,
      "titles": ["...", "...", "..."],
      "script": "...",
      "description": "...",
      "hashtags": ["..."]
    }}
  ]
}}
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

        response = requests.post(
            OPENAI_URL,
            json=payload,
            headers=headers,
            timeout=60
        )

        if response.status_code != 200:
            raise Exception(f"OpenAI Error: {response.text}")

        content = response.json()["choices"][0]["message"]["content"]

        return json.loads(content)

    except json.JSONDecodeError:
        raise Exception("OpenAI returned invalid JSON")
    except Exception as e:
        raise Exception(str(e))
