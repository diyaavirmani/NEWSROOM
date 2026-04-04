import os
import re
from datetime import datetime
from dotenv import load_dotenv
import google.ai.generativelanguage as gal
import google.ai.generativelanguage_v1beta.types as gal_types
from google.api_core.client_options import ClientOptions

load_dotenv()
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')


def _build_gemini_client():
    client_options = None
    if GOOGLE_API_KEY:
        client_options = ClientOptions(api_key=GOOGLE_API_KEY)
    return gal.TextServiceClient(client_options=client_options)


def _run_gemini(prompt: str, max_output_tokens: int = 900, temperature: float = 0.2):
    client = _build_gemini_client()
    request = gal.GenerateTextRequest(
        model='text-bison-001',
        prompt=gal_types.TextPrompt(text=prompt),
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    response = client.generate_text(request=request)
    candidates = getattr(response, 'candidates', [])
    if not candidates:
        raise RuntimeError('Gemini did not return a response')
    return candidates[0].output.strip()


def _format_fact_graph(fact_graph, topic):
    lines = [
        f'Topic: {topic}',
        f'Timestamp: {fact_graph.get("timestamp", "")}',
        'Facts: ',
    ]
    for source in fact_graph.get('sources', []):
        lines.append(f'- Source: {source.get("title") or source.get("url")}')
        if source.get('url'):
            lines.append(f'  URL: {source.get("url")}')
    if fact_graph.get('entities'):
        lines.append('Entities:')
        for entity in fact_graph['entities']:
            lines.append(f'  - {entity.get("name")} ({entity.get("type", "unknown")}) Sources: {", ".join(entity.get("sources", []))}')
    if fact_graph.get('events'):
        lines.append('Events:')
        for event in fact_graph['events']:
            lines.append(f'  - {event.get("description")} Sources: {", ".join(event.get("sources", []))}')
    if fact_graph.get('numbers'):
        lines.append('Numbers:')
        for number in fact_graph['numbers']:
            lines.append(f'  - {number.get("value")} ({number.get("context", "")}) Sources: {", ".join(number.get("sources", []))}')
    if fact_graph.get('contradictions'):
        lines.append('Contradictions:')
        for contradiction in fact_graph['contradictions']:
            lines.append(f'  - {contradiction.get("issue")} Sources: {", ".join(contradiction.get("sources", []))}')
    return '\n'.join(lines)


def _parse_article_output(text: str):
    labels = {'headline': '', 'dek': '', 'byline': ''}
    body_lines = []
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        lower = value.lower()
        if lower.startswith('headline:'):
            labels['headline'] = value.split(':', 1)[1].strip()
            continue
        if lower.startswith('dek:') or lower.startswith('subheadline:'):
            labels['dek'] = value.split(':', 1)[1].strip()
            continue
        if lower.startswith('byline:'):
            labels['byline'] = value.split(':', 1)[1].strip()
            continue
        body_lines.append(value)

    if not labels['headline'] and body_lines:
        labels['headline'] = body_lines.pop(0)
    if not labels['dek'] and body_lines:
        candidate = body_lines[0]
        if len(candidate.split()) < 25:
            labels['dek'] = body_lines.pop(0)
    if not labels['byline']:
        labels['byline'] = 'By Newsroom AI'

    return {
        'headline': labels['headline'],
        'dek': labels['dek'],
        'byline': labels['byline'],
        'body': '\n'.join(body_lines).strip(),
    }


def write_article(fact_graph, topic):
    system_prompt = (
        'You are a professional Reuters-style journalist. Write only factual content. ' 
        'Do not invent quotes, do not speculate, and do not hallucinate. ' 
        'Produce a headline, a dek (subheadline), a byline, and a body with 3-5 paragraphs. ' 
        'The headline should be 10 words max. The dek should be 1-2 sentences. ' 
        'The lede must answer who, what, when, and where. ' 
        'The closing sentence should describe what happens next. ' 
        'Use concise, objective language and treat the fact graph as the only source of truth. '
    )

    user_prompt = (
        'Use the structured fact graph below to write a single journalism-quality article. ' 
        'Include a clickable source transparency panel if possible. ' 
        'Do not include any text that is not grounded in the fact graph.\n\n'
        f'{_format_fact_graph(fact_graph, topic)}\n\n'
        'Output format should be: Headline:, Dek:, Byline:, followed by the article body. '
    )

    raw_article = _run_gemini(system_prompt + '\n\n' + user_prompt, max_output_tokens=900)
    article = _parse_article_output(raw_article)
    article['topic'] = topic
    article['generated_at'] = datetime.utcnow().isoformat() + 'Z'
    return article


def answer_question(article_text: str, question: str):
    prompt = (
        'Based on this article: \n' 
        f'{article_text}\n\n' 
        'Answer this question directly: ' 
        f'{question}\n' 
        'Do not add any extra commentary.'
    )
    return _run_gemini(prompt, max_output_tokens=256, temperature=0.0)


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
    prompt = '\n'.join(prompt_lines)
    digest_text = _run_gemini(prompt, max_output_tokens=400, temperature=0.3)
    return {'digest': digest_text.strip()}
