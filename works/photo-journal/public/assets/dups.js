/**
 * 「重复照片」视图
 *
 * 用感知哈希把"内容相同或视觉上几乎一样"的照片分组，并给出建议保留哪一张。
 * 站点的搜索索引里已经带了每张的指纹（search.json 的 ph 字段），
 * 所以这里不需要重新读图，分组在浏览器里瞬间完成。
 */

import { findDuplicates, sortGroupByKeeper, hamming, parseSignature } from '../../src/dup.js';
import { imageSrc, formatDateShort, humanBytes } from './data.js';
import { escapeHtml, ignoredIds, setIgnored, clearIgnored, ignoredCount } from '../../src/util.js';

const $ = (s) => document.querySelector(s);

/**
 * search.json 的精简条目 → 本页要用的形状
 * （字段名不同：i/d/l/th/r/ph…，这里统一成长名字，渲染与"建议保留"都用它）
 */
function normalize(p) {
  return {
    id: p.i,
    path: p.path || p.th || '(未知路径)',
    date: p.d || null,
    bytes: p.b || p.bytes || 0,
    pixel: p.px ? { width: p.px[0], height: p.px[1] } : (p.pixel || null),
    rating: p.r ?? 0,
    location: p.l || null,
    camera: p.c ? { make: null, model: p.c } : null,
    lens: p.e || null,
    thumb: p.th || null,
    phash: p.ph || p.phash || null,
  };
}

let threshold = 5;
let maxColorDistance = 7;
let groups = [];
let photos = [];
let allPhotos = [];
let onOpenPhoto = () => {};

export function createDupsView({ onOpen }) {
  if (!$('#dups-list')) return { render() {}, count: () => 0 };
  if (onOpen) onOpenPhoto = onOpen;

  // 恢复上次的阈值设置
  const savedT = Number(localStorage.getItem('pj-dup-threshold'));
  const savedC = Number(localStorage.getItem('pj-dup-color'));
  if (Number.isFinite(savedT) && savedT >= 0 && savedT <= 12) threshold = savedT;
  if (Number.isFinite(savedC) && savedC >= 0 && savedC <= 24) maxColorDistance = savedC;

  const sliderT = $('#dups-threshold');
  const sliderC = $('#dups-color');
  if (sliderT) sliderT.value = String(threshold);
  if (sliderC) sliderC.value = String(maxColorDistance);
  const labelT = $('#dups-t1-val');
  const labelC = $('#dups-t2-val');
  if (labelT) labelT.textContent = String(threshold);
  if (labelC) labelC.textContent = String(maxColorDistance);

  const applyThresholds = () => {
    if (labelT) labelT.textContent = String(threshold);
    if (labelC) labelC.textContent = String(maxColorDistance);
    try {
      localStorage.setItem('pj-dup-threshold', String(threshold));
      localStorage.setItem('pj-dup-color', String(maxColorDistance));
    } catch { /* 忽略 */ }
    renderList();
  };

  sliderT?.addEventListener('input', () => { threshold = Number(sliderT.value); applyThresholds(); });
  sliderC?.addEventListener('input', () => { maxColorDistance = Number(sliderC.value); applyThresholds(); });

  /* 懒加载缩略图对应的"真实文件路径"（详情按月文件存放，用到时才取） */
  const pathById = new Map();
  let pathsLoading = false;
  const ensurePaths = async () => {
    if (pathsLoading || pathById.size) return;
    pathsLoading = true;
    try {
      const { store } = await import('./data.js');
      const months = [...new Set(photos.map((p) => (p.date || '').slice(0, 7)).filter((m) => /^\d{4}-\d{2}$/.test(m)))];
      for (const m of months) {
        const list = await store.loadMonth(m).catch(() => []);
        for (const rec of list || []) if (rec?.id && rec?.path) pathById.set(rec.id, rec.path);
      }
    } catch { /* 拿不到就算了，显示缩略图地址 */ }
    pathsLoading = false;
    if (pathById.size) renderList();
  };

  $('#dups-clear-ignored')?.addEventListener('click', () => {
    clearIgnored();
    renderList();
  });

  $('#dups-list')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const id = btn.closest('[data-id]')?.dataset.id;
    if (!id) return;
    const act = btn.dataset.act;
    if (act === 'keep') {
      // 保留这张 → 同组其它张记为"忽略"
      const group = groups.find((g) => g.photos.some((p) => p.id === id));
      if (group) {
        for (const p of group.photos) if (p.id !== id) setIgnored(p.id, true);
      }
      renderList();
    } else if (act === 'ignore') {
      setIgnored(id, true);
      renderList();
    } else if (act === 'unignore') {
      setIgnored(id, false);
      renderList();
    } else if (act === 'open') {
      onOpenPhoto(id, photos);
    }
  });

  function recompute() {
    const result = findDuplicates(photos, { threshold, maxColorDistance });
    groups = result.groups;
    return result;
  }

  function renderSummary(stats) {
    const host = $('#dups-summary');
    if (!host) return;
    const ign = ignoredCount();
    const kpi = (v, l, warn) => `<div class="kpi${warn ? ' warn' : ''}"><b>${v}</b><span>${l}</span></div>`;
    host.innerHTML = [
      kpi(groups.length, '重复组数', groups.length > 0),
      kpi(stats.photosInGroups, '涉及照片'),
      kpi(stats.redundant, '可精简张数'),
      kpi(humanBytes(stats.wastedBytes), '可省空间'),
      kpi(ign, '已忽略'),
      kpi(photos.filter((p) => p.ph).length, '已比对指纹'),
    ].join('');
  }

  /** 一组里"这张是第几号"的提示：与保留项的距离 */
  function distanceLabel(group, p) {
    const keeperSig = parseSignature(group.keeper?.phash);
    const sig = parseSignature(p.phash);
    if (!keeperSig.dhash || !sig.dhash) return '';
    const d = hamming(keeperSig.dhash, sig.dhash);
    return d === 0 ? '与保留项完全一致' : `与保留项结构差异 ${d}`;
  }

  function renderList() {
    const host = $('#dups-list');
    if (!host) return;
    const stats = recompute().stats;
    renderSummary(stats);
    host.replaceChildren();

    const empty = $('#dups-empty');
    if (empty) empty.hidden = groups.length > 0;

    const ignored = ignoredIds();

    for (const group of groups) {
      const el = document.createElement('div');
      el.className = `dups-group ${group.confidence === 'exact' ? 'is-exact' : ''} ${group.confidence === 'low' ? 'is-low' : ''}`;

      const active = group.photos.filter((p) => !ignored.has(p.id));
      const head = document.createElement('div');
      head.className = 'dups-head';
      const conf = group.confidence === 'exact'
        ? '<span class="tag ok">内容完全相同</span>'
        : group.confidence === 'high'
          ? '<span class="tag ok">高度相似</span>'
          : '<span class="tag warn">可能重复 · 请自己确认</span>';
      head.innerHTML = `
        <div>
          <div class="dups-title">
            ${conf}
            结构差异 ${group.distance}${group.colorDistance != null ? `　颜色差异 ${Number(group.colorDistance).toFixed(1)}` : ''}
            　共 ${group.count} 张
          </div>
          <div class="dups-meta">
            可省 ${escapeHtml(humanBytes(group.wastedBytes))}　
            ${active.length < group.count ? `已忽略 ${group.count - active.length} 张　` : ''}
            建议保留：${escapeHtml(group.keeper.path)}
          </div>
        </div>`;
      el.append(head);

      const items = document.createElement('div');
      items.className = 'dups-items';
      for (const p of sortGroupByKeeper(group)) {
        const isKeeper = p.id === group.keeper.id;
        const item = document.createElement('div');
        item.className = `dup-item${isKeeper ? ' is-keeper' : ''}${ignored.has(p.id) ? ' is-ignored' : ''}`;
        item.dataset.id = p.id;
        item.innerHTML = `
          ${isKeeper ? '<span class="keeper-tag">建议保留</span>' : ''}
          ${ignored.has(p.id) ? '<span class="ignored-tag">已忽略</span>' : ''}
          <img src="${imageSrc(p, 'thumb')}" alt="" loading="lazy" data-act="open" />
          <div class="dup-info">
            <div class="dup-path" title="${escapeHtml(pathById.get(p.id) || p.path || '')}">${escapeHtml(pathById.get(p.id) || p.path || '')}</div>
            <div class="dup-sub">${escapeHtml(formatDateShort(p.d))}　${escapeHtml(humanBytes(p.bytes || 0))}${
              p.pixel ? `　${p.pixel.width}×${p.pixel.height}` : ''}</div>
            <div class="dup-sub">${escapeHtml(distanceLabel(group, p))}${
              p.r ? `　${'★'.repeat(p.r)}` : ''}</div>
            <div class="dup-actions">
              ${isKeeper ? '' : '<button class="btn" data-act="keep" type="button">保留这张</button>'}
              ${ignored.has(p.id)
                ? '<button class="btn" data-act="unignore" type="button">取消忽略</button>'
                : '<button class="btn" data-act="ignore" type="button">忽略</button>'}
            </div>
          </div>`;
        items.append(item);
      }
      el.append(items);
      host.append(el);
    }
  }

  return {
    /** @param {Array} list 当前筛选后的精简索引条目 */
    render(list) {
      const source = (list && list.length ? list : allPhotos);
      photos = source.map(normalize).filter((p) => p.phash);
      if (!photos.length) {
        // 没有指纹数据（旧版导入的数据）时给出提示
        const host = $('#dups-list');
        if (host) {
          host.innerHTML = '<p class="empty">这些照片还没有指纹数据，无法比对。<br>'
            + '重新导入一次（网页导入或 <code>npm run import</code>）即可生成指纹。</p>';
        }
        const empty = $('#dups-empty');
        if (empty) empty.hidden = true;
        const sum = $('#dups-summary');
        if (sum) sum.innerHTML = '';
        groups = [];
        return;
      }
      renderList();
      ensurePaths();
    },
    setSource(list) {
      allPhotos = list || [];
    },
    count() {
      return groups.length;
    },
  };
}
