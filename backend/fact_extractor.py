import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from tavily import TavilyClient
import google.ai.generativelanguage as gal
import google.ai.generativelanguage_v1beta.types as gal_types
from google.api_core.client_options import ClientOptions

load_dotenv()

TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
tavily_client = TavilyClient(api_key=TAVILY_API_KEY)


def _build_gemini_client():
    client_options = None
    if GOOGLE_API_KEY:
        client_options = ClientOptions(api_key=GOOGLE_API_KEY)
    return gal.TextServiceClient(client_options=client_options)


def _run_gemini(prompt: str, max_output_tokens: int = 512):
    client = _build_gemini_client()
    request = gal.GenerateTextRequest(
        model='text-bison-001',
        prompt=gal_types.TextPrompt(text=prompt),
        temperature=0.0,
        max_output_tokens=max_output_tokens,
    )
    response = client.generate_text(request=request)
    candidates = getattr(response, 'candidates', [])
    if not candidates:
        raise RuntimeError('Gemini did not return a response')
    return candidates[0].output


def _safe_json_load(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def _normalize_results(raw_results):
    if isinstance(raw_results, dict):
        for key in ('results', 'data', 'items', 'articles'):
            if key in raw_results and isinstance(raw_results[key], list):
                return raw_results[key]
        return []
    if isinstance(raw_results, list):
        return raw_results
    return []


def _extract_content(item, topic: str):
    for key in ('content', 'text', 'summary', 'snippet', 'description', 'answer'):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    url = item.get('url') or item.get('source_url') or item.get('link')
    if not url:
        return ''

    try:
        extracted = tavily_client.extract(url, format='text', extract_depth='basic', query=topic)
    except Exception:
        return ''

    if isinstance(extracted, dict):
        for result in extracted.get('results', []):
            if not isinstance(result, dict):
                continue
            for key in ('content', 'text', 'summary', 'answer'):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ''


def _normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def _extract_structured_fields(title: str, url: str, text: str):
    prompt = (
        'Extract structured facts from the article below. Return only valid JSON with keys: ' 
        'entities, events, numbers, contradictions. \n'
        'entities should be a list of objects with name, type, mentions, and sources. \n'
        'events should be a list of descriptions with sources. \n'
        'numbers should be a list of values with context and sources. \n'
        'contradictions should be a list of issues where sources disagree. \n'
        'Use the following article content exactly. Do not invent quotes. \n\n'
        f'Title: {title}\n'
        f'URL: {url}\n'
        'Article text:\n'
        f'{text}\n'
        'JSON:'
    )
    raw = _run_gemini(prompt, max_output_tokens=512)
    return _safe_json_load(raw)


def _merge_items(items, key_name, extra_keys=None):
    merged = {}
    extra_keys = extra_keys or []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key_name)
        if not value:
            continue
        normalized = _normalize_text(str(value)).lower()
        if not normalized:
            continue
        entry = merged.setdefault(normalized, {'name': str(value).strip(), 'sources': [], **{k: item.get(k) for k in extra_keys}})
        if 'sources' in entry:
            entry['sources'] = list(dict.fromkeys(entry['sources'] + item.get('sources', [])))
        for extra in extra_keys:
            if extra in item and entry.get(extra) != item[extra]:
                entry[extra] = item[extra]
    return list(merged.values())


def _merge_numbers(numbers):
    merged = {}
    for item in numbers:
        if not isinstance(item, dict):
            continue
        value = item.get('value') or item.get('number') or item.get('amount')
        context = item.get('context') or item.get('description')
        if value is None:
            continue
        normalized = _normalize_text(str(value)).lower()
        if not normalized:
            continue
        entry = merged.setdefault(normalized, {
            'value': str(value).strip(),
            'context': str(context).strip() if context else '',
            'sources': []
        })
        entry['sources'] = list(dict.fromkeys(entry['sources'] + item.get('sources', [])))
        if not entry['context'] and context:
            entry['context'] = str(context).strip()
    return list(merged.values())


def extract_facts(search_results, topic):
    sources = []
    raw_results = _normalize_results(search_results)
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = item.get('title') or item.get('headline') or 'Untitled'
        url = item.get('url') or item.get('source_url') or item.get('link') or ''
        text = _extract_content(item, topic)
        source_name = item.get('source') or item.get('domain') or item.get('site') or ''
        source_entry = {
            'title': _normalize_text(title),
            'url': _normalize_text(url),
            'source_name': _normalize_text(source_name),
            'text': _normalize_text(text)[:8000],
        }
        if not source_entry['url'] and not source_entry['text']:
            continue
        sources.append(source_entry)

    if not sources:
        return {
            'topic': topic,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'sources': [],
            'entities': [],
            'events': [],
            'numbers': [],
            'contradictions': [],
            'confidence': 0.0,
        }

    extracted = []
    for source in sources:
        try:
            content = source['text']
            if not content and source['url']:
                content = _extract_content(source, topic)
            if not content:
                continue
            capture = _extract_structured_fields(source['title'], source['url'], content)
            for key in ('entities', 'events', 'numbers', 'contradictions'):
                if key not in capture or not isinstance(capture[key], list):
                    capture[key] = []
            capture['sources'] = [source['url']] if source['url'] else []
            extracted.append(capture)
        except Exception:
            continue

    entities = []
    events = []
    numbers = []
    contradictions = []

    for capture in extracted:
        entities.extend([dict(item, sources=capture['sources']) for item in capture.get('entities', []) if isinstance(item, dict)])
        events.extend([dict(item, sources=capture['sources']) for item in capture.get('events', []) if isinstance(item, dict)])
        numbers.extend([dict(item, sources=capture['sources']) for item in capture.get('numbers', []) if isinstance(item, dict)])
        contradictions.extend([dict(item, sources=capture['sources']) for item in capture.get('contradictions', []) if isinstance(item, dict)])

    merged_entities = _merge_items(entities, 'name', extra_keys=['type', 'mentions'])
    merged_events = _merge_items(events, 'description')
    merged_numbers = _merge_numbers(numbers)

    confidence = min(1.0, 0.2 + 0.1 * len(sources) + 0.05 * len(merged_entities) + 0.05 * len(merged_events))

    return {
        'topic': topic,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'sources': sources,
        'entities': merged_entities,
        'events': merged_events,
        'numbers': merged_numbers,
        'contradictions': contradictions,
        'confidence': confidence,
    }
