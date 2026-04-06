"""
app.py — Veritas AI Newsroom Backend
Run locally:  uvicorn backend.app:app --reload --port 5000
Render runs:  uvicorn backend.app:app --host 0.0.0.0 --port $PORT
"""

import os, json, uuid, time
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── SAFE IMPORTS — one bad module never crashes the server ─────────────────
try:
    from backend.searcher import search_web
    print("[app] searcher OK")
except Exception:
    try:
        from searcher import search_web
        print("[app] searcher OK (direct)")
    except Exception as e:
        print(f"[app] searcher MISSING: {e}")
        def search_web(topic): return []

try:
    from backend.fact_extractor import extract_facts
    print("[app] fact_extractor OK")
except Exception:
    try:
        from fact_extractor import extract_facts
        print("[app] fact_extractor OK (direct)")
    except Exception as e:
        print(f"[app] fact_extractor MISSING: {e}")
        def extract_facts(results, topic):
            sources = [r.get('url','') for r in (results if isinstance(results,list) else results.get('results',[])) if isinstance(r,dict)]
            return {'facts':[],'sources':sources,'sources_count':len(sources),
                    'confidence':0.75,'verified_claims':0,'entities':[topic]}

try:
    from backend.writer import write_article
    print("[app] writer OK")
except Exception:
    try:
        from writer import write_article
        print("[app] writer OK (direct)")
    except Exception as e:
        print(f"[app] writer MISSING: {e}")
        def write_article(facts, topic, image_url=None):
            return {'id':str(uuid.uuid4()),'headline':topic,'dek':'Writer module not configured.',
                    'body':'Configure writer.py with an OpenRouter or Groq API key.',
                    'sector':'General','confidence':0.0,'sources':[],'sources_count':0,
                    'verified_claims':0,'image_url':image_url,'timestamp':datetime.now().isoformat()}

try:
    from backend.trending import get_trending_for_display, get_trending_topics
    print("[app] trending OK")
except Exception:
    try:
        from trending import get_trending_for_display, get_trending_topics
        print("[app] trending OK (direct)")
    except Exception as e:
        print(f"[app] trending MISSING: {e}")
        def get_trending_for_display(limit=6):
            return [{'topic':'India AI Policy 2026','platform':'Google Trends','views':'24M'},
                    {'topic':'RBI Rate Decision','platform':'Google Trends','views':'9M'},
                    {'topic':'OpenAI News 2026','platform':'Google Trends','views':'41M'},
                    {'topic':'ISRO Mission 2026','platform':'Google Trends','views':'18M'},
                    {'topic':'India Pakistan 2026','platform':'Google Trends','views':'88M'},
                    {'topic':'Ethereum Web3','platform':'Google Trends','views':'12M'}]
        def get_trending_topics(limit=8):
            return [{'topic':'India AI Policy 2026','image_url':None}]


# ── ARTICLES DB (JSON file) ────────────────────────────────────────────────
ARTICLES_FILE = os.path.join(os.path.dirname(__file__), 'articles.json')

def load_articles():
    try:
        if os.path.exists(ARTICLES_FILE):
            with open(ARTICLES_FILE,'r',encoding='utf-8') as f:
                return json.load(f).get('articles',[])
    except: pass
    return []

def save_article(article):
    try:
        arts = load_articles()
        headlines = {a.get('headline','') for a in arts}
        if article.get('headline','') in headlines:
            return
        arts.insert(0, article)
        arts = arts[:100]
        with open(ARTICLES_FILE,'w',encoding='utf-8') as f:
            json.dump({'articles':arts},f,ensure_ascii=False,indent=2)
        print(f"[app] Saved: {article.get('headline','')[:70]}")
    except Exception as e:
        print(f"[app] Save error: {e}")


# ── AUTO-PUBLISH ───────────────────────────────────────────────────────────
def auto_publish(max_articles=5):
    print(f"\n[auto_publish] {datetime.now().strftime('%H:%M:%S')}")
    try:
        topics = get_trending_topics(limit=max_articles*2)
    except Exception as e:
        print(f"[auto_publish] topics failed: {e}"); return

    published = 0
    for item in topics:
        if published >= max_articles: break
        topic = item.get('topic','')
        image_url = item.get('image_url')
        if not topic: continue
        try:
            results = search_web(topic)
            if not results: continue
            facts = extract_facts(results, topic)
            if facts.get('confidence',0) < 0.3: continue
            article = write_article(facts, topic, image_url)
            save_article(article)
            published += 1
            time.sleep(2)
        except Exception as e:
            print(f"[auto_publish] failed '{topic}': {e}")
    print(f"[auto_publish] published {published}\n")


# ── LIFESPAN ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n[lifespan] starting...")
    if len(load_articles()) == 0:
        print("[lifespan] no articles — running auto_publish")
        try: auto_publish(5)
        except Exception as e: print(f"[lifespan] auto_publish failed: {e}")
    else:
        print(f"[lifespan] {len(load_articles())} articles exist")

    scheduler = None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(auto_publish,'interval',hours=1,args=[3])
        scheduler.start()
        print("[lifespan] scheduler started")
    except ImportError:
        print("[lifespan] apscheduler not installed")

    yield

    if scheduler:
        scheduler.shutdown()
    print("[lifespan] shutdown")


# ── APP ────────────────────────────────────────────────────────────────────
app = FastAPI(title="Veritas AI Newsroom", version="2.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


# ── MODELS ─────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    topic: str
    source: Optional[str] = None

class QARequest(BaseModel):
    question: str
    article_id: Optional[str] = None


# ── ROUTES ─────────────────────────────────────────────────────────────────
@app.get('/')
async def root():
    index = os.path.join(frontend_dir, 'index.html')
    if os.path.exists(index):
        return FileResponse(index)
    return {"status":"ok","message":"Veritas AI Newsroom API"}

@app.get('/health')
async def health():
    arts = load_articles()
    return {
        'status':'ok',
        'articles_count':len(arts),
        'timestamp':datetime.now().isoformat(),
        'groq_configured': bool(os.environ.get('GROQ_API_KEY')),
        'tavily_configured': bool(os.environ.get('TAVILY_API_KEY')),
        'newsapi_configured': bool(os.environ.get('NEWS_API_KEY') or os.environ.get('NEWSAPI_KEY')),
    }

@app.get('/articles')
async def get_articles():
    return {'articles': load_articles()}

@app.post('/generate')
async def generate_article(req: GenerateRequest):
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(400, 'topic required')
    try:
        results = search_web(topic)
        if not results:
            raise HTTPException(503,'No search results. Check TAVILY_API_KEY.')
        facts = extract_facts(results, topic)
        article = write_article(facts, topic)
        if req.source == 'trend':
            article['trend_sourced'] = True
        save_article(article)
        return article
    except HTTPException: raise
    except Exception as e:
        print(f"[/generate] {e}")
        raise HTTPException(500, str(e))

@app.post('/qa')
async def qa(req: QARequest):
    q = req.question.strip()
    if not q: raise HTTPException(400,'question required')

    # Try OPENROUTER_API_KEY first, then GROQ_API_KEY
    key = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('GROQ_API_KEY','')
    if not key:
        raise HTTPException(503,'No API key configured. Set OPENROUTER_API_KEY on Render.')

    context = ""
    if req.article_id:
        art = next((a for a in load_articles() if str(a.get('id',''))==str(req.article_id)), None)
        if art:
            context = f"Article: {art.get('headline','')}\n\n{art.get('body','')}\n\n"

    prompt = f"""{context}Reader question: {q}
Answer in 2-3 sentences. Be specific and journalistic."""

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://newsroom-dlwe.onrender.com",
                "X-Title": "Veritas Newsroom"
            }
        )
        r = client.chat.completions.create(
            model='meta-llama/llama-3.3-70b-instruct:free',
            messages=[{'role':'user','content':prompt}],
            max_tokens=300
        )
        return {'answer': r.choices[0].message.content.strip()}
    except Exception as e:
        err = str(e)
        print(f"[/qa] Error: {err}")
        if '429' in err:
            raise HTTPException(503, 'Rate limit reached. Please try again in a moment.')
        elif '401' in err or 'auth' in err.lower():
            raise HTTPException(503, 'Invalid API key. Update OPENROUTER_API_KEY on Render.')
        raise HTTPException(503, f'Q&A unavailable: {err}')

@app.post('/digest')
async def digest():
    arts = load_articles()
    if not arts:
        return {'items':[{'text':'Bureau warming up. Articles will appear shortly.'}]}
    top = arts[:5]
    key = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('GROQ_API_KEY','')
    if key:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer":"https://newsroom-dlwe.onrender.com","X-Title":"Veritas Newsroom"}
            )
            p = "Summarise each in one punchy sentence max 20 words. JSON array of strings only:\n\n"
            for a in top: p += f"- {a.get('headline','')}: {a.get('dek','')}\n"
            r = client.chat.completions.create(
                model='meta-llama/llama-3.3-70b-instruct:free',
                messages=[{'role':'user','content':p}], max_tokens=400)
            raw = r.choices[0].message.content.strip().replace('```json','').replace('```','')
            summaries = json.loads(raw)
            return {'items':[{'text':s} for s in summaries[:5]]}
        except: pass
    items = []
    for a in top:
        t = a.get('headline','') + (f" — {a.get('dek','')[:60]}…" if a.get('dek') else '')
        items.append({'text':t})
    return {'items':items}

@app.get('/trends')
async def trends():
    try:
        t = get_trending_for_display(limit=6)
        return {'trends':t,'source':'newsapi_india'}
    except Exception as e:
        print(f"[/trends] {e}")
        return {'trends':[
            {'topic':'India AI Policy 2026','platform':'NewsAPI','views':'Trending'},
            {'topic':'RBI Rate Decision','platform':'NewsAPI','views':'Trending'},
            {'topic':'OpenAI Latest','platform':'NewsAPI','views':'Trending'},
            {'topic':'India Pakistan 2026','platform':'NewsAPI','views':'Trending'},
            {'topic':'ISRO Mission 2026','platform':'NewsAPI','views':'Trending'},
            {'topic':'Ethereum Pectra','platform':'NewsAPI','views':'Trending'},
        ],'source':'fallback'}

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT',5000))
    uvicorn.run('backend.app:app', host='0.0.0.0', port=port, reload=False)