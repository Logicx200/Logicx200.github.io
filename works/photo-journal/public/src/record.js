/**
 * 把「归档路径解析结果 + EXIF 结果 + 文件信息」合并成一条照片记录。
 * 同时负责生成稳定的 id、slug 与说明文字（caption）。
 */

import { parseArchivePath, normalizeText, extractDate, toISODate } from './parse.js';

/** 文件名 → URL 安全的 slug（保留中文，便于阅读） */
export function slugify(input, maxLen = 48) {
  const s = normalizeText(input)
    .replace(/[\\/:*?"<>|#%&{}$!'@+`=~^\[\]]/g, '-')
    .replace(/[^\u4e00-\u9fa5A-Za-z0-9._-]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^[-._]+|[-._]+$/g, '');
  return (s || 'file').slice(0, maxLen);
}

/** 稳定的短 id：FNV-1a 32bit，用在 DOM 与 URL 里 */
export function shortHash(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

/** 去掉日期/地名后剩下的文本，作为"事件说明" */
export function folderCaption(segment) {
  if (!segment) return null;
  const s = normalizeText(segment)
    .replace(/(?<!\d)(?:19|20)\d{2}\s*[年\-._/]\s*\d{1,2}\s*[月\-._/]\s*\d{1,2}\s*[日号]?/g, ' ')
    .replace(/(?<!\d)\d{1,2}\s*月\s*\d{1,2}\s*[日号]?/g, ' ')
    .replace(/(?<!\d)(?:19|20)\d{2}\s*年?/g, ' ')
    .replace(/[（(【\[][^）)】\]]*[）)】\]]/g, ' ')
    .replace(/[_\-–—]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return s || null;
}

/**
 * @param {object} args
 * @param {string} args.relPath  相对源目录的路径，例如 "2024年/10月3日 杭州西湖/DSC01234.JPG"
 * @param {string} args.fileName
 * @param {number} args.bytes
 * @param {object|null} args.exif   readExif 的结果
 * @param {object} args.prefs       全局偏好（overrideDate / overrideLocation）
 * @param {{thumb:string,preview:string,original:string}|null} args.media 生成的媒体路径（相对站点根）
 * @param {string|null} args.dominantColor
 * @param {{width:number,height:number}|null} args.displaySize
 * @param {string|null} args.originBase  原图的外部前缀（对象存储/CDN），如 "https://cdn.example.com/photos"
 */
export function buildRecord({ relPath, fileName, bytes, exif, prefs = {}, media = null, dominantColor = null, displaySize = null, originBase = null, phash = null }) {
  const segments = relPath.split(/[\\/]+/).slice(0, -1);
  const archive = parseArchivePath(segments, fileName, prefs);

  const exifDate = exif && exif.capturedAt ? String(exif.capturedAt).slice(0, 10) : null;
  const exifValid = exifDate && /^\d{4}-\d{2}-\d{2}$/.test(exifDate) ? exifDate : null;
  const folderFull = archive.date && /^\d{4}-\d{2}-\d{2}$/.test(archive.date) ? archive.date : null;

  let date = null;
  let dateSource = 'unknown';
  if (prefs.overrideDate) { date = prefs.overrideDate; dateSource = 'override'; }
  else if (folderFull && archive.dateConfidence >= 0.85) { date = folderFull; dateSource = 'folder'; }
  else if (exifValid) { date = exifValid; dateSource = 'exif'; }
  else if (folderFull) { date = folderFull; dateSource = 'folder'; }
  else if (archive.date) { date = archive.date; dateSource = 'folder-partial'; }

  const time = exif && exif.capturedAt && String(exif.capturedAt).includes('T')
    ? String(exif.capturedAt).slice(11, 19)
    : null;

  const location = prefs.overrideLocation || archive.location || null;
  let coords = archive.coords || null;
  if (exif && exif.gps) coords = exif.gps;                       // EXIF GPS 最可靠，优先
  else if (coords && coords.source !== 'hint') coords = coords;

  const geoHint = {
    lat: exif?.gps?.lat ?? archive.coords?.lat ?? null,
    lng: exif?.gps?.lng ?? archive.coords?.lng ?? null,
    city: exif?.iptcLocation?.city || null,
    province: exif?.iptcLocation?.province || null,
    country: exif?.iptcLocation?.country || archive.hint?.country || null,
  };

  const captionSource = segments.length ? segments[segments.length - 1] : fileName;
  const caption = exif?.description
    || folderCaption(captionSource)
    || location
    || fileName.replace(/\.[^.]+$/, '');

  const idSeed = relPath.replace(/\\/g, '/') + '|' + bytes;
  const id = shortHash(idSeed);

  const pixelW = displaySize?.width ?? exif?.pixels?.width ?? null;
  const pixelH = displaySize?.height ?? exif?.pixels?.height ?? null;

  return {
    id,
    file: fileName,
    path: relPath.replace(/\\/g, '/'),
    src: media?.original
      || (originBase ? `${String(originBase).replace(/\/+$/, '')}/${encodeURI(relPath.replace(/\\/g, '/'))}` : null),
    thumb: media?.thumb || null,
    preview: media?.preview || null,
    bytes,
    date,
    time,
    dateSource,
    dateConfidence: dateSource === 'exif' || dateSource === 'override' ? 1 : archive.dateConfidence,
    dateCandidate: archive.date,
    location,
    locationSource: archive.locationSource || (exif?.gps ? 'gps' : null),
    coords: coords ? { lat: coords.lat, lng: coords.lng, source: coords.source || 'exif' } : null,
    geoHint,
    caption,
    tags: archive.tags,
    keywords: exif?.keywords || [],
    rating: exif?.rating ?? null,
    label: exif?.label ?? null,
    camera: exif?.camera || null,
    lens: exif?.lens || null,
    software: exif?.software || null,
    editedBy: exif?.editedBy || null,
    exposure: exif?.exposure || null,
    pixel: pixelW && pixelH ? { width: pixelW, height: pixelH } : null,
    orientation: exif?.pixels?.orientation ?? 1,
    color: dominantColor,
    phash: phash || undefined,   // 感知哈希，用于重复照片检测
    exifMissing: !exif || exif.empty ? true : undefined,
  };
}

/** 供 --dry-run 打印的解析预览 */
export function explainArchive(relPath, prefs = {}) {
  const segments = relPath.split(/[\\/]+/);
  const fileName = segments.pop();
  const a = parseArchivePath(segments, fileName, prefs);
  return {
    路径: relPath,
    日期: a.date || '未识别',
    日期来源: a.dateSource || '-',
    置信度: a.dateConfidence,
    地点: a.location || '未识别',
    标签: a.tags.join('/') || '-',
    命中片段: a.dateMatched || '-',
  };
}

export { extractDate, toISODate };
