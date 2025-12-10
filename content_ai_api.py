import requests
import json
from typing import List, Dict, Any

# IMPORTANT:
# Move your API key to Railway ENV VARIABLES later
OPENAI_API_KEY = "sk-proj-your-key-here"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"


def generate_content(data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Main function called by FastAPI server.
    Accepts merged analytics data from n8n.
    Returns JSON content ideas.
    """

    try:
        # Prevent token overload by trimming
        data_snippet = json.dumps(data)[:15000]

        system_msg = """
You are a Short-Form Content Growth Analyst.

YOUR GOAL:
Create EXACTLY 10 content ideas that will rank in Reels, Shorts, and TikTok,
by strictly analyzing the performance patterns inside the data provided.

YOU MUST EXTRACT:
• Topic patterns connected to highest engagement
• Hook structures that retain viewers in first 3 seconds
• Visual formats (facecam / text-only / b-roll / product / meme / reaction)
• Emotional triggers (fear, speed, power, humor, curiosity)
• Call-to-action styles that convert

OUTPUT RULES:
Return ONLY valid JSON with this EXACT structure:

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
Analyze performance data and produce 10 unique, viral-ready content ideas.

DATA START:
{data_snippet}
DATA END

Return ONLY JSON. No explanation.
"""

        payload = {
            "model": "gpt-4.1-mini",
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.95
        }

        response = requests.post(
            OPENAI_URL,
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.status_code != 200:
            raise Exception(response.text)

        raw = response.json()
        message_content = raw["choices"][0]["message"]["content"]

        # Must be valid JSON
        generated = json.loads(message_content)

        return generated

    except json.JSONDecodeError:
        raise Exception("Invalid JSON returned from OpenAI")
    except Exception as e:
        raise Exception(str(e))
