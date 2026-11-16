/* 参考光栅器：用 CPU 复现应用的渲染规则，产出参考图
 *
 * ─────────────────────────────────────────────────────────────────────
 * 为什么要有这个文件
 * ─────────────────────────────────────────────────────────────────────
 * 本会话的沙箱禁止命名管道，而 Chromium 的浏览器↔渲染器 IPC 必须走它：
 *
 *   FATAL:mojo\public\cpp\platform\platform_channel.cc:183] Check failed: . : 拒绝访问。 (0x5)
 *
 * 无头浏览器因此起不来，"真实 GPU 渲染"在本会话内无法验证。
 * 退一步能证明的是：**几何与相机数学是对的**。
 *
 * 这个参考光栅器复刻了应用的全部空间逻辑，规则与着色器/固定管线逐条对齐：
 *
 *   投影      直接用 STC.view.camParams / projectToPixel —— 与应用同一份代码，
 *             不存在"第二套公式"，否则这个验证就成了自说自话
 *   帧平面    顶点在 (±w/2, ±h/2)，平移到 z_i；模型矩阵即缩放+平移
 *   UV        与 PLANE_VS 的 aUv 同一套编号，配合 flipY:true 让图像正立
 *   纹理采样  双线性过滤（对应 GL_LINEAR），越界边缘夹紧（对应 CLAMP_TO_EDGE）
 *   混合      SRC_ALPHA / ONE_MINUS_SRC_ALPHA（对应 blendFuncSeparate 的 RGB 部分）
 *   深度      透视正确插值，depthFunc(LEQUAL)，只有不透明帧写深度
 *   绘制顺序  侧面色带（写深度）→ 不透明帧（写深度）→ 半透明帧由远到近（不写深度）
 *             这与 60-renderer.js 的 render() 完全同序
 *
 * 它**不能**证明 GLSL 在真实驱动上编译运行正确 —— 那是另一层，
 * 由 test/pipeline.test.mjs 的静态审查 + 记录型 WebGL 桩覆盖。
 */
import { createDom, loadApp } from './harness.mjs';

function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }

/** 双线性采样一张 RGBA 纹理（纹素中心对齐），边缘夹紧 */
export function sampleBilinear(tex, u, v) {
  const fx = u * tex.width - 0.5;
  const fy = v * tex.height - 0.5;
  const x0 = Math.floor(fx), y0 = Math.floor(fy);
  const tx = fx - x0, ty = fy - y0;
  const x1 = x0 + 1, y1 = y0 + 1;

  const outC = [0, 0, 0, 0];
  for (let c = 0; c < 4; c++) {
    const t00 = tex.data[((clamp(y0, 0, tex.height - 1)) * tex.width + clamp(x0, 0, tex.width - 1)) * 4 + c];
    const t10 = tex.data[((clamp(y0, 0, tex.height - 1)) * tex.width + clamp(x1, 0, tex.width - 1)) * 4 + c];
    const t01 = tex.data[((clamp(y1, 0, tex.height - 1)) * tex.width + clamp(x0, 0, tex.width - 1)) * 4 + c];
    const t11 = tex.data[((clamp(y1, 0, tex.height - 1)) * tex.width + clamp(x1, 0, tex.width - 1)) * 4 + c];
    outC[c] = (t00 * (1 - tx) + t10 * tx) * (1 - ty) + (t01 * (1 - tx) + t11 * tx) * ty;
  }
  return outC;
}

/** 最近邻采样（对应 GL_NEAREST） */
export function sampleNearest(tex, u, v) {
  const x = clamp(Math.floor(u * tex.width), 0, tex.width - 1);
  const y = clamp(Math.floor(v * tex.height), 0, tex.height - 1);
  const o = (y * tex.width + x) * 4;
  return [tex.data[o], tex.data[o + 1], tex.data[o + 2], tex.data[o + 3]];
}

/* ---------------------------------------------------------------- 上下文 */

/** 建一个共享的应用实例（模块只加载一次，省时间） */
export function makeContext(vpW, vpH) {
  const dom = createDom({ width: vpW, height: vpH });
  const { STC } = loadApp(dom);
  ensureQuadLayout(STC);
  return { STC, dom, view: STC.view, quad: { pos: QUAD_POS, uv: QUAD_UV_ORDERED } };
}

export function makeFramebuffer(w, h, bg) {
  const rgba = new Uint8ClampedArray(w * h * 4);
  const depth = new Float32Array(w * h).fill(Infinity);
  const c = bg || [5, 7, 11];
  for (let i = 0; i < w * h; i++) {
    rgba[i * 4] = c[0]; rgba[i * 4 + 1] = c[1]; rgba[i * 4 + 2] = c[2]; rgba[i * 4 + 3] = 255;
  }
  return { w, h, rgba, depth };
}

/* -------------------------------------------------------- 四边形光栅化 */

/**
 * 四个角的 (位置, uv)，**直接从 shaders.V_QUAD 派生**。
 *
 * 这里刻意不再手写一份 uv：GPU 用的就是 V_QUAD，参考光栅器必须与之完全一致。
 * 手抄一份的后果在这个项目里出现过三次 —— uv 被转置或镜像，而画面里
 * "有东西"、中心像素甚至也能对上，只有拿已知位置的图形去核对才会露馅。
 * 共用同一份派生结果，就不存在抄错的可能。
 *
 * 顶点顺序：0 = (-0.5,-0.5)  1 = (0.5,-0.5)  2 = (-0.5,0.5)  3 = (0.5,0.5)
 */
let QUAD_POS = null;
let QUAD_UV_ORDERED = null;
function ensureQuadLayout(STC) {
  if (QUAD_UV_ORDERED) return;
  const laid = STC.shaders.quadLayout();
  QUAD_POS = laid.pos;
  QUAD_UV_ORDERED = laid.uv;
}
const QUAD_UV = () => QUAD_UV_ORDERED;

/** 由屏幕像素反解该点对应的 uv；不在覆盖范围内返回 null。
 *  单独抽出来是为了：光栅化与诊断代码走**同一份**重心坐标逻辑，
 *  否则"我觉得它在三角形里"和"程序认为它在三角形里"可能不是一回事。 */
export function pixelToUv(scr, uv, px, py) {
  const cx = px + 0.5, cy = py + 0.5;
  const tris = [[0, 1, 3], [0, 3, 2]];
  for (let k = 0; k < 2; k++) {
    const t = tris[k];
    const a = scr[t[0]], b = scr[t[1]], c = scr[t[2]];
    const den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
    if (Math.abs(den) < 1e-12) continue;
    const l0 = ((b[1] - c[1]) * (cx - c[0]) + (c[0] - b[0]) * (cy - c[1])) / den;
    const l1 = ((c[1] - a[1]) * (cx - c[0]) + (a[0] - c[0]) * (cy - c[1])) / den;
    const l2 = 1 - l0 - l1;
    if (l0 >= -1e-9 && l1 >= -1e-9 && l2 >= -1e-9) {
      return {
        u: l0 * uv[t[0]][0] + l1 * uv[t[1]][0] + l2 * uv[t[2]][0],
        v: l0 * uv[t[0]][1] + l1 * uv[t[1]][1] + l2 * uv[t[2]][1],
        weights: [l0, l1, l2], tri: t
      };
    }
  }
  return null;
}

/**
 * 画一个带纹理的四边形。
 * @param {object} o
 *   fb, view, cp, vp
 *   localQuad  四个角的局部坐标（由 quadLayout 派生，±0.5）
 *   uv         四个角的 uv（同上，来自同一份派生结果）
 *   planeW/H   把局部坐标放大到照片尺寸
 *   z          该帧在时间轴上的位置（模型矩阵的平移量）
 *   tex, opacity, writeDepth, filter, trace
 */
export function drawQuad(o) {
  const { fb, view, cp, vp, tex, localQuad, uv } = o;
  const pw = o.planeW === undefined ? 1 : o.planeW;
  const ph = o.planeH === undefined ? 1 : o.planeH;
  const zOff = o.z === undefined ? 0 : o.z;
  const opacity = o.opacity === undefined ? 1 : o.opacity;
  const writeDepth = !!o.writeDepth;
  const sample = o.filter === 'nearest' ? sampleNearest : sampleBilinear;

  const world = localQuad.map((p) => [p[0] * pw, p[1] * ph, p[2] + zOff]);
  const scr = world.map((p) => view.projectToPixel(cp, vp, p[0], p[1], p[2]));
  const ndcZ = scr.map((s) => s[2]);

  const minX = Math.max(0, Math.floor(Math.min(scr[0][0], scr[1][0], scr[2][0], scr[3][0])));
  const maxX = Math.min(fb.w - 1, Math.ceil(Math.max(scr[0][0], scr[1][0], scr[2][0], scr[3][0])));
  const minY = Math.max(0, Math.floor(Math.min(scr[0][1], scr[1][1], scr[2][1], scr[3][1])));
  const maxY = Math.min(fb.h - 1, Math.ceil(Math.max(scr[0][1], scr[1][1], scr[2][1], scr[3][1])));
  if (maxX < minX || maxY < minY) return 0;

  // 四边形拆两个三角形：(0,1,3) 与 (0,3,2)
  const tris = [[0, 1, 3], [0, 3, 2]];
  let painted = 0;

  /*
   * 轮廓模式（与 PLANE_FS 的 uOutline 分支同规则）：
   *   采样步长 = max(一个屏幕像素对应的 uv 变化, 一个纹素)。
   *   在 CPU 这边，一个三角形的 uv 是仿射的，所以 duv/dx 可以直接从三个顶点的
   *   屏幕坐标与 uv 解出来 —— 与着色器里的 fwidth(vUv) 是同一个量。
   *   然后取上下左右四个邻居，用**逐通道最大差**判定分界线。
   */
  const outline = !!o.outline;
  const threshold = o.edgeThreshold === undefined ? 0.25 : o.edgeThreshold;
  /*
   * 切割（选区）：与 PLANE_FS 的 uClipOn/uClip 同一判据 —— 选区外的片元直接丢弃。
   * clip = [x0, y0, x1, y1]，归一化 uv（v=0 是图像顶部，与 uv 的朝向一致），含边界。
   * **必须在采样之前丢**，否则"裁掉的区域"会以采样后的颜色留在画面里。
   */
  const clipOn = !!o.clipOn;
  const clipRect = o.clip || [0, 0, 1, 1];
  /**
   * 一个屏幕像素对应多少 uv —— 就是 GLSL 里 `fwidth(vUv)` 的等价物。
   * 三角形内 uv 是仿射的，所以直接由三个顶点的屏幕坐标与 uv 解出偏导：
   *   fwidth(f) = |df/dx| + |df/dy|
   * 下限取一个纹素，保证不会在同一纹素里取样（与着色器里的 max(…, uTexel) 一致）。
   */
  const uvStep = (t) => {
    const A = scr[t[0]], B = scr[t[1]], C = scr[t[2]];
    const det = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1]);
    const tw = 1 / (tex.width || 1), th = 1 / (tex.height || 1);
    if (Math.abs(det) < 1e-12) return [tw, th];
    const u0 = uv[t[0]], u1 = uv[t[1]], u2 = uv[t[2]];
    const dux = (u0[0] * (B[1] - C[1]) + u1[0] * (C[1] - A[1]) + u2[0] * (A[1] - B[1])) / det;
    const duy = (u0[0] * (C[0] - B[0]) + u1[0] * (A[0] - C[0]) + u2[0] * (B[0] - A[0])) / det;
    const dvx = (u0[1] * (B[1] - C[1]) + u1[1] * (C[1] - A[1]) + u2[1] * (A[1] - B[1])) / det;
    const dvy = (u0[1] * (C[0] - B[0]) + u1[1] * (A[0] - C[0]) + u2[1] * (B[0] - A[0])) / det;
    return [
      Math.max(Math.abs(dux) + Math.abs(duy), tw),
      Math.max(Math.abs(dvx) + Math.abs(dvy), th)
    ];
  };
  const chanMax = (a, b) => Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]),
    Math.abs(a[2] - b[2])) / 255;

  for (let py = minY; py <= maxY; py++) {
    for (let px = minX; px <= maxX; px++) {
      const hit = pixelToUv(scr, uv, px, py);
      if (!hit) continue;

      const t = hit.tri;
      const u = hit.u, v = hit.v;
      const l0 = hit.weights[0], l1 = hit.weights[1], l2 = hit.weights[2];
      const z = l0 * ndcZ[t[0]] + l1 * ndcZ[t[1]] + l2 * ndcZ[t[2]];

      const di = py * fb.w + px;
      const rejected = z > fb.depth[di];          // depthFunc(LEQUAL)
      // 切割：选区之外的片元整片丢弃（着色器里也是 discard，而不是画成透明）
      if (clipOn && (u < clipRect[0] || u > clipRect[2] ||
                     v < clipRect[1] || v > clipRect[3])) {
        if (o.trace) o.trace.push({ px, py, u, v, z, sampled: null, rejected, clipped: true });
        continue;
      }
      let c = rejected ? null : sample(tex, u, v);
      if (outline && c) {
        const st = uvStep(t);
        // 上下左右四个邻居，逐通道最大差取最大 —— 与 STC.view.outlineContrast 同一判据
        const nb = [
          sample(tex, u + st[0], v), sample(tex, u - st[0], v),
          sample(tex, u, v + st[1]), sample(tex, u, v - st[1])
        ];
        let m = 0;
        for (const n of nb) m = Math.max(m, chanMax(c, n));
        // 内部整片丢弃，只留分界线；线条往白里提（与着色器一致）
        c = m >= threshold
          ? [c[0] * 0.4 + 255 * 0.6, c[1] * 0.4 + 255 * 0.6, c[2] * 0.4 + 255 * 0.6, c[3]]
          : null;
      }
      if (o.trace) o.trace.push({ px, py, u, v, z, sampled: c, rejected });
      if (rejected || !c) continue;
      if (writeDepth) fb.depth[di] = z;

      const a = (c[3] / 255) * opacity;
      if (a <= 0) continue;
      const o4 = di * 4;
      fb.rgba[o4] = c[0] * a + fb.rgba[o4] * (1 - a);
      fb.rgba[o4 + 1] = c[1] * a + fb.rgba[o4 + 1] * (1 - a);
      fb.rgba[o4 + 2] = c[2] * a + fb.rgba[o4 + 2] * (1 - a);
      fb.rgba[o4 + 3] = 255;
      painted++;
    }
  }
  return painted;
}

/* ------------------------------------------------------------ 场景渲染 */

/**
 * @param {object} o
 *   ctx         makeContext 的结果
 *   seq         {geo, frames:[{width,height}], textures:[{width,height,data}]}
 *   ui          {allGhost, opCur, opOther, otherMode}
 *   cur         当前帧下标
 *   cam         {az, el, zoom, panU, panV, fov}
 *   vpW, vpH
 *   bg          背景色
 *   outline     是否只保留轮廓（等价于着色器的 uOutline）
 *   edgeThreshold 轮廓门槛（等价于 uEdgeThreshold）
 *   clipOn      是否只画选区内的画面（等价于 uClipOn）
 *   clip        [x0,y0,x1,y1] 归一化 uv 选区（等价于 uClip）
 */
export function renderScene(o) {
  const { ctx, seq, ui, cur, cam, vpW, vpH } = o;
  const view = ctx.view;
  const vp = { w: vpW, h: vpH };
  const cp = o.cp || view.camParams(seq.geo, cam, vp);
  const res = view.resolve(seq, ui, cur);
  const fb = o.fb || makeFramebuffer(vpW, vpH, o.bg);

  const halfW = seq.geo.planeW / 2;
  const halfH = seq.geo.planeH / 2;

  let items = res.items.filter((it) => it.opacity > 0 && !it.pointCloud);
  if (o.only !== undefined) items = items.filter((it) => o.only.includes(it.i));
  const opaque = items.filter((it) => it.opacity >= 0.998);
  const ghost = items.filter((it) => it.opacity < 0.998);
  view.sortFarToNear(ghost, cp);

  // 轮廓提取：与 PLANE_FS 的 uOutline 分支同一条路径
  const outline = o.outline !== undefined ? !!o.outline : !!ui.outline;
  const edgeThreshold = o.edgeThreshold !== undefined ? o.edgeThreshold : ui.edgeThreshold;
  // 切割：与 PLANE_FS 的 uClipOn/uClip 同一判据（选区外的片元丢弃）
  const clipOn = o.clipOn !== undefined ? !!o.clipOn : !!ui.clipOn;
  const clip = o.clip !== undefined ? o.clip : ui.clip;

  let quads = 0;
  for (const list of [opaque, ghost]) {
    for (const it of list) {
      const tex = seq.textures[it.i];
      if (!tex) continue;
      drawQuad({
        fb, view, cp, vp, tex,
        localQuad: ctx.quad.pos,
        uv: ctx.quad.uv,
        planeW: seq.geo.planeW,
        planeH: seq.geo.planeH,
        z: it.z,
        opacity: it.opacity,
        writeDepth: it.opacity >= 0.998,
        outline: outline,
        edgeThreshold: edgeThreshold,
        clipOn: clipOn,
        clip: clip
      });
      quads++;
    }
  }

  return { fb, cp, res, quads };
}

export { QUAD_UV_ORDERED, QUAD_UV };

/* -------------------------------------------------------- 侧面颜色条 */

/**
 * 画每张照片的**四个侧立面**（薄片的边）。
 *
 * 与应用同规则，而且**共用同一份映射函数**（`view.bandSides` /
 * `view.edgeCoord` / `view.frameRow` / `view.packEdge`）：
 *   - 每帧一片薄片：z 从 (z_i + d/2) 到 (z_i − d/2)，中面才是照片本身；
 *   - 侧立面沿边方向铺开（左右墙沿 y、半长 halfH；上下墙沿 x、半长 halfW），
 *     固定轴上的偏移就是照片的边（±halfW / ±halfH）——
 *     这两件事必须分开，混用会让侧立面与照片对不齐；
 *   - 颜色取自该帧那条边的**真实 RGB**，沿厚度方向是常数；
 *   - 不透明、写深度：它是薄片的实体外壳，先于帧平面绘制。
 *
 * 这里曾经是"一条带子从 z=0 拉到 depth、帧号沿带子插值"的模型 ——
 * 那与应用实际提交的绘制（每帧一片薄片）根本不是同一件事，
 * 于是参考渲染一路"通过"，真实画面却是一片灰。
 * 现在两边的几何表、纹理坐标、颜色来源都来自同一批纯函数。
 */
export function drawBands(o) {
  const { fb, view, cp, vp, seq } = o;
  const geo = seq.geo;
  const n = seq.frames.length;
  const ui = o.ui || {};
  const thickness = o.thickness !== undefined ? o.thickness : (ui.thickness || 0);
  const sides = view.bandSides(geo);

  // 每帧的四条边颜色（与 packEdge 同一套下标）
  const edges = seq.edgeColors
    ? seq.edgeColors
    : seq.edgePixels.map((f) => view.edgeColors(f.data, f.width, f.height));

  let drawn = 0;
  const perSide = o.perSide || null;
  for (let i = 0; i < n; i++) {
    const zc = i * (n > 1 ? geo.depth / (n - 1) : 0);
    // 与应用一致：厚度被夹到帧间距的 90%
    const step = n > 1 ? geo.depth / (n - 1) : 0;
    const d = step > 0 ? Math.min(thickness, step * 0.9) : thickness;
    if (d <= 0) continue;
    const row = view.frameRow(i, n);

    for (const s of sides) {
      const arr = edges[i] && edges[i][s.side];
      if (!arr || !arr.length) continue;

      // 角点：u 沿边（-1..1），v 沿厚度（0 前 → 1 后）
      const corner = (u, v) => {
        const along = u * s.span;
        const z = zc + d * 0.5 - v * d;
        return s.axisY ? [s.off, along, z] : [along, s.off, z];
      };
      const world = [corner(-1, 0), corner(1, 0), corner(-1, 1), corner(1, 1)];
      const scr = world.map((p) => view.projectToPixel(cp, vp, p[0], p[1], p[2]));
      // 与 quadLayout 同源的 uv 约定：u 沿边 0→1，v 沿厚度 0→1
      const quadUv = [[0, 0], [1, 0], [0, 1], [1, 1]];

      const minX = Math.max(0, Math.floor(Math.min(...scr.map((p) => p[0]))));
      const maxX = Math.min(fb.w - 1, Math.ceil(Math.max(...scr.map((p) => p[0]))));
      const minY = Math.max(0, Math.floor(Math.min(...scr.map((p) => p[1]))));
      const maxY = Math.min(fb.h - 1, Math.ceil(Math.max(...scr.map((p) => p[1]))));
      if (maxX < minX || maxY < minY) continue;

      const zNear = Math.min(scr[0][2], scr[1][2], scr[2][2], scr[3][2]);
      const zFar = Math.max(scr[0][2], scr[1][2], scr[2][2], scr[3][2]);

      for (let py = minY; py <= maxY; py++) {
        for (let px = minX; px <= maxX; px++) {
          const hit = pixelToUv(scr, quadUv, px, py);
          if (!hit) continue;
          // 沿边的位置 → 纹理横向坐标（与应用同一个 edgeCoord）
          const along = hit.u * 2 - 1;
          const ec = view.edgeCoord(s.axisY, along);
          const at = Math.round(ec * (arr.length - 1));
          const col = arr[Math.max(0, Math.min(arr.length - 1, at))];

          const zndc = zNear + (zFar - zNear) * hit.v;
          const di = py * fb.w + px;
          if (zndc > fb.depth[di]) continue;
          fb.depth[di] = zndc;

          const o4 = di * 4;
          fb.rgba[o4] = col[0];
          fb.rgba[o4 + 1] = col[1];
          fb.rgba[o4 + 2] = col[2];
          fb.rgba[o4 + 3] = 255;
          drawn++;
          if (perSide) perSide[s.side] = (perSide[s.side] || 0) + 1;
        }
      }
    }
  }
  return drawn;
}

export function pixel(fb, x, y) {
  const xi = clamp(Math.round(x), 0, fb.w - 1);
  const yi = clamp(Math.round(y), 0, fb.h - 1);
  const o = (yi * fb.w + xi) * 4;
  return [fb.rgba[o], fb.rgba[o + 1], fb.rgba[o + 2], fb.rgba[o + 3]];
}

/** 非背景像素数 */
export function litCount(fb, bg, tol) {
  const t = tol === undefined ? 6 : tol;
  const b = bg || [5, 7, 11];
  let n = 0;
  for (let i = 0; i < fb.w * fb.h; i++) {
    const o = i * 4;
    if (Math.abs(fb.rgba[o] - b[0]) > t ||
        Math.abs(fb.rgba[o + 1] - b[1]) > t ||
        Math.abs(fb.rgba[o + 2] - b[2]) > t) n++;
  }
  return n;
}

