// 无头验证外壳。由 tools/build-test.js 生成的 test/index.html 加载，
// 通过 URL 参数把应用摆到指定状态，并自动载入 ../sample 下的样本图。
//
// 参数：mode=ghost|solid   phi=deg   theta=deg   zoom=N   alpha=N   thr=N

const qs = new URLSearchParams(location.search);
const num = (k, d) => (qs.has(k) ? Number(qs.get(k)) : d);

const MODE_VALUE = { solid: 1, ghost: 2 };

function tell(obj) {
  document.title = 'CUBE ' + JSON.stringify(obj);
}

async function boot() {
  const cube = window.__cube;
  if (!cube) throw new Error('window.__cube 不存在（app.js 可能没加载成功）');

  cube.state.alpha = num('alpha', 0.12);
  cube.state.threshold = num('thr', 0);
  cube.state.samples = num('samples', 0.75);
  cube.state.zoom = num('zoom', 1);
  cube.theta.value = num('theta', 0);
  cube.phi.value = num('phi', 0);

  // 载入样本
  const names = [];
  for (let i = 0; i < 24; i++) names.push(`frame_${String(i).padStart(3, '0')}.png`);
  const files = [];
  for (const n of names) {
    const r = await fetch('../sample/' + n);
    if (!r.ok) throw new Error('取样本失败 ' + n + ' HTTP ' + r.status);
    const blob = await r.blob();
    files.push(new File([blob], n, { type: 'image/png' }));
  }
  await cube.openFiles(files);

  if (!cube.state.seq) throw new Error('序列没载入成功');

  const mode = qs.get('mode') || 'ghost';
  cube.setMode(MODE_VALUE[mode] || 2);
  cube.relayout();

  // 阈值变动会重算 alpha，重算后需要把整块纹理重传
  if (num('thr', 0) > 0) {
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  }
  cube.flushNow();

  await new Promise(r => requestAnimationFrame(r));
  cube.flushNow();
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

  const seq = cube.state.seq;
  tell({
    ready: true,
    error: window.__err || '',
    mode,
    zoom: cube.state.zoom,
    theta: cube.theta.value,
    phi: cube.phi.value,
    alpha: cube.state.alpha,
    threshold: cube.state.threshold,
    depth: seq.depth,
    width: seq.width,
    height: seq.height,
    pending: 0,
    scale: cube.uniforms.uScale.value.toArray().map(v => +v.toFixed(5)),
    basis: {
      origin: cube.uniforms.uOrigin.value.toArray().map(v => +v.toFixed(4)),
      dir: cube.uniforms.uDir.value.toArray().map(v => +v.toFixed(4)),
      right: cube.uniforms.uRight.value.toArray().map(v => +v.toFixed(4)),
      up: cube.uniforms.uUp.value.toArray().map(v => +v.toFixed(4)),
      halfExt: cube.uniforms.uHalfExt.value.toArray().map(v => +v.toFixed(4))
    }
  });
}

boot().catch(e => {
  tell({ ready: false, error: String((e && e.message) || e) });
});
