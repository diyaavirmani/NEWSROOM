"""
trending.py — fetches India trending topics for Creator's Corner
Primary: NewsAPI top-headlines for India (NEWS_API_KEY)
Fallback: curated list
"""

import os, re, random, requests
from dotenv import load_dotenv

load_dotenv()

NEWS_KEY = os.environ.get('NEWS_API_KEY') or os.environ.get('NEWSAPI_KEY')


def get_trending_topics(limit=8):
    """Returns list of {topic, image_url, source} dicts."""
    topics = _from_newsapi(limit * 2)
    if topics:
        return topics[:limit]
    return _fallback()[:limit]


def get_trending_for_display(limit=6):
    """Formatted for Creator's Corner UI."""
    topics = get_trending_topics(limit * 2)
    seen, result = set(), []
    for t in topics:
        k = t['topic'].lower()[:30]
        if k not in seen:
            seen.add(k)
            result.append({
                'topic':   t['topic'],
                'platform': t.get('source', 'NewsAPI India'),
                'views':   'Trending now',
                'image_url': t.get('image_url')
            })
        if len(result) >= limit:
            break
    return result


def _from_newsapi(limit):
    if not NEWS_KEY:
        print("[trending] NEWS_API_KEY not set — using fallback")
        return []
    try:
        resp = requests.get(
            'https://newsapi.org/v2/top-headlines',
            params={'country':'in','apiKey':NEWS_KEY,'pageSize':limit},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        topics, seen = [], set()
        for a in data.get('articles',[]):
            title = (a.get('title') or '').strip()
            if not title or '[removed]' in title.lower():
                continue
            # Strip source attribution like " - Reuters" at end
            clean = re.sub(r'\s*[-–]\s*\S+$', '', title).strip()
            if not clean or clean.lower() in seen:
                continue
            seen.add(clean.lower())
            topics.append({
                'topic':     clean,
                'image_url': a.get('urlToImage'),
                'source':    a.get('source',{}).get('name','NewsAPI')
            })
        print(f"[trending] NewsAPI returned {len(topics)} topics")
        return topics
    except Exception as e:
        print(f"[trending] NewsAPI error: {e}")
        return []


def _fallback():
    return [
        {'topic':'India AI Policy 2026','image_url':None,'source':'Curated'},
        {'topic':'RBI Interest Rate Decision','image_url':None,'source':'Curated'},
        {'topic':'OpenAI GPT-5 Release','image_url':None,'source':'Curated'},
        {'topic':'India Pakistan Relations 2026','image_url':None,'source':'Curated'},
        {'topic':'Delhi Water Crisis','image_url':None,'source':'Curated'},
        {'topic':'ISRO Gaganyaan Mission','image_url':None,'source':'Curated'},
        {'topic':'Ethereum Pectra Upgrade','image_url':None,'source':'Curated'},
        {'topic':'India Semiconductor Industry','image_url':None,'source':'Curated'},
    ]
