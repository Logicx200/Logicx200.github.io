/**
 * 通用小工具（纯函数，Node 与浏览器通用）
 */

export function compose(base, extra) {
  return { ...base, ...extra };
}

export function clamp(v, min, max) {
  return Math.min(max, Math.max(min, v));
}

/** 日期 → 'YYYY-MM'；无法判断时返回 'unknown' */
export function monthKey(date) {
  return /^\d{4}-\d{2}/.test(date || '') ? date.slice(0, 7) : 'unknown';
}

/** 日期 → 'YYYY'；无法判断时返回 'unknown' */
export function yearKey(date) {
  return /^\d{4}/.test(date || '') ? date.slice(0, 4) : 'unknown';
}

export function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

export function debounce(fn, ms = 180) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

export function download(filename, text, mime = 'application/json') {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/* ------------------------------------------------------------------ */
/* 忽略列表：把"我确认不是重复"的照片记下来，换个浏览器/刷新也还在          */
/* ------------------------------------------------------------------ */

const IGNORE_KEY = 'pj-dup-ignored';

function readIgnored() {
  try {
    const raw = localStorage.getItem(IGNORE_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

export function ignoredIds() {
  return new Set(readIgnored());
}

export function isIgnored(id) {
  return readIgnored().includes(id);
}

export function setIgnored(id, on = true) {
  const cur = readIgnored();
  const set = new Set(cur);
  if (on) set.add(id); else set.delete(id);
  const next = [...set];
  try { localStorage.setItem(IGNORE_KEY, JSON.stringify(next)); } catch { /* 忽略 */ }
  return next;
}

export function clearIgnored() {
  try { localStorage.removeItem(IGNORE_KEY); } catch { /* 忽略 */ }
}

export function ignoredCount() {
  return readIgnored().length;
}
