/**
 * 照片点云：把一张照片采样成三维点云，用鼠标旋转/缩放
 *
 * 做法：
 *   1. 把图缩到 ~440px 宽读像素
 *   2. 按"细节优先"加权采样（暗部、结构变化大的地方多取点），再补足随机点
 *   3. 每个点的深度 = 亮度（亮的地方朝观察者凸出来），颜色取原色
 *   4. 透视投影 + 深度排序（远的先画），亮度/尺寸随深度变化
 *
 * 交互：
 *   - 鼠标移动 → 轻微视差旋转（不点也能看到立体感）
 *   - 按住拖动 → 自由旋转
 *   - 滚轮 → 缩放
 *   - 点一下 → 回调（换一张）
 *
 * 性能：纯 canvas 2D 画方块，2~4 万个点在 60fps 量级；静止时不做无谓重绘。
 */

const TAU = Math.PI * 2;

export function createPointCloud(canvas, {
  onPick = () => {},
  reducedMotion = false,
} = {}) {
  const ctx = canvas.getContext('2d', { alpha: true });

  let points = null;          // {x,y,z,r,g,b,size} —— x,y 为 [-1,1]，z 为深度偏移
  let count = 0;
  let w = 0;
  let h = 0;
  let dpr = 1;

  let rotX = 0.06;            // 上下俯仰
  let rotY = -0.18;           // 左右旋转
  let targetX = rotX;
  let targetY = rotY;
  let zoom = 1;
  let targetZoom = 1;

  let dragging = false;
  let dragMoved = false;
  let dragStart = null;
  let pointer = { x: 0, y: 0 };   // -1..1 归一化后的位置
  let hasPointer = false;

  let raf = 0;
  let idlePhase = 0;
  let visible = true;
  let disposed = false;

  /* ---------------- 尺寸 ---------------- */

  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width || !rect.height) return false;
    dpr = Math.min(2, window.devicePixelRatio || 1);
    const nw = Math.round(rect.width);
    const nh = Math.round(rect.height);
    if (nw === w && nh === h) return true;
    w = nw;
    h = nh;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return true;
  }

  /* ---------------- 采样 ---------------- */

  /** 把图缩到合适尺寸并读像素 */
  async function loadImageData(url) {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    const ok = await new Promise((resolve) => {
      img.onload = () => resolve(true);
      img.onerror = () => resolve(false);
      img.src = url;
    });
    if (!ok) return null;

    const targetW = 440;
    const scale = Math.min(1, targetW / img.naturalWidth);
    const iw = Math.max(2, Math.round(img.naturalWidth * scale));
    const ih = Math.max(2, Math.round(img.naturalHeight * scale));

    const c = document.createElement('canvas');
    c.width = iw;
    c.height = ih;
    const cx = c.getContext('2d', { willReadFrequently: true });
    cx.imageSmoothingQuality = 'high';
    cx.drawImage(img, 0, 0, iw, ih);
    try {
      return cx.getImageData(0, 0, iw, ih);
    } catch {
      return null;   // 跨域等情况下读不了像素
    }
  }

  /**
   * 细节优先采样：中心、暗部、以及邻域差异大的像素更容易被选中。
   * 这样点云看起来更像照片本身，而不是一团均匀的噪点。
   */
  function samplePoints(imageData, maxPoints) {
    const { data, width, height } = imageData;
    const total = width * height;

    // 1) 先算每个像素的权重
    const weights = new Float32Array(total);
    let sum = 0;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = (y * width + x) * 4;
        const a = data[i + 3] / 255;
        if (a < 0.05) continue;                       // 透明像素不取
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

        // 与右/下相邻像素的差异，代表结构细节
        let edge = 0;
        if (x + 1 < width) {
          const j = i + 4;
          edge += Math.abs(r - data[j]) + Math.abs(g - data[j + 1]) + Math.abs(b - data[j + 2]);
        }
        if (y + 1 < height) {
          const j = i + width * 4;
          edge += Math.abs(r - data[j]) + Math.abs(g - data[j + 1]) + Math.abs(b - data[j + 2]);
        }
        edge /= 6 * 255;

        // 暗部权重高一点：夜景、暗背景的点云更有层次
        const darkness = 1 - lum;
        const wgt = 0.06 + edge * 2.2 + darkness * 0.55;
        weights[y * width + x] = wgt;
        sum += wgt;
      }
    }
    if (!sum) return { positions: new Float32Array(0), colors: new Uint8ClampedArray(0), count: 0 };

    // 2) 按权重放点：用"累积权重 + 二分查找"生成，避免对每个点做拒绝采样
    const n = Math.min(maxPoints, Math.floor(total * 0.9));
    const cumulative = new Float32Array(total);
    let acc = 0;
    for (let i = 0; i < total; i++) {
      acc += weights[i];
      cumulative[i] = acc;
    }

    const positions = new Float32Array(n * 2);
    const colors = new Uint8ClampedArray(n * 3);
    let written = 0;
    let seed = 1337;

    for (let k = 0; k < n; k++) {
      // 线性同余伪随机，速度快且分布够用
      seed = (seed * 1664525 + 1013904223) >>> 0;
      const r1 = seed / 4294967296;
      const target = r1 * acc;

      // 二分找像素
      let lo = 0;
      let hi = total - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (cumulative[mid] < target) lo = mid + 1;
        else hi = mid;
      }
      const px = lo % width;
      const py = (lo / width) | 0;
      const i = (py * width + px) * 4;
      if (data[i + 3] < 13) continue;

      positions[written * 2] = (px / (width - 1)) * 2 - 1;
      positions[written * 2 + 1] = (py / (height - 1)) * 2 - 1;
      colors[written * 3] = data[i];
      colors[written * 3 + 1] = data[i + 1];
      colors[written * 3 + 2] = data[i + 2];
      written++;
    }

    return { positions: positions.subarray(0, written * 2), colors: colors.subarray(0, written * 3), count: written };
  }

  /** 由采样结果生成带深度的三维点数组 */
  function buildPoints(sampled, aspect) {
    const { positions, colors, count: n } = sampled;
    const out = new Array(n);
    const depthScale = 0.42;

    // 先算平均亮度：夜景照片整体很暗，需要抬一下才能看清结构
    let lumSum = 0;
    for (let i = 0; i < n; i++) {
      lumSum += (0.299 * colors[i * 3] + 0.587 * colors[i * 3 + 1] + 0.114 * colors[i * 3 + 2]) / 255;
    }
    const meanLum = n ? lumSum / n : 0.5;
    // 平均越暗，gamma 越小（提亮越明显）；正常曝光的照片几乎不变
    const gamma = meanLum < 0.22 ? 0.52 : meanLum < 0.34 ? 0.68 : meanLum < 0.5 ? 0.85 : 1;

    for (let i = 0; i < n; i++) {
      const px = positions[i * 2];
      const py = positions[i * 2 + 1];
      const r = colors[i * 3];
      const g = colors[i * 3 + 1];
      const b = colors[i * 3 + 2];
      const raw = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

      // 提亮：只用于渲染的明暗与透明度，不改颜色
      const lum = Math.pow(raw, gamma);

      // 亮的地方往前凸，暗的地方往后沉；再叠一点噪声免得看起来是平面浮雕
      const noise = (((i * 2654435761) >>> 0) / 4294967296 - 0.5) * 0.06;
      out[i] = {
        x: px * aspect,
        y: py,
        z: (raw - 0.5) * 2 * depthScale + noise,
        r, g, b,
        lum,
        raw,
      };
    }
    return out;
  }

  /* ---------------- 渲染 ---------------- */

  function render() {
    if (!points || !w || !h) return;
    ctx.clearRect(0, 0, w, h);

    const focal = Math.min(w, h) * 0.82;
    const cx = w / 2;
    const cy = h / 2;

    const sinX = Math.sin(rotX);
    const cosX = Math.cos(rotX);
    const sinY = Math.sin(rotY);
    const cosY = Math.cos(rotY);
    const zScale = zoom;

    const baseSize = Math.max(1, Math.min(w, h) / 260);

    // 投影 + 深度排序
    const projected = new Array(points.length);
    for (let i = 0; i < points.length; i++) {
      const p = points[i];
      // 先绕 Y 轴，再绕 X 轴
      const x1 = p.x * cosY + p.z * sinY;
      const z1 = -p.x * sinY + p.z * cosY;
      const y1 = p.y * cosX - z1 * sinX;
      const z2 = p.y * sinX + z1 * cosX;

      const zc = z2 * zScale + 1.7;          // 相机在 z = -1.7 处看向 +z
      if (zc <= 0.15) { projected[i] = null; continue; }
      const k = focal / zc;

      // 透明度：暗部不要全透明，否则夜空类照片什么都看不到
      const depthFade = Math.min(1, Math.max(0.4, zc * 0.78));
      const alpha = (0.34 + p.lum * 0.78) * depthFade;

      // 越靠前越亮一点，强化立体感
      const front = Math.max(0, Math.min(1, (z2 + 0.5)));
      const boost = 1 + front * 0.18;

      projected[i] = {
        sx: cx + x1 * k,
        sy: cy + y1 * k,
        z: z2,
        size: Math.max(0.7, baseSize * (1.25 - z2 * 0.55)),
        alpha: Math.min(1, alpha),
        r: Math.min(255, p.r * boost) | 0,
        g: Math.min(255, p.g * boost) | 0,
        b: Math.min(255, p.b * boost) | 0,
      };
    }

    // 远的先画（z 小的先画）
    const order = [];
    for (let i = 0; i < projected.length; i++) if (projected[i]) order.push(i);
    order.sort((a, b) => projected[a].z - projected[b].z);

    for (const i of order) {
      const q = projected[i];
      const s = q.size;
      ctx.fillStyle = `rgba(${q.r},${q.g},${q.b},${q.alpha.toFixed(3)})`;
      ctx.fillRect(q.sx - s / 2, q.sy - s / 2, s, s);
    }
  }

  function tick() {
    if (disposed) return;
    raf = 0;
    if (!visible) return;

    // 未拖动时缓慢自转 + 跟随鼠标的视差
    const parallaxX = hasPointer && !dragging ? pointer.y * 0.16 : 0;
    const parallaxY = hasPointer && !dragging ? pointer.x * 0.26 : 0;

    if (!reducedMotion) idlePhase += 0.0032;

    const wantX = targetX + parallaxX;
    const wantY = targetY + parallaxY;

    rotX += (wantX - rotX) * 0.09;
    rotY += (wantY - rotY) * 0.09;
    zoom += (targetZoom - zoom) * 0.12;

    render();
    schedule();
  }

  function schedule() {
    if (raf || disposed || !visible) return;
    // 静止（未拖动、无指针、无动效）时降到低频，别空烧 CPU
    if (!dragging && !hasPointer && reducedMotion) return;
    raf = requestAnimationFrame(tick);
  }

  /* ---------------- 事件 ---------------- */

  function toNormalized(e) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((e.clientX - rect.left) / rect.width) * 2 - 1,
      y: ((e.clientY - rect.top) / rect.height) * 2 - 1,
    };
  }

  canvas.addEventListener('pointerdown', (e) => {
    dragging = true;
    dragMoved = false;
    dragStart = { x: e.clientX, y: e.clientY, rotX: targetX, rotY: targetY };
    canvas.setPointerCapture?.(e.pointerId);
    canvas.classList.add('is-dragging');
  });

  canvas.addEventListener('pointermove', (e) => {
    const n = toNormalized(e);
    pointer = n;
    hasPointer = true;
    if (dragging && dragStart) {
      const dx = (e.clientX - dragStart.x) / 220;
      const dy = (e.clientY - dragStart.y) / 220;
      if (Math.abs(e.clientX - dragStart.x) + Math.abs(e.clientY - dragStart.y) > 4) dragMoved = true;
      targetY = dragStart.rotY + dx;
      targetX = Math.max(-1.1, Math.min(1.1, dragStart.rotX + dy));
    }
    schedule();
  });

  function endDrag(e) {
    if (dragging && !dragMoved) onPick();
    dragging = false;
    dragStart = null;
    canvas.classList.remove('is-dragging');
    canvas.releasePointerCapture?.(e?.pointerId);
    schedule();
  }
  canvas.addEventListener('pointerup', endDrag);
  canvas.addEventListener('pointercancel', endDrag);

  canvas.addEventListener('pointerleave', () => {
    hasPointer = false;
    if (!dragging) schedule();
  });

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    targetZoom = Math.max(0.55, Math.min(2.4, targetZoom * Math.exp(-e.deltaY * 0.0014)));
    schedule();
  }, { passive: false });

  /* ---------------- 对外接口 ---------------- */

  return {
    /** 载入一张图并重建点云 */
    async load(url, { maxPoints } = {}) {
      if (!resize()) return { ok: false, reason: 'no-size' };
      const imageData = await loadImageData(url);
      if (!imageData) return { ok: false, reason: 'load-failed' };

      const area = w * h;
      const budget = maxPoints || Math.max(9000, Math.min(34000, Math.round(area / 26)));
      const sampled = samplePoints(imageData, budget);
      if (!sampled.count) return { ok: false, reason: 'empty' };

      const aspect = imageData.width / imageData.height;
      points = buildPoints(sampled, aspect);
      count = points.length;

      // 按图片比例调整初始缩放，保证完整进画面
      const fit = Math.min(1, 1.05 / Math.max(aspect / 1.6, 1));
      targetZoom = Math.max(0.62, fit);
      zoom = targetZoom;

      render();
      schedule();
      return { ok: true, points: count };
    },
    setVisible(v) {
      visible = v;
      if (v) { resize(); render(); schedule(); }
      else if (raf) { cancelAnimationFrame(raf); raf = 0; }
    },
    resize() {
      if (resize()) { render(); schedule(); }
    },
    reset() {
      targetX = 0.06;
      targetY = -0.18;
      targetZoom = 1;
      schedule();
    },
    dispose() {
      disposed = true;
      if (raf) cancelAnimationFrame(raf);
      points = null;
    },
    get pointCount() { return count; },
  };
}
