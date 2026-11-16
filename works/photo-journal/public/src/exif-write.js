/**
 * 最小 EXIF(APP1) 写入器 —— 零依赖，纯 Node
 *
 * 用途：
 *   1. 生成演示照片时写上真实的拍摄参数（DateTimeOriginal / 相机 / 光圈 / GPS…）
 *   2. 系统里没有 exiftool 时，可以给缺少 EXIF 的导出图补写拍摄时间与坐标
 *
 *   import { writeExifApp1 } from '../src/exif-write.js';
 *   const jpeg = writeExifApp1(buffer, {
 *     make: 'SONY', model: 'ILCE-7M4',
 *     dateTimeOriginal: new Date('2024-10-03T17:42:00'),
 *     fNumber: 2.8, exposureTime: 1 / 250, iso: 400, focalLength: 35,
 *     gps: { lat: 30.2442, lng: 120.139 },
 *   });
 *
 * 仅支持 JPEG（写入 APP1 段）；PNG / HEIC 不适用。
 */

const T = { BYTE: 1, ASCII: 2, SHORT: 3, LONG: 4, RATIONAL: 5, UNDEFINED: 7, SLONG: 9, SRATIONAL: 10 };
const TYPE_SIZE = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 };

const gcd = (a, b) => (b ? gcd(b, a % b) : a);

/* ---- 用 DataView 读写，避免依赖 Node 的 Buffer（浏览器里没有 Buffer） ---- */

function u16be(buf, off) { return new DataView(buf.buffer, buf.byteOffset).getUint16(off, false); }

/** 分配一段零填充字节 */
const alloc = (n) => new Uint8Array(n);

/** 拼接若干 Uint8Array */
function concat(chunks) {
  const total = chunks.reduce((s, c) => s + c.length, 0);
  const out = alloc(total);
  let p = 0;
  for (const c of chunks) { out.set(c, p); p += c.length; }
  return out;
}

/** 数值 → [分子, 分母] */
function toRational(value, signed = false) {
  if (value == null || Number.isNaN(value)) return null;
  if (signed) {
    const sign = value < 0 ? -1 : 1;
    const abs = Math.abs(value);
    const den = 1000;
    const num = Math.round(abs * den);
    const g = gcd(num, den) || 1;
    return [sign * (num / g), den / g];
  }
  if (Number.isInteger(value)) return [value, 1];
  if (value > 0 && value < 1) {
    const den = Math.round(1 / value);
    if (den > 0 && Math.abs(1 / den - value) / value < 1e-5) return [1, den];
  }
  const den = 10000;
  const num = Math.round(value * den);
  const g = gcd(num, den) || 1;
  return [num / g, den / g];
}

function ascii(tag, str) { return { tag, type: T.ASCII, values: String(str) }; }
function short(tag, v) { return { tag, type: T.SHORT, values: v }; }
function long(tag, v) { return { tag, type: T.LONG, values: v }; }
function rational(tag, v) { const [n, d] = toRational(v); return { tag, type: T.RATIONAL, values: [n, d] }; }
function srational(tag, v) { const [n, d] = toRational(v, true); return { tag, type: T.SRATIONAL, values: [n, d] }; }

/** 每个条目编码后的字节内容与元素个数 */
function encodeEntry(e) {
  if (e.type === T.ASCII) {
    const str = String(e.values);
    const buf = alloc(str.length + 1);
    for (let i = 0; i < str.length; i++) buf[i] = str.charCodeAt(i) & 0xff;
    return { buf, count: buf.length };
  }
  const arr = Array.isArray(e.values) ? e.values : [e.values];
  const size = TYPE_SIZE[e.type];
  const buf = alloc(arr.length * size);
  const dv = new DataView(buf.buffer);
  let o = 0;
  for (const v of arr) {
    if (e.type === T.SHORT) { dv.setUint16(o, v & 0xffff, true); o += 2; }
    else if (e.type === T.LONG) { dv.setUint32(o, v >>> 0, true); o += 4; }
    else if (e.type === T.SLONG) { dv.setInt32(o, v, true); o += 4; }
    else if (e.type === T.RATIONAL) { dv.setUint32(o, v, true); o += 4; }
    else if (e.type === T.SRATIONAL) { dv.setInt32(o, v, true); o += 4; }
    else { dv.setUint8(o, v & 0xff); o += 1; }
  }
  return { buf, count: arr.length / ((e.type === T.RATIONAL || e.type === T.SRATIONAL) ? 2 : 1) };
}

/**
 * 构建一个 IFD：目录与外置数据区分开返回，避免偏移歧义
 * @param {Array} entries
 * @param {number} dataBase 外置数据区的绝对起始偏移
 * @returns {{ dir: Uint8Array, data: Uint8Array }}
 */
function buildIFD(entries, dataBase) {
  const sorted = [...entries].sort((a, b) => a.tag - b.tag);
  const dirSize = 2 + sorted.length * 12 + 4;
  const dir = alloc(dirSize);
  const dv = new DataView(dir.buffer);
  dv.setUint16(0, sorted.length, true);

  const dataChunks = [];
  let dataCursor = dataBase;

  sorted.forEach((e, i) => {
    const off = 2 + i * 12;
    const { buf, count } = encodeEntry(e);
    dv.setUint16(off, e.tag, true);
    dv.setUint16(off + 2, e.type, true);
    dv.setUint32(off + 4, count, true);

    if (buf.length <= 4) {
      dir.set(buf, off + 8);
      return;
    }
    if (dataCursor % 2) { dataChunks.push(alloc(1)); dataCursor += 1; }
    dv.setUint32(off + 8, dataCursor, true);
    dataChunks.push(buf);
    dataCursor += buf.length;
  });
  dv.setUint32(dirSize - 4, 0, true);
  return { dir, data: concat(dataChunks) };
}

const pad2 = (n) => String(n).padStart(2, '0');

function exifDateTime(d) {
  return `${d.getFullYear()}:${pad2(d.getMonth() + 1)}:${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/** 十进制度 → [度, 分, 秒] 有理数序列 */
function dms(value) {
  const abs = Math.abs(value);
  let deg = Math.floor(abs);
  const minFloat = (abs - deg) * 60;
  let min = Math.floor(minFloat);
  let sec = Math.round((minFloat - min) * 60 * 1000);
  if (sec === 60000) { sec = 0; min += 1; }
  if (min === 60) { min = 0; deg += 1; }
  return [deg, 1, min, 1, sec, 1000];
}

/**
 * 给 JPEG 写入 EXIF（会先移除已有的 APP1 段）
 * @param {Buffer} jpegBuffer
 * @param {object} meta
 * @returns {Buffer}
 */
export function writeExifApp1(jpegBuffer, meta = {}) {
  if (jpegBuffer[0] !== 0xff || jpegBuffer[1] !== 0xd8) throw new Error('不是 JPEG 数据');

  const ifd0 = [];
  const exifIfd = [];
  const gpsIfd = [];

  if (meta.dateTimeOriginal) {
    const s = exifDateTime(meta.dateTimeOriginal);
    ifd0.push(ascii(0x0132, s));
    exifIfd.push(ascii(0x9003, s));
    exifIfd.push(ascii(0x9004, s));
  }
  if (meta.make) ifd0.push(ascii(0x010f, meta.make));
  if (meta.model) ifd0.push(ascii(0x0110, meta.model));
  if (meta.software) ifd0.push(ascii(0x0131, meta.software));
  if (meta.artist) ifd0.push(ascii(0x013b, meta.artist));
  if (meta.copyright) ifd0.push(ascii(0x8298, meta.copyright));
  if (meta.imageDescription) ifd0.push(ascii(0x010e, meta.imageDescription));
  if (meta.orientation) ifd0.push(short(0x0112, meta.orientation));

  if (meta.exposureTime != null) exifIfd.push(rational(0x829a, meta.exposureTime));
  if (meta.fNumber != null) exifIfd.push(rational(0x829d, meta.fNumber));
  if (meta.iso != null) exifIfd.push(short(0x8827, meta.iso));
  if (meta.focalLength != null) exifIfd.push(rational(0x920a, meta.focalLength));
  if (meta.focalLength35 != null) exifIfd.push(short(0xa405, meta.focalLength35));
  if (meta.exposureProgram != null) exifIfd.push(short(0x8822, meta.exposureProgram));
  if (meta.exposureCompensation != null) exifIfd.push(srational(0x9204, meta.exposureCompensation));
  if (meta.meteringMode != null) exifIfd.push(short(0x9207, meta.meteringMode));
  if (meta.flash != null) exifIfd.push(short(0x9209, meta.flash));
  if (meta.whiteBalance != null) exifIfd.push(short(0xa403, meta.whiteBalance));
  if (meta.lensModel) exifIfd.push(ascii(0xa434, meta.lensModel));
  if (meta.lensMake) exifIfd.push(ascii(0xa433, meta.lensMake));
  if (meta.pixelXDimension != null) exifIfd.push(long(0xa002, meta.pixelXDimension));
  if (meta.pixelYDimension != null) exifIfd.push(long(0xa003, meta.pixelYDimension));

  if (meta.gps && Number.isFinite(meta.gps.lat) && Number.isFinite(meta.gps.lng)) {
    const { lat, lng, alt } = meta.gps;
    gpsIfd.push({ tag: 0x0000, type: T.BYTE, values: [2, 3, 0, 0] });
    gpsIfd.push(ascii(0x0001, lat >= 0 ? 'N' : 'S'));
    gpsIfd.push({ tag: 0x0002, type: T.RATIONAL, values: dms(lat) });
    gpsIfd.push(ascii(0x0003, lng >= 0 ? 'E' : 'W'));
    gpsIfd.push({ tag: 0x0004, type: T.RATIONAL, values: dms(lng) });
    if (Number.isFinite(alt)) {
      gpsIfd.push({ tag: 0x0005, type: T.BYTE, values: [alt < 0 ? 1 : 0] });
      gpsIfd.push(rational(0x0006, Math.abs(alt)));
    }
  }

  if (!ifd0.length && !exifIfd.length && !gpsIfd.length) return jpegBuffer;

  // 布局顺序很重要：先把指针条目加进 IFD0，再算各目录长度
  const exifPointer = exifIfd.length ? long(0x8769, 0) : null;
  const gpsPointer = gpsIfd.length ? long(0x8825, 0) : null;
  if (exifPointer) ifd0.push(exifPointer);
  if (gpsPointer) ifd0.push(gpsPointer);

  const dirSize = (n) => 2 + n * 12 + 4;
  const ifd0DirSize = dirSize(ifd0.length);
  const exifDirSize = exifIfd.length ? dirSize(exifIfd.length) : 0;
  const gpsDirSize = gpsIfd.length ? dirSize(gpsIfd.length) : 0;

  const tiffBase = 8;                                        // TIFF 头长度
  const ifd0Base = tiffBase;
  const exifBase = ifd0Base + ifd0DirSize;                   // ExifIFD 目录的绝对偏移
  const gpsBase = exifBase + exifDirSize;                    // GPS IFD 目录的绝对偏移
  const dataStart = gpsBase + gpsDirSize;                    // 外置数据区起点

  // 先探测各 IFD 的外置数据区长度（只与条目内容有关，与偏移无关）
  const empty = { dir: alloc(0), data: alloc(0) };
  const ifd0Plan = buildIFD(ifd0, 0);
  const exifPlan = exifIfd.length ? buildIFD(exifIfd, 0) : empty;
  const gpsPlan = gpsIfd.length ? buildIFD(gpsIfd, 0) : empty;

  const ifd0DataStart = dataStart;
  const exifDataStart = ifd0DataStart + ifd0Plan.data.length;
  const gpsDataStart = exifDataStart + exifPlan.data.length;

  // 回填指针（指针值不参与数据区长度计算，因此上面的长度依然有效）
  if (exifPointer) exifPointer.values = exifBase;
  if (gpsPointer) gpsPointer.values = gpsBase;

  const ifd0Built = buildIFD(ifd0, ifd0DataStart);
  const exifBuilt = exifIfd.length ? buildIFD(exifIfd, exifDataStart) : empty;
  const gpsBuilt = gpsIfd.length ? buildIFD(gpsIfd, gpsDataStart) : empty;

  const tiffHeader = alloc(8);
  const thv = new DataView(tiffHeader.buffer);
  tiffHeader[0] = 0x49; tiffHeader[1] = 0x49;   // "II"
  thv.setUint16(2, 0x002a, true);
  thv.setUint32(4, ifd0Base, true);

  const payload = concat([
    new Uint8Array([0x45, 0x78, 0x69, 0x66, 0x00, 0x00]), // "Exif\0\0"
    tiffHeader,
    ifd0Built.dir,
    exifBuilt.dir,
    gpsBuilt.dir,
    ifd0Built.data,
    exifBuilt.data,
    gpsBuilt.data,
  ]);

  if (payload.length + 2 > 0xffff) throw new Error('EXIF 段超过 64KB 上限');

  const app1 = alloc(4 + payload.length);
  const av = new DataView(app1.buffer);
  av.setUint16(0, 0xffe1, false);
  av.setUint16(2, payload.length + 2, false);
  app1.set(payload, 4);

  const body = stripApp1(jpegBuffer.subarray(2));
  return concat([jpegBuffer.subarray(0, 2), app1, body]);
}

/** 保留 SOI 之后除 APP1 以外的所有段与压缩数据 */
function stripApp1(buf) {
  const chunks = [];
  let i = 0;
  while (i + 4 <= buf.length) {
    if (buf[i] !== 0xff) break;
    const marker = buf[i + 1];
    if (marker === 0xda) break;       // SOS：其后为压缩数据
    if (marker === 0xd8 || marker === 0xff) { i += 2; continue; }
    if (marker >= 0xd0 && marker <= 0xd7) { i += 2; continue; } // RSTn
    const len = u16be(buf, i + 2);
    if (marker !== 0xe1) chunks.push(buf.subarray(i, i + 2 + len));
    i += 2 + len;
  }
  chunks.push(buf.subarray(i));
  return concat(chunks);
}
