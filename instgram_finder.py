import os
import requests
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search.json"
GOOGLE_ENGINE = "google"

if not SERPAPI_KEY:
    raise RuntimeError("SERPAPI_KEY not set")

app = FastAPI(
    title="Instagram Lead Finder",
    version="1.0.0"
)

# --------------------------------------------------
# REQUEST MODEL (JSON INPUT)
# --------------------------------------------------

class SearchRequest(BaseModel):
    keywords: List[str]
    page: int = 0
    num_results: int = 10


# --------------------------------------------------
# QUERY BUILDER
# --------------------------------------------------

def build_query(keywords: List[str]) -> str:
    keyword_block = " OR ".join(f'"{k}"' for k in keywords)
    return f"site:instagram.com ({keyword_block})"


# --------------------------------------------------
# SERPAPI CALL
# --------------------------------------------------

def run_search(keywords: List[str], page: int, num_results: int) -> Dict:
    query = build_query(keywords)

    params = {
        "engine": GOOGLE_ENGINE,
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": num_results,
        "start": page * num_results
    }

    response = requests.get(SERPAPI_URL, params=params, timeout=30)

    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail="SerpAPI request failed"
        )

    return response.json()


# --------------------------------------------------
# RESULT NORMALIZER
# --------------------------------------------------

def extract_accounts(serp_data: Dict) -> List[Dict]:
    accounts = []

    for item in serp_data.get("organic_results", []):
        link = item.get("link", "")

        if "instagram.com" not in link:
            continue

        profile_url = link.split("?")[0].rstrip("/")

        accounts.append({
            "platform": "instagram",
            "profile_url": profile_url,
            "title": item.get("title"),
            "snippet": item.get("snippet")
        })

    return accounts


# --------------------------------------------------
# API ENDPOINT
# --------------------------------------------------

@app.post("/search")
def search_instagram_accounts(payload: SearchRequest):
    serp_data = run_search(
        keywords=payload.keywords,
        page=payload.page,
        num_results=payload.num_results
    )

    accounts = extract_accounts(serp_data)

    return {
        "query_used": build_query(payload.keywords),
        "total_found": len(accounts),
        "accounts": accounts
    }


# --------------------------------------------------
# RAILWAY ENTRYPOINT
# --------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
