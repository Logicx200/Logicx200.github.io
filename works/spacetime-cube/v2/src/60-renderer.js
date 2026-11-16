/* 时空立方体 · 渲染器
 *
 * 一次 render() 的绘制顺序是刻意安排的，顺序错了就会出现「后面的帧挡住前面的帧」：
 *
 *   1. 侧面颜色条 —— 不透明、写深度（它们是立方体的外墙）
 *   2. 不透明的帧平面 —— 写深度，互相正确遮挡
 *   3. 半透明的帧平面 —— 不写深度，按离相机由远到近排序，否则混合结果取决于先后
 *   4. 点云 —— 不写深度，在平面之后
 *   5. 白色线框 / 立方体外框 / 时间轴 —— 最后画，永远压在内容之上
 *
 * 另外，帧平面之间不写深度（只读），所以正对时看到的永远是所有帧的叠加，
 * 而不是「最近的那张把后面全挡住」—— 轨迹要能透出来，这是前提。
 */
(function (STC) {
  'use strict';

  var S = STC.shaders;

  function create(ctx, canvas) {
    var gl = ctx.gl;
    var P = {};
    var geom = {};

    /* ------------------------------------------------------------ program */

    function build() {
      P.plane = ctx.program(S.PLANE_VS, S.PLANE_FS, 'plane', ['aPos', 'aUv']);
      P.band = ctx.program(S.BAND_VS, S.BAND_FS, 'band', ['aPos']);
      P.solid = ctx.program(S.SOLID_VS, S.SOLID_FS, 'solid', ['aPos']);
      P.point = ctx.program(S.POINT_VS, S.POINT_FS, 'point', ['aPos', 'aUv2', 'aPosPx', 'aColor']);
      if (!P.plane || !P.band || !P.solid || !P.point) return false;

      var quad = ctx.buffer(new Float32Array(S.V_QUAD));
      geom.quad = ctx.vao(function () {
        ctx.attrib(0, quad, 3, gl.FLOAT, false, 20, 0);
        ctx.attrib(1, quad, 2, gl.FLOAT, false, 20, 12);
      });

      // 一条侧立面：四个角 = 「沿边的两端」(u=-1/1) × 「前/后」(v=0/1)。
      // 世界坐标由 BAND_VS 用 uSpan/uOff/uAxisY + 模型矩阵算出。
      geom.volBand = ctx.vao(function () {
        var b = ctx.buffer(new Float32Array([
          0, 0,          // 前，u=0
          1, 0,          // 前，u=1
          0, 1,          // 后，u=0
          1, 1           // 后，u=1
        ]));
        ctx.attrib(0, b, 2, gl.FLOAT, false, 8, 0);
      });

      /*
       * 「一帧的显示区域描边」= **真正的矩形线框**（4 条线段，8 个顶点）。
       *
       * 早先这里是用 BAND_VS 把四角缩到中心画出来的 —— 那画出来的是四条
       * 从角到中心的线，而且四个顶点组成的 TRIANGLE_STRIP 其实**填满**了整个
       * 矩形。于是"描边"变成了一层半透明白色蒙版，200 帧叠起来整片发白。
       * 现在它就是 4 条边，按 GL_LINES 画。
       */
      geom.rect = ctx.vao(function () {
        var b = ctx.buffer(new Float32Array([
          -0.5, -0.5, 0.5, -0.5,
          0.5, -0.5, 0.5, 0.5,
          0.5, 0.5, -0.5, 0.5,
          -0.5, 0.5, -0.5, -0.5
        ]));
        ctx.attrib(0, b, 2, gl.FLOAT, false, 8, 0);
      });
      geom.rectCount = 8;

      var c = new THREE_LESS_QUAD();
      geom.pointCorners = ctx.buffer(c.data);
      geom.pointCornerCount = c.count;

      /*
       * 立方体外框：**12 条棱**，每条两个端点。
       *
       * 这里必须是**真正的 VAO**。早先写的是 `geom.cage = ctx.buffer(...)`，
       * 然后在渲染时 `gl.bindVertexArray(geom.cage)` —— 把一个 Buffer 当 VAO 绑定，
       * WebGL2 会直接报 INVALID_OPERATION 并保留原来绑定的 VAO，
       * 于是外框（以及同样写错的时间轴）**一次都画不出来**。
       * 这也是"白色线框完全没显示"的根因。
       */
      geom.cage = ctx.vao(function () {
        var b = ctx.buffer(new Float32Array(cageVerts()));
        ctx.attrib(0, b, 3, gl.FLOAT, false, 0, 0);
      });
      geom.cageCount = 24;

      /*
       * 时间轴：从第一帧中心指向最后一帧中心的一条线，**末端带箭头**。
       *
       * 加箭头是因为用户看到这条黄线时的第一反应是"它为什么指着正面？"——
       * 一条两端都一样的线看不出方向，而它想表达的恰恰是**时间往哪边走**：
       * 起点 = 第一帧（正面），箭头 = 最后一帧（背面）。
       * 顶点：主线 2 个 + 箭头四条 8 个 = 10 个（GL_LINES）。
       * 箭头做成四根刺（±x、±y 各两根），这样从任何视角看都是一个锥形箭头，
       * 而不会在某个方向上退化成一条线。
       */
      geom.axis = ctx.vao(function () {
        var tip = [0, 0, 1], back = 0.93, w = 0.055;
        var v = [0, 0, 0, tip[0], tip[1], tip[2]];
        var barbs = [[w, 0], [-w, 0], [0, w], [0, -w]];
        for (var i = 0; i < barbs.length; i++) {
          v.push(tip[0], tip[1], tip[2]);
          v.push(barbs[i][0], barbs[i][1], back);
        }
        var b = ctx.buffer(new Float32Array(v));
        ctx.attrib(0, b, 3, gl.FLOAT, false, 0, 0);
      });
      geom.axisCount = 10;

      buildDebugTextures();

      return true;
    }

    function THREE_LESS_QUAD() {
      // 两个三角形拼成一个单位方块，供点云实例化使用
      this.data = new Float32Array([-1, -1, 1, -1, -1, 1, 1, -1, 1, 1, -1, 1]);
      this.count = 6;
    }

    /**
     * 单位立方体的 **12 条棱**（8 个顶点两两相连），供 GL_LINES 使用。
     * 这才是"立方体的线框"，而不是每张照片的显示区域 —— 后者在 200 帧时
     * 会有 200 个白框叠在一起，整个画面就白了。
     */
    function cageVerts() {
      var v = [];
      var c = [
        [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [-0.5, 0.5, -0.5],
        [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5], [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5]
      ];
      var edges = [
        [0, 1], [1, 2], [2, 3], [3, 0],
        [4, 5], [5, 6], [6, 7], [7, 4],
        [0, 4], [1, 5], [2, 6], [3, 7]
      ];
      for (var i = 0; i < edges.length; i++) {
        var a = c[edges[i][0]], b = c[edges[i][1]];
        v.push(a[0], a[1], a[2], b[0], b[1], b[2]);
      }
      return v;
    }

    /* ------------------------------------------------------------ 纹理 */

    function uploadFrame(f, filter) {
      if (f.texture) return f.texture;
      if (f.textureFailed) return null;          // 已经失败过，不反复重试
      f.texture = ctx.texture2D({
        source: f.bitmap,
        filter: (filter === 'nearest') ? gl.NEAREST : gl.LINEAR,
        flipY: true,
        label: f.name
      });
      if (!f.texture) {
        /*
         * 上传真的失败了。这时**必须**显式记下来：
         * 采样器没有纹理时 WebGL 的返回是未定义的，多数驱动给纯白 ——
         * 于是故障表现成"一块正常的白"，从画面上根本看不出来。
         * 着色器那边还会把它画成品红（见 PLANE_FS 的 uHasTex），双保险。
         */
        f.textureFailed = true;
        ctx.report('texture', '第 ' + (f.index + 1) + ' 帧（' + f.name +
          '）纹理上传失败。这一帧会显示成品红，而不是它的真实内容。\n' +
          '常见原因：单张尺寸超过 GPU 上限（本机 ' + ctx.info.maxTextureSize + '），' +
          '或该图解码后不是有效的位图。');
      }
      return f.texture;
    }

    function releaseFrames(frames) {
      for (var i = 0; i < frames.length; i++) {
        if (frames[i].texture) { gl.deleteTexture(frames[i].texture); frames[i].texture = null; }
        if (frames[i].pointVao) {
          gl.deleteVertexArray(frames[i].pointVao.vao);
          gl.deleteBuffer(frames[i].pointVao.posBuf);
          gl.deleteBuffer(frames[i].pointVao.colBuf);
          frames[i].pointVao = null;
        }
        if (frames[i].bitmap && frames[i].bitmap.close) { frames[i].bitmap.close(); frames[i].bitmap = null; }
      }
    }

    /* ------------------------------------------------------------ 点云 */

    /**
     * 为一个采样点建实例缓冲。
     * 颜色直接拷贝原图字节 —— 不做加权平均，不做降采样，
     * 所以点云里每个点的颜色就是那个像素的原始值。
     */
    function buildPoints(frame, stride) {
      if (frame.pointVao) return frame.pointVao;

      var w = frame.width, h = frame.height;
      var w2 = Math.floor((w - 1) / stride) + 1;
      var h2 = Math.floor((h - 1) / stride) + 1;
      var n = w2 * h2;

      var canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      var c2 = canvas.getContext('2d', { willReadFrequently: true, alpha: true });
      c2.drawImage(frame.bitmap, 0, 0);
      var px;
      try {
        px = c2.getImageData(0, 0, w, h).data;
      } catch (e) {
        ctx.report('points', frame.name + '：无法读取像素（' + (e && e.message || e) +
          '）。若用 file:// 打开，浏览器会禁止读回像素，请改用本地服务启动。');
        return null;
      }

      var pos = new Float32Array(n * 2);
      var col = new Float32Array(n * 4);
      var p = 0, q = 0;
      for (var z = 0; z < h; z += stride) {
        for (var x = 0; x < w; x += stride) {
          /*
           * 局部坐标**必须**用 view.pixelLocal 这一份共用公式：
           * 它保证图像第 0 行（顶）落在 +y，也就是与帧平面的 uv 朝向一致。
           * 早先这里直接写 (x/w-0.5, z/h-0.5)，等于把 y 取了负号，
           * 于是点云相对照片**上下颠倒** —— 而两条路径各写一套公式时，
           * 这种错只能靠肉眼发现（见 16 号 bug）。
           */
          var pl = STC.view.pixelLocal(w, h, x, z);
          pos[p++] = pl[0];
          pos[p++] = pl[1];
          var s = (z * w + x) * 4;
          col[q++] = px[s];
          col[q++] = px[s + 1];
          col[q++] = px[s + 2];
          col[q++] = px[s + 3];
        }
      }

      var posBuf = ctx.buffer(pos);
      var colBuf = ctx.buffer(col);
      var cornerBuf = geom.pointCorners;
      var vao = ctx.vao(function () {
        // location 0：单位方块的四角（每顶点）
        gl.bindBuffer(gl.ARRAY_BUFFER, cornerBuf);
        gl.enableVertexAttribArray(0);
        gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
        // location 2：逐实例的像素坐标
        gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
        gl.enableVertexAttribArray(2);
        gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 0, 0);
        gl.vertexAttribDivisor(2, 1);
        // location 3：逐实例的原始颜色
        gl.bindBuffer(gl.ARRAY_BUFFER, colBuf);
        gl.enableVertexAttribArray(3);
        gl.vertexAttribPointer(3, 4, gl.FLOAT, false, 0, 0);
        gl.vertexAttribDivisor(3, 1);
      });

      frame.pointVao = { vao: vao, count: n, posBuf: posBuf, colBuf: colBuf };
      return frame.pointVao;
    }

    function dropPoints(frame) {
      if (!frame.pointVao) return;
      gl.deleteVertexArray(frame.pointVao.vao);
      gl.deleteBuffer(frame.pointVao.posBuf);
      gl.deleteBuffer(frame.pointVao.colBuf);
      frame.pointVao = null;
    }

    /* --------------------------------------------------- 边界像素图集 */
    /*
     * 每一条边单独一张纹理，尺寸 =（沿边的像素数）×（帧数）：
     *   左/右：width = 最长的 h，height = n
     *   上/下：width = 最长的 w，height = n
     * 每个纹素是那条边界像素的**真实 RGBA**，纹理的一行就是一帧。
     *
     * 这一版纠正了两个会同时发作的老错误：
     *   1. 老图集把四条边挤进 RGBA 四个通道、每个通道只存一个 R 分量，
     *      于是侧面只能是灰的；
     *   2. 老代码算出 W×n 的像素却按 W×1 上传，n-1 帧被静默丢掉，
     *      于是所有帧的侧面颜色完全一样。
     *
     * 「平均色」模式：每条边压成一个均值，只存 1 列（width=1），
     * 采样时靠 CLAMP_TO_EDGE 取到那一列，省显存。
     */
    function buildEdgeAtlas(seq, mode, onProgress) {
      var frames = seq.frames;
      var n = frames.length;
      if (!n) return null;
      if (mode === 'off') return null;

      var W = 0, H = 0, i;
      for (i = 0; i < n; i++) {
        if (frames[i].width > W) W = frames[i].width;
        if (frames[i].height > H) H = frames[i].height;
      }
      if (W > ctx.info.maxTextureSize || H > ctx.info.maxTextureSize || n > ctx.info.maxTextureSize) {
        ctx.report('edge', '侧面颜色条图集 ' + W + '×' + n + ' 超出纹理上限，已关闭侧面。');
        return null;
      }

      // avg 模式每条边只有一个颜色 → 宽度 1
      var widthOf = {
        left: mode === 'avg' ? 1 : H,
        right: mode === 'avg' ? 1 : H,
        top: mode === 'avg' ? 1 : W,
        bottom: mode === 'avg' ? 1 : W
      };
      var buf = {};
      var SIDES = ['left', 'right', 'top', 'bottom'];
      for (i = 0; i < SIDES.length; i++) {
        buf[SIDES[i]] = new Uint8Array(widthOf[SIDES[i]] * n * 4);
      }

      var canvas = document.createElement('canvas');
      var c2 = null;

      for (i = 0; i < n; i++) {
        var f = frames[i];
        if (canvas.width !== f.width || canvas.height !== f.height) {
          canvas.width = f.width;
          canvas.height = f.height;
          c2 = canvas.getContext('2d', { willReadFrequently: true, alpha: true });
        }
        c2.clearRect(0, 0, f.width, f.height);
        c2.drawImage(f.bitmap, 0, 0);
        var px;
        try {
          px = c2.getImageData(0, 0, f.width, f.height).data;
        } catch (e) {
          ctx.report('edge', '无法读取像素（' + (e && e.message || e) + '）。' +
            'file:// 下浏览器会禁止读回像素，请改用本地服务启动。');
          return null;
        }

        var w = f.width, h = f.height;

        if (mode === 'avg') {
          // 语义见 55-view.js 的 averageEdges：每条边整条取样求平均
          var m = STC.view.averageEdges(px, w, h, 4);
          for (var s = 0; s < SIDES.length; s++) {
            var side = SIDES[s];
            var rgb = m[side];
            var off = i * widthOf[side] * 4;
            var cnt = widthOf[side];
            for (var j = 0; j < cnt; j++) {
              buf[side][off + j * 4] = rgb[0];
              buf[side][off + j * 4 + 1] = rgb[1];
              buf[side][off + j * 4 + 2] = rgb[2];
              buf[side][off + j * 4 + 3] = 255;
            }
          }
        } else {
          // 边界像素：侧面就是原图最外一列/一行沿时间轴的拉伸，颜色是真的
          for (var s2 = 0; s2 < SIDES.length; s2++) {
            var side2 = SIDES[s2];
            var dstW = widthOf[side2];
            STC.view.packEdge(px, w, h, side2, buf[side2], i * dstW * 4, dstW);
          }
        }

        if (onProgress && (i % 4 === 3 || i === n - 1)) {
          onProgress({ phase: 'edge', done: i + 1, total: n });
        }
      }

      releaseEdgeTextures(seq);
      seq.edgeTex = {};
      var bytes = 0;
      for (i = 0; i < SIDES.length; i++) {
        var nm = SIDES[i];
        var tex = ctx.edgeTexture(widthOf[nm], n, buf[nm], gl.NEAREST);
        if (!tex) { releaseEdgeTextures(seq); return null; }
        seq.edgeTex[nm] = tex;
        bytes += widthOf[nm] * n * 4;
      }
      seq.edgeBytes = bytes;
      seq.edgeRows = n;
      seq.edgeMode = mode;
      return seq.edgeTex;
    }

    /** 释放四张边纹理（没有就什么都不做） */
    function releaseEdgeTextures(seq) {
      if (!seq) return;
      if (seq.edgeTex) {
        for (var k in seq.edgeTex) {
          if (seq.edgeTex[k]) gl.deleteTexture(seq.edgeTex[k]);
        }
        seq.edgeTex = null;
      }
      // 兼容老字段：万一还有单张图集的引用，一并释放
      if (seq.edgeTexture) { gl.deleteTexture(seq.edgeTexture); seq.edgeTexture = null; }
      seq.edgeBytes = 0;
    }

    /* ------------------------------------------------------------ 渲染 */

    var mats = {
      proj: STC.math.m4(),
      view: STC.math.m4(),
      model: STC.math.m4()
    };

    /** 按「沿视线的深度」把列表排成由远到近（半透明必须这个顺序画） */
    function sortFarToNear(list, eye, dir) {
      return STC.view.sortFarToNear(list, { eye: eye, dir: dir });
    }

    // 标记的颜色。立方体线框就是用户说的「白色线框」，所以它必须是白的；
    // 时间轴是橙色，用来区分时间方向。
    var WHITE_NORMAL = [1, 1, 1, 0.45];
    var WHITE_SELECTED = [1, 1, 1, 0.98];
    var CUBE_EDGE = [1, 1, 1, 0.85];
    var AXIS_COLOR = [0.95, 0.72, 0.25, 0.95];

    function setColor(prog, rgba) {
      prog.set('uColor', function (l) {
        gl.uniform4f(l, rgba[0], rgba[1], rgba[2], rgba[3]);
      });
    }

    /**
     * @param {object} o  {seq, resolved, cam, proj, view, viewport, ui}
     *   resolved: STC.resolve(...) 的结果，每帧带 {z, opacity, current, pointCloud, vao, texture, w, h, count}
     */
    function render(o) {
      var seq = o.seq, R = o.resolved, ui = o.ui, vp = o.viewport;
      var eye = o.cam.eye, dir = o.cam.dir;
      var halfW = seq.geo.planeW * 0.5;
      var halfH = seq.geo.planeH * 0.5;
      var halfD = seq.geo.depth * 0.5;

      gl.viewport(0, 0, vp.w, vp.h);
      gl.clearColor(0.02, 0.027, 0.043, 1);
      gl.enable(gl.DEPTH_TEST);
      gl.depthFunc(gl.LEQUAL);
      gl.depthMask(true);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      gl.enable(gl.BLEND);
      gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
      gl.disable(gl.CULL_FACE);

      mats.proj.set(o.proj);
      mats.view.set(o.view);

      /*
       * 每条侧立面 = 那一帧的某条边沿厚度方向挤出的四边形。
       * 颜色是那条边上的**真实像素颜色**（每帧一行，行号由 uRow 给出），
       * 沿厚度方向是常数 —— 一张薄片的侧立面本来就只有一个颜色。
       *
       * **不透明度跟着那一帧的照片走**：薄片的立面就是那张照片的边，
       * 照片是 12% 半透明，它的边也必须 12%。所以这里和帧平面用同一套规则：
       *   不透明的立面先画、写深度；
       *   半透明的立面由远到近画、**不写深度**（否则半透明的薄片会互相挡掉）。
       *
       * bandDebug（`?banddebug=1` 或 STC.app.setBandDebug(true)）会把四个立面
       * 直接涂成红/绿/蓝/黄四种纯色 —— 这样"某个侧面到底有没有被画出来"
       * 一眼就能看出来，不用靠照片本身的边缘颜色去猜。
       */
      var bandOpaque = [], bandGhost = [];
      if (P.band && seq.edgeTex && ui.showBands && ui.edgeMode !== 'off') {
        for (var bi = 0; bi < R.items.length; bi++) {
          var bIt = R.items[bi];
          if (bIt.opacity <= 0.002) continue;          // 完全透明 = 连立面也看不见
          if (thicknessOf(bIt, ui) <= 0) continue;     // 厚度为 0 时立面没有面积
          if (bIt.opacity >= 0.998) bandOpaque.push(bIt);
          else bandGhost.push(bIt);
        }
        sortFarToNear(bandGhost, eye, dir);

        var sides = STC.view.bandSides(seq.geo);
        P.band.use();
        P.band.set('uProj', function (l) { gl.uniformMatrix4fv(l, false, mats.proj); });
        P.band.set('uView', function (l) { gl.uniformMatrix4fv(l, false, mats.view); });
        P.band.set('uEdgeTex', function (l) { gl.uniform1i(l, 0); });
        gl.activeTexture(gl.TEXTURE0);

        // 不透明的一批写深度，半透明的一批不写、由远到近
        var bandLists = [[bandOpaque, true], [bandGhost, false]];
        for (var bl = 0; bl < 2; bl++) {
          var list = bandLists[bl][0], writeDepth = bandLists[bl][1];
          if (!list.length) continue;
          gl.depthMask(writeDepth);
          for (var e = 0; e < list.length; e++) {
            var ie = list[e];
            var d = thicknessOf(ie, ui);
            STC.math.modelMat(1, 1, 1, [0, 0, ie.z + d * 0.5], mats.model);
            P.band.set('uModel', function (l) { gl.uniformMatrix4fv(l, false, mats.model); });
            P.band.set('uThick', function (l) { gl.uniform1f(l, d); });
            P.band.set('uOpacity', function (l) { gl.uniform1f(l, ie.opacity); });
            P.band.set('uRow', function (l) {
              gl.uniform1f(l, STC.view.frameRow(ie.i, seq.frames.length));
            });
            for (var k = 0; k < 4; k++) {
              (function (side, idx) {
                P.band.set('uSpan', function (l) { gl.uniform1f(l, side.span); });
                P.band.set('uOff', function (l) { gl.uniform1f(l, side.off); });
                P.band.set('uAxisY', function (l) { gl.uniform1i(l, side.axisY); });
                // 每条边一张纹理，画之前绑对应的那张
                gl.bindTexture(gl.TEXTURE_2D,
                  ui.bandDebug ? geom.debugTex[idx] : seq.edgeTex[side.side]);
              })(sides[k], k);
              gl.bindVertexArray(geom.volBand);
              gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
            }
          }
        }
        gl.depthMask(true);
        gl.bindVertexArray(null);
      }

      /* ---- 2 & 3. 帧平面 ---- */
      var opaqueList = [], transList = [];
      for (var i = 0; i < R.items.length; i++) {
        var it = R.items[i];
        if (it.pointCloud || it.opacity <= 0.002 || !it.texture) continue;
        if (it.opacity >= 0.998) opaqueList.push(it);
        else transList.push(it);
      }
      sortFarToNear(transList, eye, dir);

      if (P.plane) {
        P.plane.use();
        P.plane.set('uProj', function (l) { gl.uniformMatrix4fv(l, false, mats.proj); });
        P.plane.set('uView', function (l) { gl.uniformMatrix4fv(l, false, mats.view); });
        P.plane.set('uTex', function (l) { gl.uniform1i(l, 0); });
        gl.activeTexture(gl.TEXTURE0);

        drawPlanes(opaqueList, true, ui);
        drawPlanes(transList, false, ui);
      }

      /* ---- 4. 点云 ---- */
      if (P.point && ui.otherMode === 'points') {
        var pts = [];
        for (var m = 0; m < R.items.length; m++) {
          var im = R.items[m];
          if (im.pointCloud && im.opacity > 0.002 && im.vao) pts.push(im);
        }
        if (pts.length) {
          sortFarToNear(pts, eye, dir);
          P.point.use();
          P.point.set('uProj', function (l) { gl.uniformMatrix4fv(l, false, mats.proj); });
          P.point.set('uView', function (l) { gl.uniformMatrix4fv(l, false, mats.view); });
          P.point.set('uViewport', function (l) { gl.uniform2f(l, vp.w, vp.h); });
          P.point.set('uSquare', function (l) { gl.uniform1i(l, ui.square ? 1 : 0); });
          P.point.set('uBaseSize', function (l) { gl.uniform1f(l, ui.dotSize * 0.5); });
          P.point.set('uOrtho', function (l) { gl.uniform1i(l, o.projOrtho ? 1 : 0); });
          // 正交下点大小就是像素数：uSizePx、uOrthoSize 同义。
          // **不能**再乘世界→像素比例，否则 200 帧那种尺度下会变成亚像素、整片消失。
          P.point.set('uOrthoSize', function (l) { gl.uniform1f(l, Math.max(1, ui.dotSize)); });
          P.point.set('uLumWeight', function (l) { gl.uniform1f(l, ui.lumWeight); });
          P.point.set('uLumThreshold', function (l) { gl.uniform1f(l, ui.lumThreshold); });
          P.point.set('uLumDir', function (l) { gl.uniform1i(l, ui.lumDir === 'dark' ? 1 : 0); });
          // 切割对点云同样生效（选区外的点不画）—— 否则切到点云就会"选区失效"
          P.point.set('uClipOn', function (l) { gl.uniform1i(l, ui.clipOn ? 1 : 0); });
          P.point.set('uClip', function (l) {
            var c = ui.clip || [0, 0, 1, 1];
            gl.uniform4f(l, c[0], c[1], c[2], c[3]);
          });
          gl.depthMask(false);
          for (var q = 0; q < pts.length; q++) {
            (function (pq) {
              P.point.set('uModel', function (l) {
                gl.uniformMatrix4fv(l, false,
                  STC.math.modelMat(seq.geo.planeW, seq.geo.planeH, 1, [0, 0, pq.z], mats.model));
              });
              P.point.set('uOpacity', function (l) { gl.uniform1f(l, pq.opacity); });
              P.point.set('uSizePx', function (l) { gl.uniform1f(l, Math.max(1, Math.round(ui.dotSize))); });
              gl.bindVertexArray(pq.vao);
              gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, pq.count);
            })(pts[q]);
          }
          gl.bindVertexArray(null);
          gl.depthMask(true);
        }
      }

      /* ---- 5. 标记：写在最后，永远压在内容之上 ---- */
      /*
       * 标记是**参照物**，不是场景内容：外框、时间轴、显示区域描边都要能被看见。
       * 所以这一段关掉深度测试 —— 否则外框会被立方体自己的不透明面挡住，
       * 用户看到的就是"线框没画出来"。
       */
      gl.depthMask(false);
      gl.disable(gl.DEPTH_TEST);
      if (P.solid) {
        P.solid.use();
        P.solid.set('uProj', function (l) { gl.uniformMatrix4fv(l, false, mats.proj); });
        P.solid.set('uView', function (l) { gl.uniformMatrix4fv(l, false, mats.view); });

        /*
         * 「每张照片的显示区域」描边 —— 默认**关闭**。
         * 现在是**真正的矩形线框**（GL_LINES，8 个顶点）。
         * 需要时可以在面板里单独打开（当前帧会更亮一点，便于定位）。
         */
        if (ui.showFrameOutline) {
          /*
           * 开了「切割」之后，这个框跟着**选区**走，而不是画整张照片 ——
           * 描边的意义是"这一帧有多少面积真的被画出来了"，选区外那一圈
           * 实际上是空的，再框一整张会误导人。
           * 单位矩形的局部坐标是 [-0.5,0.5]²（u=0 在 -x、v=0 在 +y），
           * 所以按选区缩放/平移即可：
           *   x 中心 = ((x0+x1)/2 - 0.5) · planeW      宽度 = (x1-x0) · planeW
           *   y 中心 = (0.5 - (y0+y1)/2) · planeH      高度 = (y1-y0) · planeH
           */
          var clipOn = !!ui.clipOn && ui.clip;
          var cq = clipOn ? STC.view.normalizeClip({
            x0: ui.clip[0], y0: ui.clip[1], x1: ui.clip[2], y1: ui.clip[3]
          }) : null;
          for (var e2 = 0; e2 < R.items.length; e2++) {
            var ie2 = R.items[e2];
            if (cq) {
              STC.math.modelMat(
                (cq.x1 - cq.x0) * seq.geo.planeW,
                (cq.y1 - cq.y0) * seq.geo.planeH, 1,
                [((cq.x0 + cq.x1) / 2 - 0.5) * seq.geo.planeW,
                  (0.5 - (cq.y0 + cq.y1) / 2) * seq.geo.planeH, ie2.z], mats.model);
            } else {
              STC.math.modelMat(seq.geo.planeW, seq.geo.planeH, 1, [0, 0, ie2.z], mats.model);
            }
            P.solid.set('uModel', function (l) { gl.uniformMatrix4fv(l, false, mats.model); });
            setColor(P.solid, ie2.current ? WHITE_SELECTED : WHITE_NORMAL);
            gl.bindVertexArray(geom.rect);
            gl.drawArrays(gl.LINES, 0, geom.rectCount);
          }
          gl.bindVertexArray(null);
        }

        /*
         * 立方体外框：**12 条棱**（不是每张照片的框）。
         * 外框的范围要盖住"第一帧前表面 → 最后一帧后表面"，
         * 也就是所有薄片的并集：[-d/2, depth + d/2]。
         */
        if (ui.showCube) {
          var firstD = R.items.length ? thicknessOf(R.items[0], ui) : 0;
          var shellD = seq.geo.depth + firstD;
          STC.math.modelMat(halfW * 2, halfH * 2, shellD, [0, 0, halfD], mats.model);
          P.solid.set('uModel', function (l) { gl.uniformMatrix4fv(l, false, mats.model); });
          setColor(P.solid, CUBE_EDGE);
          gl.bindVertexArray(geom.cage);
          gl.drawArrays(gl.LINES, 0, geom.cageCount);
        }

        if (ui.showAxis) {
          // 时间轴：单位长度，箭头在 z=1 那一端（= 最后一帧），所以模型矩阵的
          // z 缩放就是 depth，平移半个 depth 让它从第一帧指到最后一帧。
          STC.math.modelMat(1, 1, seq.geo.depth, [0, 0, halfD], mats.model);
          P.solid.set('uModel', function (l) { gl.uniformMatrix4fv(l, false, mats.model); });
          setColor(P.solid, AXIS_COLOR);
          gl.bindVertexArray(geom.axis);
          gl.drawArrays(gl.LINES, 0, geom.axisCount);
        }
      }

      gl.bindVertexArray(null);
      gl.depthMask(true);
      gl.enable(gl.DEPTH_TEST);
      gl.disable(gl.BLEND);
      return {
        planeDraws: opaqueList.length + transList.length,
        pointDraws: ui.otherMode === 'points' ? countPoints(R) : 0
      };
    }

    function countPoints(R) {
      var n = 0;
      for (var i = 0; i < R.items.length; i++) {
        if (R.items[i].pointCloud && R.items[i].vao) n += R.items[i].count;
      }
      return n;
    }

    function drawPlanes(list, writeDepth, ui) {
      if (!list.length) return;
      gl.depthMask(!!writeDepth);
      for (var i = 0; i < list.length; i++) {
        var it = list[i];
        /*
         * 照片画在**薄片的中面**上（薄片 = [z-d/2, z+d/2]）。
         * 薄片的正面边界就是 z+d/2，中面才是"这张照片在时间轴上的位置"，
         * 点云也是画在 z 上的 —— 两者必须一致，否则切到点云时整层会平移。
         */
        STC.math.modelMat(it.w, it.h, 1, [0, 0, it.z], mats.model);
        P.plane.set('uModel', function (l) { gl.uniformMatrix4fv(l, false, mats.model); });
        P.plane.set('uOpacity', function (l) { gl.uniform1f(l, it.opacity); });
        // 纹理缺失时不静默采到默认白纹理，而是让着色器画成品红 —— 故障可见
        P.plane.set('uHasTex', function (l) { gl.uniform1i(l, it.texture ? 1 : 0); });
        /*
         * 轮廓模式：只保留"对比鲜明的颜色分界线"，内部整片 discard。
         * uTexel 是 1/纹理尺寸，着色器用它兜住采样步长的下限（见 PLANE_FS 注释）。
         */
        P.plane.set('uOutline', function (l) { gl.uniform1i(l, ui.outline ? 1 : 0); });
        P.plane.set('uEdgeThreshold', function (l) { gl.uniform1f(l, ui.edgeThreshold); });
        /*
         * 切割：选区外的片元在着色器里直接丢弃。
         * uClip = (x0, y0, x1, y1)，归一化 uv（v=0 是图像顶部）。
         * 这里不做任何"裁剪几何"的花样 —— 几何还是那一整个四边形，
         * 只是不在选区内的片元不画，所以照片本身没有被修改。
         */
        P.plane.set('uClipOn', function (l) { gl.uniform1i(l, ui.clipOn ? 1 : 0); });
        P.plane.set('uClip', function (l) {
          var c = ui.clip || [0, 0, 1, 1];
          gl.uniform4f(l, c[0], c[1], c[2], c[3]);
        });
        P.plane.set('uTexel', function (l) {
          gl.uniform2f(l, it.texW > 0 ? 1 / it.texW : 1, it.texH > 0 ? 1 / it.texH : 1);
        });
        if (it.texture) gl.bindTexture(gl.TEXTURE_2D, it.texture);
        gl.bindVertexArray(geom.quad);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      }
      gl.bindVertexArray(null);
      gl.depthMask(true);
    }

    /**
     * 这一帧的挤出厚度。
     * 用户设定的厚度是"每帧一份"，但因帧距而异：帧距小的时候若还是满厚度，
     * 相邻帧会互相穿插。所以这里夹到帧距的 90%，保证永远不会穿模。
     */
    /**
     * 诊断用的四张 1×1 纯色纹理：红=左、绿=右、蓝=上、黄=下。
     * 打开 `?banddebug=1`（或 STC.app.setBandDebug(true)）时，四个立面直接涂成
     * 这四种颜色 —— "某个侧面到底有没有画出来"就不再依赖照片本身的边缘颜色。
     * 在 build() 里一次建好：只有 4 个像素，换来的是渲染路径上没有任何分支/懒加载。
     */
    function buildDebugTextures() {
      var colors = [[255, 40, 40], [40, 220, 40], [60, 120, 255], [255, 210, 40]];
      geom.debugTex = colors.map(function (c) {
        return ctx.edgeTexture(1, 1, new Uint8Array([c[0], c[1], c[2], 255]), gl.NEAREST);
      });
    }

    function thicknessOf(it, ui) {
      var want = (ui && ui.thickness) || 0;
      if (want <= 0) return 0;
      var step = it.frameStep || 0;
      if (step <= 0) return want;
      return Math.min(want, step * 0.9);
    }

    return {
      gl: gl,
      build: build,
      programs: P,
      geom: geom,
      uploadFrame: uploadFrame,
      releaseFrames: releaseFrames,
      buildPoints: buildPoints,
      dropPoints: dropPoints,
      buildEdgeAtlas: buildEdgeAtlas,
      releaseEdgeTextures: releaseEdgeTextures,
      render: render
    };
  }

  STC.renderer = { create: create };
})(window.STC = window.STC || {});
