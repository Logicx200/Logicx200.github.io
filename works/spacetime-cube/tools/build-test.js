// 由真实的 index.html 生成 test/index.html：
// 只改写资源路径，并在 <head> 里插一个错误捕获钩子（错误会写进 document.title，
// 这样无头截图时可以通过标题看到运行时异常）。这样测试页永远和真实页面同构。

const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(root, 'index.html'), 'utf8');

const HOOK = `<script>
window.__err = '';
function __logErr(m) { if (!window.__err) window.__err = String(m); document.title = 'CUBE_ERR ' + window.__err; }
window.addEventListener('error', e => __logErr((e.message || 'error') + ' @' + (e.filename || '') + ':' + (e.lineno || 0)));
window.addEventListener('unhandledrejection', e => __logErr('unhandledrejection: ' + ((e.reason && e.reason.message) || e.reason)));
</script>`;

let out = src
  .replace('href="./styles.css"', 'href="../styles.css"')
  .replace('src="./app.js"', 'src="../app.js"')
  // 页面加载后立刻装钩子，尽量早于模块执行
  .replace('<link rel="stylesheet"', HOOK + '\n<link rel="stylesheet"');

// 追加测试外壳（ES module，所以它一定在 app.js 之后执行）
out = out.replace('</body>', '<script type="module" src="./shell.js"></script>\n</body>');

fs.mkdirSync(path.join(root, 'test'), { recursive: true });
fs.writeFileSync(path.join(root, 'test', 'index.html'), out);
console.log('已生成 test/index.html');
