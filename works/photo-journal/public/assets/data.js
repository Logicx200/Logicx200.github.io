/**
 * 数据访问层
 *
 * 运行时读取 public/data 下由 scripts/import.mjs 生成的：
 *   index.json          站点元信息 + 年/月/地点/相机/镜头/标签聚合
 *   search.json         全量精简索引（筛选、搜索、地图都用它）
 *   photos-YYYY-MM.json 单月完整记录（点开照片时才按需加载 EXIF 明细）
 */

const BASE = 'data/';

export function encodePath(p) {
  if (!p) return '';
  return p.split('/').map(encodeURIComponent).join('/');
}

async function getJSON(url) {
  const res = await fetch(BASE + url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`无法加载 ${url}（HTTP ${res.status}）`);
  return res.json();
}

export const store = {
  index: null,
  /** @type {Array<object>} 精简索引条目 */
  photos: [],
  /** id → 完整记录 */
  detail: new Map(),
  monthCache: new Map(),

  /**
   * 加载站点索引。
   * 首次使用时 data/index.json 还不存在，此时不抛错，而是返回一个空站点，
   * 这样「导入」页仍然可用（拖文件夹进来即可从零建站）。
   */
  async load() {
    // 每次重新加载都要丢掉缓存，否则导入新照片后，灯箱仍会读到旧月份文件
    this.detail.clear();
    this.monthCache.clear();
    try {
      const [index, search] = await Promise.all([getJSON('index.json'), getJSON('search.json')]);
      this.index = index;
      this.photos = search;
      this.isEmpty = false;
      this.loadError = null;
    } catch (err) {
      this.index = {
        generatedAt: null,
        title: '我的摄影记录',
        subtitle: '',
        source: '尚未导入',
        stats: {
          photos: 0, withGps: 0, withExifDate: 0, fromFolderName: 0, fromMtime: 0,
          withLocation: 0, lowConfidence: 0, firstDate: null, lastDate: null, bytes: 0,
        },
        years: {}, months: [], locations: [], cameras: [], lenses: [], editors: [], tags: [],
      };
      this.photos = [];
      this.isEmpty = true;
      this.loadError = err;
    }
    return this;
  },

  monthOf(id) {
    const p = this.photos.find((x) => x.i === id);
    if (!p || !p.d) return null;
    return /^\d{4}-\d{2}/.test(p.d) ? p.d.slice(0, 7) : 'unknown';
  },

  async loadMonth(key) {
    if (key === 'unknown') return [];
    if (!this.monthCache.has(key)) {
      const p = getJSON(`photos-${key}.json`)
        .then((d) => {
          for (const rec of d.photos) this.detail.set(rec.id, rec);
          return d.photos;
        })
        .catch(() => []);
      this.monthCache.set(key, p);
    }
    return this.monthCache.get(key);
  },

  async getDetail(id) {
    if (this.detail.has(id)) return this.detail.get(id);
    const key = this.monthOf(id);
    if (key) await this.loadMonth(key);
    return this.detail.get(id) || null;
  },
};

/* ------------------------------------------------------------------ */
/* 展示格式化                                                          */
/* ------------------------------------------------------------------ */

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

export function formatDate(date) {
  if (!date) return '日期未知';
  if (/^\d{2}-\d{2}$/.test(date)) return `${Number(date.slice(0, 2))} 月 ${Number(date.slice(3))} 日（年份待确认）`;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!m) return date;
  const d = new Date(`${date}T00:00:00`);
  return `${m[1]} 年 ${Number(m[2])} 月 ${Number(m[3])} 日 ${WEEKDAYS[d.getDay()]}`;
}

export function formatDateShort(date) {
  if (!date) return '—';
  if (/^\d{2}-\d{2}$/.test(date)) return date;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  return m ? `${m[1]}.${m[2]}.${m[3]}` : date;
}

export function dateSourceLabel(src) {
  return {
    exif: 'EXIF 拍摄时间',
    folder: '文件夹名',
    'folder-partial': '文件夹名（仅月日）',
    filename: '文件名',
    override: '手动指定',
    mtime: '文件修改时间（兜底）',
    unknown: '未识别',
  }[src] || src || '未知';
}

export function exposureSummary(p) {
  const bits = [];
  if (p.a) bits.push(p.a);
  if (p.s) bits.push(p.s);
  if (p.o) bits.push(`ISO ${p.o}`);
  if (p.f) bits.push(p.f);
  return bits.join(' · ');
}

export function humanBytes(bytes) {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/** 把精简条目补成详情面板可用的形状（详情未加载前的占位） */
export function detailFromSummary(p) {
  return {
    id: p.i,
    date: p.d || null,
    time: p.t || null,
    location: p.l || null,
    coords: p.g ? { lat: p.g[0], lng: p.g[1], source: 'exif' } : null,
    camera: p.c ? { make: null, model: p.c } : null,
    lens: p.e || null,
    caption: p.x || null,
    tags: p.k || [],
    rating: p.r ?? null,
    exposure: { aperture: p.a || null, shutter: p.s || null, iso: p.o || null, focal: p.f || null },
    thumb: p.th || null,
    preview: null,
    src: null,
    bytes: null,
    pixel: null,
    software: null,
    editedBy: null,
    keywords: [],
    color: p.cl || null,
    aspect: p.aspect || null,
    dateSource: p.ds || null,
  };
}

/** 图片地址解析：thumb=网格缩略图，full=灯箱大图 */
export function imageSrc(rec, kind = 'auto') {
  if (!rec) return '';
  // 只有真的长得像路径的才算（"folder"/"exif" 这类是日期来源标签，不是图片）
  const usable = (v) => (typeof v === 'string' && (v.includes('/') || /\.(jpe?g|png|webp|avif|heic|gif|bmp)$/i.test(v)) ? v : '');
  const thumb = usable(rec.thumb) || usable(rec.th);
  const preview = usable(rec.preview);
  const src = usable(rec.src);
  if (kind === 'thumb') return encodePath(thumb || preview || src);
  if (kind === 'full') return encodePath(preview || src || thumb);
  return encodePath(preview || thumb || src);
}

export function downloadSrc(rec) {
  return encodePath((rec && rec.src) || '');
}

/**
 * 把详情形状的记录"压扁"成精简形状，
 * 让灯箱不用同时兼容两种字段命名。
 */
export function summaryFromDetail(rec) {
  return {
    i: rec.id,
    d: rec.date || null,
    t: rec.time || null,
    l: rec.location || null,
    g: rec.coords ? [rec.coords.lat, rec.coords.lng] : null,
    c: rec.camera ? [rec.camera.make, rec.camera.model].filter(Boolean).join(' ') : null,
    e: rec.lens || null,
    s: rec.exposure?.shutter || null,
    a: rec.exposure?.aperture || null,
    o: rec.exposure?.iso ?? null,
    f: rec.exposure?.focal || null,
    k: rec.tags || null,
    x: rec.caption || null,
    th: rec.thumb || rec.preview || null,
    r: rec.rating ?? null,
    cl: rec.color || null,
    aspect: rec.aspect || (rec.pixel ? Number((rec.pixel.width / rec.pixel.height).toFixed(3)) : null),
    ds: rec.dateSource || null,
  };
}


export function coordsText(coords) {
  if (!coords) return '';
  const ns = coords.lat >= 0 ? 'N' : 'S';
  const ew = coords.lng >= 0 ? 'E' : 'W';
  return `${Math.abs(coords.lat).toFixed(5)}°${ns}, ${Math.abs(coords.lng).toFixed(5)}°${ew}`;
}
