/**
 * 相册网格：等高行式（justified rows）布局
 *
 * 与 Google Photos / Flickr 的相册一致：
 *   - 逐行放置照片，统一行高，行宽自动撑满容器
 *   - 横竖构图混排时观感整齐，不留空洞
 *   - 只渲染当前需要的一批行（按滚动位置续算），几千张也不卡
 */

import { imageSrc, formatDateShort, exposureSummary } from './data.js';

const ROW_HEIGHT = 236;      // 目标行高（紧凑模式 150）
const ROW_HEIGHT_COMPACT = 150;
const GAP = 6;
const ROWS_PER_BATCH = 6;    // 每次补渲染的行数（大图库下减少滚动抖动）

const aspectOf = (p) => {
  const a = Number(p.aspect);
  if (Number.isFinite(a) && a > 0.05 && a < 20) return a;
  return 1.5; // 未知比例时的默认（3:2）
};

function computeRows(items, width, targetH, from) {
  const rows = [];
  let row = [];
  let sum = 0;
  for (let i = from; i < items.length; i++) {
    const a = aspectOf(items[i]);
    row.push(i);
    sum += a;
    // 假设行高为 targetH 时需要的宽度
    const needed = sum * targetH + GAP * (row.length - 1);
    if (needed >= width) {
      const h = (width - GAP * (row.length - 1)) / sum;
      rows.push({ indices: row, height: h });
      row = [];
      sum = 0;
    }
  }
  if (row.length) {
    // 最后一行不足宽：不拉伸，用目标行高
    rows.push({ indices: row, height: targetH, incomplete: true });
  }
  return rows;
}

export function createGrid({ container, sentinel, onOpen }) {
  let items = [];
  let density = 'full';
  let renderedRows = 0;
  let rows = [];
  let width = 0;
  let observer = null;

  const targetHeight = () => (density === 'compact' ? ROW_HEIGHT_COMPACT : ROW_HEIGHT);

  function card(rec) {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'card';
    el.dataset.id = rec.i;
    el.title = [rec.l, rec.d, exposureSummary(rec)].filter(Boolean).join(' · ');
    el.style.background = rec.cl || 'var(--ph)';
    el.style.flex = `${aspectOf(rec)} 1 0`;
    el.style.aspectRatio = String(aspectOf(rec));
    el.style.height = '100%';

    const img = document.createElement('img');
    img.src = imageSrc(rec, 'thumb');
    img.alt = rec.x || rec.l || rec.d || '照片';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.addEventListener('load', () => el.classList.add('is-loaded'), { once: true });
    img.addEventListener('error', () => el.classList.add('is-error'), { once: true });
    el.append(img);

    const meta = document.createElement('div');
    meta.className = 'card-meta';
    meta.innerHTML = `<span class="card-date">${formatDateShort(rec.d)}</span>${
      rec.l ? `<span class="card-loc">${escapeHtml(rec.l)}</span>` : ''
    }`;
    el.append(meta);

    if (rec.r) {
      const star = document.createElement('span');
      star.className = 'card-star';
      star.textContent = '★'.repeat(Math.min(5, rec.r));
      el.append(star);
    }
    if (rec.g && !rec.l) {
      const pin = document.createElement('span');
      pin.className = 'card-pin';
      pin.textContent = '📍';
      el.append(pin);
    }

    el.addEventListener('click', () => onOpen(rec.i, items));
    return el;
  }

  function rowEl(row) {
    const div = document.createElement('div');
    div.className = 'grid-row';
    div.style.height = `${Math.round(row.height)}px`;
    for (const i of row.indices) div.append(card(items[i]));
    return div;
  }

  function renderNextBatch() {
    if (!width) width = container.clientWidth || 900;
    if (!rows.length) rows = computeRows(items, width, targetHeight(), 0);
    if (renderedRows >= rows.length) return false;

    const frag = document.createDocumentFragment();
    let n = 0;
    while (renderedRows < rows.length && n < ROWS_PER_BATCH) {
      frag.append(rowEl(rows[renderedRows]));
      renderedRows++;
      n++;
    }
    container.append(frag);
    return renderedRows < rows.length;
  }

  /** 视口驱动的续渲染：只判断"还需要再放几行" */
  function checkFill() {
    if (renderedRows >= rows.length) return;
    const last = container.lastElementChild;
    if (!last) { if (renderNextBatch()) scheduleCheck(); return; }
    const rect = last.getBoundingClientRect();
    if (rect.top < window.innerHeight + 600) {
      if (renderNextBatch()) scheduleCheck();
    }
  }

  let scheduled = false;
  function scheduleCheck() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; checkFill(); });
  }

  function ensureObserver() {
    if (observer || !sentinel) return;
    observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) checkFill();
    }, { rootMargin: '900px 0px' });
    observer.observe(sentinel);
  }

  function relayout(force = false) {
    const w = container.clientWidth || width;
    if (!w) return;
    if (!force && Math.abs(w - width) < 2 && renderedRows) return;
    width = w;
    const keepRows = Math.max(1, renderedRows);
    rows = computeRows(items, width, targetHeight(), 0);
    container.replaceChildren();
    renderedRows = 0;
    const frag = document.createDocumentFragment();
    for (let r = 0; r < Math.min(keepRows, rows.length); r++) {
      frag.append(rowEl(rows[r]));
      renderedRows++;
    }
    container.append(frag);
    scheduleCheck();
  }

  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(relayout, 120);
  });

  return {
    setItems(list) {
      items = list;
      renderedRows = 0;
      rows = [];
      width = container.clientWidth || 900;
      container.replaceChildren();
      rows = computeRows(items, width, targetHeight(), 0);
      renderNextBatch();
      ensureObserver();
      scheduleCheck();
    },
    setDensity(d) {
      density = d;
      container.classList.toggle('is-compact', d === 'compact');
      renderedRows = 0;
      rows = [];
      container.replaceChildren();
      relayout(true);
      scheduleCheck();
    },
    /** 追加一批（例如"加载更多月份"）；会重排，因此只在必要时使用 */
    append(list) {
      items = items.concat(list);
      renderedRows = 0;
      rows = computeRows(items, width || container.clientWidth || 900, targetHeight(), 0);
      container.replaceChildren();
      renderNextBatch();
      scheduleCheck();
    },
    get count() { return items.length; },
    get rendered() { return renderedRows; },
    relayout,
  };
}

export function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
