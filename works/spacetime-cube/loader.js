// 把一堆照片文件变成一块可以逐帧上传的 3D 纹理数据。
//
// 数据布局对齐 THREE.Data3DTexture(DataTexture3D) 的期望：
//   offset = (z * height + y) * width + x
// 我们让纹理坐标 (u, v, w) 分别对应：
//   u -> 画面横向 x        v -> 时间轴 y（v=0 是第一帧）      w -> 画面纵向 z
// 于是体素 (x, z) 上的第 y 帧颜色 = data[(z * N + y) * W + x]。

const MAX_LONG_EDGE = 1536;  // 单帧长边上限（只降不升；原图更小就用原尺寸）
const VOXEL_BUDGET  = 400e6; // 整块 3D 纹理的体素总量上限（约 1.6 GB 显存）
const MIN_EDGE      = 24;
const MAX_FRAMES    = 512;

export const MAX_DEPTH = MAX_FRAMES;

export async function decodeBitmap(file, maxEdge = 0) {
  let bmp;
  if (typeof createImageBitmap === 'function') {
    try {
      bmp = await createImageBitmap(file, maxEdge ? { resizeWidth: maxEdge, resizeQuality: 'high' } : undefined);
    } catch (e) {
      bmp = await createImageBitmap(file);
    }
  } else {
    bmp = await loadViaImg(file);
  }
  return bmp;
}

function loadViaImg(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片解码失败')); };
    img.src = url;
  });
}

export function naturalCompare(a, b) {
  return String(a).localeCompare(String(b), 'zh-Hans-CN', { numeric: true, sensitivity: 'base' });
}

/**
 * @param {File[]} files
 * @param {{ sort?: 'name'|'time', threshold?: number, onProgress?: (p:{phase:string,done:number,total:number})=>void, signal?: {cancelled:boolean} }} opts
 */
export async function loadSequence(files, opts = {}) {
  const {
    sort = 'name', threshold = 0, graded = true,
    onProgress = () => {}, signal = null
  } = opts;

  const list = Array.from(files).filter(f => /^image\//.test(f.type) || /\.(jpe?g|png|webp|bmp|gif|avif)$/i.test(f.name));
  if (!list.length) throw new Error('没有找到可用的图片文件（支持 JPG / PNG / WebP / BMP / GIF）');

  if (sort === 'time') {
    list.sort((a, b) => (a.lastModified - b.lastModified) || naturalCompare(a.name, b.name));
  } else {
    list.sort((a, b) => naturalCompare(a.name, b.name) || (a.lastModified - b.lastModified));
  }

  if (list.length > MAX_FRAMES) {
    // 等间隔抽稀，保证时间跨度完整
    const step = list.length / MAX_FRAMES;
    const kept = [];
    for (let i = 0; i < MAX_FRAMES; i++) kept.push(list[Math.floor(i * step)]);
    list.length = 0;
    list.push(...kept);
  }

  // --- 第一遍：量出原始尺寸，定下统一的目标分辨率 ---
  onProgress({ phase: 'measure', done: 0, total: list.length });
  const first = await decodeBitmap(list[0]);
  const aspect = (first.width || 1) / (first.height || 1);
  if (typeof first.close === 'function') first.close();
  else if (first.src) URL.revokeObjectURL(first.src);

  const geo = planGeometry(aspect, list.length);
  const { width: W, height: H, depth: D } = geo;

  // --- 第二遍：逐帧解码 → 降采样 → 阈值化 → 写入 3D 数据 ---
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) throw new Error('无法创建 2D 画布上下文');
  ctx.clearRect(0, 0, W, H);

  const data = new Uint8Array(W * H * D * 4);
  const sliceLen = W * H * 4;

  const CHUNK = 4;
  for (let i = 0; i < list.length; i++) {
    if (signal && signal.cancelled) throw new Error('已取消');

    let src;
    try {
      src = await decodeBitmap(list[i], MAX_LONG_EDGE);
    } catch (e) {
      // 单张坏图不该毁掉整个序列，留一帧空白
      continue;
    }

    ctx.clearRect(0, 0, W, H);
    ctx.drawImage(src, 0, 0, W, H);
    if (typeof src.close === 'function') src.close();

    const img = ctx.getImageData(0, 0, W, H);

    // 纹理坐标 v 对应时间：第 i 帧落在体数据的 y = i 那一层
    applyAlpha(img.data, data, i, W, H, D, threshold);

    if (i % CHUNK === CHUNK - 1 || i === list.length - 1) {
      onProgress({ phase: 'decode', done: i + 1, total: list.length });
      await nextTick();
    }
  }

  // 全部帧都在了，收尾
  onProgress({ phase: 'grade', done: list.length, total: list.length });
  await nextTick();
  return {
    data, width: W, height: H, depth: D,
    aspect, frames: list.map(f => f.name),
    stride: sliceLen
  };
}

/**
 * 求目标分辨率：保持长宽比，遵守长边上限与体素总量预算。
 * 注意 v（时间）是中间维度，纹理每个 z 平面含 N 帧，所以体素数是 W*H*D。
 */
export function planGeometry(aspect, n) {
  let W = aspect >= 1 ? MAX_LONG_EDGE : Math.round(MAX_LONG_EDGE * aspect);
  let H = aspect >= 1 ? Math.round(MAX_LONG_EDGE / aspect) : MAX_LONG_EDGE;
  W = Math.max(MIN_EDGE, W);
  H = Math.max(MIN_EDGE, H);

  let D = Math.min(n, MAX_FRAMES);

  const total = W * H * D;
  if (total > VOXEL_BUDGET) {
    const k = Math.cbrt(VOXEL_BUDGET / total);
    W = Math.max(MIN_EDGE, Math.floor(W * k));
    H = Math.max(MIN_EDGE, Math.floor(H * k));
  }
  return { width: W, height: H, depth: D };
}

/**
 * 把一帧的 RGBA 像素写进体数据的第 y 帧。
 *
 * alpha 存的是「亮度」本身（0~255），它是两件事的共同来源：
 *   1. 选定帧的不透明度 —— 亮的地方实心，暗的地方透明（背景自然不遮挡）；
 *   2. 轨迹权重 —— 由着色器用相邻帧的亮度差（时间梯度）现算。
 * 把亮度存下来而不是把梯度烘进去，是因为选定帧必须用它自己的内容，
 * 而不是「它变化了多少」—— 静止的物体梯度为 0，烘进去会把选定帧也抠掉。
 *
 * 寻址与 THREE.Data3DTexture 一致：offset = (z*depth + y)*width + x。
 */
export function applyAlpha(rgba, data, y, W, H, D, threshold, t2in) {
  const t2 = (t2in === undefined) ? threshold * threshold : t2in;
  for (let z = 0; z < H; z++) {
    const srcRow = z * W * 4;
    const dstRow = (z * D + y) * W * 4;
    for (let x = 0; x < W; x++) {
      const s = srcRow + x * 4;
      const d = dstRow + x * 4;
      const r = rgba[s], g = rgba[s + 1], b = rgba[s + 2];
      data[d] = r;
      data[d + 1] = g;
      data[d + 2] = b;
      const lum = lumOf(r, g, b);
      // 低于阈值直接抠掉（背景不参与任何计算），否则按亮度存
      data[d + 3] = lum <= t2 ? 0 : Math.round(lum * 255);
    }
  }
}

/** sRGB 空间的感知亮度，范围 0..1 */
export function lumOf(r, g, b) {
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255;
}

/**
 * 阈值变动时只重算 alpha（亮度掩码），复用已解码的 RGB 体数据。
 * 时间梯度由着色器现算，所以这里不需要重新遍历相邻帧。
 */
export function reapplyThreshold(seq, threshold) {
  const { data, width: W, height: H, depth: D } = seq;
  const t2 = threshold * threshold;

  for (let y = 0; y < D; y++) {
    for (let z = 0; z < H; z++) {
      const row = (z * D + y) * W * 4;
      for (let x = 0; x < W; x++) {
        const i = row + x * 4;
        const lum = lumOf(data[i], data[i + 1], data[i + 2]);
        data[i + 3] = lum <= t2 ? 0 : Math.round(lum * 255);
      }
    }
  }
}

function nextTick() {
  return new Promise(resolve => setTimeout(resolve, 0));
}
