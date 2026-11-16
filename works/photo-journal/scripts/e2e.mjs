/**
 * 端到端自检：用 DevTools 协议驱动无头 Edge/Chrome，验证站点各视图真的能渲染
 *
 *   node scripts/e2e.mjs [--url http://127.0.0.1:4199/] [--port 9331]
 *
 * 前置：先用 --remote-debugging-port 启动浏览器（见 README）。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';

const { values } = parseArgs({
  options: {
    url: { type: 'string', default: 'http://127.0.0.1:4199/' },
    port: { type: 'string', default: '9331' },
    shots: { type: 'string', default: '.cache' },
  },
});

const BASE = values.url.replace(/\/$/, '');
const PORT = values.port;
const SHOT_DIR = values.shots;

/* 自检需要一个已经有照片的站点；仓库里默认不带演示数据，这里自动造一份 */
async function ensureDemoSite() {
  const hasData = await fs.stat('public/data/index.json').then(() => true, () => false);
  if (hasData) return false;
  console.log('（站点还没有数据，先用演示照片自动生成一份…）');
  const { execFileSync } = await import('node:child_process');
  execFileSync(process.execPath, ['scripts/make-demo.mjs'], { stdio: 'inherit' });
  execFileSync(process.execPath, ['scripts/import.mjs', '--src', 'demo-archive', '--copy', '--clean'], { stdio: 'inherit' });
  return true;
}
const createdDemo = await ensureDemoSite();
if (createdDemo) console.log('');

const version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json();
const ws = new WebSocket(version.webSocketDebuggerUrl);
let seq = 0;
const pending = new Map();
const logs = [];

ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    if (m.error) reject(new Error(JSON.stringify(m.error))); else resolve(m.result);
  } else if (m.method === 'Runtime.exceptionThrown') {
    logs.push('异常: ' + (m.params?.exceptionDetails?.exception?.description || m.params?.exceptionDetails?.text || '').split('\n')[0]);
  } else if (m.method === 'Runtime.consoleAPICalled' && m.params?.type === 'error') {
    logs.push('console.error: ' + (m.params.args || []).map((a) => a.value ?? a.description ?? '').join(' '));
  } else if (m.method === 'Log.entryAdded' && m.params?.entry?.level === 'error') {
    logs.push('网络/日志错误: ' + m.params.entry.text + ' ' + (m.params.entry.url || ''));
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

await S('Page.enable');
await S('Runtime.enable');
await S('Log.enable').catch(() => {});
await S('Network.enable');
await S('Network.setCacheDisabled', { cacheDisabled: true });
await S('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function evaluate(expr) {
  const r = await S('Runtime.evaluate', { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}

async function waitFor(expr, timeout = 15000, label = expr) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await evaluate(`return Boolean(${expr});`)) return true;
    await sleep(200);
  }
  console.log(`  ✖ 等待超时：${label}`);
  return false;
}

async function shot(name) {
  const r = await S('Page.captureScreenshot', { format: 'png' });
  await fs.mkdir(SHOT_DIR, { recursive: true });
  const file = path.join(SHOT_DIR, name);
  await fs.writeFile(file, Buffer.from(r.data, 'base64'));
  return file;
}

const results = [];
const check = (label, ok, extra = '') => {
  results.push({ label, ok, extra });
  console.log(`  ${ok ? '✔' : '✖'} ${label}${extra ? ' — ' + extra : ''}`);
};

/* ---------------- 0. 首页点云 ---------------- */
console.log('首页点云：');
await S('Page.navigate', { url: `${BASE}/` });
logs.length = 0;

check('默认停在首页', await waitFor(`window.__pj && window.__pj.state.view === 'home'`, 20000, '首页'));

let homeInfo = null;
for (let i = 0; i < 30; i++) {
  homeInfo = JSON.parse(await evaluate(`
    const c = document.querySelector('#pointcloud');
    const ctx = c.getContext('2d');
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let lit = 0;
    for (let k = 3; k < d.length; k += 4 * 211) if (d[k] > 8) lit++;
    return JSON.stringify({
      lit,
      w: c.width, h: c.height,
      points: window.__pj.home ? window.__pj.home.pointCount : 0,
      meta: document.querySelector('#home-meta').innerText.replace(/\\s+/g, ' ').slice(0, 120),
      hasTitle: !!document.querySelector('#home-meta h3'),
      loading: document.querySelector('#home-loading').hidden,
      total: window.__pj.home ? window.__pj.home.total() : 0,
    });`));
  if (homeInfo.lit > 40 && homeInfo.hasTitle && homeInfo.loading) break;
  await sleep(500);
}
check('点云已渲染出内容', homeInfo.lit > 40 && homeInfo.points > 5000, JSON.stringify({ lit: homeInfo.lit, points: homeInfo.points }));
check('拍摄参数面板有内容', homeInfo.hasTitle && homeInfo.meta.length > 20, homeInfo.meta);

const homeInteract = await evaluate(`
  const c = document.querySelector('#pointcloud');
  const r = c.getBoundingClientRect();
  const before = c.getContext('2d').getImageData(0, 0, 200, 200).data.join('').length;
  const mk = (type, x, y) => c.dispatchEvent(new PointerEvent(type, {
    bubbles: true, cancelable: true, pointerId: 1, clientX: x, clientY: y,
  }));
  mk('pointerdown', r.left + r.width / 2, r.top + r.height / 2);
  for (let i = 1; i <= 8; i++) mk('pointermove', r.left + r.width / 2 + i * 15, r.top + r.height / 2 + i * 5);
  mk('pointerup', r.left + r.width / 2 + 120, r.top + r.height / 2 + 40);
  await new Promise(res => setTimeout(res, 700));
  return JSON.stringify({ ok: true, before });
`);
check('拖动旋转不报错', JSON.parse(homeInteract).ok === true, homeInteract);

const shuffled = await evaluate(`
  const before = document.querySelector('#home-meta h3').textContent;
  let changed = false;
  for (let i = 0; i < 5 && !changed; i++) {
    await window.__pj.home.randomNew();
    await new Promise(res => setTimeout(res, 1200));
    if (document.querySelector('#home-meta h3').textContent !== before) changed = true;
  }
  return JSON.stringify({ before, after: document.querySelector('#home-meta h3').textContent, changed });
`);
check('「换一张」能换到别的照片', JSON.parse(shuffled).changed === true, shuffled);

await shot('00-home.png');

// 从首页进入相册
await evaluate(`document.querySelector('#home-enter').click();`);
await sleep(800);
check('「进入相册」按钮生效', await evaluate(`return window.__pj.state.view === 'grid';`));

// 等高行布局：趁相册刚显示时就量（隐藏时宽度是 0，量不出东西）
const layout = JSON.parse(await evaluate(`
  await new Promise(r => setTimeout(r, 400));
  const rows = [...document.querySelectorAll('.grid-row')];
  const w = document.querySelector('#grid').clientWidth;
  return JSON.stringify({
    containerW: Math.round(w),
    rows: rows.length,
    widths: rows.slice(0, 4).map(r => Math.round(r.getBoundingClientRect().width)),
  });`));

/* ---------------- 1. 首屏 ---------------- */
console.log('');
console.log('相册与其它视图：');
console.log(`打开 ${BASE}/`);
await S('Page.navigate', { url: `${BASE}/` });
logs.length = 0;

check('首屏渲染出照片卡片', await waitFor(`document.querySelectorAll('#grid .card').length >= 8`, 20000, '至少 8 张卡片'));
let st = await evaluate(`return {
  cards: document.querySelectorAll('#grid .card').length,
  rows: document.querySelectorAll('.grid-row').length,
  title: document.querySelector('#site-title').textContent,
  sub: document.querySelector('#site-sub').textContent,
  summary: document.querySelector('#grid-summary').textContent,
  review: document.querySelector('#review-count').textContent,
  facets: document.querySelectorAll('#filters .chip').length,
  total: window.__pj.state.photos.length,
  filtered: window.__pj.state.filtered.length,
};`);
check('标题与统计正确',
  st.title.includes('摄影记录') && st.sub.includes(`${st.total} 张照片`),
  JSON.stringify(st));
// 大图库下网格是分块懒渲染的，只能断言"渲染得不比结果集多"，且不能太少
check('网格分块渲染正常', st.cards > 0 && st.cards <= st.filtered, `已渲染 ${st.cards} / 共 ${st.filtered}`);
check('筛选面板已生成', st.facets > 0, `${st.facets} 个筛选项`);

const loaded = await waitFor(`[...document.querySelectorAll('#grid img')].filter(i => i.complete && i.naturalWidth > 0).length >= 8`, 15000, '至少 8 张缩略图加载成功');
check('缩略图真实加载成功（WebP 可解码）', loaded);

// 检查每行宽度是否撑满（等高行布局正确）
check('等高行宽度撑满容器',
  layout.containerW > 200 && layout.widths.length > 0 && layout.widths.every((w) => Math.abs(w - layout.containerW) <= 2),
  JSON.stringify(layout));

await shot('01-grid.png');

/* ---------------- 2. 筛选 + 搜索 ---------------- */
// 从真实数据里挑一个一定能搜到的词（地点/相机/说明都行），避免写死演示数据
const probe = JSON.parse(await evaluate(`
  const list = window.__pj.state.photos;
  const candidates = [];
  const push = (v) => { if (v && String(v).trim().length >= 2) candidates.push(String(v).trim()); };
  for (const p of list) { push(p.l); push(p.c); push(p.x); }
  // 取出现次数最多的那个词，保证命中数量足够
  const counts = new Map();
  for (const c of candidates) counts.set(c, (counts.get(c) || 0) + 1);
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const pick = sorted.find(([, n]) => n >= 2) || sorted[0] || ['', 0];
  return JSON.stringify({ word: pick[0], expected: pick[1], total: list.length });`));
check('能从数据里取到搜索词', probe.word.length >= 2 && probe.expected >= 2, JSON.stringify(probe));

let filtered = null;
if (probe.word) {
  await evaluate(`document.querySelector('#search').value = ${JSON.stringify(probe.word)}; document.querySelector('#search').dispatchEvent(new Event('input'));`);
  await sleep(900);
  filtered = await evaluate(`return {
    n: window.__pj.state.filtered.length,
    cards: document.querySelectorAll('#grid .card').length,
    sum: document.querySelector('#grid-summary').textContent,
  };`);
  check(`搜索「${probe.word}」生效`,
    filtered.n > 0 && filtered.n < probe.total && filtered.sum.includes(`${filtered.n} 张`),
    JSON.stringify(filtered));
} else {
  check('搜索功能', false, '数据里找不到可搜索的词');
}

await evaluate(`document.querySelector('#reset-filters').click();`);
await sleep(700);
// 点击年份筛选（用站点里真实的 2024 年数量来核对）
const year2024 = await evaluate(`return window.__pj.state.photos.filter(p => (p.d || '').startsWith('2024')).length;`);
await evaluate(`
  const chips = [...document.querySelectorAll('#filters .chip')];
  const y = chips.find(c => c.textContent.includes('2024 年'));
  if (y) y.click();
  return !!y;`);
await sleep(900);
filtered = await evaluate(`return {
  n: window.__pj.state.filtered.length,
  pills: document.querySelectorAll('.active-filters .pill').length,
  sum: document.querySelector('#grid-summary').textContent,
};`);
check('按 2024 年筛选生效',
  filtered.n === year2024 && filtered.pills === 1 && filtered.sum.includes(`${year2024} 张`),
  `${JSON.stringify(filtered)}，期望 ${year2024} 张`);
await shot('02-filter-2024.png');

await evaluate(`document.querySelector('#reset-filters').click();`);
await sleep(500);

/* ---------------- 3. 灯箱 ---------------- */
await evaluate(`document.querySelector('#grid .card').click();`);
check('灯箱打开', await waitFor(`!document.querySelector('#lightbox').hidden`, 8000, '灯箱可见'));
const lb = await evaluate(`
  await new Promise(r => setTimeout(r, 1200));
  const info = document.querySelector('#lb-info').textContent;
  return {
    hasImg: !!document.querySelector('#lb-canvas img'),
    hasExif: info.includes('光圈') || info.includes('快门') || info.includes('相机'),
    infoLen: info.length,
    hash: location.hash,
  };`);
check('灯箱显示 EXIF 参数', lb.hasImg && lb.hasExif, JSON.stringify(lb));
await shot('03-lightbox.png');
await evaluate(`document.querySelector('#lightbox [data-act="close"]').click();`);
await waitFor(`document.querySelector('#lightbox').hidden`, 5000, '灯箱关闭');

/* ---------------- 4. 时间轴 ---------------- */
await evaluate(`document.querySelector('.tab[data-view="timeline"]').click();`);
check('时间轴渲染', await waitFor(`document.querySelectorAll('.tl-year').length > 0`, 8000, '年份分组'));
const tl = await evaluate(`return { years: document.querySelectorAll('.tl-year').length, thumbs: document.querySelectorAll('.tl-thumbs img').length };`);
check('时间轴有年份与缩略图', tl.years >= 1 && tl.thumbs > 0, JSON.stringify(tl));
await shot('04-timeline.png');

/* ---------------- 5. 地图 ---------------- */
await evaluate(`document.querySelector('.tab[data-view="map"]').click();`);
await sleep(900);
const map = await evaluate(`
  const c = document.querySelector('#map-canvas');
  const ctx = c.getContext('2d');
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let nonEmpty = 0;
  for (let i = 3; i < d.length; i += 4 * 97) if (d[i] > 0) nonEmpty++;
  return { w: c.width, h: c.height, nonEmpty, legend: document.querySelector('#map-legend').textContent.slice(0, 60) };`);
check('地图画布已绘制内容', map.nonEmpty > 0 && map.w > 0, JSON.stringify(map));
await shot('05-map.png');

/* ---------------- 6. 统计 ---------------- */
await evaluate(`document.querySelector('.tab[data-view="stats"]').click();`);
await sleep(600);
const stats = await evaluate(`return { cards: document.querySelectorAll('.stat-card').length, kpis: document.querySelectorAll('.kpi').length };`);
check('统计视图渲染', stats.cards >= 6 && stats.kpis >= 4, JSON.stringify(stats));
await shot('06-stats.png');

/* ---------------- 7. 待确认 ---------------- */
await evaluate(`document.querySelector('.tab[data-view="review"]').click();`);
await sleep(500);
const review = await evaluate(`return { rows: document.querySelectorAll('.review-row').length, empty: document.querySelector('#review-empty').hidden };`);
check('待确认列表有内容', review.rows > 0, JSON.stringify(review));
await shot('07-review.png');

/* ---------------- 7.5 重复照片 ---------------- */
await evaluate(`document.querySelector('.tab[data-view="dups"]').click();`);
await sleep(800);
const dups = await evaluate(`
  const view = document.querySelector('#view-dups');
  const saved = localStorage.getItem('pj-dup-ignored');
  localStorage.removeItem('pj-dup-ignored');
  return JSON.stringify({
    visible: !view.hidden,
    groups: document.querySelectorAll('.dups-group').length,
    items: document.querySelectorAll('.dup-item').length,
    keepers: document.querySelectorAll('.dup-item.is-keeper').length,
    badge: document.querySelector('#dups-count').textContent,
    hasSliders: !!document.querySelector('#dups-threshold') && !!document.querySelector('#dups-color'),
    hadIgnored: saved,
  });`);
const dp = JSON.parse(dups);
check('「重复」页可切换且有滑块', dp.visible && dp.hasSliders, dups);
check('重复分组渲染出保留项标记', dp.groups === 0 || dp.keepers > 0, dups);
check('重复组数角标已显示', dp.groups === 0 || dp.badge.length > 0, `角标=${dp.badge}`);

await shot('08-dups.png');

/* ---------------- 汇总 ---------------- */
console.log('');

/* 8. 导入后重载：模拟"网页写入完成 → 站点标签同步更新" */
const reloadCheck = await evaluate(`
  // 先制造一些缓存（打开过灯箱、加载过某个月份）
  await window.__pj.store.loadMonth('2024-10');
  const before = {
    title: document.querySelector('#site-title').textContent,
    review: document.querySelector('#review-count').textContent,
    cards: document.querySelectorAll('#grid .card').length,
    monthCache: window.__pj.store.monthCache.size,
  };
  // 强制重新拉取索引（等同写入完成后页面自动刷新数据）
  await window.__pj.reload();
  await new Promise(r => setTimeout(r, 600));
  const after = {
    sub: document.querySelector('#site-sub').textContent,
    review: document.querySelector('#review-count').textContent,
    cards: document.querySelectorAll('#grid .card').length,
    monthCache: window.__pj.store.monthCache.size,
    detailCache: window.__pj.store.detail.size,
    facets: document.querySelectorAll('#filters .chip').length,
  };
  return JSON.stringify({ before, after });
`);
const rc = JSON.parse(reloadCheck);
check('重新加载会清空月份/明细缓存',
  rc.before.monthCache > 0 && rc.after.monthCache === 0 && rc.after.detailCache === 0,
  reloadCheck);
check('重新加载后品牌栏与筛选项同步',
  rc.after.cards > 0 && rc.after.sub.includes('张照片') && rc.after.facets > 0,
  reloadCheck);

if (logs.length) {
  console.log('页面错误日志：');
  for (const l of [...new Set(logs)].slice(0, 10)) console.log('  - ' + l);
} else {
  console.log('页面无 JS 错误 ✔');
}
const realLogs = [...new Set(logs)].filter((l) => !/404 \(Not Found\)/.test(l));
const failed = results.filter((r) => !r.ok);
console.log('');
console.log(`自检结果：${results.length - failed.length}/${results.length} 通过`);
if (failed.length) {
  console.log('失败项：');
  for (const f of failed) console.log('  - ' + f.label + (f.extra ? ' ' + f.extra : ''));
}
if (realLogs.length) console.log(`页面报错 ${realLogs.length} 条（见上）`);

await send('Target.closeTarget', { targetId });
ws.close();
process.exitCode = failed.length || realLogs.length ? 1 : 0;
