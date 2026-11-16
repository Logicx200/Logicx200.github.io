#!/usr/bin/env node
/**
 * 生成演示照片归档 + 端到端跑一遍导入流程
 *
 *   node scripts/make-demo.mjs [目标目录]
 *
 * 会造出一批带真实 EXIF 的 JPEG（含相机、镜头、光圈、快门、ISO、焦距、GPS），
 * 并按"不甚规则"的中文文件夹名归档，用来验证：
 *   - 文件夹名解析（含只有月日、只有年份、纯数字、混排等）
 *   - EXIF 参数读取
 *   - GPS → 地图
 *   - 缩略图 / 索引生成
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { writeExifApp1 } from '../src/exif-write.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const target = path.resolve(process.argv[2] || path.join(ROOT, 'demo-archive'));

/* 每张演示照片：所在文件夹 + 文件名 + 拍摄参数 */
const SHOTS = [
  // ---- 2024 年 ----
  { dir: '2024年/10月3日 杭州西湖', file: 'DSC01234.JPG', date: '2024-10-03T17:42:10', w: 3000, h: 2000, color: '#d98b6a',
    cam: ['SONY', 'ILCE-7M4'], lens: 'FE 24-70mm F2.8 GM II', f: 5.6, t: 1 / 250, iso: 100, focal: 35, gps: { lat: 30.2442, lng: 120.1390, alt: 12 } },
  { dir: '2024年/10月3日 杭州西湖', file: 'DSC01235.JPG', date: '2024-10-03T18:05:33', w: 2000, h: 3000, color: '#c96f5a',
    cam: ['SONY', 'ILCE-7M4'], lens: 'FE 24-70mm F2.8 GM II', f: 2.8, t: 1 / 60, iso: 800, focal: 70, gps: { lat: 30.2455, lng: 120.1401, alt: 10 } },
  { dir: '2024年/10月4日 西溪湿地 晨雾', file: 'DSC01301.JPG', date: '2024-10-04T06:20:11', w: 3000, h: 2000, color: '#8aa9a0',
    cam: ['SONY', 'ILCE-7M4'], lens: 'FE 70-200mm F2.8 GM OSS II', f: 4, t: 1 / 400, iso: 200, focal: 135, gps: { lat: 30.2680, lng: 120.0650, alt: 8 } },
  { dir: '2024年/11月23日 婺源 秋色', file: 'DSC02088.JPG', date: '2024-11-23T15:10:00', w: 3000, h: 2000, color: '#c9a227',
    cam: ['FUJIFILM', 'X-T5'], lens: 'XF16-55mmF2.8 R LM WR', f: 8, t: 1 / 125, iso: 160, focal: 23, gps: { lat: 29.2476, lng: 117.8617 } },
  { dir: '2024年/11月23日 婺源 秋色', file: 'DSC02089.JPG', date: '2024-11-23T16:02:45', w: 2000, h: 3000, color: '#b5892a',
    cam: ['FUJIFILM', 'X-T5'], lens: 'XF16-55mmF2.8 R LM WR', f: 2.8, t: 1 / 200, iso: 160, focal: 55, gps: { lat: 29.2501, lng: 117.8650 } },
  { dir: '2024-12-31 上海外滩 跨年', file: 'IMG_20241231_231805.jpg', date: '2024-12-31T23:18:05', w: 3000, h: 2000, color: '#3b5b8c',
    cam: ['Apple', 'iPhone 15 Pro'], lens: 'iPhone 15 Pro back camera 6.765mm f/1.78', f: 1.78, t: 1 / 30, iso: 1250, focal: 6.765, gps: { lat: 31.2397, lng: 121.4900, alt: 6 } },

  // ---- 2023 年 ----
  { dir: '2023/10月1日 国庆 北京', file: 'DSC00112.JPG', date: '2023-10-01T09:30:00', w: 3000, h: 2000, color: '#a33b3b',
    cam: ['Canon', 'EOS R6'], lens: 'RF24-105mm F4 L IS USM', f: 4, t: 1 / 500, iso: 100, focal: 24, gps: { lat: 39.9163, lng: 116.3972, alt: 44 } },
  { dir: '2023/10月1日 国庆 北京', file: 'DSC00113.JPG', date: '2023-10-01T17:50:22', w: 3000, h: 2000, color: '#8c6b4f',
    cam: ['Canon', 'EOS R6'], lens: 'RF24-105mm F4 L IS USM', f: 5.6, t: 1 / 160, iso: 200, focal: 50, gps: { lat: 39.9400, lng: 116.3860 } },
  { dir: '2023/05月20日 苏州 拙政园', file: 'DSC00890.JPG', date: '2023-05-20T10:05:00', w: 2000, h: 3000, color: '#4f7a55',
    cam: ['Nikon', 'Z 6II'], lens: 'NIKKOR Z 24-120mm f/4 S', f: 5.6, t: 1 / 320, iso: 100, focal: 35, gps: { lat: 31.3230, lng: 120.6250 } },
  { dir: '2023/精选 原片 归档', file: 'DSC00999.JPG', date: '2023-08-12T20:11:03', w: 3000, h: 2000, color: '#2f3b52',
    cam: ['Nikon', 'Z 6II'], lens: 'NIKKOR Z 20mm f/1.8 S', f: 1.8, t: 8, iso: 1600, focal: 20 },   // 无 GPS：测试"待确认"
  { dir: '2023/08月15日 单位活动', file: 'DSC01000.JPG', date: '2023-08-15T12:00:00', w: 3000, h: 2000, color: '#5a5a6e',
    cam: ['Nikon', 'Z 6II'], lens: 'NIKKOR Z 24-120mm f/4 S', f: 4, t: 1 / 200, iso: 400, focal: 60 },

  // ---- 只有年月、甚至没有年份的"混乱"归档 ----
  { dir: '2022年/国庆', file: 'IMG_5512.JPG', date: '2022-10-02T11:11:11', w: 3000, h: 2000, color: '#7a5c3b',
    cam: ['Canon', 'EOS 6D Mark II'], lens: 'EF16-35mm f/4L IS USM', f: 8, t: 1 / 250, iso: 100, focal: 16 },
  { dir: '2022年/扫街/10-06 成都宽窄巷子', file: 'IMG_5601.JPG', date: '2022-10-06T18:40:00', w: 2000, h: 3000, color: '#6b4a3a',
    cam: ['Canon', 'EOS 6D Mark II'], lens: 'EF35mm f/1.4L II USM', f: 1.4, t: 1 / 80, iso: 1600, focal: 35, gps: { lat: 30.6690, lng: 104.0550 } },
  { dir: '未整理/手机照片', file: 'IMG_20210405_090001.jpg', date: '2021-04-05T09:00:01', w: 2000, h: 3000, color: '#4a6b8c',
    cam: ['Xiaomi', 'Xiaomi 13'], lens: null, f: 1.9, t: 1 / 100, iso: 640, focal: 5.4, gps: { lat: 31.2304, lng: 121.4737 } },

  // ---- Lightroom 导出的照片：Software 字段可识别 ----
  { dir: '2024年/06月18日 青岛 海边', file: '海边-成片-0001.jpg', date: '2024-06-18T18:22:00', w: 3000, h: 2000, color: '#3f6f8f',
    cam: ['SONY', 'ILCE-7RM5'], lens: 'FE 16-35mm F2.8 GM II', f: 11, t: 1 / 30, iso: 100, focal: 16,
    software: 'Adobe Photoshop Lightroom Classic 13.3 (Windows)', gps: { lat: 36.0620, lng: 120.3840 } },
  { dir: '2024年/06月18日 青岛 海边', file: '海边-成片-0002.jpg', date: '2024-06-18T19:01:00', w: 3000, h: 2000, color: '#2f5878',
    cam: ['SONY', 'ILCE-7RM5'], lens: 'FE 16-35mm F2.8 GM II', f: 8, t: 1 / 13, iso: 100, focal: 20,
    software: 'Adobe Photoshop Lightroom Classic 13.3 (Windows)', gps: { lat: 36.0671, lng: 120.3826 } },
];

/** 用 sharp 画一张有噪点/渐变的图，避免纯色（更像真实照片） */
async function makeJpeg({ w, h, color, seed }) {
  const { default: sharp } = await import('sharp');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${color}"/>
      <stop offset="60%" stop-color="#101820"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0.35"/>
    </linearGradient>
    <radialGradient id="r" cx="${(seed % 7) / 10 + 0.2}" cy="${(seed % 5) / 10 + 0.2}" r="0.6">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.1"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#g)"/>
  <rect width="100%" height="100%" fill="url(#r)"/>
  <text x="24" y="${h - 28}" font-family="sans-serif" font-size="${Math.round(Math.min(w, h) / 22)}" fill="rgba(255,255,255,.75)">JP ${seed} · ${w}×${h}</text>
</svg>`;
  return sharp(Buffer.from(svg)).jpeg({ quality: 88 }).toBuffer();
}

/** 没有 sharp 时的兜底：一张合法的最小 JPEG（1×1）——不适合当演示图，但能跑通流程 */
function tinyJpeg() {
  return Buffer.from(
    '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==',
    'base64',
  );
}

/** 生成"重复照片"测试集：同一张图的不同版本，验证感知哈希能否识别 */
async function makeDuplicateSet(target) {
  const { default: sharp } = await import('sharp');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#2b4a6f"/><stop offset="50%" stop-color="#c98a4b"/>
        <stop offset="100%" stop-color="#1b2330"/>
      </linearGradient>
    </defs>
    <rect width="100%" height="100%" fill="url(#g)"/>
    <circle cx="360" cy="260" r="150" fill="#f2e2c4" opacity="0.9"/>
    <polygon points="0,800 420,340 760,800" fill="#0f1a14" opacity="0.85"/>
    <polygon points="520,800 900,400 1200,800" fill="#132118" opacity="0.8"/>
  </svg>`;
  const base = await sharp(Buffer.from(svg)).jpeg({ quality: 92 }).toBuffer();

  const variants = [
    // [子目录, 文件名, 变换, 说明]
    ['重复测试/原图', 'SCENE-0001.jpg', (s) => s, 'original'],
    ['重复测试/原图', 'SCENE-0001-副本.jpg', (s, buf) => buf, 'identical'],
    ['重复测试/导出一遍', 'SCENE-0001-export.jpg', (s) => sharp(base).jpeg({ quality: 62 }), 'recompressed'],
    ['重复测试/缩小过', 'SCENE-0001-small.jpg', () => sharp(base).resize(600), 'resized'],
    ['重复测试/连拍', 'SCENE-0002.jpg', () => sharp(base).modulate({ brightness: 1.06 }), 'slight'],
    ['重复测试/无关照片', 'OTHER-9999.jpg', async () => {
      const other = await sharp({
        create: { width: 1200, height: 800, channels: 3, background: '#101010' },
      }).composite([{ input: Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><circle cx="300" cy="500" r="220" fill="#e8e8e8"/><rect x="700" y="120" width="380" height="380" fill="#7a7a7a"/></svg>') }]).jpeg({ quality: 90 }).toBuffer();
      return other;
    }, 'different'],
  ];

  for (const [dir, file, transform, tag] of variants) {
    const out = path.join(target, ...dir.split('/'));
    await fs.mkdir(out, { recursive: true });
    const result = await transform(sharp(base), base);
    const buf = Buffer.isBuffer(result) ? result : await result.toBuffer();
    const meta = await sharp(buf).metadata();
    const withExif = writeExifApp1(new Uint8Array(buf), {
      make: 'SONY', model: 'ILCE-7M4', lensModel: 'FE 24-70mm F2.8 GM II',
      dateTimeOriginal: new Date(tag === 'slight' ? '2024-05-01T18:00:02' : '2024-05-01T18:00:00'),
      fNumber: 5.6, exposureTime: 1 / 250, iso: 100, focalLength: 35,
      pixelXDimension: meta.width, pixelYDimension: meta.height,
      gps: { lat: 30.2442, lng: 120.139 },
    });
    await fs.writeFile(path.join(out, file), withExif);
    console.log(`  重复测试：${dir}/${file}（${tag}，${meta.width}×${meta.height}）`);
  }
}

async function main() {
  console.log(`生成演示归档：${target}`);
  await fs.mkdir(target, { recursive: true });

  let sharpOk = true;
  try { await import('sharp'); } catch { sharpOk = false; }
  if (!sharpOk) console.log('  ! 未安装 sharp，将使用占位图（仅用于跑通流程）');

  let n = 0;
  for (const shot of SHOTS) {
    const dir = path.join(target, ...shot.dir.split('/'));
    await fs.mkdir(dir, { recursive: true });
    const file = path.join(dir, shot.file);
    const base = sharpOk ? await makeJpeg({ w: shot.w, h: shot.h, color: shot.color, seed: ++n })
      : tinyJpeg();
    const withExif = writeExifApp1(new Uint8Array(base), {
      make: shot.cam[0],
      model: shot.cam[1],
      lensModel: shot.lens || undefined,
      dateTimeOriginal: new Date(shot.date),
      software: shot.software,
      fNumber: shot.f,
      exposureTime: shot.t,
      iso: shot.iso,
      focalLength: shot.focal,
      focalLength35: shot.focal ? Math.round(shot.focal * (shot.cam[1].includes('iPhone') || shot.cam[1].includes('Xiaomi') ? 4 : 1)) : undefined,
      exposureProgram: 3,
      meteringMode: 5,
      whiteBalance: 0,
      pixelXDimension: shot.w,
      pixelYDimension: shot.h,
      gps: shot.gps,
      artist: '演示数据',
    });
    await fs.writeFile(file, withExif);
    process.stdout.write(`\r  已生成 ${n}/${SHOTS.length} …`);
  }
  process.stdout.write('\r' + ' '.repeat(30) + '\r');
  console.log(`  完成：${n} 张照片，位于 ${target}`);

  if (sharpOk) {
    console.log('  生成重复照片测试集…');
    await makeDuplicateSet(target);
  }

  console.log('');
  console.log('下一步：');
  console.log(`  node scripts/import.mjs --src "${target}" --copy`);
  console.log('  npm run serve');
}

main().catch((err) => { console.error(err); process.exitCode = 1; });
