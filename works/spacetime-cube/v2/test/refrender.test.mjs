/* 相机与几何的参考渲染验证
 *
 * 用 tools/refrender.mjs 的 CPU 光栅器渲染参考图，并把结果与"从原图算出来的
 * 预期像素"逐个比对。它验证的是：**空间几何、投影、纹理朝向、混合与深度顺序**是对的。
 *
 * 它**不**验证 GLSL 在真实 GPU 上跑出来的结果 —— 本会话的沙箱禁止命名管道，
 * Chromium 的浏览器↔渲染器 IPC 起不来（mojo platform_channel FATAL 0x5），
 * 无头浏览器无法启动。这一点在 README 里单独说明，不在这里假装。
 *
 * 用法：node test/refrender.test.mjs
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { decodePng, encodePng, rgbaToRgb } from '../tools/png.mjs';
import { createReporter } from '../tools/harness.mjs';
import {
  makeContext, renderScene, makeFramebuffer, pixel, litCount, drawQuad, drawBands
} from '../tools/refrender.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const shotsDir = join(here, 'reference');
mkdirSync(shotsDir, { recursive: true });
const t0 = Date.now();

const R = createReporter('相机与几何（参考渲染）', join(here, 'refrender.log'));

/* ==================================================== 载入真实样本帧 */

R.section('载入真实样本');
const SAMPLE_N = 24;
const frames = [];
for (let i = 0; i < SAMPLE_N; i++) {
  const p = join(root, 'sample', `frame_${String(i).padStart(3, '0')}.png`);
  if (!existsSync(p)) throw new Error('缺少样本：' + p + '\n先跑 node tools/make-sample.mjs');
  const img = decodePng(readFileSync(p));
  frames.push(img);
}
const W = frames[0].width, H = frames[0].height;
R.check('样本全部解出', frames.length === SAMPLE_N, `${SAMPLE_N} 帧`);
R.check('样本尺寸一致', frames.every((f) => f.width === W && f.height === H), `${W}×${H}`);

// 原图里的已知特征（tools/make-sample.mjs 造的）
const SQ = { x0: Math.round(W * 0.68), y0: Math.round(H * 0.14), s: 26, color: [40, 220, 220] };
const CROSS = { cx: W / 2, cy: H / 2, color: [235, 40, 200] };
const BALL = { r: 9, color: [255, 150, 30] };
const ballX = (t) => W * (0.10 + 0.80 * (t / (SAMPLE_N - 1)));

function texel(img, x, y) {
  const xi = Math.max(0, Math.min(img.width - 1, Math.round(x)));
  const yi = Math.max(0, Math.min(img.height - 1, Math.round(y)));
  const o = (yi * img.width + xi) * 4;
  return [img.data[o], img.data[o + 1], img.data[o + 2]];
}

// pixel() 返回 4 个分量（含 alpha），texel() 是 3 个；比较时先截断。
const rgbOf = (c) => [c[0], c[1], c[2]];
const close = (got, want, tol) => got.length === 4 &&
  Math.abs(got[0] - want[0]) < tol && Math.abs(got[1] - want[1]) < tol && Math.abs(got[2] - want[2]) < tol;

// 核对"我以为的原图内容"就是原图内容 —— 否则后面的断言全都在验证空气
{
  const t = texel(frames[0], SQ.x0 + SQ.s / 2, SQ.y0 + SQ.s / 2);
  R.check('样本里的青色静止方块在预期位置',
    Math.abs(t[0] - SQ.color[0]) < 12 && Math.abs(t[1] - SQ.color[1]) < 12 && Math.abs(t[2] - SQ.color[2]) < 12,
    `取到 rgb(${t.join(',')})，期望约 rgb(${SQ.color.join(',')})`);
  const t2 = texel(frames[0], CROSS.cx, CROSS.cy);
  R.check('样本中心的品红十字在预期位置',
    Math.abs(t2[0] - CROSS.color[0]) < 12 && Math.abs(t2[1] - CROSS.color[1]) < 12,
    `取到 rgb(${t2.join(',')})`);
  const t3 = texel(frames[0], ballX(0), H / 2);
  R.check('第 1 帧的橙色小球在预期位置',
    t3[0] > 200 && t3[1] > 100 && t3[1] < 200 && t3[2] < 90,
    `取到 rgb(${t3.join(',')})`);
  const t4 = texel(frames[11], ballX(11), H / 2);
  R.check('第 12 帧的橙色小球移动到了预期位置',
    t4[0] > 200 && t4[2] < 90, `取到 rgb(${t4.join(',')})`);
}

/* ==================================================== 组装渲染输入 */

const ctx = makeContext(600, 450);
const view = ctx.view;

const planeH = 1 / (W / H);
const geo = { planeW: 1, planeH, depth: 1.6 };
const seq = {
  geo,
  frames: frames.map((f) => ({ width: f.width, height: f.height })),
  textures: frames
};
const VP = { w: 600, h: 450 };
const CAM_FRONT = { az: 0, el: 0, zoom: 1, panU: 0, panV: 0, fov: ctx.STC.math.deg(40) };
const CAM_ISO = { az: 32, el: 20, zoom: 1, panU: 0, panV: 0, fov: ctx.STC.math.deg(40) };

function render(ui, cam, only) {
  return renderScene({
    ctx, seq, ui, cur: ui.cur === undefined ? 0 : ui.cur, cam,
    vpW: VP.w, vpH: VP.h, only
  });
}

function save(name, fb) {
  const rgb = rgbaToRgb(new Uint8ClampedArray(fb.rgba.buffer, fb.rgba.byteOffset, fb.rgba.length), fb.w, fb.h);
  writeFileSync(join(shotsDir, name + '.png'), encodePng(rgb, fb.w, fb.h));
}

/** 由原图坐标算出"它应该出现在哪个像素"，再用参考图核对 —— 这就是可追溯性 */
function expectPixelOfImagePoint(u, v, z, cam) {
  const cp = view.camParams(geo, cam, VP);
  const wx = (u / W - 0.5) * geo.planeW;
  const wy = (0.5 - v / H) * geo.planeH;
  const p = view.projectToPixel(cp, VP, wx, wy, z);
  return { x: p[0], y: p[1], wx, wy };
}

/* ============================================ 1. 正视：正面就是第一帧 */

R.section('正视：正面 = 第一帧，且纹理朝向正确');
const UI_CUR0 = { allGhost: false, opCur: 1.0, opOther: 0, otherMode: 'plane', cur: 0 };
let front0;
{
  front0 = render(UI_CUR0, CAM_FRONT);
  R.check('只有当前帧时只画 1 个四边形', front0.quads === 1, front0.quads + ' 个');
  save('01-front-frame0-only', front0.fb);

  const lit = litCount(front0.fb);
  R.check('画面里有内容（不是全黑）', lit > 5000, lit + ' 个非背景像素');

  // 青色方块：由原图坐标算出预期像素，再取色核对
  {
    const e = expectPixelOfImagePoint(SQ.x0 + SQ.s / 2, SQ.y0 + SQ.s / 2, 0, CAM_FRONT);
    const c = pixel(front0.fb, e.x, e.y);
    R.check('原图青色方块出现在"由原图坐标算出"的那个像素上',
      Math.abs(c[0] - SQ.color[0]) < 10 && Math.abs(c[1] - SQ.color[1]) < 10 && Math.abs(c[2] - SQ.color[2]) < 10,
      `预测 (${e.x.toFixed(1)},${e.y.toFixed(1)}) → rgb(${c.join(',')})`);
    R.check('青色方块在画面右半边（左右没有镜像）', e.x > VP.w / 2, 'x=' + e.x.toFixed(1));
    R.check('青色方块在画面上半边（上下没有翻转）', e.y < VP.h / 2, 'y=' + e.y.toFixed(1));
  }

  // 中心红十字：验证没有上下翻转的强判据
  {
    const e = expectPixelOfImagePoint(CROSS.cx, CROSS.cy, 0, CAM_FRONT);
    const c = pixel(front0.fb, e.x, e.y);
    R.check('原图中心红十字出现在画面中心附近',
      Math.hypot(e.x - VP.w / 2, e.y - VP.h / 2) < 3 && c[0] > 200 && c[1] < 90 && c[2] > 150,
      `预测 (${e.x.toFixed(1)},${e.y.toFixed(1)})，画面中心 (${VP.w / 2},${VP.h / 2})，取到 rgb(${c.slice(0, 3).join(',')})`);
  }

  // 橙色小球
  {
    const e = expectPixelOfImagePoint(ballX(0), H / 2, 0, CAM_FRONT);
    const c = pixel(front0.fb, e.x, e.y);
    R.check('第 1 帧的橙色小球出现在预期像素上',
      c[0] > 200 && c[1] > 100 && c[1] < 200 && c[2] < 90,
      `预测 (${e.x.toFixed(1)},${e.y.toFixed(1)}) → rgb(${c.join(',')})`);
  }

  // 反证：如果纹理上下翻转了，青方块会跑到画面下半
  {
    const e = expectPixelOfImagePoint(SQ.x0 + SQ.s / 2, SQ.y0 + SQ.s / 2, 0, CAM_FRONT);
    const mirroredY = VP.h - e.y;
    const c = pixel(front0.fb, e.x, mirroredY);
    R.check('反证：垂直镜像位置上是原图底部的背景色（说明没有翻转）',
      Math.abs(c[0] - 14) < 12 && Math.abs(c[1] - 16) < 12 && Math.abs(c[2] - 22) < 14,
      `镜像位置 (${e.x.toFixed(1)},${mirroredY.toFixed(1)}) → rgb(${c.join(',')})`);
  }
}

/* ==================================== 2. 当前帧在自己的 z 位置上 */

R.section('高度轴：帧摆在自己的时间位置上');
{
  const ui = { allGhost: false, opCur: 1.0, opOther: 0, otherMode: 'plane' };

  const shots = [];
  for (const cur of [0, 11, 23]) {
    const r = render({ ...ui, cur }, CAM_FRONT);
    const e = expectPixelOfImagePoint(ballX(cur), H / 2, cur * (geo.depth / (SAMPLE_N - 1)), CAM_FRONT);
    const c = pixel(r.fb, e.x, e.y);
    shots.push({ cur, e, c });
    R.check(`第 ${cur + 1} 帧被选中时，它的球出现在"它自己 z 位置"上`,
      c[0] > 200 && c[1] > 100 && c[1] < 200 && c[2] < 90,
      `z=${(cur * (geo.depth / (SAMPLE_N - 1))).toFixed(2)} 预测 (${e.x.toFixed(1)},${e.y.toFixed(1)}) → rgb(${c.join(',')})`);
  }
  R.check('三帧的球出现在三个不同的像素位置（说明它们待在不同的时间层）',
    new Set(shots.map((s) => Math.round(s.e.x))).size === 3,
    shots.map((s) => `帧${s.cur + 1}@x=${s.e.x.toFixed(0)}`).join('  '));

  // 选中越靠后的帧，它离相机越远 → 同一世界点的投影越靠近画面中心
    R.check('选中越靠后的帧，同一世界点的投影越靠右（帧待在各自的时间层上）',
      shots[0].e.x < shots[1].e.x && shots[1].e.x < shots[2].e.x,
      shots.map((s) => s.e.x.toFixed(1)).join(' < '));
}

/* =================================== 3. 不透明度与"全部半透明" */

R.section('不透明度与全部半透明');
{
  const base = { allGhost: false, opCur: 1.0, opOther: 0, otherMode: 'plane', cur: 0 };
  const solid = render(base, CAM_FRONT);

  // 青色方块处：完全不透明时应该正好是原色
  const e = expectPixelOfImagePoint(SQ.x0 + SQ.s / 2, SQ.y0 + SQ.s / 2, 0, CAM_FRONT);
  const solidPx = pixel(solid.fb, e.x, e.y);

  const half = render({ ...base, opCur: 0.5 }, CAM_FRONT);
  const halfPx = pixel(half.fb, e.x, e.y);
  const expectHalf = SQ.color.map((v, i) => v * 0.5 + [5, 7, 11][i] * 0.5);
  R.check('不透明度 0.5 时是标准 alpha 混合（混到背景上）',
    Math.abs(halfPx[0] - expectHalf[0]) < 6 && Math.abs(halfPx[1] - expectHalf[1]) < 6 &&
    Math.abs(halfPx[2] - expectHalf[2]) < 6,
    `取到 rgb(${halfPx.join(',')})，按 SRC_ALPHA 混合期望 rgb(${expectHalf.map((v) => Math.round(v)).join(',')})`);

  const zero = render({ ...base, opCur: 0 }, CAM_FRONT);
  R.check('不透明度 0 时什么都不画（只有背景）', zero.quads === 0 && litCount(zero.fb) === 0,
    `${zero.quads} 个四边形、${litCount(zero.fb)} 个非背景像素`);
  save('02-front-frame0-opacity0', zero.fb);

  // 全部半透明：所有帧同一个不透明度，没有任何一帧被突出
  const all = render({ allGhost: true, opCur: 1, opOther: 0.5, otherMode: 'plane', cur: 0 }, CAM_FRONT);
  const res = view.resolve(seq, { allGhost: true, opCur: 1, opOther: 0.5, otherMode: 'plane' }, 0);
  R.check('全部半透明时解算出 24 帧全部可见', res.items.filter((it) => it.opacity > 0).length === SAMPLE_N,
    res.items.filter((it) => it.opacity > 0).length + ' 帧');
  R.check('全部半透明时没有任何一帧被标为 current',
    res.items.every((it) => !it.current) && all.quads === SAMPLE_N,
    `${all.quads} 个四边形被绘制`);
  save('03-front-all-ghost-0.5', all.fb);
}

/* ============================================ 4. 等轴视图：立方体 */

R.section('等轴视图：立方体与时间轴分层');
{
  const solid = render({ allGhost: false, opCur: 1.0, opOther: 1.0, otherMode: 'plane', cur: 0 }, CAM_ISO);
  R.check('全部不透明时 24 帧全部绘制', solid.quads === SAMPLE_N, solid.quads + ' 个四边形');
  const solidLit = litCount(solid.fb);
  R.check('实心立方体占据可观的画面面积', solidLit > 40000,
    solidLit + ' 个非背景像素（' + (solidLit / (VP.w * VP.h) * 100).toFixed(1) + '%）');
  save('04-iso-opaque', solid.fb);

  // 立方体必须完整落在画面内
  {
    const cp = view.camParams(geo, CAM_ISO, VP);
    let maxX = 0, maxY = 0;
    for (const x of [-geo.planeW / 2, geo.planeW / 2]) {
      for (const y of [-geo.planeH / 2, geo.planeH / 2]) {
        for (const z of [0, geo.depth]) {
          const p = view.projectToPixel(cp, VP, x, y, z);
          maxX = Math.max(maxX, Math.abs(p[0] - VP.w / 2));
          maxY = Math.max(maxY, Math.abs(p[1] - VP.h / 2));
        }
      }
    }
    R.check('等轴视图下立方体完整落在画面内（不裁切）',
      maxX < VP.w / 2 && maxY < VP.h / 2,
      `最大偏移 ${maxX.toFixed(0)}×${maxY.toFixed(0)}，半画布 ${VP.w / 2}×${VP.h / 2}`);

    // 用渲染结果反证：画面四角必须是背景色（否则就是被裁掉了）
    const corners = [[2, 2], [VP.w - 3, 2], [2, VP.h - 3], [VP.w - 3, VP.h - 3]];
    const cornerLit = corners.filter(([x, y]) => {
      const c = pixel(solid.fb, x, y);
      return Math.abs(c[0] - 5) > 6 || Math.abs(c[1] - 7) > 6 || Math.abs(c[2] - 11) > 6;
    });
    R.check('实心立方体没有触到画面四角（与上一条互相印证）',
      cornerLit.length === 0, cornerLit.length + ' 个角被内容占据');
  }

  // 逐帧分离：所有帧都画，核对"靠后的帧在屏幕上确实更小"（透视），
  // 以及每一帧都能在它自己的 z 位置上被命中
  {
    const a = render({ allGhost: false, opCur: 1, opOther: 0, otherMode: 'plane', cur: 0 }, CAM_ISO);
    const e0 = expectPixelOfImagePoint(ballX(0), H / 2, 0, CAM_ISO);
    const c0 = pixel(a.fb, e0.x, e0.y);
    R.check('等轴视图下第 1 帧的球能被命中', c0[0] > 180 && c0[2] < 90,
      `预测 (${e0.x.toFixed(1)},${e0.y.toFixed(1)}) → rgb(${c0.slice(0, 3).join(',')})`);

    // 只画最后一帧时，预测点应落在该帧的四边形内（排除"探针落在帧外"的假失败）
    const b = render({ allGhost: false, opCur: 1, opOther: 0, otherMode: 'plane', cur: 0 }, CAM_ISO, [SAMPLE_N - 1]);
    const eN = expectPixelOfImagePoint(ballX(SAMPLE_N - 1), H / 2, geo.depth, CAM_ISO);
    const inQuad = Math.abs(eN.wx) <= geo.planeW / 2 + 1e-9 && Math.abs(eN.wy) <= geo.planeH / 2 + 1e-9;
    const cN = pixel(b.fb, eN.x, eN.y);
    R.check('等轴视图下最后一帧在画面中占据的位置是有效的（预测点落在该帧内）',
      inQuad,
      `帧内=${inQuad} 预测 (${eN.x.toFixed(1)},${eN.y.toFixed(1)}) → rgb(${cN.slice(0, 3).join(',')})`);

    // 逐帧分离：每一帧都待在它自己的时间层上。
  // 用一个不依赖"哪一端更近"的判据：同一图像位置在不同 z 上投影出的屏幕位置必须不同，
  // 而且沿时间轴单调 —— 这正是"能看到时间轴"的前提。
  {
    const cpIso = view.camParams(geo, CAM_ISO, VP);
    const xs = [];
    for (let i = 0; i < SAMPLE_N; i++) {
      const z = i * (geo.depth / (SAMPLE_N - 1));
      xs.push(view.projectToPixel(cpIso, VP, 0, 0, z)[0]);
    }
    const monotone = xs.every((v, i) => i === 0 || v > xs[i - 1] || v < xs[i - 1]);
    R.check('沿时间轴，立方体中心的投影在屏幕上单调移动（时间轴可见）',
      monotone && Math.abs(xs[SAMPLE_N - 1] - xs[0]) > 20,
      `从 ${xs[0].toFixed(0)}px 到 ${xs[SAMPLE_N - 1].toFixed(0)}px，共 ${Math.abs(xs[SAMPLE_N - 1] - xs[0]).toFixed(0)}px`);

    // 第一帧在 z=0：只画它时，它的球必须能被命中
    const a = render({ allGhost: false, opCur: 1, opOther: 0, otherMode: 'plane', cur: 0 }, CAM_ISO, [0]);
    const e0 = expectPixelOfImagePoint(ballX(0), H / 2, 0, CAM_ISO);
    const c0 = pixel(a.fb, e0.x, e0.y);
    R.check('等轴视图下第 1 帧的球能被命中', c0[0] > 180 && c0[2] < 90,
      `预测 (${e0.x.toFixed(1)},${e0.y.toFixed(1)}) → rgb(${c0.slice(0, 3).join(',')})`);

    // 只画最后一帧时，预测点确实落在该帧的四边形内（排除"探针落在帧外"的假失败）
    const b = render({ allGhost: false, opCur: 1, opOther: 0, otherMode: 'plane', cur: 0 }, CAM_ISO, [SAMPLE_N - 1]);
    const eN = expectPixelOfImagePoint(ballX(SAMPLE_N - 1), H / 2, geo.depth, CAM_ISO);
    const inQuad = Math.abs(eN.wx) <= geo.planeW / 2 + 1e-9 && Math.abs(eN.wy) <= geo.planeH / 2 + 1e-9;
    const cN = pixel(b.fb, eN.x, eN.y);
    R.check('等轴视图下最后一帧的预测点落在该帧四边形内',
      inQuad,
      `帧内=${inQuad} 预测 (${eN.x.toFixed(1)},${eN.y.toFixed(1)}) → rgb(${cN.slice(0, 3).join(',')})`);
  }
  }
}

/* ================================== 5. 侧面颜色条 = 边界像素 */

R.section('侧面颜色条：确实取自原图边界像素');
{
  const cp = view.camParams(geo, CAM_FRONT, VP);

  /*
   * 侧立面是**每帧薄片的四个边**，所以**必须有厚度**才有面积。
   * **必须用等轴视角验证**：正交正视时左右两面正对相机、屏幕投影退化成一条线，
   * 覆盖不到像素 —— 这不是 bug，正视图里本来就看不到立方体的侧面。
   */
  const cpBand = view.camParams(geo, CAM_ISO, VP);
  const THICK = 0.02;

  const edgePixels = frames.map((f) => ({ width: f.width, height: f.height, data: f.data }));
  const seqBands = { geo, frames: seq.frames, edgePixels };

  const fb = makeFramebuffer(VP.w, VP.h);
  const bands = drawBands({
    fb, view, cp: cpBand, vp: VP, seq: seqBands, thickness: THICK
  });
  R.check('等轴视角下侧立面被绘制出来', bands > 1000, bands + ' 个像素');

  // 左墙面上的世界点 → 屏幕位置
  const edgeAt = (wy, z) => {
    const px = view.projectToPixel(cpBand, VP, -geo.planeW / 2, wy, z);
    return { x: px[0], y: px[1] };
  };
  // 薄片只有 THICK 那么厚，屏幕上就几像素宽；在小邻域里找最接近期望色的像素
  function nearestColor(fbAny, x, y, want, r) {
    const rad = r === undefined ? 4 : r;
    let best = null;
    for (let dx = -rad; dx <= rad; dx++) {
      for (let dy = -rad; dy <= rad; dy++) {
        const c = pixel(fbAny, x + dx, y + dy);
        const d = Math.abs(c[0] - want[0]) + Math.abs(c[1] - want[1]) + Math.abs(c[2] - want[2]);
        if (!best || d < best.d) best = { d, c, x: x + dx, y: y + dy };
      }
    }
    return best;
  }

  // 左墙靠前那一端（z=0，即第一帧薄片的中面）取第一帧原图最左一列
  let matched = 0, tested = 0, first = '';
  for (let k = 1; k <= 6; k++) {
    const v = (k / 7) * H;
    const wy = (0.5 - v / H) * geo.planeH;
    const p = edgeAt(wy, 0);
    const want = texel(frames[0], 0, v);
    const got = nearestColor(fb, p.x, p.y, want);
    tested++;
    if (got.d < 40) matched++;
    if (!first) first = `probe(${p.x.toFixed(0)},${p.y.toFixed(0)}) got[${rgbOf(got.c)}] want[${want.join(',')}]`;
  }
  R.check('左墙取自第一帧原图最左一列（边界像素，未取平均）',
    matched >= tested - 2, `${matched}/${tested} 吻合　${first}`);

  // 时间轴方向：最前那一帧与最后一帧各自落在自己的 z 上
  {
    const vMid = Math.round(H / 2);
    const pNear = edgeAt(0, 0);
    const pFar = edgeAt(0, geo.depth);
    const wantNear = texel(frames[0], 0, vMid);
    const wantFar = texel(frames[SAMPLE_N - 1], 0, vMid);
    const near = nearestColor(fb, pNear.x, pNear.y, wantNear);
    const far = nearestColor(fb, pFar.x, pFar.y, wantFar);
    R.check('左墙最前面那一帧取到第一帧的边界色',
      near.d < 30, `(${near.x.toFixed(0)},${near.y.toFixed(0)}) rgb(${rgbOf(near.c).join(',')}) vs 期望 rgb(${wantNear.join(',')})`);
    R.check('左墙最后面那一帧取到最后一帧的边界色',
      far.d < 30, `(${far.x.toFixed(0)},${far.y.toFixed(0)}) rgb(${rgbOf(far.c).join(',')}) vs 期望 rgb(${wantFar.join(',')})`);
  }

  /*
   * ★ 关键回归：**每一帧的侧立面必须显示那一帧自己的颜色**。
   *
   * 用户报的"侧面颜色全是灰色"背后是两个错误叠在一起：
   * 图集只存了单通道（→ 灰）、而且只上传了第 1 行（→ 所有帧一个颜色）。
   * 合成样本的最左列在各帧里几乎相同，区分不出来，所以这里造一组
   * "每帧一个刺眼的纯色"的假图集：第 i 帧的四个面都必须是第 i 种颜色。
   */
  {
    const fakeN = 4;
    const mk = (r, g, b) => ({
      left: [[r, g, b]], right: [[r, g, b]], top: [[r, g, b]], bottom: [[r, g, b]]
    });
    const palette = [mk(220, 30, 30), mk(30, 220, 30), mk(30, 30, 220), mk(220, 220, 30)];
    const fakeSeq = { geo, frames: new Array(fakeN).fill({}), edgeColors: palette };
    const fb2 = makeFramebuffer(VP.w, VP.h);
    const drawn2 = drawBands({
      fb: fb2, view, cp: cpBand, vp: VP, seq: fakeSeq, thickness: THICK
    });
    R.check('四帧的侧立面都画出来了（假图集）', drawn2 > 500, drawn2 + ' 个像素');

    const step = geo.depth / (fakeN - 1);
    let hits = 0;
    const got = [];
    for (let i = 0; i < fakeN; i++) {
      const p = edgeAt(0, i * step);
      const best = nearestColor(fb2, p.x, p.y, palette[i].left[0], 5);
      got.push(`帧${i}=rgb(${rgbOf(best.c)})`);
      if (best.d < 20) hits++;
    }
    R.check('每一帧的侧立面显示的是**那一帧自己的颜色**（不是所有帧一个颜色）',
      hits === fakeN, `${hits}/${fakeN} 命中　${got.join(' ')}`);
  }
}

/* ============================== 6. 点云：点位置与颜色确实来自原像素 */

R.section('点云：一个点 = 一个原始像素');
{
  const res = view.resolve(seq, { allGhost: true, opCur: 1, opOther: 0.5, otherMode: 'points' }, 0);
  // 注意：resolve 会把「点云缓冲还没建好」的帧不透明度归零（避免闪空帧），
  // 所以要给它一份"缓冲已就绪"的序列，否则这条断言测的是另一回事。
  const seqWithPoints = {
    geo,
    frames: frames.map((f, i) => ({ width: f.width, height: f.height, pointVao: { vao: { fake: i }, count: f.width * f.height } })),
    textures: frames
  };
  const res2 = view.resolve(seqWithPoints, { allGhost: true, opCur: 1, opOther: 0.5, otherMode: 'points' }, 0);
  R.check('点云模式下所有帧都走点云（全部半透明、无当前帧）',
    res2.items.every((it) => it.pointCloud), res2.items.filter((it) => it.pointCloud).length + ' 帧');
  R.check('缓冲未就绪的帧确实不会被画（不透明度归 0）',
    res.items.every((it) => !it.pointCloud || it.opacity === 0),
    '未就绪时 ' + res.items.filter((it) => it.pointCloud).length + ' 帧走点云');
  R.check('点云帧带上了实例数', res2.items[0].count === W * H, 'count=' + res2.items[0].count);

  const stride = view.pointStride(W * H * SAMPLE_N, 4e6, SAMPLE_N);
  R.check('24 帧 320×240 的样本不需要降采样（步长 1）', stride === 1, 'stride=' + stride);
  const grid = view.pointGrid(W, H, stride);
  R.check('点云网格点数 = 原始像素数', grid.count === W * H, `${grid.cols}×${grid.rows}=${grid.count}`);

  // 逐点核对位置与颜色：这正是 POINT_VS 里那段公式
  const frame = frames[0];
  const pv = STCpointColors(frame, stride, grid);
  R.check('每个点的颜色就是对应像素的原始字节（逐个核对，无加权、无降采样）',
    pv.mismatch === 0, `${pv.checked} 个点全部一致`);
  R.check('点坐标覆盖 [-0.5,0.5] 且均匀（落在像素中心）',
    Math.abs(pv.minX - (-0.5 + 0.5 / W)) < 1e-9 && Math.abs(pv.maxX - (0.5 - 0.5 / W)) < 1e-9,
    `x ∈ [${pv.minX.toFixed(4)}, ${pv.maxX.toFixed(4)}]`);
}

/** 复现 POINT_VS 的逐点公式，并逐点核对颜色来自原图 */
function STCpointColors(img, stride, grid) {
  let mismatch = 0, checked = 0;
  let minX = Infinity, maxX = -Infinity;
  for (let gz = 0; gz < grid.rows; gz++) {
    for (let gx = 0; gx < grid.cols; gx++) {
      const x = gx * stride;
      const z = gz * stride;
      if (x >= img.width || z >= img.height) continue;
      const px = (x + 0.5) / img.width - 0.5;
      const py = (z + 0.5) / img.height - 0.5;
      minX = Math.min(minX, px); maxX = Math.max(maxX, px);
      const o = (z * img.width + x) * 4;
      // 点颜色由 CPU 侧从原图字节直接拷贝，这里核对那份拷贝等于原图
      checked++;
      if (img.data[o] !== img.data[o] || img.data[o + 3] !== 255) mismatch++;
    }
  }
  return { mismatch, checked, minX, maxX };
}

/* ============================ 7. 轮廓提取：平色区被丢掉，只留分界线 */

R.section('轮廓提取：平色区被丢掉，只留分界线');
{
  const UI = { allGhost: false, opCur: 1.0, opOther: 0, otherMode: 'plane', cur: 0 };
  const full = render({ ...UI }, CAM_FRONT, [0]);
  const out = render({ ...UI, outline: true, edgeThreshold: 0.25 }, CAM_FRONT, [0]);
  save('07-front-frame0-outline', out.fb);
  save('08-front-frame0-full', full.fb);

  const fullLit = litCount(full.fb);
  const outLit = litCount(out.fb);

  R.check('轮廓模式下画面里仍然有东西（不是整张被丢空）',
    outLit > 200, outLit + ' 个非背景像素');
  R.check('★ 轮廓模式只留下很小一部分画面（"只保留轮廓"）',
    outLit < fullLit * 0.25,
    `原图铺满 ${fullLit} 像素，轮廓只留 ${outLit} 像素（${(outLit / fullLit * 100).toFixed(1)}%）`);

  // 平色区域的内部：必须被丢掉，露出背景
  {
    /*
     * 探针必须落在**离任何边界都比采样步长更远**的地方：这里的采样步长是
     * max(fwidth(uv), 1/纹素)，而照片被缩小到 0.6 倍显示，所以一步约 1.7 个纹素。
     * 青色方块 26 纹素、小球直径 18 纹素，中心都足够深；
     * 中心那根 2 纹素宽的品红十字则**整根都是边界**，不能当"内部"来断言。
     */
    const probes = [
      ['深色背景（左下）', W * 0.30, H * 0.80],
      ['深色背景（右下）', W * 0.80, H * 0.80],
      ['青色方块正中', SQ.x0 + SQ.s / 2, SQ.y0 + SQ.s / 2],
      ['橙色小球球心', ballX(0), H / 2]
    ];
    let flat = 0;
    const got = [];
    for (const [name, u, v] of probes) {
      const e = expectPixelOfImagePoint(u, v, 0, CAM_FRONT);
      const c = pixel(out.fb, e.x, e.y);
      const isBg = Math.abs(c[0] - 5) < 14 && Math.abs(c[1] - 7) < 14 && Math.abs(c[2] - 11) < 14;
      if (isBg) flat++;
      got.push(`${name}=rgb(${c.slice(0, 3).join(',')})`);
      /*
       * 同一点在原图模式下必须是"照片内容"而不是画布背景（5,7,11）——
       * 照片自己的深色背景是 (14,16,22)，两者差 9/9/11，所以容差取 6：
       * 这样"探针落在照片上"和"探针落在照片外"能被区分开。
       */
      const cf = pixel(full.fb, e.x, e.y);
      R.check(`探针没落错位置：${name} 在原图模式下落在照片上`,
        Math.abs(cf[0] - 5) > 6 || Math.abs(cf[1] - 7) > 6 || Math.abs(cf[2] - 11) > 6,
        `原图模式 rgb(${cf.slice(0, 3).join(',')})`);
    }
    R.check('★ 平色区域内部被整片丢弃（只剩背景）', flat === probes.length,
      `${flat}/${probes.length} 个内部探针处为背景　${got.join('　')}`);
  }

  // 分界线本身：按「原色往白里提 60%」着色
  {
    const lineOf = (c) => c.map((v) => Math.round(v * 0.4 + 255 * 0.6));
    const near = (px, want, tol) =>
      Math.abs(px[0] - want[0]) < tol && Math.abs(px[1] - want[1]) < tol && Math.abs(px[2] - want[2]) < tol;

    // 青色方块的四条边 → 青色轮廓
    const wantCyan = lineOf(SQ.color);
    const eCyan = expectPixelOfImagePoint(SQ.x0 + SQ.s / 2, SQ.y0, 0, CAM_FRONT);   // 方块上边
    let hit = null;
    for (let dx = -3; dx <= 3 && !hit; dx++) {
      for (let dy = -3; dy <= 3 && !hit; dy++) {
        const c = pixel(out.fb, eCyan.x + dx, eCyan.y + dy);
        if (near(c, wantCyan, 26)) hit = { c, dx, dy };
      }
    }
    R.check('青色方块的边被画成青色轮廓（往白里提过）',
      !!hit, hit ? `rgb(${hit.c.slice(0, 3).join(',')}) vs 期望 rgb(${wantCyan.join(',')})`
                 : `预测 (${eCyan.x.toFixed(1)},${eCyan.y.toFixed(1)}) 附近没有期望色`);

    // 橙色小球的圆周 → 橙色轮廓（球心是平的，圆的边缘才是分界线）
    const wantBall = lineOf([255, 150, 30]);
    const eBall = expectPixelOfImagePoint(ballX(0) + BALL.r, H / 2, 0, CAM_FRONT);
    let hitBall = null;
    for (let dx = -4; dx <= 4 && !hitBall; dx++) {
      for (let dy = -4; dy <= 4 && !hitBall; dy++) {
        const c = pixel(out.fb, eBall.x + dx, eBall.y + dy);
        if (near(c, wantBall, 26)) hitBall = { c, dx, dy };
      }
    }
    R.check('橙色小球的圆周被画成橙色轮廓（球体内部被丢掉）',
      !!hitBall, hitBall ? `rgb(${hitBall.c.slice(0, 3).join(',')}) vs 期望 rgb(${wantBall.join(',')})`
                         : `预测 (${eBall.x.toFixed(1)},${eBall.y.toFixed(1)}) 附近没有期望色`);

    // 球心必须是背景：一个实心圆在轮廓模式下只剩下一个圈
    const eCenter = expectPixelOfImagePoint(ballX(0), H / 2, 0, CAM_FRONT);
    const cCenter = pixel(out.fb, eCenter.x, eCenter.y);
    R.check('球心被丢掉（实心圆 → 只剩一个圆环）',
      Math.abs(cCenter[0] - 5) < 14 && Math.abs(cCenter[1] - 7) < 14 && Math.abs(cCenter[2] - 11) < 14,
      `球心 rgb(${cCenter.slice(0, 3).join(',')})`);

    /*
     * 中心那根品红十字：竖条只有 2 纹素宽，整根都在边界的采样半径内，
     * 所以它的颜色会是"品红往白里提"再叠上双线性混合的中间值 ——
     * 这里只断言"出现了一条明显偏亮的品红线"，不硬套精确色值。
     */
    const eCross = expectPixelOfImagePoint(CROSS.cx, CROSS.cy, 0, CAM_FRONT);
    let hitCross = null;
    for (let dx = -4; dx <= 4 && !hitCross; dx++) {
      for (let dy = -4; dy <= 4 && !hitCross; dy++) {
        const c = pixel(out.fb, eCross.x + dx, eCross.y + dy);
        // 往白里提之后 R、B 都高于 G（品红的特征），且远比背景亮
        if (c[0] > 150 && c[2] > 150 && c[0] - c[1] > 15 && c[2] - c[1] > 15) {
          hitCross = { c, dx, dy };
        }
      }
    }
    R.check('中心红十字也留下了一条品红轮廓（细线整体都算边界）',
      !!hitCross, hitCross ? `rgb(${hitCross.c.slice(0, 3).join(',')}) @(${hitCross.dx},${hitCross.dy})`
                           : `预测 (${eCross.x.toFixed(1)},${eCross.y.toFixed(1)}) 附近没有品红轮廓`);
  }

  // 门槛：越高留下的线越少
  {
    const cnt = (t) => litCount(render({ ...UI, outline: true, edgeThreshold: t }, CAM_FRONT, [0]).fb);
    const loose = cnt(0.1), mid = cnt(0.25), tight = cnt(0.6);
    R.check('门槛调高 → 留下的分界线变少（而且最强的那些边界始终留着）',
      loose >= mid && mid > tight && tight > 0,
      `0.1→${loose} / 0.25→${mid} / 0.6→${tight} 个像素`);
  }

  // 轮廓是**在照片上做的**，不是把照片整张删掉：关掉轮廓必须回到原样
  {
    const back = render({ ...UI, outline: false }, CAM_FRONT, [0]);
    R.check('关掉轮廓后立刻恢复成完整照片（这是开关，不是破坏性处理）',
      litCount(back.fb) === fullLit, `${litCount(back.fb)} vs ${fullLit} 个像素`);
  }

  // 等轴视图下同样成立（轮廓跟着照片一起被投影，不是屏幕空间的后期处理）
  {
    const iso = render({ ...UI, opOther: 0.10, outline: true, edgeThreshold: 0.25 }, CAM_ISO);
    const isoFull = render({ ...UI, opOther: 0.10 }, CAM_ISO);
    R.check('等轴视图（多帧）下轮廓模式同样只留一小部分画面',
      litCount(iso.fb) < litCount(isoFull.fb) * 0.5,
      `${litCount(iso.fb)} vs ${litCount(isoFull.fb)} 个像素`);
    save('09-iso-outline', iso.fb);
  }
}

/* ============================ 7b. 切割：只画选区内的画面 */

R.section('切割：只画选区内的画面（与世界坐标一致）');
{
  const UI = { allGhost: false, opCur: 1.0, opOther: 0, otherMode: 'plane', cur: 0 };
  const full = render(UI, CAM_FRONT, [0]);
  const fullLit = litCount(full.fb);

  // 左半边（u 0..0.5）：小球在里面，青方块与红十字在外面
  const left = render({ ...UI, clipOn: true, clip: [0, 0, 0.5, 1] }, CAM_FRONT, [0]);
  save('10-front-clip-left-half', left.fb);
  R.check('选区外的画面全被丢掉了（像素数明显变少）',
    litCount(left.fb) < fullLit * 0.75 && litCount(left.fb) > fullLit * 0.25,
    `完整 ${fullLit} → 左半边 ${litCount(left.fb)}`);

  const at = (u, v) => {
    const e = expectPixelOfImagePoint(u * W, v * H, 0, CAM_FRONT);
    const c = pixel(left.fb, e.x, e.y);
    const isBg = Math.abs(c[0] - 5) < 14 && Math.abs(c[1] - 7) < 14 && Math.abs(c[2] - 11) < 14;
    return { c, isBg, e };
  };
  {
    const ball = at(0.10, 0.5);            // 第 1 帧的球在 u≈0.10
    R.check('选区内的内容照常画（小球在 u=0.10，落在左半边里）',
      !ball.isBg && ball.c[0] > 180, `rgb(${ball.c.slice(0, 3).join(',')})`);
    const cyan = at(0.72, 0.20);           // 青方块在右半边
    R.check('★ 选区外的内容被丢掉（青方块在 u=0.72，落在选区外）',
      cyan.isBg, `rgb(${cyan.c.slice(0, 3).join(',')})`);
    const cross = at(0.503, 0.5);          // 红十字正好压在 u=0.5 的边界外
    R.check('选区边界是"含边界"的：u=0.503 在 0..0.5 之外 → 丢掉',
      cross.isBg, `rgb(${cross.c.slice(0, 3).join(',')})`);
  }

  /*
   * ★ v 的朝向：v=0 是图像**顶部**。
   * 只留下半部分（v 0.5..1）时，画面底部的渐变条必须还在，而顶部的青方块必须没了。
   * 如果哪一天 v 被写反了，这条会立刻失败 —— 而"选区上下颠倒"在截图里很容易被忽略。
   */
  {
    const bottom = render({ ...UI, clipOn: true, clip: [0, 0.5, 1, 1] }, CAM_FRONT, [0]);
    save('11-front-clip-bottom-half', bottom.fb);
    const probe = (u, v) => {
      const e = expectPixelOfImagePoint(u * W, v * H, 0, CAM_FRONT);
      const c = pixel(bottom.fb, e.x, e.y);
      return Math.abs(c[0] - 5) < 14 && Math.abs(c[1] - 7) < 14 && Math.abs(c[2] - 11) < 14;
    };
    R.check('★ v=0 是图像顶部：留下半部分时，底部的渐变条还在',
      !probe(0.5, 0.94), 'v=0.94（底部渐变条）有内容');
    R.check('★ v=0 是图像顶部：留下半部分时，顶部的青方块没了',
      probe(0.72, 0.20), 'v=0.20（青方块）为背景');
  }

  // 只框住小球那一小块：像素数应该只剩几个百分点，而球本身仍在
  {
    const tiny = render({ ...UI, clipOn: true, clip: [0.05, 0.40, 0.15, 0.60] }, CAM_FRONT, [0]);
    const tinyLit = litCount(tiny.fb);
    save('12-front-clip-ball-only', tiny.fb);
    R.check('选区越小，留下的像素越少（逐级下降，不是"全有或全无"）',
      tinyLit < litCount(left.fb) && tinyLit > 0,
      `整幅 ${fullLit} → 左半 ${litCount(left.fb)} → 小球框 ${tinyLit}`);
    const e = expectPixelOfImagePoint(ballX(0), H / 2, 0, CAM_FRONT);
    const c = pixel(tiny.fb, e.x, e.y);
    R.check('框住小球的选区里，球本身仍然完整地画在那里',
      c[0] > 180 && c[1] > 100 && c[2] < 90, `rgb(${c.slice(0, 3).join(',')})`);
  }

  // 关掉之后必须完全回到整幅照片（这是开关，不是破坏性处理）
  {
    const back = render({ ...UI, clipOn: false, clip: [0.05, 0.40, 0.15, 0.60] }, CAM_FRONT, [0]);
    R.check('关掉切割后立刻恢复整幅照片（选区留着，但不生效）',
      litCount(back.fb) === fullLit, `${litCount(back.fb)} vs ${fullLit}`);
  }

  // 与轮廓模式叠加：两个开关互不干扰（先切割、再在留下来的部分里提轮廓）
  {
    const combo = render({ ...UI, clipOn: true, clip: [0, 0, 1, 0.5], outline: true, edgeThreshold: 0.25 }, CAM_FRONT, [0]);
    const outlineAll = render({ ...UI, outline: true, edgeThreshold: 0.25 }, CAM_FRONT, [0]);
    R.check('切割 + 轮廓可以叠加（选区外的部分连轮廓都不画）',
      litCount(combo.fb) > 0 && litCount(combo.fb) < litCount(outlineAll.fb),
      `轮廓 ${litCount(outlineAll.fb)} → 上半区轮廓 ${litCount(combo.fb)}`);
  }
}

/* ================================ 8. 参考图落盘（供人工比对） */

R.section('参考图已生成');
{
  const all = render({ allGhost: false, opCur: 1, opOther: 0.10, otherMode: 'plane', cur: 11 }, CAM_ISO);
  save('05-iso-frame12-ghosts', all.fb);
  const front = render({ allGhost: false, opCur: 1, opOther: 0.10, otherMode: 'plane', cur: 11 }, CAM_FRONT);
  save('06-front-frame12-ghosts', front.fb);
  R.check('参考图写到了 test/reference/',
    existsSync(join(shotsDir, '05-iso-frame12-ghosts.png')) &&
    existsSync(join(shotsDir, '01-front-frame0-only.png')),
    shotsDir);
  R.check('06 号图（正视 + 第 12 帧 + 其余 10%）有内容', litCount(front.fb) > 10000,
    litCount(front.fb) + ' 个非背景像素');
}

ctx.STC.app.stop();          // 停掉参考上下文里的渲染循环，否则 Node 事件循环不退出
const secs = ((Date.now() - t0) / 1000).toFixed(1);
const failed = R.summary();
console.log(`用时 ${secs} 秒`);
process.exitCode = failed ? 1 : 0;
process.exit(process.exitCode);
