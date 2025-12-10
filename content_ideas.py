import os
import json
import requests
from typing import List, Dict, Any

# Get API key from Railway environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise Exception("Missing OPENAI_API_KEY environment variable")

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def generate_content(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generates 10 viral content ideas based on merged analytics data.
    Called directly by FastAPI in main.py.
    """

    try:
        # reduce payload size (250–500k JSON can break the model)
        data_snippet = json.dumps(data)[:15000]

        system_msg = """
You are a Short-Form Content Growth Analyst.

Your job:
Generate EXACTLY 10 content ideas that can rank on Reels, TikTok, and Shorts.
Use real performance patterns from the dataset provided.

Output MUST follow this exact JSON shape:

{
 "ideas": [
   {
     "id": 1,
     "titles": ["..."],
     "script": "...",
     "description": "...",
     "hashtags": ["..."]
   }
 ]
}
"""

        user_msg = f"""
Analyze the performance dataset below and produce 10 highly-optimized,
viral-ready content ideas.

DATA START:
{data_snippet}
DATA END

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

        response = requests.post(OPENAI_URL, json=payload, headers=headers)

        if response.status_code != 200:
            raise Exception(f"OpenAI Error: {response.text}")

        content = response.json()["choices"][0]["message"]["content"]

        # enforce valid JSON
        return json.loads(content)

    except json.JSONDecodeError:
        raise Exception("OpenAI returned invalid JSON")
    except Exception as e:
        raise Exception(str(e))
