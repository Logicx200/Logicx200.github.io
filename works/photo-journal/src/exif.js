/**
 * EXIF / XMP / IPTC 的读取结果归一化与格式化
 *
 * 这里**不依赖 exifr**，因此浏览器可以直接加载（网页里拖文件夹导入时需要）。
 * 真正调用 exifr 解析文件的代码在 exif-parse.js：
 *   - Node: 直接 import exif-parse.js
 *   - 浏览器: 由 scripts/build-vendor.mjs 打包成 public/vendor/exif-parse.js
 */

/** 需要从文件里挑出来的标签（不是这个列表里的不会被解析，速度更快） */
const PICK = [
  // 时间
  'DateTimeOriginal', 'CreateDate', 'ModifyDate', 'DateTimeDigitized', 'SubSecTimeOriginal',
  // 相机 / 镜头
  'Make', 'Model', 'LensModel', 'LensMake', 'LensInfo', 'Lens', 'LensID', 'SerialNumber', 'BodySerialNumber',
  'Software', 'CreatorTool', 'Artist', 'Copyright', 'OwnerName',
  // 曝光
  'ExposureTime', 'ShutterSpeedValue', 'FNumber', 'ApertureValue', 'ISO', 'ISOSpeedRatings',
  'RecommendedExposureIndex', 'ExposureProgram', 'ExposureCompensation', 'ExposureBiasValue',
  'MaxApertureValue', 'MeteringMode', 'Flash', 'FocalLength', 'FocalLengthIn35mmFormat', 'FocalLenIn35mmFilm',
  'WhiteBalance', 'LightSource', 'SceneCaptureType', 'DigitalZoomRatio', 'SubjectDistance',
  // 图像
  'Orientation', 'ExifImageWidth', 'ExifImageHeight', 'ImageWidth', 'ImageHeight', 'ColorSpace',
  // GPS
  'GPSLatitude', 'GPSLongitude', 'GPSLatitudeRef', 'GPSLongitudeRef', 'GPSAltitude', 'GPSAltitudeRef',
  'GPSDateStamp', 'GPSTimeStamp', 'GPSPosition', 'GPSImgDirection', 'GPSHPositioningError',
  // 描述 / 版权 / 关键词
  'ImageDescription', 'Description', 'Title', 'ObjectName', 'Caption-Abstract', 'Headline',
  'Keywords', 'Subject', 'Rating', 'Label', 'City', 'Country', 'Country-PrimaryLocationName',
  'Province-State', 'Location', 'LocationCreated',
];

const SUPPORTED_EXT = new Set([
  '.jpg', '.jpeg', '.jpe', '.png', '.tif', '.tiff', '.heic', '.heif', '.avif', '.webp', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf', '.orf', '.rw2',
]);

export function isSupportedPhoto(file) {
  const dot = file.lastIndexOf('.');
  if (dot < 0) return false;
  return SUPPORTED_EXT.has(file.slice(dot).toLowerCase());
}

export function extOf(file) {
  const dot = file.lastIndexOf('.');
  return dot < 0 ? '' : file.slice(dot).toLowerCase();
}

function toNumber(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * EXIF 的日期值 → ISO 字符串
 *
 * 注意：EXIF 里的 DateTimeOriginal 是"相机本地时间"（不带时区）。
 * 这里刻意保留墙上时间，不做 UTC 转换，否则跨时区拍摄的照片会整体偏移几小时。
 */
function toISO(v) {
  if (!v) return null;
  if (v instanceof Date) {
    if (Number.isNaN(v.getTime())) return null;
    const p = (n) => String(n).padStart(2, '0');
    return `${v.getUTCFullYear()}-${p(v.getUTCMonth() + 1)}-${p(v.getUTCDate())}`
      + `T${p(v.getUTCHours())}:${p(v.getUTCMinutes())}:${p(v.getUTCSeconds())}`;
  }
  const m = /^(\d{4})[:\-/](\d{2})[:\-/](\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(String(v));
  if (m) return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`;
  const m2 = /^(\d{4})[:\-/](\d{2})[:\-/](\d{2})/.exec(String(v));
  if (m2) return `${m2[1]}-${m2[2]}-${m2[3]}T00:00:00`;
  return null;
}

function normalizeLens(raw) {
  if (!raw) return null;
  const s = String(raw).trim();
  if (!s || /^(unknown|n\/a|-+)$/i.test(s)) return null;
  return s.replace(/\s+/g, ' ');
}

/** 快门：把 0.004 这类小数格式化为 1/250 */
export function formatShutter(exposureTime, shutterSpeedValue) {
  let t = toNumber(exposureTime);
  if (t === null && shutterSpeedValue !== undefined) {
    const apex = toNumber(shutterSpeedValue);
    if (apex !== null) t = Math.pow(2, -apex);
  }
  if (t === null || t <= 0) return null;
  if (t >= 1) return `${Number(t.toFixed(1))}s`;
  const denom = Math.round(1 / t);
  // 贴近常见档位时更友好
  const nice = [8000, 4000, 2000, 1000, 500, 250, 125, 60, 30, 15, 8, 4, 2];
  const hit = nice.find((n) => Math.abs(denom - n) / n < 0.06);
  return `1/${hit || denom}`;
}

export function formatAperture(fNumber, apertureValue) {
  let f = toNumber(fNumber);
  if (f === null && apertureValue !== undefined) {
    const apex = toNumber(apertureValue);
    if (apex !== null) f = Math.pow(Math.SQRT2, apex);
  }
  if (f === null || f <= 0) return null;
  return `f/${Number(f.toFixed(1))}`;
}

export function formatFocalLength(focal, focal35) {
  const f = toNumber(focal);
  const f35 = toNumber(focal35);
  if (f === null && f35 === null) return null;
  const base = f === null ? Math.round(f35) : Math.round(f);
  const s = `${base}mm`;
  if (f !== null && f35 !== null && Math.abs(f35 - f) > 1) return `${s} (${Math.round(f35)}mm eq.)`;
  return s;
}

const EXPOSURE_PROGRAM = {
  0: '未定义', 1: '手动', 2: '程序自动', 3: '光圈优先', 4: '快门优先',
  5: '创意模式', 6: '动作模式', 7: '人像模式', 8: '风光模式',
};

const METERING_MODE = {
  0: '未知', 1: '平均', 2: '中央重点', 3: '点测光', 4: '多点', 5: '评价测光', 6: '局部',
};

export function formatExposureProgram(v) {
  const n = toNumber(v);
  return n === null ? null : EXPOSURE_PROGRAM[n] || `模式 ${n}`;
}

export function formatMetering(v) {
  const n = toNumber(v);
  return n === null ? null : METERING_MODE[n] || `测光 ${n}`;
}

/** 度分秒数组 → 十进制度 */
function dmsToDecimal(v, ref) {
  let deg;
  if (Array.isArray(v) && v.length >= 2) {
    deg = Number(v[0]) + Number(v[1]) / 60 + Number(v[2] || 0) / 3600;
  } else {
    deg = toNumber(v);
  }
  if (deg === null) return null;
  if (ref && /^[SW]$/i.test(String(ref).trim())) deg = -Math.abs(deg);
  return deg;
}

/** 归一化 GPS：优先用 exifr 换算好的十进制度数（latitude/longitude） */
function pickGPS(out) {
  let lat = toNumber(out.latitude ?? out.GPSLatitudeDecimal);
  let lng = toNumber(out.longitude ?? out.GPSLongitudeDecimal);

  if (lat === null && out.GPSLatitude !== undefined) lat = dmsToDecimal(out.GPSLatitude, out.GPSLatitudeRef);
  if (lng === null && out.GPSLongitude !== undefined) lng = dmsToDecimal(out.GPSLongitude, out.GPSLongitudeRef);

  if ((lat === null || lng === null) && typeof out.GPSPosition === 'string') {
    const m = /^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(out.GPSPosition);
    if (m) {
      const a = Number(m[1]);
      const b = Number(m[2]);
      // GPSPosition 一般写作 "lat, lng"
      if (Math.abs(a) <= 90 && Math.abs(b) <= 180) { lat = a; lng = b; }
      else if (Math.abs(b) <= 90 && Math.abs(a) <= 180) { lat = b; lng = a; }
    }
  }
  if (lat === null || lng === null) return null;
  if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  if (lat === 0 && lng === 0) return null;
  const alt = toNumber(out.GPSAltitude);
  return {
    lat: Number(lat.toFixed(6)),
    lng: Number(lng.toFixed(6)),
    alt: alt === null ? null : Number(alt.toFixed(1)),
    source: 'exif',
  };
}

/** exifr 的解析选项：Node 与浏览器共用 */
export const EXIF_OPTIONS = {
  pick: PICK,
  gps: true,
  tiff: true,
  xmp: true,
  iptc: true,
  icc: false,
  jfif: false,
  mergeOutput: true,
  translateValues: true,
  reviveValues: true,
  sanitize: true,
};

/**
 * 把 exifr 的原始输出归一化成站点使用的结构。
 * Node（读文件路径）与浏览器（读 ArrayBuffer）都调用这一个函数，保证结果一致。
 */
export function normalizeExif(out) {
  if (!out) return { empty: true };

  const capturedAt = toISO(out.DateTimeOriginal) || toISO(out.CreateDate) || toISO(out.DateTimeDigitized);
  const software = out.Software || out.CreatorTool || null;
  const keywordsRaw = out.Keywords ?? out.Subject ?? null;
  const keywords = Array.isArray(keywordsRaw)
    ? keywordsRaw.map((k) => String(k).trim()).filter(Boolean)
    : typeof keywordsRaw === 'string'
      ? keywordsRaw.split(/[;,，、]/).map((k) => k.trim()).filter(Boolean)
      : [];

  const make = out.Make ? String(out.Make).trim() : null;
  let model = out.Model ? String(out.Model).trim() : null;
  // 部分机型 Model 已包含厂商名，避免 "Canon Canon EOS R5"
  if (make && model && model.toLowerCase().startsWith(make.toLowerCase())) model = model.slice(make.length).trim();

  const iso = toNumber(out.ISO ?? out.ISOSpeedRatings ?? out.RecommendedExposureIndex);
  const rating = toNumber(out.Rating);

  return {
    capturedAt,
    createdAt: toISO(out.CreateDate),
    modifiedAt: toISO(out.ModifyDate),
    camera: make || model ? { make, model } : null,
    lens: normalizeLens(out.LensModel || out.Lens || out.LensInfo),
    lensMake: out.LensMake ? String(out.LensMake).trim() : null,
    serial: out.SerialNumber || out.BodySerialNumber || null,
    software,
    editedBy: detectEditor(software),
    artist: out.Artist || out.OwnerName || null,
    copyright: out.Copyright || null,
    exposure: {
      shutter: formatShutter(out.ExposureTime, out.ShutterSpeedValue),
      aperture: formatAperture(out.FNumber, out.ApertureValue),
      iso: iso === null ? null : Math.round(iso),
      ev: toNumber(out.ExposureCompensation ?? out.ExposureBiasValue),
      focal: formatFocalLength(out.FocalLength, out.FocalLengthIn35mmFormat ?? out.FocalLenIn35mmFilm),
      focalMm: toNumber(out.FocalLength),
      focal35: toNumber(out.FocalLengthIn35mmFormat ?? out.FocalLenIn35mmFilm),
      program: formatExposureProgram(out.ExposureProgram),
      metering: formatMetering(out.MeteringMode),
      flash: out.Flash === undefined ? null : Boolean(out.Flash),
      whiteBalance: out.WhiteBalance === undefined ? null : (Number(out.WhiteBalance) === 0 ? '自动' : '手动'),
      digitalZoom: toNumber(out.DigitalZoomRatio),
    },
    gps: pickGPS(out),
    pixels: {
      width: toNumber(out.ExifImageWidth ?? out.ImageWidth),
      height: toNumber(out.ExifImageHeight ?? out.ImageHeight),
      orientation: toNumber(out.Orientation) ?? 1,
    },
    description: out.ImageDescription || out.Description || out['Caption-Abstract'] || out.Title || out.ObjectName || out.Headline || null,
    keywords,
    rating: rating === null ? null : Math.round(rating),
    label: out.Label || null,
    iptcLocation: {
      city: out.City || null,
      province: out['Province-State'] || null,
      country: out.Country || out['Country-PrimaryLocationName'] || null,
    },
  };
}

/**
 * Node 端便利函数：读文件路径。
 * 实现委托给 exif-parse.js，这样本文件保持"无 exifr 依赖"、浏览器可直接加载。
 */
export async function readExif(pathOrFile) {
  const mod = await import('./exif-parse.js');
  return mod.readExif(pathOrFile);
}

export { PICK as EXIF_PICK };

/** 从 Software / CreatorTool 判断后期软件 */
export function detectEditor(software) {
  if (!software) return null;
  const s = String(software);
  if (/lightroom/i.test(s)) return 'Lightroom';
  if (/photoshop|camera raw/i.test(s)) return 'Photoshop';
  if (/capture one/i.test(s)) return 'Capture One';
  if (/darktable/i.test(s)) return 'darktable';
  if (/snapseed|vsco|泼辣|picsart|美图|meitu/i.test(s)) return '手机修图';
  if (/dxo/i.test(s)) return 'DxO';
  if (/gimp/i.test(s)) return 'GIMP';
  return s.slice(0, 40);
}
