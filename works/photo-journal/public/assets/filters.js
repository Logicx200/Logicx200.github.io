/**
 * 侧边筛选栏渲染
 *
 * 每次筛选结果变化后重新计算各维度的可选值与数量，
 * 这样"选城市后剩下的相机型号数量"始终是准确的。
 */

import { compose, escapeHtml as escape } from '../../src/util.js';

const MAX_CHIPS = 26;

export function createFilterPanel({ host, onChange }) {
  let state = compose({});
  let photos = [];

  function chip(label, count, isOn, onClick, extraClass = '') {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `chip ${isOn ? 'is-on' : ''} ${extraClass}`.trim();
    b.innerHTML = `${escape(label)}${count != null ? `<span class="n">${count}</span>` : ''}`;
    b.addEventListener('click', onClick);
    return b;
  }

  function row(label, count, max, isOn, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = `facet-row ${isOn ? 'is-on' : ''}`;
    b.innerHTML = `<span title="${escape(label)}">${escape(label)}</span><span class="bar"><i style="width:${
      Math.max(2, Math.round((count / max) * 100))}%"></i></span><span class="num">${count}</span>`;
    b.addEventListener('click', onClick);
    return b;
  }

  function section(title, open, content) {
    const d = document.createElement('details');
    d.className = 'facet';
    d.open = open;
    const s = document.createElement('summary');
    s.textContent = title;
    d.append(s, content);
    return d;
  }

  function toggleIn(dim, value) {
    const cur = state[dim];
    const next = Array.isArray(cur) ? [...cur] : [];
    const i = next.indexOf(value);
    if (i >= 0) next.splice(i, 1); else next.push(value);
    state = { ...state, [dim]: next };
    onChange(state);
  }

  function render() {
    const host2 = host;
    host2.replaceChildren();
    if (!photos.length) return;

    // ---- 年份 ----
    const yearBox = document.createElement('div');
    yearBox.className = 'facet-list';
    const yearTotal = new Map();
    for (const p of photos) {
      const y = p.d && /^\d{4}/.test(p.d) ? p.d.slice(0, 4) : '未知';
      yearTotal.set(y, (yearTotal.get(y) || 0) + 1);
    }
    for (const [y, n] of [...yearTotal.entries()].sort((a, b) => String(b[0]).localeCompare(String(a[0])))) {
      yearBox.append(chip(y === '未知' ? '年份未知' : `${y} 年`, n, state.years.includes(y), () => toggleIn('years', y)));
    }
    host2.append(section('年份', true, yearBox));

    // ---- 月份（仅显示当前年份范围内的） ----
    const monthCount = new Map();
    for (const p of photos) {
      if (!p.d) continue;
      const key = /^\d{4}-\d{2}/.test(p.d) ? p.d.slice(0, 7) : '未知';
      if (state.years.length && !state.years.includes(key === '未知' ? '未知' : key.slice(0, 4))) continue;
      monthCount.set(key, (monthCount.get(key) || 0) + 1);
    }
    if (monthCount.size) {
      const box = document.createElement('div');
      box.className = 'facet-list';
      for (const [k, n] of [...monthCount.entries()].sort((a, b) => String(b[0]).localeCompare(String(a[0])))) {
        box.append(chip(k === '未知' ? '月份未知' : `${Number(k.slice(5))} 月`, n, state.months.includes(k), () => toggleIn('months', k)));
      }
      host2.append(section('月份', false, box));
    }

    // ---- 地点 ----
    const loc = tally(photos, (p) => p.l);
    if (loc.length) {
      const box = document.createElement('div');
      box.className = 'facet-list';
      for (const [name, n] of loc.slice(0, MAX_CHIPS)) {
        box.append(chip(`📍 ${name}`, n, state.locations.includes(name), () => toggleIn('locations', name)));
      }
      const noLoc = photos.filter((p) => !p.l).length;
      if (noLoc) box.append(chip('未识别地点', noLoc, state.locations.includes('__none__'), () => toggleIn('locations', '__none__')));
      host2.append(section(`地点 (${loc.length})`, state.locations.length > 0, box));
    }

    // ---- 相机 ----
    const cams = tally(photos, (p) => p.c);
    if (cams.length > 1 || (cams.length === 1 && cams[0][0])) {
      const box = document.createElement('div');
      box.className = 'facet-list is-scroll';
      const max = cams[0]?.[1] || 1;
      for (const [name, n] of cams) {
        box.append(row(name, n, max, state.cameras.includes(name), () => toggleIn('cameras', name)));
      }
      host2.append(section(`相机 (${cams.length})`, false, box));
    }

    // ---- 镜头 ----
    const lens = tally(photos, (p) => p.e);
    if (lens.length) {
      const box = document.createElement('div');
      box.className = 'facet-list is-scroll';
      const max = lens[0]?.[1] || 1;
      for (const [name, n] of lens.slice(0, 40)) {
        box.append(row(name, n, max, state.lenses.includes(name), () => toggleIn('lenses', name)));
      }
      host2.append(section(`镜头 (${lens.length})`, false, box));
    }

    // ---- 标签 ----
    const tagMap = new Map();
    for (const p of photos) for (const t of p.k || []) tagMap.set(t, (tagMap.get(t) || 0) + 1);
    const tags = [...tagMap.entries()].sort((a, b) => b[1] - a[1]);
    if (tags.length) {
      const box = document.createElement('div');
      box.className = 'facet-list';
      for (const [name, n] of tags) {
        box.append(chip(`#${name}`, n, state.tags.includes(name), () => toggleIn('tags', name)));
      }
      host2.append(section(`标签 (${tags.length})`, false, box));
    }

    // ---- 星级 ----
    const ratingMap = new Map();
    for (const p of photos) {
      const r = p.r ?? 0;
      ratingMap.set(r, (ratingMap.get(r) || 0) + 1);
    }
    if ([...ratingMap.keys()].some((r) => r > 0)) {
      const box = document.createElement('div');
      box.className = 'facet-list';
      for (const [r, n] of [...ratingMap.entries()].sort((a, b) => b[0] - a[0])) {
        box.append(chip(r === 0 ? '未评级' : '★'.repeat(r), n, state.ratings.includes(r), () => toggleIn('ratings', r)));
      }
      host2.append(section('星级（来自 Lightroom 评级）', false, box));
    }

    // ---- 日期来源 / GPS ----
    const srcMap = new Map();
    for (const p of photos) srcMap.set(p.ds || 'unknown', (srcMap.get(p.ds || 'unknown') || 0) + 1);
    const extra = document.createElement('div');
    extra.className = 'facet-list';
    const srcLabel = { exif: 'EXIF', folder: '文件夹名', 'folder-partial': '文件夹名(仅月日)', filename: '文件名', mtime: '文件时间', unknown: '未识别' };
    for (const [k, n] of srcMap) {
      extra.append(chip(`日期来源：${srcLabel[k] || k}`, n, state.dateSources.includes(k), () => toggleIn('dateSources', k)));
    }
    const gps = photos.filter((p) => p.g).length;
    if (gps) extra.append(chip('📍 有 GPS 坐标', gps, state.hasGps === true, () => {
      state = { ...state, hasGps: state.hasGps === true ? null : true };
      onChange(state);
    }));
    host2.append(section('来源 / 坐标', false, extra));
  }

  return {
    update(list, st) {
      photos = list;
      state = st;
      render();
    },
    getState() { return state; },
    setState(st) { state = st; render(); },
  };
}

function tally(photos, fn) {
  const m = new Map();
  for (const p of photos) {
    const k = fn(p);
    if (!k) continue;
    m.set(k, (m.get(k) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}
