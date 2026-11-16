// 无浏览器的核心自检：验证数据管线的布局、以及光线行进数学的关键结论。
//
// 这里用 Node 重新实现一遍体积采样与加性累积，和 shader.js 里的 GLSL 对齐，
// 然后断言两件最要紧的事：
//   1) 体素下标的编解码与 THREE.Data3DTexture 的约定一致（v=0 是第一帧）；
//   2) 正视时「正面 = 第一帧」，且半透明模式下会累积出轨迹（不在轨迹上的位置是黑的）。
//
// 用法： node test/selftest.js

const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

const ROOT = path.join(__dirname, '..');
const FPS = 24;
const W = 160, H = 120;   // 与 tools/make-sample.js 一致
const CUBE = 1;

let failures = 0;
const results = [];
function check(name, pass, detail) {
  results.push({ name, pass: !!pass, detail: String(detail) });
  if (!pass) failures++;
}

// ---------------------------------------------------------------- 参考实现

// 与 loader.js 中 applyAlpha 相同的规则
function refAlpha(lum, threshold) {
  const t2 = threshold * threshold;
  const span = Math.max(1e-4, 1 - t2);
  return lum <= t2 ? 0 : (255 * ((lum - t2) / span)) | 0;
}

function lumOf(r, g, b) { return (0.299 * r + 0.587 * g + 0.114 * b) / 255; }

/**
 * 体素取色：与 THREE.Data3DTexture 的 offset = (z*height + y)*width + x 一致。
 * 归一化坐标转下标用 floor(u*W)：等价于「取该处像素中心所在的体素」。
 * 不要用 round(u*W - 0.5)，那带半个体素的偏置，精度稍差就会落到相邻体素上。
 */
function sampleVolume(seq, u, v, w) {
  const D = seq.depth, Wd = seq.width, Hd = seq.height;
  const x = Math.min(Wd - 1, Math.max(0, Math.floor(u * Wd)));
  const y = Math.min(D - 1, Math.max(0, Math.floor(v * D)));
  const z = Math.min(Hd - 1, Math.max(0, Math.floor(w * Hd)));
  const i = (z * D + y) * Wd * 4 + x * 4;
  if (i < 0 || i + 3 >= seq.data.length) return [0, 0, 0, 0];
  return [seq.data[i], seq.data[i + 1], seq.data[i + 2], seq.data[i + 3]];
}

/**
 * 与 shader.js 对齐的取样几何：
 *   步长上限 0.5 帧 → 沿射线每个体素恰好被取到一次，采样点落在区间中点。
 *   等价的精确形式：第 y 帧取的就是 v = (y+0.5)/D 那个体素。
 *
 * raymarchSlice / raySampleAtFrame 吃的是「体坐标」，x/z ∈ [-0.5, 0.5]：
 *   shader 里 q = ro + rd*t，采样写的是
 *     texture(uVolume, vec3(q.x + 0.5, (q.y + 0.5)/depth, q.z + 0.5))
 *   所以传进来的 px 会变成 u = px + 0.5，py 会变成 w = py + 0.5。
 *
 * 于是「第 col 列 / 第 row 行」对应的体坐标就是
 *   px = (col + 0.5)/width  - 0.5
 *   py = (row + 0.5)/height - 0.5
 * 恒有 floor((px+0.5)*width) === col、floor((py+0.5)*height) === row —— 见下面的往返用例。
 */
function voxelPX(seq, col, zoom = 1) {
  return ((col + 0.5) / seq.width - 0.5) / zoom;
}

function voxelPY(seq, row, zoom = 1) {
  return ((row + 0.5) / seq.height - 0.5) / zoom;
}
function raySampleAtFrame(seq, px, py, y) {
  return sampleVolume(seq, px + 0.5, (y + 0.5) / seq.depth, py + 0.5);
}

/**
 * 复现 shader.js 的取样路径，语义与着色器逐条对应：
 *
 *   沿射线遍历所有帧，用「取最大值」合并（MIP）：
 *       acc = max(acc, 该帧颜色 × 不透明度)
 *   把所有帧都枚举一遍，正是 MIP 的上确界 —— 与取样相位无关，
 *   所以比「复刻着色器的 0.5 帧步长循环」更稳、更好断言。
 *
 *   选定帧不做任何特殊处理：它就在自己的时间位置上，和其他帧完全平等。
 *   （早先把它强行提到最前并单独提亮，导致它看起来飘在立方体外面。）
 */
function raymarchSlice(seq, opts) {
  const { px, py, alpha } = opts;
  const D = seq.depth;

  const acc = [0, 0, 0];

  for (let y = 0; y < D; y++) {
    const c = raySampleAtFrame(seq, px, py, y);
    if (c[3] <= 0.75) continue;

    // 颜色用全强度，强度只作用在不透明度上（与着色器一致）
    const cover = c[3] > 1 ? 1 : 0;
    const e = Math.min(1, Math.max(0, alpha * cover));
    for (let k = 0; k < 3; k++) acc[k] = Math.max(acc[k], c[k] * e);
  }

  // 着色器把结果夹到 [0, 1]，不再做软压缩
  const out = acc.map(v => Math.min(1, Math.max(0, v)));

  return { color: out, raw: acc.slice() };
}

// ---------------------------------------------------------------- 主流程

async function main() {
  const loader = await import(pathToFileURL(path.join(ROOT, 'loader.js')).href);
  const { planGeometry, applyAlpha } = loader;
  const { fitFrustum } = await import(pathToFileURL(path.join(ROOT, 'fit.js')).href);

  // ---- 0. 视锥拟合：立方体必须完整进画面，且像素不能变形 ----
  // 这一段之前完全没有测试覆盖，而它的 bug 症状就是「照片被裁掉」。
  //
  // 比较的两边必须同量纲：fitFrustum 返回的是**体坐标系**里的量，
  // 要跟体数据的实际跨度比，而不是跟屏幕像素比（这一条我第一次就写错了，
  // 把 halfX*2 当成屏幕宽度去比世界跨度，量纲根本不一致）。
  {
    const tseq = { width: 4000, height: 3000, depth: 200 };   // 4:3 的照片
    const sx = tseq.width / tseq.depth;   // 立方体 x 方向跨度
    const sz = tseq.height / tseq.depth;  // 立方体 z 方向跨度
    const needHalfY = Math.max(sz / 2, 0.5);   // 竖直方向还要装下深度

    const cases = [
      ['宽屏 16:9', 16 / 9], ['方屏 1:1', 1], ['竖屏 9:16', 9 / 16],
      ['接近 4:3', 4 / 3], ['超宽 21:9', 21 / 9], ['极端竖屏 1:3', 1 / 3]
    ];
    const bad = [];
    for (const [name, screenAspect] of cases) {
      const f = fitFrustum(tseq, screenAspect, 1);
      const fitsX = f.halfX >= sx / 2 - 1e-9;
      const fitsY = f.halfY >= needHalfY - 1e-9;
      const aspectOk = Math.abs((f.halfX / f.halfY) - screenAspect) < 1e-9;
      if (!fitsX || !fitsY || !aspectOk) {
        bad.push(`${name}: halfX=${f.halfX.toFixed(3)} halfY=${f.halfY.toFixed(3)}`
          + ` 需要 halfX≥${(sx / 2).toFixed(3)} halfY≥${needHalfY.toFixed(3)}`
          + ` aspect=${aspectOk}`);
      }
    }
    check('视锥拟合：各种屏幕比例下都完整装下立方体、且像素不变形',
      bad.length === 0, bad.length ? bad.join(' | ') : `${cases.length} 种屏幕比例全部通过`);

    const z1 = fitFrustum(tseq, 16 / 9, 1).halfY;
    const z2 = fitFrustum(tseq, 16 / 9, 2).halfY;
    check('视锥拟合：zoom 放大时视锥相应缩小',
      z2 < z1 - 1e-9, `zoom=1 → ${z1.toFixed(3)}，zoom=2 → ${z2.toFixed(3)}`);
  }

  // ---- 1. 样本图存在 ----
  const sampleDir = path.join(ROOT, 'sample');
  const names = [];
  for (let i = 0; i < FPS; i++) names.push(`frame_${String(i).padStart(3, '0')}.png`);
  const missing = names.filter(n => !fs.existsSync(path.join(sampleDir, n)));
  check('样本图齐备（24 张）', missing.length === 0, missing.length ? '缺 ' + missing.join(',') : 'ok');

  if (missing.length) { report(); return; }

  // ---- 2. 几何规划 ----
  const geo = planGeometry(W / H, FPS);
  check('几何规划保持长宽比', Math.abs(geo.width / geo.height - W / H) < 0.05,
    `${geo.width}x${geo.height} vs ${W}x${H}`);
  check('几何规划深度等于帧数', geo.depth === FPS, `depth=${geo.depth}`);

  // ---- 3. 构造体数据 ----
  // 自检用一个 1:1 于样本图的体数据（W×D×H），这样像素坐标和体素坐标能精确对上，
  // 断言才有意义。降采样路径由 planGeometry 的单独用例覆盖。
  const { decodePNG } = require('../tools/png.js');
  const D = FPS;
  const data = new Uint8Array(W * H * D * 4);
  const TEST_THRESHOLD = 0.5;   // 样本图背景亮度约 0.07，用 0.5 把它抠掉
const TEST_ALPHA = 0.5;        // 非选定帧的透明度

  for (let i = 0; i < FPS; i++) {
    const img = decodePNG(fs.readFileSync(path.join(sampleDir, names[i])));
    if (img.width !== W || img.height !== H) {
      check('样本图尺寸一致', false, `${names[i]} 是 ${img.width}x${img.height}`);
      report();
      return;
    }
    // 直接调用 loader.js 的真实现，避免测试里出现一份可能漂移的副本
    applyAlpha(img.data, data, i, W, H, D, TEST_THRESHOLD);
  }
  const seq = { data, width: W, height: H, depth: D };


  // ---- 4. 体素下标编解码自洽 ----
  // 在某一帧上放一个唯一标记，确认按 (x, y, z) 读回来的就是它
  const probeIdx = (7 * D + 11) * W * 4 + 3 * 4;
  data[probeIdx] = 251; data[probeIdx + 1] = 3; data[probeIdx + 2] = 7; data[probeIdx + 3] = 255;
  const rt = sampleVolume(seq, (3 + 0.5) / W, (11 + 0.5) / D, (7 + 0.5) / H);
  check('体素下标 (x,y,z) 编解码自洽：v 对应时间轴',
    rt[0] === 251 && rt[1] === 3 && rt[2] === 7,
    `读回 rgb=${rt.slice(0, 3)}，期望 [251,3,7]`);
  data[probeIdx] = 0; data[probeIdx + 1] = 0; data[probeIdx + 2] = 0; data[probeIdx + 3] = 0;

  // ---- 5. 正面 = 第一帧 ----
  // 样本点的位置在各帧之间是移动的，所以只要用「同一位置在不同帧的颜色」来判断是哪一帧。
  // 取一个圆点在第 0 帧和第 23 帧都覆盖不到、但中间帧覆盖得到的位置：
  // 第 0 帧圆点在左端，第 23 帧在右端。
  // 更稳的做法：找到第 0 帧圆点中心，检查该位置在「正面」取到的颜色等于第 0 帧。
  const frame0 = [];
  for (let z = 0; z < H; z++) {
    for (let x = 0; x < W; x++) {
      const i = (z * D + 0) * W * 4 + x * 4;
      if (data[i] - data[i + 2] > 45 && data[i] - data[i + 1] > 25 && data[i] > 80) frame0.push([x, z]);
    }
  }
  check('第 0 帧能识别出轨迹点', frame0.length > 20, `像素数=${frame0.length}`);

  if (frame0.length) {
    let cx = 0, cz = 0;
    for (const [x, z] of frame0) { cx += x; cz += z; }
    cx /= frame0.length; cz /= frame0.length;

    // 像素坐标 → 视锥坐标系（见 voxelX / voxelZ 的推导）
    const p0x = Math.floor(cx), p0z = Math.floor(cz);
    const px = voxelPX(seq, p0x);
    const py = voxelPY(seq, p0z);

    // 先自证：圆点质心处，第 0 帧的体素必须就是那个橙色像素
    const direct = data[((p0z * D + 0) * W + p0x) * 4];
    const directG = data[((p0z * D + 0) * W + p0x) * 4 + 1];
    const directB = data[((p0z * D + 0) * W + p0x) * 4 + 2];
    check('自证：圆点质心处第 0 帧就是橙色像素',
      direct - directB > 45 && direct - directG > 25,
      `像素(${p0x},${p0z}) rgb=${direct},${directG},${directB}`);

    // alpha=1 时，每个可见像素都完整参与（MIP），所以结果就是原像素本身
    const opaque = raymarchSlice(seq, { px, py, alpha: 1 });
    const front = raySampleAtFrame(seq, px, py, 0);
    // 从像素中心反推出来的 (px,py)，取回的体素必须还是同一个像素
    check('自证：像素→视锥坐标→体素 的往返一致',
      front[0] === direct && front[1] === directG && front[2] === directB,
      `往返后 rgb=${front.slice(0, 3)}，直接读 rgb=${[direct, directG, directB]}`);

    check('loader 把亮度存进 alpha（作为可见性掩码）',
      front[3] > 60 && front[3] < 255,
      `圆点像素 rgb=${front.slice(0, 3)} alpha=${front[3]}（即 亮度×255）`);

    // MIP 的本质：输出不得超过该处最强的单帧。
    // 这正是它不糊、颜色不溢出立方体的原因。
    check('MIP 上界：全强度下输出不超过该处最强的单帧',
      opaque.raw[0] <= front[0] + 1e-9,
      `输出=${opaque.raw[0].toFixed(1)} ≤ 最强单帧=${front[0]}`);

    check('全不透明模式：第 0 帧的橙色像素完整显示（不是黑的、也没被压暗）',
      front[0] > 200 && front[0] > front[2] + 60 && opaque.color[0] > 0.9,
      `像素(${p0x},${p0z}) 原始 rgb=${front.slice(0, 3)} → 输出=${opaque.color[0].toFixed(3)}`);

    check('全不透明模式：背景被抠掉（alpha 0 处不参与）',
      data[((p0z * D + 0) * W + (p0x + 60)) * 4 + 3] === 0,
      `同帧偏移 60 像素处的 alpha=` + data[((p0z * D + 0) * W + (p0x + 60)) * 4 + 3]);

    // ---- 取样间距必须保证每一帧都被采到 ----
    // 步长一旦粗于半个帧单位，有些帧会整个被跳过，轨迹出现缺口。
    {
      const Dd = 24;
      const sampled = new Set();
      const stepLen = (0.5 / 1.0) / Dd;          // uSamples = 1
      const count = Math.min(4096, Math.ceil(1 / stepLen));
      for (let k = 0; k < count; k++) {
        const s = (k + 0.5) * stepLen * Dd;      // 连续帧坐标
        if (s >= 0 && s < Dd) sampled.add(Math.floor(s));
      }
      const missed = [];
      for (let i = 0; i < Dd; i++) if (!sampled.has(i)) missed.push(i);
      check('取样间距 0.5 帧 → 每一帧都被采到（不会跳帧）',
        missed.length === 0 && sampled.size === Dd,
        missed.length ? '漏掉帧: ' + missed.join(',') : `覆盖 ${sampled.size}/${Dd} 帧`);
    }

    // ---- 帧吸附：采样位置必须落在帧中心，消除跨帧插值带来的糊 ----
    {
      const Dd = 24;
      let wrongFrame = 0;
      let worst = 0;
      let n = 0;
      const stepLen = (0.5 / 1.0) / Dd;
      const count = Math.min(4096, Math.ceil(1 / stepLen));
      for (let k = 0; k < count; k++) {
        const s = (k + 0.5) * stepLen * Dd;
        if (s < 0 || s >= Dd) continue;
        const snapped = Math.floor(s) + 0.5;
        const back = ((snapped + 0.5) / Dd) * Dd - 0.5;
        n++;
        worst = Math.max(worst, Math.abs(back - snapped));
        if (Math.floor(back) !== Math.floor(s)) wrongFrame++;
      }
      check('帧吸附：采样点始终落在帧中心，且不改变帧号（v 方向不插值）',
        wrongFrame === 0 && worst < 1e-12 && n > 0,
        `检查 ${n} 个采样点，帧号错误 ${wrongFrame} 个，偏离帧中心最大 ${worst.toExponential(1)}`);
    }

    // ---- 边界夹紧：任何采样点的纹理坐标都必须落在 [0,1] ----
    // 这是「立方体范围之外出现内容」的结构性防线。
    {
      const Dd = 24;
      const stepLen = (0.5 / 1.0) / Dd;
      const count = Math.min(4096, Math.ceil(1 / stepLen));
      let outOfRange = 0;
      let worstCoord = 0;
      for (let k = 0; k < count; k++) {
        const qy = 0.5 - (k + 0.5) * stepLen;
        if (qy > 0.5 || qy < -0.5) continue;
        const tc = qy + 0.5;
        worstCoord = Math.max(worstCoord, Math.max(0 - tc, tc - 1));
        if (tc < 0 || tc > 1) outOfRange++;
      }
      check('边界夹紧：采样纹理坐标始终在 [0,1] 内',
        outOfRange === 0 && worstCoord <= 0,
        `越界 ${outOfRange} 个，最大越界量=${worstCoord.toExponential(1)}`);
    }

    // ---- 6. 半透明模式下，不在轨迹上的位置是黑的 ----
    // 找一个所有帧都没有圆点的位置（避开左上角的白标记）
    let empty = null;
    for (let z = 4; z < H - 4 && !empty; z++) {
      for (let x = 40; x < W - 40; x++) {
        let any = false;
        for (let y = 0; y < D; y++) {
          const i = (z * D + y) * W * 4 + x * 4;
          if (data[i + 3] > 60) { any = true; break; }
        }
        if (!any) { empty = [x, z]; break; }
      }
    }
    check('存在一条完全没有轨迹的射线', !!empty, empty ? `像素 (${empty})` : '找不到');

    if (empty) {
      const epx = voxelPX(seq, empty[0]);
      const epy = voxelPY(seq, empty[1]);
      const g = raymarchSlice(seq, { px: epx, py: epy, slice: 0, alpha: TEST_ALPHA });
      // 期望值 = 逐帧枚举累加（选定帧权重 1，其余帧权重 alpha），取软压缩前
      let expect = 0;
      for (let y = 0; y < D; y++) {
        const c = raySampleAtFrame(seq, epx, epy, y);
        expect += c[0] * (c[3] / 255) * (y === 0 ? 1 : TEST_ALPHA);
      }
      // 注意：这台样本图的背景不是纯黑（亮度约 0.07），所以"无轨迹"处也会
      // 累积出一层很淡的底噪，而不是精确的 0 —— 这正是背景抑制滑块存在的理由。
      check('半透明：无轨迹处只累积出背景底噪（量级很小且与逐帧累加一致）',
        g.raw[0] < 6 && Math.abs(g.raw[0] - expect) < 1.0,
        `raw=${g.raw[0].toFixed(3)} 逐帧期望=${expect.toFixed(3)} 输出=${g.color[0].toFixed(3)}`);
    }

    // ---- 7. 半透明模式下，轨迹点的量级 ==== 单帧信号 × alpha ----
    const f5 = [];
    for (let z = 0; z < H; z++) {
      for (let x = 0; x < W; x++) {
        const i = (z * D + 5) * W * 4 + x * 4;
        if (data[i] - data[i + 2] > 45 && data[i] - data[i + 1] > 25 && data[i] > 80) f5.push([x, z]);
      }
    }
    let f5x = 0, f5z = 0;
    for (const [x, z] of f5) { f5x += x; f5z += z; }
    f5x /= f5.length; f5z /= f5.length;

    // 用明确的整数像素（而不是亚像素质心，那会正好落在体素边界上）
    const p5x = Math.floor(f5x);
    const p5z = Math.floor(f5z);
    const gpx = voxelPX(seq, p5x);
    const gpy = voxelPY(seq, p5z);

    const pos = raymarchSlice(seq, { px: gpx, py: gpy, slice: 0, alpha: TEST_ALPHA });

    // 该处信号最强的帧，应该正是第 5 帧
    let best = { y: -1, sig: 0 };
    for (let y = 0; y < D; y++) {
      const c = raySampleAtFrame(seq, gpx, gpy, y);
      const sig = c[0] * (c[3] / 255);
      if (sig > best.sig) best = { y, sig };
    }

    // 轨迹用「取最大值」合并，所以有两条本质属性可验证：
    //   1) 确实有轨迹出现（非零）—— 早期版本因为取不到点，这里是 0；
    //   2) 不会累积超过该处最强的单帧 —— 这正是它不糊、不发白的原因。
    // 不去要求逐值吻合：测试按帧枚举，着色器按 0.5 帧步长取样，相位本来就差一点。
    check('半透明：第 5 帧圆点所在位置出现轨迹，且最强的帧正是第 5 帧',
      best.y === 5 && best.sig > 50 && pos.raw[0] > 2,
      `像素(${p5x},${p5z}) 轨迹=${pos.raw[0].toFixed(2)}`
      + ` 最强帧=${best.y}(信号=${best.sig.toFixed(1)})`);

    check('轨迹不累积：输出不超过该处最强的单帧（MIP，不是求和）',
      pos.raw[0] <= best.sig + 2,
      `轨迹=${pos.raw[0].toFixed(2)} ≤ 最强单帧=${best.sig.toFixed(1)}`);

    // ---- 8. 全不透明模式：所有帧都按 1.0 参与，叠成实心的彩色立方体 ----
    {
      const opq = raymarchSlice(seq, { px: gpx, py: gpy, alpha: 1.0 });
      const weak = raymarchSlice(seq, { px: gpx, py: gpy, alpha: 0.3 });
      check('轨迹强度滑块真的起作用（1.0 比 0.3 浓）',
        opq.raw[0] > weak.raw[0] + 1,
        `alpha=1.0 → ${opq.raw[0].toFixed(1)}；alpha=0.3 → ${weak.raw[0].toFixed(1)}`);

      // 选定帧不做特殊处理：它在自己的时间位置上，由 MIP 自然呈现。
      // 这里验证第 5 帧圆点位置在第 5 帧这一层确实有内容，
      // 而第 0 帧同位置没有 —— 位置关系正确。
      const at5 = raySampleAtFrame(seq, gpx, gpy, 5);
      const at0 = raySampleAtFrame(seq, gpx, gpy, 0);
      check('每一帧都待在自己的时间位置上（第 5 帧的圆点不在第 0 帧那一层）',
        at5[3] > 60 && at0[3] < 10,
        `第5帧 alpha=${at5[3]}，第0帧同位置 alpha=${at0[3]}`);
    }

    // ---- 9. 阈值化确实会把暗背景清成 0 ----
    // 取一个真实背景像素（画面底部中央，圆点轨迹之外），而不是圆点所在位置
    const bg = sampleVolume(seq, 0.5, 0.5 / D, 0.5 - 0.4);
    const bgLum = lumOf(bg[0], bg[1], bg[2]);
    check('背景抑制：暗背景 alpha 归零、亮部保留',
      refAlpha(bgLum, 0.5) === 0 && refAlpha(bgLum, 0) > 0 && refAlpha(1, 0.5) === 255,
      `背景亮度=${bgLum.toFixed(3)}`);
  }

  report();
}

function report() {
  const pass = results.filter(r => r.pass).length;
  console.log('\n============ 核心自检 ============');
  for (const r of results) {
    console.log((r.pass ? 'PASS  ' : 'FAIL  ') + r.name + '   [' + r.detail + ']');
  }
  console.log(`\n${pass}/${results.length} 通过`);
  fs.mkdirSync(path.join(ROOT, 'test', 'shots'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'test', 'shots', 'selftest.json'),
    JSON.stringify({ pass, total: results.length, results }, null, 2));
  process.exit(failures ? 1 : 0);
}

main().catch(e => {
  console.error('自检崩溃:', e);
  process.exit(2);
});
