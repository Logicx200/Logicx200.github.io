/**
 * 开发辅助：用 Chrome DevTools 协议给运行中的站点截图 / 取渲染结果
 *
 *   node scripts/screenshot.mjs <url> <输出png> [等待选择器] [点击选择器]
 *
 * 需要先启动一个带 --remote-debugging-port 的 Edge/Chrome。
 */

import fs from 'node:fs/promises';
import path from 'node:path';

const [url, outFile, waitFor, clickSel, evalExpr] = process.argv.slice(2);
const port = process.env.CDP_PORT || '9331';

async function json(pathname) {
  const res = await fetch(`http://127.0.0.1:${port}${pathname}`);
  return res.json();
}

const version = await json('/json/version');
const wsUrl = version.webSocketDebuggerUrl;
if (!wsUrl) throw new Error('没有拿到 DevTools WebSocket 地址');

const ws = new WebSocket(wsUrl);
let id = 0;
const pending = new Map();
const events = [];

ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error)));
    else resolve(msg.result);
  } else if (msg.method) {
    events.push(msg);
  }
});

const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const mid = ++id;
  pending.set(mid, { resolve, reject });
  ws.send(JSON.stringify({ id: mid, method, params, sessionId }));
});

await new Promise((resolve) => ws.addEventListener('open', resolve, { once: true }));

// 新建标签页
const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
const S = (m, p) => send(m, p, sessionId);

await S('Page.enable');
await S('Runtime.enable');
await S('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });

await S('Page.navigate', { url });
// 收集控制台与页面异常
await S('Log.enable').catch(() => {});
events.length = 0;   // 只看本次导航之后的事件
// 等 load 事件
await new Promise((resolve) => {
  const t = setTimeout(resolve, 15000);
  const check = setInterval(() => {
    if (events.some((e) => e.method === 'Page.loadEventFired')) { clearInterval(check); clearTimeout(t); resolve(); }
  }, 100);
});

async function evaluate(expr) {
  const r = await S('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' + JSON.stringify(r.exceptionDetails.exception?.description || ''));
  return r.result.value;
}

// 等待应用渲染完成（网格出现卡片，或指定选择器）
const selector = waitFor || '#grid .card';
const deadline = Date.now() + 20000;
let ok = false;
while (Date.now() < deadline) {
  const n = await evaluate(`document.querySelectorAll(${JSON.stringify(selector)}).length`);
  if (n > 0) { ok = true; break; }
  await new Promise((r) => setTimeout(r, 250));
}
console.log(`等待 ${selector} → ${ok ? '已出现' : '超时未出现'}`);

if (clickSel) {
  await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(clickSel)}); if (el) el.click(); return !!el; })()`);
  await new Promise((r) => setTimeout(r, 1200));
}

const info = await evaluate(`JSON.stringify({
  cards: document.querySelectorAll('#grid .card').length,
  rows: document.querySelectorAll('.grid-row').length,
  images: document.querySelectorAll('img').length,
  loadedImgs: [...document.querySelectorAll('#grid img')].filter(i => i.complete && i.naturalWidth > 0).length,
  firstCardH: document.querySelector('#grid .card')?.getBoundingClientRect().height | 0,
  summary: document.querySelector('#grid-summary')?.textContent,
  errors: window.__errors || null,
})`);
console.log('页面状态:', info);

if (evalExpr) {
  console.log('自定义求值:', await evaluate(evalExpr));
}

// 打印控制台错误 / 页面异常
const problems = [];
for (const e of events) {
  if (e.method === 'Runtime.exceptionThrown') {
    problems.push('异常: ' + (e.params?.exceptionDetails?.exception?.description || e.params?.exceptionDetails?.text));
  }
  if (e.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(e.params?.type)) {
    problems.push(`console.${e.params.type}: ` + (e.params.args || []).map((a) => a.value ?? a.description ?? '').join(' '));
  }
  if (e.method === 'Log.entryAdded' && e.params?.entry?.level === 'error') {
    problems.push('日志: ' + e.params.entry.text + ' @ ' + (e.params.entry.url || ''));
  }
}
console.log(problems.length ? '发现 ' + problems.length + ' 条问题:\n  ' + problems.join('\n  ') : '控制台无错误');

if (outFile) {
  const shot = await S('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  await fs.mkdir(path.dirname(outFile), { recursive: true });
  await fs.writeFile(outFile, Buffer.from(shot.data, 'base64'));
  console.log('截图已写入', outFile);
}

await send('Target.closeTarget', { targetId });
ws.close();
