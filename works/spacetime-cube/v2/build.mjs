/* 把 src/ 合成一个完全自包含的 index.html
 *
 * 为什么要一个单独的 src/ 目录：
 *   日常维护时分成 6 个小文件好改；交付时必须是**单个 HTML 文件**，
 *   双击就能开、不联网、不依赖 CDN。这个脚本负责把两者对上。
 *
 * 用法：
 *   node build.mjs            生成 ../index.html
 *   node build.mjs --check    只做语法检查，不写文件
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = join(here, 'src');
const outFile = join(here, 'index.html');

const SCRIPTS = [
  '10-math.js',
  '20-gl.js',
  '30-exif.js',
  '40-seq.js',
  '45-video.js',
  '50-shaders.js',
  '55-view.js',
  '60-renderer.js',
  '70-app.js'
];

const CSS = 'styles.css';
const TPL = 'index.html';

function read(name) {
  return readFileSync(join(srcDir, name), 'utf8');
}

/** 用 vm 编译一遍，把语法错误挡在构建阶段 */
function syntaxCheck(parts) {
  const problems = [];
  for (const { name, code } of parts) {
    try {
      new vm.Script(code, { filename: name });
    } catch (e) {
      problems.push(`${name}: ${e.message}`);
    }
  }
  return problems;
}

/**
 * 每个模块都整体包在自己的 IIFE 里，所以顶层同名函数（例如 seq 与 view 各自
 * 有一个 pointStride）是有意为之、不会互相冲突。
 * 真正致命的是**把一个模块的 IIFE 调用写坏、导致后面所有代码掉进它的作用域**，
 * 那会在拼接后变成语法错误 —— 所以这里检查的是"把模块拼起来后能否整体解析"。
 */
function assembleCheck(parts) {
  const problems = [];
  const body = parts.map((p) => p.code.trimEnd()).join('\n\n');
  const wrapped = `(function(){\n'use strict';\n${body}\n})();\n`;
  try {
    new vm.Script(wrapped, { filename: '__assembled__.js' });
  } catch (e) {
    problems.push('拼接后无法解析（多半是某个模块的 IIFE 调用没写完整）：' + e.message);
  }
  for (const { name, code } of parts) {
    const opens = (code.match(/^\(function\s*\(/gm) || []).length;
    const closes = (code.match(/^\}\)\(window\.STC/gm) || []).length;
    if (opens !== 1 || closes !== 1) {
      problems.push(`${name}：模块外壳不完整（开头 ${opens} 处 / 结尾 ${closes} 处）`);
    }
  }
  return problems;
}

function main() {
  const checkOnly = process.argv.includes('--check');

  const parts = SCRIPTS.map((f) => ({ name: f, code: read(f) }));
  const css = read(CSS);
  const tpl = read(TPL);

  const problems = [...syntaxCheck(parts), ...assembleCheck(parts)];

  // 检查模板占位符
  for (const token of ['<!--__ASSEMBLE_STYLES__-->', '<!--__ASSEMBLE_SCRIPTS__-->']) {
    if (!tpl.includes(token)) problems.push(`模板缺少占位符 ${token}`);
  }

  if (problems.length) {
    console.error('构建检查未通过：');
    for (const p of problems) console.error('  - ' + p);
    process.exit(1);
  }

  if (checkOnly) {
    console.log(`语法与占位符检查通过（${parts.length} 个脚本，${css.split('\n').length} 行样式）`);
    return;
  }

  const body = parts
    .map((p) => `/* ===================================================== ${p.name} */\n${p.code.trimEnd()}`)
    .join('\n\n');

  const script = [
    '<script>',
    '(function () {',
    "'use strict';",
    body,
    '})();',
    '</script>'
  ].join('\n');

  let out = tpl
    .replace('<!--__ASSEMBLE_STYLES__-->', '<style>\n' + css.trimEnd() + '\n</style>')
    .replace('<!--__ASSEMBLE_SCRIPTS__-->', script);

  writeFileSync(outFile, out, 'utf8');

  const kb = (Buffer.byteLength(out, 'utf8') / 1024).toFixed(1);
  console.log(`已生成 ${outFile}`);
  console.log(`  ${out.split('\n').length} 行 / ${kb} KB / ${parts.length} 个模块合并`);
  console.log('  零依赖、零网络请求、零构建产物依赖');
}

main();
