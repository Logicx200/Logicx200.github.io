#!/usr/bin/env node
/**
 * 构建可发布的静态站点
 *
 *   node scripts/build.mjs [--out dist]
 *
 * 做三件事：
 *   1. 把 src/ 下的共享模块复制到 public/src/（站点是原生 ES Module，浏览器需要能直接取到）
 *   2. 把 public/ 整体复制到 dist/
 *   3. 生成 .nojekyll（GitHub Pages 需要，否则下划线开头的文件会被 Jekyll 忽略）
 *
 * 之后把 dist/ 推到仓库的 gh-pages 分支，或在仓库设置里选 "Deploy from a branch → / (root)"。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const { values } = parseArgs({ options: { out: { type: 'string', default: 'dist' } } });
const outRoot = path.resolve(ROOT, values.out);
const publicRoot = path.join(ROOT, 'public');

const SHARED_MODULES = [
  'parse.js', 'exif.js', 'exif-write.js', 'record.js', 'filters.js',
  'util.js', 'locationHints.js', 'media-shared.js', 'media-browser.js', 'zip.js', 'merge.js',
  'site-root.js', 'dup.js',
];

async function copyDir(src, dest) {
  await fs.mkdir(dest, { recursive: true });
  for (const e of await fs.readdir(src, { withFileTypes: true })) {
    const s = path.join(src, e.name);
    const d = path.join(dest, e.name);
    if (e.isDirectory()) await copyDir(s, d);
    else await fs.copyFile(s, d);
  }
}

async function main() {
  // 1) 共享模块 → public/src
  const sharedDest = path.join(publicRoot, 'src');
  await fs.mkdir(sharedDest, { recursive: true });
  for (const m of SHARED_MODULES) {
    const src = path.join(ROOT, 'src', m);
    try {
      await fs.copyFile(src, path.join(sharedDest, m));
    } catch (err) {
      if (err.code !== 'ENOENT') throw err;
    }
  }
  console.log(`已同步共享模块 → public/src（${SHARED_MODULES.length} 个文件）`);

  // 1.5) 浏览器用的 vendor bundle（内含 exifr）
  await import('./build-vendor.mjs');

  // 2) public → dist
  await fs.rm(outRoot, { recursive: true, force: true });
  await copyDir(publicRoot, outRoot);
  await fs.writeFile(path.join(outRoot, '.nojekyll'), '', 'utf8');

  // 站点身份标记：网页导入时用它确认"你选中的目录确实是本站的 public/"
  await fs.writeFile(
    path.join(outRoot, 'site-id.txt'),
    'photo-journal site root\n它是本项目的 public 目录，网页导入会把 data/ 与 media/ 写到这里。\n',
    'utf8',
  );

  // 3) 报告体积
  let bytes = 0;
  let files = 0;
  async function walk(d) {
    for (const e of await fs.readdir(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) await walk(p);
      else { bytes += (await fs.stat(p)).size; files++; }
    }
  }
  await walk(outRoot);
  const mb = (bytes / 1024 / 1024).toFixed(2);
  console.log(`构建完成：${outRoot}`);
  console.log(`  ${files} 个文件，共 ${mb} MB`);
  console.log('');
  console.log('部署到 GitHub Pages：');
  console.log('  git add -A && git commit -m "update gallery" && git push');
  console.log('  仓库 Settings → Pages → Source: Deploy from a branch → 分支 gh-pages / (root)');
}

main().catch((err) => { console.error(err); process.exitCode = 1; });
