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
  authTokens: 'starSakuraAuthTokens'
};
const GALLERY_ITEMS_PER_PAGE = 8;
let galleryCurrentPage = 1;
let galleryPaginationObserver = null;
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
  const skipAuth = [
    '/users/login/',
    '/users/register/',
    '/users/token/refresh/',
  ].includes(path) || options.auth === false;
  const isPublicRead = method === 'GET' && /^\/(artworks|custom|reviews|inspirations)\//.test(path);
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    headers: apiHeaders(options.headers || {}, !skipAuth && !isPublicRead)
  });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401 && !skipAuth && !isPublicRead) clearSession();
  if (!response.ok) throw new Error(payload.message || '请求失败');
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
    imageSrc: normalizeImageSrc(item.image_url || item.image || '')
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

function setAvatarElement(element, avatarSrc, fallbackName) {
  if (!element) return;
  if (avatarSrc) {
    element.innerHTML = `<img src="${avatarSrc}" alt="${escapeHTML(fallbackName)}">`;
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
          <div class="comment-author">${escapeHTML(name)}</div>
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
  const totalPages = Math.max(1, Math.ceil(cards.length / GALLERY_ITEMS_PER_PAGE));
  galleryCurrentPage = Math.min(Math.max(1, galleryCurrentPage), totalPages);
  const start = (galleryCurrentPage - 1) * GALLERY_ITEMS_PER_PAGE;
  const end = start + GALLERY_ITEMS_PER_PAGE;
  cards.forEach((card, index) => {
    card.hidden = index < start || index >= end;
  });
  if (cards.length <= GALLERY_ITEMS_PER_PAGE) {
    pagination.innerHTML = '';
    pagination.hidden = true;
    return;
  }
  pagination.hidden = false;
  const pageButtons = Array.from({ length: totalPages }, (_, index) => {
    const page = index + 1;
    return `<button type="button" class="gallery-page-btn${page === galleryCurrentPage ? ' active' : ''}" data-gallery-page="${page}" aria-label="第 ${page} 页">${page}</button>`;
  }).join('');
  pagination.innerHTML = `
    <button type="button" class="gallery-page-btn" data-gallery-page="prev" ${galleryCurrentPage === 1 ? 'disabled' : ''}>上一页</button>
    ${pageButtons}
    <span class="gallery-page-info">${galleryCurrentPage} / ${totalPages}</span>
    <button type="button" class="gallery-page-btn" data-gallery-page="next" ${galleryCurrentPage === totalPages ? 'disabled' : ''}>下一页</button>
  `;
  pagination.querySelectorAll('[data-gallery-page]').forEach(button => {
    button.addEventListener('click', () => {
      const action = button.dataset.galleryPage;
      if (action === 'prev') galleryCurrentPage -= 1;
      else if (action === 'next') galleryCurrentPage += 1;
      else galleryCurrentPage = Number(action) || 1;
      renderGalleryPagination();
      document.getElementById('gallery')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function initGalleryPaginationObserver() {
  const grid = document.getElementById('galleryGrid');
  if (!grid || galleryPaginationObserver) return;
  galleryPaginationObserver = new MutationObserver(() => {
    window.requestAnimationFrame(renderGalleryPagination);
  });
  galleryPaginationObserver.observe(grid, { childList: true });
  renderGalleryPagination();
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
      reviewsCount: Number(card.dataset.reviewsCount || 0)
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
    const items = apiList(await apiRequest('/artworks/?page_size=100&ordering=created_at'));
    const grid = document.getElementById('galleryGrid');
    grid.innerHTML = '';
    items.forEach(item => createGalleryCard(artworkToCardData(item)));
    cardIdCounter = Math.max(10, ...items.map(item => Number(item.id)).filter(Boolean)) + 1;
    localStorage.removeItem(STORAGE.gallery);
    renderMePage();
    return true;
  } catch (error) {
    console.warn('Artwork API load failed, falling back to local gallery:', error);
    return false;
  }
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
    galleryData.forEach((data, index) => {
      const card = document.createElement('div');
      card.className = 'character-card fade-in visible';
      card.dataset.id = String(data.id);
      card.dataset.owner = data.owner || (ORIGINAL_CARD_IDS.has(String(data.id)) ? 'admin' : (currentUser?.username || 'admin'));
      card.dataset.original = String(data.original ?? ORIGINAL_CARD_IDS.has(String(data.id)));
      card.dataset.saved = String(data.saved === true);
      card.dataset.reviewsCount = String(data.reviewsCount || 0);
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
        </div>
      `;
      grid.appendChild(card);
    });
    normalizeCardActions();
    normalizeCommentButtons();
    cardIdCounter = Math.max(10, ...galleryData.map(d => parseInt(d.id, 10)).filter(Boolean)) + 1;
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
      <span class="blog-date">${escapeHTML(getInspirationDisplayTime(item))} · ${escapeHTML(item.owner)}</span>
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
  const legacy = JSON.parse(localStorage.getItem(STORAGE.commissions) || '[]').map(normalizeCommissionItem);
  if (!legacy.length) {
    localStorage.setItem('starSakuraCommissionsMigrated', 'true');
    return;
  }
  for (const item of legacy) {
    await apiRequest('/custom/', {
      method: 'POST',
      body: JSON.stringify(commissionToApiPayload(item))
    });
  }
  localStorage.setItem('starSakuraCommissionsMigrated', 'true');
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
      <span class="blog-date">${escapeHTML(getInspirationDisplayTime(item))} · ${escapeHTML(item.owner)}</span>
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
        <div class="comment-author">${escapeHTML(name)}</div>
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
  activeInspirationId = String(inspirationId);
  inspirationReplyTarget = '';
  document.getElementById('inspirationDetailTitle').textContent = item.title;
  document.getElementById('inspirationDetailTag').textContent = item.tag || '灵感';
  document.getElementById('inspirationDetailOwner').textContent = item.owner ? `作者：${item.owner}` : '';
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

const inspirationAwareRenderMePage = renderMePage;
renderMePage = function() {
  inspirationAwareRenderMePage();
  refreshMyInspirationList();
  ensureInspirationsLoaded().then(() => refreshMyInspirationList());
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

document.querySelectorAll('.profile-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    const target = tab.dataset.profileTab;
    document.querySelectorAll('.profile-tab').forEach(item => item.classList.toggle('active', item === tab));
    document.querySelectorAll('.profile-tab-panel').forEach(panel => {
      panel.classList.toggle('active', panel.dataset.profilePanel === target);
    });
  });
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

document.getElementById('profileForm').addEventListener('submit', event => {
  event.preventDefault();
  if (!requireLogin()) return;
  const users = getUsers();
  const user = users[currentUser.username];
  user.profile = {
    ...user.profile,
    displayName: document.getElementById('profileDisplayNameInput').value.trim() || user.username,
    gender: document.getElementById('profileGender').value,
    birthday: document.getElementById('profileBirthday').value,
    creativeYears: document.getElementById('profileCreativeYearsInput').value.trim(),
    signature: document.getElementById('profileSignature').value.trim(),
    intro: document.getElementById('profileSignature').value.trim(),
    philosophy: document.getElementById('profilePhilosophy').value.trim(),
    skills: [...editingSkills]
  };
  saveUsers(users);
  alert('个人信息已保存。');
  refreshAuthUI();
  renderMePage();
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
