const navbar = document.getElementById('navbar');
const hamburger = document.getElementById('hamburger');
const navLinks = document.getElementById('navLinks');

const ORIGINAL_CARD_IDS = new Set(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']);
const STORAGE = {
  users: 'starSakuraUsers',
  currentUser: 'starSakuraCurrentUser',
  gallery: 'animePortfolioGallery',
  commissions: 'starSakuraCommissions',
  inspirations: 'starSakuraInspirations',
  comments: 'starSakuraArtworkComments',
  interactions: 'starSakuraInteractions',
  authTokens: 'starSakuraAuthTokens'
};
const GALLERY_ITEMS_PER_PAGE = 8;
const GALLERY_API_PAGE_SIZE = 24;
let galleryCurrentPage = 1;
let galleryVisibleCount = GALLERY_ITEMS_PER_PAGE;
let galleryPaginationObserver = null;
let galleryInfiniteObserver = null;
let galleryApiPage = 1;
let galleryApiHasMore = false;
let galleryApiLoading = false;
const API_BASE = (() => {
  const override = new URLSearchParams(location.search).get('api') || localStorage.getItem('starSakuraApiBase');
  if (override) return override.replace(/\/$/, '').replace(/\/api$/, '') + '/api';
  if (location.protocol === 'file:') return 'http://127.0.0.1:8000/api';
  return `${location.origin}/api`;
})();
let currentUser = JSON.parse(localStorage.getItem(STORAGE.currentUser) || 'null');
let cardIdCounter = 11;
let publishImageSrc = '';
let commentImageSrc = '';
let editingCommissionId = '';
let commissionCache = [];
let commissionOptionsCache = [];
let activeCommissionDetailId = '';
let commissionDetailBids = [];
let commissionDetailInvitations = [];
let commissionDetailRequestToken = 0;
let commissionLoadPromise = null;
let commissionMigrationPromise = null;
let commissionActionBusy = false;
let commissionArtistSearchTimer = null;
let commissionArtistSearchToken = 0;
let commissionArtistResults = [];
let commissionSelectedArtist = null;
let commissionArtistSearchQuery = '';
let commissionArtistSearchError = '';
let editingSkills = [];
let artworkCommentSyncTimer = null;
let artworkCommentSyncBusy = false;
const COMMENT_SYNC_INTERVAL = 1000;

const escapeHTML = (value = '') => String(value).replace(/[&<>'\"]/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '\"': '&quot;'
}[char]));

const encodeHeaderValue = (value = '') => encodeURIComponent(String(value || ''));

function apiHeaders(extra = {}, withAuth = true) {
  const headers = { 'Content-Type': 'application/json', ...extra };
  const token = currentUser?.access || JSON.parse(localStorage.getItem(STORAGE.authTokens) || '{}').access;
  if (withAuth && token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function apiRequest(path, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  const forceAuth = options.auth === true;
  const skipAuth = [
    '/users/login/',
    '/users/register/',
    '/users/token/refresh/',
  ].includes(path) || options.auth === false;
  const isPublicRead = method === 'GET' && /^\/(artworks|custom|reviews|inspirations|users\/profiles)\//.test(path);
  const token = currentUser?.access || JSON.parse(localStorage.getItem(STORAGE.authTokens) || '{}').access;
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    headers: apiHeaders(options.headers || {}, !skipAuth && (forceAuth || !isPublicRead || !!token))
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401 && !skipAuth && !isPublicRead) clearSession();
  if (!response.ok) {
    const detail = payload.message ?? payload.data ?? payload.detail;
    const messages = [];
    const collectMessages = value => {
      if (value == null) return;
      if (Array.isArray(value)) return value.forEach(collectMessages);
      if (typeof value === 'object') return Object.values(value).forEach(collectMessages);
      const text = String(value).trim();
      if (text) messages.push(text);
    };
    collectMessages(detail);
    const error = new Error(messages.join('；') || '请求失败');
    error.status = response.status;
    error.data = payload.data;
    throw error;
  }
  return payload.data ?? payload;
}

function apiList(data) {
  if (data?.data) return apiList(data.data);
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

function normalizeImageSrc(src = '') {
  if (!src) return '';
  if (/^(data:|https?:|blob:|\/)/.test(src)) return src;
  return `/${src.replace(/^\/+/, '')}`;
}

function artworkToCardData(item) {
  const tag = item.category || (Array.isArray(item.tags) ? item.tags[0] : '') || '原创作品';
  const owner = item.owner_username || 'admin';
  return {
    id: item.id,
    owner,
    original: owner === 'admin',
    saved: true,
    reviewsCount: item.reviews_count || 0,
    name: item.title,
    tag,
    imageSrc: normalizeImageSrc(item.image_url || item.image || ''),
    recommendationScore: item.recommendation_score || 0,
    matchedTags: Array.isArray(item.matched_tags) ? item.matched_tags : []
  };
}

function toApiArtwork(card) {
  const data = getCardData(card);
  return {
    title: data.name,
    description: data.name,
    category: data.tag,
    tags: data.tag ? [data.tag] : [],
    price: 0,
    is_available: true,
    image_data: data.imageSrc && data.imageSrc.startsWith('data:') ? data.imageSrc : ''
  };
}

async function persistArtwork(card) {
  if (!card) return;
  const payload = toApiArtwork(card);
  const method = card.dataset.saved === 'true' ? 'PATCH' : 'POST';
  const path = card.dataset.saved === 'true' ? `/artworks/${card.dataset.id}/` : '/artworks/';
  const saved = await apiRequest(path, {
    method,
    body: JSON.stringify(payload)
  });
  card.dataset.id = String(saved.id);
  card.dataset.saved = 'true';
  card.dataset.owner = saved.owner_username || card.dataset.owner;
  card.dataset.reviewsCount = String(saved.reviews_count || 0);
  const imageSrc = normalizeImageSrc(saved.image_url || saved.image || '');
  if (imageSrc) {
    let img = card.querySelector('.character-image img');
    if (!img) {
      img = document.createElement('img');
      card.querySelector('.character-image').insertBefore(img, card.querySelector('.character-image').firstChild);
    }
    img.src = imageSrc;
  }
  updateCommentButtons();
  return saved;
}

function artworkMatchesCard(item, card) {
  if (!item || !card) return false;
  const data = getCardData(card);
  return !!data
    && String(item.owner_username || '') === String(data.owner || '')
    && String(item.title || '').trim() === String(data.name || '').trim()
    && String(item.category || '').trim() === String(data.tag || '').trim();
}

function artworkIdsFromInteractionKeys(keys = []) {
  return (keys || []).reduce((result, key) => {
    const [type, id] = String(key).split(':');
    if (type === 'artwork' && id) result[id] = (result[id] || 0) + 1;
    return result;
  }, {});
}

function userArtworkViews() {
  const bucket = getUserInteractionBucket();
  if (!bucket?.views) return {};
  return Object.entries(bucket.views).reduce((result, [key, count]) => {
    const [type, id] = String(key).split(':');
    if (type === 'artwork' && id) result[id] = Number(count || 0);
    return result;
  }, {});
}

function buildArtworkRecommendationPayload() {
  const state = getInteractions();
  const bucket = getUserInteractionBucket(state) || defaultUserInteractionBucket();
  return {
    tags: getHomeTags(),
    views: userArtworkViews(),
    likes: artworkIdsFromInteractionKeys(bucket.liked),
    favorites: artworkIdsFromInteractionKeys(bucket.favorites),
    comments: state.artwork?.comments || {},
    history: (bucket.history || []).filter(key => String(key).startsWith('artwork:'))
  };
}

function cardRecommendationTokens(item) {
  return splitRecommendationTags([item.tag, item.name, item.owner].filter(Boolean).join(','));
}

function buildBehaviorTagWeights(items) {
  const payload = buildArtworkRecommendationPayload();
  const byId = new Map(items.map(item => [String(item.id), item]));
  const weights = {};
  const add = (id, amount) => {
    const item = byId.get(String(id));
    if (!item || amount <= 0) return;
    splitRecommendationTags(item.tag).forEach(tag => {
      const key = tag.toLowerCase();
      weights[key] = (weights[key] || 0) + amount;
    });
  };
  Object.entries(payload.views).forEach(([id, count]) => add(id, Math.min(Number(count || 0), 8)));
  Object.entries(payload.likes).forEach(([id, count]) => add(id, Number(count || 0) * 4));
  Object.entries(payload.favorites).forEach(([id, count]) => add(id, Number(count || 0) * 6));
  payload.history.forEach((key, index) => add(key.split(':')[1], Math.max(0.5, 3 - index * 0.08)));
  return weights;
}

function scoreLocalArtwork(item, behaviorWeights = {}) {
  const payload = buildArtworkRecommendationPayload();
  const tokens = new Set(cardRecommendationTokens(item).map(tag => tag.toLowerCase()));
  const text = [item.name, item.tag, item.owner].join(' ').toLowerCase();
  let score = 0;
  payload.tags.forEach((tag, index) => {
    const key = tag.toLowerCase();
    const weight = Math.max(1, payload.tags.length - index);
    if (tokens.has(key)) score += 16 * weight;
    else if (text.includes(key)) score += 5 * weight;
  });
  Object.entries(behaviorWeights).forEach(([tag, weight]) => {
    if (tokens.has(tag)) score += 5 * Math.log1p(weight);
    else if (text.includes(tag)) score += 1.5 * Math.log1p(weight);
  });
  const counts = getInteractionCounts('artwork', item.id);
  score += Math.log1p(counts.views) * 0.7;
  score += Math.log1p(counts.likes) * 2.2;
  score += Math.log1p(counts.favorites) * 3;
  score += Math.log1p(counts.comments || item.reviewsCount || 0) * 1.4;
  return score;
}

function sortGalleryDataByRecommendation(items = []) {
  const behaviorWeights = buildBehaviorTagWeights(items);
  return [...items].sort((a, b) => {
    const diff = scoreLocalArtwork(b, behaviorWeights) - scoreLocalArtwork(a, behaviorWeights);
    if (diff) return diff;
    return Number(b.id || 0) - Number(a.id || 0);
  });
}

async function ensureArtworkRecords() {
  let items = [];
  try {
    items = apiList(await apiRequest('/artworks/?page_size=200&ordering=created_at'));
  } catch (error) {
    console.warn('Artwork sync skipped:', error);
    return;
  }

  const cards = Array.from(document.querySelectorAll('.character-card'));
  let changed = false;
  for (const card of cards) {
    if (card.dataset.saved === 'true') continue;
    const matched = items.find(item => artworkMatchesCard(item, card));
    if (matched) {
      card.dataset.id = String(matched.id);
      card.dataset.saved = 'true';
      card.dataset.reviewsCount = String(matched.reviews_count || 0);
      changed = true;
      continue;
    }
    try {
      const saved = await persistArtwork(card);
      items.push(saved);
      changed = true;
    } catch (error) {
      console.warn('Artwork sync failed for card:', card.dataset.id, error);
    }
  }
  if (changed) {
    saveGallery(false);
    updateCommentButtons();
  }
}

async function deleteArtworkFromApi(card) {
  if (!card || card.dataset.saved !== 'true') return;
  await apiRequest(`/artworks/${card.dataset.id}/`, { method: 'DELETE' });
}

async function loadCommissionOptions() {
  const data = await apiRequest('/custom/options/');
  commissionOptionsCache = apiList(data).map(item => ({
    code: item.code || '',
    title: item.title || '',
    priceLabel: item.price_label || ''
  })).filter(item => item.code && item.title);
  renderCommissionOptions();
  return commissionOptionsCache;
}

function renderCommissionOptions() {
  const priceList = document.getElementById('commissionPriceList');
  const statusBadge = document.getElementById('commissionStatusBadge');
  const typeSelect = document.getElementById('type');
  if (statusBadge) {
    statusBadge.textContent = commissionOptionsCache.length ? '接受委托中' : '委托配置未加载';
  }
  if (priceList) {
    priceList.innerHTML = commissionOptionsCache.length
      ? commissionOptionsCache.map(item => `
          <li>
            <span>${escapeHTML(item.title)}</span>
            <span class="price">${escapeHTML(item.priceLabel)}</span>
          </li>
        `).join('')
      : '<li><span>暂无委托类型</span><span class="price">请稍后重试</span></li>';
  }
  if (typeSelect) {
    typeSelect.innerHTML = commissionOptionsCache.length
      ? commissionOptionsCache.map(item => `<option value="${escapeHTML(item.code)}">${escapeHTML(item.title)}</option>`).join('')
      : '<option value="">暂无可选委托类型</option>';
  }
}

function getDisplayName(user) {
  return user?.profile?.displayName || user?.username || '未登录';
}

function getIntro(user) {
  return user?.profile?.intro || user?.profile?.signature || '';
}

function getPhilosophy(user) {
  return user?.profile?.philosophy || '';
}

function getSkills(user) {
  const skills = user?.profile?.skills;
  return Array.isArray(skills) && skills.length
    ? skills
    : [];
}

function splitRecommendationTags(value = '') {
  const raw = Array.isArray(value) ? value.join(',') : String(value || '');
  const seen = new Set();
  return raw
    .split(/[,，、/|#\s]+/)
    .map(item => item.trim())
    .filter(item => {
      const key = item.toLowerCase();
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 20);
}

function getHomeTags(user = currentUser) {
  return splitRecommendationTags(user?.profile?.homeTags || user?.profile?.recommendationTags || []);
}

function renderHomeTagPreview(targetId, tags) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const safeTags = tags.length ? tags : ['暂未设置'];
  target.innerHTML = safeTags.map(tag => `<span class="skill-pill">${escapeHTML(tag)}</span>`).join('');
}

function setAvatarElement(element, avatarSrc, fallbackName) {
  if (!element) return;
  element.replaceChildren();
  if (avatarSrc) {
    const image = document.createElement('img');
    image.src = normalizeImageSrc(String(avatarSrc));
    image.alt = String(fallbackName || '头像');
    element.appendChild(image);
  } else {
    element.textContent = (fallbackName || '我').trim().slice(0, 1).toUpperCase() || '我';
  }
}

function renderSkillList(targetId, skills, editable = false) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const safeSkills = skills.length ? skills : ['暂无技能'];
  target.innerHTML = safeSkills.map((skill, index) => `
    <span class="${editable ? 'skill-pill' : 'tool-item'}">
      ${escapeHTML(skill)}
      ${editable && skill !== '暂无技能' ? `<button type="button" class="skill-remove" onclick="removeProfileSkill(${index})" aria-label="删除技能">×</button>` : ''}
    </span>
  `).join('');
}

function addProfileSkill() {
  const input = document.getElementById('profileSkillInput');
  const skill = input.value.trim();
  if (!skill) return;
  if (!editingSkills.some(item => item.toLowerCase() === skill.toLowerCase())) {
    editingSkills.push(skill);
  }
  input.value = '';
  renderSkillList('profileSkillEditorList', editingSkills, true);
}

function removeProfileSkill(index) {
  editingSkills.splice(index, 1);
  renderSkillList('profileSkillEditorList', editingSkills, true);
}

function getUsers() {
  const users = {};
  if (currentUser?.username) users[currentUser.username] = currentUser;
  return users;
}

function saveUsers(users) {
  if (!currentUser?.username || !users[currentUser.username]) return;
  currentUser = { ...currentUser, ...users[currentUser.username] };
  localStorage.setItem(STORAGE.currentUser, JSON.stringify(currentUser));
}

function normalizeCommissionItem(item, index) {
  const legacy = !('requester' in item) && ('owner' in item || 'message' in item || 'typeLabel' in item);
  if (legacy) {
    return {
      id: item.id || `legacy-${index + 1}`,
      requester: 'admin',
      artist: '',
      title: item.typeLabel || '管理员公开委托',
      typeLabel: item.typeLabel || '公开委托',
      description: item.message || '',
      budget: item.budget || '可商议',
      status: 'open',
      createdAt: item.createdAt || new Date().toLocaleString()
    };
  }
  return {
    id: item.id || `commission-${Date.now()}-${index}`,
    requester: item.requester || 'admin',
    artist: item.artist || '',
    title: item.title || '未命名委托',
    typeLabel: item.typeLabel || item.tag || '委托',
    description: item.description || '',
    budget: item.budget || '可商议',
    status: item.status || (item.artist ? 'accepted' : 'open'),
    createdAt: item.createdAt || new Date().toLocaleString()
  };
}

function getCommissions() {
  const raw = JSON.parse(localStorage.getItem(STORAGE.commissions) || '[]');
  const normalized = raw.map(normalizeCommissionItem);
  if (JSON.stringify(raw) !== JSON.stringify(normalized)) {
    localStorage.setItem(STORAGE.commissions, JSON.stringify(normalized));
  }
  return normalized;
}

function saveCommissions(commissions) {
  localStorage.setItem(STORAGE.commissions, JSON.stringify(commissions.map(normalizeCommissionItem)));
}

function getCommissionStatusLabel(status) {
  if (status === 'accepted') return '已接受';
  if (status === 'completed') return '已完成';
  return '待接单';
}

function canAcceptCommission(item) {
  return currentUser && item.status === 'open' && item.requester !== currentUser.username;
}

function getInspirations() {
  return JSON.parse(localStorage.getItem(STORAGE.inspirations) || '[]');
}

function saveInspirations(items) {
  localStorage.setItem(STORAGE.inspirations, JSON.stringify(items));
}

function getComments() {
  return JSON.parse(localStorage.getItem(STORAGE.comments) || '{}');
}

function saveComments(comments) {
  localStorage.setItem(STORAGE.comments, JSON.stringify(comments));
}

function getCardComments(cardId) {
  const comments = getComments();
  return comments[String(cardId)] || [];
}

function saveCardComments(cardId, items) {
  const comments = getComments();
  comments[String(cardId)] = items;
  saveComments(comments);
}

function defaultInteractionState() {
  return {
    artwork: { views: {}, likes: {}, favorites: {}, comments: {}, history: [] },
    inspiration: { views: {}, likes: {}, favorites: {}, comments: {}, history: [] },
    users: {}
  };
}

function defaultUserInteractionBucket() {
  return { liked: [], favorites: [], history: [], views: {} };
}

function getInteractions() {
  const raw = JSON.parse(localStorage.getItem(STORAGE.interactions) || 'null');
  const state = { ...defaultInteractionState(), ...(raw || {}) };
  state.artwork = { ...defaultInteractionState().artwork, ...(state.artwork || {}) };
  state.inspiration = { ...defaultInteractionState().inspiration, ...(state.inspiration || {}) };
  state.users = state.users || {};
  if (currentUser?.username && !state.users[currentUser.username]) {
    state.users[currentUser.username] = defaultUserInteractionBucket();
  }
  if (currentUser?.username) {
    state.users[currentUser.username] = {
      ...defaultUserInteractionBucket(),
      ...(state.users[currentUser.username] || {}),
      views: state.users[currentUser.username]?.views || {}
    };
  }
  return state;
}

function saveInteractions(state) {
  localStorage.setItem(STORAGE.interactions, JSON.stringify(state));
}

function interactionKey(type, id) {
  return `${type}:${String(id)}`;
}

function getUserInteractionBucket(state = getInteractions()) {
  if (!currentUser?.username) return null;
  state.users[currentUser.username] = {
    ...defaultUserInteractionBucket(),
    ...(state.users[currentUser.username] || {}),
    views: state.users[currentUser.username]?.views || {}
  };
  return state.users[currentUser.username];
}

function getInteractionCounts(type, id) {
  const state = getInteractions();
  const bucket = state[type] || {};
  return {
    views: Number(bucket.views?.[id] || 0),
    likes: Number(bucket.likes?.[id] || 0),
    favorites: Number(bucket.favorites?.[id] || 0),
    comments: Number(bucket.comments?.[id] || 0)
  };
}

function userHasInteraction(kind, type, id) {
  const bucket = getUserInteractionBucket();
  return !!bucket?.[kind]?.includes(interactionKey(type, id));
}

function bumpInteraction(type, id, field, amount = 1) {
  const state = getInteractions();
  state[type][field][id] = Math.max(0, Number(state[type][field][id] || 0) + amount);
  saveInteractions(state);
}

function addUserHistory(type, id) {
  if (!currentUser?.username) return;
  const state = getInteractions();
  const bucket = getUserInteractionBucket(state);
  const key = interactionKey(type, id);
  bucket.history = [key, ...bucket.history.filter(item => item !== key)].slice(0, 60);
  bucket.views[key] = Number(bucket.views[key] || 0) + 1;
  saveInteractions(state);
}

function recordView(type, id) {
  if (!id) return;
  bumpInteraction(type, id, 'views', 1);
  addUserHistory(type, id);
  updateInteractionDisplays();
  if (currentUser) renderMePage();
}

function toggleUserInteraction(kind, type, id) {
  if (!requireLogin(kind === 'favorites' ? '请先登录后再收藏。' : '请先登录后再点赞。')) return;
  const state = getInteractions();
  const bucket = getUserInteractionBucket(state);
  const key = interactionKey(type, id);
  const exists = bucket[kind].includes(key);
  bucket[kind] = exists ? bucket[kind].filter(item => item !== key) : [key, ...bucket[kind]];
  const counter = kind === 'favorites' ? 'favorites' : 'likes';
  state[type][counter][id] = Math.max(0, Number(state[type][counter][id] || 0) + (exists ? -1 : 1));
  saveInteractions(state);
  updateInteractionDisplays();
  renderMePage();
}

function setAuthMessage(message) {
  const messageEl = document.getElementById('authMessage');
  if (messageEl) messageEl.textContent = message;
}

function setSettingsMessage(message) {
  const messageEl = document.getElementById('settingsMessage');
  if (messageEl) messageEl.textContent = message;
}

function isAdmin() {
  return currentUser && currentUser.role === 'admin';
}

function setAuthMode(mode) {
  document.querySelectorAll('.auth-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.authMode === mode));
  document.getElementById('loginForm').classList.toggle('active', mode === 'login');
  document.getElementById('registerForm').classList.toggle('active', mode === 'register');
  document.getElementById('authTitle').textContent = mode === 'login' ? '账号登录' : '注册账号';
  document.getElementById('authHint').textContent = mode === 'login'
    ? '登录后可以发布作品、提交委托并进入“我”的页面。'
    : '请填写用户名、邮箱、邮箱密码和用户密码；用户名和邮箱不能重复。';
  setAuthMessage('');
}

function openAuth(mode = 'login', message = '') {
  setAuthMode(mode);
  setAuthMessage(message);
  switchPage('auth');
}

function requireLogin(message = '请先登录后再继续。') {
  if (currentUser) return true;
  openAuth('login', message);
  return false;
}

function validatePasswordPair(password, confirm, label = '密码') {
  if (password.length < 6) return `${label}至少 6 位。`;
  if (password !== confirm) return `${label}与确认输入不一致。`;
  return '';
}

function handleLogin(username, password) {
  const users = getUsers();
  const user = users[username];
  if (!user || user.password !== password) return setAuthMessage('用户名或密码不正确。');
  currentUser = { username: user.username, role: user.role };
  localStorage.setItem(STORAGE.currentUser, JSON.stringify(currentUser));
  setAuthMessage('');
  refreshAuthUI();
  switchPage('me');
}

function registerUser(formData) {
  const users = getUsers();
  const username = formData.username.trim();
  const email = formData.email.trim().toLowerCase();
  if (!username) return setAuthMessage('请输入用户名。');
  if (username === 'admin' || users[username]) return setAuthMessage('该用户名已注册。');
  if (Object.values(users).some(user => (user.email || '').toLowerCase() === email)) return setAuthMessage('该邮箱已注册，不能重复注册。');
  const passwordError = validatePasswordPair(formData.password, formData.passwordConfirm, '用户密码');
  if (passwordError) return setAuthMessage(passwordError);
  users[username] = {
    username,
    email,
    role: 'user',
    profile: { displayName: username, avatar: '', intro: '', philosophy: '', skills: [], gender: '', birthday: '', signature: '' }
  };
  saveUsers(users);
  currentUser = { username, role: 'user' };
  localStorage.setItem(STORAGE.currentUser, JSON.stringify(currentUser));
  setAuthMessage('');
  refreshAuthUI();
  switchPage('me');
}

function refreshAuthUI() {
  const navAvatar = document.getElementById('navUserAvatar');
  const navName = document.getElementById('navUserName');
  const users = currentUser ? getUsers() : {};
  const user = currentUser ? users[currentUser.username] : null;
  const displayName = currentUser ? getDisplayName(user) : '未登录';
  setAvatarElement(navAvatar, user?.profile?.avatar || '', displayName);
  if (navName) navName.textContent = displayName;
  if (currentUser && document.getElementById('auth')?.classList.contains('active')) switchPage('me');
  normalizeCardActions();
  applyCardPermissions();
  renderMePage();
}

function switchPage(pageId) {
  if (pageId === 'about') pageId = 'me';
  if (pageId === 'me' && !requireLogin('请先登录后查看个人页面。')) return;
  if (pageId === 'publish' && !requireLogin('请先登录后再发布作品。')) return;
  if (pageId === 'contact' && !currentUser) return openAuth('login', '请先登录后再使用委托功能。');
  document.querySelectorAll('.page-section').forEach(section => section.classList.toggle('active', section.id === pageId));
  document.querySelectorAll('.nav-links a[data-page]').forEach(link => link.classList.toggle('active', link.dataset.page === pageId));
  if (pageId === 'me') renderMePage();
  if (pageId === 'contact') renderCommissionBoard();
  if (pageId === 'search') renderSearchPage();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function prepareCardOwnership() {
  document.querySelectorAll('.character-card').forEach(card => {
    if (!card.dataset.owner) card.dataset.owner = ORIGINAL_CARD_IDS.has(card.dataset.id) ? 'admin' : (currentUser?.username || 'admin');
    if (!card.dataset.original) card.dataset.original = ORIGINAL_CARD_IDS.has(card.dataset.id) ? 'true' : 'false';
    if (!card.dataset.saved) card.dataset.saved = 'false';
    if (!card.dataset.reviewsCount) card.dataset.reviewsCount = '0';
  });
}

function canEditCard(card) {
  if (!currentUser || !card) return false;
  if (isAdmin()) return true;
  return card.dataset.original !== 'true' && card.dataset.owner === currentUser.username;
}

function requireCardPermission(card) {
  if (!requireLogin('请先登录后再发布或编辑作品。')) return false;
  if (canEditCard(card)) return true;
  alert('普通用户不能修改原页面画作，只能编辑自己发布的新作品。');
  return false;
}

function applyCardPermissions() {
  document.querySelectorAll('.character-card').forEach(card => {
    const editable = canEditCard(card);
    card.classList.toggle('locked', !!currentUser && !editable);
    card.classList.toggle('can-edit', editable);
    card.classList.toggle('admin-edit', isAdmin());
  });
}

function normalizeCardActions() {
  document.querySelectorAll('.character-card').forEach(card => {
    let actions = card.querySelector('.card-actions');
    if (!actions) {
      actions = document.createElement('div');
      actions.className = 'card-actions';
      card.insertBefore(actions, card.firstChild);
    }
    actions.innerHTML = `
      <button class="card-action-btn delete" onclick="deleteCard(this)" title="删除卡片">🗑️</button>
    `;
  });
}

function updateCommentButtons() {
  document.querySelectorAll('.character-card').forEach(card => {
    const button = card.querySelector('.comment-btn');
    if (!button) return;
    const count = Number(card.dataset.reviewsCount || getCardComments(card.dataset.id).length || 0);
    button.textContent = `评价 ${count}`;
  });
}

function normalizeCommentButtons() {
  document.querySelectorAll('.character-card').forEach(card => {
    let meta = card.querySelector('.character-meta');
    if (!meta) {
      meta = document.createElement('div');
      meta.className = 'character-meta';
      const info = card.querySelector('.character-info');
      if (info) info.appendChild(meta);
    }
    if (!meta.querySelector('.comment-btn')) {
      const button = document.createElement('button');
      button.className = 'comment-btn';
      button.type = 'button';
      button.addEventListener('click', event => {
        event.stopPropagation();
        openArtworkDetail(card);
      });
      meta.appendChild(button);
    }
  });
  updateCommentButtons();
}

function openImagePreview(imageContainer) {
  const img = imageContainer.querySelector('img');
  if (!img) return;
  document.getElementById('previewImage').src = img.src;
  document.getElementById('imagePreview').classList.remove('hidden');
}

function closeImagePreview() {
  document.getElementById('imagePreview').classList.add('hidden');
  document.getElementById('previewImage').removeAttribute('src');
}

updateCommentButtons = function() {
  document.querySelectorAll('.character-card').forEach(card => {
    const id = card.dataset.id;
    const counts = getInteractionCounts('artwork', id);
    const commentCount = Number(card.dataset.reviewsCount || getCardComments(id).length || counts.comments || 0);
    const view = card.querySelector('[data-artwork-stat="views"]');
    const like = card.querySelector('[data-artwork-stat="likes"]');
    const comment = card.querySelector('[data-artwork-stat="comments"]');
    const favorite = card.querySelector('[data-artwork-stat="favorites"]');
    if (view) view.textContent = `浏览 ${counts.views}`;
    if (like) {
      like.textContent = `赞 ${counts.likes}`;
      like.classList.toggle('active', userHasInteraction('liked', 'artwork', id));
    }
    if (comment) comment.textContent = `评 ${commentCount}`;
    if (favorite) {
      favorite.textContent = `藏 ${counts.favorites}`;
      favorite.classList.toggle('active', userHasInteraction('favorites', 'artwork', id));
    }
  });
};

const baseNormalizeCommentButtons = normalizeCommentButtons;
normalizeCommentButtons = function() {
  baseNormalizeCommentButtons();
  document.querySelectorAll('.character-card').forEach(card => {
    const image = card.querySelector('.character-image');
    if (image && !image.querySelector('.artwork-view-count')) {
      const view = document.createElement('span');
      view.className = 'artwork-view-count';
      view.dataset.artworkStat = 'views';
      image.appendChild(view);
    }
    let meta = card.querySelector('.character-meta');
    if (!meta) return;
    const oldComment = meta.querySelector('.comment-btn');
    if (oldComment) oldComment.remove();
    if (meta.querySelector('.interaction-strip')) return;
    const strip = document.createElement('div');
    strip.className = 'interaction-strip';
    strip.innerHTML = `
      <button type="button" data-artwork-action="like" data-artwork-stat="likes">赞 0</button>
      <button type="button" data-artwork-action="comment" data-artwork-stat="comments">评 0</button>
      <button type="button" data-artwork-action="favorite" data-artwork-stat="favorites">藏 0</button>
    `;
    strip.querySelector('[data-artwork-action="like"]').addEventListener('click', event => {
      event.stopPropagation();
      toggleUserInteraction('liked', 'artwork', card.dataset.id);
    });
    strip.querySelector('[data-artwork-action="comment"]').addEventListener('click', event => {
      event.stopPropagation();
      openArtworkDetail(card);
    });
    strip.querySelector('[data-artwork-action="favorite"]').addEventListener('click', event => {
      event.stopPropagation();
      toggleUserInteraction('favorites', 'artwork', card.dataset.id);
    });
    meta.appendChild(strip);
  });
  updateCommentButtons();
};

function updateInteractionDisplays() {
  updateCommentButtons();
  renderInspirationInteractionDisplays();
}

async function fetchArtworkReviews(cardId) {
  const data = await apiRequest(`/reviews/?artwork=${encodeURIComponent(cardId)}&page_size=100`);
  return apiList(data);
}

async function renderArtworkComments(cardId) {
  const list = document.getElementById('commentList');
  let items = [];
  try {
    items = await fetchArtworkReviews(cardId);
  } catch (error) {
    const card = getGalleryCard(cardId);
    if (card && card.dataset.saved !== 'true') {
      await ensureArtworkRecords();
      try {
        items = await fetchArtworkReviews(getGalleryCard(cardId)?.dataset.id || cardId);
      } catch (retryError) {
        list.innerHTML = '<div class="empty-state">评价加载失败，请确认后端服务已启动。</div>';
        return;
      }
    } else {
      list.innerHTML = '<div class="empty-state">评价加载失败，请确认后端服务已启动。</div>';
      return;
    }
  }
  const card = getGalleryCard(cardId);
  if (card) {
    document.getElementById('commentCardId').value = card.dataset.id;
    card.dataset.reviewsCount = String(items.length);
    const state = getInteractions();
    state.artwork.comments[card.dataset.id] = items.length;
    saveInteractions(state);
    updateCommentButtons();
  }
  if (!items.length) {
    list.innerHTML = '<div class="empty-state">还没有评价，来留下第一条想法吧。</div>';
    updateCommentButtons();
    return;
  }
  const users = getUsers();
  list.innerHTML = items.map(item => {
    const username = item.reviewer_username || item.owner || 'admin';
    const user = users[username] || { username, profile: {} };
    const name = getDisplayName(user);
    const avatar = user.profile?.avatar || '';
    const avatarHtml = avatar
      ? `<img src="${avatar}" alt="${escapeHTML(name)}">`
      : escapeHTML(name.slice(0, 1).toUpperCase());
    const imageSrc = item.image_url || item.imageSrc || '';
    const imageHtml = imageSrc ? `<img class="comment-image" src="${imageSrc}" alt="评论图片">` : '';
    const likeCount = item.like_count || 0;
    const likedClass = item.liked ? ' liked' : '';
    const reviewId = item.id || '';
    return `
      <div class="comment-item">
        <div class="comment-avatar">${avatarHtml}</div>
        <div class="comment-bubble">
          <button class="comment-author user-profile-link" type="button" data-user-profile="${escapeHTML(username)}">${escapeHTML(name)}</button>
          <div class="comment-text">${escapeHTML(item.content || item.text || '')}</div>
          ${imageHtml}
          <div class="comment-time">${escapeHTML(item.created_at || item.createdAt || '')}</div>
          ${reviewId ? `<button class="comment-like${likedClass}" type="button" onclick="toggleReviewLike('${reviewId}')">赞 ${likeCount}</button>` : ''}
        </div>
      </div>
    `;
  }).join('');
  updateCommentButtons();
}

async function syncOpenArtworkComments() {
  const modal = document.getElementById('artworkDetail');
  const cardId = document.getElementById('commentCardId')?.value;
  if (!modal || modal.classList.contains('hidden') || !cardId || artworkCommentSyncBusy) return;
  artworkCommentSyncBusy = true;
  try {
    await renderArtworkComments(cardId);
  } catch (error) {
    console.warn('Artwork comments sync failed:', error);
  } finally {
    artworkCommentSyncBusy = false;
  }
}

function startArtworkCommentSync() {
  stopArtworkCommentSync();
  artworkCommentSyncTimer = window.setInterval(syncOpenArtworkComments, COMMENT_SYNC_INTERVAL);
}

function stopArtworkCommentSync() {
  if (!artworkCommentSyncTimer) return;
  window.clearInterval(artworkCommentSyncTimer);
  artworkCommentSyncTimer = null;
}

function openArtworkDetail(cardOrId) {
  const card = typeof cardOrId === 'string' ? getGalleryCard(cardOrId) : cardOrId;
  const data = getCardData(card);
  if (!data) return;
  recordView('artwork', data.id);
  document.getElementById('detailTitle').textContent = data.name;
  document.getElementById('detailTag').textContent = data.tag;
  document.getElementById('detailImage').src = data.imageSrc || '';
  document.getElementById('commentCardId').value = data.id;
  document.getElementById('commentText').value = '';
  document.getElementById('commentImageInput').value = '';
  document.getElementById('commentImageName').textContent = '';
  commentImageSrc = '';
  renderArtworkComments(data.id);
  document.getElementById('artworkDetail').classList.remove('hidden');
  startArtworkCommentSync();
}

function closeArtworkDetail() {
  stopArtworkCommentSync();
  document.getElementById('artworkDetail').classList.add('hidden');
  document.getElementById('detailImage').removeAttribute('src');
  document.getElementById('commentCardId').value = '';
  commentImageSrc = '';
}

async function submitArtworkComment() {
  if (!requireLogin('请先登录后再发布评价。')) return;
  const cardId = document.getElementById('commentCardId').value;
  const text = document.getElementById('commentText').value.trim();
  if (!cardId) return;
  if (!text && !commentImageSrc) return alert('请填写评价文字，或选择一张图片。');
  try {
    await apiRequest('/reviews/', {
      method: 'POST',
      body: JSON.stringify({
        artwork: cardId,
        rating: 5,
        content: text,
        image_data: commentImageSrc
      })
    });
  } catch (error) {
    alert(error.message || '发布评价失败，请确认后端服务已启动。');
    return;
  }
  document.getElementById('commentText').value = '';
  document.getElementById('commentImageInput').value = '';
  document.getElementById('commentImageName').textContent = '';
  commentImageSrc = '';
  renderArtworkComments(cardId);
}

async function toggleReviewLike(reviewId) {
  try {
    await apiRequest(`/reviews/${reviewId}/like/`, { method: 'POST', body: JSON.stringify({}) });
    renderArtworkComments(document.getElementById('commentCardId').value);
  } catch (error) {
    alert('点赞失败，请确认后端服务已启动。');
  }
}

function uploadImage(imageContainer) {
  openArtworkDetail(imageContainer.closest('.character-card'));
}

function editArtwork(button) {
  const card = button.closest('.character-card');
  if (!requireCardPermission(card)) return;
  openPublishPage(card.dataset.id);
}

function editMyArtwork(cardId) {
  openPublishPage(cardId);
}

function deleteMyArtwork(cardId) {
  if (!requireLogin('请先登录后再删除作品。')) return;
  const card = getGalleryCard(cardId);
  if (!card || !canEditCard(card)) return alert('你只能删除自己发布的作品。');
  if (!confirm('确定要删除这个作品吗？')) return;
  card.remove();
  saveGallery(false);
  renderMePage();
}

function getGalleryCard(cardId) {
  return Array.from(document.querySelectorAll('.character-card')).find(card => card.dataset.id === String(cardId));
}

function getCardData(card) {
  if (!card) return null;
  const img = card.querySelector('.character-image img');
  return {
    id: card.dataset.id,
    name: card.querySelector('.character-info h3').textContent,
    tag: card.querySelector('.character-tag').textContent,
    imageSrc: img ? img.src : '',
    owner: card.dataset.owner || 'admin',
    original: card.dataset.original === 'true',
    reviewsCount: Number(card.dataset.reviewsCount || 0)
  };
}

function setPublishImage(src = '') {
  publishImageSrc = src;
  const preview = document.getElementById('publishImagePreview');
  const placeholder = document.getElementById('publishImagePlaceholder');
  if (!preview || !placeholder) return;
  if (src) {
    preview.src = src;
    preview.hidden = false;
    placeholder.hidden = true;
  } else {
    preview.removeAttribute('src');
    preview.hidden = true;
    placeholder.hidden = false;
  }
}

function setPublishEditTime(value = '') {
  const group = document.getElementById('publishEditTimeGroup');
  const input = document.getElementById('publishEditTime');
  if (!group || !input) return;
  input.value = value || '';
  group.hidden = !value;
}

function setPublishType(type) {
  const isInspiration = type === 'inspiration';
  document.getElementById('publishType').value = type;
  setPublishEditTime('');
  document.querySelectorAll('[data-publish-type]').forEach(button => {
    button.classList.toggle('active', button.dataset.publishType === type);
  });
  document.querySelector('.publish-layout').classList.toggle('inspiration-mode', isInspiration);
  document.querySelector('.publish-preview').classList.toggle('hidden', isInspiration);
  document.getElementById('publishContentGroup').hidden = !isInspiration;
  document.getElementById('publishPageTitle').textContent = isInspiration ? '发布灵感' : '发布作品';
  document.getElementById('publishPageHint').textContent = isInspiration
    ? '记录创作灵感、过程或心得，并发布到灵感页'
    : '上传图片，填写作品名称和标签后发布到作品页';
  document.getElementById('publishNameLabel').textContent = isInspiration ? '灵感标题' : '作品名称';
  document.getElementById('publishTagLabel').textContent = isInspiration ? '灵感标签' : '作品标签';
  document.getElementById('publishName').placeholder = isInspiration ? '请输入灵感标题' : '请输入作品名称';
  document.getElementById('publishTag').placeholder = isInspiration ? '例如：教程 / 创作过程' : '例如：原创角色 / 魔法少女';
  document.getElementById('publishSubmitBtn').textContent = isInspiration ? '发布灵感' : '发布作品';
}

function openPublishPage(cardId = '') {
  if (!requireLogin('请先登录后再发布作品。')) return;
  const card = cardId ? getGalleryCard(cardId) : null;
  if (card && !canEditCard(card)) return alert('你只能编辑自己发布的作品。');
  const data = getCardData(card);
  document.getElementById('publishImageInput').value = '';
  document.getElementById('publishCardId').value = data?.id || '';
  document.getElementById('publishName').value = data?.name || '';
  document.getElementById('publishTag').value = data?.tag || '';
  document.getElementById('publishContent').value = '';
  setPublishImage(data?.imageSrc || '');
  setPublishType('artwork');
  if (data) {
    document.getElementById('publishPageTitle').textContent = '编辑作品';
    document.getElementById('publishPageHint').textContent = '保留原作品数据，修改后保存发布';
    document.getElementById('publishSubmitBtn').textContent = '保存作品';
  }
  switchPage('publish');
}

function createGalleryCard(data) {
  const grid = document.getElementById('galleryGrid');
  const card = document.createElement('div');
  card.className = 'character-card fade-in visible';
  card.dataset.id = String(data.id);
  card.dataset.owner = data.owner;
  card.dataset.original = String(data.original || false);
  card.dataset.reviewsCount = String(data.reviewsCount || data.reviews_count || 0);
  card.dataset.saved = String(data.saved === true);
  card.dataset.recommendationScore = String(data.recommendationScore || data.recommendation_score || 0);
  const src = normalizeImageSrc(data.imageSrc || data.image_url || data.image || '');
  const imageHtml = src ? `<img src="${escapeHTML(src)}" alt="${escapeHTML(data.name)}">` : '';
  card.innerHTML = `
    <div class="card-actions"></div>
    <div class="character-image" onclick="uploadImage(this)" style="background: linear-gradient(135deg, #ffd6e0, #d4f1f9);">
      ${imageHtml}
      <div class="upload-overlay"><span>📷 点击上传图片</span></div>
      <input type="file" accept="image/*" style="display: none;" onchange="handleImageUpload(event, this.parentElement)">
    </div>
    <div class="character-info">
      <h3 onclick="editName(this)">${escapeHTML(data.name)}</h3>
      <span class="character-tag" onclick="editTag(this)">${escapeHTML(data.tag)}</span>
      <button class="character-owner user-profile-link" type="button" data-user-profile="${escapeHTML(data.owner || 'admin')}">@${escapeHTML(data.owner || 'admin')}</button>
    </div>
  `;
  grid.appendChild(card);
  normalizeCardActions();
  normalizeCommentButtons();
  applyCardPermissions();
  return card;
}

function getGalleryCards() {
  return Array.from(document.querySelectorAll('#galleryGrid .character-card'));
}

function renderGalleryPagination() {
  const grid = document.getElementById('galleryGrid');
  const pagination = document.getElementById('galleryPagination');
  if (!grid || !pagination) return;
  const cards = getGalleryCards();
  galleryVisibleCount = Math.min(Math.max(GALLERY_ITEMS_PER_PAGE, galleryVisibleCount), Math.max(cards.length, GALLERY_ITEMS_PER_PAGE));
  cards.forEach((card, index) => {
    card.hidden = index >= galleryVisibleCount;
  });
  pagination.hidden = false;
  const visible = Math.min(galleryVisibleCount, cards.length);
  const hasHiddenCards = visible < cards.length;
  const text = galleryApiLoading
    ? '正在加载更多推荐...'
    : hasHiddenCards || galleryApiHasMore
      ? `继续上拉查看更多作品（${visible}/${galleryApiHasMore ? `${cards.length}+` : cards.length}）`
      : cards.length
        ? `已经看完当前推荐（${cards.length} 个作品）`
        : '暂无作品';
  pagination.innerHTML = `
    <button type="button" class="gallery-page-btn" data-gallery-load-more ${(!hasHiddenCards && !galleryApiHasMore) || galleryApiLoading ? 'disabled' : ''}>加载更多</button>
    <span class="gallery-page-info">${text}</span>
  `;
  pagination.querySelector('[data-gallery-load-more]')?.addEventListener('click', loadMoreGalleryItems);
}

function initGalleryPaginationObserver() {
  const grid = document.getElementById('galleryGrid');
  if (!grid || galleryPaginationObserver) return;
  galleryPaginationObserver = new MutationObserver(() => {
    window.requestAnimationFrame(renderGalleryPagination);
  });
  galleryPaginationObserver.observe(grid, { childList: true });
  renderGalleryPagination();
  const pagination = document.getElementById('galleryPagination');
  if ('IntersectionObserver' in window && pagination && !galleryInfiniteObserver) {
    galleryInfiniteObserver = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) loadMoreGalleryItems();
    }, { rootMargin: '520px 0px' });
    galleryInfiniteObserver.observe(pagination);
  }
}

async function loadMoreGalleryItems() {
  if (galleryApiLoading) return;
  const cards = getGalleryCards();
  if (galleryVisibleCount < cards.length) {
    galleryVisibleCount += GALLERY_ITEMS_PER_PAGE;
    renderGalleryPagination();
    return;
  }
  if (galleryApiHasMore) {
    await appendGalleryFromApi();
  }
}

async function savePublishForm() {
  if (!requireLogin('请先登录后再发布作品。')) return;
  const type = document.getElementById('publishType').value;
  const cardId = document.getElementById('publishCardId').value;
  const name = document.getElementById('publishName').value.trim();
  const tag = document.getElementById('publishTag').value.trim();
  if (!name || !tag) return alert(type === 'inspiration' ? '请填写灵感标题和标签。' : '请填写作品名称和标签。');
  if (type === 'inspiration') {
    const content = document.getElementById('publishContent').value.trim();
    if (!content) return alert('请填写灵感内容。');
    const items = getInspirations();
    items.unshift({
      owner: currentUser.username,
      title: name,
      tag,
      content,
      createdAt: new Date().toLocaleDateString()
    });
    saveInspirations(items);
    renderInspirations();
    switchPage('blog');
    document.getElementById('publishForm').reset();
    setPublishType('artwork');
    return;
  }
  let card = cardId ? getGalleryCard(cardId) : null;
  if (card && !canEditCard(card)) return alert('你只能编辑自己发布的作品。');
  if (!card) {
    card = createGalleryCard({
      id: String(cardIdCounter++),
      owner: currentUser.username,
      original: false,
      name,
      tag,
      imageSrc: publishImageSrc
    });
  } else {
    card.querySelector('.character-info h3').textContent = name;
    card.querySelector('.character-tag').textContent = tag;
    const imageBox = card.querySelector('.character-image');
    let img = imageBox.querySelector('img');
    if (publishImageSrc) {
      if (!img) {
        img = document.createElement('img');
        imageBox.insertBefore(img, imageBox.firstChild);
      }
      img.src = publishImageSrc;
    } else if (img) {
      img.remove();
    }
  }
  try {
    await persistArtwork(card);
  } catch (error) {
    alert('作品保存到数据库失败，请确认后端服务已启动。');
    return;
  }
  saveGallery(false);
  renderMePage();
  switchPage('me');
}

function setPublishType(type) {
  const isArtwork = type === 'artwork';
  const isInspiration = type === 'inspiration';
  const isCommission = type === 'commission';
  document.getElementById('publishType').value = type;
  setPublishEditTime('');
  document.querySelectorAll('[data-publish-type]').forEach(button => {
    button.classList.toggle('active', button.dataset.publishType === type);
  });
  document.querySelector('.publish-layout').classList.toggle('inspiration-mode', !isArtwork);
  document.querySelector('.publish-preview').classList.toggle('hidden', !isArtwork);
  document.getElementById('publishContentGroup').hidden = isArtwork;
  document.getElementById('publishBudgetGroup').hidden = !isCommission;
  document.getElementById('publishPageTitle').textContent = isCommission ? '发布委托' : (isInspiration ? '发布灵感' : '发布作品');
  document.getElementById('publishPageHint').textContent = isCommission
    ? '填写委托标题、类型、预算和需求说明后发布到委托大厅'
    : (isInspiration ? '记录创作灵感、过程或心得，并发布到灵感页' : '上传图片，填写作品名称和标签后发布到作品页');
  document.getElementById('publishNameLabel').textContent = isCommission ? '委托标题' : (isInspiration ? '灵感标题' : '作品名称');
  document.getElementById('publishTagLabel').textContent = isCommission ? '委托类型' : (isInspiration ? '灵感标签' : '作品标签');
  document.getElementById('publishContentGroup').querySelector('label').textContent = isCommission ? '需求说明' : '灵感内容';
  document.getElementById('publishContent').placeholder = isCommission ? '描述你希望接单者完成的内容、风格和交付要求' : '记录你的创作想法、过程或心得';
  document.getElementById('publishName').placeholder = isCommission ? '例如：Q版双人头像委托' : (isInspiration ? '请输入灵感标题' : '请输入作品名称');
  document.getElementById('publishTag').placeholder = isCommission ? '例如：头像 / 半身 / Live2D' : (isInspiration ? '例如：教程 / 创作过程' : '例如：原创角色 / 魔法少女');
  document.getElementById('publishSubmitBtn').textContent = isCommission ? '发布委托' : (isInspiration ? '发布灵感' : '发布作品');
}

function openPublishPage(cardId = '') {
  if (!requireLogin('请先登录后再发布内容。')) return;
  const card = cardId ? getGalleryCard(cardId) : null;
  if (card && !canEditCard(card)) return alert('你只能编辑自己发布的作品。');
  const data = getCardData(card);
  document.getElementById('publishImageInput').value = '';
  document.getElementById('publishCardId').value = data?.id || '';
  document.getElementById('publishName').value = data?.name || '';
  document.getElementById('publishTag').value = data?.tag || '';
  document.getElementById('publishContent').value = '';
  document.getElementById('publishBudget').value = '';
  setPublishImage(data?.imageSrc || '');
  setPublishType('artwork');
  if (data) {
    document.getElementById('publishPageTitle').textContent = '编辑作品';
    document.getElementById('publishPageHint').textContent = '保留原作品数据，修改后重新保存';
    document.getElementById('publishSubmitBtn').textContent = '保存作品';
  }
  switchPage('publish');
}

async function savePublishForm() {
  if (!requireLogin('请先登录后再发布内容。')) return;
  const type = document.getElementById('publishType').value;
  const cardId = document.getElementById('publishCardId').value;
  const name = document.getElementById('publishName').value.trim();
  const tag = document.getElementById('publishTag').value.trim();
  const content = document.getElementById('publishContent').value.trim();
  const budget = document.getElementById('publishBudget').value.trim();
  if (!name || !tag) return alert(type === 'commission' ? '请填写委托标题和委托类型。' : (type === 'inspiration' ? '请填写灵感标题和标签。' : '请填写作品名称和标签。'));

  if (type === 'commission') {
    if (!content) return alert('请填写委托需求说明。');
    const commissions = getCommissions();
    commissions.unshift({
      id: `commission-${Date.now()}`,
      requester: currentUser.username,
      artist: '',
      title: name,
      typeLabel: tag,
      description: content,
      budget: budget || '可商议',
      status: 'open',
      createdAt: new Date().toLocaleString()
    });
    saveCommissions(commissions);
    document.getElementById('publishForm').reset();
    setPublishImage('');
    setPublishType('artwork');
    renderCommissionBoard();
    renderMePage();
    switchPage('contact');
    return;
  }

  if (type === 'inspiration') {
    if (!content) return alert('请填写灵感内容。');
    const items = getInspirations();
    items.unshift({
      owner: currentUser.username,
      title: name,
      tag,
      content,
      createdAt: new Date().toLocaleDateString()
    });
    saveInspirations(items);
    renderInspirations();
    document.getElementById('publishForm').reset();
    setPublishImage('');
    setPublishType('artwork');
    switchPage('blog');
    return;
  }

  let card = cardId ? getGalleryCard(cardId) : null;
  if (card && !canEditCard(card)) return alert('你只能编辑自己发布的作品。');
  if (!card) {
    card = createGalleryCard({
      id: String(cardIdCounter++),
      owner: currentUser.username,
      original: false,
      name,
      tag,
      imageSrc: publishImageSrc
    });
  } else {
    card.querySelector('.character-info h3').textContent = name;
    card.querySelector('.character-tag').textContent = tag;
    const imageBox = card.querySelector('.character-image');
    let img = imageBox.querySelector('img');
    if (publishImageSrc) {
      if (!img) {
        img = document.createElement('img');
        imageBox.insertBefore(img, imageBox.firstChild);
      }
      img.src = publishImageSrc;
    } else if (img) {
      img.remove();
    }
  }
  try {
    await persistArtwork(card);
  } catch (error) {
    alert('作品保存到数据库失败，请确认后端服务已启动。');
    return;
  }
  saveGallery(false);
  renderMePage();
  switchPage('me');
}

function handleImageUpload(event, imageContainer) {
  const card = imageContainer.closest('.character-card');
  if (!requireCardPermission(card)) {
    event.target.value = '';
    return;
  }
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(e) {
    let img = imageContainer.querySelector('img');
    if (!img) {
      img = document.createElement('img');
      imageContainer.insertBefore(img, imageContainer.firstChild);
    }
    img.src = e.target.result;
    saveGallery(false);
  };
  reader.readAsDataURL(file);
}

function editName(element) {
  const card = element.closest('.character-card');
  if (!isAdmin()) return;
  openPublishPage(card.dataset.id);
}

function editTag(element) {
  const card = element.closest('.character-card');
  if (!isAdmin()) return;
  openPublishPage(card.dataset.id);
}

function addNewCard() {
  if (!requireLogin('请先登录后再发布作品。')) return;
  const grid = document.getElementById('galleryGrid');
  const newCard = document.createElement('div');
  newCard.className = 'character-card fade-in visible';
  newCard.dataset.id = String(cardIdCounter++);
  newCard.dataset.owner = currentUser.username;
  newCard.dataset.original = 'false';
  const gradients = [
    'linear-gradient(135deg, #ffd6e0, #ffb6c1)',
    'linear-gradient(135deg, #d4f1f9, #b8e6f0)',
    'linear-gradient(135deg, #e6d4f9, #d4b8f0)',
    'linear-gradient(135deg, #f9e6d4, #f0d4b8)',
    'linear-gradient(135deg, #d4f9e6, #b8f0d4)',
    'linear-gradient(135deg, #f9d4e6, #f0b8d4)'
  ];
  const randomGradient = gradients[Math.floor(Math.random() * gradients.length)];
  newCard.innerHTML = `
    <div class="card-actions">
      <button class="card-action-btn delete" onclick="deleteCard(this)" title="删除卡片">🗑️</button>
    </div>
    <div class="character-image" onclick="uploadImage(this)" style="background: ${randomGradient};">
      <div class="upload-overlay"><span>📷 点击上传图片</span></div>
      <input type="file" accept="image/*" style="display: none;" onchange="handleImageUpload(event, this.parentElement)">
    </div>
    <div class="character-info">
      <h3 onclick="editName(this)">新角色</h3>
      <span class="character-tag" onclick="editTag(this)">点击编辑标签</span>
    </div>
  `;
  grid.appendChild(newCard);
  normalizeCardActions();
  normalizeCommentButtons();
  applyCardPermissions();
  saveGallery(false);
  renderMePage();
  newCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function deleteCard(button) {
  const card = button.closest('.character-card');
  if (!requireLogin('请先登录后再删除作品。')) return;
  if (!isAdmin()) {
    alert('作品页删除仅管理员可用，请在“我”的作品列表中删除自己的作品。');
    return;
  }
  if (confirm('确定要删除这个角色卡片吗？')) {
    card.style.transform = 'scale(0.8)';
    card.style.opacity = '0';
    setTimeout(() => {
      card.remove();
      saveGallery(false);
      renderMePage();
    }, 300);
  }
}

function serializeGallery() {
  return Array.from(document.querySelectorAll('.character-card')).map(card => {
    const img = card.querySelector('.character-image img');
    return {
      id: card.dataset.id,
      name: card.querySelector('.character-info h3').textContent,
      tag: card.querySelector('.character-tag').textContent,
      imageSrc: img ? img.src : null,
      owner: card.dataset.owner || 'admin',
      original: card.dataset.original === 'true',
      saved: card.dataset.saved === 'true',
      reviewsCount: Number(card.dataset.reviewsCount || 0),
      recommendationScore: Number(card.dataset.recommendationScore || 0)
    };
  });
}

function saveGallery(showAlert = true) {
  if (!currentUser && showAlert) return openAuth('login', '请先登录后再保存作品。');
  localStorage.setItem(STORAGE.gallery, JSON.stringify(serializeGallery()));
  if (showAlert) alert('画廊已保存！✅');
  renderMePage();
}

async function loadGalleryFromApi() {
  try {
    galleryApiPage = 1;
    galleryVisibleCount = GALLERY_ITEMS_PER_PAGE;
    const { items, hasMore } = await fetchRecommendedArtworkPage(galleryApiPage);
    const grid = document.getElementById('galleryGrid');
    grid.innerHTML = '';
    items.forEach(item => createGalleryCard(artworkToCardData(item)));
    galleryApiHasMore = hasMore;
    galleryApiPage += 1;
    cardIdCounter = Math.max(10, ...items.map(item => Number(item.id)).filter(Boolean)) + 1;
    localStorage.removeItem(STORAGE.gallery);
    renderMePage();
    renderGalleryPagination();
    return true;
  } catch (error) {
    console.warn('Artwork API load failed, falling back to local gallery:', error);
    return false;
  }
}

async function fetchRecommendedArtworkPage(page = 1) {
  const data = await apiRequest(`/artworks/recommendations/?page=${page}&page_size=${GALLERY_API_PAGE_SIZE}`, {
    method: 'POST',
    auth: false,
    body: JSON.stringify(buildArtworkRecommendationPayload())
  });
  return {
    items: apiList(data),
    hasMore: !!data?.next
  };
}

async function appendGalleryFromApi() {
  if (galleryApiLoading || !galleryApiHasMore) return;
  galleryApiLoading = true;
  renderGalleryPagination();
  try {
    const { items, hasMore } = await fetchRecommendedArtworkPage(galleryApiPage);
    const existing = new Set(getGalleryCards().map(card => String(card.dataset.id)));
    items
      .filter(item => !existing.has(String(item.id)))
      .forEach(item => createGalleryCard(artworkToCardData(item)));
    galleryApiHasMore = hasMore;
    galleryApiPage += 1;
    cardIdCounter = Math.max(cardIdCounter, ...items.map(item => Number(item.id)).filter(Boolean), 10) + 1;
  } catch (error) {
    console.warn('More artwork recommendations failed:', error);
    galleryApiHasMore = false;
  } finally {
    galleryApiLoading = false;
    renderMePage();
    renderGalleryPagination();
  }
}

async function refreshGalleryRecommendations() {
  const loaded = await loadGalleryFromApi();
  if (loaded) return;
  const grid = document.getElementById('galleryGrid');
  if (!grid) return;
  const items = sortGalleryDataByRecommendation(serializeGallery());
  galleryVisibleCount = GALLERY_ITEMS_PER_PAGE;
  galleryApiHasMore = false;
  grid.innerHTML = '';
  items.forEach(item => createGalleryCard(item));
  renderGalleryPagination();
}

function loadGallery() {
  const savedData = localStorage.getItem(STORAGE.gallery);
  if (!savedData) return;
  try {
    const galleryData = JSON.parse(savedData);
    const grid = document.getElementById('galleryGrid');
    grid.innerHTML = '';
    const gradients = [
      'linear-gradient(135deg, #ffd6e0, #ffb6c1)',
      'linear-gradient(135deg, #d4f1f9, #b8e6f0)',
      'linear-gradient(135deg, #e6d4f9, #d4b8f0)',
      'linear-gradient(135deg, #f9e6d4, #f0d4b8)',
      'linear-gradient(135deg, #d4f9e6, #b8f0d4)',
      'linear-gradient(135deg, #f9d4e6, #f0b8d4)'
    ];
    galleryVisibleCount = GALLERY_ITEMS_PER_PAGE;
    galleryApiHasMore = false;
    const behaviorWeights = buildBehaviorTagWeights(galleryData);
    sortGalleryDataByRecommendation(galleryData).forEach((data, index) => {
      const card = document.createElement('div');
      card.className = 'character-card fade-in visible';
      card.dataset.id = String(data.id);
      card.dataset.owner = data.owner || (ORIGINAL_CARD_IDS.has(String(data.id)) ? 'admin' : (currentUser?.username || 'admin'));
      card.dataset.original = String(data.original ?? ORIGINAL_CARD_IDS.has(String(data.id)));
      card.dataset.saved = String(data.saved === true);
      card.dataset.reviewsCount = String(data.reviewsCount || 0);
      card.dataset.recommendationScore = String(scoreLocalArtwork(data, behaviorWeights) || 0);
      const imageSrc = normalizeImageSrc(data.imageSrc || '');
      const imageHtml = imageSrc ? `<img src="${escapeHTML(imageSrc)}" alt="${escapeHTML(data.name)}">` : '';
      card.innerHTML = `
        <div class="card-actions">
          <button class="card-action-btn delete" onclick="deleteCard(this)" title="删除卡片">🗑️</button>
        </div>
        <div class="character-image" onclick="uploadImage(this)" style="background: ${gradients[index % gradients.length]};">
          ${imageHtml}
          <div class="upload-overlay"><span>📷 点击上传图片</span></div>
          <input type="file" accept="image/*" style="display: none;" onchange="handleImageUpload(event, this.parentElement)">
        </div>
        <div class="character-info">
          <h3 onclick="editName(this)">${escapeHTML(data.name)}</h3>
          <span class="character-tag" onclick="editTag(this)">${escapeHTML(data.tag)}</span>
          <button class="character-owner user-profile-link" type="button" data-user-profile="${escapeHTML(data.owner || 'admin')}">@${escapeHTML(data.owner || 'admin')}</button>
        </div>
      `;
      grid.appendChild(card);
    });
    normalizeCardActions();
    normalizeCommentButtons();
    cardIdCounter = Math.max(10, ...galleryData.map(d => parseInt(d.id, 10)).filter(Boolean)) + 1;
    renderGalleryPagination();
  } catch (e) {
    console.error('加载画廊数据失败:', e);
  }
}

function renderInspirations() {
  const blogList = document.querySelector('#blog .blog-list');
  if (!blogList) return;
  blogList.querySelectorAll('[data-user-inspiration="true"]').forEach(item => item.remove());
  const items = getInspirations();
  const html = items.map(item => `
    <article class="blog-item fade-in visible" data-user-inspiration="true" data-inspiration-id="${escapeHTML(item.id)}" onclick="openInspirationDetail('${escapeHTML(item.id)}')">
      <span class="blog-date">${escapeHTML(getInspirationDisplayTime(item))}</span>
      <button class="blog-author user-profile-link" type="button" data-user-profile="${escapeHTML(item.owner)}">@${escapeHTML(item.owner)}</button>
      <h3>${escapeHTML(item.title)}</h3>
      <p>${escapeHTML(item.content)}</p>
      <div class="blog-tags">
        <span class="blog-tag">${escapeHTML(item.tag)}</span>
      </div>
    </article>
  `).join('');
  blogList.insertAdjacentHTML('afterbegin', html);
}

function initCommissionPage() {
  const section = document.getElementById('contact');
  if (!section) return;
  const title = section.querySelector('.section-title h2');
  const hint = section.querySelector('.section-title p');
  if (title) title.textContent = '委托大厅';
  if (hint) hint.textContent = '在这里查看公开委托并接受合作';
  const container = section.querySelector('.contact-container');
  if (!container) return;
  container.innerHTML = `
    <div class="commission-status fade-in visible">
      <h3>当前委托</h3>
      <span class="status-badge">✅ 接受委托中</span>
      <div class="commission-summary">
        <div class="commission-stat">
          <strong id="commissionOpenCount">0</strong>
          <span>待接委托</span>
        </div>
        <div class="commission-stat">
          <strong id="commissionAcceptedCount">0</strong>
          <span>已被接受</span>
        </div>
        <div class="commission-stat">
          <strong id="commissionMineCount">0</strong>
          <span>与我相关</span>
        </div>
      </div>
    </div>
    <div class="commission-board fade-in visible" id="commissionBoard">
      <div class="commission-empty">暂时还没有公开委托，先去发布页创建一个吧。</div>
    </div>
  `;
}

function acceptCommission(commissionId) {
  if (!requireLogin('请先登录后再接受委托。')) return;
  const commissions = getCommissions();
  const item = commissions.find(entry => entry.id === commissionId);
  if (!item) return;
  if (item.requester === currentUser.username) return alert('不能接受自己发布的委托。');
  if (item.status !== 'open') return alert('这个委托已经被接受了。');
  item.artist = currentUser.username;
  item.status = 'accepted';
  saveCommissions(commissions);
  renderCommissionBoard();
  renderMePage();
}

function renderCommissionBoard() {
  const board = document.getElementById('commissionBoard');
  if (!board) return;
  const commissions = getCommissions();
  const openCount = commissions.filter(item => item.status === 'open').length;
  const acceptedCount = commissions.filter(item => item.status === 'accepted').length;
  const mineCount = currentUser
    ? commissions.filter(item => item.requester === currentUser.username || item.artist === currentUser.username).length
    : 0;
  const openEl = document.getElementById('commissionOpenCount');
  const acceptedEl = document.getElementById('commissionAcceptedCount');
  const mineEl = document.getElementById('commissionMineCount');
  if (openEl) openEl.textContent = openCount;
  if (acceptedEl) acceptedEl.textContent = acceptedCount;
  if (mineEl) mineEl.textContent = mineCount;

  if (!commissions.length) {
    board.innerHTML = '<div class="commission-empty">暂时还没有公开委托，先去发布页创建一个吧。</div>';
    return;
  }

  const users = getUsers();
  board.innerHTML = commissions.map(item => {
    const requesterUser = users[item.requester] || { username: item.requester };
    const requesterName = getDisplayName(requesterUser);
    const artistUser = item.artist ? (users[item.artist] || { username: item.artist }) : null;
    const artistName = artistUser ? getDisplayName(artistUser) : '';
    const minePill = currentUser && (item.requester === currentUser.username || item.artist === currentUser.username)
      ? '<span class="commission-pill mine">与我相关</span>'
      : '';
    const actionHtml = canAcceptCommission(item)
      ? `<button type="button" class="commission-btn" onclick="acceptCommission('${escapeHTML(item.id)}')">接受委托</button>`
      : `<button type="button" class="commission-btn secondary" disabled>${item.artist ? `接单人：${escapeHTML(artistName)}` : '等待接单'}</button>`;
    return `
      <article class="commission-card">
        <div class="commission-card-head">
          <div>
            <h3>${escapeHTML(item.title)}</h3>
            <div class="commission-meta">
              <span>发布者：${escapeHTML(requesterName)}</span>
              <span>类型：${escapeHTML(item.typeLabel)}</span>
              <span>预算：${escapeHTML(item.budget)}</span>
              <span>${escapeHTML(item.createdAt)}</span>
            </div>
          </div>
          <div>
            <span class="commission-pill${item.status === 'accepted' ? ' accepted' : ''}">${getCommissionStatusLabel(item.status)}</span>
            ${minePill}
          </div>
        </div>
        <div class="commission-desc">${escapeHTML(item.description)}</div>
        <div class="commission-actions">${actionHtml}</div>
      </article>
    `;
  }).join('');
}

function renderMePage() {
  if (!currentUser) return;
  const users = getUsers();
  const user = users[currentUser.username];
  if (!user) return;

  const profile = user.profile || {};
  const myCards = serializeGallery().filter(card => card.owner === currentUser.username);
  const commissions = getCommissions().filter(item => item.requester === currentUser.username || item.artist === currentUser.username);
  const displayName = getDisplayName(user);
  const signature = getIntro(user);
  const philosophy = getPhilosophy(user);
  editingSkills = [...getSkills(user)];

  document.getElementById('profileDisplayNameInput').value = profile.displayName || displayName;
  document.getElementById('profileUsername').value = user.username || '';
  document.getElementById('profileEmail').value = user.email || '';
  document.getElementById('profileGender').value = profile.gender || '';
  document.getElementById('profileBirthday').value = profile.birthday || '';
  document.getElementById('profileCreativeYearsInput').value = profile.creativeYears || '';
  document.getElementById('profileSignature').value = signature;
  document.getElementById('profilePhilosophy').value = philosophy;
  const homeTags = getHomeTags(user);
  const homeTagsInput = document.getElementById('profileHomeTags');
  if (homeTagsInput) homeTagsInput.value = homeTags.join('、');
  renderHomeTagPreview('profileHomeTagList', homeTags);
  document.getElementById('resetEmail').value = user.email || '';

  const avatar = document.getElementById('profileAvatar');
  const avatarEdit = document.getElementById('profileAvatarEdit');
  const display = document.getElementById('profileDisplayName');
  const handle = document.getElementById('profileHandle');
  const bio = document.getElementById('profileBio');
  const introTitle = document.getElementById('profileIntroTitle');
  const introText = document.getElementById('profileIntroText');
  const philosophyText = document.getElementById('profilePhilosophyText');
  const artworkCount = document.getElementById('profileArtworkCount');
  const commissionCount = document.getElementById('profileCommissionCount');
  const creativeYears = document.getElementById('profileCreativeYears');

  setAvatarElement(avatar, profile.avatar || '', displayName);
  setAvatarElement(avatarEdit, profile.avatar || '', displayName);
  if (display) display.textContent = displayName;
  if (handle) handle.textContent = '@' + user.username;
  if (bio) bio.textContent = signature;
  if (introTitle) introTitle.textContent = `你好，我是${displayName}`;
  if (introText) introText.textContent = signature;
  if (philosophyText) philosophyText.textContent = `创作理念：${philosophy}`;
  renderSkillList('profileSkillList', editingSkills);
  renderSkillList('profileSkillEditorList', editingSkills, true);
  if (artworkCount) artworkCount.textContent = myCards.length;
  if (commissionCount) commissionCount.textContent = commissions.length;
  if (creativeYears) creativeYears.textContent = profile.creativeYears || '0';

  document.getElementById('myArtworkList').innerHTML = myCards.length
    ? myCards.map(card => {
      const imageHtml = card.imageSrc
        ? `<img src="${escapeHTML(card.imageSrc)}" alt="${escapeHTML(card.name)}">`
        : '<span>暂无图片</span>';
      return `<div class="mini-item artwork-mini">
        <div class="mini-thumb">${imageHtml}</div>
        <div class="mini-body">
          <strong>${escapeHTML(card.name)}</strong>
          <span>${escapeHTML(card.tag)} · ${card.original ? '原页面画作' : '新发布作品'}</span>
        </div>
        <div class="mini-actions">
          <button type="button" class="mini-edit-btn" onclick="editMyArtwork('${escapeHTML(card.id)}')">编辑</button>
          <button type="button" class="mini-edit-btn mini-danger-btn" onclick="deleteMyArtwork('${escapeHTML(card.id)}')">删除</button>
        </div>
      </div>`;
    }).join('')
    : '<div class="empty-state">还没有发布画作。</div>';

  document.getElementById('myCommissionList').innerHTML = commissions.length
    ? commissions.map(item => `<div class="mini-item"><strong>${escapeHTML(item.typeLabel)}</strong><span>${escapeHTML(item.message)} · ${escapeHTML(item.createdAt)}</span></div>`).join('')
    : '<div class="empty-state">还没有作画委托。</div>';
}

function refreshMyCommissionList(commissions) {
  if (!currentUser) return;
  document.getElementById('myCommissionList').innerHTML = commissions.length
    ? commissions.map(item => {
      const role = item.requester === currentUser.username ? '我发布的委托' : '我接受的委托';
      const partner = item.requester === currentUser.username ? (item.artist || '暂未接单') : item.requester;
      return `<div class="mini-item"><strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(role)} · ${escapeHTML(item.typeLabel)} · ${getCommissionStatusLabel(item.status)} · ${escapeHTML(partner)} · ${escapeHTML(item.createdAt)}</span></div>`;
    }).join('')
    : '<div class="empty-state">还没有与你相关的委托。</div>';
}

const baseRenderMePage = renderMePage;
renderMePage = function() {
  baseRenderMePage();
  if (!currentUser) return;
  refreshMyCommissionList(
    getCommissions().filter(item => item.requester === currentUser.username || item.artist === currentUser.username)
  );
};

function refreshMyCommissionList(commissions) {
  if (!currentUser) return;
  document.getElementById('myCommissionList').innerHTML = commissions.length
    ? commissions.map(item => {
      const role = item.requester === currentUser.username ? '我发布的委托' : '我接受的委托';
      const partner = item.requester === currentUser.username ? (item.artist || '暂未接单') : item.requester;
      return `<div class="mini-item"><strong>${escapeHTML(item.title)}</strong><span>${escapeHTML(role)} · ${escapeHTML(item.typeLabel)} · ${getCommissionStatusLabel(item.status)} · ${escapeHTML(partner)} · ${escapeHTML(item.createdAt)}</span></div>`;
    }).join('')
    : '<div class="empty-state">还没有与你相关的委托。</div>';
}

function normalizeCommissionItem(item, index) {
  const legacy = !('requester' in item) && ('owner' in item || 'message' in item || 'typeLabel' in item);
  if (legacy) {
    return {
      id: item.id || `legacy-${index + 1}`,
      requester: 'admin',
      artist: '',
      title: item.typeLabel || '管理员公开委托',
      typeLabel: item.typeLabel || '公开委托',
      description: item.message || '',
      budget: item.budget || '可商议',
      status: 'open',
      createdAt: item.createdAt || new Date().toLocaleString(),
      acceptedAt: '',
      abandonRequestedAt: ''
    };
  }
  return {
    id: item.id || `commission-${Date.now()}-${index}`,
    requester: item.requester || 'admin',
    artist: item.artist || '',
    title: item.title || '未命名委托',
    typeLabel: item.typeLabel || item.tag || '委托',
    description: item.description || '',
    budget: item.budget || '可商议',
    status: item.status || (item.artist ? 'accepted' : 'open'),
    createdAt: item.createdAt || new Date().toLocaleString(),
    acceptedAt: item.acceptedAt || '',
    abandonRequestedAt: item.abandonRequestedAt || ''
  };
}

function getCommissionStatusLabel(status) {
  if (status === 'accepted') return '已接受';
  if (status === 'abandon_requested') return '申请放弃中';
  if (status === 'completed') return '已完成';
  return '待接单';
}

function openCommissionEditor(commissionId) {
  if (!requireLogin('请先登录后再编辑委托。')) return;
  const item = getCommissions().find(entry => entry.id === commissionId);
  if (!item) return;
  if (item.requester !== currentUser.username) return alert('只能编辑自己发布的委托。');
  if (item.status !== 'open') return alert('已被接受的委托不能编辑。');
  editingCommissionId = item.id;
  document.getElementById('publishImageInput').value = '';
  document.getElementById('publishCardId').value = '';
  document.getElementById('publishName').value = item.title;
  document.getElementById('publishTag').value = item.typeLabel;
  document.getElementById('publishContent').value = item.description;
  document.getElementById('publishBudget').value = item.budget;
  setPublishImage('');
  setPublishType('commission');
  document.getElementById('publishPageTitle').textContent = '编辑委托';
  document.getElementById('publishSubmitBtn').textContent = '保存委托';
  switchPage('publish');
}

function deleteCommission(commissionId) {
  if (!requireLogin('请先登录后再删除委托。')) return;
  const commissions = getCommissions();
  const item = commissions.find(entry => entry.id === commissionId);
  if (!item) return;
  if (item.requester !== currentUser.username && !isAdmin()) return alert('只能删除自己发布的委托。');
  if (item.status !== 'open') return alert('已被接受的委托不能删除。');
  if (!confirm('确定要删除这个委托吗？')) return;
  saveCommissions(commissions.filter(entry => entry.id !== commissionId));
  renderCommissionBoard();
  renderMePage();
}

function abandonCommission(commissionId) {
  if (!requireLogin('请先登录后再放弃委托。')) return;
  const commissions = getCommissions();
  const item = commissions.find(entry => entry.id === commissionId);
  if (!item) return;
  if (item.artist !== currentUser.username) return alert('只有接单人可以放弃委托。');
  if (item.status !== 'accepted') return alert('当前委托不能申请放弃。');
  const acceptedAt = item.acceptedAt ? new Date(item.acceptedAt).getTime() : 0;
  const withinOneHour = acceptedAt && (Date.now() - acceptedAt <= 60 * 60 * 1000);
  if (withinOneHour) {
    item.artist = '';
    item.status = 'open';
    item.acceptedAt = '';
    item.abandonRequestedAt = '';
  } else {
    item.status = 'abandon_requested';
    item.abandonRequestedAt = new Date().toISOString();
  }
  saveCommissions(commissions);
  renderCommissionBoard();
  renderMePage();
}

function resolveAbandonRequest(commissionId, approved) {
  if (!requireLogin('请先登录后再处理放弃申请。')) return;
  const commissions = getCommissions();
  const item = commissions.find(entry => entry.id === commissionId);
  if (!item) return;
  if (item.requester !== currentUser.username && !isAdmin()) return alert('只有发布委托的人可以处理放弃申请。');
  if (item.status !== 'abandon_requested') return;
  if (approved) {
    item.artist = '';
    item.status = 'open';
    item.acceptedAt = '';
  } else {
    item.status = 'accepted';
  }
  item.abandonRequestedAt = '';
  saveCommissions(commissions);
  renderCommissionBoard();
  renderMePage();
}

function acceptCommission(commissionId) {
  if (!requireLogin('请先登录后再接受委托。')) return;
  const commissions = getCommissions();
  const item = commissions.find(entry => entry.id === commissionId);
  if (!item) return;
  if (item.requester === currentUser.username) return alert('不能接受自己发布的委托。');
  if (item.status !== 'open') return alert('这个委托已经被接受了。');
  item.artist = currentUser.username;
  item.status = 'accepted';
  item.acceptedAt = new Date().toISOString();
  item.abandonRequestedAt = '';
  saveCommissions(commissions);
  renderCommissionBoard();
  renderMePage();
}

function commissionActionHtml(item, artistName) {
  const buttons = [];
  if (canAcceptCommission(item)) {
    buttons.push(`<button type="button" class="commission-btn" onclick="acceptCommission('${escapeHTML(item.id)}')">接受委托</button>`);
  }
  if (currentUser && item.requester === currentUser.username && item.status === 'open') {
    buttons.push(`<button type="button" class="commission-btn secondary" onclick="openCommissionEditor('${escapeHTML(item.id)}')">编辑</button>`);
    buttons.push(`<button type="button" class="commission-btn secondary" onclick="deleteCommission('${escapeHTML(item.id)}')">删除</button>`);
  }
  if (currentUser && item.artist === currentUser.username && item.status === 'accepted') {
    buttons.push(`<button type="button" class="commission-btn secondary" onclick="abandonCommission('${escapeHTML(item.id)}')">放弃委托</button>`);
  }
  if (currentUser && item.requester === currentUser.username && item.status === 'abandon_requested') {
    buttons.push(`<button type="button" class="commission-btn" onclick="resolveAbandonRequest('${escapeHTML(item.id)}', true)">同意放弃</button>`);
    buttons.push(`<button type="button" class="commission-btn secondary" onclick="resolveAbandonRequest('${escapeHTML(item.id)}', false)">拒绝放弃</button>`);
  }
  if (!buttons.length) {
    buttons.push(`<button type="button" class="commission-btn secondary" disabled>${item.artist ? `接单人：${escapeHTML(artistName)}` : '等待接单'}</button>`);
  }
  return buttons.join('');
}

renderCommissionBoard = function() {
  const board = document.getElementById('commissionBoard');
  if (!board) return;
  const commissions = getCommissions();
  const openCount = commissions.filter(item => item.status === 'open').length;
  const acceptedCount = commissions.filter(item => item.status === 'accepted' || item.status === 'abandon_requested').length;
  const mineCount = currentUser
    ? commissions.filter(item => item.requester === currentUser.username || item.artist === currentUser.username).length
    : 0;
  const openEl = document.getElementById('commissionOpenCount');
  const acceptedEl = document.getElementById('commissionAcceptedCount');
  const mineEl = document.getElementById('commissionMineCount');
  if (openEl) openEl.textContent = openCount;
  if (acceptedEl) acceptedEl.textContent = acceptedCount;
  if (mineEl) mineEl.textContent = mineCount;
  if (!commissions.length) {
    board.innerHTML = '<div class="commission-empty">暂时还没有公开委托，先去发布页创建一个吧。</div>';
    return;
  }
  const users = getUsers();
  board.innerHTML = commissions.map(item => {
    const requesterUser = users[item.requester] || { username: item.requester };
    const requesterName = getDisplayName(requesterUser);
    const artistUser = item.artist ? (users[item.artist] || { username: item.artist }) : null;
    const artistName = artistUser ? getDisplayName(artistUser) : '';
    const minePill = currentUser && (item.requester === currentUser.username || item.artist === currentUser.username)
      ? '<span class="commission-pill mine">与我相关</span>'
      : '';
    const pendingClass = item.status === 'abandon_requested' ? ' pending' : '';
    return `
      <article class="commission-card">
        <div class="commission-card-head">
          <div>
            <h3>${escapeHTML(item.title)}</h3>
            <div class="commission-meta">
              <span>发布者：${escapeHTML(requesterName)}</span>
              <span>类型：${escapeHTML(item.typeLabel)}</span>
              <span>预算：${escapeHTML(item.budget)}</span>
              <span>${escapeHTML(item.createdAt)}</span>
            </div>
          </div>
          <div>
            <span class="commission-pill${item.status === 'accepted' ? ' accepted' : ''}${pendingClass}">${getCommissionStatusLabel(item.status)}</span>
            ${minePill}
          </div>
        </div>
        <div class="commission-desc">${escapeHTML(item.description)}</div>
        <div class="commission-actions">${commissionActionHtml(item, artistName)}</div>
      </article>
    `;
  }).join('');
};

const commissionAwareSavePublishForm = savePublishForm;
savePublishForm = async function() {
  const type = document.getElementById('publishType').value;
  if (type !== 'commission') return commissionAwareSavePublishForm();
  if (!requireLogin('请先登录后再发布委托。')) return;
  const name = document.getElementById('publishName').value.trim();
  const tag = document.getElementById('publishTag').value.trim();
  const content = document.getElementById('publishContent').value.trim();
  const budget = document.getElementById('publishBudget').value.trim();
  if (!name || !tag) return alert('请填写委托标题和委托类型。');
  if (!content) return alert('请填写委托需求说明。');
  const commissions = getCommissions();
  if (editingCommissionId) {
    const item = commissions.find(entry => entry.id === editingCommissionId);
    if (!item) return;
    if (item.status !== 'open') return alert('已被接受的委托不能编辑。');
    item.title = name;
    item.typeLabel = tag;
    item.description = content;
    item.budget = budget || '可商议';
  } else {
    commissions.unshift({
      id: `commission-${Date.now()}`,
      requester: currentUser.username,
      artist: '',
      title: name,
      typeLabel: tag,
      description: content,
      budget: budget || '可商议',
      status: 'open',
      createdAt: new Date().toLocaleString(),
      acceptedAt: '',
      abandonRequestedAt: ''
    });
  }
  editingCommissionId = '';
  saveCommissions(commissions);
  document.getElementById('publishForm').reset();
  setPublishImage('');
  setPublishType('artwork');
  renderCommissionBoard();
  renderMePage();
  switchPage('contact');
};

const commissionAwareOpenPublishPage = openPublishPage;
openPublishPage = function(cardId = '') {
  editingCommissionId = '';
  commissionAwareOpenPublishPage(cardId);
};

const commissionAwareSetPublishType = setPublishType;
setPublishType = function(type) {
  if (type !== 'commission') editingCommissionId = '';
  commissionAwareSetPublishType(type);
};

document.getElementById('publishCancelBtn')?.addEventListener('click', () => {
  editingCommissionId = '';
});

refreshMyCommissionList = function(commissions) {
  if (!currentUser) return;
  document.getElementById('myCommissionList').innerHTML = commissions.length
    ? commissions.map(item => {
      const role = item.requester === currentUser.username ? '我发布的委托' : '我接受的委托';
      const partner = item.requester === currentUser.username ? (item.artist || '暂未接单') : item.requester;
      const actions = [];
      if (item.requester === currentUser.username && item.status === 'open') {
        actions.push(`<button type="button" class="mini-edit-btn" onclick="openCommissionEditor('${escapeHTML(item.id)}')">编辑</button>`);
        actions.push(`<button type="button" class="mini-edit-btn mini-danger-btn" onclick="deleteCommission('${escapeHTML(item.id)}')">删除</button>`);
      }
      if (item.artist === currentUser.username && item.status === 'accepted') {
        actions.push(`<button type="button" class="mini-edit-btn" onclick="abandonCommission('${escapeHTML(item.id)}')">放弃</button>`);
      }
      if (item.requester === currentUser.username && item.status === 'abandon_requested') {
        actions.push(`<button type="button" class="mini-edit-btn" onclick="resolveAbandonRequest('${escapeHTML(item.id)}', true)">同意放弃</button>`);
        actions.push(`<button type="button" class="mini-edit-btn mini-danger-btn" onclick="resolveAbandonRequest('${escapeHTML(item.id)}', false)">拒绝</button>`);
      }
      return `<div class="mini-item">
        <strong>${escapeHTML(item.title)}</strong>
        <span>${escapeHTML(role)} · ${escapeHTML(item.typeLabel)} · ${getCommissionStatusLabel(item.status)} · ${escapeHTML(partner)} · ${escapeHTML(item.createdAt)}</span>
        ${actions.length ? `<div class="mini-actions">${actions.join('')}</div>` : ''}
      </div>`;
    }).join('')
    : '<div class="empty-state">还没有与你相关的委托。</div>';
};

function formatCommissionTime(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function commissionFromApi(item, index = 0) {
  return normalizeCommissionItem({
    id: String(item.id || `commission-${Date.now()}-${index}`),
    requester: item.requester_username || item.requester || 'admin',
    artist: item.artist_username || item.artist || '',
    title: item.title || '未命名委托',
    typeLabel: item.type_label || item.typeLabel || '委托',
    description: item.description || '',
    budget: item.budget || item.budget_note || '可商议',
    status: item.status === 'submitted' ? 'open' : (item.status || 'open'),
    createdAt: formatCommissionTime(item.created_at) || new Date().toLocaleString(),
    acceptedAt: item.accepted_at || '',
    abandonRequestedAt: item.abandon_requested_at || ''
  }, index);
}

function commissionToApiPayload(item) {
  return {
    title: item.title,
    type_label: item.typeLabel,
    description: item.description,
    budget: item.budget || '可商议'
  };
}

async function migrateLegacyCommissionsToApi() {
  if (localStorage.getItem('starSakuraCommissionsMigrated') === 'true') return;
  if (!currentUser) return;
  if (!commissionMigrationPromise) {
    commissionMigrationPromise = (async () => {
      const legacy = JSON.parse(localStorage.getItem(STORAGE.commissions) || '[]').map(normalizeCommissionItem);
      for (const item of legacy) {
        await apiRequest('/custom/', {
          method: 'POST',
          body: JSON.stringify(commissionToApiPayload(item))
        });
      }
      localStorage.setItem('starSakuraCommissionsMigrated', 'true');
    })().finally(() => {
      commissionMigrationPromise = null;
    });
  }
  return commissionMigrationPromise;
}

async function loadCommissionsFromApi() {
  const data = await apiRequest('/custom/?page_size=100&ordering=-created_at');
  let items = apiList(data);
  if (!items.length) {
    await migrateLegacyCommissionsToApi();
    items = apiList(await apiRequest('/custom/?page_size=100&ordering=-created_at'));
  }
  commissionCache = items.map(commissionFromApi);
  return commissionCache;
}

getCommissions = function() {
  if (commissionCache.length) return commissionCache;
  return JSON.parse(localStorage.getItem(STORAGE.commissions) || '[]').map(normalizeCommissionItem);
};

saveCommissions = function(commissions) {
  commissionCache = commissions.map(normalizeCommissionItem);
  localStorage.setItem(STORAGE.commissions, JSON.stringify(commissionCache));
};

async function refreshCommissions() {
  try {
    await loadCommissionsFromApi();
  } catch (error) {
    console.warn('Commission API unavailable:', error);
  }
  renderCommissionBoard();
  if (currentUser) renderMePage();
}

openCommissionEditor = function(commissionId) {
  if (!requireLogin('请先登录后再编辑委托。')) return;
  const item = getCommissions().find(entry => String(entry.id) === String(commissionId));
  if (!item) return;
  if (item.requester !== currentUser.username) return alert('只能编辑自己发布的委托。');
  if (item.status !== 'open') return alert('已被接受的委托不能编辑。');
  editingCommissionId = item.id;
  document.getElementById('publishImageInput').value = '';
  document.getElementById('publishCardId').value = '';
  document.getElementById('publishName').value = item.title;
  document.getElementById('publishTag').value = item.typeLabel;
  document.getElementById('publishContent').value = item.description;
  document.getElementById('publishBudget').value = item.budget;
  setPublishImage('');
  setPublishType('commission');
  document.getElementById('publishPageTitle').textContent = '编辑委托';
  document.getElementById('publishSubmitBtn').textContent = '保存委托';
  switchPage('publish');
};

deleteCommission = async function(commissionId) {
  if (!requireLogin('请先登录后再删除委托。')) return;
  const item = getCommissions().find(entry => String(entry.id) === String(commissionId));
  if (!item) return;
  if (item.requester !== currentUser.username && !isAdmin()) return alert('只能删除自己发布的委托。');
  if (item.status !== 'open') return alert('已被接受的委托不能删除。');
  if (!confirm('确定要删除这个委托吗？')) return;
  try {
    await apiRequest(`/custom/${commissionId}/`, { method: 'DELETE' });
    await refreshCommissions();
  } catch (error) {
    alert(error.message || '删除委托失败，请确认后端服务已启动。');
  }
};

acceptCommission = async function(commissionId) {
  if (!requireLogin('请先登录后再接受委托。')) return;
  const item = getCommissions().find(entry => String(entry.id) === String(commissionId));
  if (item?.requester === currentUser.username) return alert('不能接受自己发布的委托。');
  if (item && item.status !== 'open') return alert('这个委托已经被接受了。');
  try {
    await apiRequest(`/custom/${commissionId}/accept/`, { method: 'POST', body: JSON.stringify({}) });
    await refreshCommissions();
  } catch (error) {
    alert(error.message || '接受委托失败，请确认后端服务已启动。');
  }
};

abandonCommission = async function(commissionId) {
  if (!requireLogin('请先登录后再放弃委托。')) return;
  try {
    await apiRequest(`/custom/${commissionId}/abandon/`, { method: 'POST', body: JSON.stringify({}) });
    await refreshCommissions();
  } catch (error) {
    alert(error.message || '放弃委托失败，请确认后端服务已启动。');
  }
};

resolveAbandonRequest = async function(commissionId, approved) {
  if (!requireLogin('请先登录后再处理放弃申请。')) return;
  try {
    await apiRequest(`/custom/${commissionId}/resolve_abandon/`, {
      method: 'POST',
      body: JSON.stringify({ approved })
    });
    await refreshCommissions();
  } catch (error) {
    alert(error.message || '处理放弃申请失败，请确认后端服务已启动。');
  }
};

renderCommissionBoard = async function() {
  const board = document.getElementById('commissionBoard');
  if (!board) return;
  if (!commissionCache.length) {
    try {
      await loadCommissionsFromApi();
    } catch (error) {
      console.warn('Commission API unavailable:', error);
    }
  }
  const commissions = getCommissions();
  const openCount = commissions.filter(item => item.status === 'open').length;
  const acceptedCount = commissions.filter(item => item.status === 'accepted' || item.status === 'abandon_requested').length;
  const mineCount = currentUser
    ? commissions.filter(item => item.requester === currentUser.username || item.artist === currentUser.username).length
    : 0;
  const openEl = document.getElementById('commissionOpenCount');
  const acceptedEl = document.getElementById('commissionAcceptedCount');
  const mineEl = document.getElementById('commissionMineCount');
  if (openEl) openEl.textContent = openCount;
  if (acceptedEl) acceptedEl.textContent = acceptedCount;
  if (mineEl) mineEl.textContent = mineCount;
  if (!commissions.length) {
    board.innerHTML = '<div class="commission-empty">暂时还没有公开委托，先去发布页创建一个吧。</div>';
    return;
  }
  const users = getUsers();
  board.innerHTML = commissions.map(item => {
    const requesterUser = users[item.requester] || { username: item.requester };
    const requesterName = getDisplayName(requesterUser);
    const artistUser = item.artist ? (users[item.artist] || { username: item.artist }) : null;
    const artistName = artistUser ? getDisplayName(artistUser) : '';
    const minePill = currentUser && (item.requester === currentUser.username || item.artist === currentUser.username)
      ? '<span class="commission-pill mine">与我相关</span>'
      : '';
    const pendingClass = item.status === 'abandon_requested' ? ' pending' : '';
    return `
      <article class="commission-card">
        <div class="commission-card-head">
          <div>
            <h3>${escapeHTML(item.title)}</h3>
            <div class="commission-meta">
              <span>发布者：${escapeHTML(requesterName)}</span>
              <span>类型：${escapeHTML(item.typeLabel)}</span>
              <span>预算：${escapeHTML(item.budget)}</span>
              <span>${escapeHTML(item.createdAt)}</span>
            </div>
          </div>
          <div>
            <span class="commission-pill${item.status === 'accepted' ? ' accepted' : ''}${pendingClass}">${getCommissionStatusLabel(item.status)}</span>
            ${minePill}
          </div>
        </div>
        <div class="commission-desc">${escapeHTML(item.description)}</div>
        <div class="commission-actions">${commissionActionHtml(item, artistName)}</div>
      </article>
    `;
  }).join('');
};

savePublishForm = async function() {
  const type = document.getElementById('publishType').value;
  if (type !== 'commission') return commissionAwareSavePublishForm();
  if (!requireLogin('请先登录后再发布委托。')) return;
  const name = document.getElementById('publishName').value.trim();
  const tag = document.getElementById('publishTag').value.trim();
  const content = document.getElementById('publishContent').value.trim();
  const budget = document.getElementById('publishBudget').value.trim();
  if (!name || !tag) return alert('请填写委托标题和委托类型。');
  if (!content) return alert('请填写委托需求说明。');
  const payload = commissionToApiPayload({
    requester: currentUser.username,
    title: name,
    typeLabel: tag,
    description: content,
    budget: budget || '可商议'
  });
  try {
    if (editingCommissionId) {
      await apiRequest(`/custom/${editingCommissionId}/`, { method: 'PATCH', body: JSON.stringify(payload) });
    } else {
      await apiRequest('/custom/', { method: 'POST', body: JSON.stringify(payload) });
    }
    editingCommissionId = '';
    document.getElementById('publishForm').reset();
    setPublishImage('');
    setPublishType('artwork');
    await refreshCommissions();
    switchPage('contact');
  } catch (error) {
    alert(error.message || '保存委托失败，请确认后端服务已启动。');
  }
};

function updatePassword(newPassword, confirmPassword, verifier) {
  if (!currentUser) return;
  const error = validatePasswordPair(newPassword, confirmPassword, '新密码');
  if (error) return setSettingsMessage(error);
  const users = getUsers();
  const user = users[currentUser.username];
  const verifyError = verifier(user);
  if (verifyError) return setSettingsMessage(verifyError);
  user.password = newPassword;
  saveUsers(users);
  setSettingsMessage('密码已修改，请记住新密码。');
}

let inspirationCache = [];
let inspirationCommentCache = [];
let activeInspirationId = '';
let inspirationReplyTarget = '';
let inspirationCommentSyncTimer = null;
let inspirationCommentSyncBusy = false;
let profileDataRefreshPromise = null;
let profileArtworkDataLoaded = false;
let profileCommissionDataLoaded = false;
let profileInspirationDataLoaded = false;
const expandedInspirationReplies = new Set();

function normalizeProfile(profile = {}, username = '') {
  return {
    displayName: username,
    avatar: '',
    intro: '',
    philosophy: '',
    skills: [],
    gender: '',
    birthday: '',
    creativeYears: '',
    signature: '',
    homeTags: [],
    ...profile
  };
}

function normalizeUserSession(user = {}, tokens = {}) {
  const profile = normalizeProfile(user.profile || {}, user.username || '');
  return {
    id: user.id,
    username: user.username,
    email: user.email || '',
    role: user.is_admin ? 'admin' : (user.role || 'user'),
    is_admin: !!user.is_admin,
    profile,
    access: tokens.access || user.access || currentUser?.access || '',
    refresh: tokens.refresh || user.refresh || currentUser?.refresh || ''
  };
}

function storeSession(user, tokens = {}) {
  currentUser = normalizeUserSession(user, tokens);
  localStorage.setItem(STORAGE.currentUser, JSON.stringify(currentUser));
  localStorage.setItem(STORAGE.authTokens, JSON.stringify({ access: currentUser.access, refresh: currentUser.refresh }));
  localStorage.removeItem(STORAGE.users);
  return currentUser;
}

function clearSession() {
  currentUser = null;
  localStorage.removeItem(STORAGE.currentUser);
  localStorage.removeItem(STORAGE.authTokens);
}

async function fetchCurrentUser() {
  const user = await apiRequest('/users/me/');
  return storeSession(user, JSON.parse(localStorage.getItem(STORAGE.authTokens) || '{}'));
}

async function restoreCurrentUserSession() {
  if (!currentUser?.access) return null;
  try {
    return await fetchCurrentUser();
  } catch (error) {
    console.warn('Session restore failed:', error);
    clearSession();
    return null;
  }
}

getUsers = function() {
  const users = {};
  if (currentUser?.username) users[currentUser.username] = normalizeUserSession(currentUser);
  return users;
};

saveUsers = function(users) {
  if (!currentUser?.username) return;
  const user = users[currentUser.username] || currentUser;
  currentUser = normalizeUserSession({ ...currentUser, ...user, profile: normalizeProfile(user.profile || {}, user.username) });
  localStorage.setItem(STORAGE.currentUser, JSON.stringify(currentUser));
  apiRequest('/users/me/', {
    method: 'PATCH',
    body: JSON.stringify({
      email: currentUser.email || '',
      profile: currentUser.profile || {}
    })
  }).catch(error => {
    console.warn('Profile sync failed:', error);
    setSettingsMessage('个人信息暂时没有同步到数据库，请确认后端服务已启动。');
  });
};

handleLogin = async function(username, password) {
  username = String(username || '').trim().normalize('NFKC');
  password = String(password || '').trim();
  try {
    const tokens = await apiRequest('/users/login/', {
      method: 'POST',
      auth: false,
      body: JSON.stringify({ username, password })
    });
    localStorage.setItem(STORAGE.authTokens, JSON.stringify(tokens));
    const user = await apiRequest('/users/me/', {
      headers: { Authorization: `Bearer ${tokens.access}` }
    });
    storeSession(user, tokens);
    setAuthMessage('');
    await Promise.allSettled([migrateLegacyInspirationsToApi(), migrateLegacyCommissionsToApi()]);
    refreshAuthUI();
    await refreshCommissions();
    await renderInspirations();
    switchPage('me');
  } catch (error) {
    setAuthMessage(error.message || '用户名或密码不正确。');
  }
};

registerUser = async function(formData) {
  const username = formData.username.trim();
  const email = formData.email.trim().toLowerCase();
  if (!username) return setAuthMessage('请输入用户名。');
  const passwordError = validatePasswordPair(formData.password, formData.passwordConfirm, '用户密码');
  if (passwordError) return setAuthMessage(passwordError);
  try {
    await apiRequest('/users/register/', {
      method: 'POST',
      body: JSON.stringify({ username, email, password: formData.password })
    });
    await handleLogin(username, formData.password);
  } catch (error) {
    setAuthMessage(error.message || '注册失败，请换一个用户名或邮箱。');
  }
};

refreshAuthUI = function() {
  const navAvatar = document.getElementById('navUserAvatar');
  const navName = document.getElementById('navUserName');
  const user = currentUser ? normalizeUserSession(currentUser) : null;
  const displayName = user ? getDisplayName(user) : '未登录';
  setAvatarElement(navAvatar, user?.profile?.avatar || '', displayName);
  if (navName) navName.textContent = displayName;
  if (currentUser && document.getElementById('auth')?.classList.contains('active')) switchPage('me');
  normalizeCardActions();
  applyCardPermissions();
  renderMePage();
};

updatePassword = async function(newPassword, confirmPassword) {
  if (!currentUser) return;
  const error = validatePasswordPair(newPassword, confirmPassword, '新密码');
  if (error) return setSettingsMessage(error);
  const oldPassword = document.getElementById('oldPassword')?.value || '';
  if (!oldPassword) {
    return setSettingsMessage('出于安全考虑，前端不再保存邮箱密码。请使用旧密码修改。');
  }
  try {
    await apiRequest('/users/password/', {
      method: 'POST',
      body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
    });
    setSettingsMessage('密码已修改，请使用新密码重新登录。');
    clearSession();
    openAuth('login', '密码已修改，请重新登录。');
    refreshAuthUI();
  } catch (error) {
    setSettingsMessage(error.message || '密码修改失败，请检查旧密码。');
  }
};

function inspirationFromApi(item) {
  return {
    id: String(item.id),
    owner: item.owner_username || item.owner || '',
    title: item.title || '',
    tag: item.tag || '',
    content: item.content || '',
    createdAt: item.created_at ? new Date(item.created_at).toLocaleDateString() : new Date().toLocaleDateString(),
    updatedAt: item.updated_at ? new Date(item.updated_at).toLocaleString() : ''
  };
}

function getInspirationDisplayTime(item) {
  return item?.updatedAt || item?.createdAt || '';
}

function inspirationCommentFromApi(item) {
  return {
    id: String(item.id),
    parent: item.parent ? String(item.parent) : '',
    reviewer: item.reviewer_username || item.reviewer || '',
    content: item.content || '',
    likeCount: Number(item.like_count || 0),
    liked: !!item.liked,
    createdAt: item.created_at ? new Date(item.created_at).toLocaleString() : ''
  };
}

async function loadInspirationsFromApi() {
  const data = await apiRequest('/inspirations/?page_size=100&ordering=-created_at');
  inspirationCache = apiList(data).map(inspirationFromApi);
  return inspirationCache;
}

getInspirations = function() {
  return inspirationCache;
};

saveInspirations = function(items) {
  inspirationCache = items;
};

async function migrateLegacyInspirationsToApi() {
  if (!currentUser || localStorage.getItem('starSakuraInspirationsMigrated') === 'true') return;
  const legacy = JSON.parse(localStorage.getItem(STORAGE.inspirations) || '[]')
    .filter(item => !item.owner || item.owner === currentUser.username);
  for (const item of legacy) {
    await apiRequest('/inspirations/', {
      method: 'POST',
      body: JSON.stringify({
        title: item.title || item.name || 'Untitled inspiration',
        tag: item.tag || '',
        content: item.content || item.description || ''
      })
    });
  }
  localStorage.removeItem(STORAGE.inspirations);
  localStorage.setItem('starSakuraInspirationsMigrated', 'true');
}

renderInspirations = async function() {
  const blogList = document.querySelector('#blog .blog-list');
  if (!blogList) return;
  try {
    await loadInspirationsFromApi();
  } catch (error) {
    console.warn('Inspiration API unavailable:', error);
  }
  blogList.innerHTML = '';
  const html = getInspirations().map(item => `
    <article class="blog-item fade-in visible" data-user-inspiration="true" data-inspiration-id="${escapeHTML(item.id)}" onclick="openInspirationDetail('${escapeHTML(item.id)}')">
      <span class="blog-date">${escapeHTML(getInspirationDisplayTime(item))}</span>
      <button class="blog-author user-profile-link" type="button" data-user-profile="${escapeHTML(item.owner)}">@${escapeHTML(item.owner)}</button>
      <h3>${escapeHTML(item.title)}</h3>
      <p>${escapeHTML(item.content)}</p>
      <div class="blog-tags">
        <span class="blog-tag">${escapeHTML(item.tag)}</span>
      </div>
    </article>
  `).join('');
  blogList.innerHTML = html || '<div class="empty-state">暂无灵感日志</div>';
};

function getInspirationById(id) {
  return getInspirations().find(item => String(item.id) === String(id));
}

const baseRenderInspirationsWithApi = renderInspirations;
renderInspirations = async function() {
  await baseRenderInspirationsWithApi();
  const blogList = document.querySelector('#blog .blog-list');
  if (!blogList) return;
  const items = getInspirations();
  blogList.innerHTML = items.length ? items.map(item => `
    <article class="blog-item fade-in visible" data-user-inspiration="true" data-inspiration-id="${escapeHTML(item.id)}" onclick="openInspirationDetail('${escapeHTML(item.id)}')">
      <span class="blog-date">${escapeHTML(getInspirationDisplayTime(item))}</span>
      <button class="blog-author user-profile-link" type="button" data-user-profile="${escapeHTML(item.owner)}">@${escapeHTML(item.owner)}</button>
      <h3>${escapeHTML(item.title)}</h3>
      <p>${escapeHTML(item.content)}</p>
      <div class="blog-tags">
        <span class="blog-tag">${escapeHTML(item.tag || '灵感')}</span>
      </div>
      <div class="interaction-strip inspiration-strip">
        <span data-inspiration-stat="views">浏览 0</span>
        <button type="button" data-inspiration-action="like" data-inspiration-stat="likes">赞 0</button>
        <span data-inspiration-stat="comments">评 0</span>
        <button type="button" data-inspiration-action="favorite" data-inspiration-stat="favorites">藏 0</button>
      </div>
    </article>
  `).join('') : '<div class="empty-state">暂无灵感日志</div>';
  blogList.querySelectorAll('[data-inspiration-action]').forEach(button => {
    button.addEventListener('click', event => {
      event.stopPropagation();
      const article = button.closest('[data-inspiration-id]');
      const kind = button.dataset.inspirationAction === 'favorite' ? 'favorites' : 'liked';
      toggleUserInteraction(kind, 'inspiration', article.dataset.inspirationId);
    });
  });
  renderInspirationInteractionDisplays();
};

function renderInspirationInteractionDisplays() {
  document.querySelectorAll('[data-inspiration-id]').forEach(article => {
    const id = article.dataset.inspirationId;
    const counts = getInteractionCounts('inspiration', id);
    const view = article.querySelector('[data-inspiration-stat="views"]');
    const like = article.querySelector('[data-inspiration-stat="likes"]');
    const comment = article.querySelector('[data-inspiration-stat="comments"]');
    const favorite = article.querySelector('[data-inspiration-stat="favorites"]');
    if (view) view.textContent = `浏览 ${counts.views}`;
    if (like) {
      like.textContent = `赞 ${counts.likes}`;
      like.classList.toggle('active', userHasInteraction('liked', 'inspiration', id));
    }
    if (comment) comment.textContent = `评 ${counts.comments}`;
    if (favorite) {
      favorite.textContent = `藏 ${counts.favorites}`;
      favorite.classList.toggle('active', userHasInteraction('favorites', 'inspiration', id));
    }
  });
}

async function fetchInspirationComments(inspirationId) {
  const data = await apiRequest(`/inspirations/${encodeURIComponent(inspirationId)}/comments/`);
  inspirationCommentCache = apiList(data).map(inspirationCommentFromApi);
  return inspirationCommentCache;
}

function renderInspirationReplyForm(parentId) {
  return '';
}

function updateInspirationComposer() {
  const textEl = document.getElementById('inspirationCommentText');
  const hintEl = document.getElementById('inspirationReplyHint');
  const cancelBtn = document.getElementById('cancelInspirationReplyBtn');
  const submitBtn = document.querySelector('#inspirationCommentForm .submit-btn');
  const target = inspirationReplyTarget
    ? inspirationCommentCache.find(item => String(item.id) === String(inspirationReplyTarget))
    : null;
  if (textEl) {
    textEl.placeholder = target ? `回复 ${target.reviewer || '这条评价'}` : '留下你对这条灵感的评价';
  }
  if (hintEl) {
    hintEl.textContent = target ? `正在回复：${target.reviewer || '这条评价'}` : '支持对评价回复，最多 2 层';
  }
  if (cancelBtn) cancelBtn.hidden = !target;
  if (submitBtn) submitBtn.textContent = target ? '发布回复' : '发布评价';
}

function renderInspirationCommentItem(item, isReply = false) {
  const users = getUsers();
  const user = users[item.reviewer] || { username: item.reviewer, profile: {} };
  const name = getDisplayName(user) || item.reviewer || '访客';
  const avatar = user.profile?.avatar || '';
  const avatarHtml = avatar ? `<img src="${escapeHTML(avatar)}" alt="${escapeHTML(name)}">` : escapeHTML((name || '?').slice(0, 1));
  const likedClass = item.liked ? ' liked' : '';
  return `
    <div class="comment-item${isReply ? ' reply' : ''}">
      <div class="comment-avatar">${avatarHtml}</div>
      <div class="comment-bubble">
        <button class="comment-author user-profile-link" type="button" data-user-profile="${escapeHTML(item.reviewer || '')}">${escapeHTML(name)}</button>
        <div class="comment-text">${escapeHTML(item.content)}</div>
        <div class="comment-time">${escapeHTML(item.createdAt)}</div>
        <button class="comment-like${likedClass}" type="button" onclick="toggleInspirationCommentLike('${escapeHTML(item.id)}')">赞 ${item.likeCount}</button>
        ${isReply ? '' : `<button class="comment-reply" type="button" onclick="showInspirationReply('${escapeHTML(item.id)}')">回复</button>`}
      </div>
      ${isReply ? '' : renderInspirationReplyForm(item.id)}
    </div>
  `;
}

function renderInspirationComments() {
  const list = document.getElementById('inspirationCommentList');
  if (!list) return;
  if (activeInspirationId) {
    const state = getInteractions();
    state.inspiration.comments[activeInspirationId] = inspirationCommentCache.length;
    saveInteractions(state);
    renderInspirationInteractionDisplays();
  }
  const rootComments = inspirationCommentCache.filter(item => !item.parent);
  const repliesByParent = inspirationCommentCache.reduce((acc, item) => {
    if (!item.parent) return acc;
    if (!acc[item.parent]) acc[item.parent] = [];
    acc[item.parent].push(item);
    return acc;
  }, {});
  const countEl = document.getElementById('inspirationCommentCount');
  if (countEl) countEl.textContent = `${inspirationCommentCache.length} 条`;
  if (!rootComments.length) {
    list.innerHTML = '<div class="empty-state">暂无评价，来写下第一条吧。</div>';
    updateInspirationComposer();
    return;
  }
  list.innerHTML = rootComments.map(item => {
    const replies = repliesByParent[item.id] || [];
    const expanded = expandedInspirationReplies.has(item.id);
    const visibleReplies = replies.slice(0, expanded ? 20 : 6);
    const expandHtml = replies.length > 6
      ? `<button class="comment-expand" type="button" onclick="toggleInspirationReplies('${escapeHTML(item.id)}')">${expanded ? '收起回复' : `展开更多回复（${Math.min(replies.length, 20)}）`}</button>`
      : '';
    return `
      ${renderInspirationCommentItem(item)}
      ${visibleReplies.length ? `<div class="comment-replies">${visibleReplies.map(reply => renderInspirationCommentItem(reply, true)).join('')}${expandHtml}</div>` : ''}
    `;
  }).join('');
  updateInspirationComposer();
}

async function syncOpenInspirationComments() {
  const modal = document.getElementById('inspirationDetail');
  if (!modal || modal.classList.contains('hidden') || !activeInspirationId || inspirationCommentSyncBusy) return;
  inspirationCommentSyncBusy = true;
  try {
    await fetchInspirationComments(activeInspirationId);
    renderInspirationComments();
  } catch (error) {
    console.warn('Inspiration comments sync failed:', error);
  } finally {
    inspirationCommentSyncBusy = false;
  }
}

function startInspirationCommentSync() {
  stopInspirationCommentSync();
  inspirationCommentSyncTimer = window.setInterval(syncOpenInspirationComments, COMMENT_SYNC_INTERVAL);
}

function stopInspirationCommentSync() {
  if (!inspirationCommentSyncTimer) return;
  window.clearInterval(inspirationCommentSyncTimer);
  inspirationCommentSyncTimer = null;
}

async function openInspirationDetail(inspirationId) {
  const item = getInspirationById(inspirationId);
  if (!item) return;
  recordView('inspiration', inspirationId);
  activeInspirationId = String(inspirationId);
  inspirationReplyTarget = '';
  document.getElementById('inspirationDetailTitle').textContent = item.title;
  document.getElementById('inspirationDetailTag').textContent = item.tag || '灵感';
  const inspirationOwner = document.getElementById('inspirationDetailOwner');
  inspirationOwner.textContent = item.owner ? `作者：${item.owner}` : '';
  inspirationOwner.classList.toggle('user-profile-link', !!item.owner);
  if (item.owner) inspirationOwner.dataset.userProfile = item.owner;
  else delete inspirationOwner.dataset.userProfile;
  document.getElementById('inspirationDetailDate').textContent = getInspirationDisplayTime(item) ? `时间：${getInspirationDisplayTime(item)}` : '';
  document.getElementById('inspirationDetailContent').textContent = item.content;
  document.getElementById('inspirationCommentId').value = activeInspirationId;
  document.getElementById('inspirationCommentText').value = '';
  updateInspirationComposer();
  document.getElementById('inspirationDetail').classList.remove('hidden');
  try {
    await fetchInspirationComments(activeInspirationId);
  } catch (error) {
    console.warn('Inspiration comments API unavailable:', error);
    inspirationCommentCache = [];
  }
  const state = getInteractions();
  state.inspiration.comments[activeInspirationId] = inspirationCommentCache.length;
  saveInteractions(state);
  renderInspirationComments();
  startInspirationCommentSync();
}

function closeInspirationDetail() {
  stopInspirationCommentSync();
  document.getElementById('inspirationDetail').classList.add('hidden');
  activeInspirationId = '';
  inspirationReplyTarget = '';
  inspirationCommentCache = [];
  updateInspirationComposer();
}

async function submitInspirationComment(parentId = '') {
  if (!activeInspirationId) return;
  if (!requireLogin('请先登录后再发布评价。')) return;
  const replyParentId = parentId || inspirationReplyTarget || '';
  const textEl = document.getElementById('inspirationCommentText');
  const content = textEl?.value.trim() || '';
  if (!content) return alert('请填写评价内容。');
  await apiRequest(`/inspirations/${encodeURIComponent(activeInspirationId)}/comments/`, {
    method: 'POST',
    body: JSON.stringify({ content, parent: replyParentId || null })
  });
  if (textEl) textEl.value = '';
  inspirationReplyTarget = '';
  await fetchInspirationComments(activeInspirationId);
  renderInspirationComments();
}

function submitInspirationReply(event, parentId) {
  event.preventDefault();
  submitInspirationComment(parentId);
}

function showInspirationReply(parentId) {
  if (!requireLogin('请先登录后再回复评价。')) return;
  inspirationReplyTarget = String(parentId);
  renderInspirationComments();
  updateInspirationComposer();
  setTimeout(() => document.getElementById('inspirationCommentText')?.focus(), 0);
}

function cancelInspirationReply() {
  inspirationReplyTarget = '';
  renderInspirationComments();
  updateInspirationComposer();
}

function toggleInspirationReplies(parentId) {
  if (expandedInspirationReplies.has(parentId)) expandedInspirationReplies.delete(parentId);
  else expandedInspirationReplies.add(parentId);
  renderInspirationComments();
}

async function toggleInspirationCommentLike(commentId) {
  if (!requireLogin('请先登录后再点赞评价。')) return;
  await apiRequest(`/inspirations/${encodeURIComponent(activeInspirationId)}/comments/${encodeURIComponent(commentId)}/like/`, {
    method: 'POST',
    body: JSON.stringify({})
  });
  await fetchInspirationComments(activeInspirationId);
  renderInspirationComments();
}

commissionToApiPayload = function(item) {
  return {
    title: item.title,
    type_label: item.typeLabel,
    description: item.description,
    budget: item.budget || '可商议'
  };
};

migrateLegacyCommissionsToApi = async function() {
  if (!currentUser || localStorage.getItem('starSakuraCommissionsMigrated') === 'true') return;
  const legacy = JSON.parse(localStorage.getItem(STORAGE.commissions) || '[]')
    .map(normalizeCommissionItem)
    .filter(item => !item.requester || item.requester === currentUser.username || item.requester === 'admin');
  for (const item of legacy) {
    await apiRequest('/custom/', {
      method: 'POST',
      body: JSON.stringify(commissionToApiPayload({ ...item, requester: currentUser.username }))
    });
  }
  localStorage.removeItem(STORAGE.commissions);
  localStorage.setItem('starSakuraCommissionsMigrated', 'true');
};

getCommissions = function() {
  return commissionCache;
};

saveCommissions = function(commissions) {
  commissionCache = commissions.map(normalizeCommissionItem);
};

function canManageInspiration(item) {
  return !!currentUser && !!item && (item.owner === currentUser.username || isAdmin());
}

function refreshMyInspirationList() {
  const list = document.getElementById('myInspirationList');
  if (!list || !currentUser) return;
  const items = getInspirations().filter(item => item.owner === currentUser.username);
  list.innerHTML = items.length
    ? items.map(item => `
      <div class="mini-item">
        <div class="mini-body">
          <strong>${escapeHTML(item.title)}</strong>
          <span>${escapeHTML(item.tag || '灵感')} · ${escapeHTML(getInspirationDisplayTime(item))}</span>
        </div>
        <div class="mini-actions">
          <button type="button" class="mini-edit-btn" onclick="openInspirationDetail('${escapeHTML(item.id)}')">查看</button>
          <button type="button" class="mini-edit-btn" onclick="editMyInspiration('${escapeHTML(item.id)}')">编辑</button>
          <button type="button" class="mini-edit-btn mini-danger-btn" onclick="deleteMyInspiration('${escapeHTML(item.id)}')">删除</button>
        </div>
      </div>
    `).join('')
    : '<div class="empty-state">还没有发布灵感。</div>';
}

async function ensureInspirationsLoaded() {
  if (getInspirations().length) return;
  try {
    await loadInspirationsFromApi();
  } catch (error) {
    console.warn('Inspiration API unavailable:', error);
  }
}

function resolveInteractionItem(key) {
  const [type, id] = String(key).split(':');
  if (type === 'artwork') {
    const card = getCardData(getGalleryCard(id));
    if (!card) return null;
    return { type, id, title: card.name, subtitle: card.tag, imageSrc: card.imageSrc || '', meta: '作品' };
  }
  if (type === 'inspiration') {
    const item = getInspirationById(id);
    if (!item) return null;
    return { type, id, title: item.title, subtitle: item.content, imageSrc: '', meta: `灵感 · ${item.tag || ''}` };
  }
  return null;
}

function renderInteractionMiniList(targetId, keys, emptyText) {
  const list = document.getElementById(targetId);
  if (!list) return;
  const items = (keys || []).map(resolveInteractionItem).filter(Boolean);
  list.innerHTML = items.length ? items.map(item => `
    <div class="mini-item interaction-mini" data-profile-interaction-type="${escapeHTML(item.type)}" data-profile-interaction-id="${escapeHTML(item.id)}">
      <div class="mini-thumb">${item.imageSrc ? `<img src="${escapeHTML(item.imageSrc)}" alt="${escapeHTML(item.title)}">` : `<span>${escapeHTML(item.meta.slice(0, 2))}</span>`}</div>
      <div class="mini-body">
        <strong>${escapeHTML(item.title)}</strong>
        <span>${escapeHTML(item.meta)} · ${escapeHTML(item.subtitle || '')}</span>
      </div>
    </div>
  `).join('') : `<div class="empty-state">${escapeHTML(emptyText)}</div>`;
}

function refreshProfileInteractionLists() {
  if (!currentUser) return;
  const state = getInteractions();
  const bucket = getUserInteractionBucket(state);
  renderInteractionMiniList('myHistoryList', bucket?.history || [], '还没有浏览记录。');
  renderInteractionMiniList('myLikeList', bucket?.liked || [], '还没有点赞内容。');
  renderInteractionMiniList('myFavoriteList', bucket?.favorites || [], '还没有收藏内容。');
}

function insertMiniStats(actions, counts, comments) {
  if (!actions) return;
  actions.querySelectorAll('.mini-stat').forEach(item => item.remove());
  const html = `
    <span class="mini-stat">浏览 ${counts.views}</span>
    <span class="mini-stat">赞 ${counts.likes}</span>
    <span class="mini-stat">评 ${comments}</span>
    <span class="mini-stat">藏 ${counts.favorites}</span>
  `;
  actions.insertAdjacentHTML('afterbegin', html);
}

function refreshProfileContentStats() {
  document.querySelectorAll('#myArtworkList .artwork-mini').forEach(item => {
    const editButton = item.querySelector('[onclick^="editMyArtwork"]');
    const match = editButton?.getAttribute('onclick')?.match(/editMyArtwork\('([^']+)'\)/);
    if (!match) return;
    const id = match[1];
    const card = serializeGallery().find(entry => String(entry.id) === String(id));
    const counts = getInteractionCounts('artwork', id);
    insertMiniStats(item.querySelector('.mini-actions'), counts, Number(card?.reviewsCount || counts.comments || 0));
  });
  document.querySelectorAll('#myInspirationList .mini-item').forEach(item => {
    const viewButton = item.querySelector('[onclick^="openInspirationDetail"]');
    const match = viewButton?.getAttribute('onclick')?.match(/openInspirationDetail\('([^']+)'\)/);
    if (!match) return;
    const id = match[1];
    const counts = getInteractionCounts('inspiration', id);
    insertMiniStats(item.querySelector('.mini-actions'), counts, counts.comments);
  });
}

const inspirationAwareRenderMePage = renderMePage;
renderMePage = function() {
  inspirationAwareRenderMePage();
  refreshMyInspirationList();
  refreshProfileInteractionLists();
  refreshProfileContentStats();
  ensureInspirationsLoaded().then(() => {
    refreshMyInspirationList();
    refreshProfileInteractionLists();
    refreshProfileContentStats();
  });
};

async function ensureProfileDataLoaded() {
  if (!currentUser) return;
  if (profileDataRefreshPromise) return profileDataRefreshPromise;
  profileDataRefreshPromise = Promise.allSettled([
    profileArtworkDataLoaded
      ? Promise.resolve()
      : loadGalleryFromApi().then(() => { profileArtworkDataLoaded = true; }),
    profileCommissionDataLoaded
      ? Promise.resolve()
      : loadCommissionsFromApi().then(() => { profileCommissionDataLoaded = true; }),
    profileInspirationDataLoaded
      ? Promise.resolve()
      : loadInspirationsFromApi().then(() => { profileInspirationDataLoaded = true; })
  ]).then(() => {
    refreshMyCommissionList(
      getCommissions().filter(item => item.requester === currentUser.username || item.artist === currentUser.username)
    );
    refreshMyInspirationList();
    inspirationAwareRenderMePage();
    refreshProfileInteractionLists();
    refreshProfileContentStats();
  }).catch(error => {
    console.warn('Profile data refresh failed:', error);
  }).finally(() => {
    profileDataRefreshPromise = null;
  });
  return profileDataRefreshPromise;
}

const dataAwareRenderMePage = renderMePage;
renderMePage = function() {
  dataAwareRenderMePage();
  ensureProfileDataLoaded();
};

function editMyInspiration(inspirationId) {
  if (!requireLogin('请先登录后再编辑灵感。')) return;
  const item = getInspirationById(inspirationId);
  if (!canManageInspiration(item)) return alert('只能编辑自己发布的灵感。');
  editingCommissionId = '';
  document.getElementById('publishImageInput').value = '';
  document.getElementById('publishName').value = item.title || '';
  document.getElementById('publishTag').value = item.tag || '';
  document.getElementById('publishContent').value = item.content || '';
  document.getElementById('publishBudget').value = '';
  setPublishImage('');
  setPublishType('inspiration');
  document.getElementById('publishCardId').value = item.id;
  setPublishEditTime(getInspirationDisplayTime(item));
  document.getElementById('publishPageTitle').textContent = '编辑灵感';
  document.getElementById('publishSubmitBtn').textContent = '保存灵感';
  switchPage('publish');
}

async function deleteMyInspiration(inspirationId) {
  if (!requireLogin('请先登录后再删除灵感。')) return;
  const item = getInspirationById(inspirationId);
  if (!canManageInspiration(item)) return alert('只能删除自己发布的灵感。');
  if (!confirm('确定要删除这条灵感吗？')) return;
  try {
    await apiRequest(`/inspirations/${encodeURIComponent(inspirationId)}/`, { method: 'DELETE' });
    await renderInspirations();
    renderMePage();
  } catch (error) {
    alert(error.message || '删除灵感失败，请确认后端服务已启动。');
  }
}

const secureSavePublishForm = savePublishForm;
savePublishForm = async function() {
  const type = document.getElementById('publishType').value;
  if (type !== 'inspiration') return secureSavePublishForm();
  if (!requireLogin('请先登录后再发布灵感。')) return;
  const inspirationId = document.getElementById('publishCardId').value;
  const title = document.getElementById('publishName').value.trim();
  const tag = document.getElementById('publishTag').value.trim();
  const content = document.getElementById('publishContent').value.trim();
  if (!title || !tag) return alert('请填写灵感标题和标签。');
  if (!content) return alert('请填写灵感内容。');
  try {
    await apiRequest(inspirationId ? `/inspirations/${encodeURIComponent(inspirationId)}/` : '/inspirations/', {
      method: inspirationId ? 'PATCH' : 'POST',
      body: JSON.stringify({ title, tag, content })
    });
    document.getElementById('publishForm').reset();
    setPublishImage('');
    document.getElementById('publishCardId').value = '';
    setPublishType('artwork');
    await renderInspirations();
    renderMePage();
    switchPage(inspirationId ? 'me' : 'blog');
  } catch (error) {
    alert(error.message || '灵感保存到数据库失败，请确认后端服务已启动。');
  }
};

const searchState = {
  query: '',
  filter: 'all',
  loading: false,
  results: {
    artworks: [],
    commissions: [],
    inspirations: []
  }
};

function normalizeSearchValue(value = '') {
  return String(value || '').trim().toLowerCase();
}

function textMatchesKeyword(values, keyword) {
  const needle = normalizeSearchValue(keyword);
  return values.some(value => normalizeSearchValue(value).includes(needle));
}

function mergeById(primary, secondary) {
  const seen = new Set();
  return [...primary, ...secondary].filter(item => {
    const key = String(item.id || item.title || item.name || Math.random());
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function localArtworkSearch(query) {
  return serializeGallery().filter(item => textMatchesKeyword([item.name, item.tag, item.owner], query));
}

function localCommissionSearch(query) {
  if (!currentUser) return [];
  return getCommissions().filter(item => textMatchesKeyword([
    item.title,
    item.typeLabel,
    item.description,
    item.budget,
    item.requester,
    item.artist,
    getCommissionStatusLabel(item.status)
  ], query));
}

function localInspirationSearch(query) {
  return getInspirations().filter(item => textMatchesKeyword([item.title, item.tag, item.content, item.owner], query));
}

async function fetchSearchResults(query) {
  const encoded = encodeURIComponent(query);
  const [artworks, commissions, inspirations] = await Promise.allSettled([
    apiRequest(`/artworks/?search=${encoded}&page_size=50&ordering=-created_at`).then(data => apiList(data).map(artworkToCardData)),
    currentUser
      ? apiRequest(`/custom/?search=${encoded}&page_size=50&ordering=-created_at`).then(data => apiList(data).map(commissionFromApi))
      : Promise.resolve([]),
    apiRequest(`/inspirations/?search=${encoded}&page_size=50&ordering=-created_at`).then(data => apiList(data).map(inspirationFromApi))
  ]);
  return {
    artworks: mergeById(artworks.status === 'fulfilled' ? artworks.value : [], localArtworkSearch(query)),
    commissions: mergeById(commissions.status === 'fulfilled' ? commissions.value : [], localCommissionSearch(query)),
    inspirations: mergeById(inspirations.status === 'fulfilled' ? inspirations.value : [], localInspirationSearch(query))
  };
}

function searchResultCount() {
  return searchState.results.artworks.length
    + searchState.results.commissions.length
    + searchState.results.inspirations.length;
}

function getVisibleSearchResults() {
  if (searchState.filter === 'all') {
    return [
      ...searchState.results.artworks.map(item => ({ type: 'artworks', item })),
      ...searchState.results.commissions.map(item => ({ type: 'commissions', item })),
      ...searchState.results.inspirations.map(item => ({ type: 'inspirations', item }))
    ];
  }
  return searchState.results[searchState.filter].map(item => ({ type: searchState.filter, item }));
}

function renderSearchCard(result) {
  const { type, item } = result;
  if (type === 'artworks') {
    const imageHtml = item.imageSrc ? `<img src="${escapeHTML(item.imageSrc)}" alt="${escapeHTML(item.name)}">` : '作品';
    return `<article class="search-result-card" data-search-result-type="artworks" data-search-result-id="${escapeHTML(item.id)}">
      <div class="search-result-media">${imageHtml}</div>
      <div class="search-result-body">
        <div class="search-result-head">
          <span class="search-result-type">作品</span>
          <h3>${escapeHTML(item.name)}</h3>
        </div>
        <p class="search-result-desc">${escapeHTML(item.name)} 是由 @${escapeHTML(item.owner || 'admin')} 发布的作品。</p>
        <div class="search-result-meta">
          <button class="user-profile-link" type="button" data-user-profile="${escapeHTML(item.owner || 'admin')}">作者 @${escapeHTML(item.owner || 'admin')}</button>
          <span>评价 ${Number(item.reviewsCount || 0)} 条</span>
        </div>
        <div class="search-result-tags"><span>${escapeHTML(item.tag || '原创作品')}</span></div>
      </div>
    </article>`;
  }
  if (type === 'commissions') {
    return `<article class="search-result-card" data-search-result-type="commissions" data-search-result-id="${escapeHTML(item.id)}">
      <div class="search-result-media">委托</div>
      <div class="search-result-body">
        <div class="search-result-head">
          <span class="search-result-type">委托</span>
          <h3>${escapeHTML(item.title)}</h3>
        </div>
        <p class="search-result-desc">${escapeHTML(item.description || '暂无需求说明')}</p>
        <div class="search-result-meta">
          <button class="user-profile-link" type="button" data-user-profile="${escapeHTML(item.requester || 'admin')}">发布者 @${escapeHTML(item.requester || 'admin')}</button>
          ${item.artist ? `<button class="user-profile-link" type="button" data-user-profile="${escapeHTML(item.artist)}">接单者 @${escapeHTML(item.artist)}</button>` : '<span>接单者 暂未接单</span>'}
          <span>${escapeHTML(item.createdAt || '')}</span>
        </div>
        <div class="search-result-tags">
          <span>${escapeHTML(item.typeLabel || '委托')}</span>
          <span>${escapeHTML(item.budget || '可商议')}</span>
          <span>${getCommissionStatusLabel(item.status)}</span>
        </div>
      </div>
    </article>`;
  }
  return `<article class="search-result-card" data-search-result-type="inspirations" data-search-result-id="${escapeHTML(item.id)}">
    <div class="search-result-media">灵感</div>
    <div class="search-result-body">
      <div class="search-result-head">
        <span class="search-result-type">灵感</span>
        <h3>${escapeHTML(item.title)}</h3>
      </div>
      <p class="search-result-desc">${escapeHTML(item.content || '暂无内容')}</p>
      <div class="search-result-meta">
        <button class="user-profile-link" type="button" data-user-profile="${escapeHTML(item.owner || 'admin')}">作者 @${escapeHTML(item.owner || 'admin')}</button>
        <span>${escapeHTML(getInspirationDisplayTime(item) || '')}</span>
      </div>
      <div class="search-result-tags"><span>${escapeHTML(item.tag || '灵感')}</span></div>
    </div>
  </article>`;
}

function renderSearchPage() {
  const title = document.getElementById('searchPageTitle');
  const hint = document.getElementById('searchPageHint');
  const summary = document.getElementById('searchSummary');
  const results = document.getElementById('searchResults');
  const navInput = document.getElementById('navSearchInput');
  const pageInput = document.getElementById('searchPageInput');
  if (navInput && navInput.value !== searchState.query) navInput.value = searchState.query;
  if (pageInput && pageInput.value !== searchState.query) pageInput.value = searchState.query;
  document.querySelectorAll('[data-search-type]').forEach(button => {
    button.classList.toggle('active', button.dataset.searchType === searchState.filter);
  });
  if (!summary || !results) return;
  if (!searchState.query) {
    if (title) title.textContent = '搜索';
    if (hint) hint.textContent = '输入关键词，发现相关作品、委托和灵感';
    summary.textContent = '请输入关键词开始搜索';
    results.innerHTML = '<div class="search-empty">在上方输入关键词，点击搜索后查看结果。</div>';
    return;
  }
  if (title) title.textContent = `搜索：${searchState.query}`;
  if (hint) hint.textContent = '相关内容会按作品、委托和灵感聚合展示';
  if (searchState.loading) {
    summary.textContent = '正在搜索...';
    results.innerHTML = '<div class="search-empty">正在连接数据源，请稍候。</div>';
    return;
  }
  const visibleResults = getVisibleSearchResults();
  summary.textContent = `找到 ${searchResultCount()} 条相关内容`;
  results.innerHTML = visibleResults.length
    ? visibleResults.map(renderSearchCard).join('')
    : '<div class="search-empty">没有找到相关内容，换个关键词试试。</div>';
}

async function performSearch(query) {
  const keyword = String(query || '').trim();
  searchState.query = keyword;
  searchState.filter = 'all';
  if (!keyword) {
    switchPage('search');
    renderSearchPage();
    return;
  }
  switchPage('search');
  searchState.loading = true;
  renderSearchPage();
  try {
    searchState.results = await fetchSearchResults(keyword);
  } catch (error) {
    console.warn('Search failed:', error);
    searchState.results = {
      artworks: localArtworkSearch(keyword),
      commissions: localCommissionSearch(keyword),
      inspirations: localInspirationSearch(keyword)
    };
  } finally {
    searchState.loading = false;
    renderSearchPage();
  }
}

function focusGallerySearchResult(artworkId) {
  switchPage('gallery');
  const cards = getGalleryCards();
  const index = cards.findIndex(card => String(card.dataset.id) === String(artworkId));
  if (index >= 0) {
    galleryVisibleCount = Math.max(galleryVisibleCount, index + 1);
    renderGalleryPagination();
    window.setTimeout(() => {
      const card = getGalleryCard(artworkId);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
  }
}

function openCommissionDetail(commissionId) {
  const item = getCommissions().find(entry => String(entry.id) === String(commissionId))
    || searchState.results.commissions.find(entry => String(entry.id) === String(commissionId));
  if (!item) return;
  document.getElementById('commissionDetailTitle').textContent = item.title || '委托详情';
  document.getElementById('commissionDetailStatus').textContent = getCommissionStatusLabel(item.status);
  document.getElementById('commissionDetailType').textContent = item.typeLabel || '委托';
  document.getElementById('commissionDetailBudget').textContent = item.budget || '可商议';
  document.getElementById('commissionDetailRequester').textContent = item.requester || 'admin';
  document.getElementById('commissionDetailArtist').textContent = item.artist || '暂未接单';
  document.getElementById('commissionDetailDate').textContent = item.createdAt || '';
  document.getElementById('commissionDetailDescription').textContent = item.description || '暂无需求说明';
  const actions = document.getElementById('commissionDetailActions');
  if (actions) {
    const canAccept = canAcceptCommission(item);
    actions.innerHTML = canAccept
      ? `<button type="button" class="commission-btn" onclick="acceptCommission('${escapeHTML(item.id)}'); closeCommissionDetail();">接受委托</button>`
      : `<button type="button" class="commission-btn secondary" disabled>${item.artist ? `接单者：${escapeHTML(item.artist)}` : '等待接单'}</button>`;
  }
  document.getElementById('commissionDetail').classList.remove('hidden');
}

function closeCommissionDetail() {
  document.getElementById('commissionDetail')?.classList.add('hidden');
  activeCommissionDetailId = '';
  commissionDetailRequestToken += 1;
  clearTimeout(commissionArtistSearchTimer);
}

function openSearchResult(type, id) {
  if (type === 'artworks') {
    const card = getGalleryCard(id);
    if (card) openArtworkDetail(card);
    else focusGallerySearchResult(id);
    return;
  }
  if (type === 'commissions') {
    if (!currentUser) {
      openAuth('login', '请先登录后再查看委托内容。');
      return;
    }
    openCommissionDetail(id);
    return;
  }
  if (type === 'inspirations') {
    const item = getInspirationById(id);
    if (item) openInspirationDetail(id);
    else switchPage('blog');
  }
}

window.addEventListener('scroll', () => {
  if (window.scrollY > 50) navbar.classList.add('scrolled');
  else navbar.classList.remove('scrolled');
  const parallaxBg = document.querySelector('.parallax-bg');
  if (parallaxBg) parallaxBg.style.transform = `translateY(${window.pageYOffset * 0.5}px)`;
});

hamburger.addEventListener('click', () => {
  hamburger.classList.toggle('active');
  navLinks.classList.toggle('active');
});

document.querySelectorAll('.nav-links a[data-page]').forEach(link => {
  link.addEventListener('click', event => {
    event.preventDefault();
    hamburger.classList.remove('active');
    navLinks.classList.remove('active');
    switchPage(link.dataset.page);
  });
});

document.querySelector('.cta-button').addEventListener('click', event => {
  event.preventDefault();
  switchPage('gallery');
});

document.getElementById('publishNavBtn').addEventListener('click', () => {
  openPublishPage();
});

document.getElementById('navUserChip').addEventListener('click', () => {
  if (!currentUser) return openAuth('login', '请先登录后查看个人页面。');
  switchPage('me');
});

document.getElementById('navSearchForm')?.addEventListener('submit', event => {
  event.preventDefault();
  performSearch(document.getElementById('navSearchInput')?.value || '');
});

document.getElementById('searchPageForm')?.addEventListener('submit', event => {
  event.preventDefault();
  performSearch(document.getElementById('searchPageInput')?.value || '');
});

document.getElementById('searchTabs')?.addEventListener('click', event => {
  const button = event.target.closest('[data-search-type]');
  if (!button) return;
  if (button.dataset.searchType === 'commissions' && !currentUser) {
    openAuth('login', '请先登录后再搜索委托内容。');
    return;
  }
  searchState.filter = button.dataset.searchType;
  renderSearchPage();
});

document.getElementById('searchResults')?.addEventListener('click', event => {
  const card = event.target.closest('[data-search-result-type]');
  if (!card) return;
  openSearchResult(card.dataset.searchResultType, card.dataset.searchResultId);
});

document.getElementById('commissionDetailClose')?.addEventListener('click', closeCommissionDetail);

document.getElementById('commissionDetail')?.addEventListener('click', event => {
  if (event.target.id === 'commissionDetail') closeCommissionDetail();
});

function normalizeCommissionBid(value) {
  if (!value) return null;
  const artistId = value.artistId || value.artist_id || value.artist || '';
  return {
    id: String(value.id || ''),
    customRequest: value.customRequest || value.custom_request || '',
    artistId,
    artist: value.artistUsername || value.artist_username || (typeof value.artist === 'string' ? value.artist : '') || (artistId ? 'artist-' + artistId : ''),
    avatar: normalizeImageSrc(value.avatar || value.artistAvatar || value.artist_avatar || ''),
    amount: String(value.amount || ''),
    message: value.message || '',
    status: value.status || 'active',
    createdAt: value.createdAt || value.created_at || '',
    updatedAt: value.updatedAt || value.updated_at || ''
  };
}

function normalizeCommissionInvitation(value) {
  if (!value) return null;
  const artistId = value.artistId || value.artist_id || value.artist || '';
  return {
    id: String(value.id || ''),
    customRequest: value.customRequest || value.custom_request || '',
    artistId,
    artist: value.artistUsername || value.artist_username || (typeof value.artist === 'string' ? value.artist : '') || (artistId ? 'artist-' + artistId : ''),
    avatar: normalizeImageSrc(value.avatar || value.artistAvatar || value.artist_avatar || ''),
    invitedBy: value.invitedBy || value.invited_by || '',
    invitedByUsername: value.invitedByUsername || value.invited_by_username || '',
    amount: String(value.amount || ''),
    message: value.message || '',
    status: value.status || 'pending',
    respondedAt: value.respondedAt || value.responded_at || '',
    createdAt: value.createdAt || value.created_at || '',
    updatedAt: value.updatedAt || value.updated_at || ''
  };
}

const commissionItemNormalizer = normalizeCommissionItem;
normalizeCommissionItem = function(item, index = 0) {
  const normalized = commissionItemNormalizer(item, index);
  return Object.assign(normalized, {
    requesterId: item.requesterId || item.requester_id || (typeof item.requester === 'number' ? item.requester : ''),
    artistId: item.artistId || item.artist_id || (typeof item.artist === 'number' ? item.artist : ''),
    agreedPrice: String(item.agreedPrice || item.agreed_price || ''),
    bidCount: Number(item.bidCount ?? item.bid_count ?? 0),
    myBid: normalizeCommissionBid(item.myBid || item.my_bid),
    myInvitation: normalizeCommissionInvitation(item.myInvitation || item.my_invitation),
    selectedBid: normalizeCommissionBid(item.selectedBid || item.selected_bid)
  });
};

commissionFromApi = function(item, index = 0) {
  return normalizeCommissionItem({
    id: String(item.id || 'commission-' + Date.now() + '-' + index),
    requester: item.requester_username || item.requester || 'admin',
    requesterId: item.requester,
    artist: item.artist_username || item.artist || '',
    artistId: item.artist,
    title: item.title || '\u672a\u547d\u540d\u59d4\u6258',
    typeLabel: item.type_label || item.typeLabel || '\u59d4\u6258',
    description: item.description || '',
    budget: item.budget || item.budget_note || '\u53ef\u5546\u8bae',
    agreedPrice: item.agreed_price || '',
    status: item.status === 'submitted' ? 'open' : (item.status || 'open'),
    bidCount: item.bid_count,
    myBid: item.my_bid,
    myInvitation: item.my_invitation,
    selectedBid: item.selected_bid,
    createdAt: formatCommissionTime(item.created_at) || new Date().toLocaleString(),
    acceptedAt: item.accepted_at || '',
    abandonRequestedAt: item.abandon_requested_at || ''
  }, index);
};

getCommissionStatusLabel = function(status) {
  const labels = {
    open: '\u7ade\u4ef7\u4e2d',
    submitted: '\u7ade\u4ef7\u4e2d',
    accepted: '\u5df2\u9009\u5b9a\u753b\u5e08',
    abandon_requested: '\u7533\u8bf7\u653e\u5f03\u4e2d',
    in_progress: '\u521b\u4f5c\u4e2d',
    reviewing: '\u5f85\u786e\u8ba4',
    completed: '\u5df2\u5b8c\u6210',
    cancelled: '\u5df2\u53d6\u6d88'
  };
  return labels[status] || '\u5f85\u63a5\u5355';
};

function getCommissionBidStatusLabel(status) {
  return {
    active: '\u6709\u6548\u62a5\u4ef7',
    withdrawn: '\u5df2\u64a4\u56de',
    selected: '\u5df2\u9009\u4e2d',
    rejected: '\u672a\u9009\u4e2d'
  }[status] || status || '\u672a\u77e5';
}

function getCommissionInvitationStatusLabel(status) {
  return {
    pending: '\u5f85\u56de\u5e94',
    accepted: '\u5df2\u63a5\u53d7',
    declined: '\u5df2\u62d2\u7edd',
    cancelled: '\u5df2\u53d6\u6d88'
  }[status] || status || '\u672a\u77e5';
}

const unguardedCommissionLoader = loadCommissionsFromApi;
loadCommissionsFromApi = function() {
  if (!commissionLoadPromise) {
    commissionLoadPromise = Promise.resolve()
      .then(() => unguardedCommissionLoader())
      .finally(() => {
        commissionLoadPromise = null;
      });
  }
  return commissionLoadPromise;
};

const initializeCommissionPage = initCommissionPage;
initCommissionPage = function() {
  initializeCommissionPage();
  const section = document.getElementById('contact');
  const hint = section?.querySelector('.section-title p');
  const badge = section?.querySelector('.status-badge');
  if (hint) hint.textContent = '\u753b\u5e08\u63d0\u4ea4\u62a5\u4ef7\uff0c\u53d1\u5e03\u8005\u6311\u9009\u5408\u9002\u4eba\u9009\uff0c\u4e5f\u53ef\u5b9a\u5411\u9080\u8bf7\u5408\u4f5c';
  if (badge) badge.textContent = '\u7ade\u4ef7\u5f00\u653e\u4e2d';
};

function setCommissionWorkspaceLabels() {
  const labels = {
    commissionWorkspaceTitle: '\u7ade\u4ef7\u4e0e\u5b9a\u5411\u9080\u8bf7',
    commissionDetailRefresh: '\u5237\u65b0',
    commissionBidKicker: '\u516c\u5f00\u7ade\u4ef7',
    commissionBidTitle: '\u753b\u5e08\u62a5\u4ef7',
    commissionInvitationKicker: '\u5b9a\u5411\u5408\u4f5c',
    commissionInvitationTitle: '\u753b\u5e08\u9080\u8bf7',
    commissionDetailAgreedPriceLabel: '\u6210\u4ea4\u4ef7'
  };
  Object.entries(labels).forEach(([id, label]) => {
    const element = document.getElementById(id);
    if (element) element.textContent = label;
  });
}

function commissionStatusClass(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9_-]/g, '');
}

function formatCommissionAmount(value, fallback = '') {
  const text = String(value || '').trim();
  return text ? '\uffe5' + text : fallback;
}

function commissionAvatarHtml(src, username) {
  const image = normalizeImageSrc(src || '');
  if (image) {
    return '<span class="commission-avatar"><img src="' + escapeHTML(image) + '" alt="' + escapeHTML(username || '\u753b\u5e08') + '"></span>';
  }
  const fallback = String(username || '\u753b').trim().slice(0, 1).toUpperCase() || '\u753b';
  return '<span class="commission-avatar">' + escapeHTML(fallback) + '</span>';
}

function commissionPersonalStateHtml(item) {
  const states = [];
  if (item.myBid) {
    states.push(
      '<span class="commission-inline-state status-' + commissionStatusClass(item.myBid.status) + '">' +
      '\u6211\u7684\u62a5\u4ef7 ' + escapeHTML(formatCommissionAmount(item.myBid.amount)) +
      ' \u00b7 ' + escapeHTML(getCommissionBidStatusLabel(item.myBid.status)) +
      '</span>'
    );
  }
  if (item.myInvitation) {
    states.push(
      '<span class="commission-inline-state status-' + commissionStatusClass(item.myInvitation.status) + '">' +
      '\u5b9a\u5411\u9080\u8bf7 \u00b7 ' + escapeHTML(getCommissionInvitationStatusLabel(item.myInvitation.status)) +
      '</span>'
    );
  }
  if (item.agreedPrice) {
    states.push('<span class="commission-inline-state status-selected">\u6210\u4ea4 ' + escapeHTML(formatCommissionAmount(item.agreedPrice)) + '</span>');
  }
  return states.length ? '<div class="commission-personal-states">' + states.join('') + '</div>' : '';
}

commissionActionHtml = function(item) {
  const buttons = [];
  let detailLabel = '\u67e5\u770b\u8be6\u60c5';
  if (currentUser && item.requester === currentUser.username) detailLabel = '\u67e5\u770b\u62a5\u4ef7\u4e0e\u9080\u8bf7';
  else if (item.myInvitation?.status === 'pending') detailLabel = '\u5904\u7406\u9080\u8bf7';
  else if (currentUser && item.status === 'open') detailLabel = item.myBid?.status === 'active' ? '\u66f4\u65b0\u62a5\u4ef7' : '\u67e5\u770b\u5e76\u62a5\u4ef7';
  buttons.push('<button type="button" class="commission-btn" onclick="openCommissionDetail(\'' + escapeHTML(item.id) + '\')">' + detailLabel + '</button>');
  if (currentUser && item.requester === currentUser.username && item.status === 'open') {
    buttons.push('<button type="button" class="commission-btn secondary" onclick="openCommissionEditor(\'' + escapeHTML(item.id) + '\')">\u7f16\u8f91</button>');
    buttons.push('<button type="button" class="commission-btn secondary danger" onclick="deleteCommission(\'' + escapeHTML(item.id) + '\')">\u5220\u9664</button>');
  }
  if (currentUser && item.artist === currentUser.username && item.status === 'accepted') {
    buttons.push('<button type="button" class="commission-btn secondary" onclick="abandonCommission(\'' + escapeHTML(item.id) + '\')">\u653e\u5f03\u59d4\u6258</button>');
  }
  if (currentUser && item.requester === currentUser.username && item.status === 'abandon_requested') {
    buttons.push('<button type="button" class="commission-btn" onclick="resolveAbandonRequest(\'' + escapeHTML(item.id) + '\', true)">\u540c\u610f\u653e\u5f03</button>');
    buttons.push('<button type="button" class="commission-btn secondary" onclick="resolveAbandonRequest(\'' + escapeHTML(item.id) + '\', false)">\u62d2\u7edd\u653e\u5f03</button>');
  }
  return buttons.join('');
};

renderCommissionBoard = async function() {
  const board = document.getElementById('commissionBoard');
  if (!board) return;
  if (!commissionCache.length) {
    board.innerHTML = '<div class="commission-empty">\u6b63\u5728\u52a0\u8f7d\u59d4\u6258...</div>';
    try {
      await loadCommissionsFromApi();
    } catch (error) {
      console.warn('Commission API unavailable:', error);
    }
  }
  const commissions = getCommissions();
  const openCount = commissions.filter(item => item.status === 'open').length;
  const acceptedCount = commissions.filter(item => !['open', 'cancelled'].includes(item.status)).length;
  const mineCount = currentUser
    ? commissions.filter(item => item.requester === currentUser.username || item.artist === currentUser.username || item.myBid || item.myInvitation).length
    : 0;
  const counters = {
    commissionOpenCount: openCount,
    commissionAcceptedCount: acceptedCount,
    commissionMineCount: mineCount
  };
  Object.entries(counters).forEach(([id, value]) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  });
  if (!commissions.length) {
    board.innerHTML = '<div class="commission-empty">\u6682\u65f6\u8fd8\u6ca1\u6709\u516c\u5f00\u59d4\u6258\uff0c\u5148\u53bb\u53d1\u5e03\u9875\u521b\u5efa\u4e00\u4e2a\u5427\u3002</div>';
    return;
  }
  const users = getUsers();
  board.innerHTML = commissions.map(item => {
    const requesterUser = users[item.requester] || { username: item.requester };
    const requesterName = getDisplayName(requesterUser);
    const minePill = currentUser && (item.requester === currentUser.username || item.artist === currentUser.username || item.myBid || item.myInvitation)
      ? '<span class="commission-pill mine">\u4e0e\u6211\u76f8\u5173</span>'
      : '';
    const pendingClass = item.status === 'abandon_requested' ? ' pending' : '';
    const acceptedClass = item.status === 'accepted' ? ' accepted' : '';
    const bidSummary = item.status === 'open'
      ? '<span class="commission-bid-summary"><strong>' + escapeHTML(item.bidCount) + '</strong> \u4e2a\u6709\u6548\u62a5\u4ef7</span>'
      : item.agreedPrice
        ? '<span class="commission-bid-summary selected"><strong>' + escapeHTML(formatCommissionAmount(item.agreedPrice)) + '</strong> \u5df2\u6210\u4ea4</span>'
        : '<span class="commission-bid-summary"><strong>' + escapeHTML(item.bidCount) + '</strong> \u4e2a\u62a5\u4ef7</span>';
    return '<article class="commission-card">' +
      '<div class="commission-card-head">' +
        '<div>' +
          '<h3>' + escapeHTML(item.title) + '</h3>' +
          '<div class="commission-meta">' +
            '<span>\u53d1\u5e03\u8005\uff1a' + escapeHTML(requesterName) + '</span>' +
            '<span>\u7c7b\u578b\uff1a' + escapeHTML(item.typeLabel) + '</span>' +
            '<span>\u9884\u7b97\uff1a' + escapeHTML(item.budget) + '</span>' +
            '<span>' + escapeHTML(item.createdAt) + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="commission-card-badges">' +
          '<span class="commission-pill' + acceptedClass + pendingClass + '">' + escapeHTML(getCommissionStatusLabel(item.status)) + '</span>' +
          minePill +
        '</div>' +
      '</div>' +
      '<div class="commission-desc">' + escapeHTML(item.description) + '</div>' +
      '<div class="commission-market-summary">' + bidSummary + commissionPersonalStateHtml(item) + '</div>' +
      '<div class="commission-actions">' + commissionActionHtml(item) + '</div>' +
    '</article>';
  }).join('');
};

const renderProfileBeforeMarketplace = renderMePage;
renderMePage = function() {
  renderProfileBeforeMarketplace();
  if (!currentUser) return;
  const related = getCommissions().filter(item =>
    item.requester === currentUser.username ||
    item.artist === currentUser.username ||
    item.myBid ||
    item.myInvitation
  );
  const count = document.getElementById('profileCommissionCount');
  if (count) count.textContent = related.length;
  refreshMyCommissionList(related);
};

refreshMyCommissionList = function(commissions) {
  if (!currentUser) return;
  const target = document.getElementById('myCommissionList');
  if (!target) return;
  target.innerHTML = commissions.length
    ? commissions.map(item => {
      let role = '\u4e0e\u6211\u76f8\u5173';
      if (item.requester === currentUser.username) role = '\u6211\u53d1\u5e03\u7684\u59d4\u6258';
      else if (item.artist === currentUser.username) role = '\u6211\u627f\u63a5\u7684\u59d4\u6258';
      else if (item.myInvitation) role = '\u6536\u5230\u7684\u5b9a\u5411\u9080\u8bf7';
      else if (item.myBid) role = '\u6211\u53c2\u4e0e\u7684\u7ade\u4ef7';
      const states = [];
      if (item.myBid) states.push(formatCommissionAmount(item.myBid.amount) + ' \u00b7 ' + getCommissionBidStatusLabel(item.myBid.status));
      if (item.myInvitation) states.push(getCommissionInvitationStatusLabel(item.myInvitation.status));
      if (item.agreedPrice) states.push('\u6210\u4ea4 ' + formatCommissionAmount(item.agreedPrice));
      return '<div class="mini-item">' +
        '<strong>' + escapeHTML(item.title) + '</strong>' +
        '<span>' + escapeHTML(role) + ' \u00b7 ' + escapeHTML(item.typeLabel) + ' \u00b7 ' + escapeHTML(getCommissionStatusLabel(item.status)) +
          (states.length ? ' \u00b7 ' + escapeHTML(states.join(' / ')) : '') + '</span>' +
        '<div class="mini-actions"><button type="button" class="mini-edit-btn" onclick="openCommissionDetail(\'' + escapeHTML(item.id) + '\')">\u67e5\u770b\u7ade\u4ef7\u4e0e\u9080\u8bf7</button></div>' +
      '</div>';
    }).join('')
    : '<div class="empty-state">\u8fd8\u6ca1\u6709\u4e0e\u4f60\u76f8\u5173\u7684\u59d4\u6258\u3002</div>';
};

function isCommissionRequester(item) {
  return !!currentUser && item?.requester === currentUser.username;
}

function renderCommissionDetailSummary(item) {
  if (!item) return;
  setCommissionWorkspaceLabels();
  document.getElementById('commissionDetailTitle').textContent = item.title || '\u59d4\u6258\u8be6\u60c5';
  document.getElementById('commissionDetailStatus').textContent = getCommissionStatusLabel(item.status);
  document.getElementById('commissionDetailType').textContent = item.typeLabel || '\u59d4\u6258';
  document.getElementById('commissionDetailBudget').textContent = item.budget || '\u53ef\u5546\u8bae';
  document.getElementById('commissionDetailRequester').textContent = item.requester || 'admin';
  document.getElementById('commissionDetailArtist').textContent = item.artist || '\u6682\u672a\u9009\u5b9a';
  document.getElementById('commissionDetailDate').textContent = item.createdAt || '';
  document.getElementById('commissionDetailDescription').textContent = item.description || '\u6682\u65e0\u9700\u6c42\u8bf4\u660e';
  const agreedRow = document.getElementById('commissionDetailAgreedPriceRow');
  const agreedPrice = document.getElementById('commissionDetailAgreedPrice');
  if (agreedRow) agreedRow.hidden = !item.agreedPrice;
  if (agreedPrice) agreedPrice.textContent = item.agreedPrice ? formatCommissionAmount(item.agreedPrice) : '';
  const actions = document.getElementById('commissionDetailActions');
  if (!actions) return;
  const buttons = [];
  if (isCommissionRequester(item) && item.status === 'open') {
    buttons.push('<button type="button" class="commission-btn secondary" onclick="closeCommissionDetail(); openCommissionEditor(\'' + escapeHTML(item.id) + '\')">\u7f16\u8f91\u59d4\u6258</button>');
    buttons.push('<button type="button" class="commission-btn secondary danger" onclick="closeCommissionDetail(); deleteCommission(\'' + escapeHTML(item.id) + '\')">\u5220\u9664\u59d4\u6258</button>');
  }
  if (currentUser && item.artist === currentUser.username && item.status === 'accepted') {
    buttons.push('<button type="button" class="commission-btn secondary" onclick="abandonCommission(\'' + escapeHTML(item.id) + '\')">\u7533\u8bf7\u653e\u5f03</button>');
  }
  if (isCommissionRequester(item) && item.status === 'abandon_requested') {
    buttons.push('<button type="button" class="commission-btn" onclick="resolveAbandonRequest(\'' + escapeHTML(item.id) + '\', true)">\u540c\u610f\u653e\u5f03</button>');
    buttons.push('<button type="button" class="commission-btn secondary" onclick="resolveAbandonRequest(\'' + escapeHTML(item.id) + '\', false)">\u62d2\u7edd\u653e\u5f03</button>');
  }
  actions.innerHTML = buttons.join('');
}

function parseCommissionBudgetAmount(value) {
  const text = String(value || '').trim().replace(/,/g, '');
  const match = text.match(/^(?:[\uffe5\u00a5$]\s*)?(\d+(?:\.\d{1,2})?)\s*(?:\u5143)?$/);
  return match && Number(match[1]) > 0 ? match[1] : '';
}

function detailCommissionBid(item) {
  return commissionDetailBids.find(bid =>
    String(bid.artistId) === String(currentUser?.id || '') ||
    bid.artist === currentUser?.username
  ) || item.myBid || null;
}

function detailCommissionInvitation(item) {
  return commissionDetailInvitations.find(invitation =>
    String(invitation.artistId) === String(currentUser?.id || '') ||
    invitation.artist === currentUser?.username
  ) || item.myInvitation || null;
}

function renderCommissionBidComposer(item) {
  const target = document.getElementById('commissionBidComposer');
  if (!target) return;
  if (!currentUser) {
    target.innerHTML = '<div class="commission-market-note">\u767b\u5f55\u540e\u624d\u80fd\u63d0\u4ea4\u62a5\u4ef7\u3002</div>';
    return;
  }
  if (isCommissionRequester(item)) {
    target.innerHTML = '<div class="commission-market-note">\u4f60\u53ef\u4ee5\u6bd4\u8f83\u753b\u5e08\u7684\u4ef7\u683c\u4e0e\u8bf4\u660e\uff0c\u7136\u540e\u9009\u5b9a\u4e00\u4f4d\u3002</div>';
    return;
  }
  if (item.status !== 'open') {
    target.innerHTML = '<div class="commission-market-note">\u8be5\u59d4\u6258\u5df2\u7ed3\u675f\u7ade\u4ef7\u3002</div>';
    return;
  }
  const myBid = detailCommissionBid(item);
  const active = myBid?.status === 'active';
  const submitLabel = active ? '\u66f4\u65b0\u62a5\u4ef7' : (myBid ? '\u91cd\u65b0\u62a5\u4ef7' : '\u63d0\u4ea4\u62a5\u4ef7');
  target.innerHTML =
    '<form class="commission-market-form" onsubmit="submitCommissionBid(event)">' +
      '<label for="commissionBidAmount">\u62a5\u4ef7\u91d1\u989d\uff08\u5143\uff09</label>' +
      '<input id="commissionBidAmount" type="number" min="0.01" step="0.01" required value="' + escapeHTML(myBid?.amount || '') + '" placeholder="500.00">' +
      '<label for="commissionBidMessage">\u62a5\u4ef7\u8bf4\u660e</label>' +
      '<textarea id="commissionBidMessage" maxlength="500" placeholder="\u8bf4\u660e\u5de5\u671f\u3001\u98ce\u683c\u6216\u53ef\u4fee\u6539\u6b21\u6570">' + escapeHTML(myBid?.message || '') + '</textarea>' +
      '<div class="commission-form-actions">' +
        '<button type="submit" class="commission-btn">' + submitLabel + '</button>' +
        (active ? '<button type="button" class="commission-btn secondary danger" onclick="withdrawCommissionBid()">\u64a4\u56de\u62a5\u4ef7</button>' : '') +
      '</div>' +
    '</form>';
}

function renderCommissionBidList(item) {
  const target = document.getElementById('commissionDetailBidList');
  const count = document.getElementById('commissionDetailBidCount');
  if (!target || !count) return;
  const byId = new Map();
  commissionDetailBids.filter(Boolean).forEach(bid => byId.set(String(bid.id), bid));
  if (item.myBid) byId.set(String(item.myBid.id || 'mine'), item.myBid);
  if (item.selectedBid) byId.set(String(item.selectedBid.id || 'selected'), item.selectedBid);
  const bids = [...byId.values()].sort((a, b) => {
    const rank = { selected: 0, active: 1, withdrawn: 2, rejected: 3 };
    return (rank[a.status] ?? 9) - (rank[b.status] ?? 9);
  });
  count.textContent = item.bidCount || bids.filter(bid => bid.status === 'active').length;
  if (!bids.length) {
    target.innerHTML = '<div class="commission-market-empty">\u8fd8\u6ca1\u6709\u753b\u5e08\u62a5\u4ef7\u3002</div>';
    return;
  }
  target.innerHTML = bids.map(bid => {
    const canSelect = isCommissionRequester(item) && item.status === 'open' && bid.status === 'active';
    return '<article class="commission-offer-card status-' + commissionStatusClass(bid.status) + '">' +
      '<div class="commission-offer-head">' +
        '<div class="commission-person user-profile-link" data-user-profile="' + escapeHTML(bid.artist || '') + '">' +
          commissionAvatarHtml(bid.avatar, bid.artist) +
          '<div><strong>' + escapeHTML(bid.artist || '\u753b\u5e08') + '</strong><span>' + escapeHTML(formatCommissionTime(bid.updatedAt || bid.createdAt)) + '</span></div>' +
        '</div>' +
        '<strong class="commission-offer-amount">' + escapeHTML(formatCommissionAmount(bid.amount, '\u5f85\u6c9f\u901a')) + '</strong>' +
      '</div>' +
      (bid.message ? '<p>' + escapeHTML(bid.message) + '</p>' : '<p class="muted">\u672a\u586b\u5199\u62a5\u4ef7\u8bf4\u660e</p>') +
      '<div class="commission-offer-foot">' +
        '<span class="commission-state-chip status-' + commissionStatusClass(bid.status) + '">' + escapeHTML(getCommissionBidStatusLabel(bid.status)) + '</span>' +
        (canSelect ? '<button type="button" class="commission-btn compact" onclick="selectCommissionBid(\'' + escapeHTML(bid.id) + '\')">\u9009\u5b9a\u8be5\u753b\u5e08</button>' : '') +
      '</div>' +
    '</article>';
  }).join('');
}

function renderCommissionInviteComposer(item) {
  const target = document.getElementById('commissionInviteComposer');
  if (!target) return;
  if (!isCommissionRequester(item)) {
    target.innerHTML = '<div class="commission-market-note">\u53d1\u5e03\u8005\u53ef\u4ee5\u5b9a\u5411\u9080\u8bf7\u753b\u5e08\uff1b\u6536\u5230\u9080\u8bf7\u540e\u53ef\u5728\u4e0b\u65b9\u56de\u5e94\u3002</div>';
    return;
  }
  if (item.status !== 'open') {
    target.innerHTML = '<div class="commission-market-note">\u8be5\u59d4\u6258\u5df2\u9009\u5b9a\u753b\u5e08\uff0c\u4e0d\u518d\u53d1\u51fa\u65b0\u9080\u8bf7\u3002</div>';
    return;
  }
  const selected = commissionSelectedArtist;
  target.innerHTML =
    '<form class="commission-market-form" onsubmit="sendCommissionInvitation(event)">' +
      '<label for="commissionArtistSearch">\u641c\u7d22\u753b\u5e08</label>' +
      '<input id="commissionArtistSearch" type="search" autocomplete="off" value="' + escapeHTML(selected ? '@' + selected.username : '') + '" placeholder="\u8f93\u5165\u753b\u5e08\u7528\u6237\u540d" oninput="queueCommissionArtistSearch(this.value)">' +
      '<input id="commissionArtistId" type="hidden" value="' + escapeHTML(selected?.id || '') + '">' +
      '<div class="commission-artist-results" id="commissionArtistResults"></div>' +
      '<label for="commissionInviteAmount">\u9080\u8bf7\u4ef7\u683c\uff08\u5143\uff09</label>' +
      '<input id="commissionInviteAmount" type="number" min="0.01" step="0.01" required value="' + escapeHTML(parseCommissionBudgetAmount(item.budget)) + '" placeholder="500.00">' +
      '<label for="commissionInviteMessage">\u9080\u8bf7\u7559\u8a00</label>' +
      '<textarea id="commissionInviteMessage" maxlength="500" placeholder="\u8bf4\u660e\u5e0c\u671b\u4e0e\u8be5\u753b\u5e08\u5408\u4f5c\u7684\u539f\u56e0"></textarea>' +
      '<div class="commission-form-actions"><button type="submit" class="commission-btn">\u53d1\u9001\u9080\u8bf7</button></div>' +
    '</form>';
  renderCommissionArtistResults();
}

function renderCommissionInvitationList(item) {
  const target = document.getElementById('commissionDetailInvitationList');
  const count = document.getElementById('commissionDetailInvitationCount');
  if (!target || !count) return;
  const byId = new Map();
  commissionDetailInvitations.filter(Boolean).forEach(invitation => byId.set(String(invitation.id), invitation));
  if (item.myInvitation) byId.set(String(item.myInvitation.id || 'mine'), item.myInvitation);
  const invitations = [...byId.values()].sort((a, b) => {
    const rank = { pending: 0, accepted: 1, declined: 2, cancelled: 3 };
    return (rank[a.status] ?? 9) - (rank[b.status] ?? 9);
  });
  count.textContent = invitations.length;
  if (!invitations.length) {
    target.innerHTML = '<div class="commission-market-empty">\u6682\u65e0\u5b9a\u5411\u9080\u8bf7\u3002</div>';
    return;
  }
  target.innerHTML = invitations.map(invitation => {
    const canRespond = !isCommissionRequester(item) && invitation.status === 'pending' && (
      invitation.artist === currentUser?.username ||
      String(invitation.artistId) === String(currentUser?.id || '') ||
      commissionDetailInvitations.length === 1
    );
    return '<article class="commission-offer-card status-' + commissionStatusClass(invitation.status) + '">' +
      '<div class="commission-offer-head">' +
        '<div class="commission-person user-profile-link" data-user-profile="' + escapeHTML(invitation.artist || '') + '">' +
          commissionAvatarHtml(invitation.avatar, invitation.artist) +
          '<div><strong>' + escapeHTML(invitation.artist || '\u753b\u5e08') + '</strong><span>' + escapeHTML(formatCommissionTime(invitation.updatedAt || invitation.createdAt)) + '</span></div>' +
        '</div>' +
        '<strong class="commission-offer-amount">' + escapeHTML(formatCommissionAmount(invitation.amount, '\u5f85\u6c9f\u901a')) + '</strong>' +
      '</div>' +
      (invitation.message ? '<p>' + escapeHTML(invitation.message) + '</p>' : '<p class="muted">\u672a\u586b\u5199\u9080\u8bf7\u7559\u8a00</p>') +
      '<div class="commission-offer-foot">' +
        '<span class="commission-state-chip status-' + commissionStatusClass(invitation.status) + '">' + escapeHTML(getCommissionInvitationStatusLabel(invitation.status)) + '</span>' +
        (canRespond ? '<div class="commission-form-actions"><button type="button" class="commission-btn compact" onclick="respondCommissionInvitation(\'' + escapeHTML(invitation.id) + '\', \'accept\')">\u63a5\u53d7</button><button type="button" class="commission-btn secondary compact" onclick="respondCommissionInvitation(\'' + escapeHTML(invitation.id) + '\', \'decline\')">\u62d2\u7edd</button></div>' : '') +
      '</div>' +
    '</article>';
  }).join('');
}

function renderCommissionWorkspace(item, options = {}) {
  const hint = document.getElementById('commissionWorkspaceHint');
  if (!item || !hint) return;
  if (options.loading) hint.textContent = '\u6b63\u5728\u52a0\u8f7d\u6700\u65b0\u62a5\u4ef7\u4e0e\u9080\u8bf7...';
  else if (options.error) hint.textContent = '\u6682\u65f6\u65e0\u6cd5\u540c\u6b65\u6700\u65b0\u6570\u636e\uff0c\u8bf7\u7a0d\u540e\u5237\u65b0\u3002';
  else if (isCommissionRequester(item) && item.status === 'open') hint.textContent = '\u6bd4\u8f83\u753b\u5e08\u62a5\u4ef7\uff0c\u6216\u6309\u7528\u6237\u540d\u5b9a\u5411\u9080\u8bf7\u3002';
  else if (detailCommissionInvitation(item)?.status === 'pending') hint.textContent = '\u4f60\u6536\u5230\u4e86\u5b9a\u5411\u9080\u8bf7\uff0c\u53ef\u4ee5\u63a5\u53d7\u6216\u62d2\u7edd\u3002';
  else if (item.status === 'open') hint.textContent = '\u586b\u5199\u4ef7\u683c\u548c\u8bf4\u660e\u53c2\u4e0e\u7ade\u4ef7\uff0c\u62a5\u4ef7\u53ef\u66f4\u65b0\u6216\u64a4\u56de\u3002';
  else hint.textContent = '\u8be5\u59d4\u6258\u5df2\u7ed3\u675f\u5019\u9009\u9636\u6bb5\u3002';
  renderCommissionBidComposer(item);
  renderCommissionBidList(item);
  renderCommissionInviteComposer(item);
  renderCommissionInvitationList(item);
}

function getActiveCommissionDetail() {
  return getCommissions().find(item => String(item.id) === String(activeCommissionDetailId))
    || searchState.results.commissions.find(item => String(item.id) === String(activeCommissionDetailId))
    || null;
}

async function refreshActiveCommissionDetail() {
  const commissionId = activeCommissionDetailId;
  const cached = getActiveCommissionDetail();
  if (!commissionId || !cached) return;
  const requestToken = ++commissionDetailRequestToken;
  renderCommissionDetailSummary(cached);
  renderCommissionWorkspace(cached, { loading: true });
  if (!currentUser) {
    renderCommissionWorkspace(cached);
    return;
  }
  const [detailResult, bidsResult, invitationsResult] = await Promise.allSettled([
    apiRequest('/custom/' + encodeURIComponent(commissionId) + '/', { auth: true }),
    apiRequest('/custom/' + encodeURIComponent(commissionId) + '/bids/', { auth: true }),
    apiRequest('/custom/' + encodeURIComponent(commissionId) + '/invitations/', { auth: true })
  ]);
  if (requestToken !== commissionDetailRequestToken || String(activeCommissionDetailId) !== String(commissionId)) return;
  let item = cached;
  if (detailResult.status === 'fulfilled') {
    item = commissionFromApi(detailResult.value);
    const index = commissionCache.findIndex(entry => String(entry.id) === String(item.id));
    if (index >= 0) commissionCache[index] = item;
    else commissionCache.unshift(item);
  }
  if (bidsResult.status === 'fulfilled') {
    commissionDetailBids = apiList(bidsResult.value).map(normalizeCommissionBid).filter(Boolean);
  } else {
    commissionDetailBids = item.myBid ? [item.myBid] : [];
  }
  if (invitationsResult.status === 'fulfilled') {
    commissionDetailInvitations = apiList(invitationsResult.value).map(normalizeCommissionInvitation).filter(Boolean);
  } else {
    commissionDetailInvitations = item.myInvitation ? [item.myInvitation] : [];
  }
  renderCommissionDetailSummary(item);
  renderCommissionWorkspace(item, {
    error: bidsResult.status === 'rejected' || invitationsResult.status === 'rejected'
  });
  renderCommissionBoard();
  if (currentUser) renderMePage();
}

openCommissionDetail = async function(commissionId) {
  if (!currentUser) {
    openAuth('login', '\u8bf7\u5148\u767b\u5f55\u540e\u67e5\u770b\u7ade\u4ef7\u4e0e\u9080\u8bf7\u3002');
    return;
  }
  const item = getCommissions().find(entry => String(entry.id) === String(commissionId))
    || searchState.results.commissions.find(entry => String(entry.id) === String(commissionId));
  if (!item) return;
  activeCommissionDetailId = String(item.id);
  commissionDetailBids = item.myBid ? [item.myBid] : [];
  commissionDetailInvitations = item.myInvitation ? [item.myInvitation] : [];
  commissionSelectedArtist = null;
  commissionArtistResults = [];
  commissionArtistSearchQuery = '';
  commissionArtistSearchError = '';
  renderCommissionDetailSummary(item);
  renderCommissionWorkspace(item, { loading: true });
  document.getElementById('commissionDetail').classList.remove('hidden');
  await refreshActiveCommissionDetail();
};

function setCommissionMarketplaceBusy(busy) {
  commissionActionBusy = busy;
  const workspace = document.getElementById('commissionWorkspace');
  workspace?.classList.toggle('is-busy', busy);
  workspace?.querySelectorAll('button, input, textarea').forEach(element => {
    element.disabled = busy;
  });
}

async function runCommissionMarketplaceAction(task, successMessage) {
  if (commissionActionBusy || !activeCommissionDetailId) return false;
  setCommissionMarketplaceBusy(true);
  try {
    await task();
    await refreshCommissions();
    await refreshActiveCommissionDetail();
    if (successMessage) alert(successMessage);
    return true;
  } catch (error) {
    alert(error.message || '\u64cd\u4f5c\u5931\u8d25\uff0c\u8bf7\u7a0d\u540e\u91cd\u8bd5\u3002');
    return false;
  } finally {
    setCommissionMarketplaceBusy(false);
  }
}

async function submitCommissionBid(event) {
  event.preventDefault();
  const amount = document.getElementById('commissionBidAmount')?.value.trim() || '';
  const message = document.getElementById('commissionBidMessage')?.value.trim() || '';
  if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) {
    alert('\u8bf7\u586b\u5199\u5927\u4e8e 0 \u7684\u62a5\u4ef7\u91d1\u989d\u3002');
    return;
  }
  await runCommissionMarketplaceAction(
    () => apiRequest('/custom/' + encodeURIComponent(activeCommissionDetailId) + '/bids/', {
      method: 'POST',
      body: JSON.stringify({ amount, message })
    }),
    '\u62a5\u4ef7\u5df2\u63d0\u4ea4\uff0c\u53d1\u5e03\u8005\u73b0\u5728\u53ef\u4ee5\u770b\u5230\u3002'
  );
}

async function withdrawCommissionBid() {
  if (!confirm('\u786e\u5b9a\u64a4\u56de\u5f53\u524d\u62a5\u4ef7\u5417\uff1f')) return;
  await runCommissionMarketplaceAction(
    () => apiRequest('/custom/' + encodeURIComponent(activeCommissionDetailId) + '/bids/', { method: 'DELETE' }),
    '\u62a5\u4ef7\u5df2\u64a4\u56de\u3002'
  );
}

async function selectCommissionBid(bidId) {
  const bid = commissionDetailBids.find(item => String(item.id) === String(bidId));
  const summary = bid ? bid.artist + ' / ' + formatCommissionAmount(bid.amount) : '\u8be5\u62a5\u4ef7';
  if (!confirm('\u786e\u5b9a\u9009\u5b9a ' + summary + ' \u5417\uff1f\u9009\u5b9a\u540e\u5c06\u7ed3\u675f\u5176\u4ed6\u7ade\u4ef7\u4e0e\u9080\u8bf7\u3002')) return;
  await runCommissionMarketplaceAction(
    () => apiRequest('/custom/' + encodeURIComponent(activeCommissionDetailId) + '/select-bid/', {
      method: 'POST',
      body: JSON.stringify({ bid_id: bidId })
    }),
    '\u5df2\u9009\u5b9a\u753b\u5e08\uff0c\u6210\u4ea4\u4ef7\u5df2\u786e\u8ba4\u3002'
  );
}

function renderCommissionArtistResults() {
  const target = document.getElementById('commissionArtistResults');
  if (!target) return;
  if (commissionSelectedArtist) {
    target.innerHTML =
      '<div class="commission-artist-option selected">' +
        commissionAvatarHtml(commissionSelectedArtist.avatar, commissionSelectedArtist.username) +
        '<span><strong>' + escapeHTML(commissionSelectedArtist.displayName || commissionSelectedArtist.username) + '</strong><small>@' + escapeHTML(commissionSelectedArtist.username) + ' \u00b7 \u5df2\u9009\u62e9</small></span>' +
      '</div>';
    return;
  }
  if (commissionArtistSearchError) {
    target.innerHTML = '<div class="commission-market-empty compact">' + escapeHTML(commissionArtistSearchError) + '</div>';
    return;
  }
  if (!commissionArtistSearchQuery) {
    target.innerHTML = '<div class="commission-market-empty compact">\u8f93\u5165\u7528\u6237\u540d\u6216\u6635\u79f0\u641c\u7d22\u753b\u5e08\u3002</div>';
    return;
  }
  if (!commissionArtistResults.length) {
    target.innerHTML = '<div class="commission-market-empty compact">\u6ca1\u6709\u627e\u5230\u5339\u914d\u753b\u5e08\u3002</div>';
    return;
  }
  target.innerHTML = commissionArtistResults.map(artist =>
    '<button type="button" class="commission-artist-option" onclick="selectCommissionArtist(\'' + escapeHTML(artist.id) + '\')">' +
      commissionAvatarHtml(artist.avatar, artist.username) +
      '<span><strong>' + escapeHTML(artist.displayName || artist.username) + '</strong><small>@' + escapeHTML(artist.username) + (artist.bio ? ' \u00b7 ' + escapeHTML(artist.bio) : '') + '</small></span>' +
    '</button>'
  ).join('');
}

function queueCommissionArtistSearch(value) {
  const query = String(value || '').replace(/^@/, '').trim();
  commissionArtistSearchQuery = query;
  commissionArtistSearchError = '';
  if (commissionSelectedArtist && query !== commissionSelectedArtist.username) {
    commissionSelectedArtist = null;
    const hidden = document.getElementById('commissionArtistId');
    if (hidden) hidden.value = '';
  }
  clearTimeout(commissionArtistSearchTimer);
  if (!query) {
    commissionArtistResults = [];
    renderCommissionArtistResults();
    return;
  }
  const target = document.getElementById('commissionArtistResults');
  if (target) target.innerHTML = '<div class="commission-market-empty compact">\u6b63\u5728\u641c\u7d22...</div>';
  commissionArtistSearchTimer = setTimeout(() => searchCommissionArtists(query), 260);
}

async function searchCommissionArtists(query) {
  const token = ++commissionArtistSearchToken;
  try {
    const data = await apiRequest('/custom/artists/?search=' + encodeURIComponent(query) + '&page_size=20', { auth: true });
    if (token !== commissionArtistSearchToken || query !== commissionArtistSearchQuery) return;
    const activeItem = getActiveCommissionDetail();
    commissionArtistResults = apiList(data)
      .map(artist => ({
        id: artist.id,
        username: artist.username || '',
        avatar: normalizeImageSrc(artist.avatar || artist.profile?.avatar || ''),
        displayName: artist.profile?.displayName || artist.first_name || artist.username || '',
        bio: artist.bio || artist.profile?.signature || artist.profile?.intro || ''
      }))
      .filter(artist => artist.id && artist.username && artist.username !== currentUser?.username && artist.username !== activeItem?.requester);
    commissionArtistSearchError = '';
  } catch (error) {
    if (token !== commissionArtistSearchToken) return;
    commissionArtistResults = [];
    commissionArtistSearchError = error.message || '\u753b\u5e08\u641c\u7d22\u5931\u8d25\u3002';
  }
  renderCommissionArtistResults();
}

function selectCommissionArtist(artistId) {
  const artist = commissionArtistResults.find(item => String(item.id) === String(artistId));
  if (!artist) return;
  commissionSelectedArtist = artist;
  commissionArtistSearchQuery = artist.username;
  const input = document.getElementById('commissionArtistSearch');
  const hidden = document.getElementById('commissionArtistId');
  if (input) input.value = '@' + artist.username;
  if (hidden) hidden.value = artist.id;
  renderCommissionArtistResults();
}

async function sendCommissionInvitation(event) {
  event.preventDefault();
  const artistId = document.getElementById('commissionArtistId')?.value || commissionSelectedArtist?.id || '';
  const amount = document.getElementById('commissionInviteAmount')?.value.trim() || '';
  const message = document.getElementById('commissionInviteMessage')?.value.trim() || '';
  if (!artistId) {
    alert('\u8bf7\u5148\u4ece\u641c\u7d22\u7ed3\u679c\u4e2d\u9009\u62e9\u753b\u5e08\u3002');
    return;
  }
  if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) {
    alert('\u8bf7\u586b\u5199\u5927\u4e8e 0 \u7684\u9080\u8bf7\u4ef7\u683c\u3002');
    return;
  }
  const success = await runCommissionMarketplaceAction(
    () => apiRequest('/custom/' + encodeURIComponent(activeCommissionDetailId) + '/invitations/', {
      method: 'POST',
      body: JSON.stringify({ artist_id: artistId, amount, message })
    }),
    '\u5b9a\u5411\u9080\u8bf7\u5df2\u53d1\u9001\u3002'
  );
  if (success) {
    commissionSelectedArtist = null;
    commissionArtistResults = [];
    commissionArtistSearchQuery = '';
    const item = getActiveCommissionDetail();
    if (item) renderCommissionInviteComposer(item);
  }
}

async function respondCommissionInvitation(invitationId, decision) {
  const verb = decision === 'accept' ? '\u63a5\u53d7' : '\u62d2\u7edd';
  if (!confirm('\u786e\u5b9a' + verb + '\u8fd9\u4e2a\u5b9a\u5411\u9080\u8bf7\u5417\uff1f')) return;
  await runCommissionMarketplaceAction(
    () => apiRequest('/custom/' + encodeURIComponent(activeCommissionDetailId) + '/respond-invitation/', {
      method: 'POST',
      body: JSON.stringify({ invitation_id: invitationId, decision })
    }),
    '\u5df2' + verb + '\u9080\u8bf7\u3002'
  );
}

document.getElementById('commissionDetailRefresh')?.addEventListener('click', refreshActiveCommissionDetail);

document.getElementById('publishImageBox').addEventListener('click', () => {
  document.getElementById('publishImageInput').click();
});

document.getElementById('publishImageInput').addEventListener('change', event => {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => setPublishImage(e.target.result);
  reader.readAsDataURL(file);
});

document.querySelectorAll('[data-publish-type]').forEach(button => {
  button.addEventListener('click', () => {
    if (document.getElementById('publishCardId').value) return;
    setPublishType(button.dataset.publishType);
  });
});

document.getElementById('publishForm').addEventListener('submit', event => {
  event.preventDefault();
  savePublishForm();
});

document.getElementById('publishCancelBtn').addEventListener('click', () => {
  switchPage('me');
});

document.querySelectorAll('.auth-tab').forEach(tab => {
  tab.addEventListener('click', () => setAuthMode(tab.dataset.authMode));
});

function setupSettingsPanel() {
  const profilePanel = document.querySelector('[data-profile-panel="profile"]');
  const profileGrid = profilePanel?.querySelector('.profile-grid');
  const slot = document.getElementById('settingsProfileSlot');
  if (profileGrid && slot && !slot.contains(profileGrid)) {
    slot.appendChild(profileGrid);
    profilePanel.hidden = true;
  }
  document.getElementById('openSettingsDetailBtn')?.addEventListener('click', () => {
    openSettingsPanel();
  });
  document.getElementById('openSettingsFromProfileBtn')?.addEventListener('click', openSettingsPanel);
}

setupSettingsPanel();

function openSettingsPanel() {
  document.querySelectorAll('.profile-tab').forEach(item => item.classList.toggle('active', item.dataset.profileTab === 'settings'));
  document.querySelectorAll('.profile-tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.profilePanel === 'settings');
  });
  const entry = document.getElementById('settingsEntry');
  const detail = document.getElementById('settingsDetail');
  if (entry) entry.hidden = true;
  if (detail) detail.hidden = false;
  document.querySelector('[data-profile-panel="settings"]')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

document.querySelectorAll('.profile-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.profileTab;
    document.querySelectorAll('.profile-tab').forEach(item => item.classList.toggle('active', item === tab));
    document.querySelectorAll('.profile-tab-panel').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.profilePanel === target);
    });
  });
});

document.querySelector('.profile-page')?.addEventListener('click', event => {
  const item = event.target.closest('[data-profile-interaction-type]');
  if (!item) return;
  const type = item.dataset.profileInteractionType;
  const id = item.dataset.profileInteractionId;
  if (type === 'artwork') openArtworkDetail(id);
  if (type === 'inspiration') openInspirationDetail(id);
});

document.getElementById('loginForm').addEventListener('submit', event => {
  event.preventDefault();
  handleLogin(document.getElementById('loginUsername').value.trim(), document.getElementById('loginPassword').value);
});

document.getElementById('registerForm').addEventListener('submit', event => {
  event.preventDefault();
  registerUser({
    username: document.getElementById('registerUsername').value,
    email: document.getElementById('registerEmail').value,
    password: document.getElementById('registerPassword').value,
    passwordConfirm: document.getElementById('registerPasswordConfirm').value
  });
});

document.getElementById('logoutBtn').addEventListener('click', () => {
  clearSession();
  openAuth('login', '已退出，请登录或切换账号。');
  refreshAuthUI();
});

document.getElementById('switchAccountBtn').addEventListener('click', () => {
  clearSession();
  openAuth('login', '请选择要切换的账号登录。');
  refreshAuthUI();
});

document.getElementById('previewClose').addEventListener('click', closeImagePreview);

document.getElementById('imagePreview').addEventListener('click', event => {
  if (event.target.id === 'imagePreview') closeImagePreview();
});

document.getElementById('detailClose').addEventListener('click', closeArtworkDetail);

document.getElementById('artworkDetail').addEventListener('click', event => {
  if (event.target.id === 'artworkDetail') closeArtworkDetail();
});

document.getElementById('inspirationDetailClose').addEventListener('click', closeInspirationDetail);

document.getElementById('inspirationDetail').addEventListener('click', event => {
  if (event.target.id === 'inspirationDetail') closeInspirationDetail();
});

document.getElementById('inspirationCommentForm').addEventListener('submit', event => {
  event.preventDefault();
  submitInspirationComment();
});

document.getElementById('cancelInspirationReplyBtn')?.addEventListener('click', cancelInspirationReply);

document.getElementById('commentImageBtn').addEventListener('click', () => {
  if (!requireLogin('请先登录后再发布评价。')) return;
  document.getElementById('commentImageInput').click();
});

document.getElementById('commentImageInput').addEventListener('change', event => {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    commentImageSrc = e.target.result;
    document.getElementById('commentImageName').textContent = file.name;
  };
  reader.readAsDataURL(file);
});

document.getElementById('commentForm').addEventListener('submit', event => {
  event.preventDefault();
  submitArtworkComment();
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeImagePreview();
    closeArtworkDetail();
    closeInspirationDetail();
  }
});

document.getElementById('profileAvatarBtn').addEventListener('click', () => {
  document.getElementById('profileAvatarInput').click();
});

document.getElementById('profileAvatarInput').addEventListener('change', event => {
  if (!requireLogin()) return;
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    const users = getUsers();
    const user = users[currentUser.username];
    user.profile = { ...(user.profile || {}), avatar: e.target.result };
    saveUsers(users);
    refreshAuthUI();
    renderMePage();
  };
  reader.readAsDataURL(file);
});

document.getElementById('addProfileSkillBtn').addEventListener('click', addProfileSkill);

document.getElementById('profileSkillInput').addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    addProfileSkill();
  }
});

document.getElementById('profileHomeTags')?.addEventListener('input', event => {
  renderHomeTagPreview('profileHomeTagList', splitRecommendationTags(event.target.value));
});

document.getElementById('profileForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (!requireLogin()) return;
  const users = getUsers();
  const user = users[currentUser.username];
  const homeTags = splitRecommendationTags(document.getElementById('profileHomeTags')?.value || '');
  user.profile = {
    ...user.profile,
    displayName: document.getElementById('profileDisplayNameInput').value.trim() || user.username,
    gender: document.getElementById('profileGender').value,
    birthday: document.getElementById('profileBirthday').value,
    creativeYears: document.getElementById('profileCreativeYearsInput').value.trim(),
    signature: document.getElementById('profileSignature').value.trim(),
    intro: document.getElementById('profileSignature').value.trim(),
    philosophy: document.getElementById('profilePhilosophy').value.trim(),
    skills: [...editingSkills],
    homeTags
  };
  saveUsers(users);
  alert('个人信息已保存。');
  refreshAuthUI();
  renderMePage();
  await refreshGalleryRecommendations();
});

document.getElementById('changeByOldPasswordBtn').addEventListener('click', () => {
  updatePassword(
    document.getElementById('newPasswordOld').value,
    document.getElementById('confirmPasswordOld').value,
    user => user.password === document.getElementById('oldPassword').value ? '' : '旧密码不正确。'
  );
});

document.getElementById('changeByEmailBtn').addEventListener('click', () => {
  setSettingsMessage('出于安全考虑，前端不再保存邮箱密码。请使用旧密码修改。');
});

document.getElementById('contactForm').addEventListener('submit', function(e) {
  e.preventDefault();
  if (!requireLogin('请先登录后再提交作画委托。')) return;
  const typeSelect = document.getElementById('type');
  const commissions = getCommissions();
  commissions.push({
    owner: currentUser.username,
    name: document.getElementById('name').value.trim(),
    email: document.getElementById('email').value.trim(),
    type: typeSelect.value,
    typeLabel: typeSelect.options[typeSelect.selectedIndex].textContent,
    message: document.getElementById('message').value.trim(),
    createdAt: new Date().toLocaleString(),
    status: '待确认'
  });
  saveCommissions(commissions);
  alert('委托已提交，可在“我”的页面查看。');
  this.reset();
  renderMePage();
});

document.getElementById('contactForm').addEventListener('submit', async event => {
  event.preventDefault();
  event.stopImmediatePropagation();
  if (!requireLogin('请先登录后再提交作画委托。')) return;
  const typeSelect = document.getElementById('type');
  try {
    await apiRequest('/custom/', {
      method: 'POST',
      body: JSON.stringify({
        title: document.getElementById('name').value.trim() || typeSelect.options[typeSelect.selectedIndex].textContent,
        type_label: typeSelect.options[typeSelect.selectedIndex].textContent,
        description: document.getElementById('message').value.trim(),
        budget: '可商议'
      })
    });
    alert('委托已提交，可在“我”的页面查看。');
    event.currentTarget.reset();
    await refreshCommissions();
  } catch (error) {
    alert(error.message || '提交委托失败，请确认后端服务已启动。');
  }
}, true);

// ===== Public profiles and following =====
let activePublicProfile = null;
let publicProfileArtworks = [];
let publicProfileRequestToken = 0;
let socialPreviousPage = 'gallery';
let ownSocialSummary = null;
let ownSocialSummaryPromise = null;
let socialSessionUsername = '';
let socialSessionToken = 0;
const socialListCache = { followers: [], following: [] };

function resetSocialState() {
  socialSessionToken += 1;
  publicProfileRequestToken += 1;
  activePublicProfile = null;
  publicProfileArtworks = [];
  ownSocialSummary = null;
  ownSocialSummaryPromise = null;
  socialSessionUsername = '';
  socialListCache.followers = [];
  socialListCache.following = [];
  const followerList = document.getElementById('myFollowerList');
  const followingList = document.getElementById('myFollowingList');
  if (followerList) followerList.innerHTML = '<div class="empty-state">登录后查看粉丝。</div>';
  if (followingList) followingList.innerHTML = '<div class="empty-state">登录后查看关注列表。</div>';
  const followerCount = document.getElementById('profileFollowerCount');
  const followingCount = document.getElementById('profileFollowingCount');
  if (followerCount) followerCount.textContent = '0';
  if (followingCount) followingCount.textContent = '0';
}

function normalizePublicUser(item = {}) {
  const source = item.user || item;
  const profile = source.profile && typeof source.profile === 'object' ? source.profile : {};
  const username = source.username || profile.username || '';
  const displayName = source.display_name || source.displayName || profile.displayName || username || '创作者';
  const intro = source.intro || source.bio || profile.intro || profile.signature || '';
  return {
    id: source.id ?? source.user_id ?? '',
    username,
    displayName,
    avatar: normalizeImageSrc(source.avatar || profile.avatar || ''),
    bio: source.bio || intro,
    intro,
    philosophy: source.philosophy || profile.philosophy || '',
    skills: Array.isArray(source.skills) ? source.skills : (Array.isArray(profile.skills) ? profile.skills : []),
    creativeYears: source.creative_years || source.creativeYears || profile.creativeYears || '',
    artworkCount: Number(source.artwork_count ?? source.artworkCount ?? source.artworks_count ?? 0),
    followerCount: Number(source.follower_count ?? source.followerCount ?? source.followers_count ?? 0),
    followingCount: Number(source.following_count ?? source.followingCount ?? 0),
    isFollowing: !!(source.is_following ?? source.isFollowing ?? source.following),
    isFollowedBy: !!(source.is_followed_by ?? source.isFollowedBy ?? source.follows_me),
    isMutual: !!(source.is_mutual ?? source.isMutual ?? source.mutual)
  };
}

function mergePublicUser(current, update = {}) {
  if (!current) return normalizePublicUser(update);
  const relation = normalizePublicUser({
    ...current,
    ...update,
    display_name: update.display_name ?? current.displayName,
    creative_years: update.creative_years ?? current.creativeYears,
    artwork_count: update.artwork_count ?? current.artworkCount,
    follower_count: update.follower_count ?? current.followerCount,
    following_count: update.following_count ?? current.followingCount,
    is_following: update.is_following ?? current.isFollowing,
    is_followed_by: update.is_followed_by ?? current.isFollowedBy,
    is_mutual: update.is_mutual ?? current.isMutual
  });
  return { ...current, ...relation };
}

function socialAvatarHtml(user, className = 'social-avatar') {
  const avatar = normalizeImageSrc(user?.avatar || '');
  const name = user?.displayName || user?.username || '画';
  return `<span class="${className}">${avatar
    ? `<img src="${escapeHTML(avatar)}" alt="${escapeHTML(name)}">`
    : escapeHTML(String(name).trim().slice(0, 1).toUpperCase() || '画')}</span>`;
}

function getActivePageId() {
  return document.querySelector('.page-section.active')?.id || 'home';
}

function setPublicProfileLoading(identifier) {
  activePublicProfile = null;
  publicProfileArtworks = [];
  setAvatarElement(document.getElementById('publicProfileAvatar'), '', identifier || '画');
  document.getElementById('publicProfileDisplayName').textContent = '正在加载...';
  document.getElementById('publicProfileHandle').textContent = identifier ? `@${identifier}` : '@user';
  document.getElementById('publicProfileBio').textContent = '正在读取公开资料';
  document.getElementById('publicProfileIntro').textContent = '正在读取简介...';
  document.getElementById('publicProfilePhilosophy').textContent = '';
  document.getElementById('publicProfileSkillList').innerHTML = '<span class="tool-item">加载中</span>';
  ['publicProfileArtworkCount', 'publicProfileFollowerCount', 'publicProfileFollowingCount', 'publicProfileCreativeYears'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.textContent = '0';
  });
  document.getElementById('publicProfileArtworkList').innerHTML = '<div class="empty-state">正在加载作品...</div>';
  document.getElementById('publicProfileFollowBtn').disabled = true;
  document.getElementById('publicProfileMessageBtn').disabled = true;
}

function renderPublicProfile() {
  const user = activePublicProfile;
  if (!user) return;
  setAvatarElement(document.getElementById('publicProfileAvatar'), user.avatar, user.displayName);
  document.getElementById('publicProfileDisplayName').textContent = user.displayName;
  document.getElementById('publicProfileHandle').textContent = `@${user.username}`;
  document.getElementById('publicProfileBio').textContent = user.bio || '这个人还没有填写简介。';
  document.getElementById('publicProfileIntro').textContent = user.intro || '这个人还没有填写简介。';
  document.getElementById('publicProfilePhilosophy').textContent = user.philosophy
    ? `创作理念：${user.philosophy}`
    : '暂未填写创作理念。';
  renderSkillList('publicProfileSkillList', user.skills || []);
  document.getElementById('publicProfileArtworkCount').textContent = user.artworkCount || publicProfileArtworks.length || 0;
  document.getElementById('publicProfileFollowerCount').textContent = user.followerCount;
  document.getElementById('publicProfileFollowingCount').textContent = user.followingCount;
  document.getElementById('publicProfileCreativeYears').textContent = user.creativeYears || '0';

  const isSelf = !!currentUser && user.username === currentUser.username;
  const followButton = document.getElementById('publicProfileFollowBtn');
  const messageButton = document.getElementById('publicProfileMessageBtn');
  followButton.hidden = isSelf;
  followButton.disabled = false;
  followButton.textContent = user.isFollowing ? '取消关注' : (user.isFollowedBy ? '回关' : '关注');
  followButton.classList.toggle('secondary', user.isFollowing);
  messageButton.hidden = isSelf;
  messageButton.disabled = false;
  messageButton.textContent = user.isMutual ? '私信 · 互关' : '私信';
}

function renderPublicProfileArtworks() {
  const target = document.getElementById('publicProfileArtworkList');
  if (!target) return;
  target.innerHTML = publicProfileArtworks.length
    ? publicProfileArtworks.map(item => `
      <article class="public-work-card" data-public-artwork="${escapeHTML(item.id)}" tabindex="0">
        <div class="public-work-media">${item.imageSrc
          ? `<img src="${escapeHTML(item.imageSrc)}" alt="${escapeHTML(item.name)}">`
          : '<span>暂无图片</span>'}</div>
        <div class="public-work-body">
          <strong>${escapeHTML(item.name)}</strong>
          <span>${escapeHTML(item.tag || '原创作品')} · 评价 ${Number(item.reviewsCount || 0)}</span>
        </div>
      </article>
    `).join('')
    : '<div class="empty-state">TA 还没有发布作品。</div>';
  if (activePublicProfile) {
    activePublicProfile.artworkCount = Math.max(activePublicProfile.artworkCount, publicProfileArtworks.length);
    document.getElementById('publicProfileArtworkCount').textContent = activePublicProfile.artworkCount;
  }
}

async function openUserProfile(identifier) {
  const value = String(identifier || '').replace(/^@/, '').trim();
  if (!value) return;
  if (currentUser?.username && value === currentUser.username) {
    closeArtworkDetail();
    closeInspirationDetail();
    closeCommissionDetail();
    switchPage('me');
    return;
  }
  const currentPage = getActivePageId();
  if (currentPage !== 'userProfile' && currentPage !== 'auth') socialPreviousPage = currentPage;
  closeArtworkDetail();
  closeInspirationDetail();
  closeCommissionDetail();
  setPublicProfileLoading(value);
  switchPage('userProfile');
  const token = ++publicProfileRequestToken;
  try {
    const profile = normalizePublicUser(await apiRequest(`/users/profiles/${encodeURIComponent(value)}/`));
    if (token !== publicProfileRequestToken) return;
    activePublicProfile = profile;
    renderPublicProfile();
    const artworkData = await apiRequest(`/artworks/?owner=${encodeURIComponent(profile.id)}&page_size=100&ordering=-created_at`, { auth: false });
    if (token !== publicProfileRequestToken) return;
    publicProfileArtworks = apiList(artworkData).map(artworkToCardData);
    renderPublicProfileArtworks();
  } catch (error) {
    if (token !== publicProfileRequestToken) return;
    document.getElementById('publicProfileDisplayName').textContent = '无法打开个人主页';
    document.getElementById('publicProfileBio').textContent = error.message || '用户不存在或暂时无法访问。';
    document.getElementById('publicProfileArtworkList').innerHTML = '<div class="empty-state">公开资料加载失败，请稍后重试。</div>';
  }
}

function openPublicProfileArtwork(artworkId) {
  const item = publicProfileArtworks.find(entry => String(entry.id) === String(artworkId));
  if (!item) return;
  const existing = getGalleryCard(String(item.id));
  if (existing) return openArtworkDetail(existing);
  recordView('artwork', item.id);
  document.getElementById('detailTitle').textContent = item.name;
  document.getElementById('detailTag').textContent = item.tag;
  document.getElementById('detailImage').src = item.imageSrc || '';
  document.getElementById('commentCardId').value = item.id;
  const owner = document.getElementById('detailOwner');
  owner.hidden = false;
  owner.textContent = `作者 @${item.owner}`;
  owner.dataset.userProfile = item.owner;
  renderArtworkComments(item.id);
  document.getElementById('artworkDetail').classList.remove('hidden');
  startArtworkCommentSync();
}

async function togglePublicProfileFollow() {
  if (!activePublicProfile) return;
  if (!requireLogin('请先登录后再关注创作者。')) return;
  const button = document.getElementById('publicProfileFollowBtn');
  button.disabled = true;
  try {
    const data = await apiRequest(`/users/profiles/${encodeURIComponent(activePublicProfile.username)}/follow/`, {
      method: activePublicProfile.isFollowing ? 'DELETE' : 'POST',
      body: JSON.stringify({})
    });
    activePublicProfile = mergePublicUser(activePublicProfile, data);
    ownSocialSummary = null;
    socialListCache.followers = [];
    socialListCache.following = [];
    renderPublicProfile();
    ensureOwnSocialSummary(true);
    refreshConversations({ silent: true });
  } catch (error) {
    alert(error.message || '关注操作失败，请稍后重试。');
  } finally {
    button.disabled = false;
  }
}

async function ensureOwnSocialSummary(force = false) {
  if (!currentUser?.username) return null;
  if (socialSessionUsername !== currentUser.username) {
    resetSocialState();
    socialSessionUsername = currentUser.username;
  }
  if (ownSocialSummary && !force) return ownSocialSummary;
  if (ownSocialSummaryPromise) return ownSocialSummaryPromise;
  const sessionUsername = currentUser.username;
  const sessionToken = socialSessionToken;
  const request = apiRequest(`/users/profiles/${encodeURIComponent(sessionUsername)}/`)
    .then(data => {
      if (currentUser?.username !== sessionUsername || socialSessionToken !== sessionToken) return null;
      ownSocialSummary = normalizePublicUser(data);
      const follower = document.getElementById('profileFollowerCount');
      const following = document.getElementById('profileFollowingCount');
      if (follower) follower.textContent = ownSocialSummary.followerCount;
      if (following) following.textContent = ownSocialSummary.followingCount;
      return ownSocialSummary;
    })
    .catch(error => {
      if (currentUser?.username === sessionUsername) console.warn('Social summary unavailable:', error);
      return null;
    })
    .finally(() => {
      if (ownSocialSummaryPromise === request) ownSocialSummaryPromise = null;
    });
  ownSocialSummaryPromise = request;
  return ownSocialSummaryPromise;
}

function renderSocialList(kind, items = socialListCache[kind]) {
  const target = document.getElementById(kind === 'followers' ? 'myFollowerList' : 'myFollowingList');
  if (!target) return;
  const normalized = items.map(normalizePublicUser).filter(user => user.username);
  socialListCache[kind] = normalized;
  target.innerHTML = normalized.length
    ? normalized.map(user => `
      <article class="social-user-card">
        <button class="social-user-main" type="button" data-user-profile="${escapeHTML(user.username)}">
          ${socialAvatarHtml(user)}
          <span><strong>${escapeHTML(user.displayName)}</strong><small>@${escapeHTML(user.username)}${user.isMutual ? ' · 已互关' : ''}</small></span>
        </button>
        <div class="social-user-actions">
          <button class="toolbar-btn secondary" type="button" data-message-user="${escapeHTML(user.username)}">私信</button>
          <button class="toolbar-btn${user.isFollowing ? ' secondary' : ''}" type="button" data-list-follow="${escapeHTML(user.username)}" data-is-following="${String(user.isFollowing)}">${user.isFollowing ? '取消关注' : (user.isFollowedBy ? '回关' : '关注')}</button>
        </div>
      </article>
    `).join('')
    : `<div class="empty-state">${kind === 'followers' ? '还没有粉丝。' : '还没有关注任何人。'}</div>`;
}

async function loadSocialList(kind, force = false) {
  if (!requireLogin('请先登录后查看关注关系。')) return;
  if (!['followers', 'following'].includes(kind)) return;
  await ensureOwnSocialSummary();
  const sessionUsername = currentUser?.username || '';
  const sessionToken = socialSessionToken;
  const target = document.getElementById(kind === 'followers' ? 'myFollowerList' : 'myFollowingList');
  if (socialListCache[kind].length && !force) return renderSocialList(kind);
  if (target) target.innerHTML = '<div class="empty-state">正在加载...</div>';
  try {
    const data = await apiRequest(`/users/${kind}/?page_size=100`);
    if (currentUser?.username !== sessionUsername || socialSessionToken !== sessionToken) return;
    socialListCache[kind] = apiList(data).map(normalizePublicUser);
    renderSocialList(kind);
    ensureOwnSocialSummary(true);
  } catch (error) {
    if (target && currentUser?.username === sessionUsername && socialSessionToken === sessionToken) {
      target.innerHTML = `<div class="empty-state">${escapeHTML(error.message || '列表加载失败，请稍后重试。')}</div>`;
    }
  }
}

function activateProfileSocialTab(kind) {
  if (!requireLogin('请先登录后查看关注关系。')) return;
  switchPage('me');
  const tab = document.querySelector(`.profile-tab[data-profile-tab="${kind}"]`);
  if (tab) tab.click();
  loadSocialList(kind);
}

async function toggleFollowFromList(username, isFollowing) {
  if (!requireLogin('请先登录后再关注创作者。')) return;
  try {
    await apiRequest(`/users/profiles/${encodeURIComponent(username)}/follow/`, {
      method: isFollowing ? 'DELETE' : 'POST',
      body: JSON.stringify({})
    });
    ownSocialSummary = null;
    socialListCache.followers = [];
    socialListCache.following = [];
    await Promise.allSettled([ensureOwnSocialSummary(true), loadSocialList(getActiveProfileSocialTab(), true)]);
    refreshConversations({ silent: true });
  } catch (error) {
    alert(error.message || '关注操作失败，请稍后重试。');
  }
}

function getActiveProfileSocialTab() {
  const tab = document.querySelector('.profile-tab.active')?.dataset.profileTab;
  return ['followers', 'following'].includes(tab) ? tab : 'following';
}

const profileAwareOpenArtworkDetail = openArtworkDetail;
openArtworkDetail = function(cardOrId) {
  const card = typeof cardOrId === 'string' ? getGalleryCard(cardOrId) : cardOrId;
  const data = getCardData(card);
  profileAwareOpenArtworkDetail(cardOrId);
  const owner = document.getElementById('detailOwner');
  if (!owner || !data?.owner) return;
  owner.hidden = false;
  owner.textContent = `作者 @${data.owner}`;
  owner.dataset.userProfile = data.owner;
};

const profileAwareRenderCommissionDetail = renderCommissionDetailSummary;
renderCommissionDetailSummary = function(item) {
  profileAwareRenderCommissionDetail(item);
  const requester = document.getElementById('commissionDetailRequester');
  const artist = document.getElementById('commissionDetailArtist');
  if (requester && item?.requester) {
    requester.classList.add('user-profile-link');
    requester.dataset.userProfile = item.requester;
  }
  if (artist) {
    artist.classList.toggle('user-profile-link', !!item?.artist);
    if (item?.artist) artist.dataset.userProfile = item.artist;
    else delete artist.dataset.userProfile;
  }
};

const socialAwareRenderMePage = renderMePage;
renderMePage = function() {
  socialAwareRenderMePage();
  if (currentUser) ensureOwnSocialSummary();
};

const socialAwareSwitchPage = switchPage;
switchPage = function(pageId) {
  if (pageId === 'messages' && !requireLogin('请先登录后查看私信。')) return;
  socialAwareSwitchPage(pageId);
  document.getElementById('messageNavBtn')?.classList.toggle('active', pageId === 'messages');
};

document.addEventListener('click', event => {
  const profileTrigger = event.target.closest('[data-user-profile]');
  if (profileTrigger) {
    event.preventDefault();
    event.stopPropagation();
    openUserProfile(profileTrigger.dataset.userProfile);
    return;
  }
  const messageTrigger = event.target.closest('[data-message-user]');
  if (messageTrigger) {
    event.preventDefault();
    event.stopPropagation();
    openMessages(messageTrigger.dataset.messageUser);
    return;
  }
  const followTrigger = event.target.closest('[data-list-follow]');
  if (followTrigger) {
    event.preventDefault();
    event.stopPropagation();
    toggleFollowFromList(followTrigger.dataset.listFollow, followTrigger.dataset.isFollowing === 'true');
    return;
  }
  const artwork = event.target.closest('[data-public-artwork]');
  if (artwork) openPublicProfileArtwork(artwork.dataset.publicArtwork);
}, true);

document.querySelectorAll('[data-social-list]').forEach(button => {
  button.addEventListener('click', () => activateProfileSocialTab(button.dataset.socialList));
});

document.querySelectorAll('[data-refresh-social-list]').forEach(button => {
  button.addEventListener('click', () => loadSocialList(button.dataset.refreshSocialList, true));
});

document.querySelectorAll('.profile-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    if (['followers', 'following'].includes(tab.dataset.profileTab)) loadSocialList(tab.dataset.profileTab);
  });
});

document.getElementById('publicProfileFollowBtn')?.addEventListener('click', togglePublicProfileFollow);
document.getElementById('publicProfileMessageBtn')?.addEventListener('click', () => {
  if (activePublicProfile) openMessages(activePublicProfile.username, activePublicProfile);
});
document.getElementById('publicProfileBackBtn')?.addEventListener('click', () => {
  switchPage(document.getElementById(socialPreviousPage)?.classList.contains('page-section') ? socialPreviousPage : 'gallery');
});

// ===== Direct messages =====
let messageConversations = [];
let activeMessageUser = null;
let activeMessageItems = [];
let activeMessagePage = 1;
let activeMessageHasOlder = false;
let activeMessageUnlimited = false;
let activeMessageRemaining = 3;
let activeMessageLimit = 3;
let messageThreadToken = 0;
let messageSendBusy = false;
let messageSendToken = 0;
let messageRefreshPromise = null;
let messageThreadRefreshPromise = null;
let messageSessionUsername = '';
let messagePollTimer = null;

function normalizeDirectMessage(item = {}) {
  const senderUsername = item.sender_username || item.senderUsername || '';
  return {
    id: String(item.id || ''),
    senderId: item.sender || item.sender_id || '',
    senderUsername,
    recipientId: item.recipient || item.recipient_id || '',
    recipientUsername: item.recipient_username || item.recipientUsername || '',
    body: item.body || '',
    createdAt: item.created_at || item.createdAt || '',
    readAt: item.read_at || item.readAt || '',
    isMine: Boolean(item.is_mine ?? item.isMine ?? (
      currentUser && (String(item.sender || '') === String(currentUser.id || '') || senderUsername === currentUser.username)
    ))
  };
}

function normalizeConversation(item = {}) {
  const user = normalizePublicUser(item.user || {});
  return {
    user,
    lastMessage: normalizeDirectMessage(item.last_message || item.lastMessage || {}),
    lastMessageAt: item.last_message_at || item.lastMessageAt || '',
    unreadCount: Number(item.unread_count ?? item.unreadCount ?? 0),
    unlimited: Boolean(item.unlimited),
    remainingMessages: item.remaining_messages == null ? null : Number(item.remaining_messages),
    messageLimit: Number(item.message_limit ?? item.messageLimit ?? 3)
  };
}

function formatDirectMessageTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const today = new Date();
  return date.toDateString() === today.toDateString()
    ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : date.toLocaleDateString([], { month: '2-digit', day: '2-digit' });
}

function setMessageUnreadCount(value) {
  const count = Math.max(0, Number(value || 0));
  const badge = document.getElementById('messageUnreadBadge');
  if (!badge) return;
  badge.hidden = count <= 0;
  badge.textContent = count > 99 ? '99+' : String(count);
}

function renderConversationList() {
  const target = document.getElementById('conversationList');
  if (!target) return;
  target.innerHTML = messageConversations.length
    ? messageConversations.map(item => {
      const preview = item.lastMessage.body || '开始一段对话';
      const prefix = item.lastMessage.isMine ? '我：' : '';
      const active = activeMessageUser && item.user.username === activeMessageUser.username;
      return `
        <button class="conversation-item${active ? ' active' : ''}" type="button" data-conversation-user="${escapeHTML(item.user.username)}">
          <span class="conversation-person">
            ${socialAvatarHtml(item.user, 'message-avatar')}
            <span>
              <strong>${escapeHTML(item.user.displayName)}</strong>
              <small>@${escapeHTML(item.user.username)}${item.user.isMutual ? ' · 已互关' : ''}</small>
              <span class="conversation-preview">${escapeHTML(prefix + preview)}</span>
            </span>
          </span>
          <span class="conversation-meta">
            <time>${escapeHTML(formatDirectMessageTime(item.lastMessageAt || item.lastMessage.createdAt))}</time>
            ${item.unreadCount ? `<span class="conversation-unread">${item.unreadCount > 99 ? '99+' : item.unreadCount}</span>` : ''}
          </span>
        </button>`;
    }).join('')
    : '<div class="message-empty"><strong>还没有私信</strong><span>从创作者个人主页发起第一条消息吧。</span></div>';
}

function renderMessageLimit() {
  const badge = document.getElementById('messageLimitBadge');
  const hint = document.getElementById('messageComposerHint');
  const composer = document.getElementById('messageComposer');
  const body = document.getElementById('messageBody');
  const send = document.getElementById('sendMessageBtn');
  const reached = !activeMessageUnlimited && Number(activeMessageRemaining) <= 0;
  if (badge) {
    badge.classList.toggle('unlimited', activeMessageUnlimited);
    badge.textContent = activeMessageUnlimited
      ? '互关 · 不限条数'
      : `剩余 ${Math.max(0, Number(activeMessageRemaining || 0))}/${activeMessageLimit} 条`;
  }
  if (hint) {
    hint.textContent = activeMessageUnlimited
      ? '你们已互相关注，可以自由发送私信。'
      : reached
        ? '本方向的 3 条私信已用完，双方互关后可继续发送。'
        : `对方尚未与你互关，本方向还可发送 ${Math.max(0, Number(activeMessageRemaining || 0))} 条。`;
  }
  composer?.classList.toggle('limit-reached', reached);
  if (body) body.disabled = reached || messageSendBusy;
  if (send) send.disabled = reached || messageSendBusy;
}

function renderMessageThread({ preserveScroll = false, scrollToBottom = false } = {}) {
  const welcome = document.getElementById('chatWelcome');
  const active = document.getElementById('chatActive');
  if (!activeMessageUser) {
    if (welcome) welcome.hidden = false;
    if (active) active.hidden = true;
    document.querySelector('.message-shell')?.classList.remove('chat-open');
    return;
  }
  if (welcome) welcome.hidden = true;
  if (active) active.hidden = false;
  document.querySelector('.message-shell')?.classList.add('chat-open');
  setAvatarElement(document.getElementById('chatAvatar'), activeMessageUser.avatar, activeMessageUser.displayName);
  document.getElementById('chatDisplayName').textContent = activeMessageUser.displayName;
  document.getElementById('chatUsername').textContent = `@${activeMessageUser.username}`;
  const personButton = document.getElementById('chatPersonBtn');
  if (personButton) personButton.dataset.userProfile = activeMessageUser.username;

  const history = document.getElementById('messageHistory');
  const previousHeight = history?.scrollHeight || 0;
  const previousTop = history?.scrollTop || 0;
  if (history) {
    history.innerHTML = activeMessageItems.length
      ? activeMessageItems.map(message => `
        <div class="message-row${message.isMine ? ' mine' : ''}">
          ${message.isMine ? '' : socialAvatarHtml(activeMessageUser, 'message-avatar')}
          <div class="message-bubble">
            <span>${escapeHTML(message.body)}</span>
            <time>${escapeHTML(formatCommissionTime(message.createdAt))}${message.isMine ? ` · ${message.readAt ? '已读' : '已发送'}` : ''}</time>
          </div>
        </div>`).join('')
      : '<div class="message-empty"><strong>还没有消息</strong><span>打个招呼开始交流吧。</span></div>';
    if (preserveScroll) history.scrollTop = Math.max(0, history.scrollHeight - previousHeight + previousTop);
    else if (scrollToBottom) history.scrollTop = history.scrollHeight;
  }
  const older = document.getElementById('loadOlderMessagesBtn');
  if (older) older.hidden = !activeMessageHasOlder;
  renderMessageLimit();
  renderConversationList();
}

function resetMessagingState() {
  messageConversations = [];
  activeMessageUser = null;
  activeMessageItems = [];
  activeMessagePage = 1;
  activeMessageHasOlder = false;
  activeMessageUnlimited = false;
  activeMessageRemaining = 3;
  activeMessageLimit = 3;
  messageSendBusy = false;
  messageSendToken += 1;
  messageRefreshPromise = null;
  messageThreadRefreshPromise = null;
  messageSessionUsername = '';
  messageThreadToken += 1;
  if (messagePollTimer) clearInterval(messagePollTimer);
  messagePollTimer = null;
  setMessageUnreadCount(0);
  const draft = document.getElementById('messageBody');
  if (draft) draft.value = '';
  renderConversationList();
  renderMessageThread();
}

function ensureMessageSession() {
  const username = currentUser?.username || '';
  if (messageSessionUsername !== username) {
    resetMessagingState();
    messageSessionUsername = username;
  }
  return !!username;
}

async function refreshConversations({ silent = false } = {}) {
  if (!ensureMessageSession()) return [];
  if (messageRefreshPromise) return messageRefreshPromise;
  const sessionUsername = currentUser.username;
  const target = document.getElementById('conversationList');
  if (!silent && target && !messageConversations.length) {
    target.innerHTML = '<div class="message-empty">正在加载会话...</div>';
  }

  const request = apiRequest('/users/messages/conversations/?page_size=100')
    .then(data => {
      if (currentUser?.username !== sessionUsername || messageSessionUsername !== sessionUsername) return [];
      messageConversations = apiList(data).map(normalizeConversation).filter(item => item.user.username);
      setMessageUnreadCount(data?.total_unread_count ?? messageConversations.reduce((sum, item) => sum + item.unreadCount, 0));
      if (activeMessageUser) {
        const current = messageConversations.find(item => item.user.username === activeMessageUser.username);
        if (current) {
          activeMessageUser = mergePublicUser(activeMessageUser, current.user);
          activeMessageUnlimited = current.unlimited;
          activeMessageRemaining = current.remainingMessages;
          activeMessageLimit = current.messageLimit;
        }
      }
      renderConversationList();
      if (activeMessageUser) renderMessageLimit();
      return messageConversations;
    })
    .catch(error => {
      if (!silent && target && currentUser?.username === sessionUsername) {
        target.innerHTML = `<div class="message-empty"><strong>会话加载失败</strong><span>${escapeHTML(error.message || '请稍后重试。')}</span></div>`;
      }
      if (silent) console.warn('Conversation refresh failed:', error);
      return [];
    })
    .finally(() => {
      if (messageRefreshPromise === request) messageRefreshPromise = null;
    });
  messageRefreshPromise = request;
  return request;
}

async function openMessages(identifier = '', userHint = null) {
  if (!requireLogin('请先登录后使用私信功能。')) return;
  ensureMessageSession();
  switchPage('messages');
  await refreshConversations({ silent: true });
  const username = String(identifier || '').replace(/^@/, '').trim();
  if (username) await loadMessageThread(username, 1, false, userHint);
  else renderMessageThread();
}

function mergeMessageItems(olderItems, newerItems) {
  const seen = new Set();
  return [...olderItems, ...newerItems].filter(message => {
    const key = message.id || `${message.senderUsername}:${message.recipientUsername}:${message.createdAt}:${message.body}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function markActiveConversationRead(username, token) {
  try {
    await apiRequest(`/users/messages/${encodeURIComponent(username)}/read/`, {
      method: 'POST',
      body: JSON.stringify({})
    });
    if (token === messageThreadToken && activeMessageUser?.username === username) {
      await refreshConversations({ silent: true });
    }
  } catch (error) {
    console.warn('Unable to mark messages as read:', error);
  }
}

async function loadMessageThread(identifier, page = 1, prepend = false, userHint = null) {
  if (!ensureMessageSession()) return;
  const username = String(identifier || '').replace(/^@/, '').trim();
  if (!username || username === currentUser.username) return;
  messageSendToken += 1;
  messageSendBusy = false;
  const token = ++messageThreadToken;
  const normalizedPage = Math.max(1, Number(page) || 1);
  const knownConversation = messageConversations.find(item => item.user.username === username);

  if (normalizedPage === 1) {
    if (activeMessageUser?.username !== username) {
      const draft = document.getElementById('messageBody');
      if (draft) draft.value = '';
    }
    activeMessageUser = userHint
      ? normalizePublicUser(userHint)
      : (knownConversation?.user || normalizePublicUser({ username, display_name: username }));
    activeMessageItems = [];
    activeMessagePage = 1;
    activeMessageHasOlder = false;
    activeMessageUnlimited = knownConversation?.unlimited || false;
    activeMessageRemaining = knownConversation?.remainingMessages ?? 3;
    activeMessageLimit = knownConversation?.messageLimit || 3;
    renderMessageThread();
    const history = document.getElementById('messageHistory');
    if (history) history.innerHTML = '<div class="message-empty">正在加载消息...</div>';
  } else {
    const olderButton = document.getElementById('loadOlderMessagesBtn');
    if (olderButton) {
      olderButton.disabled = true;
      olderButton.textContent = '正在加载...';
    }
  }

  try {
    const data = await apiRequest(`/users/messages/${encodeURIComponent(username)}/?page=${normalizedPage}&page_size=50`);
    if (token !== messageThreadToken || currentUser?.username !== messageSessionUsername) return;
    const responseUser = normalizePublicUser(data?.user || { username });
    activeMessageUser = activeMessageUser
      ? mergePublicUser(activeMessageUser, responseUser)
      : responseUser;
    const incoming = apiList(data?.messages).map(normalizeDirectMessage);
    activeMessageItems = prepend
      ? mergeMessageItems(incoming, activeMessageItems)
      : mergeMessageItems([], incoming);
    activeMessagePage = normalizedPage;
    activeMessageHasOlder = !!data?.messages?.next;
    activeMessageUnlimited = Boolean(data?.unlimited);
    activeMessageRemaining = data?.remaining_messages == null ? null : Number(data.remaining_messages);
    activeMessageLimit = Number(data?.message_limit || 3);
    renderMessageThread({ preserveScroll: prepend, scrollToBottom: !prepend });
    if (normalizedPage === 1) void markActiveConversationRead(username, token);
  } catch (error) {
    if (token !== messageThreadToken) return;
    const history = document.getElementById('messageHistory');
    if (history) {
      history.innerHTML = `<div class="message-empty"><strong>消息加载失败</strong><span>${escapeHTML(error.message || '请稍后重试。')}</span></div>`;
    }
  } finally {
    if (token === messageThreadToken) {
      const olderButton = document.getElementById('loadOlderMessagesBtn');
      if (olderButton) {
        olderButton.disabled = false;
        olderButton.textContent = '加载更早消息';
      }
    }
  }
}

async function loadOlderMessages() {
  if (!activeMessageUser || !activeMessageHasOlder) return;
  await loadMessageThread(activeMessageUser.username, activeMessagePage + 1, true, activeMessageUser);
}

async function sendDirectMessage(event) {
  event?.preventDefault();
  if (!activeMessageUser || messageSendBusy) return;
  const input = document.getElementById('messageBody');
  const body = String(input?.value || '').trim();
  if (!body) {
    input?.focus();
    return;
  }
  const sessionUsername = currentUser?.username || '';
  const recipientUsername = activeMessageUser.username;
  const threadToken = messageThreadToken;
  const sendToken = ++messageSendToken;
  const isCurrentSend = () => (
    sendToken === messageSendToken
    && threadToken === messageThreadToken
    && currentUser?.username === sessionUsername
    && activeMessageUser?.username === recipientUsername
  );
  messageSendBusy = true;
  renderMessageLimit();
  try {
    const data = await apiRequest(`/users/messages/${encodeURIComponent(recipientUsername)}/`, {
      method: 'POST',
      body: JSON.stringify({ body })
    });
    if (!isCurrentSend()) {
      if (currentUser?.username === sessionUsername) refreshConversations({ silent: true });
      return;
    }
    const message = normalizeDirectMessage(data?.message || {});
    if (message.id && !activeMessageItems.some(item => item.id === message.id)) activeMessageItems.push(message);
    activeMessageUnlimited = Boolean(data?.unlimited);
    activeMessageRemaining = data?.remaining_messages == null ? null : Number(data.remaining_messages);
    activeMessageLimit = Number(data?.message_limit || 3);
    if (input) input.value = '';
    renderMessageThread({ scrollToBottom: true });
    await refreshConversations({ silent: true });
  } catch (error) {
    if (!isCurrentSend()) return;
    const state = error.data && typeof error.data === 'object' ? error.data : {};
    if ('unlimited' in state) activeMessageUnlimited = Boolean(state.unlimited);
    if ('remaining_messages' in state) {
      activeMessageRemaining = state.remaining_messages == null ? null : Number(state.remaining_messages);
    }
    if ('message_limit' in state) activeMessageLimit = Number(state.message_limit || 3);
    alert(error.message || '私信发送失败，请稍后重试。');
  } finally {
    if (!isCurrentSend()) return;
    messageSendBusy = false;
    renderMessageLimit();
    input?.focus();
  }
}

async function refreshActiveMessageThread() {
  if (messageThreadRefreshPromise || !currentUser || !activeMessageUser || getActivePageId() !== 'messages') {
    return messageThreadRefreshPromise;
  }
  const sessionUsername = currentUser.username;
  const recipientUsername = activeMessageUser.username;
  const threadToken = messageThreadToken;
  const history = document.getElementById('messageHistory');
  const previousTop = history?.scrollTop || 0;
  const wasNearBottom = !history || history.scrollHeight - history.scrollTop - history.clientHeight < 90;

  const request = apiRequest(`/users/messages/${encodeURIComponent(recipientUsername)}/?page=1&page_size=50`)
    .then(data => {
      if (
        currentUser?.username !== sessionUsername
        || activeMessageUser?.username !== recipientUsername
        || messageThreadToken !== threadToken
      ) return;
      const incoming = apiList(data?.messages).map(normalizeDirectMessage);
      const indexes = new Map(activeMessageItems.map((message, index) => [message.id, index]));
      incoming.forEach(message => {
        if (message.id && indexes.has(message.id)) {
          const index = indexes.get(message.id);
          activeMessageItems[index] = { ...activeMessageItems[index], ...message };
        } else {
          indexes.set(message.id, activeMessageItems.length);
          activeMessageItems.push(message);
        }
      });
      activeMessageUser = mergePublicUser(activeMessageUser, data?.user || {});
      activeMessageUnlimited = Boolean(data?.unlimited);
      activeMessageRemaining = data?.remaining_messages == null ? null : Number(data.remaining_messages);
      activeMessageLimit = Number(data?.message_limit || 3);
      if (activeMessagePage === 1) activeMessageHasOlder = !!data?.messages?.next;
      renderMessageThread({ scrollToBottom: wasNearBottom });
      if (!wasNearBottom && history) history.scrollTop = previousTop;
      if (incoming.some(message => !message.isMine && !message.readAt)) {
        void markActiveConversationRead(recipientUsername, threadToken);
      }
    })
    .catch(error => console.warn('Active conversation refresh failed:', error))
    .finally(() => {
      if (messageThreadRefreshPromise === request) messageThreadRefreshPromise = null;
    });
  messageThreadRefreshPromise = request;
  return request;
}

function startMessagePolling() {
  if (messagePollTimer || !currentUser) return;
  messagePollTimer = setInterval(async () => {
    if (!currentUser || document.visibilityState === 'hidden') return;
    await refreshConversations({ silent: true });
    await refreshActiveMessageThread();
  }, 30000);
}

document.getElementById('messageNavBtn')?.addEventListener('click', () => openMessages());
document.getElementById('refreshConversationsBtn')?.addEventListener('click', async () => {
  await refreshConversations();
  if (activeMessageUser) await loadMessageThread(activeMessageUser.username, 1, false, activeMessageUser);
});
document.getElementById('messageComposer')?.addEventListener('submit', sendDirectMessage);
document.getElementById('messageBody')?.addEventListener('keydown', event => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    document.getElementById('messageComposer')?.requestSubmit();
  }
});
document.getElementById('loadOlderMessagesBtn')?.addEventListener('click', loadOlderMessages);
document.getElementById('chatBackBtn')?.addEventListener('click', () => {
  document.querySelector('.message-shell')?.classList.remove('chat-open');
});
document.getElementById('conversationList')?.addEventListener('click', event => {
  const item = event.target.closest('[data-conversation-user]');
  if (item) loadMessageThread(item.dataset.conversationUser);
});

const directMessageSwitchPage = switchPage;
switchPage = function(pageId) {
  const result = directMessageSwitchPage(pageId);
  if (pageId === 'messages' && currentUser) {
    ensureMessageSession();
    startMessagePolling();
    refreshConversations({ silent: true });
  }
  return result;
};

const directMessageClearSession = clearSession;
clearSession = function() {
  directMessageClearSession();
  resetSocialState();
  resetMessagingState();
};

const directMessageRefreshAuthUI = refreshAuthUI;
refreshAuthUI = function() {
  directMessageRefreshAuthUI();
  if (currentUser) {
    ensureMessageSession();
    startMessagePolling();
    refreshConversations({ silent: true });
  } else {
    resetMessagingState();
  }
};

const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) entry.target.classList.add('visible');
  });
}, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

window.addEventListener('DOMContentLoaded', async () => {
  await restoreCurrentUserSession();
  getUsers();
  loadCommissionOptions().catch(error => {
    console.warn('Commission options API unavailable:', error);
    renderCommissionOptions();
  });
  initCommissionPage();
  renderInspirations();
  renderCommissionBoard();
  refreshCommissions();
  initGalleryPaginationObserver();
  const loadedFromApi = await loadGalleryFromApi();
  if (!loadedFromApi) {
    loadGallery();
  }
  prepareCardOwnership();
  if (!loadedFromApi) {
    await ensureArtworkRecords();
  }
  normalizeCardActions();
  normalizeCommentButtons();
  applyCardPermissions();
  renderGalleryPagination();
  refreshAuthUI();
  const initialPage = location.hash ? location.hash.slice(1) : 'home';
  const normalizedInitialPage = initialPage === 'about' ? 'me' : initialPage;
  switchPage(document.getElementById(normalizedInitialPage)?.classList.contains('page-section') ? normalizedInitialPage : 'home');
});
