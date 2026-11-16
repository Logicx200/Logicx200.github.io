#!/usr/bin/env node
/**
 * 烘焙世界海岸线数据 → public/assets/mapatlas.js
 *
 * 数据源：npm 上的 world-atlas（Natural Earth 110m 陆地），TopoJSON 格式。
 * 这里在构建期把它转成"经纬度环线数组"，站点运行时零依赖、离线可用。
 *
 *   node scripts/build-atlas.mjs
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, '..', 'public', 'assets', 'mapatlas.js');

/* TopoJSON 解码：把 delta 编码的 arcs 还原成绝对坐标 */
function decodeArcs(topology) {
  const { scale = [1, 1], translate = [0, 0] } = topology.transform || {};
  return topology.arcs.map((arc) => {
    let x = 0;
    let y = 0;
    return arc.map(([dx, dy]) => {
      x += dx;
      y += dy;
      return [x * scale[0] + translate[0], y * scale[1] + translate[1]];
    });
  });
}

function ringFromArcIndices(indices, arcs) {
  const points = [];
  for (const idx of indices) {
    const reverse = idx < 0;
    const arc = arcs[reverse ? ~idx : idx];
    const seq = reverse ? arc.slice().reverse() : arc;
    for (let i = 0; i < seq.length; i++) {
      if (i === 0 && points.length) continue; // 去掉共享端点
      points.push([seq[i][0], seq[i][1]]);
    }
  }
  return points;
}

/** 计算环的近似面积（度²），用于过滤小岛 */
function ringArea(ring) {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    a += ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
  }
  return Math.abs(a / 2);
}

function simplify(ring, tolerance) {
  if (ring.length < 8) return ring;
  // 简单的 Douglas-Peucker
  const sqTol = tolerance * tolerance;
  const sqSegDist = (p, a, b) => {
    let x = a[0];
    let y = a[1];
    let dx = b[0] - x;
    let dy = b[1] - y;
    if (dx !== 0 || dy !== 0) {
      const t = ((p[0] - x) * dx + (p[1] - y) * dy) / (dx * dx + dy * dy);
      if (t > 1) { x = b[0]; y = b[1]; } else if (t > 0) { x += dx * t; y += dy * t; }
    }
    dx = p[0] - x;
    dy = p[1] - y;
    return dx * dx + dy * dy;
  };
  const getSqDist = (p, a, b) => sqSegDist(p, a, b);

  const run = (first, last, out) => {
    let maxDist = sqTol;
    let index = -1;
    for (let i = first + 1; i < last; i++) {
      const d = getSqDist(ring[i], ring[first], ring[last]);
      if (d > maxDist) { index = i; maxDist = d; }
    }
    if (index > 0) {
      if (index - first > 1) run(first, index, out);
      out.push(ring[index]);
      if (last - index > 1) run(index, last, out);
    }
  };

  const out = [ring[0]];
  run(0, ring.length - 1, out);
  out.push(ring[ring.length - 1]);
  return out.length >= 4 ? out : ring;
}

async function main() {
  const url = 'https://unpkg.com/world-atlas@2/land-110m.json';
  console.log('下载底图数据：' + url);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`下载失败 HTTP ${res.status}`);
  const topo = await res.json();

  const arcs = decodeArcs(topo);
  const geom = topo.objects.land;
  
  /** @type {number[][][]} */
  const rings = [];

  const collect = (geometry) => {
    if (geometry.type === 'Polygon') {
      geometry.arcs.forEach((ring, i) => rings.push({ ring: ringFromArcIndices(ring, arcs), outer: i === 0 }));
    } else if (geometry.type === 'MultiPolygon') {
      for (const poly of geometry.arcs) {
        poly.forEach((ring, i) => rings.push({ ring: ringFromArcIndices(ring, arcs), outer: i === 0 }));
      }
    } else if (geometry.type === 'GeometryCollection') {
      geometry.geometries.forEach(collect);
    }
  };
  collect(geom);

  const MIN_AREA = 1.2; // 度²：过滤掉小到看不见的岛
  const kept = rings
    .filter((r) => r.outer && ringArea(r.ring) >= MIN_AREA)
    .map((r) => simplify(r.ring, 0.35))
    .map((r) => r.map(([lon, lat]) => [Number(lon.toFixed(2)), Number(lat.toFixed(2))]))
    .sort((a, b) => ringArea(b) - ringArea(a));

  const payload = JSON.stringify(kept);
  const js = `/**
 * 世界海岸线（Natural Earth 110m，经 Douglas-Peucker 简化）
 * 由 scripts/build-atlas.mjs 生成，请勿手工编辑。
 * 数据格式：[[ [lon, lat], ... ], ...]  等距圆柱投影可直接使用
 */
export const WORLD_LAND = ${payload};
export default WORLD_LAND;
`;
  await fs.writeFile(OUT, js, 'utf8');
  const kb = (Buffer.byteLength(js) / 1024).toFixed(1);
  console.log(`写出 ${OUT}（${kept.length} 个环，${kb} KB）`);
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
