/**
 * 缩略图 / 预览图生成（Node 端，用 sharp）
 *
 *   media/thumbs/<hash>.webp   400px  相册网格
 *   media/previews/<hash>.webp 1600px 灯箱查看
 *
 * 注意：
 *   - 用 .rotate() 按 EXIF 方向摆正，方向信息会写进输出文件本身，站点无需再处理。
 *   - 原始照片不会被修改；raw 格式（dng/cr2/nef…）sharp 可能读不了，
 *     这时会自动回退为"直接用原图"，站点依然可用（只是加载慢些）。
 *   - 浏览器端对应实现见 media-browser.js（网页里拖文件夹导入时使用）。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { makeSignature, histogramFromPixels } from './dup.js';

export { humanSize } from './media-shared.js';

let sharpModule;
let sharpLoadError = null;

export async function loadSharp() {
  if (sharpModule !== undefined) return sharpModule;
  try {
    const mod = await import('sharp');
    sharpModule = mod.default || mod;
  } catch (err) {
    sharpLoadError = err;
    sharpModule = null;
  }
  return sharpModule;
}

export function sharpError() {
  return sharpLoadError;
}

const RAW_EXT = new Set(['.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf', '.orf', '.rw2']);

async function exists(p) {
  try { await fs.access(p); return true; } catch { return false; }
}

/**
 * @param {object} opts
 * @param {string} opts.srcPath      原图绝对路径
 * @param {string} opts.mediaRoot    public/media 绝对路径
 * @param {string} opts.hash         内容哈希（缓存键）
 * @param {number} opts.previewWidth
 * @param {number} opts.thumbWidth
 * @param {boolean} opts.force       强制重新生成
 */
export async function makeMedia({ srcPath, mediaRoot, hash, previewWidth = 1600, thumbWidth = 400, force = false }) {
  const sharp = await loadSharp();
  const isRaw = RAW_EXT.has(path.extname(srcPath).toLowerCase());
  if (!sharp) return { skipped: 'sharp-unavailable', isRaw };

  const thumbDir = path.join(mediaRoot, 'thumbs');
  const previewDir = path.join(mediaRoot, 'previews');
  await fs.mkdir(thumbDir, { recursive: true });
  await fs.mkdir(previewDir, { recursive: true });

  const thumbPath = path.join(thumbDir, `${hash}.webp`);
  const previewPath = path.join(previewDir, `${hash}.webp`);
  const thumbExists = !force && (await exists(thumbPath));
  const previewExists = !force && (await exists(previewPath));

  const result = { thumb: null, preview: null, color: null, size: null, isRaw };

  try {
    if (!thumbExists || !previewExists || force) {
      const base = sharp(srcPath, { failOn: 'none', unlimited: false }).rotate();
      const meta = await base.metadata();

      if (!thumbExists || force) {
        await sharp(srcPath, { failOn: 'none' }).rotate()
          .resize({ width: thumbWidth, withoutEnlargement: true })
          .webp({ quality: 78, effort: 4 })
          .toFile(thumbPath);
      }
      if (!previewExists || force) {
        await sharp(srcPath, { failOn: 'none' }).rotate()
          .resize({ width: previewWidth, withoutEnlargement: true })
          .webp({ quality: 82, effort: 4 })
          .toFile(previewPath);
      }
      // 主色调（用于加载前的占位背景）
      try {
        const stats = await sharp(srcPath, { failOn: 'none' }).rotate()
          .resize({ width: 24, height: 24, fit: 'inside' })
          .removeAlpha()
          .raw()
          .toBuffer({ resolveWithObject: true });
        const { data, info } = stats;
        let r = 0; let g = 0; let b = 0; let n = 0;
        for (let i = 0; i + info.channels - 1 < data.length; i += info.channels) {
          r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
        }
        if (n) result.color = `#${[r / n, g / n, b / n].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;
      } catch { /* 主色调失败无所谓 */ }

      const w = meta.autoOrient?.width || meta.width;
      const h = meta.autoOrient?.height || meta.height;
      if (w && h) result.size = { width: w, height: h };
    }

    // 生成（或已存在）后统一确认路径，避免"已存在但没赋值"
    if (await exists(thumbPath)) result.thumb = `media/thumbs/${hash}.webp`;
    if (await exists(previewPath)) result.preview = `media/previews/${hash}.webp`;
  } catch (err) {
    return { ...result, error: String(err && err.message ? err.message : err) };
  }

  return result;
}

/**
 * 感知指纹（结构 + 颜色），存成 28 个十六进制字符
 *
 * 结构：缩到 9×8 灰度，逐行比较相邻像素明暗 → 64 位
 * 颜色：4×4×4 直方图 → 12 个十六进制字符
 *
 * 两者一起用才能既认出"同一张的不同版本"，又不把"两张都像渐变"的无关照片误判为重复。
 * 浏览器端等价实现见 media-browser.js。
 */
export async function perceptualHash(srcPath) {
  const sharp = await loadSharp();
  if (!sharp) return null;
  try {
    const grey = await sharp(srcPath, { failOn: 'none' })
      .rotate()
      .greyscale()
      .resize(9, 8, { fit: 'fill' })
      .raw()
      .toBuffer();
    let bits = 0n;
    let k = 0n;
    for (let y = 0; y < 8; y++) {
      for (let x = 0; x < 8; x++) {
        if (grey[y * 9 + x] > grey[y * 9 + x + 1]) bits |= (1n << k);
        k++;
      }
    }

    const { data } = await sharp(srcPath, { failOn: 'none' })
      .rotate()
      .resize(64, 64, { fit: 'fill' })
      .removeAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const hist = histogramFromPixels(data, 3, 1, 64);

    return makeSignature(bits.toString(16).padStart(16, '0'), hist);
  } catch {
    return null;
  }
}

/** 目录大小统计，用于汇报仓库体积 */export async function dirSize(dir, { ext = null } = {}) {
  let total = 0;
  let count = 0;
  async function walk(d) {
    let entries;
    try { entries = await fs.readdir(d, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) await walk(p);
      else {
        if (ext && !e.name.toLowerCase().endsWith(ext)) continue;
        try { const st = await fs.stat(p); total += st.size; count++; } catch { /* ignore */ }
      }
    }
  }
  await walk(dir);
  return { bytes: total, count };
}
