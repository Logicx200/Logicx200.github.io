/* 本地静态服务（只用 node 内置模块）
 *
 * 为什么需要它：
 *   1. 浏览器在 file:// 下会禁止 canvas 读回像素（getImageData 抛 SecurityError），
 *      而侧面颜色条和点云都需要读像素；
 *   2. fetch 示例图在 file:// 下也不允许。
 *
 * 用法：node tools/serve.mjs [port] [rootDir]
 */
import { createServer } from 'node:http';
import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(process.argv[3] || join(here, '..'));
const port = parseInt(process.argv[2] || '8731', 10);

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.bmp': 'image/bmp',
  '.avif': 'image/avif',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain; charset=utf-8'
};

const server = createServer((req, res) => {
  const t0 = Date.now();
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  } catch {
    res.writeHead(400).end('bad url');
    return;
  }
  if (pathname.endsWith('/')) pathname += 'index.html';

  const full = resolve(join(root, normalize(pathname)));
  if (!full.startsWith(root)) {
    res.writeHead(403).end('forbidden');
    return;
  }

  let st;
  try {
    st = statSync(full);
    if (st.isDirectory()) throw new Error('dir');
  } catch {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' }).end('404 ' + pathname);
    console.log(`404 ${pathname}`);
    return;
  }

  res.writeHead(200, {
    'content-type': TYPES[extname(full).toLowerCase()] || 'application/octet-stream',
    'content-length': st.size,
    'cache-control': 'no-store',
    'access-control-allow-origin': '*'
  });
  createReadStream(full).pipe(res);
  res.on('finish', () => console.log(`${res.statusCode} ${pathname} ${st.size}B ${Date.now() - t0}ms`));
});

server.on('error', (e) => {
  console.error('服务启动失败：' + e.message);
  process.exit(1);
});

server.listen(port, '127.0.0.1', () => {
  console.log(`时空立方体 · 本地服务`);
  console.log(`  root : ${root}`);
  console.log(`  url  : http://127.0.0.1:${port}/`);
  console.log('  Ctrl+C 停止');
});
