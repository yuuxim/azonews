// ── State ─────────────────────────────────────────────────────
const state = {
  activeCategory: 'all',
  activeStatus: 'all',
  activeScale: 'all',
  searchQuery: '',
  sortBy: 'newest',
  viewMode: 'grid',
  showNotifPanel: false,
  notifications: [...NOTIFICATIONS],
  wishlist: new Set(),
  selectedProduct: null,
  toasts: [],
  toastIdCounter: 0,
};

// ── Helpers ───────────────────────────────────────────────────
function fmt(price) {
  return price.toLocaleString('ja-JP');
}

function timeAgo(date) {
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function getStatusLabel(status) {
  return {
    'in-stock': 'In Stock',
    'restock': 'Restock',
    'pre-order': 'Pre-Order',
    'out-of-stock': 'Sold Out',
  }[status] || status;
}

function getCategoryIcon(category) {
  const icons = {
    original: '🎀', character: '🌸', body: '✨', clothing: '👗', supplies: '🔧'
  };
  return icons[category] || '◈';
}

function getSeriesColor(series) {
  const hash = [...series].reduce((a, c) => a + c.charCodeAt(0), 0);
  const colors = ['#e8c87a', '#7be8a0', '#7baee8', '#e87b7b', '#b87be8', '#e8a07b', '#7be8e0'];
  return colors[hash % colors.length];
}

// ── Filter & Sort ─────────────────────────────────────────────
function getFilteredProducts() {
  let products = [...PRODUCTS];

  if (state.activeCategory !== 'all') {
    products = products.filter(p => p.category === state.activeCategory);
  }
  if (state.activeStatus !== 'all') {
    products = products.filter(p => p.status === state.activeStatus);
  }
  if (state.activeScale !== 'all') {
    products = products.filter(p => p.scale === state.activeScale);
  }
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    products = products.filter(p =>
      p.name.toLowerCase().includes(q) ||
      p.series.toLowerCase().includes(q) ||
      (p.nameJp && p.nameJp.includes(q))
    );
  }

  products.sort((a, b) => {
    if (state.sortBy === 'newest') return new Date(b.releaseDate) - new Date(a.releaseDate);
    if (state.sortBy === 'price-asc') return a.price - b.price;
    if (state.sortBy === 'price-desc') return b.price - a.price;
    if (state.sortBy === 'name') return a.name.localeCompare(b.name);
    if (state.sortBy === 'status') {
      const order = { restock: 0, 'in-stock': 1, 'pre-order': 2, 'out-of-stock': 3 };
      return (order[a.status] ?? 9) - (order[b.status] ?? 9);
    }
    return 0;
  });

  return products;
}

function getCounts() {
  const counts = { all: PRODUCTS.length };
  CATEGORIES.slice(1).forEach(cat => {
    counts[cat.id] = PRODUCTS.filter(p => p.category === cat.id).length;
  });
  return counts;
}

function getStatusCounts() {
  const statuses = ['in-stock', 'restock', 'pre-order', 'out-of-stock'];
  const counts = { all: PRODUCTS.length };
  statuses.forEach(s => { counts[s] = PRODUCTS.filter(p => p.status === s).length; });
  return counts;
}

// ── Render Helpers ────────────────────────────────────────────
function renderTags(tags, size = 'sm') {
  return tags.map(t => `<span class="tag tag-${t}">${t}</span>`).join('');
}

function renderStatusPill(status) {
  return `<span class="status-pill ${status}">${getStatusLabel(status)}</span>`;
}

function renderCardImage(product) {
  const icon = getCategoryIcon(product.category);
  const color = getSeriesColor(product.series);
  return `
    <div class="card-image" style="background: linear-gradient(135deg, var(--bg-secondary), rgba(${hexToRgb(color)}, 0.05))">
      <div class="card-image-placeholder">
        <span class="doll-icon">${icon}</span>
        <span class="series-label">${product.series}</span>
      </div>
      <div class="card-tags">${renderTags(product.tags)}</div>
      <button class="card-wishlist ${state.wishlist.has(product.id) ? 'active' : ''}"
              onclick="toggleWishlist(event, ${product.id})" title="Add to wishlist">
        ${state.wishlist.has(product.id) ? '♥' : '♡'}
      </button>
    </div>
  `;
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

// ── Product Card ──────────────────────────────────────────────
function renderProductCard(product) {
  const isRestock = product.status === 'restock';
  const isPreorder = product.status === 'pre-order';
  const classes = [
    'product-card',
    isRestock ? 'is-restock' : '',
    isPreorder ? 'is-preorder' : '',
  ].filter(Boolean).join(' ');

  return `
    <div class="${classes}" onclick="openModal(${product.id})">
      ${renderCardImage(product)}
      <div class="card-body">
        <div class="card-series">${product.series}</div>
        <div class="card-name">${product.name}</div>
        <div class="card-meta">
          <span class="card-scale">${product.scale}</span>
          <span>${new Date(product.releaseDate).toLocaleDateString('en-US', { year: 'numeric', month: 'short' })}</span>
        </div>
      </div>
      <div class="card-footer">
        <div class="card-price"><span class="yen">¥</span>${fmt(product.price)}</div>
        ${renderStatusPill(product.status)}
      </div>
    </div>
  `;
}

// ── Ticker ────────────────────────────────────────────────────
function renderTicker() {
  const items = [
    ...PRODUCTS.filter(p => p.status === 'restock').map(p =>
      `<span class="ticker-item"><span class="ticker-dot restock"></span>RESTOCK · ${p.name}</span>`
    ),
    ...PRODUCTS.filter(p => p.status === 'pre-order').map(p =>
      `<span class="ticker-item"><span class="ticker-dot preorder"></span>PRE-ORDER · ${p.name}</span>`
    ),
    ...PRODUCTS.filter(p => p.tags.includes('new')).map(p =>
      `<span class="ticker-item"><span class="ticker-dot new"></span>NEW · ${p.name}</span>`
    ),
  ];
  const doubled = [...items, ...items];
  document.getElementById('ticker-content').innerHTML = doubled.join('');
}

// ── Sidebar ───────────────────────────────────────────────────
function renderSidebar() {
  const counts = getCounts();
  const statusCounts = getStatusCounts();
  const scales = [...new Set(PRODUCTS.map(p => p.scale))].sort();

  // Categories
  const catHtml = CATEGORIES.map(cat => `
    <div class="nav-item ${state.activeCategory === cat.id ? 'active' : ''}"
         onclick="setCategory('${cat.id}')">
      <span class="nav-item-icon">${cat.icon}</span>
      <span>${cat.label}</span>
      <span class="nav-count">${counts[cat.id] || 0}</span>
    </div>
  `).join('');
  document.getElementById('sidebar-categories').innerHTML = catHtml;

  // Status Filters
  const statusItems = [
    { id: 'all', label: 'All Status' },
    { id: 'in-stock', label: 'In Stock' },
    { id: 'restock', label: 'Restock' },
    { id: 'pre-order', label: 'Pre-Order' },
    { id: 'out-of-stock', label: 'Sold Out' },
  ];
  const statusHtml = statusItems.map(s => `
    <div class="status-btn ${state.activeStatus === s.id ? 'active' : ''}"
         onclick="setStatus('${s.id}')">
      <span class="status-dot ${s.id}"></span>
      ${s.label}
      <span style="margin-left:auto;font-size:11px;color:var(--text-muted)">${statusCounts[s.id] || 0}</span>
    </div>
  `).join('');
  document.getElementById('sidebar-status').innerHTML = statusHtml;

  // Scale Filters
  const scaleHtml = [
    `<div class="status-btn ${state.activeScale === 'all' ? 'active' : ''}" onclick="setScale('all')">
      <span style="font-size:12px">⬜</span> All Scales
    </div>`,
    ...scales.map(s => `
      <div class="status-btn ${state.activeScale === s ? 'active' : ''}" onclick="setScale('${s}')">
        <span style="font-size:12px">▪</span> ${s}
        <span style="margin-left:auto;font-size:11px;color:var(--text-muted)">
          ${PRODUCTS.filter(p => p.scale === s).length}
        </span>
      </div>
    `)
  ].join('');
  document.getElementById('sidebar-scales').innerHTML = scaleHtml;
}

// ── Main Content ──────────────────────────────────────────────
function renderContent() {
  const filtered = getFilteredProducts();
  const restockItems = filtered.filter(p => p.status === 'restock');
  const unreadCount = state.notifications.filter(n => !n.read).length;

  // Restock banner
  const bannerHtml = restockItems.length > 0 ? `
    <div class="restock-banner" onclick="setStatus('restock')">
      <div class="restock-banner-dot"></div>
      <div class="restock-banner-text">
        <strong>${restockItems.length} item${restockItems.length > 1 ? 's' : ''} restocked</strong>
        — ${restockItems.map(p => p.name.split('/')[1]?.trim() || p.name).join(', ')}
      </div>
      <span class="restock-banner-arrow">→</span>
    </div>
  ` : '';
  document.getElementById('restock-banner').innerHTML = bannerHtml;

  // Active filters chips
  const chips = [];
  if (state.activeCategory !== 'all') {
    const cat = CATEGORIES.find(c => c.id === state.activeCategory);
    chips.push(`<div class="filter-chip" onclick="setCategory('all')">${cat?.label} <span class="remove">×</span></div>`);
  }
  if (state.activeStatus !== 'all') {
    chips.push(`<div class="filter-chip" onclick="setStatus('all')">${getStatusLabel(state.activeStatus)} <span class="remove">×</span></div>`);
  }
  if (state.activeScale !== 'all') {
    chips.push(`<div class="filter-chip" onclick="setScale('all')">${state.activeScale} <span class="remove">×</span></div>`);
  }
  if (state.searchQuery) {
    chips.push(`<div class="filter-chip" onclick="clearSearch()">"${state.searchQuery}" <span class="remove">×</span></div>`);
  }
  document.getElementById('active-filters').innerHTML = chips.join('');

  // Result count
  document.getElementById('result-count').innerHTML =
    `Showing <span>${filtered.length}</span> of <span>${PRODUCTS.length}</span> products`;

  // Notification badge
  document.getElementById('notif-badge').textContent = unreadCount;
  document.getElementById('notif-badge').style.display = unreadCount > 0 ? 'flex' : 'none';

  // Wishlist count
  document.getElementById('wishlist-count').textContent = state.wishlist.size;
  document.getElementById('wishlist-count').style.display = state.wishlist.size > 0 ? 'flex' : 'none';

  // Sort select
  document.getElementById('sort-select').value = state.sortBy;

  // View mode
  document.getElementById('btn-grid').classList.toggle('active', state.viewMode === 'grid');
  document.getElementById('btn-list').classList.toggle('active', state.viewMode === 'list');

  // Products
  const grid = document.getElementById('product-grid');
  grid.className = 'product-grid' + (state.viewMode === 'list' ? ' list-view' : '');

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>No products found</h3>
        <p>Try adjusting your filters or search query.</p>
      </div>
    `;
  } else {
    grid.innerHTML = filtered.map(renderProductCard).join('');
  }
}

// ── Notification Panel ────────────────────────────────────────
function renderNotifPanel() {
  if (!state.showNotifPanel) {
    document.getElementById('notif-panel').style.display = 'none';
    return;
  }
  document.getElementById('notif-panel').style.display = 'block';

  const listHtml = state.notifications.length === 0
    ? `<div class="notif-empty">No notifications yet</div>`
    : state.notifications.map(n => {
        const product = PRODUCTS.find(p => p.id === n.productId);
        return `
          <div class="notif-item ${n.read ? '' : 'unread'}" onclick="markRead(${n.id})">
            <div class="notif-icon ${n.type}">
              ${n.type === 'restock' ? '🔄' : '🔔'}
            </div>
            <div class="notif-content">
              <div class="notif-message">${n.message}</div>
              <div class="notif-time">${timeAgo(n.timestamp)}</div>
            </div>
          </div>
        `;
      }).join('');

  document.getElementById('notif-list').innerHTML = listHtml;
}

// ── Modal ─────────────────────────────────────────────────────
function renderModal() {
  const overlay = document.getElementById('modal-overlay');
  if (!state.selectedProduct) {
    overlay.style.display = 'none';
    document.body.style.overflow = '';
    return;
  }

  const p = state.selectedProduct;
  overlay.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  const icon = getCategoryIcon(p.category);
  const color = getSeriesColor(p.series);

  const extraInfo = [
    p.restockDate ? `
      <div class="modal-info-item" style="border-color:rgba(224,149,82,0.3);background:rgba(224,149,82,0.05)">
        <div class="modal-info-label" style="color:var(--orange)">Restock Date</div>
        <div class="modal-info-value">${new Date(p.restockDate).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</div>
      </div>
    ` : '',
    p.restockQty ? `
      <div class="modal-info-item" style="border-color:rgba(224,149,82,0.3);background:rgba(224,149,82,0.05)">
        <div class="modal-info-label" style="color:var(--orange)">Availability</div>
        <div class="modal-info-value" style="color:var(--orange)">${p.restockQty}</div>
      </div>
    ` : '',
    p.preOrderDeadline ? `
      <div class="modal-info-item" style="border-color:rgba(82,152,224,0.3);background:rgba(82,152,224,0.05)">
        <div class="modal-info-label" style="color:var(--blue)">Pre-Order Deadline</div>
        <div class="modal-info-value">${new Date(p.preOrderDeadline).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</div>
      </div>
    ` : '',
  ].filter(Boolean).join('');

  const btnLabel = {
    'in-stock': 'View on Azone Shop',
    'restock': 'View Restock on Azone Shop',
    'pre-order': 'Pre-Order on Azone Shop',
    'out-of-stock': 'View on Azone Shop',
  }[p.status] || 'View on Azone Shop';

  document.getElementById('modal-content').innerHTML = `
    <div class="modal-image" style="background:linear-gradient(135deg,var(--bg-secondary),rgba(${hexToRgb(color)},0.08))">
      <span class="doll-icon-lg">${icon}</span>
    </div>
    <div class="modal-body">
      <div class="modal-series">${p.series}</div>
      <div class="modal-title">${p.name}</div>
      <div class="modal-title-jp">${p.nameJp}</div>
      <div class="modal-tags">
        ${renderTags(p.tags, 'md')}
        ${renderStatusPill(p.status)}
      </div>
      <div class="modal-grid">
        <div class="modal-info-item">
          <div class="modal-info-label">Scale</div>
          <div class="modal-info-value">${p.scale}</div>
        </div>
        <div class="modal-info-item">
          <div class="modal-info-label">Price (incl. tax)</div>
          <div class="modal-info-value">¥${fmt(p.price)}</div>
        </div>
        <div class="modal-info-item">
          <div class="modal-info-label">Release Date</div>
          <div class="modal-info-value">${new Date(p.releaseDate).toLocaleDateString('en-US', { year: 'numeric', month: 'long' })}</div>
        </div>
        <div class="modal-info-item">
          <div class="modal-info-label">Category</div>
          <div class="modal-info-value">${CATEGORIES.find(c => c.id === p.category)?.label || p.category}</div>
        </div>
        ${extraInfo}
      </div>
      <div class="modal-description">${p.description}</div>
      <div class="modal-actions">
        <button class="btn-primary" onclick="goToAzone(${p.id})">
          ↗ ${btnLabel}
        </button>
        <button class="btn-secondary" onclick="toggleWishlistModal(${p.id})">
          ${state.wishlist.has(p.id) ? '♥ Wishlisted' : '♡ Wishlist'}
        </button>
        <button class="btn-secondary" onclick="closeModal()">Close</button>
      </div>
    </div>
  `;
}

// ── Toast System ──────────────────────────────────────────────
function showToast(message, type = 'restock') {
  const id = ++state.toastIdCounter;
  state.toasts.push({ id, message, type });
  renderToasts();
  setTimeout(() => removeToast(id), 5000);
}

function removeToast(id) {
  const el = document.getElementById(`toast-${id}`);
  if (el) {
    el.classList.add('removing');
    setTimeout(() => {
      state.toasts = state.toasts.filter(t => t.id !== id);
      renderToasts();
    }, 300);
  }
}

function renderToasts() {
  document.getElementById('toast-container').innerHTML = state.toasts.map(t => `
    <div class="toast" id="toast-${t.id}">
      <div class="toast-dot ${t.type}"></div>
      <div class="toast-text">${t.message}</div>
      <button class="toast-close" onclick="removeToast(${t.id})">×</button>
    </div>
  `).join('');
}

// ── Actions ───────────────────────────────────────────────────
function setCategory(id) {
  state.activeCategory = id;
  renderSidebar();
  renderContent();
}

function setStatus(id) {
  state.activeStatus = id;
  renderSidebar();
  renderContent();
}

function setScale(id) {
  state.activeScale = id;
  renderSidebar();
  renderContent();
}

function clearSearch() {
  state.searchQuery = '';
  document.getElementById('search-input').value = '';
  renderContent();
}

function openModal(id) {
  state.selectedProduct = PRODUCTS.find(p => p.id === id);
  renderModal();
}

function closeModal() {
  state.selectedProduct = null;
  renderModal();
}

function toggleNotifPanel() {
  state.showNotifPanel = !state.showNotifPanel;
  if (state.showNotifPanel) {
    setTimeout(() => {
      document.addEventListener('click', closeNotifPanelOutside, { once: true });
    }, 0);
  }
  renderNotifPanel();
}

function closeNotifPanelOutside(e) {
  const panel = document.getElementById('notif-panel');
  const btn = document.getElementById('notif-btn');
  if (!panel.contains(e.target) && !btn.contains(e.target)) {
    state.showNotifPanel = false;
    renderNotifPanel();
  } else if (state.showNotifPanel) {
    document.addEventListener('click', closeNotifPanelOutside, { once: true });
  }
}

function markRead(id) {
  const n = state.notifications.find(n => n.id === id);
  if (n) n.read = true;
  renderNotifPanel();
  renderContent();
}

function clearAllNotifications() {
  state.notifications.forEach(n => n.read = true);
  renderNotifPanel();
  renderContent();
}

function toggleWishlist(event, id) {
  event.stopPropagation();
  if (state.wishlist.has(id)) {
    state.wishlist.delete(id);
  } else {
    state.wishlist.add(id);
    const p = PRODUCTS.find(p => p.id === id);
    showToast(`Added "${p.name.split('/')[1]?.trim() || p.name}" to wishlist`, 'preorder');
  }
  renderContent();
}

function toggleWishlistModal(id) {
  if (state.wishlist.has(id)) {
    state.wishlist.delete(id);
  } else {
    state.wishlist.add(id);
    const p = PRODUCTS.find(p => p.id === id);
    showToast(`Added to wishlist`, 'preorder');
  }
  renderModal();
  renderContent();
}

function goToAzone(id) {
  window.open('https://www.azone-int.co.jp/azonet/', '_blank');
}

// ── Search ────────────────────────────────────────────────────
let searchTimeout;
function onSearch(value) {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    state.searchQuery = value.trim();
    renderContent();
  }, 200);
}

// ── Sort & View ───────────────────────────────────────────────
function onSort(value) {
  state.sortBy = value;
  renderContent();
}

function setView(mode) {
  state.viewMode = mode;
  renderContent();
}

// ── Keyboard ──────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (state.selectedProduct) closeModal();
    if (state.showNotifPanel) { state.showNotifPanel = false; renderNotifPanel(); }
  }
  if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(e.target.tagName)) {
    e.preventDefault();
    document.getElementById('search-input').focus();
  }
});

// ── Demo Toasts ───────────────────────────────────────────────
function startDemoToasts() {
  setTimeout(() => {
    showToast('🔄 Ex☆Cute / Miu "Dreamy Lolita" just restocked — limited units!', 'restock');
  }, 1500);
  setTimeout(() => {
    showToast('🔔 New pre-order: Ex☆Cute "Starry Night" Anniversary Edition', 'preorder');
  }, 6000);
  setTimeout(() => {
    showToast('🔄 Sugar★Cups / Shocolara restock confirmed for July 15', 'restock');
  }, 14000);
}

// ── Init ──────────────────────────────────────────────────────
function init() {
  renderTicker();
  renderSidebar();
  renderContent();
  renderNotifPanel();
  startDemoToasts();

  document.getElementById('search-input').addEventListener('input', e => onSearch(e.target.value));
  document.getElementById('sort-select').addEventListener('change', e => onSort(e.target.value));

  document.getElementById('modal-overlay').addEventListener('click', e => {
    if (e.target === document.getElementById('modal-overlay')) closeModal();
  });
}

document.addEventListener('DOMContentLoaded', init);
