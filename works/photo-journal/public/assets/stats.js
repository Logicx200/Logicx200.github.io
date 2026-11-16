/**
 * 统计视图：KPI、逐月柱状图、相机 / 镜头 / 光圈 / 焦段 / 快门 分布
 */

import { escapeHtml } from '../../src/util.js';
import { formatDateShort } from './data.js';

function bars(entries, { limit = 12, unit = '张', onPick = null } = {}) {
  const max = Math.max(1, ...entries.map((e) => e[1]));
  const wrap = document.createElement('div');
  wrap.className = 'bars';
  for (const [name, n] of entries.slice(0, limit)) {
    const row = document.createElement('div');
    row.className = 'bar-row';
    row.innerHTML = `<span title="${escapeHtml(name)}">${escapeHtml(name)}</span>
      <span class="bar"><i style="width:${Math.round(n / max * 100)}%"></i></span>
      <span class="num">${n}${unit === '张' ? '' : ' ' + unit}</span>`;
    if (onPick) {
      row.style.cursor = 'pointer';
      row.addEventListener('click', () => onPick(name));
    }
    wrap.append(row);
  }
  if (!entries.length) wrap.innerHTML = '<p class="muted small">暂无数据</p>';
  return wrap;
}

function card(title, content, extraClass = '') {
  const d = document.createElement('div');
  d.className = `stat-card ${extraClass}`.trim();
  const h = document.createElement('h3');
  h.textContent = title;
  d.append(h, content);
  return d;
}

function kpi(value, label) {
  const d = document.createElement('div');
  d.className = 'kpi';
  d.innerHTML = `<b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span>`;
  return d;
}

const tally = (photos, fn) => {
  const m = new Map();
  for (const p of photos) {
    const k = fn(p);
    if (k == null || k === '') continue;
    m.set(k, (m.get(k) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
};

/** 从 "f/2.8" / "1/250" / "35mm (52mm eq.)" 里抽出排序键 */
const apertureOf = (p) => {
  const m = /f\/([\d.]+)/.exec(p.a || '');
  return m ? Number(m[1]) : null;
};
const focalOf = (p) => {
  const m = /^(\d+)/.exec(p.f || '');
  return m ? Number(m[1]) : null;
};
const isoOf = (p) => p.o || null;

export function renderStats(host, photos, { stats, onPickLocation, onPickCamera } = {}) {
  host.replaceChildren();
  if (!photos.length) {
    host.innerHTML = '<p class="empty">没有可统计的照片。</p>';
    return;
  }

  /* KPI */
  const dates = photos.map((p) => p.d).filter((d) => /^\d{4}/.test(d || '')).sort();
  const span = dates.length ? Math.max(1, Math.round((new Date(dates[dates.length - 1]) - new Date(dates[0])) / 86400000)) : 0;
  const kpis = document.createElement('div');
  kpis.className = 'kpis';
  kpis.append(
    kpi(String(photos.length), '当前筛选下照片数'),
    kpi(String(new Set(photos.map((p) => p.l).filter(Boolean)).size), '地点数'),
    kpi(String(photos.filter((p) => p.g).length), '带 GPS 坐标'),
    kpi(span ? `${span} 天` : '—', '时间跨度'),
    kpi(String(stats?.photos ?? photos.length), '总照片数'),
  );
  host.append(card('概览', kpis));

  /* 逐月柱状图 */
  const monthMap = new Map();
  for (const p of photos) {
    if (!p.d || !/^\d{4}-\d{2}/.test(p.d)) continue;
    const k = p.d.slice(0, 7);
    monthMap.set(k, (monthMap.get(k) || 0) + 1);
  }
  const months = [...monthMap.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  const chart = document.createElement('div');
  chart.className = 'month-chart';
  if (months.length) {
    const max = Math.max(...months.map((m) => m[1]));
    chart.style.cssText = 'display:flex;align-items:flex-end;gap:3px;height:150px;overflow-x:auto;padding-top:6px';
    for (const [k, n] of months) {
      const bar = document.createElement('div');
      const h = Math.max(3, Math.round((n / max) * 118));
      bar.style.cssText = `flex:0 0 auto;width:12px;height:${h}px;background:var(--accent);opacity:.65;border-radius:3px 3px 0 0`;
      bar.title = `${k}：${n} 张`;
      chart.append(bar);
    }
  } else {
    chart.innerHTML = '<p class="muted small">暂无按月数据</p>';
  }
  host.append(card(`逐月拍摄量（${months.length} 个月）`, chart));

  /* 相机 */
  const cams = tally(photos, (p) => p.c);
  host.append(card('相机使用分布', bars(cams, { limit: 10, onPick: onPickCamera })));

  /* 镜头 */
  const lenses = tally(photos, (p) => p.e);
  host.append(card('镜头使用分布', bars(lenses, { limit: 10 })));

  /* 光圈 */
  const aps = tally(photos, (p) => {
    const v = apertureOf(p);
    return v == null ? null : `f/${v}`;
  }).sort((a, b) => Number(a[0].slice(2)) - Number(b[0].slice(2)));
  host.append(card('光圈分布', bars(aps, { limit: 14 })));

  /* 焦段 */
  const focals = tally(photos, (p) => {
    const v = focalOf(p);
    return v == null ? null : `${v}mm`;
  }).sort((a, b) => Number(a[0].replace('mm', '')) - Number(b[0].replace('mm', '')));
  host.append(card('焦距分布', bars(focals, { limit: 16 })));

  /* ISO */
  const isos = tally(photos, (p) => {
    const v = isoOf(p);
    return v == null ? null : `ISO ${v}`;
  }).sort((a, b) => Number(a[0].slice(4)) - Number(b[0].slice(4)));
  host.append(card('ISO 分布', bars(isos, { limit: 12 })));

  /* 地点 */
  const locs = tally(photos, (p) => p.l);
  host.append(card('拍摄地点排行', bars(locs, { limit: 14, onPick: onPickLocation })));

  /* 日期来源（数据质量） */
  const srcLabel = {
    exif: 'EXIF 拍摄时间', folder: '文件夹名', 'folder-partial': '文件夹名（仅月日）',
    filename: '文件名', mtime: '文件修改时间（兜底）', unknown: '未识别',
  };
  const srcs = tally(photos, (p) => srcLabel[p.ds] || p.ds || '未识别');
  host.append(card('日期来源（自动识别质量）', bars(srcs, { limit: 8 })));

  /* 时间跨度 */
  if (dates.length) {
    const info = document.createElement('div');
    info.className = 'muted small';
    info.innerHTML = `最早：${escapeHtml(formatDateShort(dates[0]))}　最晚：${escapeHtml(formatDateShort(dates[dates.length - 1]))}`;
    host.append(card('时间范围', info));
  }
}
