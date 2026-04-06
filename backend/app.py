"""
app.py - The Pulse Gazette / Veritas Backend
FastAPI server with auto-publishing, Q&A, trending, and digest endpoints.

How to run locally:
    uvicorn app:app --reload --port 5000

How Render runs it:
    uvicorn app:app --host 0.0.0.0 --port $PORT
"""

import os
import json
import uuid
import time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── IMPORT OUR MODULES ────────────────────────────────────────────────────────
# Each import is wrapped in try/except so one missing module
# does NOT crash the whole server.

try:
    from searcher import search_web
    print("[app.py] searcher.py loaded OK")
except ImportError as e:
    print(f"[app.py] WARNING: searcher.py not found: {e}")
    def search_web(topic): return []

try:
    from fact_extractor import extract_facts
    print("[app.py] fact_extractor.py loaded OK")
except ImportError as e:
    print(f"[app.py] WARNING: fact_extractor.py not found: {e}")
    def extract_facts(results, topic):
        return {'facts': [], 'sources': [], 'sources_count': 0,
                'confidence': 0.75, 'verified_claims': 0, 'entities': [topic]}

try:
    from writer import write_article
    print("[app.py] writer.py loaded OK")
except ImportError as e:
    print(f"[app.py] WARNING: writer.py not found: {e}")
    def write_article(facts, topic, image_url=None):
        return {
            'id': str(uuid.uuid4()), 'headline': topic,
            'dek': 'Article generation module not configured.',
            'body': 'Please configure the writer.py module with a Groq API key.',
            'sector': 'General', 'confidence': 0.0,
            'sources': [], 'sources_count': 0, 'verified_claims': 0,
            'image_url': image_url, 'timestamp': datetime.now().isoformat()
        }

try:
    from trending import get_trending_for_display, get_trending_topics
    print("[app.py] trending.py loaded OK")
except ImportError as e:
    print(f"[app.py] WARNING: trending.py not found: {e}")
    def get_trending_for_display(limit=6):
        return [{'topic': 'India AI Policy', 'platform': 'Google Trends', 'views': '24M'}]
    def get_trending_topics(limit=8):
        return [{'topic': 'India AI Policy 2026', 'image_url': None}]


# ── ARTICLES DATABASE ─────────────────────────────────────────────────────────
# Simple JSON file as our database. For production use PostgreSQL.

ARTICLES_FILE = 'articles.json'


def load_articles():
    """Load all articles from JSON file. Returns empty list if file missing."""
    try:
        if os.path.exists(ARTICLES_FILE):
            with open(ARTICLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('articles', [])
    except Exception as e:
        print(f"[app.py] Error loading articles: {e}")
    return []


def save_article(article: dict):
    """Append one article to the JSON file."""
    try:
        articles = load_articles()
        # Avoid duplicates by headline
        existing_headlines = {a.get('headline', '') for a in articles}
        if article.get('headline') in existing_headlines:
            print(f"[app.py] Skipping duplicate: {article['headline'][:60]}")
            return
        articles.insert(0, article)      # newest first
        articles = articles[:100]         # keep max 100 articles
        with open(ARTICLES_FILE, 'w', encoding='utf-8') as f:
            json.dump({'articles': articles}, f, ensure_ascii=False, indent=2)
        print(f"[app.py] Saved: {article.get('headline', 'Untitled')[:60]}")
    except Exception as e:
        print(f"[app.py] Error saving article: {e}")


# ── AUTO-PUBLISH ──────────────────────────────────────────────────────────────

def auto_publish(max_articles=5):
    """
    Fetches trending topics and generates articles for each.
    Called on startup and every hour by APScheduler.
    """
    print(f"\n[auto_publish] Starting at {datetime.now().strftime('%H:%M:%S')}")
    try:
        topics = get_trending_topics(limit=max_articles * 2)
    except Exception as e:
        print(f"[auto_publish] Failed to fetch topics: {e}")
        return

    published = 0
    for item in topics:
        if published >= max_articles:
            break
        topic = item.get('topic', '')
        image_url = item.get('image_url')
        if not topic:
            continue
        try:
            print(f"[auto_publish] Processing: {topic[:60]}")
            results = search_web(topic)
            if not results:
                print(f"[auto_publish] No search results for: {topic}")
                continue
            facts = extract_facts(results, topic)
            if facts.get('confidence', 0) < 0.3:
                print(f"[auto_publish] Low confidence ({facts['confidence']:.2f}), skipping: {topic}")
                continue
            article = write_article(facts, topic, image_url)
            save_article(article)
            published += 1
            time.sleep(2)   # Be gentle with APIs
        except Exception as e:
            print(f"[auto_publish] Failed for '{topic}': {e}")

    print(f"[auto_publish] Done. Published {published} articles.\n")


# ── LIFESPAN ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on server startup and shutdown.
    - Startup: generate articles if none exist, start hourly scheduler
    - Shutdown: stop scheduler cleanly
    """
    print("\n[lifespan] Server starting up...")

    # Generate articles on startup if feed is empty
    existing = load_articles()
    if len(existing) == 0:
        print("[lifespan] No articles found. Running initial auto_publish...")
        try:
            auto_publish(max_articles=5)
        except Exception as e:
            print(f"[lifespan] Startup auto_publish failed: {e}")
    else:
        print(f"[lifespan] Found {len(existing)} existing articles. Skipping initial publish.")

    # Start hourly scheduler
    scheduler = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(auto_publish, 'interval', hours=1, args=[3])
        scheduler.start()
        print("[lifespan] Scheduler started — will auto-publish every hour.")
    except ImportError:
        print("[lifespan] apscheduler not installed. Add 'apscheduler' to requirements.txt.")

    yield   # Server is now running

    # Shutdown
    if scheduler:
        scheduler.shutdown()
        print("[lifespan] Scheduler stopped.")
    print("[lifespan] Server shutting down.")


# ── APP ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Veritas — AI Newsroom API",
    description="Backend for Veritas, an AI-native newsroom. Auto-publishes from Google Trends.",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # Allow all origins (fine for hackathon)
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REQUEST MODELS ────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic: str
    source: Optional[str] = None    # e.g. 'virlo_trend', 'manual', 'auto'

class QARequest(BaseModel):
    question: str
    article_id: Optional[str] = None


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.get('/')
async def serve_frontend():
    return FileResponse('frontend/index.html')


@app.get('/health')
async def health():
    """Health check — Render uses this to verify server is alive."""
    articles = load_articles()
    return {
        'status': 'ok',
        'articles_count': len(articles),
        'timestamp': datetime.now().isoformat(),
        'groq_configured': bool(os.environ.get('GROQ_API_KEY')),
        'tavily_configured': bool(os.environ.get('TAVILY_API_KEY')),
    }


@app.get('/articles')
async def get_articles():
    """Returns all published articles, newest first."""
    articles = load_articles()
    return {'articles': articles, 'count': len(articles)}


@app.post('/generate')
async def generate_article(request: GenerateRequest):
    """
    Generates a full article for a given topic.
    Pipeline: topic → Tavily search → fact extraction → Groq writing → save → return
    """
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail='Topic cannot be empty')

    try:
        # Step 1: Search the web
        results = search_web(topic)
        if not results:
            raise HTTPException(status_code=503, detail='No search results found. Check TAVILY_API_KEY.')

        # Step 2: Extract facts
        facts = extract_facts(results, topic)

        # Step 3: Write article
        article = write_article(facts, topic)

        # Mark if sourced from trending signal
        if request.source == 'trend':
            article['trend_sourced'] = True
            article['trend_label'] = 'Discovered via Google Trends'

        # Step 4: Save
        save_article(article)

        return article

    except HTTPException:
        raise
    except Exception as e:
        print(f"[/generate] Error: {e}")
        raise HTTPException(status_code=500, detail=f'Article generation failed: {str(e)}')


@app.post('/qa')
async def qa_endpoint(request: QARequest):
    """
    Answers a reader's question about an article using Groq.
    If article_id is provided, answers in context of that article.
    If not, answers the question generally.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail='Question cannot be empty')

    context = ""
    if request.article_id:
        articles = load_articles()
        article = next((a for a in articles if str(a.get('id', '')) == str(request.article_id)), None)
        if article:
            context = f"Article: {article.get('headline', '')}\n\n{article.get('body', '')}\n\n"

    prompt = f"""{context}Reader question: {question}

Answer directly and specifically in 2-3 sentences. 
If given an article context, base your answer on it.
Be informative and journalistic in tone."""

    try:
        import groq
        client = groq.Groq(
            api_key=os.environ.get('GROQ_API_KEY', 'dummy_key'),
            base_url="https://openrouter.ai/api/v1"
        )
        response = client.chat.completions.create(
            model='meta-llama/llama-3.1-70b-instruct',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=300
        )
        answer = response.choices[0].message.content.strip()
        return {'answer': answer}

    except ImportError:
        raise HTTPException(status_code=503, detail='Groq not installed. Add groq to requirements.txt.')
    except Exception as e:
        raise HTTPException(status_code=503, detail=f'Q&A unavailable: {str(e)}')


@app.post('/digest')
async def generate_digest():
    """
    Returns a morning briefing — top 5 articles as a numbered digest.
    Uses Groq to write punchy one-line summaries.
    """
    articles = load_articles()
    if not articles:
        return {'items': [{'text': 'No articles published yet. The bureau is warming up.'}]}

    top = articles[:5]

    try:
        import groq
        client = groq.Groq(
            api_key=os.environ.get('GROQ_API_KEY', 'dummy_key'),
            base_url="https://openrouter.ai/api/v1"
        )
        summaries_prompt = "Summarize each headline + dek in one punchy sentence each (max 20 words). Return as JSON array of strings:\n\n"
        for a in top:
            summaries_prompt += f"- {a.get('headline', '')}: {a.get('dek', '')}\n"

        response = client.chat.completions.create(
            model='meta-llama/llama-3.1-70b-instruct',
            messages=[{'role': 'user', 'content': summaries_prompt}],
            max_tokens=400
        )
        raw = response.choices[0].message.content.strip()
        # Clean up JSON
        raw = raw.replace('```json', '').replace('```', '').strip()
        summaries = json.loads(raw)
        return {'items': [{'text': s} for s in summaries[:5]]}
    except Exception:
        # Fallback: headline + first 60 chars of dek
        items = []
        for a in top:
            headline = a.get('headline', '')
            dek = a.get('dek', '')
            text = headline + (f' — {dek[:60]}…' if dek else '')
            items.append({'text': text})
        return {'items': items}


@app.get('/trends')
async def get_trends():
    """
    Returns today's trending topics from Google Trends (India).
    Used by Creator's Corner in the frontend.
    Replaces Virlo API — 100% free.
    """
    try:
        trends = get_trending_for_display(limit=6)
        return {'trends': trends, 'source': 'google_trends_india'}
    except Exception as e:
        return {
            'trends': [
                {'topic': 'India AI Policy 2026', 'platform': 'Google Trends', 'views': '24.2M'},
                {'topic': 'RBI Rate Decision', 'platform': 'Google Trends', 'views': '9.3M'},
                {'topic': 'OpenAI Latest News', 'platform': 'Google Trends', 'views': '41.5M'},
                {'topic': 'India Pakistan 2026', 'platform': 'Google Trends', 'views': '88.1M'},
                {'topic': 'ISRO 2026 Mission', 'platform': 'Google Trends', 'views': '18.7M'},
                {'topic': 'Ethereum Web3 India', 'platform': 'Google Trends', 'views': '12.3M'},
            ],
            'source': 'fallback'
        }


# ── LOCAL DEV ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 5000))
    uvicorn.run('app:app', host='0.0.0.0', port=port, reload=False)