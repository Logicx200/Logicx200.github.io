// 语法自检：用 node 内置的 vm 在进程内解析，不起子进程
// （这个沙箱禁止用管道捕获子进程输出，spawn 也是 EPERM）。
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..');

const ESM = ['app.js', 'loader.js', 'shader.js', 'test/selftest.js', 'test/shell.js'];
const CJS = ['server.js', 'tools/png.js', 'tools/make-sample.js', 'tools/build-test.js', 'tools/syntax-check.js'];

const lines = [];
let bad = 0;

function report(kind, f, err) {
  if (!err) { lines.push(`ok    ${f}  (${kind})`); return; }
  bad++;
  lines.push(`FAIL  ${f}  (${kind})\n      ${String(err.message).split('\n')[0]}`);
}

for (const f of ESM) {
  const full = path.join(ROOT, f);
  if (!fs.existsSync(full)) { report('esm', f, new Error('文件不存在')); continue; }
  try {
    // 只解析不执行：构造 SourceTextModule 会做语法检查
    new vm.SourceTextModule(fs.readFileSync(full, 'utf8'), { identifier: full });
    report('esm', f, null);
  } catch (e) {
    report('esm', f, e);
  }
}

for (const f of CJS) {
  const full = path.join(ROOT, f);
  if (!fs.existsSync(full)) { report('cjs', f, new Error('文件不存在')); continue; }
  try {
    new vm.Script(fs.readFileSync(full, 'utf8'), { filename: full });
    report('cjs', f, null);
  } catch (e) {
    report('cjs', f, e);
  }
}

lines.push('');
lines.push(bad ? `${bad} 个文件语法有误` : `全部 ${ESM.length + CJS.length} 个文件语法检查通过`);
const out = lines.join('\n');
try { fs.writeFileSync(path.join(__dirname, 'syntax-report.txt'), out, 'utf8'); } catch (_) {}
console.log(out);
process.exit(bad ? 1 : 0);
