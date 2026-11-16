#!/usr/bin/env node
/**
 * 生成浏览器用的 vendor bundle
 *
 *   node scripts/build-vendor.mjs
 *
 * 浏览器不认识裸模块名 `exifr`，所以要用 esbuild 把 src/exif-parse.js
 * 打成 public/vendor/exif-parse.js（自带 exifr，无外部依赖）。
 *
 * `npm run build` 会自动调用它。
 *
 * 注意：某些受限环境不允许 Node 通过管道启动子进程（spawn EPERM），
 * 这时会退回"直接执行 esbuild 可执行文件"。两种方式都失败时会给出提示并继续，
 * 站点其余功能不受影响（只有网页里的「导入」会不可用）。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const ENTRY = path.join(ROOT, 'src', 'exif-parse.js');
const OUT = path.join(ROOT, 'public', 'vendor', 'exif-parse.js');

const CLI_ARGS = [
  ENTRY, '--bundle', '--format=esm', '--platform=browser',
  '--target=chrome110,safari16,firefox110',
  `--outfile=${OUT}`, '--minify', '--legal-comments=none', '--log-level=warning',
];

function tryJsApi() {
  return import('esbuild').then(
    (esbuild) => esbuild.build({
      entryPoints: [ENTRY],
      bundle: true,
      format: 'esm',
      platform: 'browser',
      target: ['chrome110', 'safari16', 'firefox110'],
      outfile: OUT,
      minify: true,
      legalComments: 'none',
      logLevel: 'warning',
    }).then(() => true),
    () => false,
  );
}

function tryCli() {
  const candidates = [
    path.join(ROOT, 'node_modules', '@esbuild', 'win32-x64', 'esbuild.exe'),
    path.join(ROOT, 'node_modules', '@esbuild', 'linux-x64', 'bin', 'esbuild'),
    path.join(ROOT, 'node_modules', '@esbuild', 'darwin-arm64', 'bin', 'esbuild'),
    path.join(ROOT, 'node_modules', '@esbuild', 'darwin-x64', 'bin', 'esbuild'),
  ];
  for (const bin of candidates) {
    const r = spawnSync(bin, CLI_ARGS, { stdio: 'inherit' });
    if (r.error) continue;
    if (r.status === 0) return true;
  }
  // 最后试 npx 形式
  const r = spawnSync(process.execPath, [path.join(ROOT, 'node_modules', 'esbuild', 'bin', 'esbuild'), ...CLI_ARGS], { stdio: 'inherit' });
  return !r.error && r.status === 0;
}

async function main() {
  await fs.mkdir(path.dirname(OUT), { recursive: true });

  let ok = false;
  try {
    ok = await tryJsApi();
  } catch {
    ok = false;
  }
  if (!ok) {
    console.warn('  · esbuild JS API 不可用，尝试直接调用可执行文件…');
    ok = tryCli();
  }

  if (!ok) {
    console.warn('  ! 无法生成 public/vendor/exif-parse.js');
    console.warn('    原因通常是 esbuild 未安装，或当前环境禁止启动子进程。');
    console.warn('    影响：网页里的「导入」功能不可用；命令行导入与相册浏览不受影响。');
    console.warn('    处理：在本机终端执行  npm install  然后  npm run vendor');
    return false;
  }

  const stat = await fs.stat(OUT);
  console.log(`已生成 public/vendor/exif-parse.js（${(stat.size / 1024).toFixed(1)} KB）`);
  return true;
}

await main();
