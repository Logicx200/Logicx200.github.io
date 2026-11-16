import * as THREE from 'three';
import { loadSequence, reapplyThreshold } from './loader.js';
import { fitFrustum } from './fit.js';
import {
  vertexShader, fragmentShader, MODE_SOLID, MODE_GHOST
} from './shader.js';

const CUBE = 1;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 6;
const CAM_DIST = 10 * CUBE;
const FOV_DEG = 42;

const state = {
  seq: null,
  texture: null,
  mode: MODE_GHOST,
  alpha: 1.2,
  threshold: 0,
  samples: 1.0,
  zoom: 1,
  sort: 'name',
  lastFiles: null,
  req: null 
};

// 渲染分辨率相对画布的比例。画质滑块调高时超采样（>1），
// 帧数多、分辨率高时会被自适应压到 1 以下，避免 GPU 被拖死。
let renderScale = 1;

const theta = { value: 0 };   // 垂直俯仰
const phi = { value: 0 };     // 水平环绕

const clamp = (v, a, b) => (v < a ? a : (v > b ? b : v));
const el = id => document.getElementById(id);

const canvas = el('view');
const ui = {
  file: el('file'), open: el('open'), status: el('status'), sort: el('sort'),
  mode: el('mode'), alpha: el('alpha'), threshold: el('threshold'),
  quality: el('quality'), reset: el('reset'), panel: el('panel'),
  veil: el('veil'), veilText: el('veiltext'), veilBar: el('veilbar'),
  fatal: el('fatal')
};

// ---------------------------------------------------------------- 渲染器

const renderer = new THREE.WebGLRenderer({
  canvas, antialias: false, alpha: false, depth: true,
  powerPreference: 'high-performance'
});

if (!renderer.capabilities.isWebGL2) {
  showFatal('这个可视化需要 WebGL2。\n请用较新的 Chrome / Edge / Firefox 打开。');
}

renderer.setClearColor(0x05070b, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.NoToneMapping;

const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(-0.7, 0.7, 0.7, -0.7, 0.01, 100);

const uniforms = {
  uVolume: { value: null },
  uOrigin: { value: new THREE.Vector3(0, CAM_DIST, 0) },
  uDir: { value: new THREE.Vector3(0, -1, 0) },
  uRight: { value: new THREE.Vector3(-1, 0, 0) },
  uUp: { value: new THREE.Vector3(0, 0, 1) },
  uHalfExt: { value: new THREE.Vector2(0.7, 0.7) },
  uDepth: { value: 1 },
  uAlpha: { value: state.alpha },
  uSamples: { value: state.samples },
  uBright: { value: 1 }
};

const quad = new THREE.Mesh(
  new THREE.PlaneGeometry(2, 2),
  new THREE.ShaderMaterial({
    vertexShader, fragmentShader, uniforms,
    depthTest: false, depthWrite: false,
    transparent: true, blending: THREE.AdditiveBlending
  })
);
quad.frustumCulled = false;
scene.add(quad);

// ---------------------------------------------------------------- 相机 / 投影

const camOrigin = new THREE.Vector3();
const camRight = new THREE.Vector3(1, 0, 0);
const camUp = new THREE.Vector3(0, 0, 1);
// 相机的注视点。体数据在 z 方向以 0 为中心，所以要把视线中心挪到 -sz/2。
const focus = new THREE.Vector3(0, 0, 0);

// 正交视锥的半高：让照片平面（体数据在 z 方向的跨度）正好铺满画面高度。
// 这里必须跟着体数据的尺寸走，不能用固定的视锥角 —— 否则深度一大，
// 立方体上下就会被裁掉。y 方向不额外放大，图形因此不会被拉伸。
function layout() {
  const w = Math.max(1, canvas.clientWidth || window.innerWidth);
  const h = Math.max(1, canvas.clientHeight || window.innerHeight);

  // 采样代价 ≈ 像素数 × 帧数。帧数一多就必须降分辨率，否则 GPU 会被拖到卡死。
  // 画质滑块允许超采样（>1），但自适应只会往下压，不会超过画质滑块给的上限。
  let budget;
  if (!state.seq) {
    budget = 8e6;
  } else {
    const steps = state.seq.depth * 2 / Math.max(state.samples, 0.1);
    budget = 8e9 / Math.max(steps, 1);
  }
  const maxScale = state.samples > 1 ? state.samples : 1;
  renderScale = clamp(Math.sqrt(budget / (w * h)), 0.25, maxScale);

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2) * renderScale);

  if (!state.seq) {
    // 还没载入体数据：给一个单位立方体的视锥
    const f = fitFrustum(null, w / h, state.zoom, 1.04);
    camera.left = -f.halfX; camera.right = f.halfX;
    camera.top = f.halfY; camera.bottom = -f.halfY;
    camera.near = 1;
    camera.far = CAM_DIST + 3 * CUBE;
    camera.updateProjectionMatrix();
    uniforms.uHalfExt.value.set(f.halfX, f.halfY);
    return;
  }

  // 体数据的实际尺寸：x = W/depth，z = H/depth，y 恒为 1（三方向等比）。
  // 视锥必须**等比容纳整个立方体**，而不是让照片平面去填满屏幕 ——
  // 后者会在平面比屏幕更"方"时把上下裁掉。这段数学抽在 fit.js 里，有测试覆盖。
  const { halfX, halfY } = fitFrustum(state.seq, w / h, state.zoom, 1.04);

  camera.left = -halfX;
  camera.right = halfX;
  camera.top = halfY;
  camera.bottom = -halfY;
  camera.near = 1;
  camera.far = CAM_DIST + 3 * CUBE;
  camera.updateProjectionMatrix();

  // 正视时画面「上」对应世界 +z，所以 z 方向的中心要往 -z 挪半个平面高，
  // 这样照片正好落在画面中央、深度方向也居中。
  focus.y = -(state.seq.height / state.seq.depth) / 2;
  camera.position.copy(camOrigin).add(focus);
  camera.lookAt(focus);

  uniforms.uHalfExt.value.set(halfX, halfY);
}

function updateCamera() {
  const th = theta.value * Math.PI / 180;
  const ph = phi.value * Math.PI / 180;
  const ct = Math.cos(th), st = Math.sin(th);
  const cp = Math.cos(ph), sp = Math.sin(ph);

  // 角度为 0 时相机落在 +y（相对注视点），正对着立方体
  camOrigin.set(CAM_DIST * ct * sp, CAM_DIST * ct * cp, CAM_DIST * st).add(focus);

  const fwd = new THREE.Vector3().subVectors(focus, camOrigin).normalize();  // 视线方向
  const worldUp = new THREE.Vector3(0, 0, 1);
  const r = new THREE.Vector3().crossVectors(worldUp, fwd);
  if (r.lengthSq() < 1e-8) r.set(1, 0, 0);
  r.normalize();
  const up = new THREE.Vector3().crossVectors(fwd, r).normalize();

  camRight.copy(r);
  camUp.copy(up);

  camera.position.copy(camOrigin);
  camera.up.copy(up);
  camera.lookAt(focus);

  // 着色器里的射线起点在体数据坐标系：把注视点减掉，
  // 于是体数据恰好占 [-0.5, 0.5]³，边界判断保持简单。
  uniforms.uOrigin.value.copy(camOrigin).sub(focus);
  uniforms.uDir.value.copy(fwd);
  uniforms.uRight.value.copy(r);
  uniforms.uUp.value.copy(up);
}

// ---------------------------------------------------------------- 脏帧上传队列

// 数组 + Set 维护一个「最旧优先」的队列。GPU 上第 y 帧与第 y+1 帧相邻，
// 顺序推进会形成一条连续的上传带，比随机顺序大量 texSubImage3D 快得多。
const pendingQueue = [];
const pendingSet = new Set();

function markDirty(y) {
  if (!pendingSet.has(y)) { pendingSet.add(y); pendingQueue.push(y); }
}

function markAllDirty() {
  pendingQueue.length = 0;
  pendingSet.clear();
  if (!state.seq) return;
  for (let y = 0; y < state.seq.depth; y++) markDirty(y);
}

function flushUploads(limit) {
  if (!state.texture || !state.seq || !pendingQueue.length) return;
  const { width, height, data } = state.seq;
  const sliceLen = width * height * 4;
  const tex = state.texture;

  let n = 0;
  const batch = [];
  while (pendingQueue.length && n < limit) {
    const y = pendingQueue.shift();
    pendingSet.delete(y);
    const off = y * sliceLen;
    const view = data.subarray(off, off + sliceLen);
    tex.image.data.set(view);
    batch.push({ y, view });
    n++;
  }
  if (!batch.length) return;

  const gl = renderer.getContext();
  // 先让 Three 走一次它自己的上传路径（第一次会整块 texImage3D，之后只是绑定），
  // 它同时负责设好 pixelStorei；随后我们自己在纹理单元 0 上按帧增量更新。
  renderer.setRenderTarget(null);
  renderer.initTexture(tex);
  const prev = gl.getParameter(gl.ACTIVE_TEXTURE);
  gl.activeTexture(gl.TEXTURE0);
  gl.bindTexture(gl.TEXTURE_3D, tex.__webglTexture);
  gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
  for (const { y, view } of batch) {
    gl.texSubImage3D(
      gl.TEXTURE_3D, 0, 0, y, 0, width, 1, height,
      gl.RGBA, gl.UNSIGNED_BYTE, view
    );
  }
  gl.activeTexture(prev);
}

let reapplyScheduled = false;

/** 阈值变动时重算 alpha（可见性掩码 + 时间梯度），复用已解码的 RGB 体数据 */
function reapplyGrading(seq, threshold) {
  reapplyThreshold(seq, threshold);
}

function scheduleReapply() {
  if (reapplyScheduled) return;
  reapplyScheduled = true;
  requestAnimationFrame(() => {
    reapplyScheduled = false;
    if (!state.seq) return;
    reapplyGrading(state.seq, state.threshold);
    markAllDirty();
  });
}

// ---------------------------------------------------------------- 状态同步

/** 状态栏文字：帧数、体素尺寸、以及自适应后的实际渲染分辨率 */
function statusText() {
  if (!state.seq) return '';
  const w = Math.max(1, canvas.clientWidth || window.innerWidth);
  const h = Math.max(1, canvas.clientHeight || window.innerHeight);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const rw = Math.round(w * dpr * renderScale);
  const rh = Math.round(h * dpr * renderScale);
  // 渲染分辨率低于画布时就说明会被放大显示，那本身就会糊 —— 明确标出来
  const hint = renderScale < 0.99
    ? ` · 渲染 ${rw}×${rh}（被放大，画质会糊）`
    : ` · 渲染 ${rw}×${rh}`;
  return `${state.seq.depth} 帧 · 单帧 ${state.seq.width}×${state.seq.height}${hint}`;
}

function applyUniforms() {
  // 全不透明 = 所有帧都按 1.0 参与，叠成一个实心的彩色立方体
  uniforms.uAlpha.value = (state.mode === MODE_SOLID) ? 1.0 : state.alpha;
  uniforms.uSamples.value = state.samples;
  uniforms.uDepth.value = state.seq ? state.seq.depth : 1;
  uniforms.uBright.value = 1.0;

  // 输出已经夹到 [0,1]，用普通混合即可。
  // 加性混合在这里反而是错的：它会让重叠处溢出成白色。
  const m = quad.material;
  m.blending = THREE.NormalBlending;
  m.transparent = true;
  quad.renderOrder = 1;
  m.needsUpdate = true;
}

function syncModeButtons() {
  for (const b of ui.mode.querySelectorAll('button')) {
    const m = b.dataset.mode === 'solid' ? MODE_SOLID : MODE_GHOST;
    b.setAttribute('aria-pressed', String(m === state.mode));
  }
}

function setMode(mode) {
  state.mode = mode;
  syncModeButtons();
  applyUniforms();
}

// ---------------------------------------------------------------- 载入

function setBusy(on, text, ratio) {
  ui.veil.classList.toggle('on', on);
  if (typeof text === 'string') ui.veilText.textContent = text;
  if (typeof ratio === 'number') ui.veilBar.style.width = `${Math.round(ratio * 100)}%`;
}

function showFatal(msg) {
  ui.fatal.textContent = msg;
  ui.fatal.classList.add('on');
}

function disposeVolume() {
  pendingQueue.length = 0;
  pendingSet.clear();
  if (state.texture) {
    state.texture.dispose();
    state.texture = null;
    uniforms.uVolume.value = null;
  }
  state.seq = null;
}

async function openFiles(files) {
  if (files && files.length) state.lastFiles = files;
  if (!state.lastFiles || !state.lastFiles.length) return;

  if (state.req) state.req.cancelled = true;
  const req = state.req = { cancelled: false };

  disposeVolume();
  setBusy(true, '正在读取照片…', 0);

  try {
    const seq = await loadSequence(state.lastFiles, {
      sort: state.sort,
      threshold: state.threshold,
      signal: req,
      onProgress: ({ phase, done, total }) => {
        if (phase === 'measure') setBusy(true, '正在测量尺寸…', 0);
        else if (phase === 'grade') setBusy(true, '正在计算时间梯度…', 1);
        else setBusy(true, `正在解码 ${done} / ${total}`, done / total);
      }
    });
    if (req.cancelled) return;

    // 3D 纹理尺寸 = 宽 × 帧数 × 高，一次整块传上去
    const tex = new THREE.Data3DTexture(seq.data, seq.width, seq.depth, seq.height);
    tex.format = THREE.RGBAFormat;
    tex.type = THREE.UnsignedByteType;
    tex.minFilter = THREE.LinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.wrapS = THREE.ClampToEdgeWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    tex.wrapR = THREE.ClampToEdgeWrapping;
    tex.unpackAlignment = 1;
    tex.colorSpace = THREE.NoColorSpace;
    tex.needsUpdate = true;

    state.seq = seq;
    state.texture = tex;
    uniforms.uVolume.value = tex;

    applyUniforms();
    layout();          // 视锥尺寸依赖体数据的长宽比，必须先更新几何再摆相机
    updateCamera();

    ui.status.textContent = statusText();
  } catch (err) {
    if (!req.cancelled && !String(err && err.message).includes('已取消')) {
      showFatal(String((err && err.message) || err));
    }
  } finally {
    if (!req.cancelled) setBusy(false);
  }
}

// ---------------------------------------------------------------- 交互

ui.open.addEventListener('click', () => ui.file.click());
ui.file.addEventListener('change', () => {
  const f = ui.file.files;
  ui.file.value = '';
  if (f && f.length) openFiles(f);
});

ui.sort.addEventListener('change', () => {
  state.sort = ui.sort.value;
  if (state.lastFiles) openFiles(null);
});

ui.mode.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  setMode(b.dataset.mode === 'solid' ? MODE_SOLID : MODE_GHOST);
});

ui.alpha.addEventListener('input', () => {
  state.alpha = Number(ui.alpha.value);
  uniforms.uAlpha.value = state.alpha;
});

ui.threshold.addEventListener('input', () => {
  state.threshold = Number(ui.threshold.value);
  scheduleReapply();
});

ui.quality.addEventListener('input', () => {
  state.samples = Number(ui.quality.value);
  uniforms.uSamples.value = state.samples;
  // 渲染分辨率是按采样代价自适应算出来的，所以画质变化要重算一次
  layout();
  if (state.seq) {
    ui.status.textContent = statusText();
  }
});

function resetView() {
  theta.value = 0; phi.value = 0; state.zoom = 1;
  layout(); updateCamera();
}
ui.reset.addEventListener('click', resetView);

// 拖拽旋转 / 滚轮缩放 / 双指捏合
const pointers = new Map();

canvas.addEventListener('pointerdown', e => {
  try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()];
    state.pinchDist = Math.hypot(a.x - b.x, a.y - b.y);
    state.pinchZoom = state.zoom;
  }
});

canvas.addEventListener('pointermove', e => {
  const prev = pointers.get(e.pointerId);
  if (!prev) return;
  const dx = e.clientX - prev.x;
  const dy = e.clientY - prev.y;
  prev.x = e.clientX;
  prev.y = e.clientY;

  if (pointers.size >= 2) {
    const [a, b] = [...pointers.values()];
    const dist = Math.hypot(a.x - b.x, a.y - b.y);
    if (state.pinchDist > 0) {
      state.zoom = clamp(state.pinchZoom * (state.pinchDist / Math.max(1, dist)), MIN_ZOOM, MAX_ZOOM);
      layout();
    }
    return;
  }

  phi.value = (phi.value - dx * 0.28) % 360;
  theta.value = clamp(theta.value + dy * 0.28, -85, 85);
  updateCamera();
});

function endPointer(e) {
  pointers.delete(e.pointerId);
  if (pointers.size < 2) state.pinchDist = 0;
}
canvas.addEventListener('pointerup', endPointer);
canvas.addEventListener('pointercancel', endPointer);
canvas.addEventListener('pointerleave', endPointer);

canvas.addEventListener('wheel', e => {
  e.preventDefault();
  state.zoom = clamp(state.zoom * Math.exp(e.deltaY * 0.0012), MIN_ZOOM, MAX_ZOOM);
  layout();
}, { passive: false });

canvas.addEventListener('dblclick', resetView);

window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => {
  e.preventDefault();
  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
    openFiles(e.dataTransfer.files);
  }
});

window.addEventListener('keydown', e => {
  if (!state.seq) return;
  if (e.key === 'r' || e.key === 'R') {
    resetView();
  }
});

window.addEventListener('resize', () => { layout(); updateCamera(); });

// ---------------------------------------------------------------- 主循环

let last = performance.now();

// 着色器编译自检：跑第一次渲染，然后看看 Three 有没有真的把程序建起来。
// 编译失败时 Three 只往控制台打日志，画面上则什么都没有 —— 那是最难从外部
// 察觉的一类故障，所以这里主动把 GLSL 日志捞出来显示在界面上。
let shaderChecked = false;

function checkShaderCompiled() {
  // 没有体数据时材质还没被真正用到，渲染器里可能还没有程序，别误报
  if (shaderChecked || !state.seq) return;
  shaderChecked = true;

  const programs = (renderer.info && renderer.info.programs) || [];
  const broken = programs.filter(p => p.diagnostics);

  if (!programs.length || broken.some(p => p.diagnostics.runnable === false)) {
    const log = broken
      .map(p => {
        const d = p.diagnostics || {};
        return (d.fragmentShader && d.fragmentShader.log) || d.programLog || '';
      })
      .filter(Boolean)
      .join('\n\n');
    showFatal('着色器编译失败，画面无法渲染。\n\n'
      + (log || 'Three 没有给出日志，请按 F12 打开控制台查看红色报错。'));
    return;
  }

  if (broken.length) {
    const log = broken
      .map(p => {
        const d = p.diagnostics || {};
        return (d.fragmentShader && d.fragmentShader.log) || d.programLog || '';
      })
      .filter(Boolean)
      .join('\n\n');
    showFatal('着色器编译有告警：\n\n' + log);
  }
}

function loop(now) {
  requestAnimationFrame(loop);
  last = now;

  if (state.texture && pendingQueue.length) {
    flushUploads(Math.max(4, Math.ceil(state.seq.depth / 20)));
  }

  try {
    renderer.render(scene, camera);
  } catch (err) {
    // 渲染循环里抛异常会每帧刷屏，只报一次
    if (!window.__cubeRenderError) {
      window.__cubeRenderError = true;
      showFatal('渲染出错：\n\n' + ((err && err.stack) || err));
    }
    return;
  }

  checkShaderCompiled();
}

// ---------------------------------------------------------------- 启动

window.addEventListener('error', e => {
  if (window.__cubeRenderError) return;
  window.__cubeRenderError = true;
  showFatal('运行时错误：\n\n' + (e.message || e.error || '未知错误')
    + (e.filename ? '\n' + e.filename + ':' + e.lineno : ''));
});

window.addEventListener('unhandledrejection', e => {
  if (window.__cubeRenderError) return;
  window.__cubeRenderError = true;
  const r = e.reason;
  showFatal('未处理的异步错误：\n\n' + ((r && r.stack) || r));
});

layout();
updateCamera();
syncModeButtons();
applyUniforms();
setBusy(false);
requestAnimationFrame(loop);

// 内部状态暴露：既方便控制台调试，也是无头验证的抓手
window.__cube = {
  state, uniforms, renderer, camera, scene,
  theta, phi,
  openFiles, setMode, resetView,
  flushNow: () => flushUploads(1e9),
  relayout: () => { layout(); updateCamera(); }
};
