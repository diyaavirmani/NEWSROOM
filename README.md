# Veritas — AI-Powered Newsroom 📰

**Live Deployment:** [https://newsroom-dlwe.onrender.com](https://newsroom-dlwe.onrender.com)

Veritas is a fully autonomous, AI-driven newsroom platform built with Python, FastAPI, and Vanilla JS/CSS. It seamlessly fetches trending topics, extracts structured facts, generates detailed journalistic articles using advanced LLMs, and presents them in a sophisticated, premium broadsheet-style user interface.

## 🌟 Key Features

- **Autonomous Publishing:** A background job automatically polls for trending topics and writes/publishes fresh articles on a set interval.
- **Resilient AI Routing:** Intelligently switches between OpenRouter (`meta-llama/llama-3.3-70b-instruct:free`) and Groq (`llama-3.3-70b-versatile`) APIs dynamically, preventing backend crashes if keys are reconfigured.
- **Live Fact Extraction:** Utilizes Tavily for real-time web search and Google Gemini to map entities, events, numbers, and contradictions into a robust structured query.
- **Interactive Q&A Widget:** Readers can ask follow-up questions within any article modal, answered contextually in real-time by the AI.
- **Premium Frontend:** Features a high-fidelity, responsive Javascript UI, slick micro-animations, and a robust fallback state that populates demo data gracefully if the backend is down.

## 🛠️ Technology Stack

- **Backend:** Python, FastAPI, Uvicorn, APScheduler
- **AI Models:** LLaMA-3.3 (via OpenRouter/Groq), Google Gemini 1.5 Flash
- **Data & Search:** Tavily Search API, NewsAPI
- **Frontend:** Vanilla HTML5, CSS3, JavaScript
- **Deployment:** Hosted on Render natively via `Procfile`

## 🚀 Environment Setup

To run locally, create a `.env` file in the root directory:
```env
OPENROUTER_API_KEY=sk-or-v1-...     # Optional if GROQ_API_KEY is provided
GROQ_API_KEY=gsk_...                # Optional if OPENROUTER_API_KEY is provided
TAVILY_API_KEY=tvly-...             # Handled web search
NEWS_API_KEY=...                    # Fetches trending topics
GOOGLE_API_KEY=...                  # Gemini extraction
PORT=10000
```

## 💻 Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Start the backend server (FastAPI):**
   ```bash
   uvicorn backend.app:app --host 0.0.0.0 --port 10000 --reload
   ```
3. Navigate to `http://localhost:10000` to interact with the platform.
