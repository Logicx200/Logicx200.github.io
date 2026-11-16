/**
 * 时间轴视图：年 → 月 → 缩略图
 */

import { imageSrc, formatDateShort } from './data.js';
import { escapeHtml, monthKey } from '../../src/util.js';

export function renderTimeline(host, photos, { onOpen, onMonthClick }) {
  host.replaceChildren();
  if (!photos.length) return;

  const byYear = new Map();
  for (const p of photos) {
    const y = p.d && /^\d{4}/.test(p.d) ? p.d.slice(0, 4) : '未知';
    if (!byYear.has(y)) byYear.set(y, new Map());
    const mk = monthKey(p.d);
    const months = byYear.get(y);
    if (!months.has(mk)) months.set(mk, []);
    months.get(mk).push(p);
  }

  const years = [...byYear.entries()].sort((a, b) => String(b[0]).localeCompare(String(a[0])));
  const maxYearCount = Math.max(...years.map(([, m]) => [...m.values()].reduce((s, x) => s + x.length, 0)));

  for (const [year, months] of years) {
    const total = [...months.values()].reduce((s, x) => s + x.length, 0);
    const details = document.createElement('details');
    details.className = 'tl-year';
    details.open = years.length <= 3 || year === years[0][0];

    const summary = document.createElement('summary');
    summary.innerHTML = `<span>${year === '未知' ? '日期未知' : year + ' 年'}</span>
      <span class="tl-count">${total} 张 · ${months.size} 个月 · ${Math.round(total / maxYearCount * 100)}%</span>`;
    details.append(summary);

    const body = document.createElement('div');
    body.className = 'tl-body';

    for (const [mk, list] of [...months.entries()].sort((a, b) => String(b[0]).localeCompare(String(a[0])))) {
      const row = document.createElement('div');
      row.className = 'tl-month';
      const head = document.createElement('button');
      head.type = 'button';
      head.className = 'tl-month-head';
      const label = mk === 'unknown' ? '月份未知' : `${Number(mk.slice(5))} 月`;
      const rel = Math.round((list.length / total) * 100);
      head.innerHTML = `<span>${label}</span><span class="bar"><i style="width:${rel}%"></i></span><span class="muted">${list.length} 张</span>`;
      head.addEventListener('click', () => onMonthClick?.(mk, list));
      row.append(head);

      const thumbs = document.createElement('div');
      thumbs.className = 'tl-thumbs';
      for (const p of list.slice(0, 30)) {
        const img = document.createElement('img');
        img.loading = 'lazy';
        img.decoding = 'async';
        img.src = imageSrc(p, 'thumb');
        img.alt = p.x || p.l || p.d || '';
        img.title = [p.l, formatDateShort(p.d)].filter(Boolean).join(' · ');
        img.style.background = p.cl || 'var(--ph)';
        img.addEventListener('click', () => onOpen(p.i, list));
        thumbs.append(img);
      }
      if (list.length > 30) {
        const more = document.createElement('button');
        more.type = 'button';
        more.className = 'chip';
        more.textContent = `还有 ${list.length - 30} 张 →`;
        more.addEventListener('click', () => onMonthClick?.(mk, list));
        thumbs.append(more);
      }
      row.append(thumbs);
      body.append(row);
    }

    details.append(body);
    host.append(details);
  }
}
