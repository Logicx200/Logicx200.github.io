/**
 * 验证：选错目录时必须明确报错；选对/选上一层时必须能正确解析
 *
 *   node scripts/e2e-pickdir.mjs
 *
 * 用无头浏览器 + File System Access API：
 *   1. 先尝试拿一个真实的目录句柄（无头环境通常拿不到，自动降级为桩对象）
 *   2. 校验逻辑：照片文件夹 → 拒绝；项目根目录 → 找到 public；public → 通过
 */

import fs from 'node:fs/promises';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: {
  url: { type: 'string', default: 'http://127.0.0.1:4199/' },
  port: { type: 'string', default: '9331' },
} });

const results = [];
const check = (label, ok, extra = '') => {
  results.push({ label, ok });
  console.log(`  ${ok ? '✔' : '✖'} ${label}${extra ? ' — ' + extra : ''}`);
};

const version = await (await fetch(`http://127.0.0.1:${values.port}/json/version`)).json();
const ws = new WebSocket(version.webSocketDebuggerUrl);
let seq = 0;
const pending = new Map();
ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    if (m.error) reject(new Error(JSON.stringify(m.error))); else resolve(m.result);
  }
});
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = ++seq;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params, sessionId }));
});
await new Promise((r) => ws.addEventListener('open', r, { once: true }));
const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
const S = (m, p) => send(m, p, sessionId);
await S('Page.enable'); await S('Runtime.enable'); await S('Network.enable');
await S('Network.setCacheDisabled', { cacheDisabled: true });
await S('Page.navigate', { url: values.url });
await new Promise((r) => setTimeout(r, 3000));

const evaluate = async (expr) => {
  const r = await S('Runtime.evaluate', {
    expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true, userGesture: true,
  });
  if (r.exceptionDetails) return 'ERROR: ' + (r.exceptionDetails.exception?.description || '').split('\n')[0];
  return r.result.value;
};

console.log(`打开 ${values.url}\n`);

/* 1. 试试能不能拿到真实目录句柄（无头环境一般会失败） */
const realHandle = await evaluate(`
  try {
    const dir = await window.showDirectoryPicker({ mode: 'readwrite' });
    return JSON.stringify({ ok: true, name: dir.name });
  } catch (e) {
    return JSON.stringify({ ok: false, name: e.name, msg: e.message });
  }
`);
console.log('真实目录句柄：', realHandle);

/* 2. 用桩对象验证三种选择场景 */
const pickTest = await evaluate(`
  const { inspectSiteRoot, findSiteRoots } = await import('/src/site-root.js');

  // 造一个"照片文件夹"：只有照片，没有 index.html
  const photoDir = {
    kind: 'directory', name: '照片归档',
    async getFileHandle() { const e = new Error('nf'); e.name = 'NotFoundError'; throw e; },
    async getDirectoryHandle() { const e = new Error('nf'); e.name = 'NotFoundError'; throw e; },
    async *entries() {
      yield ['2024年', { kind: 'directory', name: '2024年' }];
      yield ['DSC01234.JPG', { kind: 'file', name: 'DSC01234.JPG' }];
    },
  };

  // 造一个"项目根目录"：里面只有合格的 public
  const siteHtml = '<!DOCTYPE html><html data-pj-site="photo-journal"><body><section id="view-import"></section></body></html>';
  const publicDir = {
    kind: 'directory', name: 'public',
    async getFileHandle(n) {
      if (n === 'site-id.txt') return { text: 'photo-journal site root' };
      if (n === 'index.html') return { text: siteHtml };
      const e = new Error('nf'); e.name = 'NotFoundError'; throw e;
    },
    async getDirectoryHandle() { const e = new Error('nf'); e.name = 'NotFoundError'; throw e; },
    async *entries() {
      yield ['index.html', { kind: 'file', name: 'index.html' }];
      yield ['assets', { kind: 'directory', name: 'assets' }];
    },
  };
  const projectRoot = {
    kind: 'directory', name: 'photo-journal',
    async getFileHandle() { const e = new Error('nf'); e.name = 'NotFoundError'; throw e; },
    async getDirectoryHandle(n) { if (n === 'public') return publicDir; const e = new Error('nf'); e.name = 'NotFoundError'; throw e; },
    async *entries() {
      yield ['public', publicDir];
      yield ['src', { kind: 'directory', name: 'src' }];
      yield ['package.json', { kind: 'file', name: 'package.json' }];
    },
  };

  const photoCheck = await inspectSiteRoot(photoDir);
  const rootCheck = await inspectSiteRoot(projectRoot);
  const publicCheck = await inspectSiteRoot(publicDir);
  const found = await findSiteRoots(projectRoot);

  return JSON.stringify({
    photo: photoCheck,
    projectRoot: rootCheck,
    publicDir: publicCheck,
    foundFromRoot: found.map(f => f.label),
  });
`);
const t = JSON.parse(pickTest);
check('选中照片文件夹 → 被拒绝', t.photo.ok === false, JSON.stringify(t.photo));
check('拒绝原因说明了"没有 index.html"', /index\.html/.test(t.photo.reason || ''), t.photo.reason);
check('选中 public 目录 → 通过', t.publicDir.ok === true, JSON.stringify(t.publicDir));
check('选中项目根目录 → 能从中找到 public', t.foundFromRoot.includes('public'), JSON.stringify(t.foundFromRoot));

/* 3. 选错时页面上的提示是否醒目且持久（走真实的 showWriteResult） */
const uiFeedback = await evaluate(`
  const pj = window.__pj;
  const view = pj && pj.importView;
  if (!view || typeof view.showWriteResult !== 'function') {
    return JSON.stringify({ ok: false, reason: '页面没有暴露 showWriteResult' });
  }

  // 模拟真实场景：用户失败后切到了相册页并刷新
  pj.setView('grid');
  await new Promise(r => setTimeout(r, 200));

  view.showWriteResult('你选择的是「照片归档」，目录里没有 index.html，看起来不是站点根目录。请选择本项目里的 public 目录。', false);
  await new Promise(r => setTimeout(r, 200));

  const banner = document.querySelector('#global-banner');
  const bText = document.querySelector('#global-banner-text');
  const bRect = banner.getBoundingClientRect();
  const el = document.querySelector('#imp-write-result');

  return JSON.stringify({
    ok: true,
    importViewHidden: document.querySelector('#view-import').hidden,
    bannerVisible: !banner.hidden,
    bannerHeight: Math.round(bRect.height),
    bannerText: bText.textContent.slice(0, 80),
    persisted: Boolean(localStorage.getItem('pj-last-write-result')),
    resultBoxHasHeight: Math.round(el.getBoundingClientRect().height),
  });
`);
const u = JSON.parse(uiFeedback);
check('在相册页（导入页隐藏）也能看到失败横幅',
  u.ok && u.importViewHidden && u.bannerVisible && u.bannerHeight > 20, uiFeedback);
check('失败横幅说明了原因', /没有 index\.html/.test(u.bannerText || ''), u.bannerText);
check('失败结果会保留（刷新后仍能看到）', u.persisted === true, uiFeedback);

/* 4. 日志面板可用 */
const logTest = await evaluate(`
  const el = document.querySelector('#imp-log');
  if (!el) return JSON.stringify({ ok: false });
  // 触发一次诊断，看日志是否会写出来
  document.querySelector('.tab[data-view="import"]').click();
  await new Promise(r => setTimeout(r, 200));
  document.querySelector('#imp-diagnose').click();
  await new Promise(r => setTimeout(r, 2000));
  return JSON.stringify({ ok: true, hidden: el.hidden, len: el.textContent.length, head: el.textContent.slice(0, 60) });
`);
const l = JSON.parse(logTest);
check('诊断日志会显示在页面上', l.ok && !l.hidden && l.len > 100, logTest);

console.log('');
const failed = results.filter((r) => !r.ok);
console.log(`选错目录行为验证：${results.length - failed.length}/${results.length} 通过`);
if (failed.length) for (const f of failed) console.log('  - ' + f.label);

await send('Target.closeTarget', { targetId });
ws.close();
process.exitCode = failed.length ? 1 : 0;
