// 端到端冒烟测试：进程内起服务，验证页面依赖的每个资源都能取到、类型正确，
// 并确认 CDN 上的 Three.js 确实导出了我们用到的那些符号。
//
// 用法： node tools/smoke.js

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const PORT = 8792;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.png': 'image/png'
};

function startServer() {
  const server = http.createServer((req, res) => {
    let p;
    try { p = decodeURIComponent(new URL(req.url, 'http://x').pathname); }
    catch (_) { res.writeHead(400).end('bad'); return; }
    if (p === '/') p = '/index.html';
    const target = path.resolve(ROOT, '.' + p);
    if (target !== ROOT && !target.startsWith(ROOT + path.sep)) { res.writeHead(403).end(); return; }
    fs.stat(target, (e, st) => {
      if (e || !st.isFile()) { res.writeHead(404).end('404'); return; }
      res.writeHead(200, {
        'Content-Type': MIME[path.extname(target).toLowerCase()] || 'application/octet-stream',
        'Content-Length': st.size
      });
      fs.createReadStream(target).pipe(res);
    });
  });
  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(PORT, '127.0.0.1', () => resolve(server));
  });
}

const results = [];
function check(name, pass, detail) {
  results.push({ name, pass: !!pass, detail: String(detail) });
}

async function main() {
  const server = await startServer();
  const base = `http://127.0.0.1:${PORT}`;

  // 1) 真实页面依赖的静态资源
  const assets = [
    ['/index.html', 'text/html', '主页面'],
    ['/styles.css', 'text/css', '样式'],
    ['/app.js', 'javascript', '主程序'],
    ['/loader.js', 'javascript', '数据管线'],
    ['/shader.js', 'javascript', '着色器'],
    ['/test/index.html', 'text/html', '无头测试页'],
    ['/sample/frame_000.png', 'image/png', '样本图'],
    ['/sample/frame_023.png', 'image/png', '样本图（末帧）']
  ];

  for (const [url, wantType, label] of assets) {
    try {
      const r = await fetch(base + url);
      const type = r.headers.get('content-type') || '';
      const body = await r.arrayBuffer();
      check(`资源可取 ${url}（${label}）`,
        r.ok && type.includes(wantType) && body.byteLength > 50,
        `${r.status} ${type} ${body.byteLength}B`);
    } catch (e) {
      check(`资源可取 ${url}（${label}）`, false, e.message);
    }
  }

  // 2) index.html 里的关键结构
  const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  const neededIds = ['view', 'file', 'open', 'sort', 'mode', 'alpha', 'threshold',
    'quality', 'reset', 'veil', 'fatal'];
  const missing = neededIds.filter(id => !html.includes(`id="${id}"`));
  check('index.html 包含 app.js 需要的全部元素 id', missing.length === 0,
    missing.length ? '缺 ' + missing.join(',') : `${neededIds.length} 个都在`);

  check('index.html 用 importmap 固定了 three 版本',
    /"three"\s*:\s*"https:\/\/cdn\.jsdelivr\.net\/npm\/three@[\d.]+/.test(html),
    (html.match(/three@[\d.]+/) || ['未找到'])[0]);

  // 3) app.js 与各个本地模块之间的导入是否自洽
  //    通用做法：从 app.js 里发现所有 `from './xxx.js'`，再逐个核对导出符号。
  //    不要硬编码模块名 —— 新增一个模块就会被漏掉（fit.js 就是这么漏的）。
  const app = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
  const loader = fs.readFileSync(path.join(ROOT, 'loader.js'), 'utf8');
  const shader = fs.readFileSync(path.join(ROOT, 'shader.js'), 'utf8');

  const exportsOf = src => {
    const out = new Set();
    for (const m of src.matchAll(/export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)/g)) {
      out.add(m[1]);
    }
    // export { a, b as c } 形式
    for (const m of src.matchAll(/export\s*\{([^}]+)\}/g)) {
      for (const part of m[1].split(',')) {
        const name = part.trim().split(/\s+as\s+/).pop().trim();
        if (name) out.add(name);
      }
    }
    return out;
  };

  const localModules = new Set(
    [...app.matchAll(/from\s*'\.\/([\w.-]+\.js)'/g)].map(m => m[1])
  );
  const exportsByModule = new Map();
  for (const mod of localModules) {
    const p = path.join(ROOT, mod);
    exportsByModule.set(mod, fs.existsSync(p) ? exportsOf(fs.readFileSync(p, 'utf8')) : null);
  }

  const appImports = [...app.matchAll(/import\s*\{([^}]+)\}\s*from\s*'\.\/([\w.-]+\.js)'/g)]
    .flatMap(m => m[1].split(',').map(s => s.trim()).filter(Boolean).map(sym => ({ sym, from: m[2] })));

  const badImports = appImports.filter(({ sym, from }) => {
    const pool = exportsByModule.get(from);
    return !pool || !pool.has(sym);
  });
  check('app.js 从各个本地模块导入的符号都存在',
    badImports.length === 0,
    badImports.length
      ? badImports.map(b => `${b.from}:${b.sym}`).join(', ')
      : `${localModules.size} 个模块 / ${appImports.length} 个符号：`
        + appImports.map(i => i.sym).join(', '));

  // 4) CDN 上的 Three.js 是否导出我们实际用到的符号
  const usedThree = [...app.matchAll(/THREE\.([A-Za-z_$][\w$]*)/g)].map(m => m[1]);
  const uniqueThree = [...new Set(usedThree)];
  const coreUrl = (html.match(/"three"\s*:\s*"([^"]+)"/) || [])[1];
  let coreSrc = '';          // 后面第 9 步还要用它查 renderer 成员
  if (!coreUrl) {
    check('CDN Three.js 可下载', false, 'importmap 里没找到 three');
  } else {
    try {
      const r = await fetch(coreUrl);
      coreSrc = await r.text();
      const notExported = uniqueThree.filter(sym =>
        !new RegExp(`(export\\s*\\{[^}]*\\b${sym}\\b|export\\s+(class|function|const)\\s+${sym}\\b)`).test(coreSrc));
      check('CDN Three.js 导出了用到的每个符号',
        r.ok && notExported.length === 0,
        r.ok ? (notExported.length ? '未导出: ' + notExported.join(',') : uniqueThree.join(','))
          : 'HTTP ' + r.status);
    } catch (e) {
      check('CDN Three.js 可下载', false, e.message);
    }
  }

  // 5) 着色器里引用的 uniform 是否都在 app.js 里提供了
  const shaderUniforms = [...shader.matchAll(/uniform\s+\w+\s+(u[A-Za-z]\w*)\s*;/g)].map(m => m[1]);
  const declaredInApp = [...app.matchAll(/(u[A-Za-z]\w*)\s*:\s*\{\s*value/g)].map(m => m[1]);
  const missingUniforms = [...new Set(shaderUniforms)].filter(u => !declaredInApp.includes(u));
  check('shader.js 声明的 uniform 都在 app.js 的 uniforms 里提供了',
    missingUniforms.length === 0,
    missingUniforms.length ? '缺 ' + missingUniforms.join(',')
      : `${[...new Set(shaderUniforms)].length} 个都齐`);

  // 6) 反向检查：着色器正文里用到的每个 u* 都必须有 uniform 声明。
  //    漏声明会直接导致 GLSL 编译失败 —— 那会让画面全空、而 JS 一切正常，
  //    是最难从外部察觉的一类故障，所以必须静态查出来。
  const declaredSet = new Set(shaderUniforms);
  const usedIds = new Set((shader.match(/\b(?:u[A-Z][A-Za-z0-9_]*|uVolume)\b/g) || []));
  const undeclared = [...usedIds].filter(id => !declaredSet.has(id));
  check('shader.js 用到的每个 u* 标识符都有 uniform 声明',
    undeclared.length === 0,
    undeclared.length
      ? '未声明就使用: ' + undeclared.join(',')
      : `${usedIds.size} 个标识符全部已声明`);

  // 7) app.js 提供的 uniform 是否都被着色器声明了（多余的无害，但值得知道）
  const unusedInShader = declaredInApp.filter(u => !declaredSet.has(u) && u !== 'uVolume');
  check('app.js 没有提供着色器不认识的 uniform',
    unusedInShader.length === 0,
    unusedInShader.length ? '多余: ' + unusedInShader.join(',') : '一致');

  // 8) ---- DOM 契约：HTML 里的 id 与 JS 里的引用必须对得上 ----
  // 这一条是因为删掉帧滑块时漏删了一句 `ui.frame.max = ...`，
  // 结果载入照片直接抛 "Cannot set properties of undefined" 而加的。
  // 纯字符串 id 的松散引用，没有静态检查就是定时炸弹。
  const htmlIds = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));

  // 8a) app.js 里 el('xxx') 引用的 id 必须存在
  const elRefs = [...new Set([...app.matchAll(/\bel\('([^']+)'\)/g)].map(m => m[1]))];
  const missingEl = elRefs.filter(id => !htmlIds.has(id));
  check('app.js 里 el(...) 引用的 id 都存在于 index.html',
    missingEl.length === 0,
    missingEl.length ? '缺: ' + missingEl.join(',') : `${elRefs.length} 个 id`);

  // 8b) ui 表里的每个元素都要能在 index.html 里找到
  const uiBlock = (app.match(/const ui = \{([\s\S]*?)\n\};/) || [])[1] || '';
  const uiMap = [...uiBlock.matchAll(/(\w+):\s*el\('([^']+)'\)/g)].map(m => ({ key: m[1], id: m[2] }));
  const badUi = uiMap.filter(u => !htmlIds.has(u.id));
  check('ui 表里的元素都能在 index.html 里找到',
    badUi.length === 0,
    badUi.length ? '缺: ' + badUi.map(u => `${u.key}->${u.id}`).join(',') : `${uiMap.length} 个`);

  // 8c) 反向：任何 `ui.xxx` 引用都必须在该表里 —— 这正是漏删那句犯的错
  const uiKeys = new Set(uiMap.map(u => u.key));
  const uiUsed = new Set([...app.matchAll(/\bui\.(\w+)/g)].map(m => m[1]));
  const uiMissing = [...uiUsed].filter(k => !uiKeys.has(k));
  check('没有引用 ui 表之外的成员（删元素后漏删引用会被抓出来）',
    uiMissing.length === 0,
    uiMissing.length ? '未定义: ui.' + uiMissing.join(', ui.') : `${uiUsed.size} 个引用全部有定义`);

  // 9) app.js 用到的 renderer 成员在 three 里是否存在
  if (coreSrc) {
    const rendererMembers = [...new Set([...app.matchAll(/renderer\.(\w+)/g)].map(m => m[1]))];
    const badMembers = rendererMembers.filter(mem => !new RegExp(`this\\.${mem}\\b`).test(coreSrc));
    check('app.js 用到的 renderer 成员在 three 里都存在',
      badMembers.length === 0,
      badMembers.length ? '不存在: ' + badMembers.join(',') : rendererMembers.join(','));
  }

  server.close();

  const pass = results.filter(r => r.pass).length;
  const lines = ['', '============ 冒烟测试 ============'];
  for (const r of results) lines.push((r.pass ? 'PASS  ' : 'FAIL  ') + r.name + '   [' + r.detail + ']');
  lines.push('', `${pass}/${results.length} 通过`);
  const out = lines.join('\n');
  fs.writeFileSync(path.join(ROOT, 'test', 'smoke-report.txt'), out, 'utf8');
  console.log(out);
  process.exit(pass === results.length ? 0 : 1);
}

main().catch(e => {
  console.error('冒烟测试崩溃:', e);
  process.exit(2);
});
