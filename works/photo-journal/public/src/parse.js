/**
 * 归档名称解析器（纯函数，Node 与浏览器通用）
 *
 * 目标：从"不甚规则"的中文文件夹 / 文件名里，尽可能可靠地推断出
 *   1) 拍摄日期（年 / 月 / 日）
 *   2) 拍摄地点（归一化地名 + 可选坐标）
 *
 * 设计原则：
 *   - 只依赖字符串，不依赖文件系统，方便单元测试与在浏览器里做"实时预览"。
 *   - 所有推断都带 source（来自层级 / 文件夹 / 文件名 / EXIF）与 confidence，
 *     方便在站点上标记"低置信度、请人工确认"。
 */

import { LOCATION_HINTS, NOISE_WORDS, CAMERA_WORDS } from './locationHints.js';

/* ------------------------------------------------------------------ */
/* 正则工具箱                                                          */
/* ------------------------------------------------------------------ */

/** 日期之后紧跟的时间，例如 " 14-30"、"T14:30:05"、"_143005" */
const TRAILING_TIME_RE =
  /(?:^|[\s_\-Tt.])([01]?\d|2[0-3])[:：.\-_]([0-5]\d)(?:[:：.\-_]([0-5]\d))?(?!\d)/;

const FULL_DATE_RES = [
  // 中文：2024年10月3日 / 2024 年 10 月 3 号（日/号可省略）
  {
    re: /(?<!\d)((?:19|20)\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?/,
    groups: 'ymd',
  },
  // 8 位纯数字：20241003 / IMG_20240105_123456
  {
    re: /(?<!\d)((?:19|20)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)/,
    groups: 'ymd',
  },
  // 分隔符：[2024-10-03] / [2024.1.5] / [2024_12_31] / [2024/7/8]
  {
    re: /(?<!\d)((?:19|20)\d{2})\s*[-._/]\s*(\d{1,2})\s*[-._/]\s*(\d{1,2})(?!\d)/,
    groups: 'ymd',
  },
];

const MONTH_DAY_RES = [
  // 10月3日 / 10月3号
  { re: /(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?/, kind: 'cn' },
  // 10-03 / 10.3 / 10_03 / 10/3
  { re: /(?<!\d)(\d{1,2})[.\-_/](\d{1,2})(?![\d])/, kind: 'sep' },
  // 1003（仅当月份合法时）
  { re: /(?<!\d)(\d{2})(\d{2})(?![\d])/, kind: 'compact' },
];

const TIME_RE = /(?<!\d)([01]?\d|2[0-3])[:：.]([0-5]\d)(?:[:：.]([0-5]\d))?(?!\d)/;

/** 归一化：去掉各种不可见字符，统一分隔符 */
export function normalizeText(input) {
  if (!input) return '';
  return String(input)
    .normalize('NFKC')
    .replace(/[\u200b-\u200f\ufeff]/g, '')
    .replace(/[，,、;；]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isValidYMD(y, m, d) {
  if (!(y >= 1900 && y <= 2100)) return false;
  if (!(m >= 1 && m <= 12)) return false;
  if (!(d >= 1 && d <= 31)) return false;
  const dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d;
}

const pad = (n) => String(n).padStart(2, '0');
/** year 为 null 时返回 MM-DD 形式的"部分日期" */
export const toISODate = (y, m, d) => (y == null ? `${pad(m)}-${pad(d)}` : `${y}-${pad(m)}-${pad(d)}`);
export const isFullDate = (s) => /^\d{4}-\d{2}-\d{2}$/.test(String(s || ''));

function timeFromText(text) {
  const t = TIME_RE.exec(text || '');
  if (!t) return null;
  const hh = Number(t[1]);
  const mm = Number(t[2]);
  const ss = t[3] === undefined ? 0 : Number(t[3]);
  if (hh > 23 || mm > 59 || ss > 59) return null;
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}`;
}

/* ------------------------------------------------------------------ */
/* 日期解析                                                            */
/* ------------------------------------------------------------------ */

/**
 * 从一段文本（文件夹名或文件名）里找日期
 * @param {string} text
 * @param {{ parentYear?: number }} [opts]
 * @returns {{date:string, year:number, month:number, day:number, yearInferred:boolean, confidence:number, matched:string, hadTime:boolean}|null}
 */
export function extractDate(text, opts = {}) {
  const s = normalizeText(text);
  if (!s) return null;
  const time = timeFromText(s);

  // 1) 完整年月日
  for (const { re } of FULL_DATE_RES) {
    re.lastIndex = 0;
    const m = re.exec(s);
    if (!m) continue;
    const y = Number(m[1]);
    const mm = Number(m[2]);
    const dd = Number(m[3]);

    if (!isValidYMD(y, mm, dd)) {
      // 命中了一个"看起来像日期"的整体，但日期非法（如 2024-02-30）
      // 视为该段文本没有可用日期，避免退化成一个错误的月日
      return null;
    }
    const tail = s.slice(m.index + m[0].length, m.index + m[0].length + 10);
    const trailing = TRAILING_TIME_RE.exec(tail);
    return {
      date: toISODate(y, mm, dd), year: y, month: mm, day: dd,
      yearInferred: false, confidence: 0.98, matched: m[0],
      hadTime: Boolean(time || trailing),
    };
  }

  // 2) 只有月日
  for (const { re, kind } of MONTH_DAY_RES) {
    const m = re.exec(s);
    if (!m) continue;
    const mm = Number(m[1]);
    const dd = Number(m[2]);
    if (mm < 1 || mm > 12) continue;
    if (kind === 'compact' && mm < 1) continue;
    if (dd < 1 || dd > 31) continue;

    if (opts.parentYear && isValidYMD(opts.parentYear, mm, dd)) {
      return {
        date: toISODate(opts.parentYear, mm, dd), year: opts.parentYear, month: mm, day: dd,
        yearInferred: true, confidence: 0.9, matched: m[0], hadTime: Boolean(time),
      };
    }
    return {
      date: toISODate(null, mm, dd), year: null, month: mm, day: dd,
      yearInferred: true, confidence: 0.6, matched: m[0], hadTime: Boolean(time), partial: true,
    };
  }

  // 3) 特殊节日（国庆 / 元旦…）—— 只作为弱提示
  const festival = matchFestival(s);
  if (festival && opts.parentYear) {
    return {
      date: toISODate(opts.parentYear, festival.month, festival.day),
      year: opts.parentYear, month: festival.month, day: festival.day,
      yearInferred: true, confidence: 0.45, matched: festival.word, hadTime: Boolean(time),
    };
  }

  return null;
}

const FESTIVALS = [
  { word: '元旦', month: 1, day: 1 },
  { word: '春节', month: 2, day: 1 },
  { word: '清明', month: 4, day: 5 },
  { word: '劳动节', month: 5, day: 1 },
  { word: '五一', month: 5, day: 1 },
  { word: '端午', month: 6, day: 1 },
  { word: '中秋', month: 9, day: 15 },
  { word: '国庆', month: 10, day: 1 },
  { word: '十一', month: 10, day: 1 },
  { word: '圣诞', month: 12, day: 25 },
];

function matchFestival(s) {
  return FESTIVALS.find((f) => s.includes(f.word)) || null;
}

/** 从一段文本里抽取所有 19xx/20xx 年份（用于给子目录推断年份） */
export function extractYears(text) {
  const s = normalizeText(text);
  const out = new Set();
  const re = /(?<!\d)((?:19|20)\d{2})(?!\d)/g;
  let m;
  while ((m = re.exec(s))) out.add(Number(m[1]));
  return [...out];
}

/* ------------------------------------------------------------------ */
/* 地点解析                                                            */
/* ------------------------------------------------------------------ */

function escapeRe(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** 去掉日期片段，避免 "10" "3" 这类数字干扰地点识别 */
function stripDateParts(text) {
  return normalizeText(text)
    .replace(/(?<![\d])(?:19|20)\d{2}\s*[年\-\/._]\s*\d{1,2}\s*[月\-\/._]\s*\d{1,2}\s*[日号]?/g, ' ')
    .replace(/(?<!\d)\d{1,2}\s*月\s*\d{1,2}\s*[日号]?/g, ' ')
    .replace(/(?<![\d])(?:19|20)\d{2}(?![\d])/g, ' ')
    .replace(/(?<!\d)\d{1,2}[.\-_/]\d{1,2}(?![\d])/g, ' ')
    .replace(TIME_RE, ' ')
    .replace(/(?<!\d)\d{2}(?![\d])/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * 从文本里识别地点
 * @param {string} text
 * @returns {{location:string|null, parts:string[], coords:{lat:number,lng:number,source:string}|null, hint:object|null, confidence:number}}
 */
export function extractLocation(text) {
  const stripped = stripDateParts(text);
  if (!stripped) return { location: null, parts: [], coords: null, hint: null, confidence: 0 };

  const lower = stripped.toLowerCase();
  const found = [];
  let best = null;

  for (const hint of LOCATION_HINTS) {
    const names = [hint.name, ...(hint.aliases || [])];
    for (const n of names) {
      if (!n) continue;
      const idx = stripped.indexOf(n) >= 0 ? stripped.indexOf(n) : lower.indexOf(n.toLowerCase());
      if (idx < 0) continue;
      const score = n.length * 10 - idx;
      found.push({ hint, matched: n, idx, score });
      if (!best || score > best.score) best = { hint, matched: n, idx, score };
      break; // 同一地点只记一次
    }
  }

  // 位置片段：优先用命中的地名（保留用户写的顺序）
  if (best) {
    const others = found
      .filter((f) => f.hint !== best.hint && f.idx > best.idx && f.idx - best.idx < 24)
      .sort((a, b) => a.idx - b.idx)
      .map((f) => f.hint.name);
    // 若同时命中"城市 + 地点"（例如 杭州 + 西湖），拼成"杭州 西湖"
    const chain = [best.hint.name, ...others.filter((n) => n !== best.hint.name)];
    const unique = [...new Set([...others.slice(0, 0), ...chain])];
    return {
      location: unique.join(' '),
      parts: unique,
      coords: { lat: best.hint.lat, lng: best.hint.lng, source: 'hint' },
      hint: best.hint,
      confidence: Math.min(0.95, 0.6 + best.matched.length * 0.06),
    };
  }

  // 未命中地名表：回退到"清洗后的剩余文本"
  const cleaned = cleanFallbackName(stripped);
  if (!cleaned) return { location: null, parts: [], coords: null, hint: null, confidence: 0 };
  return {
    location: cleaned,
    parts: cleaned.split(/[\s·]+/).filter(Boolean),
    coords: null,
    hint: null,
    confidence: 0.35,
  };
}

/**
 * 没命中地名表时的兜底：剥掉噪声词、器材词、纯数字，取最长的中文/字母片段
 */
export function cleanFallbackName(text) {
  let s = normalizeText(text);
  const noiseAll = [...NOISE_WORDS, ...CAMERA_WORDS];
  for (const w of noiseAll) {
    if (!w) continue;
    s = s.replace(new RegExp(escapeRe(w), 'gi'), ' ');
  }
  s = s
    .replace(/[（(【\[][^）)】\]]*[）)】\]]/g, ' ') // 括号内容通常是备注
    .replace(/[^\u4e00-\u9fa5A-Za-z\u3040-\u30ff\s·\-]/g, ' ')
    .replace(/\s*[-–—]+\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!s) return null;
  const tokens = s
    .split(' ')
    .filter((t) => t.length > 0 && !/^\d+$/.test(t))
    .map((t, i) => ({ t, i }));
  if (!tokens.length) return null;
  // 取最长的若干片段（最多 3 段），再按原始顺序拼回
  const picked = tokens
    .slice()
    .sort((a, b) => b.t.length - a.t.length)
    .slice(0, 3)
    .sort((a, b) => a.i - b.i)
    .map((x) => x.t);
  const joined = picked.join(' ').slice(0, 24).trim();
  return joined || null;
}

/** 从文件夹名里抽取"标签"（夜景、日出、人像…），供站点筛选 */
export function extractTags(...texts) {
  const joined = normalizeText(texts.filter(Boolean).join(' '));
  const tagWords = [
    '夜景', '日出', '日落', '星空', '银河', '星轨', '蓝调', '黄金时刻', '朝霞', '晚霞',
    '人像', '街拍', '扫街', '风光', '风景', '建筑', '人文', '纪实', '静物', '微距', '花卉',
    '动物', '鸟', '婚礼', '活动', '旅行', '旅拍', '雪景', '雨天', '雾', '云海', '秋色', '春天',
    '夏天', '冬天', '海边', '湖泊', '山脉', '城市', '庙会', '烟花', '长曝光', '延时',
  ];
  const hit = tagWords.filter((t) => joined.includes(t));
  const lensMatch = /(广角|长焦|中焦|定焦|微距|鱼眼|标头)/.exec(joined);
  if (lensMatch) hit.push(lensMatch[1]);
  return [...new Set(hit)];
}

/* ------------------------------------------------------------------ */
/* 组合：一个文件夹路径 → 拍摄信息                                      */
/* ------------------------------------------------------------------ */

/**
 * @param {string[]} segments 从根到叶的文件夹名数组（不含盘符）
 * @param {string} [filename] 文件名（不含扩展名亦可）
 * @param {{ overrideDate?:string, overrideLocation?:string }} [prefs]
 */
export function parseArchivePath(segments = [], filename = '', prefs = {}) {
  const segs = segments.map(normalizeText).filter(Boolean);
  const name = normalizeText(filename);

  // 从最深层往上找最近的可推断年份
  const years = [];
  for (let i = segs.length - 1; i >= 0; i--) {
    for (const y of extractYears(segs[i])) years.push(y);
  }
  // 优先"看起来像目录年份"的（单独一段或段首）
  const parentYear = years.length ? Math.max(...years) : undefined;

  const candidates = [];
  segs.forEach((s, i) => {
    const d = extractDate(s, { parentYear });
    if (d) {
      // 越靠近叶目录、越具体（有年）的候选优先级越高
      const depthBonus = i * 0.01;
      const specBonus = d.yearInferred ? 0 : 0.1;
      candidates.push({ ...d, source: 'folder', score: d.confidence + depthBonus + specBonus, segIndex: i, segText: s });
    }
  });
  if (name) {
    const d = extractDate(name, { parentYear });
    if (d) candidates.push({ ...d, source: 'filename', score: d.confidence + 0.06, segIndex: 99, segText: name });
  }

  candidates.sort((a, b) => b.score - a.score);
  let best = candidates[0] || null;

  if (prefs.overrideDate) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(prefs.overrideDate);
    if (m && isValidYMD(Number(m[1]), Number(m[2]), Number(m[3]))) {
      best = {
        date: prefs.overrideDate, year: Number(m[1]), month: Number(m[2]), day: Number(m[3]),
        yearInferred: false, confidence: 1, matched: '手动指定', source: 'override', hadTime: false,
      };
    }
  }

  // 地点：从叶往根拼接，取第一个有结果的（越靠近叶越具体）
  let location = { location: null, parts: [], coords: null, hint: null, confidence: 0 };
  for (let i = segs.length - 1; i >= 0; i--) {
    const r = extractLocation(segs[i]);
    if (r.location) { location = { ...r, fromSegment: segs[i] }; break; }
  }
  if (!location.location && name) {
    const r = extractLocation(name);
    if (r.location) location = { ...r, fromSegment: name };
  }
  if (prefs.overrideLocation) {
    const hinted = LOCATION_HINTS.find(
      (h) => h.name === prefs.overrideLocation || (h.aliases || []).includes(prefs.overrideLocation),
    );
    location = {
      location: prefs.overrideLocation,
      parts: [prefs.overrideLocation],
      coords: hinted ? { lat: hinted.lat, lng: hinted.lng, source: 'hint' } : null,
      hint: hinted || null,
      confidence: 1,
      fromSegment: '手动指定',
    };
  }

  const allSegs = [...segs, name].filter(Boolean);
  return {
    date: best ? best.date : null,
    year: best ? best.year : null,
    month: best ? best.month : null,
    day: best ? best.day : null,
    dateSource: best ? best.source : null,
    dateConfidence: best ? Number(best.confidence.toFixed(2)) : 0,
    yearInferred: best ? Boolean(best.yearInferred) : false,
    partialDate: best ? Boolean(best.partial) : false,
    dateMatched: best ? best.matched : null,
    timeHint: best && best.hadTime ? timeFromText(normalizeText(best.segText || '')) : null,
    location: location.location,
    locationParts: location.parts,
    coords: location.coords,
    locationSource: location.fromSegment || null,
    locationConfidence: Number((location.confidence || 0).toFixed(2)),
    tags: extractTags(...allSegs),
    rawSegments: segs,
  };
}

/** 供站点"实时预览"使用：把用户输入的一整条路径字符串切开解析 */
export function parsePathString(pathStr, prefs = {}) {
  const parts = String(pathStr || '')
    .split(/[\\/]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    // 去掉盘符与常见顶层归档名
    .filter((s) => !/^[A-Za-z]:$/.test(s));
  const last = parts[parts.length - 1] || '';
  const isFile = /\.[A-Za-z0-9]{2,5}$/.test(last);
  const segs = isFile ? parts.slice(0, -1) : parts;
  const filename = isFile ? last : '';
  return parseArchivePath(segs, filename, prefs);
}
