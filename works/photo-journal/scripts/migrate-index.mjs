#!/usr/bin/env node
/**
 * 索引字段迁移：把精简索引里的 `src`（日期来源）改成 `ds`
 *
 *   node scripts/migrate-index.mjs [--out public] [--dry-run]
 *
 * 背景：`search.json` 里的 `src` 原本存的是"日期来源"（folder / exif / mtime），
 * 但图片地址解析里 `src` 表示"原图路径"，两者同名会把 dateSource 当成图片路径去请求，
 * 于是产生 http://.../folder 这类 404。改名为 `ds` 彻底分开。
 *
 * 只改 JSON 索引，不碰任何照片文件；顺带把月份文件里的文件体积/像素补进精简索引
 * （重复检测页需要它们来算"能省多少空间"）。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const { values } = parseArgs({ options: {
  out: { type: 'string', default: 'public' },
  'dry-run': { type: 'boolean', default: false },
} });

const dataDir = path.resolve(ROOT, values.out, 'data');

async function main() {
  const files = await fs.readdir(dataDir).catch(() => []);
  const searchPath = path.join(dataDir, 'search.json');
  if (!files.includes('search.json')) {
    console.log('没有找到 search.json，无需迁移。');
    return;
  }

  const search = JSON.parse(await fs.readFile(searchPath, 'utf8'));
  console.log(`search.json：${search.length} 条`);

  // 1) 从月份文件里补 b（体积）与 px（像素）
  const monthFiles = files.filter((f) => /^photos-.*\.json$/.test(f) && !f.includes('backup'));
  const detail = new Map();
  for (const f of monthFiles) {
    try {
      const d = JSON.parse(await fs.readFile(path.join(dataDir, f), 'utf8'));
      for (const p of d.photos || []) detail.set(p.id, p);
    } catch { /* 单个文件坏了就跳过 */ }
  }
  console.log(`月份文件：${monthFiles.length} 个，共 ${detail.size} 条明细`);

  let renamed = 0;
  let enriched = 0;
  const out = search.map((p) => {
    const q = { ...p };
    if ('src' in q) {
      if (q.src) q.ds = q.src;
      delete q.src;                       // 清掉会被误当图片路径的字段
      renamed++;
    }
    const rec = detail.get(q.i);
    if (rec) {
      if (rec.bytes && !q.b) { q.b = rec.bytes; enriched++; }
      if (rec.pixel && !q.px) q.px = [rec.pixel.width, rec.pixel.height];
    }
    return q;
  });

  console.log(`字段改名 src → ds：${renamed} 条`);
  console.log(`补充体积/像素：${enriched} 条`);

  if (values['dry-run']) {
    console.log('（--dry-run，未写入）');
    return;
  }

  // 先备份
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  await fs.mkdir(path.join(dataDir, 'backup'), { recursive: true });
  await fs.copyFile(searchPath, path.join(dataDir, 'backup', `${stamp}_search.json`));
  await fs.writeFile(searchPath, JSON.stringify(out), 'utf8');
  console.log(`已写入 search.json（原文件备份在 data/backup/${stamp}_search.json）`);
}

main().catch((err) => { console.error(err); process.exitCode = 1; });
