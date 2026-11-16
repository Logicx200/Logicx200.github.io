/**
 * 筛选逻辑（纯函数，便于单元测试）
 *
 * 筛选状态示例：
 * {
 *   years: ['2024'], months: ['2024-10'], locations: ['杭州 西湖'],
 *   cameras: ['SONY ILCE-7M4'], lenses: ['FE 24-70mm F2.8 GM II'],
 *   tags: ['夜景'], ratings: [5], hasGps: true, dateSources: ['exif'],
 *   text: '西湖 日落'
 * }
 *
 * 同一维度内是"或"，不同维度之间是"与"。
 */

import { compose } from './util.js';

/** 把任意部分筛选条件补齐成完整状态（避免某个维度 undefined 导致遍历报错） */
export function createFilterState(init = {}) {
  return compose({
    years: [], months: [], locations: [], cameras: [], lenses: [],
    tags: [], ratings: [], dateSources: [], hasGps: null, text: null,
  }, init);
}

/** 在已有状态上合并新条件（等价于 compose，语义更清晰） */
export function withFilter(base, extra) {
  return createFilterState({ ...(base || {}), ...(extra || {}) });
}

export function monthKeyOf(date) {
  if (!date) return null;
  if (/^\d{4}-\d{2}/.test(date)) return date.slice(0, 7);
  return 'unknown';
}

export function yearKeyOf(date) {
  if (!date) return null;
  if (/^\d{4}/.test(date)) return date.slice(0, 4);
  return 'unknown';
}

function textBlob(p) {
  if (p.__blob) return p.__blob;
  const parts = [p.x, p.l, p.c, p.e, p.s, p.a, p.o, p.f, p.d,
    ...(p.k || [])];
  const blob = parts.filter(Boolean).join(' ').toLowerCase();
  try {
    Object.defineProperty(p, '__blob', { value: blob, enumerable: false });
  } catch { /* 冻结对象时忽略 */ }
  return blob;
}

export function matches(p, f) {
  if (!f) return true;
  if (f.years?.length && !f.years.includes(yearKeyOf(p.d))) return false;
  if (f.months?.length && !f.months.includes(monthKeyOf(p.d))) return false;
  if (f.locations?.length) {
    const loc = p.l || '';
    if (!f.locations.some((x) => loc === x || loc.includes(x))) return false;
  }
  if (f.cameras?.length && !f.cameras.includes(p.c)) return false;
  if (f.lenses?.length && !f.lenses.includes(p.e)) return false;
  if (f.tags?.length) {
    const tags = p.k || [];
    if (!f.tags.some((t) => tags.includes(t))) return false;
  }
  if (f.ratings?.length && !f.ratings.includes(p.r ?? 0)) return false;
  if (f.dateSources?.length && !f.dateSources.includes(p.ds || 'unknown')) return false;
  if (f.hasGps === true && !p.g) return false;
  if (f.hasGps === false && p.g) return false;
  if (f.text) {
    const words = String(f.text).toLowerCase().split(/\s+/).filter(Boolean);
    const blob = textBlob(p);
    if (!words.every((w) => blob.includes(w))) return false;
  }
  return true;
}

export function apply(photos, f) {
  return photos.filter((p) => matches(p, f));
}

export function activeCount(f) {
  if (!f) return 0;
  let n = 0;
  for (const k of ['years', 'months', 'locations', 'cameras', 'lenses', 'tags', 'ratings', 'dateSources']) {
    n += (f[k]?.length || 0);
  }
  if (f.hasGps === true) n++;
  if (f.hasGps === false) n++;
  if (f.text) n++;
  return n;
}

export function toggle(list, value) {
  const i = list.indexOf(value);
  if (i >= 0) return list.filter((x) => x !== value);
  return [...list, value];
}

/** 描述当前筛选，用于"已选条件"标签 */
export function describe(f) {
  const out = [];
  for (const y of f.years) out.push({ dim: 'years', value: y, label: `${y} 年` });
  for (const m of f.months) {
    out.push({ dim: 'months', value: m, label: m === 'unknown' ? '年份未知' : `${m.slice(0, 4)} 年 ${Number(m.slice(5))} 月` });
  }
  for (const v of f.locations) out.push({ dim: 'locations', value: v, label: `📍 ${v}` });
  for (const v of f.cameras) out.push({ dim: 'cameras', value: v, label: `📷 ${v}` });
  for (const v of f.lenses) out.push({ dim: 'lenses', value: v, label: `🔭 ${v}` });
  for (const v of f.tags) out.push({ dim: 'tags', value: v, label: `#${v}` });
  for (const v of f.ratings) out.push({ dim: 'ratings', value: v, label: `${'★'.repeat(v)}${v === 0 ? '未评级' : ''}` });
  for (const v of f.dateSources) out.push({ dim: 'dateSources', value: v, label: `日期来源：${v}` });
  if (f.hasGps === true) out.push({ dim: 'hasGps', value: true, label: '有 GPS' });
  if (f.hasGps === false) out.push({ dim: 'hasGps', value: false, label: '无 GPS' });
  if (f.text) out.push({ dim: 'text', value: f.text, label: `🔍 ${f.text}` });
  return out;
}

/** 从当前结果集里统计各维度分布（用于显示数量徽标） */
export function facets(photos) {
  const count = (keyFn) => {
    const m = new Map();
    for (const p of photos) {
      const k = keyFn(p);
      if (k == null || k === '') continue;
      m.set(k, (m.get(k) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  };
  return {
    years: count((p) => yearKeyOf(p.d)),
    months: count((p) => monthKeyOf(p.d)).sort((a, b) => b[0].localeCompare(a[0])),
    locations: count((p) => p.l),
    cameras: count((p) => p.c),
    lenses: count((p) => p.e),
    tags: count((p) => (p.k || []).join('|')).flatMap(([k, n]) => k.split('|').map((t) => [t, n]))
      .reduce((acc, [t, n]) => {
        const hit = acc.find((x) => x[0] === t);
        if (hit) hit[1] += n; else acc.push([t, n]);
        return acc;
      }, [])
      .sort((a, b) => b[1] - a[1]),
    ratings: count((p) => p.r ?? 0).sort((a, b) => b[0] - a[0]),
    dateSources: count((p) => p.ds),
  };
}
