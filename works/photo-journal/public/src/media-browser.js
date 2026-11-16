/**
 * 缩略图 / 预览图生成（浏览器端，用 Canvas）
 *
 * 浏览器里拖入文件夹时使用，产出与 media-node.js 完全一致的 WebP，
 * 因此网页导入和命令行导入得到的站点文件可以互换。
 */

export { humanSize } from './media-shared.js';
import { makeSignature, histogramFromPixels } from './dup.js';

const BROWSER_DECODABLE = new Set(['.jpg', '.jpeg', '.jpe', '.png', '.webp', '.avif', '.gif', '.bmp']);

const extOf = (name) => {
  const dot = String(name).lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot).toLowerCase();
};

/**
 * 感知指纹（结构 + 颜色）—— 浏览器端实现
 *
 * 与 media-node.js 的 perceptualHash 算法一致：
 *   结构 = 9×8 灰度相邻比较（64 位）
 *   颜色 = 4×4×4 直方图（12 个十六进制字符）
 * 两者一起用，既能认出"同一张的不同版本"，又不会把无关的渐变图误判为重复。
 */
export async function perceptualHashInBrowser(blob) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' });
  } catch {
    return null;
  }
  try {
    // 先逐级缩小到接近目标尺寸，再一次性画到目标尺寸，避免直接缩产生锯齿噪声
    let w = bitmap.width;
    let h = bitmap.height;
    let src = bitmap;
    while (w > 32 && h > 32) {
      w = Math.max(9, Math.round(w / 2));
      h = Math.max(8, Math.round(h / 2));
      const c = newCanvas(w, h);
      const cx = c.getContext('2d');
      cx.imageSmoothingQuality = 'high';
      cx.drawImage(src, 0, 0, w, h);
      if (src !== bitmap) src.close?.();
      src = c;
    }

    const small = newCanvas(9, 8);
    const sx = small.getContext('2d');
    sx.imageSmoothingQuality = 'high';
    sx.drawImage(src, 0, 0, 9, 8);
    if (src !== bitmap) src.close?.();

    const { data } = sx.getImageData(0, 0, 9, 8);
    let bits = 0n;
    let k = 0n;
    for (let y = 0; y < 8; y++) {
      for (let x = 0; x < 8; x++) {
        const i = (y * 9 + x) * 4;
        const j = (y * 9 + x + 1) * 4;
        // 用感知亮度（人眼对绿色更敏感）
        const left = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
        const right = 0.299 * data[j] + 0.587 * data[j + 1] + 0.114 * data[j + 2];
        if (left > right) bits |= (1n << k);
        k++;
      }
    }

    // 颜色分布
    const colorCanvas = newCanvas(64, 64);
    const cx = colorCanvas.getContext('2d');
    cx.imageSmoothingQuality = 'high';
    cx.drawImage(bitmap, 0, 0, 64, 64);
    const px = cx.getImageData(0, 0, 64, 64).data;
    const hist = histogramFromPixels(px, 4, 1, 64);

    return makeSignature(bits.toString(16).padStart(16, '0'), hist);
  } catch {
    return null;
  } finally {
    bitmap.close?.();
  }
}

export function browserCanDecode(fileName) {
  return BROWSER_DECODABLE.has(extOf(fileName));
}

function canvasToBlob(canvas, quality) {
  return new Promise((resolve) => {
    if (typeof canvas.convertToBlob === 'function') {
      canvas.convertToBlob({ type: 'image/webp', quality }).then(resolve).catch(() => resolve(null));
      return;
    }
    canvas.toBlob((b) => resolve(b), 'image/webp', quality);
  });
}

function newCanvas(w, h) {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(w, h);
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  return c;
}

/**
 * 在浏览器里把一张图（File/Blob）转成缩略图 + 预览图 + 主色调
 * @param {Blob} blob
 * @param {{thumbWidth?:number, previewWidth?:number}} [opts]
 */
export async function makeMediaInBrowser(blob, { thumbWidth = 400, previewWidth = 1600 } = {}) {
  let bitmap;
  try {
    // imageOrientation: 'from-image' 会按 EXIF 方向摆正
    bitmap = await createImageBitmap(blob, { imageOrientation: 'from-image' });
  } catch {
    return { thumb: null, preview: null, color: null, size: null };
  }

  const out = { thumb: null, preview: null, color: null, size: { width: bitmap.width, height: bitmap.height } };

  try {
    const render = async (maxWidth, quality) => {
      const scale = Math.min(1, maxWidth / bitmap.width);
      const w = Math.max(1, Math.round(bitmap.width * scale));
      const h = Math.max(1, Math.round(bitmap.height * scale));
      const canvas = newCanvas(w, h);
      const ctx = canvas.getContext('2d');
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(bitmap, 0, 0, w, h);
      return canvasToBlob(canvas, quality);
    };

    out.thumb = await render(thumbWidth, 0.78);
    out.preview = await render(previewWidth, 0.82);

    // 主色调
    const s = 16;
    const c = newCanvas(s, s);
    const cx = c.getContext('2d');
    cx.drawImage(bitmap, 0, 0, s, s);
    const { data } = cx.getImageData(0, 0, s, s);
    let r = 0; let g = 0; let b = 0; let n = 0;
    for (let i = 0; i < data.length; i += 4) { r += data[i]; g += data[i + 1]; b += data[i + 2]; n++; }
    if (n) out.color = `#${[r / n, g / n, b / n].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;
  } catch {
    /* 生成失败就用原图兜底 */
  } finally {
    bitmap.close?.();
  }
  return out;
}
