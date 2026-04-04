import os
from dotenv import load_dotenv
from tavily import TavilyClient

# to read .env files we use load_dotenv()

load_dotenv()

api_key = os.environ.get('TAVILY_API_KEY')
tavily_client = TavilyClient(api_key=api_key)

# Block 4 — Main function
def search_web(topic):
    """Search the web for a topic using Tavily API client."""
    if not topic or not isinstance(topic, str):
        raise ValueError('topic must be a non-empty string')

    results = tavily_client.search(topic)

    return results


# Block 5 — Test
if __name__ == '__main__':
    query = 'latest news on technology'
    search_results = search_web(query)
    print('Search query:', query)
    print('Search results:', search_results)


