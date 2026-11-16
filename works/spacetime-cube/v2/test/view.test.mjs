/* 纯逻辑自检：数学、相机、逐帧解算、深度排序、点云网格、边界像素打包、EXIF
 *
 * 这些都不需要浏览器，但它们恰好是「画面对不对」的根：
 * 相机矩阵错了 → 立方体不在画面里；深度排序错了 → 前后帧互相遮挡；
 * 边界像素下标错了 → 侧面颜色来自错误的像素（画面上很难一眼看出来）。
 *
 * 用法：node test/view.test.mjs
 */
import { createDom, loadApp, createReporter } from '../tools/harness.mjs';
import { fakeImageFile } from '../tools/make-sample.mjs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const R = createReporter('纯逻辑自检', join(here, 'view.log'));
const dom = createDom({ width: 1200, height: 800 });
const { STC } = loadApp(dom);

const { math: M, view: V, seq: SQ } = STC;
const VPS = { w: 1200, h: 800 };
// 320×240 的照片：宽固定为 1，高 0.75；深度按 1.6 倍长边
const GEO = { planeW: 1, planeH: 0.75, depth: 1.6 };
const CAM_FRONT = { az: 0, el: 0, zoom: 1, panU: 0, panV: 0, fov: M.deg(40) };
const CAM_ISO = { az: 32, el: 20, zoom: 1, panU: 0, panV: 0, fov: M.deg(40) };

/* ============================================================ 1. 矩阵 */

R.section('矩阵与投影');
{
  const I = M.m4();
  const v = M.xformPoint(I, 0.3, -0.2, 0.5);
  R.near('单位矩阵是恒等变换 x', v[0], 0.3);
  R.near('单位矩阵是恒等变换 y', v[1], -0.2);
  R.near('单位矩阵是恒等变换 z', v[2], 0.5);

  // 平移矩阵：把 (1,2,3) 加上 (10,20,30)
  const T = M.m4();
  T[12] = 10; T[13] = 20; T[14] = 30;
  const t = M.xformPoint(T, 1, 2, 3);
  R.check('平移矩阵按预期平移', t[0] === 11 && t[1] === 22 && t[2] === 33,
    `${t[0]},${t[1]},${t[2]}`);

  // 乘法结合顺序：mul(A,B) 表示"先 B 后 A"
  const S = M.m4();
  S[0] = 2; S[5] = 3; S[10] = 4;
  const ST = M.mul(T, S);            // 先缩放再平移
  const st = M.xformPoint(ST, 1, 1, 1);
  R.check('mul(A,B) 的语义是"先 B 后 A"', st[0] === 12 && st[1] === 23 && st[2] === 34,
    `${st[0]},${st[1]},${st[2]}（期望 12,23,34）`);

  // 透视投影：近裁剪面上的点映射到 z = -1，远裁剪面到 z = +1
  const P = M.perspective(M.deg(60), 1, 1, 100);
  const nearPt = M.xformPoint(P, 0, 0, -1);
  const farPt = M.xformPoint(P, 0, 0, -100);
  const zNear = nearPt[2] / nearPt[3];
  const zFar = farPt[2] / farPt[3];
  R.near('透视投影：近裁剪面 → NDC z = -1', zNear, -1, 1e-5);
  R.near('透视投影：远裁剪面 → NDC z = +1', zFar, 1, 1e-5);
  R.check('透视矩阵把相机前方的点放在 w>0 一侧', nearPt[3] > 0, 'w=' + nearPt[3]);

  // lookAt：相机在 +Z、看向原点时，原点的 NDC x/y 都应为 0
  const eye = [0, 0, 3];
  const LV = M.lookAt(eye, [0, 0, 0], [0, 1, 0]);
  const o = M.xformPoint(LV, 0, 0, 0);
  R.near('lookAt 后原点落在视线中心 x', o[0], 0, 1e-9);
  R.near('lookAt 后原点落在视线中心 y', o[1], 0, 1e-9);
  R.near('lookAt 后原点位于相机前方 3 个单位', o[2], -3, 1e-9);
  // 相机右侧的点必须投到 +x（这是"左右没有镜像"的判据）
  const rightPt = M.xformPoint(LV, 0.5, 0, 0);
  R.check('相机右侧的点投到 +x（纹理左右无镜像）', rightPt[0] > 0, 'x=' + rightPt[0]);
  // 相机上方的点必须投到 +y（纹理上下无翻转的判据之一）
  const upPt = M.xformPoint(LV, 0, 0.5, 0);
  R.check('相机上方的点投到 +y', upPt[1] > 0, 'y=' + upPt[1]);
}

/* ============================================================ 2. 相机 */

R.section('相机（正视 = 第一帧正对屏幕）');
{
  const cp = V.camParams(GEO, CAM_FRONT, VPS);
  R.check('正视时相机在 +Z 轴上', Math.abs(cp.eye[0]) < 1e-9 && Math.abs(cp.eye[1]) < 1e-9 && cp.eye[2] > 0,
    `eye=(${cp.eye.map((n) => n.toFixed(3)).join(',')})`);
  R.check('正视时视线朝 -Z', cp.dir[2] < -0.999, 'dir.z=' + cp.dir[2].toFixed(6));

  // 关键断言：世界原点必须落在画布中心
  const c = V.projectToPixel(cp, VPS, 0, 0, 0);
  R.near('世界原点投影到画布水平中心', c[0], VPS.w / 2, 1e-6);
  R.near('世界原点投影到画布垂直中心', c[1], VPS.h / 2, 1e-6);

  // 第一帧平面在 z=0，是立方体的前表面；最后一帧在 z=depth，更远
  const d0 = V.frameDepth(cp, 0);
  const dN = V.frameDepth(cp, GEO.depth);
  R.check('第一帧比最后一帧更靠近相机（正面=第一帧）', d0 < dN,
    `depth(0)=${d0.toFixed(3)} < depth(depth)=${dN.toFixed(3)}`);

  // 照片右侧的点必须出现在画面右半边（左右不镜像）
  const pr = V.projectToPixel(cp, VPS, 0.4, 0, 0);
  R.check('照片右侧的点出现在画面右半边', pr[0] > VPS.w / 2, 'px=' + pr[0].toFixed(1));
  // 照片上方的点（世界 +y）必须出现在画面上半边（上下不翻转）
  const pu = V.projectToPixel(cp, VPS, 0, 0.3, 0);
  R.check('照片上方的点出现在画面上半边', pu[1] < VPS.h / 2, 'py=' + pu[1].toFixed(1));

  // 立方体必须完整落在画面内（这是"不裁切"的判据）
  let maxAbsX = 0, maxAbsY = 0;
  for (const x of [-0.5, 0.5]) {
    for (const y of [-0.375, 0.375]) {
      for (const z of [0, GEO.depth]) {
        const p = V.projectToPixel(cp, VPS, x, y, z);
        maxAbsX = Math.max(maxAbsX, Math.abs(p[0] - VPS.w / 2));
        maxAbsY = Math.max(maxAbsY, Math.abs(p[1] - VPS.h / 2));
      }
    }
  }
  R.check('正视时立方体完整落在画面内（不裁切）',
    maxAbsX < VPS.w / 2 && maxAbsY < VPS.h / 2,
    `最大偏移 ${maxAbsX.toFixed(0)}×${maxAbsY.toFixed(0)} 像素，半画布 ${VPS.w / 2}×${VPS.h / 2}`);

  // 等轴视图：要有真实的 3D 感（视线不再平行于 z 轴），且仍完整入画
  const ci = V.camParams(GEO, CAM_ISO, VPS);
  R.check('等轴视图的视线不是正对 z 轴（能看到侧面）',
    Math.abs(ci.dir[2]) < 0.98 && Math.abs(ci.dir[0]) > 0.1,
    `dir=(${ci.dir.map((n) => n.toFixed(3)).join(',')})`);
  let iMaxX = 0, iMaxY = 0;
  for (const x of [-0.5, 0.5]) {
    for (const y of [-0.375, 0.375]) {
      for (const z of [0, GEO.depth]) {
        const p = V.projectToPixel(ci, VPS, x, y, z);
        iMaxX = Math.max(iMaxX, Math.abs(p[0] - VPS.w / 2));
        iMaxY = Math.max(iMaxY, Math.abs(p[1] - VPS.h / 2));
      }
    }
  }
  R.check('等轴视图下立方体仍完整入画',
    iMaxX < VPS.w / 2 && iMaxY < VPS.h / 2,
    `最大偏移 ${iMaxX.toFixed(0)}×${iMaxY.toFixed(0)}`);

  // 极端窗口比例也不能裁切
  for (const [w, h] of [[1600, 500], [500, 1200], [900, 900], [2100, 380]]) {
    const vp = { w, h };
    const cpx = V.camParams(GEO, CAM_ISO, vp);
    let mx = 0, my = 0;
    for (const x of [-0.5, 0.5]) for (const y of [-0.375, 0.375]) for (const z of [0, GEO.depth]) {
      const p = V.projectToPixel(cpx, vp, x, y, z);
      mx = Math.max(mx, Math.abs(p[0] - w / 2));
      my = Math.max(my, Math.abs(p[1] - h / 2));
    }
    R.check(`窗口 ${w}×${h} 下立方体完整入画`, mx < w / 2 && my < h / 2,
      `偏移 ${mx.toFixed(0)}×${my.toFixed(0)} / 半画布 ${w / 2}×${h / 2}`);
  }

  // far 平面必须真的把所有东西装进去
  const farEdge = V.frameDepth(ci, GEO.depth) + ci.radius * 2;
  R.check('远裁剪面足够远（不会把立方体切掉）', ci.far > farEdge,
    `far=${ci.far.toFixed(2)} vs 需要 >${farEdge.toFixed(2)}`);

  // 正交投影：near/far 是到相机的绝对距离，必须都是正的、且把立方体夹在中间
  R.check('用的是正交投影（没有透视缩放）', ci.ortho === true && ci.proj[15] === 1,
    'ortho=' + ci.ortho + ' proj[15]=' + ci.proj[15]);
  R.check('正交 near 为正、far 大于 near',
    ci.near > 0 && ci.far > ci.near, `near=${ci.near.toFixed(2)} far=${ci.far.toFixed(2)}`);
  {
    // 立方体沿视线的范围必须落在 [near, far] 内
    let minAxial = Infinity, maxAxial = -Infinity;
    for (const x of [-0.5, 0.5]) {
      for (const y of [-GEO.planeH / 2, GEO.planeH / 2]) {
        for (const z of [0, GEO.depth]) {
          const rel = [
            x - ci.target[0], y - ci.target[1], z - ci.target[2]
          ];
          const axial = ci.dist + (rel[0] * ci.dir[0] + rel[1] * ci.dir[1] + rel[2] * ci.dir[2]);
          minAxial = Math.min(minAxial, axial);
          maxAxial = Math.max(maxAxial, axial);
        }
      }
    }
    R.check('立方体完整落在正交裁剪范围内（near < 最近点、far > 最远点）',
      ci.near < minAxial && ci.far > maxAxial,
      `near=${ci.near.toFixed(2)} < ${minAxial.toFixed(2)}；far=${ci.far.toFixed(2)} > ${maxAxial.toFixed(2)}`);
  }
  R.check('正交下同一世界点在前后两帧上投影尺寸完全相同（无近大远小）',
    Math.abs(
      (V.projectToPixel(ci, VPS, 0.5, 0, 0)[0] - V.projectToPixel(ci, VPS, -0.5, 0, 0)[0]) -
      (V.projectToPixel(ci, VPS, 0.5, 0, GEO.depth)[0] - V.projectToPixel(ci, VPS, -0.5, 0, GEO.depth)[0])
    ) < 1e-9,
    '照片宽度在两个不同 z 上投影出的像素宽度必须一致');
}

/* =================== 2b. 尺度不随视角变化（用户明确要求） */

R.section('正交尺度恒定：转动视角时立方体大小不变');
{
  /*
   * 用户反馈"大小随视角变化，很难受"。原因是当时按**旋转后的包围盒**拟合视锥：
   * 立方体转到对角线时投影范围最大、正对时最小，两者相差 √3 ≈ 1.73 倍。
   * 现在改成按**包围球**定死尺度，所以这两条必须成立。
   */
  const angles = [];
  for (let az = 0; az < 360; az += 15) angles.push({ az, el: 0 });
  for (let el = -80; el <= 80; el += 20) angles.push({ az: 30, el });

  const halfHs = angles.map((a) =>
    V.camParams(GEO, { az: a.az, el: a.el, zoom: 1, panU: 0, panV: 0 }, VPS).halfH);
  const minH = Math.min(...halfHs), maxH = Math.max(...halfHs);
  R.check('所有视角下正交视野半高完全相同（尺度不随视角变）',
    Math.abs(maxH - minH) < 1e-12,
    `半高范围 ${minH.toFixed(9)} ~ ${maxH.toFixed(9)}（${angles.length} 个视角）`);

  /*
   * 「大小不变」的准确判据，是**投影核在不同方向上的尺度一致**。
   *
   * 不能拿一段固定方向的世界线段去比长度：正交投影下，沿视线方向的分量本来就会
   * 塌缩（az→90° 时沿 x 的线段正好与视线平行，投影长度为 0）。那是正确的立体感，
   * 不是"大小变了"。**忽大忽小的根源是取景范围随视角变化**（原来按旋转后的包围盒拟合，
   * 对角线时视野要放大 √3 倍），所以这里直接验证取景范围本身。
   */
  const pxPerUnit = (cp, axis) => {
    // 沿某个世界轴走一个单位，投影到屏幕上的长度（取绝对值）
    const o = V.projectToPixel(cp, VPS, 0, 0, 0);
    const p = axis === 'x' ? V.projectToPixel(cp, VPS, 1, 0, 0)
      : axis === 'y' ? V.projectToPixel(cp, VPS, 0, 1, 0)
        : V.projectToPixel(cp, VPS, 0, 0, 1);
    return { r: Math.hypot(p[0] - o[0], p[1] - o[1]), dx: p[0] - o[0], dy: p[1] - o[1] };
  };

  // 1) 纯方位角旋转（el 固定）下，竖直尺度必须完全不变
  const verticals = angles.filter((a) => a.el === 0).map((a) =>
    pxPerUnit(V.camParams(GEO, { az: a.az, el: a.el, zoom: 1, panU: 0, panV: 0 }, VPS), 'y'));
  const vMin = Math.min(...verticals.map((v) => Math.abs(v.dy)));
  const vMax = Math.max(...verticals.map((v) => Math.abs(v.dy)));
  R.check('绕方位角旋转时竖直尺度完全不变（不会忽大忽小）',
    Math.abs(vMax - vMin) < 1e-9,
    `竖直像素/单位 ∈ [${vMin.toFixed(6)}, ${vMax.toFixed(6)}]（${verticals.length} 个方位角）`);

  // 2) 竖直尺度不许随方位角出现任何跳变 —— 逐角度换算回世界单位都等于常数
  const worldPerPx = verticals.map((v) => 1 / Math.abs(v.dy));
  R.check('换算成「世界单位/像素」在各方位角下是同一个常数',
    Math.abs(Math.max(...worldPerPx) - Math.min(...worldPerPx)) < 1e-12,
    `世界单位/像素 = ${worldPerPx[0].toFixed(9)}（全部相同）`);

  // 3) 视野半高在**全部**视角（含仰角）下都相同 —— 取景范围完全不随视角变
  const allViewAngles = [];
  for (let az = 0; az < 360; az += 15) for (const el of [-80, -40, 0, 40, 80]) allViewAngles.push({ az, el });
  allViewAngles.push({ az: 137, el: 42 });
  const allHalf = allViewAngles.map((a) =>
    V.camParams(GEO, { az: a.az, el: a.el, zoom: 1, panU: 0, panV: 0 }, VPS).halfH);
  R.check('全部 97 个视角下视野半高都是同一个常数',
    Math.abs(Math.max(...allHalf) - Math.min(...allHalf)) < 1e-12,
    `半高 = ${allHalf[0].toFixed(9)}（${allViewAngles.length} 个视角全部相同）`);

  // 4) 同一视角在不同窗口比例下，竖直尺度也不能变（否则拉窗口就会缩放）
  for (const [w, h] of [[1600, 500], [500, 1200], [900, 900]]) {
    const cpW = V.camParams(GEO, { az: 32, el: 20, zoom: 1, panU: 0, panV: 0 }, { w, h });
    const dy = Math.abs(pxPerUnit(cpW, 'y').dy);
    const ref = Math.abs(pxPerUnit(
      V.camParams(GEO, { az: 32, el: 20, zoom: 1, panU: 0, panV: 0 }, { w: 1200, h: 800 }), 'y').dy);
    R.check(`窗口 ${w}×${h} 下竖直尺度与 1200×800 一致（只与 zoom 有关）`,
      Math.abs(dy - ref) < 1e-9,
      `${dy.toFixed(6)} vs ${ref.toFixed(6)}`);
  }

  // 每个视角下立方体都必须完整入画
  let worstX = 0, worstY = 0;
  for (const a of angles) {
    const cp = V.camParams(GEO, { az: a.az, el: a.el, zoom: 1, panU: 0, panV: 0 }, VPS);
    for (const x of [-0.5, 0.5]) {
      for (const y of [-0.375, 0.375]) {
        for (const z of [0, GEO.depth]) {
          const p = V.projectToPixel(cp, VPS, x, y, z);
          worstX = Math.max(worstX, Math.abs(p[0] - VPS.w / 2));
          worstY = Math.max(worstY, Math.abs(p[1] - VPS.h / 2));
        }
      }
    }
  }
  R.check('全部视角下立方体都完整入画（尺度固定后仍不裁切）',
    worstX < VPS.w / 2 && worstY < VPS.h / 2,
    `最坏偏移 ${worstX.toFixed(0)}×${worstY.toFixed(0)}，半画布 ${VPS.w / 2}×${VPS.h / 2}`);

  // 缩放只由 zoom 决定，与视角无关
  const zoomed = V.camParams(GEO, { az: 137, el: 42, zoom: 2, panU: 0, panV: 0 }, VPS);
  const base = V.camParams(GEO, { az: 0, el: 0, zoom: 1, panU: 0, panV: 0 }, VPS);
  R.check('zoom=2 时视野半高正好是 zoom=1 的一半（缩放只由 zoom 控制）',
    Math.abs(zoomed.halfH - base.halfH / 2) < 1e-12,
    `${zoomed.halfH.toFixed(6)} vs ${(base.halfH / 2).toFixed(6)}`);
}

/* ====================================================== 3. 逐帧解算 */

R.section('逐帧解算（滑块 / 不透明度 / 点云）');
{
  const mk = (n) => ({
    geo: { planeW: 1, planeH: 0.75, depth: 1.6 },
    frames: Array.from({ length: n }, (_, i) => ({ index: i, pointVao: null }))
  });

  const seq = mk(25);
  const ui = { allGhost: false, opCur: 1.0, opOther: 0.12, otherMode: 'plane' };
  const r = V.resolve(seq, ui, 12);

  R.check('解算出的条目数等于帧数', r.items.length === 25, 'items=' + r.items.length);
  R.check('只有当前帧被标为 current', r.items.filter((it) => it.current).length === 1 &&
    r.items[12].current === true, 'currentIndex=' + r.stats.currentIndex);
  R.near('当前帧用 opCur', r.items[12].opacity, 1.0);
  R.near('其余帧用 opOther', r.items[11].opacity, 0.12);
  R.check('当前帧是唯一不透明项，其余为半透明',
    r.stats.opaque === 1 && r.stats.ghost === 24, `opaque=${r.stats.opaque} ghost=${r.stats.ghost}`);

  // 时间轴位置：第 i 帧在 z = i * depth/(n-1)；第一帧在 0（前表面）
  R.near('第一帧位于 z=0（立方体前表面）', r.items[0].z, 0);
  R.near('最后一帧位于 z=depth（立方体后表面）', r.items[24].z, 1.6, 1e-6);
  R.near('帧间距 = depth/(n-1)', r.items[1].z - r.items[0].z, 1.6 / 24, 1e-9);
  R.check('z 随帧号单调递增', r.items.every((it, i) => i === 0 || it.z > r.items[i - 1].z));

  // 「全部半透明」必须取消当前帧的特殊地位
  const g = V.resolve(seq, Object.assign({}, ui, { allGhost: true, opOther: 0.3 }), 12);
  R.check('全部半透明时没有任何帧被标为 current', g.items.every((it) => !it.current));
  R.check('全部半透明时所有帧同一个不透明度',
    g.items.every((it) => Math.abs(it.opacity - 0.3) < 1e-9), 'opacity 全为 0.3');
  R.check('全部半透明时 stats 里没有不透明项', g.stats.opaque === 0, 'opaque=' + g.stats.opaque);

  // 不透明度为 0 → 内容全部透明（但仍占位，线框照画）
  const z0 = V.resolve(seq, Object.assign({}, ui, { allGhost: true, opOther: 0 }), 12);
  R.check('不透明度 0 时所有帧都不画内容', z0.items.every((it) => it.opacity === 0 && !it.pointCloud));
  R.check('不透明度 0 时隐藏计数正确', z0.stats.hidden === 25, 'hidden=' + z0.stats.hidden);

  // 点云模式：当前帧仍以平面显示，其余帧走点云
  const seqP = mk(25);
  for (const f of seqP.frames) f.pointVao = { vao: { kind: 'vao' }, count: 100 };
  const p = V.resolve(seqP, Object.assign({}, ui, { otherMode: 'points' }), 3);
  R.check('点云模式下当前帧仍然是平面', p.items[3].pointCloud === false && p.items[3].current === true);
  R.check('点云模式下其余帧都走点云', p.items.filter((it) => it.pointCloud).length === 24,
    '点云帧数=' + p.items.filter((it) => it.pointCloud).length);
  R.check('点云帧带上了实例数与 VAO', p.items[0].vao !== null && p.items[0].count === 100);

  // 缓冲还没建好时不能闪空帧：该帧不透明度必须为 0
  const seqNoBuf = mk(25);
  const np = V.resolve(seqNoBuf, Object.assign({}, ui, { otherMode: 'points' }), 3);
  R.check('点云缓冲未就绪的帧不会被画（不透明度归 0）',
    np.items.every((it) => it.pointCloud === false || it.opacity === 0));
}

/* ====================================================== 4. 深度排序 */

R.section('深度排序（半透明必须由远到近画）');
{
  const cp = V.camParams(GEO, CAM_FRONT, VPS);
  const items = [];
  for (let i = 0; i < 7; i++) items.push({ i, z: i * (1.6 / 6) });
  V.sortFarToNear(items, cp);
  R.check('正视时由远到近 = 帧号从大到小（最后一帧先画）',
    items.map((it) => it.i).join(',') === '6,5,4,3,2,1,0',
    items.map((it) => it.i).join(','));
  R.check('每个条目都带上了 depth',
    items.every((it) => typeof it.depth === 'number'));

  // 从背面看：顺序必须正好反过来
  const cpBack = V.camParams(GEO, { az: 180, el: 0, zoom: 1, panU: 0, panV: 0, fov: M.deg(40) }, VPS);
  const items2 = [];
  for (let i = 0; i < 7; i++) items2.push({ i, z: i * (1.6 / 6) });
  V.sortFarToNear(items2, cpBack);
  R.check('从背面看时顺序反过来（由近到远变成帧号从小到大）',
    items2.map((it) => it.i).join(',') === '0,1,2,3,4,5,6',
    items2.map((it) => it.i).join(','));

  // 排序必须稳定可复现（同一次运行两次结果一致）
  const a = []; const b = [];
  for (let i = 0; i < 20; i++) { a.push({ i, z: (i * 7 % 13) / 13 * 1.6 }); b.push({ i, z: (i * 7 % 13) / 13 * 1.6 }); }
  V.sortFarToNear(a, cp); V.sortFarToNear(b, cp);
  R.check('排序结果可复现', a.map((x) => x.i).join(',') === b.map((x) => x.i).join(','));
}

/* ======================================================== 5. 点云网格 */

R.section('点云网格与预算');
{
  const g1 = V.pointGrid(320, 240, 1);
  R.check('步长 1：点数等于原始像素数', g1.count === 320 * 240, `${g1.cols}×${g1.rows}=${g1.count}`);
  R.check('步长 1：列数等于宽度、行数等于高度', g1.cols === 320 && g1.rows === 240);

  const g2 = V.pointGrid(320, 240, 2);
  R.check('步长 2：列数 = floor((w-1)/2)+1', g2.cols === Math.floor(319 / 2) + 1, 'cols=' + g2.cols);
  R.check('步长 2：行数 = floor((h-1)/2)+1', g2.rows === Math.floor(239 / 2) + 1, 'rows=' + g2.rows);
  R.check('步长 2：点数约为四分之一', Math.abs(g2.count - 320 * 240 / 4) < 200, 'count=' + g2.count);

  const g5 = V.pointGrid(321, 241, 5);
  R.check('步长 5：点数落在预算量级', g5.count === g5.cols * g5.rows);
  R.check('步长被夹到至少 1', V.pointGrid(320, 240, 0).count === 320 * 240, 'stride 0 → 视为 1');
  R.check('步长 1 时每个点都在像素中心（网格不越界）',
    V.pointGrid(320, 240, 1).cols === 320);

  R.check('小序列：预算充足 → 步长 1', V.pointStride(320 * 240 * 24, 4e6, 24) === 1);
  const stride = V.pointStride(4000 * 3000 * 200, 4e6, 200);
  const grid = V.pointGrid(4000, 3000, stride);
  R.check('大序列：步长被加大到预算之内', grid.count * 200 <= 4e6 * 1.05,
    `stride=${stride} 总点数≈${(grid.count * 200 / 1e6).toFixed(2)}M`);
  R.check('步长不会退化成 0 或负数', stride >= 1, 'stride=' + stride);
}

/* ================================================ 6. 边界像素图集打包 */

R.section('侧面颜色条：边界像素打包');
{
  // 造一张 4×3 的图，每个像素用一个可辨认的值
  const w = 4, h = 3;
  const px = new Uint8Array(w * h * 4);
  const at = (x, y) => (y * w + x) * 4;
  // 设计：R 通道存 x，G 通道存 y，方便核对取到的是哪个像素
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const o = at(x, y);
      px[o] = 10 + x;       // R = 10 + x
      px[o + 1] = 20 + y;   // G = 20 + y
      px[o + 2] = 30;       // B
      px[o + 3] = 40;       // A
    }
  }

  /*
   * 每条边现在是**独立的一张纹理行**，而且每个像素是**完整的 RGB**。
   *
   * 这一节是从旧版重写过来的。旧版验证的是"四条边压进 RGBA 四个通道、
   * 每个通道只存一个 R 分量" —— 那条设计本身就是错的：
   * 侧面只能是灰度，而且纹理只上传了 1 行，其余帧的数据全被丢掉。
   * 断言写得太贴近实现，于是把一个错误的设计"验证"成了正确的。
   */
  const dstW = 6;                          // 故意大于源长度，验证最近邻重采样
  function row(which, width) {
    const out = new Uint8Array((width || dstW) * 4);
    V.packEdge(px, w, h, which, out, 0, width || dstW);
    return out;
  }
  // 目标列 j → 源下标，这就是"最近邻重采样"的定义
  const srcAt = (j, srcLen, width) => Math.min(srcLen - 1, Math.floor(j * srcLen / width));

  const left = row('left');
  R.check('左边缘：取每行第 0 列的**完整颜色**（不是单个通道）',
    left[0] === 10 && left[1] === 20 && left[2] === 30 && left[3] === 255,
    `第 0 个像素 = [${left[0]},${left[1]},${left[2]},${left[3]}]（期望 [10,20,30,255]）`);

  // 源高 3、目标 6 → 每个源行覆盖两列：[0,0,1,1,2,2]
  const leftG = [];
  const rightR = [];
  for (let j = 0; j < dstW; j++) {
    leftG.push(left[j * 4 + 1]);
    rightR.push(row('right')[j * 4]);
  }
  R.check('左边缘：逐列核对取样到的是哪一行（G = 20 + 行号）',
    leftG.join(',') === '20,20,21,21,22,22',
    `G 序列 = ${leftG.join(',')}（期望 20,20,21,21,22,22）`);
  R.check('左边缘的 R 恒为 10（一直取的是第 0 列）',
    left[0] === 10 && left[8] === 10 && left[20] === 10, 'R=10');

  const right = row('right');
  R.check('右边缘：每一列都取最后一列（R=13），G 随行号递增',
    rightR.join(',') === '13,13,13,13,13,13' && right[1] === 20 && right[9] === 21,
    `R 序列 = ${rightR.join(',')}，G[0]=${right[1]} G[2]=${right[9]}`);

  // 源宽 4、目标 6 → 列覆盖 [0,0,1,2,2,3]
  const top = row('top');
  const topR = [], topG = [], bottomR = [], bottomG = [];
  const bottom = row('bottom');
  for (let j = 0; j < dstW; j++) {
    topR.push(top[j * 4]); topG.push(top[j * 4 + 1]);
    bottomR.push(bottom[j * 4]); bottomG.push(bottom[j * 4 + 1]);
  }
  R.check('上边缘：逐列核对取样到的是哪一列（R = 10 + 列号）',
    topR.join(',') === '10,10,11,12,12,13',
    `R 序列 = ${topR.join(',')}（期望 10,10,11,12,12,13）`);
  R.check('上边缘的 G 恒为 20（一直取的是第 0 行）',
    topG.every((g) => g === 20), 'G 序列 = ' + topG.join(','));
  R.check('下边缘：逐列取样最后一行（R 同列号、G 恒为 22）',
    bottomR.join(',') === '10,10,11,12,12,13' && bottomG.every((g) => g === 22),
    `R = ${bottomR.join(',')}，G = ${bottomG.join(',')}`);

  // 尺寸一致时是一一对应，绝不插值
  const exact = new Uint8Array(4 * 4);
  V.packEdge(px, w, h, 'top', exact, 0, 4);
  R.check('目标宽度等于源长度时是一一对应（不做任何插值）',
    exact[0] === 10 && exact[4] === 11 && exact[8] === 12 && exact[12] === 13,
    `${exact[0]},${exact[4]},${exact[8]},${exact[12]}`);
  R.check('重采样用的就是 floor(j × 源长 ÷ 目标宽) 这套下标',
    srcAt(0, 4, 6) === 0 && srcAt(2, 4, 6) === 1 && srcAt(3, 4, 6) === 2 && srcAt(5, 4, 6) === 3,
    'srcAt = ' + [0, 1, 2, 3, 4, 5].map((j) => srcAt(j, 4, 6)).join(','));

  R.check('每条边写进去的像素数等于图集宽度', V.packEdge(px, w, h, 'left', left, 0, dstW) === dstW,
    '返回 ' + V.packEdge(px, w, h, 'left', left, 0, dstW));
  R.check('边的采样点数：左右 = 高，上下 = 宽',
    V.edgeLength('left', w, h) === h && V.edgeLength('top', w, h) === w,
    `left=${V.edgeLength('left', w, h)} top=${V.edgeLength('top', w, h)}`);

  // edgeColors 是参考渲染用的「四条边真实颜色」版本
  const ec = V.edgeColors(px, w, h);
  R.check('edgeColors：四条边都是完整 RGB',
    ec.left.length === h && ec.top.length === w &&
    ec.left[0][0] === 10 && ec.left[0][1] === 20 && ec.left[0][2] === 30,
    `left ${ec.left.length} 个、top ${ec.top.length} 个`);

  /*
   * 侧面的几何表：**这一层是渲染器与参考渲染共用的唯一真相**。
   * span（沿边半长）与 off（固定轴偏移）必须分得很清楚 ——
   * 早先两者共用一个 uLong，左右墙就比照片高出 (halfW-halfH)。
   */
  const geo = { planeW: 1, planeH: 0.75, depth: 1.6 };
  const sides = V.bandSides(geo);
  const byName = {};
  sides.forEach((s) => { byName[s.side] = s; });
  R.check('左右墙：沿 y 展开、半长 = halfH、偏移 = ±halfW',
    byName.left.axisY === 1 && byName.left.span === 0.375 && byName.left.off === -0.5 &&
    byName.right.axisY === 1 && byName.right.off === 0.5,
    `left span=${byName.left.span} off=${byName.left.off}`);
  R.check('上下墙：沿 x 展开、半长 = halfW、偏移 = ±halfH',
    byName.top.axisY === 0 && byName.top.span === 0.5 && byName.top.off === 0.375 &&
    byName.bottom.axisY === 0 && byName.bottom.off === -0.375,
    `top span=${byName.top.span} off=${byName.top.off}`);
  R.check('四条边的固定轴偏移量就是「照片的边长」（几何与照片严格对齐）',
    Math.abs(byName.left.off) === geo.planeW / 2 &&
    Math.abs(byName.top.off) === geo.planeH / 2,
    '左右墙贴在 x=±halfW，上下墙贴在 y=±halfH');

  // 沿边的纹理坐标：左右墙要上下翻转（世界 +y 是图像顶部）
  R.check('左右墙：图像第 0 行落在 +y 那一端（edgeCoord = 1-t）',
    V.edgeCoord(1, -1) === 1 && V.edgeCoord(1, 1) === 0, 'along=-1 → 1，along=1 → 0');
  R.check('上下墙：图像第 0 列落在 -x 那一端（edgeCoord = t）',
    V.edgeCoord(0, -1) === 0 && V.edgeCoord(0, 1) === 1, 'along=-1 → 0，along=1 → 1');

  // 帧行坐标：必须落在纹素中心，且第 0 帧和第 n-1 帧都不跑到边缘外
  R.check('帧行坐标落在纹素中心（第 0 帧 / 最后一帧）',
    Math.abs(V.frameRow(0, 25) - 0.02) < 1e-9 && Math.abs(V.frameRow(24, 25) - 0.98) < 1e-9,
    `${V.frameRow(0, 25)} … ${V.frameRow(24, 25)}`);
  R.check('只有一帧时行坐标取 0.5', V.frameRow(0, 1) === 0.5);
  R.check('帧行坐标被夹在 [0, n-1]（越界不会采样到别的帧）',
    V.frameRow(-5, 25) === V.frameRow(0, 25) && V.frameRow(99, 25) === V.frameRow(24, 25));

  // 平均色模式
  const avg = V.averageEdges(px, w, h, 1);
  R.check('平均色：左边缘 = 各行第 0 列的均值', avg.left[0] === 10,
    'left.R=' + avg.left[0] + '（期望 10）');
  R.check('平均色：右边缘 = 各行最后一列的均值', avg.right[0] === 13,
    'right.R=' + avg.right[0] + '（期望 13）');
  R.check('平均色:上边缘 = 第 0 行的均值', avg.top[0] === Math.round((10 + 11 + 12 + 13) / 4),
    'top.R=' + avg.top[0]);
  R.check('平均色：取样间隔生效（step=4 只取一个点）',
    V.averageEdges(px, w, h, 4).top[0] === 10, 'top.R=' + V.averageEdges(px, w, h, 4).top[0]);

  // 时间轴映射：z=0 → 第一帧，z=depth → 最后一帧
  R.near('z=0 对应第 0 帧', V.zToFrame(0, 1.6, 25), 0);
  R.near('z=depth 对应最后一帧', V.zToFrame(1.6, 1.6, 25), 24);
  R.near('z=中点对应中间帧', V.zToFrame(0.8, 1.6, 25), 12, 1e-6);
  R.near('只有一帧时恒为 0', V.zToFrame(0.8, 1.6, 1), 0);
}

/* ================================================== 7b. 轮廓提取（纯函数） */

R.section('轮廓提取：只保留对比鲜明的颜色分界线');
{
  /*
   * 造一张 8×8 的图，故意放三种边界：
   *   红(255,0,0) | 绿(0,130,0)  —— **等亮度**的强对比（Rec.601 亮度都 ≈0.299）
   *   红 | 深蓝(10,10,90)        —— 强对比
   *   红(255,0,0) | 红(200,0,0)  —— 弱对比（只差 55/255 ≈ 0.216），用来验证门槛
   */
  const w = 8, h = 8;
  const px = new Uint8Array(w * h * 4);
  const set = (x, y, r, g, b) => {
    const o = (y * w + x) * 4;
    px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = 255;
  };
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (y >= 6) set(x, y, 10, 10, 90);              // 最下面两行：深蓝
      else if (x === 0) set(x, y, 200, 0, 0);         // 最左一列：暗一点的红（弱边界）
      else if (x < 4) set(x, y, 255, 0, 0);           // 左半：红
      else set(x, y, 0, 130, 0);                      // 右半：绿（与红等亮度）
    }
  }

  R.check('平色区域内部没有分界线（对比度为 0）',
    V.outlineContrast(px, w, h, 2, 1) === 0 && V.outlineContrast(px, w, h, 6, 3) === 0,
    '红区内部与绿区内部都是 0');

  const cVert = V.outlineContrast(px, w, h, 3, 2);      // 红|绿 竖直边界
  const cHorz = V.outlineContrast(px, w, h, 2, 5);      // 红|深蓝 水平边界
  const cWeak = V.outlineContrast(px, w, h, 0, 2);      // 暗红|红（弱）
  R.check('★ 红↔绿的竖直边界被提出来（亮度几乎相同，靠逐通道差才抓得到）',
    cVert > 0.9, '对比度 = ' + cVert.toFixed(3));
  const lumOf = (c) => (c[0] * 0.299 + c[1] * 0.587 + c[2] * 0.114) / 255;
  const lumR = lumOf([255, 0, 0]), lumG = lumOf([0, 130, 0]);
  R.check('这两个颜色的**亮度**几乎一样（所以"亮度差"这种判据会整片漏掉它）',
    Math.abs(lumR - lumG) < 0.01, `亮度 ${lumR.toFixed(3)} vs ${lumG.toFixed(3)}`);
  R.check('红↔深蓝的水平边界也能提出来', cHorz > 0.9, '对比度 = ' + cHorz.toFixed(3));
  R.check('弱边界（差 55/255）也被算出来，但值明显更小',
    cWeak > 0.15 && cWeak < 0.3, '对比度 = ' + cWeak.toFixed(3));

  const mask = V.outlineMask(px, w, h, 0.25);
  const count = mask.reduce((a, b) => a + b, 0);
  R.check('掩码只覆盖边界那一圈，不是整片（这就是"只保留轮廓"）',
    count > 0 && count < w * h * 0.5, count + ' / ' + (w * h) + ' 个像素');
  R.check('内部像素在掩码里全是 0',
    mask[1 * w + 1] === 0 && mask[3 * w + 6] === 0 && mask[7 * w + 3] === 0,
    '红区/绿区/深蓝区的内部都是 0');
  R.check('红绿分界的那些像素在掩码里是 1',
    mask[2 * w + 3] === 1 || mask[2 * w + 4] === 1, 'x=3 或 x=4 那一列被标记');
  R.check('门槛 0.25 时弱边界被滤掉（只留"对比鲜明"的）',
    mask[2 * w + 0] === 0 && mask[2 * w + 1] === 0, '暗红|红 那一列不在掩码里');

  // 门槛越高，留下的线越少
  const cnt = (t) => V.outlineMask(px, w, h, t).reduce((a, b) => a + b, 0);
  const loose = cnt(0.1), mid = cnt(0.25), tight = cnt(0.7);
  R.check('门槛调高 → 留下的分界线变少（弱边界先消失，强边界最后才消失）',
    loose > mid && mid >= tight && tight > 0,
    `0.1→${loose} / 0.25→${mid} / 0.7→${tight}`);
  R.check('门槛 0.1 时弱边界也进来了（所以它确实是被门槛滤掉的，不是没算出来）',
    loose > mid, `0.1 → ${loose} 个像素，0.25 → ${mid} 个`);

  // 平坦的纯色图：一条线都不该有
  const flat = new Uint8Array(16 * 16 * 4).fill(120);
  R.check('整张纯色图提不出任何轮廓',
    V.outlineMask(flat, 16, 16, 0.02).reduce((a, b) => a + b, 0) === 0, '0 条');

  R.check('CPU 侧的判据被单独抽成函数（着色器是它的 GPU 版，两处公式对应）',
    typeof V.outlineContrast === 'function' && typeof V.outlineMask === 'function',
    'outlineContrast / outlineMask');
}

/* ================================ 切割：只显示选区内的影像 */

R.section('切割：选区换算与判据（纯函数，可逐值断言）');
{
  const W = 320, H = 240;

  // 1) 像素矩形 → 归一化选区：就是除以宽高，不做任何插值
  const c = V.pixelsToClip(W, H, 32, 24, 160, 120);
  R.check('像素矩形 → 归一化选区（uv = 像素 / 尺寸）',
    Math.abs(c.x0 - 0.1) < 1e-12 && Math.abs(c.y0 - 0.1) < 1e-12 &&
    Math.abs(c.x1 - 0.5) < 1e-12 && Math.abs(c.y1 - 0.5) < 1e-12,
    JSON.stringify(c));

  // 2) 反过来：选区 → 像素，用来在面板上显示"选了多少像素"
  const px = V.clipToPixels(c, W, H);
  R.check('选区 → 像素矩形（往返一致）',
    px.x0 === 32 && px.y0 === 24 && px.w === 128 && px.h === 96,
    `${px.w}×${px.h} @ (${px.x0},${px.y0})`);

  // 3) 反向拖出来的矩形要被规整（x0>x1 也要能用）
  const flipped = V.normalizeClip({ x0: 0.8, y0: 0.9, x1: 0.2, y1: 0.1 });
  R.check('反着拖出来的选区被规整成正的（不会出现负面积）',
    flipped.x0 === 0.2 && flipped.y0 === 0.1 && flipped.x1 === 0.8 && flipped.y1 === 0.9,
    JSON.stringify(flipped));
  R.check('越界的选区被夹到 [0,1]',
    JSON.stringify(V.normalizeClip({ x0: -1, y0: -2, x1: 3, y1: 4 })) ===
    JSON.stringify({ x0: 0, y0: 0, x1: 1, y1: 1 }),
    JSON.stringify(V.normalizeClip({ x0: -1, y0: -2, x1: 3, y1: 4 })));
  R.check('缺省/空选区 = 整个画面', V.clipIsFull(null) && V.clipIsFull({ x0: 0, y0: 0, x1: 1, y1: 1 }));

  // 4) 面积
  R.check('选区面积 = 宽 × 高（0.4 × 0.4 = 16%）',
    Math.abs(V.clipArea({ x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.6 }) - 0.16) < 1e-12,
    V.clipArea({ x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.6 }).toFixed(4));

  /*
   * 5) ★ 判据本身：像素中心落在选区内才算数。
   *    这条必须与 PLANE_FS 里那段 `vUv.x < uClip.x || …` 完全一致（含边界）。
   */
  const half = { x0: 0, y0: 0, x1: 0.5, y1: 0.5 };
  let inside = 0, outside = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const u = (x + 0.5) / W, v = (y + 0.5) / H;
      const want = x < W / 2 && y < H / 2;
      if (V.clipContains(half, u, v) === want) { if (want) inside++; else outside++; }
    }
  }
  R.check('★ 逐像素核对：左上半区(160×120)的像素全部"在选区内"',
    inside === 160 * 120, inside + ' / ' + (160 * 120));
  R.check('★ 其余 3/4 画面的像素全部"在选区外"', outside === 320 * 240 - 160 * 120,
    outside + ' 个在外（应为 ' + (320 * 240 - 160 * 120) + '）');
  R.check('v=0 是图像**顶部**：上半区在选区内，下半区在外',
    V.clipContains(half, 0.25, 0.01) && !V.clipContains(half, 0.25, 0.99),
    'y 小 = 上 = 在选区内');

  // 6) 极小选区被抬到至少 1 像素（否则会出现"整幅都看不见"这种像 bug 的状态）
  const tiny = V.clipAtLeastOnePixel({ x0: 0.5, y0: 0.5, x1: 0.5, y1: 0.5 }, W, H);
  R.check('零面积选区被撑到至少 1 像素（不会变成"整幅都看不见"）',
    (tiny.x1 - tiny.x0) * W >= 1 - 1e-9 && (tiny.y1 - tiny.y0) * H >= 1 - 1e-9,
    `${(tiny.x1 - tiny.x0) * W}×${(tiny.y1 - tiny.y0) * H} 像素`);

  // 7) 选区对所有帧生效：同一块画面内容在不同尺寸的帧上得到同一个归一化选区
  const c2 = V.pixelsToClip(640, 480, 64, 48, 320, 240);
  R.check('同一块区域在不同尺寸的帧上得到同一个归一化选区（所以能对所有帧生效）',
    Math.abs(c2.x0 - c.x0) < 1e-12 && Math.abs(c2.y1 - c.y1) < 1e-12, JSON.stringify(c2));
}

R.section('切割编辑器：手柄命中与拖拽（纯函数）');
{
  const R0 = { x0: 0.2, y0: 0.2, x1: 0.8, y1: 0.8 };
  const tolU = 0.02, tolV = 0.025;      // 9 屏幕像素换算出来的容差

  R.check('四角：左上/右上/左下/右下',
    V.cropHit(R0, 0.2, 0.2, tolU, tolV) === 'nw' &&
    V.cropHit(R0, 0.8, 0.2, tolU, tolV) === 'ne' &&
    V.cropHit(R0, 0.2, 0.8, tolU, tolV) === 'sw' &&
    V.cropHit(R0, 0.8, 0.8, tolU, tolV) === 'se',
    '四角都认得出来');
  R.check('四边：上/下/左/右',
    V.cropHit(R0, 0.5, 0.2, tolU, tolV) === 'n' &&
    V.cropHit(R0, 0.5, 0.8, tolU, tolV) === 's' &&
    V.cropHit(R0, 0.2, 0.5, tolU, tolV) === 'w' &&
    V.cropHit(R0, 0.8, 0.5, tolU, tolV) === 'e',
    '四边都认得出来');
  R.check('矩形内部 = 移动，外部 = 画新矩形',
    V.cropHit(R0, 0.5, 0.5, tolU, tolV) === 'move' &&
    V.cropHit(R0, 0.05, 0.05, tolU, tolV) === 'new',
    '内部 move，外部 new');
  R.check('★ 选区还是"整个画面"时，按哪里都是画新矩形（否则拖着毫无反应）',
    V.cropHit({ x0: 0, y0: 0, x1: 1, y1: 1 }, 0.5, 0.5, tolU, tolV) === 'new' &&
    V.cropHit({ x0: 0, y0: 0, x1: 1, y1: 1 }, 0.01, 0.99, tolU, tolV) === 'new',
    '整幅选区 → 一律 new');

  const moved = V.cropDrag(R0, 'move', { u: 0.5, v: 0.5 }, { u: 0.6, v: 0.6 });
  R.check('拖动内部 = 整体平移（宽高不变）',
    Math.abs(moved.x0 - 0.3) < 1e-12 && Math.abs(moved.x1 - 0.9) < 1e-12 &&
    Math.abs(moved.x1 - moved.x0 - 0.6) < 1e-12,
    JSON.stringify(moved));
  const clamped = V.cropDrag(R0, 'move', { u: 0.5, v: 0.5 }, { u: 5, v: 5 });
  R.check('平移被夹在画面内（矩形不会被推出去，也不会被压扁）',
    clamped.x1 <= 1 + 1e-12 && clamped.y1 <= 1 + 1e-12 &&
    Math.abs(clamped.x1 - clamped.x0 - 0.6) < 1e-12,
    JSON.stringify(clamped));

  const east = V.cropDrag(R0, 'e', { u: 0.8, v: 0.5 }, { u: 0.6, v: 0.5 });
  R.check('拖右边只改 x1，其余三条边不动',
    Math.abs(east.x0 - 0.2) < 1e-12 && Math.abs(east.x1 - 0.6) < 1e-12 &&
    Math.abs(east.y0 - 0.2) < 1e-12 && Math.abs(east.y1 - 0.8) < 1e-12,
    JSON.stringify(east));
  const nw = V.cropDrag(R0, 'nw', { u: 0.2, v: 0.2 }, { u: 0.4, v: 0.3 });
  R.check('拖左上角同时改 x0/y0（另外两条边不动）',
    Math.abs(nw.x0 - 0.4) < 1e-12 && Math.abs(nw.y0 - 0.3) < 1e-12 &&
    Math.abs(nw.x1 - 0.8) < 1e-12 && Math.abs(nw.y1 - 0.8) < 1e-12,
    JSON.stringify(nw));
  const over = V.cropDrag(R0, 'e', { u: 0.8, v: 0.5 }, { u: 0.1, v: 0.5 });
  R.check('手柄拖过头（越过对面那条边）时选区被翻正，而不是变成负面积',
    over.x0 === 0.1 && over.x1 === 0.2 && over.x1 > over.x0, JSON.stringify(over));
  R.check('翻正之后仍然是一个合法的正向选区（面积 > 0，且都在 [0,1] 内）',
    over.x1 > over.x0 && over.y1 > over.y0 && over.x0 >= 0 && over.x1 <= 1,
    '宽 ' + (over.x1 - over.x0).toFixed(2));

  const fresh = V.cropDrag(R0, 'new', { u: 0.7, v: 0.75 }, { u: 0.25, v: 0.3 });
  R.check('在空白处按下并拖动 = 画一个新矩形（起点与终点都算）',
    fresh.x0 === 0.25 && fresh.y0 === 0.3 && fresh.x1 === 0.7 && fresh.y1 === 0.75,
    JSON.stringify(fresh));
}

R.section('★ 点云与照片的朝向必须是同一套（6 号 bug 的回归网）');
{
  R.check('点云的局部 y：图像第 0 行（顶）在 +y、最后一行在 -y',
    V.pixelLocal(320, 240, 0, 0)[1] > 0.49 &&
    V.pixelLocal(320, 240, 0, 239)[1] < -0.49 &&
    Math.abs(V.pixelLocal(320, 240, 160, 120)[1]) < 0.01,
    V.pixelLocal(320, 240, 0, 0)[1].toFixed(4) + ' / ' +
    V.pixelLocal(320, 240, 0, 239)[1].toFixed(4));
  R.check('点云的局部 x：图像第 0 列（左）在 -x、最后一列在 +x',
    V.pixelLocal(320, 240, 0, 0)[0] < -0.49 && V.pixelLocal(320, 240, 319, 0)[0] > 0.49,
    V.pixelLocal(320, 240, 0, 0)[0].toFixed(4) + ' / ' +
    V.pixelLocal(320, 240, 319, 0)[0].toFixed(4));
  R.check('★ 这条公式与帧平面的 uv 朝向一致：v=0 给的是 +y 那一端',
    Math.abs(V.pixelLocal(320, 240, 160, 0)[1] - (0.5 - 0.5 / 240)) < 1e-12 &&
    Math.abs(V.pixelLocal(320, 240, 160, 239)[1] + (0.5 - 0.5 / 240)) < 1e-12,
    '第 0 行 → +0.4979，最后一行 → −0.4979（像素中心，照片的 v=0 也在 +y）');

  // 投影层面的交叉核对：同一个图像像素，两条路径必须落在同一个屏幕像素上
  const geo = { planeW: 1, planeH: 0.75, depth: 1.6 };
  const cam = { az: 0, el: 0, zoom: 1, panU: 0, panV: 0, fov: Math.PI * 2 / 9 };
  const vp = { w: 600, h: 450 };
  const cp = V.camParams(geo, cam, vp);
  let worst = 0;
  for (const [X, Z] of [[218, 34], [160, 120], [32, 120], [300, 230]]) {
    const u = (X + 0.5) / 320, v = (Z + 0.5) / 240;
    const planePt = V.projectToPixel(cp, vp, (u - 0.5) * geo.planeW, (0.5 - v) * geo.planeH, 0);
    const pl = V.pixelLocal(320, 240, X, Z);
    const pointPt = V.projectToPixel(cp, vp, pl[0] * geo.planeW, pl[1] * geo.planeH, 0);
    worst = Math.max(worst, Math.abs(planePt[0] - pointPt[0]), Math.abs(planePt[1] - pointPt[1]));
  }
  R.check('★ 同一个图像像素：点云与照片投影到**同一个屏幕像素**（差 < 0.01 px）',
    worst < 0.01, '四个采样点最大偏差 ' + worst.toExponential(2) + ' px');
  // 反证：老写法（把 (z/h-0.5) 直接当局部 y）必须能被这条判据抓住
  const X = 218, Z = 34;
  const u = (X + 0.5) / 320, v = (Z + 0.5) / 240;
  const planePt = V.projectToPixel(cp, vp, (u - 0.5) * geo.planeW, (0.5 - v) * geo.planeH, 0);
  const oldPt = V.projectToPixel(cp, vp, u - 0.5, (v - 0.5) * geo.planeH, 0);
  R.check('反证：把 y 写成 v−0.5（旧写法）会偏出上百像素 —— 这条判据不是空的',
    Math.abs(planePt[1] - oldPt[1]) > 30,
    '偏差 ' + Math.abs(planePt[1] - oldPt[1]).toFixed(1) + ' px（上下颠倒）');
}

/* ======================================================= 7. EXIF 排序键 */

R.section('EXIF 拍摄时间（JPEG 最小解析）');
{
  // 手工拼一个带 EXIF 的最小 JPEG：SOI + APP1(Exif/TIFF) + EOI
  function buildJpeg(dateStr, orientation) {
    const s = dateStr + '\0';
    const entries = [];
    // IFD0：Orientation(0x0112) SHORT + ExifIFD 指针(0x8769) LONG
    // Exif IFD：DateTimeOriginal(0x9003) ASCII
    const asciiLen = s.length;
    const exifIfdOffset = 8 + 2 + 2 * 12 + 4;          // 紧跟在 IFD0 之后
    const dateDataOffset = exifIfdOffset + 2 + 12 + 4; // 跟在 Exif IFD 之后

    const tiff = new Uint8Array(dateDataOffset + asciiLen + 4);
    const dv = new DataView(tiff.buffer);
    dv.setUint16(0, 0x4D4D, false);   // 大端
    dv.setUint16(2, 0x002A, false);
    dv.setUint32(4, 8, false);

    // IFD0
    dv.setUint16(8, 2, false);
    let e = 10;
    dv.setUint16(e, 0x0112, false); dv.setUint16(e + 2, 3, false);
    dv.setUint32(e + 4, 1, false); dv.setUint16(e + 8, orientation, false);
    e += 12;
    dv.setUint16(e, 0x8769, false); dv.setUint16(e + 2, 4, false);
    dv.setUint32(e + 4, 1, false); dv.setUint32(e + 8, exifIfdOffset, false);
    e += 12;
    dv.setUint32(e, 0, false);        // 下一个 IFD = 0

    // Exif IFD
    dv.setUint16(exifIfdOffset, 1, false);
    const f = exifIfdOffset + 2;
    dv.setUint16(f, 0x9003, false); dv.setUint16(f + 2, 2, false);
    dv.setUint32(f + 4, asciiLen, false); dv.setUint32(f + 8, dateDataOffset, false);
    dv.setUint32(exifIfdOffset + 2 + 12, 0, false);
    for (let i = 0; i < asciiLen; i++) tiff[dateDataOffset + i] = s.charCodeAt(i);

    const app1Len = 2 + 6 + tiff.length;
    const out = new Uint8Array(2 + 2 + app1Len + 2);
    const odv = new DataView(out.buffer);
    let p = 0;
    out[p++] = 0xFF; out[p++] = 0xD8;                     // SOI
    out[p++] = 0xFF; out[p++] = 0xE1;                     // APP1
    odv.setUint16(p, app1Len, false); p += 2;
    out[p++] = 0x45; out[p++] = 0x78; out[p++] = 0x69; out[p++] = 0x66;  // Exif
    out[p++] = 0x00; out[p++] = 0x00;
    out.set(tiff, p); p += tiff.length;
    out[p++] = 0xFF; out[p++] = 0xD9;                     // EOI
    return out;
  }

  const j = buildJpeg('2024:03:17 08:09:10', 6);
  const parsed = STC.exif.parseJpeg(new DataView(j.buffer), j.byteLength);
  R.check('解析出 EXIF 日期', parsed.date instanceof Date, String(parsed.date));
  R.check('日期各字段正确（注意 EXIF 用冒号分隔日期）',
    parsed.date && parsed.date.getFullYear() === 2024 && parsed.date.getMonth() === 2 &&
    parsed.date.getDate() === 17 && parsed.date.getHours() === 8 &&
    parsed.date.getMinutes() === 9 && parsed.date.getSeconds() === 10,
    parsed.date && parsed.date.toISOString());
  R.check('解析出方向标记 Orientation=6', parsed.orientation === 6, 'orientation=' + parsed.orientation);
  R.check('标记为"确实有 EXIF"', parsed.hasExif === true);

  const noExif = new Uint8Array([0xFF, 0xD8, 0xFF, 0xD9]);
  const p2 = STC.exif.parseJpeg(new DataView(noExif.buffer), noExif.byteLength);
  R.check('没有 EXIF 时不报错、日期为 null', p2.date === null && p2.hasExif === false);

  const garbage = new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8]);
  const p3 = STC.exif.parseJpeg(new DataView(garbage.buffer), garbage.byteLength);
  R.check('非 JPEG 输入被安静地拒绝', p3.date === null && p3.hasExif === false);

  // 年份不合理的日期必须被丢掉，否则会把照片排到错误的位置
  const bad = buildJpeg('0000:00:00 00:00:00', 1);
  const p4 = STC.exif.parseJpeg(new DataView(bad.buffer), bad.byteLength);
  R.check('非法日期（0000:00:00）被丢弃', p4.date === null, String(p4.date));
}

/* ================================================== 8. 排序与预算规则 */

R.section('排序规则与显存预算');
{
  // 排序：EXIF 优先，其次文件名自然序（frame_2 必须排在 frame_10 前面）
  const files = [
    fakeImageFile('frame_10.png', 8, 8, 5000),
    fakeImageFile('frame_2.png', 8, 8, 1000),
    fakeImageFile('frame_1.png', 8, 8, 9000)
  ];
  const byName = await SQ.order(files, 'name');
  R.check('按文件名排序是自然序（2 在 10 之前）',
    byName.files.map((f) => f.name).join(',') === 'frame_1.png,frame_2.png,frame_10.png',
    byName.files.map((f) => f.name).join(','));

  const byTime = await SQ.order(files, 'mtime');
  R.check('按修改时间排序',
    byTime.files.map((f) => f.name).join(',') === 'frame_2.png,frame_10.png,frame_1.png',
    byTime.files.map((f) => f.name).join(','));

  const byExif = await SQ.order(files, 'exif');
  R.check('没有 EXIF 时间时退化为文件名自然序',
    byExif.files.map((f) => f.name).join(',') === 'frame_1.png,frame_2.png,frame_10.png',
    byExif.files.map((f) => f.name).join(','));
  R.check('统计出"没有 EXIF"的张数', byExif.noExif === 3, 'noExif=' + byExif.noExif);

  R.check('非图片文件被过滤', (await SQ.order(
    [fakeImageFile('a.png', 4, 4), { name: 'notes.txt', type: 'text/plain', size: 3 }], 'name'
  )).files.length === 1);

  // 超过单张纹理上限 → 明确跳过，绝不偷偷降分辨率
  const big = [fakeImageFile('a.png', 9000, 100), fakeImageFile('b.png', 100, 100)];
  let threw = null;
  try {
    await SQ.load(big, { sort: 'name', maxTextureSize: 8192 });
  } catch (e) { threw = e.message; }
  R.check('超出 GPU 纹理上限的帧被跳过并给出明确原因（不降分辨率）',
    threw !== null && /8192/.test(threw), String(threw).replace(/\n/g, ' '));

  // 显存预算：不满足时明确说明差多少，而不是让页面白掉
  const many = [];
  for (let i = 0; i < 6; i++) many.push(fakeImageFile('f' + i + '.png', 512, 512));
  const frameBytes = 512 * 512 * 4;
  const loaded = await SQ.load(many, {
    sort: 'name', maxTextureSize: 8192, budget: frameBytes * 3 + 1
  });
  R.check('显存预算不足时停止加载并记录原因（而非静默降质）',
    loaded.budgetHit !== null && loaded.frames.length === 3,
    loaded.budgetHit
      ? `载入 ${loaded.frames.length} 帧后停止：已用 ${loaded.budgetHit.usedMB}MB，本帧需 ${loaded.budgetHit.needMB}MB，上限 ${loaded.budgetHit.budgetMB}MB`
      : '没有触发预算');
  R.check('预算说明里给出了确切的字节数差',
    loaded.budgetHit && loaded.budgetHit.budgetMB === 3,
    JSON.stringify(loaded.budgetHit));
  R.check('预算内每一帧都保持原始尺寸（没有被缩放）',
    loaded.frames.every((f) => f.width === 512 && f.height === 512 && f.bytes === frameBytes),
    loaded.frames.map((f) => `${f.width}x${f.height}`).join(' '));

  // 纹理字节账必须等于原始像素数 × 4
  R.check('纹理字节账 = 帧数 × 宽 × 高 × 4',
    loaded.bytes === loaded.frames.length * frameBytes,
    `${loaded.bytes} vs ${loaded.frames.length * frameBytes}`);
}

STC.app.stop();          // 停掉渲染循环，否则 Node 事件循环不退出
process.exitCode = R.summary() ? 1 : 0;
