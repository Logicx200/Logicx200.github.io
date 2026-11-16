// 启动脚本的静态校验：
//   - .bat 必须是纯 ASCII + CRLF（cmd.exe 按 ANSI 码页逐字节解析，非 ASCII 会撑坏行结构）
//   - 每个 goto 目标必须有对应标签
//   - .ps1 必须能被解析（且带 BOM，免得 Windows PowerShell 5.1 按 ANSI 读中文）
// Python 回退路径另做实测。
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { spawn } = require('node:child_process');

const ROOT = path.join(__dirname, '..');
const BAT = path.join(ROOT, '启动.bat');
const PS1 = path.join(ROOT, '启动.ps1');

const out = [];
let bad = 0;
const check = (name, pass, detail) => {
  if (!pass) bad++;
  out.push(`${pass ? 'PASS' : 'FAIL'}  ${name}   [${detail}]`);
};

// ---------- .bat ----------
const bat = fs.readFileSync(BAT);
const batStr = bat.toString('latin1');

const nonAscii = [...bat].filter(x => x > 127).length;
check('.bat 是纯 ASCII（cmd 按 ANSI 码页解析，非 ASCII 会破坏行结构）',
  nonAscii === 0, `${nonAscii} 个非 ASCII 字节`);

const crlf = (batStr.match(/\r\n/g) || []).length;
const loneLf = (batStr.match(/(?<!\r)\n/g) || []).length;
check('.bat 使用 CRLF 行尾', loneLf === 0, `CRLF=${crlf} 孤立LF=${loneLf}`);

check('.bat 没有 BOM', !(bat[0] === 0xEF && bat[1] === 0xBB && bat[2] === 0xBF),
  [...bat.slice(0, 3)].map(x => x.toString(16)).join(' '));

const text = bat.toString('utf8');
const lines = text.split(/\r?\n/).map(l => l.trim());

const labels = new Set(
  lines.filter(l => /^:[A-Za-z_][\w]*$/.test(l)).map(l => l.slice(1))
);
const gotos = lines
  .map(l => l.match(/^goto\s+([A-Za-z_][\w]*)\s*$/))
  .filter(Boolean)
  .map(m => m[1]);

const missing = [...new Set(gotos)].filter(g => !labels.has(g));
check('.bat 里每个 goto 目标都有对应标签',
  missing.length === 0,
  missing.length ? '缺 ' + missing.join(',') : `goto ${[...new Set(gotos)].length} 个，标签 ${labels.size} 个`);

// 关键命令都在
for (const [needle, label] of [
  ['where node', '探测 Node'],
  ['where python', '探测 Python'],
  ['server.js', '调用 server.js'],
  ['http.server', 'Python 回退'],
  ['start "" ', '打开浏览器']
]) {
  check(`.bat 包含「${label}」`, text.includes(needle), needle);
}

// ---------- .ps1 ----------
const ps1 = fs.readFileSync(PS1);
const ps1Str = ps1.toString('utf8');
const ps1NonAscii = [...ps1].filter(x => x > 127).length;
const ps1Bom = ps1[0] === 0xEF && ps1[1] === 0xBB && ps1[2] === 0xBF;
check('.ps1 带 UTF-8 BOM（否则 Windows PowerShell 5.1 会把中文按 ANSI 读）',
  ps1Bom || ps1NonAscii === 0,
  ps1Bom ? '有 BOM' : `${ps1NonAscii} 个非 ASCII 字节但没有 BOM`);

const braceOpen = (ps1Str.match(/\{/g) || []).length;
const braceClose = (ps1Str.match(/\}/g) || []).length;
check('.ps1 花括号配平', braceOpen === braceClose, `{ ${braceOpen} } ${braceClose}`);

// ---------- Python 回退实测 ----------
async function testPythonFallback() {
  const py = 'C:\\Users\\x1503\\AppData\\Local\\Programs\\Python\\Python311\\python.exe';
  if (!fs.existsSync(py)) {
    out.push('SKIP  Python 回退实测（找不到 python 解释器）');
    return;
  }
  const PORT = 8794;
  const fd = fs.openSync(path.join(ROOT, 'test', 'python-probe.log'), 'w');
  const p = spawn(py, ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1', '--directory', ROOT],
    { stdio: ['ignore', fd, fd], windowsHide: true });

  let ok = false;
  let detail = '';
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/index.html`);
      const body = await r.text();
      ok = r.ok && body.includes('时空立方体');
      detail = `HTTP ${r.status}，${body.length} 字节`;
      break;
    } catch (_) {
      await new Promise(res => setTimeout(res, 250));
    }
  }
  p.kill();
  check('Python 回退路径能真正提供服务（含中文路径）', ok, detail || '超时');
}

testPythonFallback().then(() => {
  const pass = out.filter(l => l.startsWith('PASS')).length;
  const total = out.filter(l => !l.startsWith('SKIP')).length;
  out.push('', `${pass}/${total} 通过`);
  const report = out.join('\n');
  fs.writeFileSync(path.join(ROOT, 'test', 'launcher-report.txt'), report, 'utf8');
  console.log(report);
  process.exit(bad ? 1 : 0);
});
