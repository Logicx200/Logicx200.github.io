/* 检查参考图是否真的"可看"：尺寸、内容占比、是否有内容越界、颜色分布 */
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodePng } from './png.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const dir = join(here, '..', 'test', 'reference');

const FILES = [
  '01-front-frame0-only.png',
  '02-front-frame0-opacity0.png',
  '03-front-all-ghost-0.5.png',
  '04-iso-opaque.png',
  '05-iso-frame12-ghosts.png',
  '06-front-frame12-ghosts.png'
];

const BG = [5, 7, 11];

for (const f of FILES) {
  let img;
  try { img = decodePng(readFileSync(join(dir, f))); }
  catch (e) { console.log(`${f}: 读不出（${e.message}）`); continue; }

  let lit = 0;
  let minX = 1e9, maxX = -1, minY = 1e9, maxY = -1;
  let sum = [0, 0, 0];
  const hist = new Map();
  for (let y = 0; y < img.height; y++) {
    for (let x = 0; x < img.width; x++) {
      const o = (y * img.width + x) * 4;
      const r = img.data[o], g = img.data[o + 1], b = img.data[o + 2];
      sum[0] += r; sum[1] += g; sum[2] += b;
      const key = `${r >> 5},${g >> 5},${b >> 5}`;
      hist.set(key, (hist.get(key) || 0) + 1);
      if (Math.abs(r - BG[0]) > 6 || Math.abs(g - BG[1]) > 6 || Math.abs(b - BG[2]) > 6) {
        lit++;
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
      }
    }
  }
  const n = img.width * img.height;
  const avg = sum.map((s) => (s / n).toFixed(1));
  const top = [...hist.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3)
    .map(([k, c]) => `(${k})×${(c / n * 100).toFixed(0)}%`).join(' ');

  console.log(`${f}`);
  console.log(`  ${img.width}×${img.height}  内容 ${(lit / n * 100).toFixed(1)}%  平均色 rgb(${avg.join(',')})`);
  console.log(`  内容范围 x∈[${lit ? minX : '-'},${lit ? maxX : '-'}] y∈[${lit ? minY : '-'},${lit ? maxY : '-'}]`);
  console.log(`  主要色块（量化到 32 级）：${top}`);
  // 内容是否越界：非背景像素不能贴到画面边缘
  if (lit > 0) {
    const touches = minX === 0 || minY === 0 || maxX === img.width - 1 || maxY === img.height - 1;
    console.log(`  贴边（应恒为 false）：${touches}`);
  }
  console.log('');
}
