/**
 * 站点主逻辑：加载索引 → 筛选 → 渲染各视图
 */

import { store, imageSrc, formatDateShort, formatDate, dateSourceLabel, coordsText } from './data.js';
import { apply, describe, withFilter } from '../../src/filters.js';
import { createGrid } from './grid.js';
import { createFilterPanel } from './filters.js';
import { createLightbox } from './lightbox.js';
import { createMap } from './map.js';
import { renderTimeline } from './timeline.js';
import { renderStats } from './stats.js';
import { createImportView } from './importview.js';
import { createDupsView } from './dups.js';
import { createHomeView } from './home.js';
import { escapeHtml, download, debounce } from '../../src/util.js';

const $ = (sel) => document.querySelector(sel);

const state = {
  filter: withFilter({}),
  view: 'grid',
  density: 'full',
  photos: [],
  filtered: [],
  seq: [],
};

let grid;
let lb;
let map;
let panel;
let importView;
let dupsView;
let homeView;

/* ------------------------------------------------------------------ */
/* 启动                                                                */
/* ------------------------------------------------------------------ */

async function boot() {
  window.__pjBooting = false;   // 告诉看门狗：脚本已经跑起来了
  await store.load();

  const idx = store.index;
  document.title = idx.title || '摄影记录';
  $('#site-title').textContent = idx.title || '摄影记录';
  const sub = store.isEmpty
    ? ['还没有照片，切到「导入」页把文件夹拖进来即可']
    : [idx.subtitle, `${idx.stats.photos} 张照片`,
      idx.stats.firstDate ? `${idx.stats.firstDate} → ${idx.stats.lastDate}` : null,
      idx.stats.withGps ? `${idx.stats.withGps} 张含 GPS` : null].filter(Boolean);
  $('#site-sub').textContent = sub.join(' · ');

  state.photos = store.photos;
  state.filtered = store.photos;

  grid = createGrid({
    container: $('#grid'),
    sentinel: $('#grid-sentinel'),
    onOpen: (id, list) => openPhoto(id, list),
  });

  lb = createLightbox({
    root: $('#lightbox'),
    onIndexChange: (id) => {
      lb.syncHash();
      if (id) {
        const el = document.querySelector(`.card[data-id="${id}"]`);
        if (el) el.setAttribute('aria-current', 'true');
      }
    },
  });

  map = createMap({
    canvas: $('#map-canvas'),
    tip: $('#map-tip'),
    onPick: (point) => {
      state.filter = withFilter(state.filter, { locations: [point.name] });
      setView('grid');
      refresh();
    },
  });

  panel = createFilterPanel({
    host: $('#filters'),
    onChange: (f) => { state.filter = f; syncFiltersToHash(); refresh(); },
  });

  // 导入页：拖文件夹 → 当场解析 → 合并写入 public/
  importView = createImportView();

  // 重复照片：用感知哈希分组
  dupsView = createDupsView({
    onOpen: (id, list) => openPhoto(id, list),
  });
  dupsView.setSource(store.photos);

  // 首页：随机一张照片 → 点云
  homeView = createHomeView({
    onOpenPhoto: (id, list) => openPhoto(id, list),
    onEnterGallery: () => setView('grid'),
  });
  homeView.setPhotos(store.photos);

  bindUI(idx);
  parseHash();
  refresh();
  lb.syncHash();

  // 没有数据时直接停在导入页，避免看到空相册；有数据则默认停在首页
  setView(store.isEmpty ? 'import' : 'home');

  // 便于排查问题：在浏览器控制台里可以查看 window.__pj
  window.__pj = {
    state, store, grid, lb, map, panel, refresh, setView,
    reload: reloadSite,
    resetFilters,
    highlightIds,
    importView,
    dupsView,
    home: homeView,
  };
}

/** 清空所有筛选条件 */
function resetFilters() {
  state.filter = withFilter({});
  const searchBox = $('#search');
  if (searchBox) searchBox.value = '';
  syncFiltersToHash();
  refresh();
}

/**
 * 高亮某些照片（刚导入的那些），并在相册里标出来。
 * 网格是分块渲染的，因此渲染完成后还要再补一次标记。
 */
function highlightIds(ids) {
  const set = new Set(ids || []);
  const mark = () => {
    let hit = 0;
    for (const card of document.querySelectorAll('#grid .card')) {
      const on = set.has(card.dataset.id);
      card.classList.toggle('is-new', on);
      if (on) hit++;
    }
    return hit;
  };

  const first = mark();
  if (first < set.size) {
    // 还有没渲染出来的，下一帧、以及稍后再补一次
    requestAnimationFrame(mark);
    setTimeout(mark, 400);
    setTimeout(mark, 1200);
  }
  setTimeout(() => {
    for (const card of document.querySelectorAll('.card.is-new')) card.classList.remove('is-new');
  }, 20000);
}

/** 从磁盘/网络重新读取索引并刷新界面 */
async function reloadSite() {
  const wasEmpty = store.isEmpty;
  await store.load();
  state.photos = store.photos;
  lastDupCountFor = -1;      // 数据变了，重复组要重算
  const idx = store.index;
  document.title = idx.title || '摄影记录';
  $('#site-title').textContent = idx.title || '摄影记录';
  $('#site-sub').textContent = store.isEmpty
    ? '还没有照片，切到「导入」页把文件夹拖进来即可'
    : [idx.subtitle, `${idx.stats.photos} 张照片`,
      idx.stats.firstDate ? `${idx.stats.firstDate} → ${idx.stats.lastDate}` : null,
      idx.stats.withGps ? `${idx.stats.withGps} 张含 GPS` : null].filter(Boolean).join(' · ');
  refresh();
  homeView?.setPhotos(store.photos);
  if (wasEmpty && !store.isEmpty) setView('grid');
  else if (state.view === 'home') homeView?.activate();
}

/* ------------------------------------------------------------------ */
/* 事件绑定                                                            */
/* ------------------------------------------------------------------ */

function bindUI(idx) {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => setView(tab.dataset.view));
  }

  for (const btn of document.querySelectorAll('.seg-btn')) {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.seg-btn').forEach((b) => b.classList.toggle('is-active', b === btn));
      state.density = btn.dataset.density;
      grid.setDensity(state.density);
    });
  }

  $('#reset-filters').addEventListener('click', () => {
    state.filter = withFilter({});
    $('#search').value = '';
    refresh();
  });

  $('#search').addEventListener('input', debounce((e) => {
    state.filter = withFilter(state.filter, { text: e.target.value.trim() || null });
    refresh();
  }, 220));

  $('#export-btn').addEventListener('click', () => {
    const rows = state.filtered.map((p) => ({
      id: p.i, date: p.d, time: p.t || null, location: p.l || null,
      coords: p.g ? { lat: p.g[0], lng: p.g[1] } : null,
      camera: p.c || null, lens: p.e || null,
      shutter: p.s || null, aperture: p.a || null, iso: p.o || null, focal: p.f || null,
      tags: p.k || null, caption: p.x || null, thumbnail: p.th || null,
    }));
    download(`photo-journal-selection-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(rows, null, 2));
    toast(`已导出 ${rows.length} 条记录`);
  });

  $('#map-fit').addEventListener('click', () => map.reset());

  // 移动端：筛选面板收放
  const sidebarToggle = $('#sidebar-toggle');
  sidebarToggle.addEventListener('click', () => {
    const open = $('#sidebar').classList.toggle('is-open');
    sidebarToggle.setAttribute('aria-expanded', String(open));
  });

  document.addEventListener('pj:goto-map', (e) => {
    const rec = e.detail;
    lb.close();
    setView('map');
    setTimeout(() => map.focusOn?.(rec), 30);
  });

  window.addEventListener('hashchange', () => {
    const m = /^#p=(.+)$/.exec(location.hash);
    if (m) {
      const id = decodeURIComponent(m[1]);
      if (!lb.isOpen()) openPhoto(id, state.seq.length ? state.seq : state.filtered);
    } else if (lb.isOpen()) {
      lb.close();
    }
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      $('#search').focus();
    }
  });

  $('#review-count').textContent = String(countNeedReview());
}

/* ------------------------------------------------------------------ */
/* 视图切换与刷新                                                       */
/* ------------------------------------------------------------------ */

function setView(view) {
  state.view = view;
  for (const tab of document.querySelectorAll('.tab')) {
    const on = tab.dataset.view === view;
    tab.classList.toggle('is-active', on);
    tab.setAttribute('aria-selected', String(on));
  }
  for (const v of ['home', 'import', 'grid', 'timeline', 'map', 'stats', 'dups', 'review']) {
    const el = document.querySelector(`#view-${v}`);
    if (el) el.hidden = v !== view;
  }
  // 首页的点云只在可见时动画
  homeView?.[view === 'home' ? 'activate' : 'deactivate']?.();
  // 导入页有自己的状态，不需要走 refresh 的渲染分支
  if (view === 'import') {
    importView?.activate?.();
    return;
  }
  if (view === 'home') return;
  // 每次切换都重新渲染当前视图（view 为 'map' 时 refresh 里会重画画布）
  refresh();
}

function refresh() {
  state.filtered = apply(state.photos, state.filter);
  state.seq = state.filtered;
  updateSummary();
  renderActiveFilters();

  if (state.view === 'grid') {
    grid.setItems(state.filtered);
    $('#grid-empty').hidden = state.filtered.length > 0;
  } else if (state.view === 'timeline') {
    renderTimeline($('#timeline'), state.filtered, {
      onOpen: (id, list) => openPhoto(id, list),
      onMonthClick: (mk, list) => {
        state.filter = withFilter(state.filter, { months: [mk] });
        syncFiltersToHash();
        setView('grid');
        refresh();
      },
    });
    $('#timeline-empty').hidden = state.filtered.length > 0;
  } else if (state.view === 'map') {
    map.setPhotos(state.filtered);
    map.render();
    renderLegend();
    // 视图刚从 display:none 切回来时，画布尺寸可能还是 0，下一帧再量一次
    requestAnimationFrame(() => { map.render(); });
  } else if (state.view === 'stats') {
    renderStats($('#stats'), state.filtered, {
      stats: store.index.stats,
      onPickLocation: (name) => {
        state.filter = withFilter(state.filter, { locations: [name] });
        setView('grid');
        refresh();
      },
      onPickCamera: (name) => {
        state.filter = withFilter(state.filter, { cameras: [name] });
        setView('grid');
        refresh();
      },
    });
  } else if (state.view === 'review') {
    renderReview();
  } else if (state.view === 'dups') {
    dupsView.setSource(state.photos);
    dupsView.render(state.filtered.length === state.photos.length ? state.photos : state.filtered);
  }

  // 重复组数写进标签页角标：数据只有几百到几千条，浏览器里算起来很快
  updateDupsBadge();

  // 没有数据时不必算筛选项（首次使用时站点是空的）
  if (!state.photos.length) {
    $('#review-count').textContent = '0';
    return;
  }

  // 侧栏筛选数字基于"排除自身维度"的结果，避免出现 0 项
  const forFacets = apply(state.photos, withFilter(state.filter, {
    years: [], months: [], locations: [], cameras: [], lenses: [], tags: [], ratings: [], dateSources: [], hasGps: null,
  }));
  panel.update(forFacets.length ? forFacets : state.photos, state.filter);
  $('#review-count').textContent = String(countNeedReview());
}

let lastDupCountFor = -1;
let lastDupCount = 0;

/** 计算重复组数并更新标签页角标（照片数量没变就复用上次结果） */
function updateDupsBadge() {
  const el = $('#dups-count');
  if (!el || !dupsView) return;
  if (state.photos.length === lastDupCountFor) {
    el.textContent = lastDupCount ? String(lastDupCount) : '';
    return;
  }
  try {
    dupsView.setSource(state.photos);
    dupsView.render(state.photos);
    lastDupCount = dupsView.count() || 0;
    lastDupCountFor = state.photos.length;
    el.textContent = lastDupCount ? String(lastDupCount) : '';
  } catch {
    el.textContent = '';
  }
}

function updateSummary() {
  const n = state.filtered.length;
  const total = state.photos.length;
  $('#sidebar-foot').hidden = total === 0;
  if (!total) {
    $('#grid-summary').textContent = '站点里还没有照片，切到「导入」页拖入文件夹即可';
    $('#map-summary').textContent = '';
    return;
  }
  const parts = [`共 ${n} 张`];
  if (n !== total) parts.push(`（全部 ${total} 张）`);
  const dates = state.filtered.map((p) => p.d).filter((d) => /^\d{4}/.test(d || '')).sort();
  if (dates.length) parts.push(`${formatDateShort(dates[0])} → ${formatDateShort(dates[dates.length - 1])}`);
  const gps = state.filtered.filter((p) => p.g).length;
  if (gps) parts.push(`${gps} 张有坐标`);
  $('#grid-summary').textContent = parts.join(' · ');
  $('#map-summary').textContent = `${gps} 张带 GPS 的照片，聚合为 ${new Set(state.filtered.filter((p) => p.g).map((p) => `${p.g[0].toFixed(2)},${p.g[1].toFixed(2)}`)).size} 个位置`;
  $('#stats-line').textContent = store.isEmpty || !store.index.generatedAt
    ? '尚未导入照片'
    : `数据生成于 ${new Date(store.index.generatedAt).toLocaleString('zh-CN')}｜来源：${store.index.source || '-'}`;
}

function renderActiveFilters() {
  const host = $('#active-filters');
  host.replaceChildren();
  for (const d of describe(state.filter)) {
    const pill = document.createElement('span');
    pill.className = 'pill';
    pill.innerHTML = `${escapeHtml(d.label)}<button type="button" aria-label="移除">✕</button>`;
    pill.querySelector('button').addEventListener('click', () => {
      const cur = state.filter[d.dim];
      if (Array.isArray(cur)) {
        state.filter = withFilter(state.filter, { [d.dim]: cur.filter((x) => x !== d.value) });
      } else {
        state.filter = withFilter(state.filter, { [d.dim]: null });
        if (d.dim === 'text') $('#search').value = '';
      }
      syncFiltersToHash();
      refresh();
    });
    host.append(pill);
  }
}

function renderLegend() {
  const host = $('#map-legend');
  const pts = map.points || [];
  host.replaceChildren();
  if (!pts.length) {
    host.innerHTML = '<span class="muted">当前筛选下没有带 GPS 坐标的照片。想补上坐标？见 README 的“地点坐标”一节。</span>';
    return;
  }
  const byYear = new Map();
  for (const p of pts) {
    const y = p.first ? p.first.slice(0, 4) : '未知';
    byYear.set(y, (byYear.get(y) || 0) + p.count);
  }
  host.innerHTML = [...byYear.entries()].sort((a, b) => b[0].localeCompare(a[0]))
    .map(([y, n]) => `<span><i style="background:var(--accent)"></i>${y} 年 · ${n} 张</span>`).join('')
    + `<span class="muted">｜点位 ${pts.length} 个，光点越大照片越多，点击可按地点筛选</span>`;
}

/* ------------------------------------------------------------------ */
/* 待确认列表                                                          */
/* ------------------------------------------------------------------ */

function needsReview(p) {
  if (!p.l) return '缺少地点';
  if (p.ds === 'mtime' || p.src === 'mtime') return '日期来自文件时间';
  if (!p.d) return '缺少日期';
  if (/^\d{2}-\d{2}$/.test(p.d)) return '年份未确定';
  return null;
}

function countNeedReview() {
  return store.photos.filter((p) => needsReview(p)).length;
}

function renderReview() {
  const host = $('#review-list');
  host.replaceChildren();
  const list = state.filtered.filter((p) => needsReview(p));
  $('#review-empty').hidden = list.length > 0;
  for (const p of list.slice(0, 300)) {
    const row = document.createElement('div');
    row.className = 'review-row';
    const why = needsReview(p);
    row.innerHTML = `
      <img loading="lazy" src="${imageSrc(p, 'thumb')}" alt="" style="background:${p.cl || 'var(--ph)'}" />
      <div>
        <div>${escapeHtml(p.x || p.d || '未命名')} <span class="muted small">${escapeHtml(p.l || '')}</span></div>
        <div class="path">${escapeHtml(p.th || '')}</div>
      </div>
      <div class="why">${escapeHtml(why)}</div>`;
    row.addEventListener('click', () => openPhoto(p.i, state.filtered));
    row.style.cursor = 'zoom-in';
    host.append(row);
  }
  if (list.length > 300) {
    const more = document.createElement('p');
    more.className = 'muted small';
    more.textContent = `仅显示前 300 条，共 ${list.length} 条待确认。`;
    host.append(more);
  }
}

/* ------------------------------------------------------------------ */
/* 工具                                                                */
/* ------------------------------------------------------------------ */

function openPhoto(id, list) {
  const seq = list && list.length ? list : state.filtered;
  const i = seq.findIndex((p) => p.i === id);
  if (i < 0) return;
  lb.show(seq, i);
}

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 2200);
}

/** 把筛选与选中照片写进地址栏，方便分享 */
function syncFiltersToHash() {
  const params = new URLSearchParams();
  const f = state.filter;
  if (f.years?.length) params.set('y', f.years.join(','));
  if (f.months?.length) params.set('m', f.months.join(','));
  if (f.locations?.length) params.set('l', f.locations.join('|'));
  if (f.cameras?.length) params.set('c', f.cameras.join('|'));
  if (f.lenses?.length) params.set('e', f.lenses.join('|'));
  if (f.tags?.length) params.set('t', f.tags.join(','));
  if (f.text) params.set('q', f.text);
  const p = state.seq?.[0]?.i && lb?.isOpen() ? lb : null;
  const hash = p ? `#p=${p.id}` : '';
  const qs = params.toString();
  history.replaceState(null, '', `${location.pathname}${qs ? '?' + qs : ''}${hash}`);
}

function parseHash() {
  const params = new URLSearchParams(location.search);
  const f = {};
  if (params.get('y')) f.years = params.get('y').split(',');
  if (params.get('m')) f.months = params.get('m').split(',');
  if (params.get('l')) f.locations = params.get('l').split('|');
  if (params.get('c')) f.cameras = params.get('c').split('|');
  if (params.get('e')) f.lenses = params.get('e').split('|');
  if (params.get('t')) f.tags = params.get('t').split(',');
  if (params.get('q')) { f.text = params.get('q'); $('#search').value = f.text; }
  state.filter = withFilter(state.filter, f);

  const m = /^#p=(.+)$/.exec(location.hash);
  if (m) {
    const id = decodeURIComponent(m[1]);
    // 需要等筛选完成后再定位
    setTimeout(() => openPhoto(id, state.filtered), 0);
  }
}

boot();
