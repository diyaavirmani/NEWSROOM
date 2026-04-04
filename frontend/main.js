const topicInput = document.getElementById('topicInput');
const generateButton = document.getElementById('generateButton');
const digestButton = document.getElementById('digestButton');
const feed = document.getElementById('feed');
const status = document.getElementById('status');

function clearFeed() {
  feed.innerHTML = '';
}

function setStatus(message, isError = false) {
  status.textContent = message;
  status.className = isError ? 'status error' : 'status';
}

function createArticleCard(article) {
  const card = document.createElement('article');
  card.className = 'card';

  const headline = document.createElement('h2');
  headline.textContent = article.headline || 'No headline';
  card.appendChild(headline);

  const dek = document.createElement('p');
  dek.className = 'dek';
  dek.textContent = article.dek || '';
  card.appendChild(dek);

  const byline = document.createElement('p');
  byline.className = 'byline';
  byline.textContent = article.byline || 'By Newsroom AI';
  card.appendChild(byline);

  const body = document.createElement('div');
  body.className = 'body';
  body.textContent = article.body || '';
  card.appendChild(body);

  if (article.sources && article.sources.length) {
    const sourceList = document.createElement('div');
    sourceList.className = 'sources';
    sourceList.innerHTML = '<strong>Sources</strong>';
    const list = document.createElement('ul');
    article.sources.forEach((source) => {
      const item = document.createElement('li');
      const link = document.createElement('a');
      link.href = source.url || '#';
      link.target = '_blank';
      link.textContent = source.title || source.url || 'Source';
      item.appendChild(link);
      list.appendChild(item);
    });
    sourceList.appendChild(list);
    card.appendChild(sourceList);
  }

  return card;
}

function displayArticle(article) {
  clearFeed();
  feed.appendChild(createArticleCard(article));
}

async function fetchJson(url, body = null) {
  const options = {
    method: body ? 'POST' : 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  };
  if (body) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

async function generateArticle() {
  const topic = topicInput.value.trim();
  if (!topic) {
    setStatus('Please enter a topic.', true);
    return;
  }

  setStatus('Generating article...');
  try {
    const article = await fetchJson('/generate', { topic });
    displayArticle(article);
    setStatus('Article generated successfully.');
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  }
}

async function fetchDigest() {
  setStatus('Loading morning digest...');
  try {
    const digest = await fetchJson('/digest');
    clearFeed();
    const card = document.createElement('article');
    card.className = 'card';
    const title = document.createElement('h2');
    title.textContent = 'Morning Digest';
    const body = document.createElement('div');
    body.className = 'body';
    body.textContent = digest.digest || 'No digest available.';
    card.appendChild(title);
    card.appendChild(body);
    feed.appendChild(card);
    setStatus('Digest loaded successfully.');
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  }
}

generateButton.addEventListener('click', generateArticle);
digestButton.addEventListener('click', fetchDigest);

topicInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    generateArticle();
  }
});
