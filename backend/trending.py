import os
import re
from dotenv import load_dotenv
import requests

load_dotenv()
NEWS_API_KEY = os.environ.get('NEWS_API_KEY') or os.environ.get('NEWSAPI_KEY')
NEWSAPI_URL = 'https://newsapi.org/v2/top-headlines'


def get_trending_topics(limit=8, country='in'):
    topics = get_trending_topics_with_images(country=country)
    return topics[:limit]

def get_trending_topics_with_images(country='in'):
    if not NEWS_API_KEY:
        print('NEWS_API_KEY is missing. Returning empty trending topics.')
        return []
    params = {
        'country': country,
        'apiKey': NEWS_API_KEY,
        'pageSize': 10,
    }
    response = requests.get(NEWSAPI_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    topics = []
    seen = set()
    for article in data.get('articles', []):
        title = article.get('title', '')
        if not title or '[removed]' in title.lower():
            continue
        cleaned = re.sub(r'\s+', ' ', title).strip()
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        topics.append({
            "topic": cleaned,
            "image_url": article.get('urlToImage'),
            "source": article.get('source', {}).get('name', '')
        })
        if len(topics) >= 10:
            break

    return topics
