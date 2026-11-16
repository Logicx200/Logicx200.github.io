/** 开发辅助：把烘焙好的海岸线渲染成 PNG，用于人工目视检查 */
import fs from 'node:fs/promises';
import { WORLD_LAND } from '../public/assets/mapatlas.js';

const W = 900;
const H = 450;
const paths = WORLD_LAND.map((r) => 'M' + r
  .map(([x, y]) => `${((x + 180) / 360 * W).toFixed(1)},${((90 - y) / 180 * H).toFixed(1)}`)
  .join('L') + 'Z').join('');

const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">
<rect width="100%" height="100%" fill="#0b1220"/>
<g stroke="#7fa8d0" stroke-width="0.4" fill="#24405c">${'<path d="' + paths + '"/>'}</g>
<g stroke="#1e3350" stroke-width="0.5">
${[-60, -30, 0, 30, 60].map((lat) => `<line x1="0" y1="${((90 - lat) / 180 * H).toFixed(1)}" x2="${W}" y2="${((90 - lat) / 180 * H).toFixed(1)}"/>`).join('')}
${[-120, -60, 0, 60, 120].map((lon) => `<line x1="${((lon + 180) / 360 * W).toFixed(1)}" y1="0" x2="${((lon + 180) / 360 * W).toFixed(1)}" y2="${H}"/>`).join('')}
</g></svg>`;

await fs.writeFile('.cache/atlas-preview.svg', svg, 'utf8');
try {
  const { default: sharp } = await import('sharp');
  await sharp(Buffer.from(svg)).png().toFile('.cache/atlas-preview.png');
  console.log('已生成 .cache/atlas-preview.png');
} catch (e) {
  console.log('sharp 不可用，仅生成 SVG：' + e.message);
}
