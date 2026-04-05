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
    from .trending import get_trending_topics
    from .writer import answer_question, write_article, write_digest
except ImportError:
    # When run directly: python app.py
    from searcher import search_web
    from fact_extractor import extract_facts
    from trending import get_trending_topics
    from writer import answer_question, write_article, write_digest

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup pe: agar articles.json empty hai toh auto-generate karo
    if len(load_articles()) == 0:
        auto_publish()           # 5 trending articles generate karo
    
    # Har 6 ghante auto-publish
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_publish, 'interval', hours=6)
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
    try:
        topics = get_trending_topics()
    except Exception as exc:
        print('Auto publish skipped: unable to fetch trending topics:', exc)
        return

    published = 0
    for topic in topics[:5]:
        try:
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
                'fact_graph': fact_graph,
                'published_at': datetime.now(timezone.utc).isoformat(),
            }
            save_article(article_record)
            published += 1
        except Exception as exc:
            print(f'Auto publish failed for {topic}:', exc)

    print(f'Auto publish completed: {published} articles published.')


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
        'fact_graph': fact_graph,
        'published_at': datetime.now(timezone.utc).isoformat(),
    }
    save_article(article_record)
    return article_record


@app.post('/qa')
async def qa(request: QARequest):
    article = get_article(request.article_id)
    if not article:
        raise HTTPException(status_code=404, detail='Article not found')

    article_text = ' '.join([
        article.get('headline', ''),
        article.get('dek', ''),
        article.get('body', ''),
    ]).strip()
    if not article_text:
        raise HTTPException(status_code=400, detail='Article text is unavailable')

    answer = answer_question(article_text, request.question)
    return {
        'article_id': request.article_id,
        'question': request.question,
        'answer': answer,
    }


@app.get('/digest')
async def digest():
    articles = get_todays_articles()
    return write_digest(articles)


if __name__ == '__main__':
    import uvicorn

    port = int(os.environ.get('PORT', 5000))
    uvicorn.run('app:app', host='0.0.0.0', port=port, reload=False)
          