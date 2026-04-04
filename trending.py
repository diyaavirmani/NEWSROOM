import os
import re
from dotenv import load_dotenv
import requests

load_dotenv()
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
NEWSAPI_URL = 'https://newsapi.org/v2/top-headlines'


def get_trending_topics(country='in'):
    if not NEWSAPI_KEY:
        raise ValueError('NEWSAPI_KEY is required to fetch trending topics')
    params = {
        'country': country,
        'apiKey': NEWSAPI_KEY,
        'pageSize': 10,
    }
    response = requests.get(NEWSAPI_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    titles = []
    seen = set()
    for article in data.get('articles', []):
        title = article.get('title')
        if not title:
            continue
        cleaned = re.sub(r'\s+', ' ', title).strip()
        key = cleaned.lower()
        if not cleaned or '[removed]' in key or key in seen:
            continue
        seen.add(key)
        titles.append(cleaned)
        if len(titles) >= 10:
            break

    return titles
