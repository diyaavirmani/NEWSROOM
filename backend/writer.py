import groq
import os, json, uuid
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
client = groq.Groq(
    api_key=os.environ.get("GROQ_API_KEY", "dummy_key_until_configured"),
    base_url="https://openrouter.ai/api/v1"
)

SYSTEM_PROMPT = """
You are a senior journalist at The Economist.
Write with clarity, neutrality, and depth.
Return ONLY valid JSON (no markdown):
{"headline":"...","dek":"...","body":"...","sector":"...","confidence":0.0}
"""

def write_article(fact_graph, topic, image_url=None):
    user_prompt = f"""Topic: {topic}
Facts: {json.dumps(fact_graph.get("facts", []))}
Sources: {fact_graph.get("sources_count", 0)}
Confidence: {fact_graph.get("confidence", 0.8)}
Write the full article."""

    response = client.chat.completions.create(
        model="meta-llama/llama-3.1-70b-instruct",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=1500, temperature=0.3
    )

    raw = response.choices[0].message.content.strip()
    try: 
        result = json.loads(raw)
    except: 
        result = {"headline": topic, "dek": "", "body": raw, "sector": "General", "confidence": 0.7}

    return {
        "id": str(uuid.uuid4()),
        "headline": result.get("headline", topic),
        "dek": result.get("dek", ""),
        "body": result.get("body", ""),
        "sector": result.get("sector", "General"),
        "confidence": fact_graph.get("confidence", 0.8),
        "sources": fact_graph.get("sources", []),
        "sources_count": fact_graph.get("sources_count", 0),
        "verified_claims": fact_graph.get("verified_claims", 0),
        "image_url": image_url,
        "timestamp": datetime.now().isoformat()
    }

def write_digest(articles):
    if not articles:
        return {'digest': 'No articles were published today.'}

    prompt_lines = [
        'Write a punchy 5-item morning briefing in the style of Axios or Morning Brew.',
        'Use concise prose, a conversational tone, and highlight why each story matters.',
        'Use the article headlines and dek/body text below as the source material.',
        '',
        'Article summaries:',
    ]
    for article in articles:
        summary = article.get('dek') or article.get('body', '')[:180]
        if summary:
            prompt_lines.append(f'- {article.get("headline", "Untitled")}: {summary}')
    prompt = '\\n'.join(prompt_lines)
    
    response = client.chat.completions.create(
        model="meta-llama/llama-3.1-70b-instruct",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.3
    )
    return {'digest': response.choices[0].message.content.strip()}
