/* 时空立方体 · 数学
 *
 * 约定（坐标系是右手系，单位与「照片宽度」无关，照片宽固定为 1）：
 *
 *      +X  画面向右
 *      +Y  画面向上
 *      +Z  从第一帧指向最后一帧 —— 也就是时间轴的正方向
 *
 * 于是：
 *      正面（z = 0）        第一帧
 *      背面（z = depth）    最后一帧
 *      左右/上下四个侧面    每一行（列）像素沿 Z 拉成的颜色条
 *
 * 矩阵一律列主序（和 WebGL 一致），函数名里的 `m4` 前缀表示 4x4，
 * `mul(a, b)` 的语义是「先施加 b，再施加 a」，即 a·b·v。
 */
(function (STC) {
  'use strict';

  var TAU = Math.PI * 2;

  function clamp(v, a, b) { return v < a ? a : (v > b ? b : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function deg(d) { return d * Math.PI / 180; }
  function rad(r) { return r * 180 / Math.PI; }

  /* ------------------------------------------------------------ 4x4 矩阵 */

  function m4() {
    return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
  }

  /** out = a · b （两者都是列主序） */
  function mul(a, b, out) {
    out = out || m4();
    var a00 = a[0], a01 = a[1], a02 = a[2], a03 = a[3];
    var a10 = a[4], a11 = a[5], a12 = a[6], a13 = a[7];
    var a20 = a[8], a21 = a[9], a22 = a[10], a23 = a[11];
    var a30 = a[12], a31 = a[13], a32 = a[14], a33 = a[15];
    for (var i = 0; i < 4; i++) {
      var b0 = b[i * 4], b1 = b[i * 4 + 1], b2 = b[i * 4 + 2], b3 = b[i * 4 + 3];
      out[i * 4]     = a00 * b0 + a10 * b1 + a20 * b2 + a30 * b3;
      out[i * 4 + 1] = a01 * b0 + a11 * b1 + a21 * b2 + a31 * b3;
      out[i * 4 + 2] = a02 * b0 + a12 * b1 + a22 * b2 + a32 * b3;
      out[i * 4 + 3] = a03 * b0 + a13 * b1 + a23 * b2 + a33 * b3;
    }
    return out;
  }

  /** 透视投影，输出 NDC z ∈ [-1, 1] */
  function perspective(fovyRad, aspect, near, far, out) {
    out = out || m4();
    var f = 1 / Math.tan(fovyRad / 2);
    var nf = 1 / (near - far);
    out[0] = f / aspect; out[1] = 0; out[2] = 0;  out[3] = 0;
    out[4] = 0; out[5] = f; out[6] = 0;           out[7] = 0;
    out[8] = 0; out[9] = 0; out[10] = (far + near) * nf; out[11] = -1;
    out[12] = 0; out[13] = 0; out[14] = 2 * far * near * nf; out[15] = 0;
    return out;
  }

  /**
   * 正交投影，输出 NDC z ∈ [-1, 1]。
   *
   * near/far 是**沿视线的有符号距离**（前方为负，和 lookAt 的相机空间一致）：
   * 相机空间里点在视线前方时 z 为负，所以 near 通常取一个负数。
   * 映射公式与透视一致：z_ndc = -2/(far-near) * z + (far+near)/(near-far) 取负号后
   * 化简为上式的 (far+near)/(near-far) 与 2/(near-far)。
   */
  function ortho(left, right, bottom, top, near, far, out) {
    out = out || m4();
    var lr = 1 / (right - left);
    var bt = 1 / (top - bottom);
    var nf = 1 / (near - far);
    out[0] = 2 * lr; out[1] = 0;      out[2] = 0;       out[3] = 0;
    out[4] = 0;      out[5] = 2 * bt; out[6] = 0;       out[7] = 0;
    out[8] = 0;      out[9] = 0;      out[10] = 2 * nf; out[11] = 0;
    out[12] = -(right + left) * lr;
    out[13] = -(top + bottom) * bt;
    out[14] = (far + near) * nf;
    out[15] = 1;
    return out;
  }

  /** 视图矩阵：把世界坐标变换到相机坐标（相机看向 -Z） */
  function lookAt(eye, center, up, out) {
    out = out || m4();
    var zx = eye[0] - center[0], zy = eye[1] - center[1], zz = eye[2] - center[2];
    var zl = Math.hypot(zx, zy, zz) || 1;
    zx /= zl; zy /= zl; zz /= zl;

    var xx = up[1] * zz - up[2] * zy;
    var xy = up[2] * zx - up[0] * zz;
    var xz = up[0] * zy - up[1] * zx;
    var xl = Math.hypot(xx, xy, xz);
    if (xl < 1e-6) { xx = 1; xy = 0; xz = 0; }   // up 与视线共线时的退化处理
    else { xx /= xl; xy /= xl; xz /= xl; }

    var yx = zy * xz - zz * xy;
    var yy = zz * xx - zx * xz;
    var yz = zx * xy - zy * xx;

    out[0] = xx; out[1] = yx; out[2] = zx; out[3] = 0;
    out[4] = xy; out[5] = yy; out[6] = zy; out[7] = 0;
    out[8] = xz; out[9] = yz; out[10] = zz; out[11] = 0;
    out[12] = -(xx * eye[0] + xy * eye[1] + xz * eye[2]);
    out[13] = -(yx * eye[0] + yy * eye[1] + yz * eye[2]);
    out[14] = -(zx * eye[0] + zy * eye[1] + zz * eye[2]);
    out[15] = 1;
    return out;
  }

  /** 模型矩阵：先缩放，再平移到局部原点 loc。照片平面在 z = 0 上。 */
  function modelMat(sx, sy, sz, loc, out) {
    out = out || m4();
    out[0] = sx; out[1] = 0; out[2] = 0; out[3] = 0;
    out[4] = 0; out[5] = sy; out[6] = 0; out[7] = 0;
    out[8] = 0; out[9] = 0; out[10] = sz; out[11] = 0;
    out[12] = loc[0]; out[13] = loc[1]; out[14] = loc[2]; out[15] = 1;
    return out;
  }

  function normalMat3(m, out) {
    out = out || new Float32Array(9);
    // 这里的模型矩阵只有缩放+平移，法线矩阵就是左上 3x3 的逆转置，
    // 对轴对齐缩放来说等于按 1/s 缩放。直接取左上角再归一化即可
    // —— 但我们只在世界空间做光照/描边，不依赖精确法线，故原样取出。
    out[0] = m[0]; out[1] = m[1]; out[2] = m[2];
    out[3] = m[4]; out[4] = m[5]; out[5] = m[6];
    out[6] = m[8]; out[7] = m[9]; out[8] = m[10];
    return out;
  }

  /**
   * 世界坐标 → NDC。
   * 注意这里**没有做透视除法**：我们用的是正交式的用法（相机在远处、
   * 场景很扁），而且所有断言都基于同一套变换，所以保持"不除 w"的一致性更重要。
   * 真正的透视除法由 GPU 在光栅化前完成。
   */
  function xformPoint(m, x, y, z, out) {
    out = out || [0, 0, 0];
    out[0] = m[0] * x + m[4] * y + m[8] * z + m[12];
    out[1] = m[1] * x + m[5] * y + m[9] * z + m[13];
    out[2] = m[2] * x + m[6] * y + m[10] * z + m[14];
    out[3] = m[3] * x + m[7] * y + m[11] * z + m[15];
    return out;
  }

  /* -------------------------------------------------------------- 轨道相机
   *
   * 球坐标：方位角 az 绕 +Y，仰角 el 抬离 XZ 平面。
   *   az = 0, el = 0  →  相机在 +Z 轴上，正对第一帧（正视）
   * 我们刻意让 az 的符号与直觉一致：向右拖动让物体向右转。
   */
  function orbitEye(target, dist, azDeg, elDeg, out) {
    out = out || [0, 0, 0];
    var az = deg(azDeg), el = deg(elDeg);
    var c = Math.cos(el);
    out[0] = target[0] + dist * c * Math.sin(az);
    out[1] = target[1] + dist * Math.sin(el);
    out[2] = target[2] + dist * c * Math.cos(az);
    return out;
  }

  /** 包围球半径：把半尺寸 (hx, hy, hz) 的盒子装进以 target 为心的球 */
  function boundRadius(hx, hy, hz) {
    return Math.hypot(hx, hy, hz);
  }

  /** 让半径为 r 的球恰好进入竖直视场 fovy 所需的距离 */
  function fitDistance(r, fovyRad) {
    return r / Math.max(Math.sin(fovyRad / 2), 1e-4);
  }

  STC.math = {
    TAU: TAU, clamp: clamp, lerp: lerp, deg: deg, rad: rad,
    m4: m4, mul: mul, perspective: perspective, ortho: ortho, lookAt: lookAt,
    modelMat: modelMat, normalMat3: normalMat3, xformPoint: xformPoint,
    orbitEye: orbitEye, boundRadius: boundRadius, fitDistance: fitDistance
  };
})(window.STC = window.STC || {});
