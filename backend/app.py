import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    # When run as module: python -m backend.app
    from .searcher import search_web
    from .fact_extractor import extract_facts
    from .trending import get_trending_topics, get_trending_topics_with_images
    from .writer import write_article, write_digest
except ImportError:
    # When run directly: python app.py
    from searcher import search_web
    from fact_extractor import extract_facts
    from trending import get_trending_topics, get_trending_topics_with_images
    from writer import write_article, write_digest

import groq as GroqClient
groq_client = GroqClient.Groq(api_key=os.environ.get("GROQ_API_KEY"))

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup: generate articles if none exist
    if len(load_articles()) == 0:
        print("No articles found. Running auto_publish()...")
        auto_publish()  # Generates 5 articles immediately

    # Schedule: run every 1 hour
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_publish, "interval", hours=1)
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "frontend")), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
ARTICLES_PATH = BASE_DIR / 'articles.json'


class GenerateRequest(BaseModel):
    topic: str


class QARequest(BaseModel):
    article_id: str
    question: str


def load_articles():
    if not ARTICLES_PATH.exists():
        return []
    with open(ARTICLES_PATH, 'r', encoding='utf-8') as handle:
        try:
            data = json.load(handle)
        except json.JSONDecodeError:
            data = []
    return data


def save_articles(articles):
    with open(ARTICLES_PATH, 'w', encoding='utf-8') as handle:
        json.dump(articles, handle, indent=2, ensure_ascii=False)


def save_article(article):
    articles = load_articles()
    articles.append(article)
    save_articles(articles)


def get_article(article_id):
    for article in load_articles():
        if article.get('id') == article_id:
            return article
    return None


def infer_sector(text: str):
    value = (text or '').lower()
    if any(term in value for term in ['ai', 'artificial intelligence', 'machine learning', 'chip', 'semiconductor', 'tech']):
        return 'AI'
    if any(term in value for term in ['economy', 'economic', 'markets', 'inflation', 'trade', 'gdp', 'finance']):
        return 'Economy'
    if any(term in value for term in ['geopolitic', 'diplomacy', 'tension', 'war', 'ambassador', 'treaty', 'border']):
        return 'Geopolitics'
    if any(term in value for term in ['web3', 'crypto', 'blockchain', 'bitcoin', 'ethereum', 'nft', 'decentralized']):
        return 'Web3'
    return 'General'


def get_todays_articles():
    today = datetime.now(timezone.utc).date()
    articles = []
    for article in load_articles():
        published_at = article.get('published_at')
        if not published_at:
            continue
        try:
            published_date = datetime.fromisoformat(published_at.replace('Z', '+00:00')).date()
            if published_date == today:
                articles.append(article)
        except ValueError:
            continue
    return articles


def auto_publish():
    topics = get_trending_topics_with_images()
    for item in topics[:5]:
        try:
            results = search_web(item["topic"])
            facts = extract_facts(results, item["topic"])
            if facts["confidence"] < 0.4:
                continue  # Skip low-confidence topics
            article = write_article(facts, item["topic"], item.get("image_url"))
            save_article(article)
            print(f"Published: {article['headline']}")
        except Exception as e:
            print(f"Failed {item['topic']}: {e}")


@app.get('/')
async def root():
    return FileResponse(BASE_DIR / 'frontend' / 'index.html')


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.get('/articles')
async def articles():
    return load_articles()


@app.get('/articles/{article_id}')
async def article_detail(article_id: str):
    article = get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail='Article not found')
    return article


@app.post('/generate')
async def generate(request: GenerateRequest):
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail='topic is required')

    search_results = search_web(topic)
    fact_graph = extract_facts(search_results, topic)
    article = write_article(fact_graph, topic)
    article_record = {
        'id': str(uuid.uuid4()),
        'topic': topic,
        'headline': article.get('headline'),
        'dek': article.get('dek'),
        'byline': article.get('byline'),
        'body': article.get('body'),
        'sources': fact_graph.get('sources', []),
        'sector': infer_sector(topic),
        'confidence': round(float(fact_graph.get('confidence', 0.0)), 2),
        'sources_count': fact_graph.get('sources_count', len(fact_graph.get('sources', []))),
        'verified_claims': fact_graph.get('verified_claims', 0),
        'fact_count': fact_graph.get('fact_count', 0),
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'fact_graph': fact_graph,
    }
    save_article(article_record)
    return article_record


@app.post("/qa")
async def qa_endpoint(request: QARequest):
    articles = load_articles()
    article = next(
        (a for a in articles if str(a["id"]) == str(request.article_id)),
        None
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    prompt = f"""
    Article: {article["headline"]}
    {article["body"]}

    Question: {request.question}

    Answer in 2-3 sentences. Be specific to the article."""

    response = groq_client.chat.completions.create(
        model="llama-3.1-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    return {"answer": response.choices[0].message.content}


@app.get('/digest')
async def digest():
    articles = get_todays_articles()
    return write_digest(articles)


if __name__ == '__main__':
    import uvicorn

    port = int(os.environ.get('PORT', 5000))
    uvicorn.run('app:app', host='0.0.0.0', port=port, reload=False)
          