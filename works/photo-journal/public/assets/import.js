/**
 * 浏览器端导入引擎
 *
 * 拖一个文件夹进网页，就完成整个导入：
 *   读取文件 → exifr 读 EXIF/XMP/GPS → 解析文件夹名 → Canvas 生成 WebP 缩略图
 *   → 合并进 data/index.json 等索引 → 写回仓库目录 / 打包 zip 下载
 *
 * 生成的文件结构与 scripts/import.mjs 完全一致，因此两种导入方式可以混用。
 */

import { isSupportedPhoto, extOf } from '../../src/exif.js';
// 浏览器端由 scripts/build-vendor.mjs 打好的 bundle（内含 exifr）
import { readExifFromBuffer } from '../vendor/exif-parse.js';
import { buildRecord } from '../../src/record.js';
import { mergeRecords, compactRecord } from '../../src/merge.js';

export { mergeRecords, compactRecord };
import { makeMediaInBrowser, browserCanDecode, perceptualHashInBrowser } from '../../src/media-browser.js';
import { createZip } from '../../src/zip.js';

const SKIP_DIRS = new Set([
  'node_modules', '.git', '.cache', '.npm-cache', 'dist', '$RECYCLE.BIN',
  'System Volume Information', 'Thumbs.db', 'Previews.lrdata', '.thumbnails',
]);
const SKIP_FILE_RE = /(^\.|^Thumbs\.db$|^desktop\.ini$|\.xmp$|\.lrcat|\.lrdata$|\.tmp$|\.bak$|\.dop$|\.pp3$)/i;
const VIDEO_EXT = new Set(['.mp4', '.mov', '.m4v', '.avi', '.mkv']);

/* ------------------------------------------------------------------ */
/* 收集文件                                                            */
/* ------------------------------------------------------------------ */

/** 拖拽进来的 DataTransfer → 扁平文件列表（支持整个文件夹） */
export async function collectFromDataTransfer(dataTransfer) {
  const items = dataTransfer.items ? [...dataTransfer.items] : [];
  const roots = [];
  for (const item of items) {
    if (item.kind !== 'file') continue;
    const entry = item.webkitGetAsEntry?.();
    if (entry) roots.push(entry);
  }
  if (!roots.length) {
    // 退路：直接取 items 里的 File（某些浏览器/合成事件下拿不到 entry）
    const files = [];
    for (const item of items) {
      if (item.kind !== 'file') continue;
      const f = item.getAsFile?.();
      if (f) files.push({ file: f, path: f.webkitRelativePath || f.name });
    }
    if (files.length) return files;
    return [...(dataTransfer.files || [])].map((f) => ({ file: f, path: f.webkitRelativePath || f.name }));
  }
  const out = [];
  for (const root of roots) await walkEntry(root, '', out);
  return out;
}

function entryFile(entry) {
  return new Promise((resolve) => entry.file(resolve, () => resolve(null)));
}

async function walkEntry(entry, prefix, out) {
  if (!entry) return;
  if (entry.isFile) {
    if (SKIP_FILE_RE.test(entry.name)) return;
    const file = await entryFile(entry);
    if (file) out.push({ file, path: prefix ? `${prefix}/${entry.name}` : entry.name });
    return;
  }
  if (!entry.isDirectory) return;
  if (SKIP_DIRS.has(entry.name) || entry.name.startsWith('.')) return;
  const dirPrefix = prefix ? `${prefix}/${entry.name}` : entry.name;
  const reader = entry.createReader();
  const children = [];
  // readEntries 每次最多返回 100 条，需要反复读
  await new Promise((resolve) => {
    const readBatch = () => {
      reader.readEntries(async (batch) => {
        if (!batch.length) { resolve(); return; }
        children.push(...batch);
        readBatch();
      }, () => resolve());
    };
    readBatch();
  });
  for (const child of children) await walkEntry(child, dirPrefix, out);
}

/** <input type="file" webkitdirectory> 或 DataTransfer.files 里的相对路径 */
export function collectFromFileList(fileList) {
  return [...fileList]
    .filter((f) => !SKIP_FILE_RE.test(f.name))
    .map((f) => ({ file: f, path: (f.webkitRelativePath || f.name).replace(/\\/g, '/') }));
}

/* ------------------------------------------------------------------ */
/* 哈希（与 Node 端保持一致的思路：前 256KB + 文件大小）                  */
/* ------------------------------------------------------------------ */

async function hashOf(file) {
  const head = await file.slice(0, 256 * 1024).arrayBuffer();
  const buf = new Uint8Array(head.byteLength + 8);
  buf.set(new Uint8Array(head), 0);
  new DataView(buf.buffer).setFloat64(head.byteLength, file.size, true);
  if (crypto?.subtle) {
    const digest = await crypto.subtle.digest('SHA-1', buf);
    return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 20);
  }
  // 极老的浏览器：退回简单哈希
  let h = 0x811c9dc5;
  for (const b of buf) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, '0');
}

/* ------------------------------------------------------------------ */
/* 导入主流程                                                          */
/* ------------------------------------------------------------------ */

/**
 * @param {object} opts
 * @param {Array<{file:File, path:string}>} opts.entries
 * @param {string} opts.rootName       拖入的顶层文件夹名（用于判断路径层级）
 * @param {boolean} opts.keepOriginals 是否把原图也写进 media/originals
 * @param {(p:object)=>void} opts.onProgress
 * @param {Map<string, object>} [opts.existingMedia] 已存在的缩略图（hash → 路径），用于跳过重复生成
 */
export async function processEntries({
  entries, rootName = '', keepOriginals = false, onProgress = () => {}, existingMedia = new Map(),
}) {
  // 过滤出可处理的照片
  const photos = [];
  const skipped = [];
  for (const e of entries) {
    const ext = extOf(e.file.name);
    if (isSupportedPhoto(e.file.name) || VIDEO_EXT.has(ext)) photos.push(e);
    else skipped.push(e.path);
  }
  photos.sort((a, b) => a.path.localeCompare(b.path, 'zh-Hans-CN'));

  const results = [];
  const media = new Map();     // 相对 public 的路径 → Blob/Uint8Array
  const originals = new Map(); // 同上，仅 keepOriginals
  const errors = [];
  const total = photos.length;

  // 自动剥掉顶层文件夹名，避免 output 里多一层
  const stripRoot = (p) => {
    if (!rootName) return p;
    const first = p.split('/')[0];
    return first === rootName ? p.split('/').slice(1).join('/') || p : p;
  };

  for (let i = 0; i < total; i++) {
    const e = photos[i];
    const rel = stripRoot(e.path);
    onProgress({ phase: 'process', done: i, total, current: rel, results: results.length });

    const ext = extOf(e.file.name);
    const isVideo = VIDEO_EXT.has(ext);
    let exif = { empty: true };
    let hash = null;
    let thumbEntry = null;
    let previewEntry = null;
    let color = null;
    let displaySize = null;
    let phash = null;

    try {
      if (!isVideo) {
        const buffer = await e.file.arrayBuffer();
        exif = await readExifFromBuffer(buffer);
      }
    } catch (err) {
      errors.push(`${rel}: 读 EXIF 失败 ${err.message}`);
    }

    try {
      hash = await hashOf(e.file);
    } catch (err) {
      errors.push(`${rel}: 计算哈希失败 ${err.message}`);
    }

    const thumbPath = hash ? `media/thumbs/${hash}.webp` : null;
    const previewPath = hash ? `media/previews/${hash}.webp` : null;

    if (!isVideo && hash && browserCanDecode(e.file.name)) {
      const cached = existingMedia.get(thumbPath);
      if (cached) {
        // 已有相同内容的缩略图，直接复用（不重复生成）
        thumbEntry = cached.thumb;
        previewEntry = cached.preview;
        color = cached.color || null;
      } else {
        try {
          const made = await makeMediaInBrowser(e.file);
          if (made.thumb) { media.set(thumbPath, made.thumb); thumbEntry = thumbPath; }
          if (made.preview) { media.set(previewPath, made.preview); previewEntry = previewPath; }
          color = made.color;
          displaySize = made.size;
        } catch (err) {
          errors.push(`${rel}: 生成缩略图失败 ${err.message}`);
        }
        // 感知哈希（用于重复照片检测）
        try {
          phash = await perceptualHashInBrowser(e.file);
        } catch { /* 失败就跳过，只是查不了重复 */ }
      }
    } else if (!isVideo && hash && !browserCanDecode(e.file.name)) {
      skipped.push(`${rel}（浏览器无法预览该格式，已读取参数但不生成缩略图）`);
    }

    if (keepOriginals && hash) {
      const target = `media/originals/${hash.slice(0, 2)}/${hash}${ext}`;
      originals.set(target, e.file);
    }

    let rec;
    try {
      rec = buildRecord({
        relPath: rel,
        fileName: e.file.name,
        bytes: e.file.size,
        exif,
        prefs: {},
        media: {
          thumb: thumbEntry,
          preview: previewEntry,
          original: keepOriginals && hash ? `media/originals/${hash.slice(0, 2)}/${hash}${ext}` : null,
        },
        dominantColor: color,
        displaySize,
        phash,
      });
      rec.video = isVideo || undefined;
      if (!rec.date) {
        rec.date = new Date(e.file.lastModified).toISOString().slice(0, 10);
        rec.dateSource = 'mtime';
        rec.dateConfidence = 0.2;
      }
      if (!keepOriginals) rec.src = null;
    } catch (err) {
      errors.push(`${rel}: 组装记录失败 ${err.message}`);
      continue;
    }

    results.push(rec);
  }

  onProgress({ phase: 'done', done: total, total, results: results.length });

  // 按时间倒序
  results.sort((a, b) => {
    const da = a.date || '0000-00-00';
    const db = b.date || '0000-00-00';
    if (da !== db) return db.localeCompare(da);
    return (b.time || '').localeCompare(a.time || '');
  });

  return { results, media, originals, errors, skipped, total };
}

/* ------------------------------------------------------------------ */
/* 索引生成（与 scripts/import.mjs 的规则一致）                          */
/* ------------------------------------------------------------------ */

export function buildIndex({ photos, title, subtitle, author, source }) {
  const byMonth = new Map();
  for (const p of photos) {
    const key = /^\d{4}-\d{2}/.test(p.date || '') ? p.date.slice(0, 7) : 'unknown';
    if (!byMonth.has(key)) byMonth.set(key, []);
    byMonth.get(key).push(p);
  }

  const years = {};
  for (const [key, list] of byMonth) {
    if (key === 'unknown') continue;
    const y = key.slice(0, 4);
    years[y] = (years[y] || 0) + list.length;
  }

  const locMap = new Map();
  for (const p of photos) {
    const name = p.location || '未识别地点';
    const key = p.coords ? `${name}|${p.coords.lat.toFixed(3)},${p.coords.lng.toFixed(3)}` : name;
    if (!locMap.has(key)) {
      locMap.set(key, {
        name, lat: p.coords?.lat ?? null, lng: p.coords?.lng ?? null,
        count: 0, first: p.date, last: p.date, cover: p.thumb || p.preview,
      });
    }
    const e = locMap.get(key);
    e.count++;
    if (p.date && (!e.first || p.date < e.first)) e.first = p.date;
    if (p.date && (!e.last || p.date > e.last)) e.last = p.date;
  }

  const tally = (fn) => {
    const m = new Map();
    for (const p of photos) {
      const v = fn(p);
      if (!v) continue;
      m.set(v, (m.get(v) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count }));
  };

  const tagMap = new Map();
  for (const p of photos) for (const t of p.tags || []) tagMap.set(t, (tagMap.get(t) || 0) + 1);

  const dates = photos.map((p) => p.date).filter((d) => /^\d{4}/.test(d || '')).sort();

  const stats = {
    photos: photos.length,
    withGps: photos.filter((p) => p.coords).length,
    withExifDate: photos.filter((p) => p.dateSource === 'exif').length,
    fromFolderName: photos.filter((p) => p.dateSource === 'folder' || p.dateSource === 'folder-partial').length,
    fromMtime: photos.filter((p) => p.dateSource === 'mtime').length,
    withLocation: photos.filter((p) => p.location).length,
    lowConfidence: photos.filter((p) => (p.dateConfidence ?? 0) < 0.6 || !p.location).length,
    firstDate: dates[0] || null,
    lastDate: dates[dates.length - 1] || null,
    bytes: photos.reduce((s, p) => s + (p.bytes || 0), 0),
  };

  const index = {
    generatedAt: new Date().toISOString(),
    title: title || '我的摄影记录',
    subtitle: subtitle || '',
    author: author || '',
    source: source || '网页导入',
    stats,
    years,
    months: [...byMonth.entries()]
      .map(([key, list]) => ({ key, count: list.length, cover: list[0].thumb || list[0].preview || list[0].src }))
      .sort((a, b) => b.key.localeCompare(a.key)),
    locations: [...locMap.values()].sort((a, b) => b.count - a.count),
    cameras: tally((p) => (p.camera ? [p.camera.make, p.camera.model].filter(Boolean).join(' ') : null)),
    lenses: tally((p) => p.lens),
    editors: tally((p) => p.editedBy),
    tags: [...tagMap.entries()].sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count })),
  };

  const search = photos.map(compactRecord);

  const monthFiles = [...byMonth.entries()].map(([key, list]) => ({
    name: key === 'unknown' ? 'photos-unknown.json' : `photos-${key}.json`,
    data: JSON.stringify({ month: key, count: list.length, photos: list }, null, 1),
  }));

  return { index, search, byMonth, monthFiles };
}

/* ------------------------------------------------------------------ */
/* 写出结果                                                            */
/* ------------------------------------------------------------------ */

function mediaNameOf(pathname) {
  return pathname.split('/').pop();
}

/**
 * 写入前把上一次的索引备份到 data/backup/，并顺手删掉已经没用的旧月份文件。
 * 这样即使新写入有问题，也能从 backup 里找回上一版索引。
 * 备份失败不影响导入本身。
 */
async function backupAndPrune(publicDir, dataDir, keepNames) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  let backupDir = null;
  let backedUp = 0;
  const removed = [];

  try {
    backupDir = await dataDir.getDirectoryHandle('backup', { create: true });
  } catch { /* 无法建备份目录就跳过 */ }

  // 1) 备份并找出过期的月份文件
  try {
    for await (const [name, handle] of dataDir.entries()) {
      if (handle.kind !== 'file') continue;
      if (!/\.json$/.test(name)) continue;

      if (backupDir && (name === 'index.json' || name === 'search.json')) {
        try {
          const file = await handle.getFile();
          const text = await file.text();
          const fh = await backupDir.getFileHandle(`${stamp}_${name}`, { create: true });
          const w = await fh.createWritable();
          await w.write(text);
          await w.close();
          backedUp++;
        } catch { /* 单个备份失败忽略 */ }
      }

      // 旧月份文件：这次不再生成的就删掉，避免留下过期数据
      if (/^photos-.*\.json$/.test(name) && !keepNames.has(name)) {
        try {
          await dataDir.removeEntry(name);
          removed.push(name);
        } catch { /* 删不掉就算了 */ }
      }
    }
  } catch { /* 列目录失败忽略 */ }

  return { backedUp, removed, stamp };
}

/**
 * 用 File System Access API 写回仓库的 public/ 目录
 * @param {FileSystemDirectoryHandle} publicDir 用户选中的 public 目录
 * @param {object} bundle
 * @param {(p:{done:number,total:number,current:string})=>void} [bundle.onProgress] 进度回调
 */
export async function writeToDirectory(publicDir, { index, search, monthFiles, media, originals, overrides, onProgress }) {
  const written = { photos: 0, media: 0, json: 0, bytes: 0, readBack: null, backup: null, removed: [] };
  const report = (current) => {
    const total = media.size + originals.size + monthFiles.length + 2;
    onProgress?.({ done: written.media + written.json, total, current });
  };

  const dataDir = await publicDir.getDirectoryHandle('data', { create: true });

  // 先备份 + 清理过期月份文件
  const keepNames = new Set(monthFiles.map((m) => m.name));
  written.backup = await backupAndPrune(publicDir, dataDir, keepNames);
  written.removed = written.backup.removed;

  const writeText = async (dirHandle, name, text) => {
    const fh = await dirHandle.getFileHandle(name, { create: true });
    const w = await fh.createWritable();
    await w.write(text);
    await w.close();
    written.json++;
    written.bytes += text.length;
    report(name);
  };

  await writeText(dataDir, 'index.json', JSON.stringify(index, null, 1));
  await writeText(dataDir, 'search.json', JSON.stringify(search));
  for (const m of monthFiles) await writeText(dataDir, m.name, m.data);
  if (overrides) await writeText(dataDir, 'archives.json', JSON.stringify(overrides, null, 1));

  const writeBlob = async (rootHandle, pathname, blob) => {
    let dir = rootHandle;
    const parts = pathname.split('/').slice(1, -1); // 去掉 "media" 与文件名
    for (const p of parts) dir = await dir.getDirectoryHandle(p, { create: true });
    const fh = await dir.getFileHandle(mediaNameOf(pathname), { create: true });
    const w = await fh.createWritable();
    await w.write(blob);
    await w.close();
    written.media++;
    written.bytes += blob.size || 0;
    report(pathname);
  };

  const mediaRoot = await publicDir.getDirectoryHandle('media', { create: true });
  for (const [pathname, blob] of media) await writeBlob(mediaRoot, pathname, blob);
  for (const [pathname, blob] of originals) await writeBlob(mediaRoot, pathname, blob);

  // 写完立刻回读一遍，确认真的落到磁盘上了（不是只"以为"写成功）
  try {
    const fh = await dataDir.getFileHandle('index.json');
    const file = await fh.getFile();
    const text = await file.text();
    const parsed = JSON.parse(text);
    written.readBack = { size: file.size, photos: parsed?.stats?.photos ?? null };
  } catch (err) {
    written.readBack = { error: err.message };
  }

  written.photos = index.stats.photos;
  return written;
}

/** 打包成 zip 下载（兼容所有浏览器） */
export async function exportZip({ index, search, monthFiles, media, originals, overrides }) {
  const files = [
    { name: 'public/data/index.json', data: JSON.stringify(index, null, 1) },
    { name: 'public/data/search.json', data: JSON.stringify(search) },
    ...monthFiles.map((m) => ({ name: `public/data/${m.name}`, data: m.data })),
    ...(overrides ? [{ name: 'public/data/archives.json', data: JSON.stringify(overrides, null, 1) }] : []),
  ];
  for (const [pathname, blob] of media) files.push({ name: `public/${pathname}`, data: blob });
  for (const [pathname, blob] of originals) files.push({ name: `public/${pathname}`, data: blob });

  const bytes = await createZip(files);
  const blob = new Blob([bytes], { type: 'application/zip' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `photo-journal-import-${new Date().toISOString().slice(0, 10)}.zip`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
  return { files: files.length, bytes: bytes.length };
}

/** 读取站点上已有的精简索引（首次导入时返回空数组） */
export async function loadExistingPhotos() {
  try {
    const res = await fetch('data/search.json', { cache: 'no-cache' });
    if (!res.ok) return [];
    const list = await res.json();
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

/**
 * 读取站点上已有的**完整**记录（逐月文件）。
 * 合并时需要完整记录才能正确重算统计、相机/镜头分布等。
 */
export async function loadExistingFullPhotos() {
  try {
    const idxRes = await fetch('data/index.json', { cache: 'no-cache' });
    if (!idxRes.ok) return [];
    const index = await idxRes.json();
    // 只请求索引里确实存在的月份文件，避免无意义的 404
    const files = (index.months || [])
      .map((m) => m.key)
      .filter((k) => k && k !== 'unknown')
      .map((k) => `photos-${k}.json`);
    const out = [];
    for (const f of files) {
      try {
        const r = await fetch(`data/${f}`, { cache: 'no-cache' });
        if (!r.ok) continue;
        const d = await r.json();
        if (Array.isArray(d.photos)) out.push(...d.photos);
      } catch { /* 单个文件失败不影响整体 */ }
    }
    return out;
  } catch {
    return [];
  }
}

/** 读取已有缩略图清单，用于跳过重复生成 */
export async function loadExistingMedia() {
  const map = new Map();
  for (const p of await loadExistingPhotos()) {
    if (p.th) {
      map.set(p.th, { thumb: p.th, preview: p.th.replace('/thumbs/', '/previews/'), color: p.cl || null });
    }
  }
  return map;
}

/**
 * 把新导入的照片合并进已有记录（按 id 去重，新数据优先）。
 * 规则与实现见 src/merge.js（同一份代码，命令行与网页共用）。
 */

/** 把人工修正收集成 overrides（供 CLI 下次导入时复用） */
export function collectOverrides(photos) {
  const out = {};
  for (const p of photos) {
    if (!p.__override) continue;
    const key = p.__folder || p.path;
    out[key] = { ...(out[key] || {}), ...p.__override };
  }
  return out;
}
