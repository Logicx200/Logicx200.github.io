/**
 * exifr 解析入口（只有这个文件依赖 exifr）
 *
 * 拆出来的原因：Node 端可以直接 `import exifr from 'exifr'`，
 * 但浏览器不认识裸模块名，需要先用 esbuild 打包成 public/vendor/exifr-bundle.js。
 * 其余格式化/归一化逻辑放在 exif.js，浏览器可直接加载。
 *
 * Node 端：`node scripts/build-vendor.mjs` 会重新生成浏览器用的 bundle。
 */

import exifr from 'exifr';
import { EXIF_OPTIONS, normalizeExif } from './exif.js';

export { EXIF_OPTIONS, normalizeExif };

/** 读文件路径（Node） */
export async function readExif(pathOrFile) {
  let out;
  try {
    out = await exifr.parse(pathOrFile, EXIF_OPTIONS);
  } catch (err) {
    return { error: String(err && err.message ? err.message : err), empty: true };
  }
  return normalizeExif(out);
}

/** 读 ArrayBuffer / Uint8Array / Blob（浏览器） */
export async function readExifFromBuffer(buffer) {
  let out;
  try {
    out = await exifr.parse(buffer, EXIF_OPTIONS);
  } catch (err) {
    return { error: String(err && err.message ? err.message : err), empty: true };
  }
  return normalizeExif(out);
}

/** 只取 GPS 坐标的快捷方法 */
export async function readGps(pathOrBuffer) {
  try {
    const g = await exifr.gps(pathOrBuffer);
    if (!g || !Number.isFinite(g.latitude) || !Number.isFinite(g.longitude)) return null;
    return { lat: Number(g.latitude.toFixed(6)), lng: Number(g.longitude.toFixed(6)), alt: null, source: 'exif' };
  } catch {
    return null;
  }
}
