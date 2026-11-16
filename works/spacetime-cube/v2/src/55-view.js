/* 时空立方体 · 计算核心（无 DOM 依赖，可在 Node 里直接跑）
 *
 * 这个文件存在的唯一理由是**可验证性**。
 *
 * 这个会话的运行环境禁止命名管道，Chromium 的多进程 IPC 因此失败、
 * 渲染器进程起不来，所以「启动无头浏览器截图断言」这条路在这里是走不通的。
 * 于是把真正的计算逻辑（相机、投影、逐帧解算、深度排序）集中到这里，
 * 全部做成纯函数：不碰 document、不碰 WebGL、不碰时间。
 * 这样 Node 里可以逐值断言它们，而不是只能"看起来没问题"。
 *
 * app.js 与 renderer.js 只负责把这里算出来的结果喂给 GPU。
 */
(function (STC) {
  'use strict';

  var M = STC.math;

  /**
   * 正交取景的视野半高 = 包围球半径 × 这个系数。
   *
   * 取 1.16 的理由：包围球半径正好是立方体对角线的一半，
   * 所以正对时立方体在画面里占约 1/1.16 ≈ 86% 高度，转到对角线时占满 ——
   * 既能保证任何角度都不被裁掉，又不会显得太小。**关键是与视角无关。**
   */
  var ORTHO_SPHERE_FILL = 1.16;

  /* ============================================================== 相机 */

  /**
   * 由「几何 + 相机状态 + 视口尺寸」算出视线、投影、视图矩阵。
   *
   * **投影一律用正交（orthographic）**：立方体各面都是严格的矩形，
   * 切片几何就是真正的 xoz 平面，没有透视缩放、没有近大远小。
   * 这是刻意的选择 —— 读图场景里透视会让远处的帧变小，
   * 帧与帧之间就失去可比性。
   *
   * 约定：方位角 az = 0 且仰角 el = 0 时，相机在 +Z 轴上看向立方体中心，
   * 也就是正对第一帧（第一帧在 z = 0，是立方体的前表面）。
   *
   * 坐标一致性 —— 这里错开半个深度，立方体就会被裁掉：
   *   帧摆在 z ∈ [0, depth]，第一帧 z=0、最后一帧 z=depth
   *   所以立方体的几何中心是 targetZ = depth/2，取景与深度排序都必须以它为准。
   *
   * @param {{planeW:number, planeH:number, depth:number}} geo
   * @param {{az:number, el:number, zoom:number, panU:number, panV:number}} c
   * @param {{w:number, h:number}} vp
   */
  function camParams(geo, c, vp) {
    var hx = geo.planeW * 0.5, hy = geo.planeH * 0.5, hz = geo.depth * 0.5;
    var targetZ = hz;
    var radius = M.boundRadius(hx, hy, hz);

    var az = M.deg(c.az), el = M.deg(c.el);
    // 从相机指向场景的方向
    var dir = [
      -Math.cos(el) * Math.sin(az),
      -Math.sin(el),
      -Math.cos(el) * Math.cos(az)
    ];
    // 相机的右向量（水平，且与视线垂直）
    var right = [Math.cos(az), 0, -Math.sin(az)];
    // 上向量 = 视线 × 右向量
    var up = [
      dir[1] * right[2] - dir[2] * right[1],
      dir[2] * right[0] - dir[0] * right[2],
      dir[0] * right[1] - dir[1] * right[0]
    ];

    var aspect = vp.w / Math.max(vp.h, 1);
    var target = [0, 0, targetZ];
    // 正交下相机距离只影响裁剪，不影响成像大小，所以取一个宽松的固定值
    var distance = radius * 4;

    var offU = c.panU * radius, offV = c.panV * radius;
    var eye = [
      target[0] - dir[0] * distance + right[0] * offU + up[0] * offV,
      target[1] - dir[1] * distance + right[1] * offU + up[1] * offV,
      target[2] - dir[2] * distance + right[2] * offU + up[2] * offV
    ];

    // 平移之后视线要重新指向目标
    var d2 = [target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]];
    var dl = Math.hypot(d2[0], d2[1], d2[2]) || 1;
    d2 = [d2[0] / dl, d2[1] / dl, d2[2] / dl];

    /*
     * 正交视锥：**按包围球定死尺度**，不随视角变化。
     *
     * 这里刻意不用"按旋转后的包围盒拟合"：那样立方体转到对角线时投影范围最大、
     * 转到正对时最小，两者相差 √3 ≈ 1.73 倍，看起来就是"一转动就忽大忽小"。
     * 包围球半径与旋转无关，所以取 halfH = radius × 系数 就能得到**恒定的尺度**：
     * 无论怎么转，同一个世界长度在屏幕上永远是同样多像素。
     *
     * 代价是正对时四周会多留一些空 —— 这是"不缩放"必须付出的，也正是想要的效果。
     */
    var halfH = radius * ORTHO_SPHERE_FILL / Math.max(c.zoom, 0.05);
    var halfW = halfH * aspect;

    // 极窄的窗口（aspect < 1）下，按包围球算出的横向范围可能仍然装不下立方体。
    // 这时只把**横向**撑开：纵向尺度保持不变（那是"大小不随视角变"的落点），
    // 横向在窄窗口里放开不构成问题 —— 因为 aspect 与视角无关，
    // 所以撑开量也是恒定的，转动视角依然不会忽大忽小。
    var tightW = radius * ORTHO_SPHERE_FILL;
    if (halfW < tightW) halfW = tightW;

    // 正交矩阵的 near/far 是**到相机的绝对距离**（都是正的），不是以目标点为原点。
    // 相机在 distance 处看向 target，场景沿视线最远伸到 distance+radius，
    // 最近到 distance-radius，所以两端各留 2*radius 的余量。
    var pad = 2 * radius;
    var near = Math.max(0.01, distance - pad);
    var far = distance + pad;
    var projM = M.ortho(-halfW, halfW, -halfH, halfH, near, far);
    var viewM = M.lookAt(eye, target, [0, 1, 0]);

    // 世界单位 → 像素（点大小用；正交下与深度无关）
    var scale = vp.h / (2 * halfH);

    return {
      ortho: true,
      eye: eye, target: target, dir: d2, dist: distance, radius: radius,
      proj: projM, view: viewM, near: near, far: far, scale: scale,
      right: right, up: up,
      halfW: halfW, halfH: halfH,
      fitH: radius * ORTHO_SPHERE_FILL, fitW: radius * ORTHO_SPHERE_FILL * aspect,
      sphereFill: ORTHO_SPHERE_FILL
    };
  }

  /**
   * 正交取景的视野半高由 camParams 直接按包围球算出（见 ORTHO_SPHERE_FILL）。
   *
   * 这里额外暴露一个「按旋转后包围盒拟合」的版本，**只用于诊断和测试**：
   * 它能让画面在正对时尽量铺满，但代价是尺度随视角变化（对角线时 1.73 倍），
   * 所以实际渲染不用它 —— 用户明确要求"大小不随视角变"。
   */
  function orthoBounds(hx, hy, hz, right, up, aspect) {
    var maxU = 0, maxV = 0;
    for (var i = 0; i < 8; i++) {
      var x = (i & 1) ? hx : -hx;
      var y = (i & 2) ? hy : -hy;
      var z = (i & 4) ? hz : -hz;
      maxU = Math.max(maxU, Math.abs(x * right[0] + y * right[1] + z * right[2]));
      maxV = Math.max(maxV, Math.abs(x * up[0] + y * up[1] + z * up[2]));
    }
    var halfH = Math.max(maxV, maxU / Math.max(aspect, 1e-6));
    return { maxU: maxU, maxV: maxV, halfH: halfH, halfW: halfH * aspect };
  }

  /** 世界坐标 → 画布像素坐标（左上为原点，与 probe 的取点方式一致）
   *
   * 必须做透视除法（除以 w）：GPU 在光栅化前会自己做这一步，
   * 但这个函数是"某个世界坐标应该出现在哪个像素"的判据，
   * 少除一个 w 会算出偏大的偏移量，于是把"立方体是否完整入画"判错。
   */
  function projectToPixel(cp, vp, x, y, z) {
    var m = M.mul(cp.proj, cp.view, M.m4());
    var n = M.xformPoint(m, x, y, z);
    var w = n[3];
    if (!w || Math.abs(w) < 1e-9) w = 1;
    var nx = n[0] / w, ny = n[1] / w, nz = n[2] / w;
    return [
      (nx * 0.5 + 0.5) * vp.w,
      (1 - (ny * 0.5 + 0.5)) * vp.h,
      nz
    ];
  }

  /** 从相机出发沿视线看，某个 z 位置排在第几（数值越大越远） */
  function frameDepth(cp, z) {
    return -(cp.dir[0] * cp.eye[0] + cp.dir[1] * cp.eye[1] + cp.dir[2] * (z - cp.eye[2]));
  }

  /* ========================================================== 逐帧解算 */

  /**
   * 把「当前状态」解算成渲染器要的逐帧条目。
   * 纯函数：给定同样的输入永远得到同样的输出，因此可以被逐值断言。
   *
   * @param {{geo:object, frames:Array}} seq
   * @param {{allGhost:boolean, opCur:number, opOther:number, otherMode:string}} ui
   * @param {number} cur 当前帧下标
   */
  function resolve(seq, ui, cur) {
    var n = seq.frames.length;
    var step = seq.geo && n > 1 ? seq.geo.depth / (n - 1) : 0;
    var items = [];
    var stat = { total: n, opaque: 0, ghost: 0, points: 0, hidden: 0, currentIndex: -1 };

    for (var i = 0; i < n; i++) {
      var f = seq.frames[i];
      var isCur = !ui.allGhost && i === cur;
      var op = ui.allGhost ? ui.opOther : (isCur ? ui.opCur : ui.opOther);
      var asPoints = ui.otherMode === 'points' && !isCur;

      // 点云缓冲还没建好就先不画，避免闪一帧空白
      if (asPoints && !f.pointVao) op = 0;
      if (op <= 0.002) op = 0;

      if (op >= 0.998) stat.opaque++;
      else if (op > 0) stat.ghost++;
      else stat.hidden++;
      if (asPoints && op > 0) stat.points++;
      if (isCur) stat.currentIndex = i;

      items.push({
        i: i,
        z: i * step,
        // 相邻帧间距：渲染器用它把挤出厚度夹到不会穿模的范围
        frameStep: step,
        opacity: op,
        current: isCur,
        pointCloud: asPoints && op > 0,
        vao: asPoints && f.pointVao ? f.pointVao.vao : null,
        count: asPoints && f.pointVao ? f.pointVao.count : 0,
        texture: f.texture,
        w: seq.geo ? seq.geo.planeW : 1,
        h: seq.geo ? seq.geo.planeH : 1,
        // 纹理的像素尺寸：轮廓模式要用它算"一个纹素在 uv 里有多大"
        texW: f.width || 0,
        texH: f.height || 0
      });
    }
    return { items: items, stats: stat };
  }

  /* ========================================================== 深度排序 */

  /** 给每个条目补上沿视线的深度，并返回由远到近的数组（半透明必须这样排） */
  function sortFarToNear(items, cp) {
    for (var i = 0; i < items.length; i++) {
      items[i].depth = frameDepth(cp, items[i].z);
    }
    items.sort(function (a, b) { return b.depth - a.depth; });
    return items;
  }

  /* ============================================================ 点云 */

  /**
   * 采样网格：步长 stride 下，多少列多少行、总共多少个点。
   * 这个数是「点云有多少个点」的唯一真相来源，
   * 渲染时的实例数必须与它一致，否则会出现空隙或越界。
   */
  function pointGrid(w, h, stride) {
    var s = Math.max(1, Math.floor(stride));
    var cols = Math.floor((w - 1) / s) + 1;
    var rows = Math.floor((h - 1) / s) + 1;
    return { cols: cols, rows: rows, count: cols * rows };
  }

  /**
   * 用总点数预算反推采样步长。
   *
   * 注意量纲：budget 是**所有帧加起来**的点数上限，
   * 所以单帧上限是 budget / 帧数。步长 s 使单帧采样点数约为 像素数 / s²。
   * 令 像素数/s² ≤ budget/帧数  →  s = ceil(sqrt(像素数 × 帧数 / budget))。
   */
  function pointStride(totalPixels, budget, frames) {
    var n = frames && frames > 0 ? frames : 1;
    var b = budget > 0 ? budget : 1;
    if (totalPixels <= b) return 1;
    return Math.max(1, Math.ceil(Math.sqrt(totalPixels * n / b)));
  }

  /* ==================================================== 切割：只留选区 */
  /*
   * 「切割」= 只显示某一块区域内的影像。
   *
   * 选区用**归一化 uv** 存：{x0, y0, x1, y1} ∈ [0,1]，朝向与帧平面的 vUv 完全一致：
   *   u = 0 → 图像左边缘     u = 1 → 右边缘
   *   v = 0 → 图像**顶部**   v = 1 → 底部
   * （v 的朝向见 50-shaders.js 里 V_QUAD 的约定：v=0 给的是四边形的上方顶点。）
   *
   * 存归一化坐标而不是像素，是因为它必须**对所有帧生效**：
   * 各帧像素尺寸可能不同（混排照片与视频、或用了缩放），归一化之后
   * "同一块区域"在各帧上指的就是同一块画面内容。
   *
   * 这几个函数都是纯函数，着色器里的判据与它们是同一套（见 PLANE_FS 的 uClip），
   * 所以"选区内/外"可以在 Node 里逐像素断言，而不是只能靠眼睛看。
   */

  function clamp01(v) {
    return v < 0 ? 0 : (v > 1 ? 1 : (isFinite(v) ? v : 0));
  }

  /** 把任意的 {x0,y0,x1,y1} 规整成 [0,1] 内、且 x0≤x1、y0≤y1 的选区 */
  function normalizeClip(r) {
    if (!r) return { x0: 0, y0: 0, x1: 1, y1: 1 };
    var ax = clamp01(r.x0), bx = clamp01(r.x1);
    var ay = clamp01(r.y0), by = clamp01(r.y1);
    return {
      x0: Math.min(ax, bx), y0: Math.min(ay, by),
      x1: Math.max(ax, bx), y1: Math.max(ay, by)
    };
  }

  /** 选区是不是"整个画面"（等价于没有切割） */
  function clipIsFull(r) {
    var c = normalizeClip(r);
    return c.x0 <= 0 && c.y0 <= 0 && c.x1 >= 1 && c.y1 >= 1;
  }

  /** 选区面积占整幅画面的比例（0..1） */
  function clipArea(r) {
    var c = normalizeClip(r);
    return (c.x1 - c.x0) * (c.y1 - c.y0);
  }

  /**
   * 选区是否至少有 1 像素宽/高 —— 太小的选区会变成"整幅都看不见"，这里给个下限。
   * 退化成一个点（宽高都是 0）时**以那个点为中心撑开**，而不是只把某一条边挪出去。
   */
  function clipAtLeastOnePixel(r, w, h) {
    var c = normalizeClip(r);
    var minU = w > 0 ? 1 / w : 1;
    var minV = h > 0 ? 1 / h : 1;
    var x0 = c.x0, x1 = c.x1, y0 = c.y0, y1 = c.y1;
    if (x1 - x0 < minU) {
      var cx = Math.min(Math.max((x0 + x1) / 2, minU / 2), 1 - minU / 2);
      x0 = cx - minU / 2;
      x1 = cx + minU / 2;
    }
    if (y1 - y0 < minV) {
      var cy = Math.min(Math.max((y0 + y1) / 2, minV / 2), 1 - minV / 2);
      y0 = cy - minV / 2;
      y1 = cy + minV / 2;
    }
    return { x0: x0, y0: y0, x1: x1, y1: y1 };
  }

  /** 图像像素矩形（边界坐标，不是像素中心）→ 归一化选区 */
  function pixelsToClip(w, h, x0, y0, x1, y1) {
    if (!(w > 0) || !(h > 0)) return { x0: 0, y0: 0, x1: 1, y1: 1 };
    return normalizeClip({ x0: x0 / w, y0: y0 / h, x1: x1 / w, y1: y1 / h });
  }

  /** 归一化选区 → 图像像素矩形（用于面板里显示"选了多少像素"） */
  function clipToPixels(r, w, h) {
    var c = normalizeClip(r);
    return {
      x0: c.x0 * w, y0: c.y0 * h, x1: c.x1 * w, y1: c.y1 * h,
      w: (c.x1 - c.x0) * w, h: (c.y1 - c.y0) * h
    };
  }

  /**
   * 图像像素中心是不是落在选区内。
   * 判据与 PLANE_FS 里那段必须**完全一致**（含边界：>= 且 <=）。
   */
  function clipContains(r, u, v) {
    var c = normalizeClip(r);
    return u >= c.x0 && u <= c.x1 && v >= c.y0 && v <= c.y1;
  }

  /**
   * 图像像素中心 → 照片的**局部坐标**（[-0.5,0.5]²）。
   *
   * 这一条是点云与照片"朝向上必须一致"的唯一真相来源：
   * 帧平面的 V_QUAD 约定是 u=0 在 -x 端、v=0 在 +y 端，而 v=0 是图像顶部，
   * 所以图像第 0 行（顶）落在 **+y**。点云如果直接拿 (x/w-0.5, z/h-0.5) 当局部坐标，
   * 就会与照片**上下颠倒** —— 这正是 6 号 bug 那一类错误（当时改错了方向，
   * 换成这条共用规则之后两边不可能再各写一套）。
   */
  function pixelLocal(w, h, x, z) {
    return [(x + 0.5) / w - 0.5, 0.5 - (z + 0.5) / h];
  }

  /* ------------------------------------------------ 框选面板的拖拽逻辑 */
  /*
   * 这两条也是纯函数：编辑器只负责把鼠标坐标换算成 uv，
   * "拖到了哪个手柄、拖完变成什么选区"由这里决定 —— 于是可以在 Node 里断言，
   * 不需要真实鼠标，也不需要浏览器。
   */

  /**
   * 命中判定：鼠标落在哪个手柄上。
   * @returns 'nw'|'n'|'ne'|'e'|'se'|'s'|'sw'|'w'|'move'|'new'
   *          （'new' = 落在选区之外，按下去就画一个新矩形）
   */
  function cropHit(rect, u, v, tolU, tolV) {
    var c = normalizeClip(rect);
    var tu = tolU === undefined ? 0.02 : tolU;
    var tv = tolV === undefined ? 0.02 : tolV;
    /*
     * 选区还是"整个画面"时，按哪里都算"画新矩形"。
     * 它本来就无处可移（平移会被夹回原位），若按"内部 = 移动"处理，
     * 用户拖了半天什么都不会发生 —— 看起来就像框选坏了。
     */
    if (clipIsFull(c)) return 'new';
    var inX = u >= c.x0 - tu && u <= c.x1 + tu;
    var inY = v >= c.y0 - tv && v <= c.y1 + tv;
    if (!inX || !inY) return 'new';
    var L = Math.abs(u - c.x0) <= tu, R = Math.abs(u - c.x1) <= tu;
    var T = Math.abs(v - c.y0) <= tv, B = Math.abs(v - c.y1) <= tv;
    if (L && T) return 'nw';
    if (R && T) return 'ne';
    if (L && B) return 'sw';
    if (R && B) return 'se';
    if (T) return 'n';
    if (B) return 's';
    if (L) return 'w';
    if (R) return 'e';
    return 'move';
  }

  /**
   * 拖拽之后的选区。
   * @param {object} rect 起始选区（第一次按下时的选区）
   * @param {string} mode cropHit 的结果
   * @param {{u:number,v:number}} a 按下时的点
   * @param {{u:number,v:number}} b 当前的点
   */
  function cropDrag(rect, mode, a, b) {
    var c = normalizeClip(rect);
    if (mode === 'new') {
      return normalizeClip({ x0: a.u, y0: a.v, x1: b.u, y1: b.v });
    }
    if (mode === 'move') {
      var w = c.x1 - c.x0, h = c.y1 - c.y0;
      // 整体不出画面：先按位移走，再夹回来（而不是把矩形压扁）
      var x0 = Math.min(Math.max(c.x0 + (b.u - a.u), 0), 1 - w);
      var y0 = Math.min(Math.max(c.y0 + (b.v - a.v), 0), 1 - h);
      return { x0: x0, y0: y0, x1: x0 + w, y1: y0 + h };
    }
    var r = { x0: c.x0, y0: c.y0, x1: c.x1, y1: c.y1 };
    if (mode.indexOf('w') >= 0) r.x0 = b.u;
    if (mode.indexOf('e') >= 0) r.x1 = b.u;
    if (mode.indexOf('n') >= 0) r.y0 = b.v;
    if (mode.indexOf('s') >= 0) r.y1 = b.v;
    // normalizeClip 会把"拖过头"的矩形翻正，所以手柄可以互换、不会变成负面积
    return normalizeClip(r);
  }

  /* ======================================================== 边界像素图集 */
  /*
   * 四个侧面各需要「每帧的一条边界像素」：
   *   左 = 每一行取第 0 列        右 = 每一行取最后一列
   *   上 = 每一列取第 0 行        下 = 每一列取最后一行
   *
   * 每一条边单独一张纹理，尺寸 = （沿边的长度）×（帧数）：
   *   左/右：width = h，height = n      上/下：width = w，height = n
   * 每个纹素是**完整的 RGBA**，也就是那条边界像素的真实颜色。
   *
   * 这里曾经把四条边分别压进 RGBA 的四个通道（R=左 G=右 B=上 A=下），
   * 于是侧面只能是灰度的，而且纹理只上传了 1 行高、其余帧的数据被静默丢掉。
   * 两个错误叠在一起的表现就是"侧面颜色全是灰色、每帧还都一样"。
   * 现在不再节省这点显存：侧面用真实颜色，帧用纹理的行来区分。
   */

  /** 一条边有多少个采样点（沿边方向的像素数） */
  function edgeLength(which, w, h) {
    return (which === 'left' || which === 'right') ? h : w;
  }

  /**
   * 把一帧的一条边写进图集的第 rowBase 行（每像素 RGBA）。
   *
   * @param {Uint8ClampedArray|Uint8Array} px 该帧的原始像素
   * @param {number} dstW 图集宽度（所有帧里最长的那个边），用**最近邻**重采样：
   *                      目标列 j ← 源下标 floor(j * srcLen / dstW)
   *                      尺寸一致时这是一一对应，不做任何插值。
   * @returns {number} 写进去的像素个数
   */
  function packEdge(px, w, h, which, out, rowBase, dstW) {
    var srcLen = edgeLength(which, w, h);
    if (!srcLen || !dstW) return 0;
    var written = 0;
    for (var j = 0; j < dstW; j++) {
      var at = Math.min(srcLen - 1, Math.floor(j * srcLen / dstW));
      var i;
      if (which === 'left') i = (at * w) * 4;
      else if (which === 'right') i = (at * w + w - 1) * 4;
      else if (which === 'top') i = at * 4;
      else i = ((h - 1) * w + at) * 4;
      var o = rowBase + j * 4;
      out[o] = px[i];
      out[o + 1] = px[i + 1];
      out[o + 2] = px[i + 2];
      out[o + 3] = 255;
      written++;
    }
    return written;
  }

  /**
   * 侧面在几何上的四条边 —— **渲染器与参考渲染共用这一张表**。
   *
   * 这里的 `span` 与 `off` 必须分别给出，不能像早先那样共用一个 uLong：
   * 左右墙沿 y 展开，半长是 **halfH**；上下墙沿 x 展开，半长是 **halfW**。
   * 当时两者都用了 halfW，于是左右墙比照片高出 (halfW-halfH)，
   * 上下墙又比照片窄 —— 表现就是"加出来的侧面尺寸不对"。
   */
  function bandSides(geo) {
    var halfW = geo.planeW * 0.5, halfH = geo.planeH * 0.5;
    return [
      { side: 'left', axisY: 1, off: -halfW, span: halfH },
      { side: 'right', axisY: 1, off: halfW, span: halfH },
      { side: 'top', axisY: 0, off: halfH, span: halfW },
      { side: 'bottom', axisY: 0, off: -halfH, span: halfW }
    ];
  }

  /**
   * 世界点沿边方向的位置 → 该边纹理的横向坐标（0..1）。
   * @param {number} axisY 1 = 边沿 y（左右墙），0 = 边沿 x（上下墙）
   * @param {number} along -1..1（由 aPos.x 换算出来的归一化位置）
   *
   * 左右墙：世界 +y 是图像顶部，所以图像第 0 行落在 t=1 那一端 → 取 1-t。
   * 上下墙：世界 +x 是图像右侧，图像第 0 列落在 t=0 那一端 → 取 t。
   */
  function edgeCoord(axisY, along) {
    var t = (along + 1) * 0.5;
    return axisY ? 1 - t : t;
  }

  /** 第 i 帧在纹理里的行坐标（取样点落在纹素中心，配合 NEAREST 精确命中） */
  function frameRow(i, n) {
    if (n <= 1) return 0.5;
    return (Math.max(0, Math.min(n - 1, i)) + 0.5) / n;
  }

  /**
   * 「平均色」模式：把每条边压成一个均值（它其实是一整个面只用一种颜色）。
   *
   * 这里的语义是**沿整条边取样求平均**，取样间隔为 step：
   *   左边缘 = 最左一列自上而下取平均；右边缘 = 最右一列
   *   上边缘 = 最上一行；下边缘 = 最下一行
   * 四条边一律按升序扫，避免"有的边正着扫、有的边倒着扫"这种说不清的行为。
   */
  function averageEdges(px, w, h, step) {
    var s = Math.max(1, step || 4);

    function meanColumn(col) {
      var a = [0, 0, 0], c = 0;
      for (var z = 0; z < h; z += s) {
        var i = (z * w + col) * 4;
        a[0] += px[i]; a[1] += px[i + 1]; a[2] += px[i + 2]; c++;
      }
      return c ? [Math.round(a[0] / c), Math.round(a[1] / c), Math.round(a[2] / c)] : [0, 0, 0];
    }

    function meanRow(row) {
      var a = [0, 0, 0], c = 0;
      for (var x = 0; x < w; x += s) {
        var i = (row * w + x) * 4;
        a[0] += px[i]; a[1] += px[i + 1]; a[2] += px[i + 2]; c++;
      }
      return c ? [Math.round(a[0] / c), Math.round(a[1] / c), Math.round(a[2] / c)] : [0, 0, 0];
    }

    return {
      left: meanColumn(0),
      right: meanColumn(w - 1),
      top: meanRow(0),
      bottom: meanRow(h - 1)
    };
  }

  /**
   * 侧面颜色条在时间轴上的取样：世界 z → 帧下标。
   * 侧面从 z=0（第一帧）拉到 z=depth（最后一帧），
   * 所以这个映射必须是单调的、且两端刚好落在首末帧上。
   */
  function zToFrame(z, depth, n) {
    if (n <= 1) return 0;
    var t = depth > 0 ? z / depth : 0;
    return t * (n - 1);
  }

  /**
   * packEdge 的「直接返回四条边」版本，供参考渲染与逐值核对使用。
   * 与应用共用同一套下标算式，不存在"两套实现各错各的"。
   * 每一条边返回该边每个位置的 [r,g,b]。
   */
  function edgeColors(px, w, h) {
    var res = { left: [], right: [], top: [], bottom: [] };
    ['left', 'right', 'top', 'bottom'].forEach(function (which) {
      var len = edgeLength(which, w, h);
      var out = new Uint8Array(len * 4);
      packEdge(px, w, h, which, out, 0, len);
      for (var j = 0; j < len; j++) {
        res[which].push([out[j * 4], out[j * 4 + 1], out[j * 4 + 2]]);
      }
    });
    return res;
  }

  /* ======================================================== 轮廓提取 */
  /*
   * 「提取画面中对比鲜明的颜色分界线，并且只保留轮廓」这件事的**唯一真相**在这里，
   * 着色器里的 PLANE_FS 是它的 GPU 版（公式逐项对应，见 50-shaders.js 的注释）。
   *
   * 判据：一个像素与它上下左右四个邻居的**逐通道最大差**，四者取最大。
   * 为什么不用亮度差？红↔绿这种"等亮度的强对比"亮度差接近 0，会被整片漏掉，
   * 而那恰恰是"对比鲜明的颜色分界线"的典型例子。
   *
   * @param {Uint8ClampedArray|Uint8Array} px RGBA 像素
   * @param {number} w @param {number} h
   * @param {number} x @param {number} y 像素坐标（整数）
   * @returns {number} 0..1 的对比度（超过阈值就算分界线）
   */
  function outlineContrast(px, w, h, x, y) {
    var i = (y * w + x) * 4;
    var r = px[i], g = px[i + 1], b = px[i + 2];
    var m = 0;
    // 上下左右四个邻居（越界就跳过，不做出界采样）
    var dx = [1, -1, 0, 0], dy = [0, 0, 1, -1];
    for (var k = 0; k < 4; k++) {
      var nx = x + dx[k], ny = y + dy[k];
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
      var j = (ny * w + nx) * 4;
      var dr = Math.abs(px[j] - r), dg = Math.abs(px[j + 1] - g), db = Math.abs(px[j + 2] - b);
      var d = dr > dg ? dr : dg;
      if (db > d) d = db;
      if (d > m) m = d;
    }
    return m / 255;
  }

  /**
   * 整张图的轮廓掩码：1 = 分界线，0 = 内部。
   * 纯函数，用来把"轮廓到底提得对不对"变成可断言的事实。
   */
  function outlineMask(px, w, h, threshold) {
    var t = threshold === undefined ? 0.25 : threshold;
    var mask = new Uint8Array(w * h);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        if (outlineContrast(px, w, h, x, y) >= t) mask[y * w + x] = 1;
      }
    }
    return mask;
  }

  STC.view = {
    camParams: camParams,
    projectToPixel: projectToPixel,
    frameDepth: frameDepth,
    resolve: resolve,
    sortFarToNear: sortFarToNear,
    pointGrid: pointGrid,
    pointStride: pointStride,
    // 切割选区（纯函数：着色器里的 uClip 判据与它们同源）
    normalizeClip: normalizeClip,
    clipIsFull: clipIsFull,
    clipArea: clipArea,
    clipAtLeastOnePixel: clipAtLeastOnePixel,
    pixelsToClip: pixelsToClip,
    clipToPixels: clipToPixels,
    clipContains: clipContains,
    // 图像像素 → 照片局部坐标（点云与照片朝向一致）
    pixelLocal: pixelLocal,
    // 框选面板：手柄命中与拖拽（纯函数，可无浏览器断言）
    cropHit: cropHit,
    cropDrag: cropDrag,
    packEdge: packEdge,
    edgeLength: edgeLength,
    edgeColors: edgeColors,
    averageEdges: averageEdges,
    bandSides: bandSides,
    edgeCoord: edgeCoord,
    frameRow: frameRow,
    outlineContrast: outlineContrast,
    outlineMask: outlineMask,
    zToFrame: zToFrame
  };
})(window.STC = window.STC || {});
