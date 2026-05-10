"""
news.py - News briefing for FRIDAY
Uses NewsAPI (free tier: 100 requests/day).

Setup:
  1. Get free API key: https://newsapi.org/register
  2. Set NEWSAPI_KEY in config.py
  3. Set NEWS_COUNTRY in config.py (e.g. "in" for India, "us" for USA)

Voice commands (handled in commands.py):
  "Give me today's news"
  "What's in the news?"
  "News headlines"
  "Tech news"
  "Sports news"
  "Business news"
"""

import requests
from config import NEWSAPI_KEY, NEWS_COUNTRY

BASE_URL = "https://newsapi.org/v2"


def _available() -> bool:
    return bool(NEWSAPI_KEY and not NEWSAPI_KEY.startswith("YOUR_"))


def get_headlines(category: str = "general", count: int = 5) -> str:
    """Return spoken top headlines for a category."""
    if not _available():
        return ("News is not configured. "
                "Get a free API key at newsapi.org and set "
                "NEWSAPI_KEY in config.py.")

    VALID_CATEGORIES = ["business", "entertainment", "general",
                        "health", "science", "sports", "technology"]
    if category not in VALID_CATEGORIES:
        category = "general"

    try:
        resp = requests.get(
            f"{BASE_URL}/top-headlines",
            params={
                "country":  NEWS_COUNTRY,
                "category": category,
                "pageSize": count,
                "apiKey":   NEWSAPI_KEY
            },
            timeout=8
        )
        if resp.status_code == 401:
            return "Invalid NewsAPI key. Check NEWSAPI_KEY in config.py."
        resp.raise_for_status()

        articles = resp.json().get("articles", [])
        if not articles:
            return f"No {category} news found right now."

        cat_label = category.title()
        intro     = f"Here are the top {cat_label} headlines. "
        lines = []
        for i, a in enumerate(articles[:count], 1):
            title  = a.get("title",  "").split(" - ")[0].strip()
            source = a.get("source", {}).get("name", "")
            if title:
                lines.append(f"Number {i}: {title}. Source: {source}.")

        return intro + " ".join(lines)

    except requests.exceptions.ConnectionError:
        return "No internet connection for news."
    except Exception as e:
        return f"News error: {e}"


def get_topic_news(topic: str, count: int = 3) -> str:
    """Search news for a specific topic."""
    if not _available():
        return "News API not configured."

    try:
        resp = requests.get(
            f"{BASE_URL}/everything",
            params={
                "q":        topic,
                "language": "en",
                "pageSize": count,
                "sortBy":   "publishedAt",
                "apiKey":   NEWSAPI_KEY
            },
            timeout=8
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])

        if not articles:
            return f"No recent news found about '{topic}'."

        lines = [f"Here's what I found about {topic}."]
        for i, a in enumerate(articles[:count], 1):
            title = a.get("title", "").split(" - ")[0].strip()
            if title:
                lines.append(f"{i}: {title}.")

        return " ".join(lines)

    except Exception as e:
        return f"Topic news error: {e}"


# Category keyword -> API category
CATEGORY_MAP = {
    "tech":         "technology",
    "technology":   "technology",
    "sport":        "sports",
    "sports":       "sports",
    "cricket":      "sports",
    "business":     "business",
    "finance":      "business",
    "market":       "business",
    "health":       "health",
    "medical":      "health",
    "science":      "science",
    "entertainment":"entertainment",
    "movies":       "entertainment",
    "bollywood":    "entertainment",
}


def parse_and_fetch(text: str) -> str:
    """Parse voice text and return appropriate news."""
    t = text.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in t:
            return get_headlines(category)
    # Check for topic search: "news about cricket"
    if "about " in t:
        topic = t.split("about ")[-1].strip()
        return get_topic_news(topic)
    return get_headlines("general")


if __name__ == "__main__":
    print(get_headlines("technology", 3))
