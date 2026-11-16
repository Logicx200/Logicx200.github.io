/* 生成一套可控的合成测试序列（自带最小 PNG 编码器，无外部依赖）
 *
 * 这套图是为了让「轨迹」这件事可以被逐像素验证，所以每个元素都有精确的已知位置：
 *
 *   深色背景        —— 让轨迹能从背景里浮出来（这也是参考视频里必备的条件）
 *   橙色小球        —— 横穿画面的运动目标，只在 x 方向移动，y 恒为 0
 *   青色方块        —— 完全静止的参照物：所有帧里它必须落在同一个屏幕位置
 *   品红十字        —— 画面中心，用来验证纹理上下方向没有被翻转
 *
 * 因为小球在 y_world=0 的直线上运动，它在正视图里的轨迹必然是一条**水平直线**；
 * 而在等轴视图里，它沿时间轴连起来就是一条斜线。这两个都是可断言的。
 *
 * 用法：node tools/make-sample.mjs [outDir] [frames] [w] [h]
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { encodePng } from './png.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(process.argv[2] || join(here, '..', 'sample'));
const FRAMES = parseInt(process.argv[3] || '24', 10);
const W = parseInt(process.argv[4] || '320', 10);
const H = parseInt(process.argv[5] || '240', 10);

/* ------------------------------------------------------------- PNG 编码 */

/* --------------------------------------------------------------- 画图 */

function makeFrame(w, h, t) {
  const px = new Uint8Array(w * h * 3);
  const BG = [14, 16, 22];

  for (let i = 0; i < w * h; i++) {
    px[i * 3] = BG[0]; px[i * 3 + 1] = BG[1]; px[i * 3 + 2] = BG[2];
  }

  const put = (x, y, c) => {
    x = Math.round(x); y = Math.round(y);
    if (x < 0 || y < 0 || x >= w || y >= h) return;
    const o = (y * w + x) * 3;
    px[o] = c[0]; px[o + 1] = c[1]; px[o + 2] = c[2];
  };

  const rect = (x0, y0, x1, y1, c) => {
    for (let y = Math.round(y0); y < Math.round(y1); y++) {
      for (let x = Math.round(x0); x < Math.round(x1); x++) put(x, y, c);
    }
  };

  const disc = (cx, cy, r, c) => {
    const r2 = r * r;
    for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++) {
      for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
        const dx = x + 0.5 - cx, dy = y + 0.5 - cy;
        if (dx * dx + dy * dy <= r2) put(x, y, c);
      }
    }
  };

  // 静止参照：青色方块，固定在画面右上（所有帧完全相同）
  rect(w * 0.68, h * 0.14, w * 0.68 + 26, h * 0.14 + 26, [40, 220, 220]);

  // 画面中心：品红十字（验证纹理没有上下翻转）
  rect(w / 2 - 1, h / 2 - 9, w / 2 + 1, h / 2 + 9, [235, 40, 200]);
  rect(w / 2 - 9, h / 2 - 1, w / 2 + 9, h / 2 + 1, [235, 40, 200]);

  // 运动目标：橙色小球，只在水平方向移动，y 恒在画面中线
  const u = FRAMES > 1 ? t / (FRAMES - 1) : 0;
  const bx = w * (0.10 + 0.80 * u);
  const by = h * 0.5;
  disc(bx, by, 9, [255, 150, 30]);

  // 底部一条暗蓝渐变条：给侧面颜色条提供可辨识的横向结构
  // 注意 clamp：`10 + 30*sin` 会走到 -20，而目标是 Uint8Array ——
  // 负值会**回绕成 236**，在暗蓝渐变的中间凭空出现一条刺眼的亮红带。
  // 这个坑是在核对轮廓参考图时发现的（那条亮红带被当成了轮廓）。
  for (let x = 0; x < w; x++) {
    const v = Math.max(0, Math.round(10 + 30 * Math.sin((x / w) * Math.PI * 2)));
    for (let y = h - 14; y < h - 6; y++) put(x, y, [v, Math.min(255, v + 8), 90]);
  }

  return px;
}

/**
 * 造一个「看起来像图片文件」的对象，供 Node 侧无浏览器自检使用：
 * 带真实的 PNG 头（自检可以通过读头部拿到尺寸）、能 slice、能 close。
 */
function fakeImageFile(name, w, h, lastModified) {
  const blank = new Uint8Array(w * h * 3);
  const png = encodePng(blank, w, h);
  const buf = png.buffer.slice(png.byteOffset, png.byteOffset + png.byteLength);
  const file = {
    name,
    type: 'image/png',
    size: buf.byteLength,
    lastModified: lastModified || 0,
    _buf: buf,
    slice(start, end) {
      const s = start || 0;
      const e = end === undefined ? buf.byteLength : Math.min(end, buf.byteLength);
      return { arrayBuffer: async () => buf.slice(s, e) };
    }
  };
  return file;
}

/**
 * 造一个「看起来像视频文件」的对象。
 *
 * 真正的解码交给 tools/harness.mjs 里的 <video> 替身：它按 `_video` 里的
 * 宽高 / 帧率 / 时长把一个虚拟时间轴走一遍，并**只通过 requestVideoFrameCallback
 * 报帧** —— 与真浏览器一致，所以"每一帧都保留"这条能被真正断言。
 *
 * @param {string} name
 * @param {{width?:number, height?:number, fps?:number, duration?:number,
 *          dropEvery?:number}} o
 *   dropEvery: 每隔几帧让替身报一个"丢帧"（用来验证丢帧会被如实上报）
 */
function fakeVideoFile(name, o) {
  o = o || {};
  const meta = {
    width: o.width || 640,
    height: o.height || 360,
    fps: o.fps || 30,
    duration: o.duration === undefined ? 2 : o.duration,
    dropEvery: o.dropEvery || 0
  };
  return {
    name,
    type: 'video/mp4',
    size: 1024,
    lastModified: o.lastModified || 0,
    _video: meta,
    slice() { return { arrayBuffer: async () => new ArrayBuffer(8) }; }
  };
}

/** 一个真正的视频文件在替身里的帧数（= duration × fps） */
function videoFrameCount(file) {
  const m = file && file._video;
  if (!m) return 0;
  return Math.max(0, Math.round(m.duration * m.fps));
}

/** 造一个 ImageBitmap 替身：尺寸取自 PNG 头，带 close() */
function fakeBitmap(w, h) {
  return { width: w, height: h, _fake: true, close() { this.closed = true; } };
}

/* --------------------------------------------------------------- 主流程 */

// 被 import 时只导出工具函数，不生成文件（自检脚本会复用 encodePng）
const isMain = process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url));
if (isMain) {
  let sum = 0;
  mkdirSync(outDir, { recursive: true });
  for (let t = 0; t < FRAMES; t++) {
    const px = makeFrame(W, H, t);
    const png = encodePng(px, W, H);
    sum += png.length;
    const name = join(outDir, `frame_${String(t).padStart(3, '0')}.png`);
    writeFileSync(name, png);
  }

  console.log(`已生成 ${FRAMES} 帧 → ${outDir}`);
  console.log(`  尺寸 ${W}×${H}，共 ${(sum / 1024).toFixed(1)} KB，无压缩损失（PNG 无损）`);
  console.log(`  橙色小球沿中线水平移动；青色方块静止；中心有品红十字`);
}

export { makeFrame, fakeImageFile, fakeVideoFile, videoFrameCount, fakeBitmap };
export { encodePng, decodePng, pngSize, rgbaToRgb } from './png.mjs';
