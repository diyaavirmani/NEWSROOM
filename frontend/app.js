const topicInput = document.getElementById('topicInput');
const generateButton = document.getElementById('generateButton');
const digestButton = document.getElementById('digestButton');
const feed = document.getElementById('feed');
const status = document.getElementById('status');
const spinner = document.getElementById('spinner');
const tags = Array.from(document.querySelectorAll('.tag'));

const articleHeadline = document.getElementById('articleHeadline');
const articleDek = document.getElementById('articleDek');
const articleByline = document.getElementById('articleByline');
const articleBody = document.getElementById('articleBody');
const sourceList = document.getElementById('sourceList');
const questionInput = document.getElementById('questionInput');
const askButton = document.getElementById('askButton');
const qaStatus = document.getElementById('qaStatus');
const chatLog = document.getElementById('chatLog');

let articlesCache = [];
let activeSector = 'All';

function setLoading(isLoading) {
  if (spinner) {
    spinner.classList.toggle('hidden', !isLoading);
  }
  if (generateButton) {
    generateButton.disabled = isLoading;
  }
  if (askButton) {
    askButton.disabled = isLoading;
  }
}

function setStatus(message, isError = false) {
  if (!status) return;
  status.textContent = message;
  status.className = isError ? 'status error' : 'status';
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

function getSectorTag(article) {
  return article.sector || 'General';
}

function renderCard(article) {
  const card = document.createElement('article');
  card.className = 'article-card';
  card.dataset.id = article.id;

  const meta = document.createElement('div');
  meta.className = 'card-meta';
  meta.innerHTML = `
    <span class="meta-pill">${getSectorTag(article)}</span>
    <span class="meta-pill">${new Date(article.published_at).toLocaleDateString()}</span>
    <span class="meta-pill">Confidence ${Math.round((article.confidence || 0) * 100)}%</span>
  `;
  card.appendChild(meta);

  const headline = document.createElement('h2');
  headline.textContent = article.headline || 'Untitled';
  card.appendChild(headline);

  if (article.dek) {
    const dek = document.createElement('p');
    dek.className = 'dek';
    dek.textContent = article.dek;
    card.appendChild(dek);
  }

  const excerpt = document.createElement('div');
  excerpt.className = 'excerpt';
  excerpt.textContent = article.body ? article.body.slice(0, 220) + '...' : 'No preview available.';
  card.appendChild(excerpt);

  const readMore = document.createElement('p');
  readMore.className = 'read-more';
  readMore.textContent = 'Read full article →';
  card.appendChild(readMore);

  card.addEventListener('click', () => openArticle(article.id));
  return card;
}

function displayFeed(articles) {
  if (!feed) return;
  feed.innerHTML = '';

  const filtered = articles.filter((article) => {
    if (activeSector === 'All') return true;
    return getSectorTag(article) === activeSector;
  });

  if (!filtered.length) {
    const empty = document.createElement('div');
    empty.textContent = 'No articles match this filter yet.';
    empty.style.color = '#5a5147';
    feed.appendChild(empty);
    return;
  }

  filtered.forEach((article) => feed.appendChild(renderCard(article)));
}

async function loadFeed() {
  if (!feed) return;
  setStatus('Loading saved articles...');
  setLoading(true);
  try {
    const articles = await fetchJson('/articles');
    articlesCache = Array.isArray(articles) ? articles.reverse() : [];
    displayFeed(articlesCache);
    setStatus('Showing saved articles.');
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  } finally {
    setLoading(false);
  }
}

async function generateArticle() {
  if (!topicInput) return;
  const topic = topicInput.value.trim();
  if (!topic) {
    setStatus('Please enter a topic.', true);
    return;
  }

  setStatus('Generating article...');
  setLoading(true);
  try {
    const article = await fetchJson('/generate', { topic });
    articlesCache.unshift(article);
    displayFeed(articlesCache);
    setStatus('Article generated successfully.');
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  } finally {
    setLoading(false);
  }
}

async function generateDigest() {
  setStatus('Generating morning digest...');
  setLoading(true);
  try {
    const digest = await fetchJson('/digest');
    const panel = document.createElement('article');
    panel.className = 'article-card';
    panel.innerHTML = `
      <h2>Morning Digest</h2>
      <div class="body">${digest.digest || 'No digest available.'}</div>
    `;
    if (feed) {
      feed.innerHTML = '';
      feed.appendChild(panel);
    }
    setStatus('Morning digest is ready.');
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  } finally {
    setLoading(false);
  }
}

function openArticle(id) {
  localStorage.setItem('dispatchArticleId', id);
  window.location.href = '/static/article.html';
}

function renderSources(sources) {
  if (!sourceList) return;
  sourceList.innerHTML = '';
  if (!Array.isArray(sources) || !sources.length) {
    sourceList.innerHTML = '<li>No sources available.</li>';
    return;
  }
  sources.forEach((source) => {
    const li = document.createElement('li');
    const anchor = document.createElement('a');
    anchor.href = source.url || '#';
    anchor.target = '_blank';
    anchor.textContent = source.title || source.url || 'Source link';
    li.appendChild(anchor);
    sourceList.appendChild(li);
  });
}

function appendChatMessage(text, role = 'ai') {
  if (!chatLog) return;
  const li = document.createElement('li');
  li.className = role;
  li.textContent = text;
  chatLog.appendChild(li);
  li.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function askQuestion() {
  if (!questionInput) return;
  const question = questionInput.value.trim();
  if (!question) {
    qaStatus.textContent = 'Please enter a question.';
    qaStatus.className = 'status error';
    return;
  }

  const articleId = localStorage.getItem('dispatchArticleId');
  if (!articleId) {
    qaStatus.textContent = 'Article not loaded.';
    qaStatus.className = 'status error';
    return;
  }

  qaStatus.textContent = 'Fetching answer...';
  qaStatus.className = 'status';
  setLoading(true);
  try {
    appendChatMessage(`Q: ${question}`, 'user');
    const response = await fetchJson('/qa', { article_id: articleId, question });
    appendChatMessage(`A: ${response.answer}`, 'ai');
    questionInput.value = '';
    qaStatus.textContent = 'Answered.';
  } catch (err) {
    qaStatus.textContent = `Error: ${err.message}`;
    qaStatus.className = 'status error';
  } finally {
    setLoading(false);
  }
}

async function loadArticle() {
  const articleId = localStorage.getItem('dispatchArticleId');
  if (!articleId) {
    if (articleHeadline) articleHeadline.textContent = 'Article not found';
    return;
  }

  setLoading(true);
  try {
    const article = await fetchJson(`/articles/${articleId}`);
    if (articleHeadline) articleHeadline.textContent = article.headline || 'Untitled';
    if (articleDek) articleDek.textContent = article.dek || '';
    if (articleByline) articleByline.textContent = `${article.byline || 'By Newsroom AI'} · ${new Date(article.published_at).toLocaleString()}`;
    if (articleBody) articleBody.textContent = article.body || '';
    renderSources(article.sources || []);
    setStatus('Article loaded.');
  } catch (err) {
    setStatus(`Error loading article: ${err.message}`, true);
  } finally {
    setLoading(false);
  }
}

function setActiveTag(tagValue) {
  activeSector = tagValue;
  tags.forEach((button) => {
    button.classList.toggle('active', button.dataset.sector === tagValue);
  });
  displayFeed(articlesCache);
}

function attachIndexListeners() {
  if (generateButton) generateButton.addEventListener('click', generateArticle);
  if (digestButton) digestButton.addEventListener('click', generateDigest);
  tags.forEach((button) => {
    button.addEventListener('click', () => setActiveTag(button.dataset.sector));
  });
  if (topicInput) {
    topicInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        generateArticle();
      }
    });
  }
}

function attachArticleListeners() {
  if (askButton) askButton.addEventListener('click', askQuestion);
  if (questionInput) {
    questionInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        askQuestion();
      }
    });
  }
}

function init() {
  if (feed) {
    attachIndexListeners();
    loadFeed();
    return;
  }
  if (articleHeadline) {
    attachArticleListeners();
    loadArticle();
  }
}

init();
