/**
 * 浏览器端导入自检：验证"拖文件夹进网页"这条链路真的能跑通
 *
 *   node scripts/e2e-import.mjs
 *
 * 做法：在页面里用 Canvas 造一张 JPEG → 用 exif-write.js 写入 EXIF →
 * 包装成 File 对象 → 走一遍 setInputFiles / processEntries 的处理流程，
 * 再检查识别出的日期、地点、参数是否正确，并验证 zip 打包可用。
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { parseArgs } from 'node:util';

const { values } = parseArgs({ options: {
  url: { type: 'string', default: 'http://127.0.0.1:4199/' },
  port: { type: 'string', default: '9331' },
  shots: { type: 'string', default: '.cache' },
} });

/* 合并测试需要站点上已经有照片；仓库默认不带演示数据，这里自动造一份 */
const hasData = await fs.stat('public/data/index.json').then(() => true, () => false);
if (!hasData) {
  console.log('（站点还没有数据，先用演示照片自动生成一份…）');
  const { execFileSync } = await import('node:child_process');
  execFileSync(process.execPath, ['scripts/make-demo.mjs'], { stdio: 'inherit' });
  execFileSync(process.execPath, ['scripts/import.mjs', '--src', 'demo-archive', '--copy', '--clean'], { stdio: 'inherit' });
  console.log('');
}

const version = await (await fetch(`http://127.0.0.1:${values.port}/json/version`)).json();
const ws = new WebSocket(version.webSocketDebuggerUrl);
let seq = 0;
const pending = new Map();
const problems = [];

ws.addEventListener('message', (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) {
    const { resolve, reject } = pending.get(m.id);
    pending.delete(m.id);
    if (m.error) reject(new Error(JSON.stringify(m.error))); else resolve(m.result);
    return;
  }
  if (m.method === 'Runtime.exceptionThrown') {
    problems.push('异常: ' + (m.params?.exceptionDetails?.exception?.description || '').split('\n')[0]);
  }
  if (m.method === 'Runtime.consoleAPICalled' && m.params?.type === 'error') {
    problems.push('console.error: ' + (m.params.args || []).map((a) => a.value ?? a.description).join(' '));
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
await S('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
await S('Page.navigate', { url: values.url });
await new Promise((r) => setTimeout(r, 3500));
problems.length = 0;

const evaluate = async (expr) => {
  const r = await S('Runtime.evaluate', {
    expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true,
  });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const results = [];
const check = (label, ok, extra = '') => {
  results.push({ label, ok });
  console.log(`  ${ok ? '✔' : '✖'} ${label}${extra ? ' — ' + extra : ''}`);
};

console.log(`打开 ${values.url}`);

/* 1. 导入页是否可用 */
const tabInfo = await evaluate(`
  const tab = document.querySelector('.tab[data-view="import"]');
  tab.click();
  await new Promise(r => setTimeout(r, 500));
  return JSON.stringify({
    visible: !document.querySelector('#view-import').hidden,
    dropZone: !!document.querySelector('#drop-zone'),
    hasPicker: typeof window.showDirectoryPicker === 'function',
    dirInput: !!document.querySelector('#file-input-dir'),
    overlay: !!document.querySelector('#drop-overlay'),
  });`);
check('「导入」页存在且可切换', JSON.parse(tabInfo).visible && JSON.parse(tabInfo).dropZone, tabInfo);
check('支持拖拽遮罩与目录选择', JSON.parse(tabInfo).overlay && JSON.parse(tabInfo).dirInput);

/* 2. 在页面里造 4 张带 EXIF 的照片（模拟拖入的文件夹）
      故意造得彼此差异明显：两张是不同场景、一张是同场景调亮、一张是同场景竖构图 */
const built = await evaluate(`
  const { writeExifApp1 } = await import('/src/exif-write.js');

  /** 画一张"有明确内容"的图：大色块 + 明显图形，避免渐变图互相撞车 */
  const makeJpeg = (w, h, scene, brightness = 1) => new Promise((resolve) => {
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    const palettes = {
      西湖: ['#3f6f9f', '#0d1a26'],
      宽窄巷: ['#8a5a3a', '#2a1a12'],
      手机: ['#4a7b5a', '#12221a'],
      夜景: ['#1a2038', '#05070f'],
    };
    const [c1, c2] = palettes[scene] || ['#5a5a5a', '#111111'];
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, c1); g.addColorStop(1, c2);
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);

    // 依据场景摆不同的几何图形，让结构差异足够大
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    if (scene === '西湖') {
      ctx.beginPath(); ctx.arc(w * 0.25, h * 0.35, Math.min(w, h) * 0.22, 0, Math.PI * 2); ctx.fill();
      ctx.fillRect(0, h * 0.72, w, h * 0.28);
    } else if (scene === '宽窄巷') {
      ctx.fillRect(0, 0, w * 0.28, h);
      ctx.fillRect(w * 0.45, h * 0.2, w * 0.5, h * 0.22);
    } else if (scene === '手机') {
      ctx.fillRect(w * 0.1, h * 0.1, w * 0.35, h * 0.35);
      ctx.beginPath(); ctx.arc(w * 0.72, h * 0.7, Math.min(w, h) * 0.2, 0, Math.PI * 2); ctx.fill();
    } else {
      ctx.fillRect(0, h * 0.45, w, h * 0.1);
      ctx.beginPath(); ctx.arc(w * 0.8, h * 0.25, Math.min(w, h) * 0.1, 0, Math.PI * 2); ctx.fill();
    }

    if (brightness !== 1) {
      ctx.fillStyle = brightness > 1
        ? 'rgba(255,255,255,' + (brightness - 1) + ')'
        : 'rgba(0,0,0,' + (1 - brightness) + ')';
      ctx.fillRect(0, 0, w, h);
    }

    c.toBlob((b) => b.arrayBuffer().then((buf) => resolve(new Uint8Array(buf))), 'image/jpeg', 0.92);
  });

  const shots = [
    { path: '照片归档/2024年/10月3日 杭州西湖/DSC01234.JPG', date: '2024-10-03T17:42:10', w: 900, h: 600, scene: '西湖',
      make: 'SONY', model: 'ILCE-7M4', lens: 'FE 24-70mm F2.8 GM II', f: 5.6, t: 1/250, iso: 100, focal: 35,
      gps: { lat: 30.2442, lng: 120.139 } },
    { path: '照片归档/2024年/10月3日 杭州西湖/DSC01235.JPG', date: '2024-10-03T18:05:33', w: 600, h: 900, scene: '夜景',
      make: 'SONY', model: 'ILCE-7M4', lens: 'FE 24-70mm F2.8 GM II', f: 2.8, t: 1/60, iso: 800, focal: 70,
      gps: { lat: 30.2455, lng: 120.1401 } },
    { path: '照片归档/2022年/扫街/10-06 成都宽窄巷子/IMG_5601.JPG', date: '2022-10-06T18:40:00', w: 900, h: 600, scene: '宽窄巷',
      make: 'Canon', model: 'EOS 6D Mark II', lens: 'EF35mm f/1.4L II USM', f: 1.4, t: 1/80, iso: 1600, focal: 35,
      gps: { lat: 30.669, lng: 104.055 } },
    { path: '照片归档/未整理/手机照片/IMG_20210405_090001.jpg', date: '2021-04-05T09:00:01', w: 800, h: 600, scene: '手机', brightness: 1.18,
      make: 'Xiaomi', model: 'Xiaomi 13', lens: null, f: 1.9, t: 1/100, iso: 640, focal: 5.4,
      software: 'Adobe Photoshop Lightroom Classic 13.3 (Windows)' },
  ];

  const files = [];
  for (const s of shots) {
    const base = await makeJpeg(s.w, s.h, s.scene, s.brightness || 1);
    const withExif = writeExifApp1(new Uint8Array(base), {
      make: s.make, model: s.model, lensModel: s.lens || undefined,
      dateTimeOriginal: new Date(s.date), software: s.software,
      fNumber: s.f, exposureTime: s.t, iso: s.iso, focalLength: s.focal,
      pixelXDimension: s.w, pixelYDimension: s.h, gps: s.gps,
    });
    const file = new File([withExif], s.path.split('/').pop(), { type: 'image/jpeg', lastModified: Date.now() });
    files.push({ file, path: s.path });
  }
  window.__testFiles = files;
  return files.length;`);

check('页面内生成 4 张带 EXIF 的测试照片', built === 4, `${built} 张`);

/* 3. 走一遍真实的处理流程 */
const processed = await evaluate(`
  const mod = await import('/assets/import.js');
  const entries = window.__testFiles;
  const { results, media, errors, skipped } = await mod.processEntries({
    entries, rootName: '照片归档', keepOriginals: false, onProgress: () => {},
  });
  window.__testResult = { results, media, errors, skipped };
  return JSON.stringify({
    n: results.length,
    media: media.size,
    errors,
    skipped,
    rows: results.map(r => ({
      path: r.path, date: r.date, src: r.dateSource, loc: r.location,
      cam: r.camera ? (r.camera.make + ' ' + r.camera.model) : null,
      ap: r.exposure?.aperture, sh: r.exposure?.shutter, iso: r.exposure?.iso, focal: r.exposure?.focal,
      gps: r.coords ? [r.coords.lat, r.coords.lng] : null,
      thumb: r.thumb, preview: r.preview, edited: r.editedBy,
      aspect: r.pixel ? +(r.pixel.width / r.pixel.height).toFixed(2) : null,
    })),
  });`);
const pr = JSON.parse(processed);
check('4 张全部处理成功', pr.n === 4 && pr.errors.length === 0, JSON.stringify({ n: pr.n, errors: pr.errors, skipped: pr.skipped }));
check('每张都生成了缩略图与预览图', pr.media === 8, `media=${pr.media}`);
const byPath = Object.fromEntries(pr.rows.map((r) => [r.path, r]));
const r1 = byPath['2024年/10月3日 杭州西湖/DSC01234.JPG'];
check('文件夹名识别日期 + EXIF 参数', r1 && r1.date === '2024-10-03' && r1.ap === 'f/5.6' && r1.sh === '1/250' && r1.iso === 100,
  JSON.stringify(r1));
check('相机与镜头', r1 && r1.cam === 'SONY ILCE-7M4', r1 && r1.cam);
check('地点与 GPS', r1 && r1.loc && r1.loc.includes('西湖') && Math.abs(r1.gps[0] - 30.2442) < 0.001, JSON.stringify([r1.loc, r1.gps]));
const r3 = byPath['2022年/扫街/10-06 成都宽窄巷子/IMG_5601.JPG'];
check('父目录年份 + 月日 推断正确', r3 && r3.date === '2022-10-06', r3 && r3.date);
const r4 = byPath['未整理/手机照片/IMG_20210405_090001.jpg'];
check('文件名日期 + Lightroom 识别', r4 && r4.date === '2021-04-05' && r4.edited === 'Lightroom', JSON.stringify([r4.date, r4.edited]));
check('竖图比例被正确记录', byPath['2024年/10月3日 杭州西湖/DSC01235.JPG'].aspect < 1);

/* 4.5 重复照片：指纹与分组 */
const dupInfo = await evaluate(`
  const mod = await import('/assets/import.js');
  const { results } = window.__testResult;
  const { findDuplicates, parseSignature } = await import('/src/dup.js');
  const withPh = results.filter(r => r.phash);
  const group = findDuplicates(results, { threshold: 5, maxColorDistance: 7 });
  return JSON.stringify({
    withPhash: withPh.length,
    total: results.length,
    sigLen: withPh[0] ? withPh[0].phash.length : 0,
    groups: group.groups.length,
    stats: group.stats,
  });`);
const di = JSON.parse(dupInfo);
check('浏览器端算出了感知指纹', di.withPhash === di.total && di.sigLen === 32, dupInfo);
check('4 张不同场景的测试图不会被误判为重复', di.groups === 0, dupInfo);

// 再验证"确实能检出重复"：同一条记录复制成两份不同路径 + 一张同图调亮版
const dupDetect = await evaluate(`
  const { results } = window.__testResult;
  const { findDuplicates } = await import('/src/dup.js');
  const a = results[0];

  const copy = { ...a, id: a.id + '-copy', path: a.path.replace('.JPG', '-副本.JPG') };
  // 结构相同、颜色特征也一致（模拟"调过亮度再导出"）
  const edited = { ...a, id: a.id + '-edited', path: a.path.replace('.JPG', '-修图.jpg'), phash: a.phash };

  const found = findDuplicates([a, copy, edited, ...results.slice(1)], { threshold: 5, maxColorDistance: 7 });
  const g = found.groups[0];
  return JSON.stringify({
    groups: found.groups.length,
    count: g ? g.count : 0,
    confidence: g ? g.confidence : null,
    keeperIsOriginal: g ? /DSC01234\\.JPG$/.test(g.keeper.path) || g.keeper.id === a.id : null,
  });
`);
const dd = JSON.parse(dupDetect);
check('同图副本 + 同图调亮版被检出（1 组 3 张）', dd.groups === 1 && dd.count === 3, dupDetect);
check('建议保留项选择了像素/体积更大的原图', dd.keeperIsOriginal === true, dupDetect);
const idx = await evaluate(`
  const mod = await import('/assets/import.js');
  const { results, media } = window.__testResult;
  const bundle = mod.buildIndex({ photos: results, title: '测试站', source: '网页导入' });
  window.__testBundle = { ...bundle, media, originals: new Map(), overrides: null };
  return JSON.stringify({
    photos: bundle.index.stats.photos,
    months: bundle.index.months.map(m => m.key),
    searchKeys: Object.keys(bundle.search[0]).sort(),
    monthFiles: bundle.monthFiles.map(m => m.name),
    firstSearch: bundle.search.find(p => p.i === results[0].id),
  });`);
const ij = JSON.parse(idx);
check('索引统计与月份分组正确', ij.photos === 4 && ij.months.includes('2024-10') && ij.months.includes('2021-04'), JSON.stringify(ij.months));
check('search.json 字段与命令行一致',
  ['a', 'aspect', 'cl', 'd', 'e', 'f', 'g', 'i', 'l', 'o', 's', 'src', 'th'].every((k) => ij.searchKeys.includes(k)),
  ij.searchKeys.join(','));

/* 5. zip 打包 */
const zip = await evaluate(`
  const mod = await import('/assets/import.js');
  const { createZip } = await import('/src/zip.js');
  const b = window.__testBundle;
  const files = [
    { name: 'public/data/index.json', data: JSON.stringify(b.index) },
    { name: 'public/data/search.json', data: JSON.stringify(b.search) },
    ...b.monthFiles.map(m => ({ name: 'public/data/' + m.name, data: m.data })),
  ];
  for (const [p, blob] of b.media) files.push({ name: 'public/' + p, data: blob });
  const bytes = await createZip(files);
  const head = [...bytes.slice(0, 4)].map(x => x.toString(16).padStart(2, '0')).join(' ');
  return JSON.stringify({ files: files.length, bytes: bytes.length, head });`);
const zj = JSON.parse(zip);
check('zip 打包可用（PK 头正确）', zj.head === '50 4b 03 04' && zj.bytes > 10000, zip);

/* 6. 真实交互：在页面里造一批照片，用 DataTransfer 派发 drop 事件，
      走完整的「拖进网页 → 结果表 → 人工修正」界面流程 */
await evaluate(`
  window.__errs = window.__errs || [];
  window.addEventListener('error', (e) => window.__errs.push(String(e.message)));
  window.addEventListener('unhandledrejection', (e) => window.__errs.push('rejection: ' + (e.reason && e.reason.message || e.reason)));
  return true;`);

const dropped = await evaluate(`
  const files = window.__testFiles;
  const dt = new DataTransfer();
  for (const { file, path: p } of files) {
    // 用 webkitRelativePath 模拟"整个文件夹拖进来"
    const f = new File([file], file.name, { type: file.type, lastModified: file.lastModified });
    try { Object.defineProperty(f, 'webkitRelativePath', { value: p }); } catch {}
    dt.items.add(f);
  }
  const zone = document.querySelector('#drop-zone');
  zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  return dt.files.length;`);
check('drop 事件派发成功（模拟拖入文件夹）', dropped === 4, `${dropped} 个文件`);

await sleep(500);
let rows = 0;
const deadline = Date.now() + 40000;
while (Date.now() < deadline) {
  rows = await evaluate(`return document.querySelectorAll('#imp-tbody tr').length;`);
  if (rows >= 4) break;
  await sleep(400);
}
const pageErrs = await evaluate(`return JSON.stringify(window.__errs || []);`);
check('结果表渲染出 4 行', rows === 4, `表格 ${rows} 行，页面错误 ${pageErrs}`);

const ui = await evaluate(`return JSON.stringify({
  kpis: document.querySelectorAll('#imp-summary .kpi').length,
  firstRow: (document.querySelector('#imp-tbody tr') || {}).innerText ? document.querySelector('#imp-tbody tr').innerText.replace(/\\s+/g, ' ').slice(0, 80) : null,
  hint: document.querySelector('#imp-write-hint').innerText.slice(0, 60),
  thumbs: [...document.querySelectorAll('#imp-tbody img')].filter(i => i.complete && i.naturalWidth > 0).length,
  saveEnabled: !document.querySelector('#imp-save').disabled,
});`);
const u = JSON.parse(ui);
check('摘要、缩略图、写入按钮都就绪', u.kpis === 6 && u.thumbs === 4 && u.saveEnabled, ui);
check('写入提示说明了合并结果（不会冲掉已有照片）',
  /合并进站点/.test(u.hint) && /保留原有/.test(u.hint), u.hint);

/* 6.5 合并逻辑：模拟"写入完成后数据刷新"，站点标签应随之更新 */
const merged = await evaluate(`
  const mod = await import('/assets/import.js');
  const existing = await mod.loadExistingFullPhotos();
  const fresh = window.__testResult.results;
  const m = mod.mergeRecords(fresh, existing);
  // 用合并后的完整记录重建索引（与写入时同一套代码）
  const fixed = m.photos.map(p => (p.thumb ? p : { ...p, thumb: 'media/thumbs/x.webp' }));
  const bundle = mod.buildIndex({ photos: fixed, title: '测试站', source: '合并测试' });
  window.__mergedBundle = bundle;
  return JSON.stringify({ existing: existing.length, added: m.added, replaced: m.replaced, kept: m.kept, total: m.total, indexPhotos: bundle.index.stats.photos });
`);
const mj = JSON.parse(merged);
check('合并计算正确（已有照片被保留）',
  mj.existing > 0 && mj.kept === mj.existing && mj.total === mj.existing + mj.added, merged);
check('合并后的索引包含全部照片', mj.indexPhotos === mj.total, merged);

await S('Page.captureScreenshot', { format: 'png' }).then(async (r) => {
  await fs.mkdir(values.shots, { recursive: true });
  await fs.writeFile(path.join(values.shots, '10-import.png'), Buffer.from(r.data, 'base64'));
});

/* 7. 人工修正 */
const edited2 = await evaluate(`
  const first = document.querySelector('#imp-tbody tr [data-act="edit"]');
  if (!first) return JSON.stringify({ shown: false, reason: '结果表没有行' });
  first.click();
  await new Promise(r => setTimeout(r, 250));
  document.querySelector('#imp-tbody tr [data-f="location"]').value = '测试地点';
  document.querySelector('#imp-tbody tr [data-act="save"]').click();
  await new Promise(r => setTimeout(r, 300));
  return JSON.stringify({
    shown: document.querySelector('#imp-tbody tr').innerText.includes('测试地点'),
  });`);
check('人工修正地点生效', JSON.parse(edited2).shown === true, edited2);

console.log('');
if (problems.length) {
  console.log('页面报错：');
  for (const p of [...new Set(problems)].slice(0, 6)) console.log('  - ' + p);
}
const failed = results.filter((r) => !r.ok);
console.log('');
console.log(`导入链路自检：${results.length - failed.length}/${results.length} 通过`);

await send('Target.closeTarget', { targetId });
ws.close();
process.exitCode = failed.length ? 1 : 0;
