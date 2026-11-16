/**
 * 「导入」页的交互逻辑：拖拽 → 处理 → 结果预览/人工修正 → 写盘或导出 zip
 */

import {
  collectFromDataTransfer, collectFromFileList, processEntries,
  buildIndex, writeToDirectory, exportZip, loadExistingMedia, collectOverrides,
  loadExistingFullPhotos, mergeRecords,
} from './import.js';
import { formatDateShort, dateSourceLabel, exposureSummary, imageSrc } from './data.js';
import { escapeHtml } from '../../src/util.js';
import { humanSize } from '../../src/media-browser.js';
import { inspectSiteRoot, findSiteRoots, describeSitePick, SITE_MARKER_FILE, SITE_MARKER_TEXT } from '../../src/site-root.js';

const $ = (s) => document.querySelector(s);

/* ---------------- 诊断日志 ---------------- */

const LOG_KEY = 'pj-import-log';
const RESULT_KEY = 'pj-last-write-result';
const logLines = [];
let lastWriteTime = 0;

/** 记一行日志（同时写到控制台、页面上的日志框，并留一份在 localStorage 里） */
function log(msg) {
  const line = `${new Date().toLocaleTimeString('zh-CN')}  ${msg}`;
  logLines.push(line);
  if (logLines.length > 200) logLines.shift();
  console.log('[导入]', msg);
  const el = $('#imp-log');
  if (el) { el.hidden = false; el.textContent = logLines.join('\n'); el.scrollTop = el.scrollHeight; }
  try { localStorage.setItem(LOG_KEY, logLines.slice(-120).join('\n')); } catch { /* 忽略 */ }
}

// 页面级的报错也收集进来，这样"按钮点了没反应"能查到原因
if (typeof window !== 'undefined') {
  window.addEventListener('error', (e) => log(`页面错误：${e.message} @ ${e.filename || ''}:${e.lineno || ''}`));
  window.addEventListener('unhandledrejection', (e) => {
    const r = e.reason;
    log(`未处理的 Promise 错误：${(r && (r.stack || r.message)) || r}`);
  });
}


/* ---------------- IndexedDB：记住上次的 public 目录，下次点一下就能写 ---------------- */

const DB_NAME = 'photo-journal';
const STORE = 'handles';

function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function saveHandle(name, handle) {
  try {
    const db = await idb();
    await new Promise((res, rej) => {
      const tx = db.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put(handle, name);
      tx.oncomplete = res;
      tx.onerror = () => rej(tx.error);
    });
    db.close();
  } catch { /* 无痕模式等场景忽略 */ }
}

async function loadHandle(name) {
  try {
    const db = await idb();
    const handle = await new Promise((res, rej) => {
      const tx = db.transaction(STORE, 'readonly');
      const r = tx.objectStore(STORE).get(name);
      r.onsuccess = () => res(r.result || null);
      r.onerror = () => rej(r.error);
    });
    db.close();
    return handle || null;
  } catch {
    return null;
  }
}

/* ---------------- 状态 ---------------- */

const state = {
  photos: [],        // 处理结果（可人工修正）
  media: new Map(),  // 路径 → Blob
  originals: new Map(),
  errors: [],
  skipped: [],
  keepOriginals: false,
  dirHandle: null,
  busy: false,
  visible: 200,
  filter: { text: '', todoOnly: false, sort: 'path' },
  existing: [],      // 站点上已有的完整记录
  lastMerge: null,
};

/* ---------------- 主入口 ---------------- */

export function createImportView() {
  if (!$('#drop-zone')) {
    console.warn('[导入] 页面上找不到 #drop-zone，导入界面未初始化');
    return { activate() {}, hasPhotos: () => false };
  }
  log(`导入界面已初始化｜浏览器支持直接写目录：${typeof window.showDirectoryPicker === 'function' ? '是' : '否'}`);

  const overlay = $('#drop-overlay');
  let dragDepth = 0;

  // 整页拖拽：显示遮罩，松开即导入
  window.addEventListener('dragenter', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth++;
    overlay.hidden = false;
  });
  window.addEventListener('dragover', (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });
  window.addEventListener('dragleave', (e) => {
    if (!hasFiles(e)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) overlay.hidden = true;
  });
  window.addEventListener('drop', async (e) => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    overlay.hidden = true;
    const entries = await collectFromDataTransfer(e.dataTransfer);
    await runImport(entries, '拖入的文件夹');
  });

  // 框内的拖拽
  const zone = $('#drop-zone');
  for (const evt of ['dragenter', 'dragover']) {
    zone.addEventListener(evt, (e) => { e.preventDefault(); zone.classList.add('is-over'); });
  }
  for (const evt of ['dragleave', 'drop']) {
    zone.addEventListener(evt, () => zone.classList.remove('is-over'));
  }

  // 选择文件夹（优先 File System Access API，其次 input[webkitdirectory]）
  $('#pick-dir').addEventListener('click', async () => {
    if (window.showDirectoryPicker) {
      try {
        const dir = await window.showDirectoryPicker({ mode: 'read' });
        await saveHandle('source', dir);
        const entries = [];
        await walkDirHandle(dir, '', entries);
        await runImport(entries, dir.name);
        return;
      } catch (err) {
        if (err && err.name === 'AbortError') return;
        // 不支持时退回 input
      }
    }
    $('#file-input-dir').click();
  });

  $('#pick-files').addEventListener('click', () => $('#file-input-files').click());

  $('#file-input-dir').addEventListener('change', async (e) => {
    const files = collectFromFileList(e.target.files);
    await runImport(files, '选择的文件夹');
    e.target.value = '';
  });
  $('#file-input-files').addEventListener('change', async (e) => {
    const files = collectFromFileList(e.target.files);
    await runImport(files, '选择的文件');
    e.target.value = '';
  });

  for (const radio of document.querySelectorAll('input[name="imp-mode"]')) {
    radio.addEventListener('change', () => {
      state.keepOriginals = radio.value === 'full';
      updateWriteHint();
    });
  }

  $('#imp-search').addEventListener('input', (e) => {
    state.filter.text = e.target.value.trim().toLowerCase();
    state.visible = 200;
    renderTable();
  });
  $('#imp-only-todo').addEventListener('change', (e) => {
    state.filter.todoOnly = e.target.checked;
    state.visible = 200;
    renderTable();
  });
  $('#imp-sort').addEventListener('change', (e) => {
    state.filter.sort = e.target.value;
    renderTable();
  });

  $('#imp-save').addEventListener('click', () => saveToDirectory());
  $('#imp-zip').addEventListener('click', () => doExportZip());
  $('#imp-reset').addEventListener('click', () => resetAll());
  $('#imp-diagnose').addEventListener('click', () => diagnose());
  $('#global-banner-close')?.addEventListener('click', () => hideGlobalBanner());

  // 表格内的操作（事件委托）
  $('#imp-tbody').addEventListener('click', onTableClick);
  $('#imp-tbody').addEventListener('change', onTableChange);

  // 恢复上次保存的目标目录句柄，并摸清站点已有多少照片
  (async () => {
    restoreWriteResult();
    const h = await loadHandle('target');
    if (h) {
      state.dirHandle = h;
      updateWriteHint();
    }
    await loadSiteState();
    updateWriteHint();

    // 浏览器不支持直接写目录时，明确提示，避免"点了没反应"
    if (typeof window.showDirectoryPicker !== 'function') {
      const warn = $('#imp-warn');
      if (warn) {
        warn.textContent = '当前浏览器不支持「直接写入文件夹」（Firefox/Safari/部分套壳浏览器）：'
          + '点「写入站点目录」会自动改成下载 zip，请解压后覆盖仓库里的 public/ 目录。'
          + '想要一键写入，请用 Chrome 或 Edge 打开本页。';
      }
      log('提示：当前浏览器不支持 showDirectoryPicker，写入会退化为下载 zip');
    }
  })();

  updateWriteHint();

  return {
    activate() {
      if (state.photos.length) renderSummary();
    },
    hasPhotos: () => state.photos.length > 0,
    // 便于自检脚本验证"失败提示真的看得见"
    showWriteResult,
    diagnose,
  };
}

function hasFiles(e) {
  const dt = e.dataTransfer;
  if (!dt) return false;
  if (dt.types && [...dt.types].includes('Files')) return true;
  return false;
}

/* ---------------- 从目录句柄递归收集 ---------------- */

const SKIP_DIRS = new Set(['node_modules', '.git', '.cache', 'dist', '$RECYCLE.BIN', 'System Volume Information']);

async function walkDirHandle(dirHandle, prefix, out) {
  for await (const [name, handle] of dirHandle.entries()) {
    if (name.startsWith('.')) continue;
    const path = prefix ? `${prefix}/${name}` : name;
    if (handle.kind === 'directory') {
      if (SKIP_DIRS.has(name)) continue;
      await walkDirHandle(handle, path, out);
    } else {
      try {
        const file = await handle.getFile();
        out.push({ file, path });
      } catch { /* 忽略读不了的文件 */ }
    }
  }
}

/* ---------------- 导入流程 ---------------- */

async function runImport(entries, rootName) {
  if (state.busy) return;
  if (!entries.length) {
    toast('没有发现可导入的文件');
    return;
  }
  state.busy = true;
  setViewIfNeeded('import');
  $('#imp-result').hidden = true;
  $('#imp-progress').hidden = false;
  $('#imp-phase').textContent = '正在读取拍摄参数与生成缩略图…';
  $('#imp-current').textContent = '';
  $('#imp-stats').textContent = `${entries.length} 个文件排队中`;

  const existingMedia = await loadExistingMedia();
  const existingCount = await loadSiteState();
  let lastPaint = 0;
  let total = entries.length;          // 注意：必须在 processEntries 之前初始化
  const bar = $('#imp-bar');

  try {
    const { results, media, originals, errors, skipped, total: totalDone } = await processEntries({
      entries,
      rootName,
      keepOriginals: state.keepOriginals,
      existingMedia,
      onProgress: (p) => {
        if (p.phase !== 'process') return;
        const pct = total ? Math.round((p.done / total) * 100) : 0;
        bar.style.width = `${pct}%`;
        // 每 120ms 刷一次，避免拖慢处理
        const now = performance.now();
        if (now - lastPaint < 120 && p.done !== total) return;
        lastPaint = now;
        $('#imp-current').textContent = p.current ? `正在处理：${p.current}` : '';
        $('#imp-stats').textContent = `${p.done} / ${total}　已识别 ${p.results} 张`;
      },
    });

    state.photos = results;
    state.media = media;
    state.originals = originals;
    state.errors = errors;
    state.skipped = skipped;
    state.visible = 200;
    total = totalDone || total;

    bar.style.width = '100%';
    $('#imp-progress').hidden = true;
    $('#imp-result').hidden = false;
    renderSummary();
    renderTable();
    updateWriteHint();
    if (!results.length) toast('没识别到可用的照片，请确认拖入的是照片文件夹');
    else if (existingCount) toast(`本次识别 ${results.length} 张；站点已有 ${existingCount} 张，写入时会合并`);
  } catch (err) {
    console.error(err);
    toast('导入出错：' + err.message);
    $('#imp-progress').hidden = true;
  } finally {
    state.busy = false;
  }
}

function setViewIfNeeded(view) {
  const tab = document.querySelector(`.tab[data-view="${view}"]`);
  if (tab && !tab.classList.contains('is-active')) tab.click();
}

/* ---------------- 结果概览 ---------------- */

function renderSummary() {
  const photos = state.photos;
  const gps = photos.filter((p) => p.coords).length;
  const exifDate = photos.filter((p) => p.dateSource === 'exif').length;
  const folderDate = photos.filter((p) => p.dateSource === 'folder' || p.dateSource === 'folder-partial').length;
  const todo = photos.filter(needsReview).length;
  const mediaCount = state.media.size + state.originals.size;

  const kpi = (value, label, warn) => `<div class="kpi${warn ? ' warn' : ''}"><b>${value}</b><span>${label}</span></div>`;
  $('#imp-summary').innerHTML = [
    kpi(photos.length, '识别到的照片'),
    kpi(gps, '含 GPS 坐标'),
    kpi(exifDate, '日期来自 EXIF'),
    kpi(folderDate, '日期来自文件夹名'),
    kpi(todo, '需要确认', todo > 0),
    kpi(mediaCount, '生成的文件', false),
  ].join('');
}

function needsReview(p) {
  if (!p.location) return true;
  if (p.dateSource === 'mtime') return true;
  if (!p.date) return true;
  if (/^\d{2}-\d{2}$/.test(p.date)) return true;
  return false;
}

/* ---------------- 结果表格 ---------------- */

function filteredPhotos() {
  let list = state.photos.slice();
  const f = state.filter;
  if (f.todoOnly) list = list.filter(needsReview);
  if (f.text) {
    list = list.filter((p) => [p.path, p.location, p.caption,
      p.camera && [p.camera.make, p.camera.model].join(' '), p.lens,
      p.date, ...(p.tags || [])].filter(Boolean).join(' ').toLowerCase().includes(f.text));
  }
  if (f.sort === 'date') {
    list.sort((a, b) => (b.date || '').localeCompare(a.date || '') || (b.time || '').localeCompare(a.time || ''));
  } else {
    list.sort((a, b) => (a.path || '').localeCompare(b.path || '', 'zh-Hans-CN'));
  }
  return list;
}

function rowHtml(p) {
  const folder = p.path.includes('/') ? p.path.slice(0, p.path.lastIndexOf('/')) : '';
  const file = p.path.slice(p.path.lastIndexOf('/') + 1);
  const cam = p.camera ? [p.camera.make, p.camera.model].filter(Boolean).join(' ') : '';
  const ex = exposureSummary({
    a: p.exposure?.aperture, s: p.exposure?.shutter, o: p.exposure?.iso, f: p.exposure?.focal,
  });
  const srcTag = p.dateSource === 'exif'
    ? '<span class="tag ok">EXIF</span>'
    : p.dateSource === 'mtime'
      ? '<span class="tag warn">文件时间</span>'
      : p.dateSource === 'folder' || p.dateSource === 'folder-partial'
        ? '<span class="tag">文件夹名</span>'
        : '';
  const gpsTag = p.coords ? '<span class="tag ok">GPS</span>' : '';
  const thumb = p.thumb || p.preview;
  let thumbUrl = '';
  if (thumb && state.media.has(thumb)) {
    thumbUrl = URL.createObjectURL(state.media.get(thumb));
    objectUrls.push(thumbUrl);
  } else {
    thumbUrl = imageSrc(p, 'thumb');
  }

  return `<tr data-id="${p.id}">
    <td class="c-thumb">${thumbUrl ? `<img src="${thumbUrl}" alt="" loading="lazy" />` : '<span class="muted">—</span>'}</td>
    <td class="cell-path">
      <div class="folder">${escapeHtml(folder || '(根目录)')}</div>
      <div class="cell-sub">${escapeHtml(file)}　${humanSize(p.bytes)}</div>
    </td>
    <td>
      <div>${escapeHtml(formatDateShort(p.date))}${p.time ? ` <span class="cell-sub">${p.time}</span>` : ''}</div>
      <div>${srcTag}</div>
    </td>
    <td>
      <div>${escapeHtml(p.location || '未识别')}</div>
      <div>${gpsTag}${p.coords ? `<span class="cell-sub">${p.coords.lat.toFixed(3)}, ${p.coords.lng.toFixed(3)}</span>` : ''}</div>
    </td>
    <td>
      <div>${escapeHtml(cam || '—')}</div>
      <div class="cell-sub">${escapeHtml(ex || (p.lens || ''))}</div>
    </td>
    <td>
      <button class="btn" data-act="edit" type="button">修正</button>
    </td>
  </tr>`;
}

function renderTable() {
  const tbody = $('#imp-tbody');
  const list = filteredPhotos();
  const slice = list.slice(0, state.visible);
  revokeObjectUrls();
  tbody.innerHTML = slice.map(rowHtml).join('');
  if (!slice.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="muted" style="padding:26px;text-align:center">没有匹配的记录</td></tr>';
  }
  const more = list.length - slice.length;
  $('#imp-write-hint').dataset.more = String(more);
  updateWriteHint();
}

let objectUrls = [];
function revokeObjectUrls() {
  for (const u of objectUrls) URL.revokeObjectURL(u);
  objectUrls = [];
}

function onTableClick(e) {
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const tr = btn.closest('tr');
  const id = tr.dataset.id;
  const p = state.photos.find((x) => x.id === id);
  if (!p) return;
  if (btn.dataset.act === 'edit') startEdit(tr, p);
  if (btn.dataset.act === 'cancel') renderTable();
  if (btn.dataset.act === 'delete') {
    state.photos = state.photos.filter((x) => x.id !== id);
    if (p.thumb) state.media.delete(p.thumb);
    if (p.preview) state.media.delete(p.preview);
    renderSummary();
    renderTable();
    toast('已从本次导入中移除这张');
  }
}

function startEdit(tr, p) {
  tr.innerHTML = `<td colspan="6">
    <div class="edit-row">
      <label>日期 <input type="date" data-f="date" value="${/^\d{4}-\d{2}-\d{2}$/.test(p.date) ? p.date : ''}" /></label>
      <label>地点 <input type="text" data-f="location" value="${escapeHtml(p.location || '')}" placeholder="如 杭州 西湖" /></label>
      <label>标签 <input type="text" data-f="tags" value="${escapeHtml((p.tags || []).join(' '))}" placeholder="空格分隔" /></label>
      <button class="btn btn-primary" data-act="save" type="button">保存</button>
      <button class="btn" data-act="cancel" type="button">取消</button>
      <button class="link" data-act="delete" type="button">不导入这张</button>
    </div>
  </td>`;
  tr.querySelector('[data-act="save"]').addEventListener('click', () => {
    const date = tr.querySelector('[data-f="date"]').value;
    const location = tr.querySelector('[data-f="location"]').value.trim();
    const tags = tr.querySelector('[data-f="tags"]').value.trim().split(/\s+/).filter(Boolean);
    if (date) { p.date = date; p.dateSource = 'override'; p.dateConfidence = 1; }
    if (location) { p.location = location; p.locationConfidence = 1; }
    if (tags.length) p.tags = [...new Set([...(p.tags || []), ...tags])];
    p.__override = { ...(p.__override || {}), ...(date ? { date } : {}), ...(location ? { location } : {}), ...(tags.length ? { tags } : {}) };
    p.__folder = p.path.includes('/') ? p.path.slice(0, p.path.lastIndexOf('/')) : '';
    renderSummary();
    renderTable();
    toast('已修正，写入时会一并保存为 overrides');
  });
}

function onTableChange() { /* 预留 */ }

/* ---------------- 写出 ---------------- */

function updateWriteHint() {
  const n = state.photos.length;
  const mediaCount = state.media.size + state.originals.size;
  const more = Number($('#imp-write-hint').dataset.more || 0);
  const existing = state.existing?.length || 0;
  const parts = [];
  if (n) {
    parts.push(`本次导入 <b>${n}</b> 张、<b>${mediaCount}</b> 个图片文件`);
    if (existing) {
      const preview = mergeRecords(state.photos, state.existing);
      parts.push(`将合并进站点：新增 <b>${preview.added}</b>、更新 <b>${preview.replaced}</b>、保留原有 <b>${preview.kept}</b>，合计 <b>${preview.total}</b> 张`);
    } else {
      parts.push('站点当前还没有照片，将成为第一批');
    }
    if (more > 0) parts.push(`（表格中还有 ${more} 条未显示，不影响写入）`);
  } else {
    parts.push('还没有可写入的内容，先把照片拖进来吧');
  }
  if (state.dirHandle) parts.push(`上次的目录已记住：<b>${escapeHtml(state.dirHandle.name)}</b>`);
  $('#imp-write-hint').innerHTML = parts.join('　');
  $('#imp-save').disabled = !n;
  $('#imp-zip').disabled = !n;

  const warn = [];
  if (state.errors.length) warn.push(`${state.errors.length} 个文件处理失败（见控制台）`);
  if (state.skipped.length) warn.push(`${state.skipped.length} 个文件被跳过`);
  if (state.originals.size > 0) warn.push('完整模式会把原图一并写入，注意 GitHub 仓库体积（见 docs/存储方案.md）');
  // 浏览器不支持直接写目录时，这条提示优先显示
  if (typeof window.showDirectoryPicker !== 'function') {
    warn.unshift('当前浏览器不支持直接写入文件夹：点「写入站点目录」会自动改成下载 zip，请解压后覆盖仓库里的 public/。想一键写入请用 Chrome / Edge。');
  }
  $('#imp-warn').textContent = warn.join('；');
}

/** 写入成功后重新读取站点数据，刷新品牌栏、筛选、各视图与待确认计数 */
async function refreshSiteAfterWrite() {
  const reload = window.__pj?.reload;
  if (reload) {
    await reload();
    await loadSiteState();
    updateWriteHint();
    renderSummary();
    return;
  }
  await loadSiteState();
  updateWriteHint();
}

/** 导入完成后切到相册，并标出这次导入的照片 */
function focusImportedPhotos() {
  const ids = state.importedIds || [];
  if (!ids.length) return;
  const pj = window.__pj;
  if (!pj) return;

  // 清掉可能存在的筛选，确保新照片不会被筛掉
  const hasFilter = pj.state.filter && Object.values(pj.state.filter).some(
    (v) => (Array.isArray(v) && v.length) || (v && v !== null && v !== false),
  );
  if (hasFilter) {
    pj.resetFilters?.();
  }
  pj.setView('grid');
  pj.highlightIds?.(ids);
}

/* ---------------- 目标目录校验 ---------------- */

/**
 * 判断一个目录句柄是不是本站的站点根目录（也就是本项目的 public/）。
 *
 * 这一步非常关键：以前如果选错了目录，代码会自作主张在里面新建一个 public 子目录，
 * 结果是"写了但站点看不到"。现在改为**绝不擅自改动去向**，选错就直接报错说明。
 * 具体实现见 src/site-root.js（Node 与浏览器共用，有单元测试）。
 */
async function pickSiteRoot() {
  const picked = await window.showDirectoryPicker({ mode: 'readwrite', id: 'pj-target' });

  const direct = await inspectSiteRoot(picked);
  if (direct.ok) return picked;

  // 选到了上一层：如果在里面找到唯一的站点目录，就用它
  const candidates = await findSiteRoots(picked);
  if (candidates.length === 1) {
    toast(`已自动使用 ${candidates[0].label}`);
    return candidates[0].handle;
  }
  if (candidates.length > 1) {
    throw new Error(
      `你选的目录里有多个站点目录（${candidates.map((c) => c.label).join('、')}），请直接选择其中一个 public 目录`,
    );
  }

  throw new Error(describeSitePick(picked.name, direct.reason));
}

/** 写入之后回到站点上验证一遍：索引真的能被页面读到了吗 */
async function verifyWritten() {
  try {
    const res = await fetch(`data/index.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return { ok: false, reason: `站点返回 HTTP ${res.status}` };
    const idx = await res.json();
    const search = await (await fetch(`data/search.json?t=${Date.now()}`, { cache: 'no-store' })).json();
    return { ok: true, photos: idx?.stats?.photos ?? 0, searchCount: Array.isArray(search) ? search.length : 0 };
  } catch (err) {
    return { ok: false, reason: err.message };
  }
}

async function saveToDirectory() {
  log('──────── 点击「写入站点目录」 ────────');
  // 清掉上一次的结果记录，避免旧信息误导本次判断
  try { localStorage.removeItem(RESULT_KEY); } catch { /* 忽略 */ }
  const oldResult = $('#imp-write-result');
  if (oldResult) { oldResult.hidden = true; oldResult.textContent = ''; }
  hideGlobalBanner();
  log(`本机是否支持 showDirectoryPicker：${typeof window.showDirectoryPicker === 'function'}`);
  log(`页面地址：${location.href}`);
  log(`站点上是否已能读到索引：${await siteHasIndex() ? '是' : '否'}`);

  if (!state.photos.length) {
    log('中断：本次还没有处理任何照片（要先拖文件夹进来）');
    toast('还没有可写入的照片，请先把文件夹拖进来');
    return;
  }
  log(`准备写入 ${state.photos.length} 张照片、${state.media.size + state.originals.size} 个图片文件`);
  log(`站点上已有 ${state.existing?.length || 0} 张（会合并，不会被冲掉）`);

  if (!window.showDirectoryPicker) {
    log('本浏览器不支持 showDirectoryPicker，改为导出 zip');
    toast('此浏览器不支持直接写目录，已改为下载 zip');
    await doExportZip();
    return;
  }

  let dir = state.dirHandle;
  try {
    if (dir) {
      log(`已有记住的目录：${dir.name}，检查权限…`);
      let perm = await dir.queryPermission({ mode: 'readwrite' });
      log(`权限状态：${perm}`);
      if (perm !== 'granted') perm = await dir.requestPermission({ mode: 'readwrite' });
      if (perm !== 'granted') {
        log('权限未授予，需要重新选择目录');
        dir = null;
      } else {
        const check = await inspectSiteRoot(dir);
        log(`目录校验：${check.ok ? '通过（' + check.via + '）' : '不通过 — ' + check.reason}`);
        if (!check.ok) {
          toast(`上次记住的目录「${dir.name}」${check.reason}，请重新选择`);
          dir = null;
        }
      }
    }
    if (!dir) {
      log('弹出目录选择框…（请选择本项目里的 public 目录）');
      dir = await pickSiteRoot();
      log(`已选中目录：${dir.name}`);
    }
    state.dirHandle = dir;
    await saveHandle('target', dir);
  } catch (err) {
    if (err && err.name === 'AbortError') {
      log('用户取消了目录选择');
      return;
    }
    log(`目录选择/校验失败：${err.message}`);
    console.warn(err);
    toast('目录不对：' + err.message);
    showWriteResult('写入未开始：' + err.message, false);
    return;
  }

  const btn = $('#imp-save');
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = '正在写入…';

  try {
    const bundle = prepareBundle();
    log(`开始写入：索引 ${bundle.monthFiles.length} 个月份文件 + media ${bundle.media.size} 个…`);
    let lastLog = 0;
    bundle.onProgress = ({ done, total, current }) => {
      const now = performance.now();
      if (now - lastLog < 400 && done < total) return;
      lastLog = now;
      log(`写入中 ${done}/${total}：${current}`);
    };
    const written = await writeToDirectory(dir, bundle);
    log(`写入完成：${written.photos} 张 / ${written.media} 个图片 / ${written.json} 个索引文件，共 ${(written.bytes / 1048576).toFixed(1)} MB`);
    if (written.readBack?.error) {
      log(`回读失败（写入可能没落盘）：${written.readBack.error}`);
    } else if (written.readBack) {
      log(`回读校验：index.json ${written.readBack.size} 字节，记录 ${written.readBack.photos} 张`);
    }

    // 留一个站点身份标记，下次重新选择目录时能一眼认出来
    try {
      const fh = await dir.getFileHandle(SITE_MARKER_FILE, { create: true });
      const w = await fh.createWritable();
      await w.write('photo-journal site root\n它是本项目的 public 目录，网页导入会把 data/ 与 media/ 写到这里。\n');
      await w.close();
    } catch { /* 标记失败不影响导入 */ }

    const m = state.lastMerge;
    const mergeInfo = m
      ? `新增 ${m.added}、更新 ${m.replaced}${m.kept > 0 ? `、保留原有 ${m.kept}` : ''}，站点共 ${m.total} 张`
      : `${written.photos} 张`;

    // 写入后一定回到站点上核对一遍
    const check = await verifyWritten();
    log(`回站校验：${check.ok ? `通过，站点现有 ${check.photos} 张` : '失败 — ' + check.reason}`);
    if (!check.ok) {
      toast(`已写入「${dir.name}」，但站点读不到索引（${check.reason}）`);
      showWriteResult(
        `已写入「${dir.name}」，但站点未能读取到新索引：${check.reason}\n`
        + '请确认你选择的是本项目的 public 目录（里面应该有 index.html）。',
        false,
      );
      return;
    }

    const now = Date.now();
    const recent = lastWriteTime && (now - lastWriteTime) < 600000;
    if (recent && check.photos === 0) {
      log('警告：上次写入后站点仍是 0 张，可能写到了别的目录');
      showWriteResult(
        '写入报告成功，但站点上仍是 0 张照片。请确认你选择的是本项目的 public 目录，'
        + '并检查浏览器控制台与「诊断」输出。',
        false,
      );
      return;
    }

    showWriteResult(
      `已写入 ${written.photos} 张照片 / ${written.media} 个图片文件 / ${written.json} 个索引文件`
      + `（${mergeInfo}）→ 站点现有 ${check.photos} 张`,
      true,
    );
    lastWriteTime = now;
    showGlobalBanner(`导入成功：${mergeInfo}。已写入「${dir.name}」，站点现有 ${check.photos} 张照片。`);
    setTimeout(() => hideGlobalBanner(), 6000);
    state.importedIds = state.photos.map((p) => p.id);
    log(`本次导入的 id：${state.importedIds.length} 个，开始刷新界面`);
    toast(`导入完成：${mergeInfo}，正在显示新导入的照片`);
    await refreshSiteAfterWrite();
    focusImportedPhotos();
    log('界面已刷新并切回相册');
  } catch (err) {
    log(`写入失败：${err.name || ''} ${err.message}`);
    console.error(err);
    toast('写入失败：' + err.message);
    showWriteResult('写入失败：' + err.message, false);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
    updateWriteHint();
  }
}

/** 站点上现在能不能读到索引 */
async function siteHasIndex() {
  try {
    const r = await fetch(`data/index.json?t=${Date.now()}`, { cache: 'no-store' });
    return r.ok;
  } catch {
    return false;
  }
}

/** 诊断：把环境、模块、数据链路一次性检查清楚并打印出来 */
async function diagnose() {
  log('════════ 开始诊断 ════════');
  log(`浏览器：${navigator.userAgent}`);
  log(`页面地址：${location.href}`);
  log(`是否安全上下文（https 或 localhost）：${window.isSecureContext ? '是' : '否'}`);
  log(`showDirectoryPicker：${typeof window.showDirectoryPicker === 'function' ? '支持' : '不支持（Firefox/Safari 或旧版浏览器）'}`);
  log(`indexedDB：${typeof indexedDB !== 'undefined' ? '可用' : '不可用（无痕模式？）'}`);
  log(`createImageBitmap：${typeof createImageBitmap === 'function' ? '可用' : '不可用'}`);
  log(`OffscreenCanvas：${typeof OffscreenCanvas !== 'undefined' ? '可用' : '不可用（会退回普通 canvas）'}`);
  try {
    if (navigator.storage?.estimate) {
      const est = await navigator.storage.estimate();
      log(`浏览器存储配额：已用 ${(est.usage / 1048576).toFixed(1)} MB / 上限 ${(est.quota / 1048576).toFixed(0)} MB`);
    }
  } catch { /* 忽略 */ }

  // 模块能否加载
  for (const [name, path] of [
    ['exifr bundle', 'vendor/exif-parse.js'],
    ['导入引擎', 'assets/import.js'],
    ['目录校验', 'src/site-root.js'],
  ]) {
    try {
      const res = await fetch(path, { cache: 'no-store' });
      log(`模块 ${name}：HTTP ${res.status}${res.ok ? '' : ' ← 缺失！'}`);
    } catch (err) {
      log(`模块 ${name}：加载失败 ${err.message}`);
    }
  }

  // 站点数据链路
  for (const f of ['data/index.json', 'data/search.json']) {
    try {
      const res = await fetch(`${f}?t=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) { log(`${f}：HTTP ${res.status}（尚未导入过就属正常）`); continue; }
      const json = await res.json();
      const n = f.includes('index') ? json?.stats?.photos : (Array.isArray(json) ? json.length : '?');
      log(`${f}：HTTP 200，记录 ${n} 张`);
    } catch (err) {
      log(`${f}：读取失败 ${err.message}`);
    }
  }

  // 当前导入状态
  log(`本次已处理：${state.photos.length} 张，图片文件 ${state.media.size + state.originals.size} 个`);
  log(`站点已有：${state.existing?.length || 0} 张`);
  log(`记住的目标目录：${state.dirHandle ? state.dirHandle.name : '（无）'}`);
  if (state.errors.length) log(`处理失败 ${state.errors.length} 条：${state.errors.slice(0, 3).join('；')}`);

  log('提示：把上面这段内容发给我即可定位问题。');
  log('════════ 诊断结束 ════════');
  toast('诊断结果已显示在下方，可复制发给开发者');
}

/* ---------------- 目标目录校验 ---------------- */

/** 把写入结果写进界面（而不是只弹一个会消失的 toast），并留一份以便刷新后仍能看到 */
function showWriteResult(message, ok) {
    // 关键：结果框在 #imp-result 里面，如果那个面板还藏着，用户就什么都看不到
  const panel = $('#imp-result');
  if (panel) panel.hidden = false;

  const el = $('#imp-write-result');
  if (el) {
    el.hidden = false;
    el.className = `imp-write-result ${ok ? 'is-ok' : 'is-bad'}`;
    el.textContent = message;
    if (el.offsetParent) el.scrollIntoView({ block: 'nearest' });
  }
  const saved = { message, ok, at: Date.now() };
  try { localStorage.setItem(RESULT_KEY, JSON.stringify(saved)); } catch { /* 忽略 */ }
  if (ok) lastWriteTime = saved.at;

  // 失败一定要在任何页面都看得见（导入页可能是隐藏的）
  if (!ok) showGlobalBanner(`导入未能写入，照片没有保存到站点：\n${message}`);
}

/** 全局横幅（任何视图下都可见） */
function showGlobalBanner(text) {
  const box = $('#global-banner');
  const el = $('#global-banner-text');
  if (!box || !el) return;
  el.textContent = text;
  box.hidden = false;
  box.classList.remove('is-ok');
}

/** 隐藏全局横幅 */
function hideGlobalBanner() {
  const box = $('#global-banner');
  if (box) box.hidden = true;
}

/** 刷新页面后把上一次的写入结果重新显示出来（避免"什么都没发生"的错觉） */
function restoreWriteResult() {
  try {
    const raw = localStorage.getItem(RESULT_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (!saved || !saved.message) return;
    const when = new Date(saved.at).toLocaleString('zh-CN');
    const panel = $('#imp-result');
    if (panel) panel.hidden = false;
    const el = $('#imp-write-result');
    if (!el) return;
    el.hidden = false;
    el.className = `imp-write-result ${saved.ok ? 'is-ok' : 'is-bad'}`;
    el.textContent = `【上次写入结果 · ${when}】${saved.message}`;

    // 上一次是失败的话，用全局横幅再提醒一次
    if (!saved.ok) {
      showGlobalBanner(`上一次导入没有写入成功（${when}）：\n${saved.message}`);
    }
  } catch { /* 忽略 */ }
}

async function doExportZip() {
  if (!state.photos.length) return;
  const btn = $('#imp-zip');
  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = '打包中…';
  try {
    const bundle = prepareBundle();
    const r = await exportZip(bundle);
    toast(`已打包 ${r.files} 个文件（${humanSize(r.bytes)}），解压后覆盖 public/ 即可`);
  } catch (err) {
    console.error(err);
    toast('打包失败：' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}

function prepareBundle() {
  // 合并人工修正出来的 overrides
  const overrides = collectOverrides(state.photos);
  // 合并站点上已有的照片（按 id 去重，本次导入的优先）
  const merged = mergeRecords(state.photos, state.existing || []);
  state.lastMerge = merged;
  const bundle = buildIndex({
    photos: merged.photos,
    title: document.title || '我的摄影记录',
    subtitle: '',
    source: '网页导入',
  });
  return {
    ...bundle,
    media: state.media,
    originals: state.originals,
    overrides: Object.keys(overrides).length ? overrides : null,
  };
}

/** 导入前先摸清站点上已有什么，写入时才知道是"新增"还是"替换" */
async function loadSiteState() {
  state.existing = [];
  try {
    state.existing = await loadExistingFullPhotos();
  } catch {
    state.existing = [];
  }
  return state.existing.length;
}

function resetAll() {
  state.photos = [];
  state.media = new Map();
  state.originals = new Map();
  state.errors = [];
  state.skipped = [];
  $('#imp-result').hidden = true;
  $('#imp-progress').hidden = true;
  $('#imp-bar').style.width = '0';
  updateWriteHint();
  toast('已清空，可以重新拖入');
}

/* ---------------- 小工具 ---------------- */

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3200);
}
