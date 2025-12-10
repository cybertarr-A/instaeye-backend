import os
import time
import requests
from datetime import datetime
from typing import List, Dict, Any
from pytrends.request import TrendReq

# Pull this from Railway later (optional)
DEFAULT_NEWS_API_KEY = os.getenv("NEWS_API_KEY")

TIMEFRAME = "now 14-d"
GEO = "US"

# Reuse a single pytrends session
pytrends = TrendReq(
    hl="en-US",
    tz=360,
    retries=3,
    backoff_factor=0.3
)


# -----------------------------------
# Google Trends Analyzer
# -----------------------------------
def analyze_trend(keyword: str) -> Dict[str, Any]:
    try:
        time.sleep(2)  # avoid Google rate-limit

        pytrends.build_payload(
            kw_list=[keyword],
            timeframe=TIMEFRAME,
            geo=GEO
        )

        df = pytrends.interest_over_time()

        if df.empty:
            return {
                "direction": "no_data",
                "score_percent": 0,
                "latest_interest": 0
            }

        values = df[keyword].tolist()
        start, end = values[0], values[-1]

        # Determine direction
        if end > start:
            direction = "rising"
        elif end < start:
            direction = "falling"
            direction = "falling"
        else:
            direction = "stable"

        # Percent growth
        score = round(((end - start) / max(start, 1)) * 100, 2)

        return {
            "direction": direction,
            "score_percent": score,
            "latest_interest": end
        }

    except Exception as e:
        return {
            "direction": "error",
            "score_percent": 0,
            "latest_interest": 0,
            "message": str(e)
        }


# -----------------------------------
# News API Analyzer
# -----------------------------------
def fetch_news(keyword: str, api_key: str) -> Dict[str, Any]:
    """Fetch recent news headlines for a keyword."""
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": keyword,
        "apiKey": api_key,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5
    }

    resp = requests.get(url, params=params)

    if resp.status_code != 200:
        return {"count": 0, "headlines": {"list": []}}

    articles = resp.json().get("articles", [])
    headlines = [a.get("title") for a in articles]

    return {
        "count": len(headlines),
        "headlines": {"list": headlines}
    }


# -----------------------------------
# MAIN FUNCTION FOR FASTAPI
# -----------------------------------
def analyze_industry(keywords: List[str], news_api_key: str = None) -> Dict[str, Any]:
    """
    Master function called by the main FastAPI backend.
    Performs trends + news for each keyword.
    """

    if not news_api_key:
        news_api_key = DEFAULT_NEWS_API_KEY  # fallback to ENV VAR

    results = []
    timestamp = datetime.utcnow().isoformat()

    for keyword in keywords:
        trend = analyze_trend(keyword)
        news = fetch_news(keyword, news_api_key)

        results.append({
            "industry": keyword,
            "timestamp": timestamp,
            "trend_analysis": trend,
            "news_analysis": news
        })

    return {
        "system": "Industry Intelligence Engine",
        "timeframe": TIMEFRAME,
        "source": {
            "providers": ["Google Trends", "NewsAPI"]
        },
        "results": results
    }
