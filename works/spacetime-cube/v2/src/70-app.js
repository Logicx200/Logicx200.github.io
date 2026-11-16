/* 时空立方体 · 主程序
 *
 * 数据流：
 *   文件 → 排序（EXIF 拍摄时间优先）→ 原画质解码 → ImageBitmap
 *        → 纹理（按需上传，先上传最可能马上要看的帧）
 *        → 逐帧沿 Z 轴摆到 z_i = i * step，第一帧在 z=0（前表面）
 *        → 侧面颜色条由「边界像素图集」提供
 *
 * 三个滑块/开关分别对应：
 *   帧滑块        —— 哪一帧是「当前帧」（它按 opCur 显示）
 *   其他帧不透明度 —— 非当前帧的不透明度（半透明平面，或者点云）
 *   全部半透明     —— 取消「当前帧」的特殊地位，所有帧同一个不透明度
 */
(function (STC) {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };

  var state = {
    seq: null,
    files: null,
    frame: 0,
    allGhost: false,
    opCur: 1.0,
    opOther: 0.12,
    otherMode: 'plane',
    edgeMode: 'edge',
    /* 厚度条（每张薄片的四个立面）的开关。关掉时连图集一起释放，省显存。 */
    showBands: true,
    /* 诊断：把四个立面涂成红/绿/蓝/黄，用来确认"四个面都画出来了" */
    bandDebug: false,
    /* 每帧的挤出厚度（世界单位）。0 = 没有厚度、侧面是零宽的线。
       有了厚度，正视图里也能看到侧面那条颜色带。 */
    thickness: 0.02,
    /* 帧距：cube 在时间轴上的总深度（世界单位）。越大帧之间越散、轨迹拉得越长。 */
    spacing: 1.6,
    /* 点云的密度加权：参与密度的量越大，保留的点越多。
       lumDir='bright' → 亮处密；'dark' → 暗处密（用户两种都要）。 */
    lumWeight: 0.85,
    lumThreshold: 0.02,
    lumDir: 'bright',
    dotSize: 5,
    square: true,
    nearest: false,
    showFrameOutline: false,   // 默认关闭 —— 200 帧时它会把画面叠成一片白
    showCube: true,
    showAxis: true,
    sort: 'exif',
    lastSort: 'exif',
    /* 分辨率策略：
     *   'auto'  → 按预算与帧数自动解一个长边，保证全部帧都能装下
     *   'orig'  → 不缩放（帧数多时会撞预算，程序会如实报告装到第几帧）
     *   '960'/'1280'/'1920' → 固定长边
     * 这是显存硬约束下必须由用户做的选择，不是可以替他默认的。 */
    resMode: 'auto',
    /* 视频抽帧：1 = 每一帧都保留（默认）。2/3/5 = 每 N 个呈现帧保留 1 个。
       默认必须是 1 —— 用户要的就是"每一帧都留"。 */
    videoStep: 1,
    /* 轮廓模式：只保留"对比鲜明的颜色分界线"，内部整片丢弃。
       edgeThreshold 是逐通道最大差的门槛（0..1）。 */
    outline: false,
    edgeThreshold: 0.25,
    /* 切割：只显示选区内的影像。
       clipRect 用**归一化 uv** 存（v=0 是图像顶部），所以对所有帧都生效；
       选区是在某一张照片上框出来的（见 openCrop），但作用范围是整个立方体。 */
    clip: false,
    clipRect: { x0: 0, y0: 0, x1: 1, y1: 1 },
    busy: false,
    signal: { cancelled: false },
    loadError: null
  };

  var cam = {
    az: 32, el: 20, dist: 1, zoom: 1, panU: 0, panV: 0,
    fov: STC.math.deg(40)
  };

  var DEFAULT_VIEW = { az: 32, el: 20, zoom: 1, panU: 0, panV: 0 };

  var glCtx = null, R = null, canvas = null;
  var viewport = { w: 1, h: 1, dpr: 1 };

  /* ============================================================== 初始化 */

  function boot() {
    canvas = $('view');
    armFatalDismiss();

    /*
     * 这个顺序是刻意的：**先做输入，再做渲染**。
     *
     * 之前的顺序是「WebGL 初始化 → bindUI() → resize()」，中间任何一步抛异常，
     * 后面的 bindUI() 就不会执行 —— 结果是拖放监听不存在（浏览器于是把拖入的
     * 文件当链接打开，一次开出上百个标签页），切换控件的监听也全部缺失。
     * 一个渲染层的小问题，把整个交互层一起拖垮了。
     *
     * 现在交互绑定放在最前、并且各自 try 住，无论如何输入都是通的。
     */
    try {
      bindUI();
    } catch (e) {
      appendFatal('界面事件绑定失败（部分控件可能无响应）：' + (e && e.message || e) +
        '\n\n' + (e && e.stack || ''));
    }

    try {
      resize();
    } catch (e) {
      appendFatal('画布尺寸初始化失败：' + (e && e.message || e));
    }

    try {
      window.addEventListener('resize', resize);
      // 窗口尺寸变了，框选面板里那块画布的显示尺寸也会变 —— 选区框要跟着重新贴上去
      window.addEventListener('resize', function () { if (cropDraft) cropLayout(); });
      window.addEventListener('keydown', onKey);
    } catch (e) { /* 忽略：这两个不是关键路径 */ }

    var glError = null;
    try {
      glCtx = STC.gl.create(canvas);
      R = STC.renderer.create(glCtx, canvas);
      if (!R.build()) {
        glError = '着色器编译/链接失败，画面不会正常显示。\n\n' + glCtx.errors.join('\n\n');
      }
    } catch (e) {
      glError = 'WebGL 初始化失败：' + (e && e.message || e) + '\n\n' + (e && e.stack || '');
    }
    if (glError) {
      fatal(glError);
      return;
    }

    try {
      var q = new URLSearchParams(location.search);
      if (q.get('hold') === '1') document.body.dataset.hold = '1';
      // ?banddebug=1：四个立面涂成红/绿/蓝/黄，用来确认它们都画出来了
      if (q.get('banddebug') === '1') state.bandDebug = true;
      if (q.get('bands') === '0') state.showBands = false;
      if (q.get('demo')) {
        loadPaths(parseDemo(q.get('demo'), parseInt(q.get('n') || '0', 10)));
      } else {
        status('拖入一批照片，或点「打开照片」' + hintLimits());
      }
      loop();
    } catch (e) {
      fatal('启动收尾阶段失败：' + (e && e.message || e) + '\n\n' + (e && e.stack || ''));
    }
  }

  function hintLimits() {
    return '　（单张纹理上限 ' + glCtx.info.maxTextureSize + '×' + glCtx.info.maxTextureSize +
      '，纹理预算 ' + Math.round(STC.seq.RAM_BUDGET / 1048576) + ' MB）';
  }

  function fatal(msg) {
    var el = $('fatal');
    fatalText = msg;
    el.textContent = msg;
    el.setAttribute('title', msg);
    showFatal();
    veil(false);
    status('启动失败');
  }

  function status(s) { $('status').textContent = s; }

  /* ============================================================== 相机 */
  /* 真正的计算在 55-view.js 里（纯函数，Node 里可逐值断言）；
     这里只负责把当前的几何/相机/视口喂进去。 */

  function camParams() {
    var geo = state.seq ? state.seq.geo : { planeW: 1, planeH: 1, depth: 1.6 };
    return STC.view.camParams(geo, cam, viewport);
  }

  function applyView(name) {
    if (name === 'front') { cam.az = 0; cam.el = 0; cam.zoom = 1; cam.panU = cam.panV = 0; }
    else if (name === 'iso') { cam.az = DEFAULT_VIEW.az; cam.el = DEFAULT_VIEW.el; cam.zoom = 1; cam.panU = cam.panV = 0; }
    else if (name === 'top') { cam.az = 0; cam.el = 88; cam.zoom = 1; cam.panU = cam.panV = 0; }
    else if (name === 'reset') { cam.az = DEFAULT_VIEW.az; cam.el = DEFAULT_VIEW.el; cam.zoom = DEFAULT_VIEW.zoom; cam.panU = cam.panV = 0; }
    segOn('viewMode', name === 'reset' ? 'iso' : name);
  }

  /* ============================================================== 每帧解算 */

  function resolve(seq, ui, cur) {
    return STC.view.resolve(seq, ui, cur);
  }

  /* ========================================================== 纹理上传 */
  /*
   * 纹理是**按需**上传的，但最终必须把全部帧都传完 ——
   * 否则没传到的帧会拿不到纹理，在 WebGL 里采样成纯白（或品红）。
   * 所以这里分成两段：
   *   1. ensureFrames(near) —— 优先把当前帧附近传好，保证立刻有画可看；
   *   2. 后台渐进循环 —— 有空就把剩下的补上，并且随着你拖滑块不断重新排序，
   *      始终优先保证"当前看得到的那些帧"是齐的。
   * 每传几张就让出主线程，否则几百张图会把页面卡死。
   */
  var uploadGen = 0;
  var uploadWant = 0;
  var uploadRunning = false;

  /** 按到 want 的距离排出上传顺序（近的优先） */
  function uploadOrder(seq, want) {
    var order = [];
    var n = seq.frames.length;
    for (var d = 0; d < n; d++) {
      if (want - d >= 0) order.push(want - d);
      if (d > 0 && want + d < n) order.push(want + d);
    }
    return order;
  }

  /**
   * 把离 want 最近的若干帧传好。
   * @param {number} want 目标帧
   * @param {number} limit 最多传多少帧（传 Infinity 表示全部）
   */
  async function ensureFrames(want, limit) {
    var seq = state.seq;
    if (!seq) return 0;
    var order = uploadOrder(seq, want);
    var max = limit === undefined ? Infinity : limit;
    var done = 0;
    for (var k = 0; k < order.length && done < max; k++) {
      if (state.signal.cancelled) break;
      var f = seq.frames[order[k]];
      if (!f.texture && !f.textureFailed && f.bitmap) {
        R.uploadFrame(f, state.nearest ? 'nearest' : 'linear');
        done++;
        if (done % 4 === 0) { hud(); await tick(); }
      }
    }
    hud();
    return done;
  }

  /**
   * 后台把剩余帧补齐。它是**幂等且可重入**的：重复调用只会更新"优先目标"，
   * 不会叠加多个循环；换新序列时 uploadGen 一变，旧循环自己退出。
   */
  async function uploadRemaining() {
    uploadWant = state.frame;
    if (uploadRunning) return;
    uploadRunning = true;
    var gen = uploadGen;
    try {
      while (gen === uploadGen && !state.signal.cancelled && state.seq) {
        // 每次重新取一遍顺序：用户拖了滑块，优先目标就跟着变
        var want = uploadWant;
        var moved = await ensureFrames(want, 8);
        if (moved === 0 && want === uploadWant) break;   // 这一轮没得传了，收工
        await tick();
      }
    } finally {
      if (gen === uploadGen) uploadRunning = false;
    }
    hud();
  }

  function cancelUploads() { uploadGen++; uploadRunning = false; }

  function tick() { return new Promise(function (r) { setTimeout(r, 0); }); }

  /* ============================================================== 渲染 */

  function frame() {
    if (!state.seq || !R) return;
    var cur = Math.min(state.frame, state.seq.frames.length - 1);
    var res = resolve(state.seq, state, cur);
    var cp = camParams();
    var out = R.render({
      seq: state.seq, resolved: res, cam: cp,
      proj: cp.proj, view: cp.view,
      projOrtho: cp.ortho, pointScale: cp.scale,
      viewport: viewport,
      ui: {
        otherMode: state.otherMode, edgeMode: state.edgeMode,
        showBands: state.showBands, bandDebug: state.bandDebug,
        dotSize: state.dotSize, square: state.square,
        thickness: state.thickness,
        lumWeight: state.lumWeight, lumThreshold: state.lumThreshold,
        lumDir: state.lumDir,
        outline: state.outline, edgeThreshold: state.edgeThreshold,
        clipOn: state.clip, clip: clipVec4(),
        showFrameOutline: state.showFrameOutline,
        showCube: state.showCube, showAxis: state.showAxis
      }
    });
    lastStats = { res: res.stats, out: out, cam: cp };
    hud();
  }

  var lastStats = null;
  var rafPending = false;
  var running = true;

  function loop() {
    if (!running) return;
    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(function () { rafPending = false; frame(); });
    }
    requestAnimationFrame(loop);
  }

  /** 停掉渲染循环。浏览器里用不到，Node 自检必须调它，否则事件循环永不退出。 */
  function stop() {
    running = false;
  }

  function invalidate() {
    // 下一帧 rAF 自然会重画；这里把状态暴露到 DOM 上，供无头自检读取
    document.body.dataset.frame = String(state.frame);
    document.body.dataset.renderTick = String(++renderTick);
    // 用户换了帧：让后台上传循环把优先目标跟过去
    uploadWant = state.frame;
  }

  var renderTick = 0;

  function hud() {
    if (!lastStats || !state.seq) { $('hud').textContent = ''; return; }
    var s = lastStats.res, o = lastStats.out;
    var mem = 0;
    var uploaded = 0;
    for (var i = 0; i < state.seq.frames.length; i++) {
      if (state.seq.frames[i].texture) { mem += state.seq.frames[i].bytes; uploaded++; }
    }
    var pts = 0;
    for (var j = 0; j < state.seq.frames.length; j++) {
      if (state.seq.frames[j].pointVao) pts += state.seq.frames[j].pointVao.count;
    }
    var bits = [
      '帧 ' + (state.frame + 1) + '/' + s.total,
      '已上传 ' + uploaded + '/' + s.total + ' 帧（' + (mem / 1048576).toFixed(1) + ' MB 显存）',
      '不透明 ' + s.opaque + ' · 半透明 ' + s.ghost + ' · 点云 ' + (pts / 1e6).toFixed(2) + 'M 点',
      '侧面 ' + (state.seq.edgeBytes ? (state.seq.edgeBytes / 1048576).toFixed(1) + ' MB' : '关闭'),
      '绘制 ' + o.planeDraws + ' 次平面 + ' + (o.pointDraws ? '1 次点云实例' : '0')
    ];
    // 切割生效时把选区也写在画面上 —— 否则"画面缺了一块"会像故障
    if (state.clip) bits.push('切割 ' + Math.round(STC.view.clipArea(state.clipRect) * 100) + '%');
    $('hud').textContent = bits.join('  ·  ');
    clipInfoTick();
  }

  /**
   * 面板里那行选区说明要跟着**当前帧**走（它显示的是"本帧约多少像素"）。
   * 只在有选区时更新，并且只在文本真的变了才写 DOM —— 它每帧都会被调到。
   */
  function clipInfoTick() {
    var el = $('clipInfo');
    if (!el) return;
    if (STC.view.clipIsFull(state.clipRect) && el.textContent === '选区：整个画面（未切割）') return;
    var t = clipInfoText();
    if (el.textContent !== t) el.textContent = t;
  }

  /* ============================================================== 尺寸 */

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var w = Math.max(1, Math.round(canvas.clientWidth * dpr));
    var h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    viewport = { w: w, h: h, dpr: dpr };
    if (document.body) document.body.dataset.viewport = w + 'x' + h;
  }

  /* ============================================================== 加载 */

  function parseDemo(spec, n) {
    // 支持 ?demo=./sample/frame_%03d.png&n=24  或  ?demo=a.jpg,b.jpg
    if (spec.indexOf(',') >= 0) return spec.split(',').map(trim).filter(Boolean);
    if (spec.indexOf('%') >= 0) {
      var pad = /%0?(\d+)d/.exec(spec);
      var width = pad ? parseInt(pad[1], 10) : 3;
      var out = [];
      var count = n > 0 ? n : 24;
      for (var i = 0; i < count; i++) {
        out.push(spec.replace(/%0?\d+d/, String(i).padStart(width, '0')));
      }
      return out;
    }
    return [spec];
  }

  function trim(s) { return s.trim(); }

  /** 从一批 URL 加载（用于无头自检与示例；日常用不到） */
  async function loadPaths(paths) {
    if (state.busy) return;
    veil(true, '正在读取 ' + paths.length + ' 张照片…', 0);
    try {
      var files = [];
      for (var i = 0; i < paths.length; i++) {
        var resp = await fetch(paths[i]);
        if (!resp.ok) throw new Error(paths[i] + ' → HTTP ' + resp.status);
        var blob = await resp.blob();
        files.push(new File([blob], paths[i].split('/').pop(), { type: blob.type }));
      }
      await ingest(files);
    } catch (e) {
      veil(false);
      fatal('加载示例失败：' + (e && e.message || e) + '\n' +
        '（file:// 下 fetch 会被浏览器拦掉，请用本地服务打开。）');
    }
  }

  async function loadFiles(files) {
    if (state.busy) return;
    state.files = Array.from(files);
    await ingest(state.files);
  }

  async function ingest(files) {
    state.busy = true;
    state.signal = { cancelled: false };
    state.loadError = null;
    clearFatal();
    resetSeq();

    var t0 = performance.now();
    // 抽帧速度的滚动估计（400ms 窗口），用来显示"帧/秒"和"约还需几秒"
    var videoRate = 0;
    var videoRateMark = { t: 0, frames: 0 };
    veil(true, '正在排序…', 0);
    try {
      var resOpt = { longEdge: 0, autoLongEdge: false };
      if (state.resMode === 'auto') resOpt.autoLongEdge = true;
      else if (state.resMode !== 'orig') resOpt.longEdge = parseInt(state.resMode, 10) || 0;

      var seq = await STC.seq.load(files, {
        sort: state.sort,
        maxTextureSize: glCtx.info.maxTextureSize,
        budget: STC.seq.defaultBudget(),
        longEdge: resOpt.longEdge,
        autoLongEdge: resOpt.autoLongEdge,
        videoStep: state.videoStep,
        depthRatio: state.spacing,
        signal: state.signal,
        onProgress: function (p) {
          if (p.phase === 'exif') {
            veil(true, '正在读取拍摄时间… ' + p.done + '/' + p.total, p.done / p.total * 0.2);
          } else if (p.phase === 'measure') {
            veil(true, '正在确定序列尺寸…', 0.2);
          } else if (p.phase === 'video-meta') {
            veil(true, '正在读取视频信息… ' + (p.done + 1) + '/' + p.total, 0.2);
          } else if (p.phase === 'video-probe') {
            veil(true, '正在探测视频帧率… ' + (p.name || ''), 0.22);
          } else if (p.phase === 'video') {
            /*
             * 抽帧按"处理能力"推进：跟不上就自动降速（必要时暂停），
             * 所以可能要花得比视频时长更久 —— 进度里要给出速度和预计剩余时间，
             * 否则用户会以为卡死了。
             */
            var frac = p.duration > 0 ? Math.min(1, p.time / p.duration) : 0;
            var mm = Math.floor(p.time / 60), ss = (p.time % 60).toFixed(1);
            var now = performance.now();
            if (videoRateMark.t !== now || !videoRateMark.frames) { /* 首次 */ }
            if (videoRateMark.frames && now > videoRateMark.t + 400 && p.frames > videoRateMark.frames) {
              videoRate = (p.frames - videoRateMark.frames) / ((now - videoRateMark.t) / 1000);
              videoRateMark = { t: now, frames: p.frames };
            } else if (!videoRateMark.frames) {
              videoRateMark = { t: now, frames: p.frames };
            }
            var eta = '';
            if (videoRate > 0.2 && p.seen > 0 && p.duration > 0) {
              var remainFrames = Math.max(0, Math.round(p.duration * (p.seen / Math.max(p.time, 0.001)) * (1 / (p.keepEvery || 1))) - p.frames);
              if (isFinite(remainFrames) && remainFrames > 0) eta = '　约还需 ' + Math.ceil(remainFrames / videoRate) + ' 秒';
            }
            var slow = p.playbackRate && p.playbackRate < 0.99
              ? '　跟不上，已降到 ' + p.playbackRate.toFixed(2) + '× 速度（保帧优先）' : '';
            veil(true, '正在抽取视频帧 ' + (p.name || '') + '　' +
              (mm > 0 ? mm + '分' : '') + ss + ' 秒 / ' +
              (p.duration > 0 ? p.duration.toFixed(1) + ' 秒' : '?') +
              '　已抓 ' + p.frames + ' 帧（呈现 ' + p.seen + '）' +
              (videoRate > 0.2 ? '　' + videoRate.toFixed(1) + ' 帧/秒' : '') + eta + slow,
              0.25 + frac * 0.55, true);
          } else {
            veil(true, '正在解码 ' + p.done + '/' + p.total, 0.2 + p.done / p.total * 0.6);
          }
        }
      });
      state.seq = seq;
      state.frame = 0;
      // 统一用第一帧的宽高比（按短边对齐后不拉伸），其余帧保持各自原始纹理
      seq.geo = STC.seq.layout(1, seq.baseH / seq.baseW, seq.frames.length, state.spacing);
      $('frame').max = String(seq.frames.length - 1);
      $('frame').disabled = false;
      $('frame').value = '0';
      $('lbFrame').textContent = '1 / ' + seq.frames.length;
      $('lbThick').textContent = thickText(state.thickness);   // 有了照片宽度才能换算成像素
      document.body.dataset.frames = String(seq.frames.length);
      document.body.dataset.baseSize = seq.baseW + 'x' + seq.baseH;
      document.body.dataset.origSize = seq.origW + 'x' + seq.origH;
      document.body.dataset.scaled = seq.scaled ? '1' : '0';

      veil(true, '正在上传纹理…', 0.8);
      // 先把当前帧附近的传好，保证立刻有画可看；剩下的交给后台补齐
      await ensureFrames(0, 24);
      uploadRemaining();

      if (state.showBands && state.edgeMode !== 'off') {
        veil(true, '正在生成厚度条…', 0.85);
        await tick();
        R.buildEdgeAtlas(seq, state.edgeMode, function (p) {
          veil(true, '正在生成厚度条 ' + p.done + '/' + p.total, 0.85 + p.done / p.total * 0.15);
        });
      }
      if (state.otherMode === 'points') await ensurePoints();

      // 点云密度
      var stride = STC.seq.pointStride(seq.frames, STC.seq.POINT_BUDGET);
      document.body.dataset.stride = String(stride);
      document.body.dataset.edgeMode = state.edgeMode;
      document.body.dataset.textureBytes = String(seq.bytes);

      veil(false);
      var ms = Math.round(performance.now() - t0);
      var resNote = seq.scaled
        ? '每帧 ' + seq.baseW + '×' + seq.baseH + '（原图 ' + seq.origW + '×' + seq.origH +
          ' → 长边缩到 ' + seq.longEdge + (seq.autoChosen ? '，自动适配' : '') + '）'
        : '每帧 ' + seq.baseW + '×' + seq.baseH + '（原画质，未缩放）';
      var vidNote = '';
      if (seq.video && seq.video.length) {
        for (var vk = 0; vk < seq.video.length; vk++) {
          var vv = seq.video[vk];
          vidNote += '　· 视频 ' + vv.name + '：' + vv.duration.toFixed(1) + ' 秒 → ' +
            vv.kept + ' 帧' + (vv.keepEvery > 1 ? '（每 ' + vv.keepEvery + ' 帧取 1，' : '（') +
            '呈现 ' + vv.seen + ' 帧' + (vv.dropped ? '，丢 ' + vv.dropped : '') + '）';
        }
      }
      status('已载入 ' + seq.frames.length + ' 帧 · ' + resNote + ' · ' +
        (seq.bytes / 1048576).toFixed(1) + ' MB 显存 · 用时 ' + ms + ' ms' + vidNote);
      if (seq.notes && seq.notes.length) {
        appendFatal('视频抽帧提示：\n' + seq.notes.join('\n\n'));
      }
      if (seq.failed && seq.failed.length) {
        appendFatal('以下内容被跳过：\n' + seq.failed.join('\n'));
      }
      if (seq.trimmed) appendFatal('帧数超过 ' + STC.seq.MAX_FRAMES + '，等间隔抽稀掉了 ' + seq.trimmed + ' 帧。');
      if (seq.budgetHit) {
        var bh = seq.budgetHit;
        appendFatal('显存预算已满：载入到第 ' + bh.at + '/' + bh.total +
          ' 帧时停止（已用 ' + bh.usedMB + ' MB，本帧还需 ' + bh.needMB +
          ' MB，预算 ' + bh.budgetMB + ' MB）。\n\n' +
          (bh.kind === 'video'
            ? '这个视频估计共 ' + bh.estimate + ' 帧，按当前分辨率只装得下 ' + (bh.kept || bh.at) +
              ' 帧。要留住整段，请把「视频抽帧」改成「每 2 / 3 / 5 帧取 1」，' +
              '或把顶栏「分辨率」改成更低的值。'
            : '相册有 ' + seq.requested + ' 帧，全都要的话请把顶栏的「分辨率」改成' +
              '「自动适配」或固定的 1920 / 1280 / 960 —— ' +
              '或者保持原画质、分两批做。') +
          '\n程序不会背着你压缩像素，也不会替你丢帧。');
      }
      if (seq.noExif) {
        status($('status').textContent + '　（' + seq.noExif + ' 张没有 EXIF 拍摄时间，按文件名排在其后）');
      }
      // 换了序列：选区可能已经退化成"整幅"（例如整批照片换了尺寸），面板要跟着刷新
      refreshClipUI();
      applyView('iso');
      invalidate();
    } catch (e) {
      veil(false);
      var msg = String(e && e.message || e);
      if (msg.indexOf('已取消') < 0) fatal('载入失败：\n' + msg);
    } finally {
      state.busy = false;
    }
  }

  function resetSeq() {
    cancelUploads();
    if (state.seq) {
      R.releaseFrames(state.seq.frames);
      R.releaseEdgeTextures(state.seq);
      state.seq = null;
    }
  }

  /** 惰性建点云缓冲；只对「会被显示的点云帧」建 */
  async function ensurePoints() {
    var seq = state.seq;
    if (!seq) return;
    var stride = STC.seq.pointStride(seq.frames, STC.seq.POINT_BUDGET);
    for (var i = 0; i < seq.frames.length; i++) {
      var f = seq.frames[i];
      if (f.pointVao) continue;
      if (!f.texture) R.uploadFrame(f, state.nearest ? 'nearest' : 'linear');
      R.buildPoints(f, stride);
      if (i % 2 === 1) {
        veil(true, '正在建点云 ' + (i + 1) + '/' + seq.frames.length, (i + 1) / seq.frames.length * 0.15);
        await tick();
      }
    }
  }

  function dropAllPoints() {
    if (!state.seq) return;
    for (var i = 0; i < state.seq.frames.length; i++) R.dropPoints(state.seq.frames[i]);
  }

  function rebuildEdgeAtlas(mode) {
    if (!state.seq) return;
    state.edgeMode = mode;
    if (mode === 'off') {
      R.releaseEdgeTextures(state.seq);
      document.body.dataset.edgeMode = 'off';
      return;
    }
    veil(true, '正在生成厚度条…', 0);
    setTimeout(function () {
      R.buildEdgeAtlas(state.seq, mode, function (p) {
        veil(true, '正在生成厚度条 ' + p.done + '/' + p.total, p.done / p.total);
      });
      document.body.dataset.edgeMode = mode;
      veil(false);
    }, 0);
  }

  /**
   * 厚度条总开关。关掉时连图集一起释放；重新打开时按当前模式重建。
   * @param {boolean} on
   */
  function setBands(on) {
    state.showBands = !!on;
    if ($('showBands')) $('showBands').checked = state.showBands;
    document.body.dataset.showBands = state.showBands ? '1' : '0';
    if (!state.seq) { invalidate(); return; }
    if (state.showBands) {
      rebuildEdgeAtlas(state.edgeMode === 'off' ? 'edge' : state.edgeMode);
    } else {
      R.releaseEdgeTextures(state.seq);
      document.body.dataset.edgeMode = 'off';
    }
    invalidate();
  }

  /* ============================================================== 遮罩 */

  function veil(on, text, frac, cancellable) {
    var v = $('veil');
    var c = $('veilCancel');
    if (on) {
      v.classList.add('on');
      if (text) $('veilText').textContent = text;
      $('veilBar').style.width = Math.round((frac || 0) * 100) + '%';
      if (c) c.style.display = cancellable ? '' : 'none';
    } else {
      $('veilBar').style.width = '100%';
      v.classList.remove('on');
      if (c) c.style.display = 'none';
    }
  }

  /*
   * 提示条：显示 3 秒后渐隐消失。
   *
   * 之所以要有这个：视频抽帧那类提示（丢帧、降速、抽稀）**是必然会出现的**
   * —— 丢帧在多任务系统里无法完全避免 —— 如果一直挂在画面上，用户每次都要
   * 手动去关，最后就变成"永远有一块红字挡着"。
   * 所以：显示 3 秒 → 0.9 秒淡出 → 不再占位；想看完整内容点一下它就会再显示 3 秒
   * （完整文本同时留在 title 里，鼠标悬停也能看到）。
   */
  var FATAL_HOLD_MS = 3000;
  var fatalTimer = null;
  var fatalFadeTimer = null;

  function appendFatal(msg) {
    var el = $('fatal');
    if (!el) return;
    var text = (el.textContent ? el.textContent + '\n\n' : '') + msg;
    fatalText = text;
    el.textContent = text;
    el.setAttribute('title', text);
    showFatal();
  }

  function showFatal() {
    var el = $('fatal');
    if (!el || !fatalText) return;
    el.classList.add('on');
    el.classList.remove('out');
    if (fatalTimer) clearTimeout(fatalTimer);
    if (fatalFadeTimer) clearTimeout(fatalFadeTimer);
    fatalTimer = setTimeout(function () {
      el.classList.add('out');
      // 淡出结束后彻底不占位（pointer-events 已在 CSS 里关掉）
      fatalFadeTimer = setTimeout(function () { el.classList.remove('on'); }, 1000);
    }, FATAL_HOLD_MS);
  }

  function armFatalDismiss() {
    var el = $('fatal');
    if (!el) return;
    el.addEventListener('click', function () { showFatal(); });
  }

  /** 清掉提示（换一批照片时用） */
  function clearFatal() {
    var el = $('fatal');
    if (fatalTimer) clearTimeout(fatalTimer);
    if (fatalFadeTimer) clearTimeout(fatalFadeTimer);
    fatalText = '';
    if (el) {
      el.textContent = '';
      el.classList.remove('on');
      el.classList.remove('out');
    }
  }

  var fatalText = '';

  /* ============================================== 切割（选区）与框选面板 */

  /** 提交给着色器的选区向量 (x0,y0,x1,y1)；关掉切割时也照传，着色器用 uClipOn 判断 */
  function clipVec4() {
    var c = STC.view.normalizeClip(state.clipRect);
    return [c.x0, c.y0, c.x1, c.y1];
  }

  /** 当前这一帧的像素尺寸（用来把归一化选区显示成"选了多少像素"） */
  function clipFrameSize() {
    if (!state.seq || !state.seq.frames.length) return null;
    var f = state.seq.frames[Math.min(state.frame, state.seq.frames.length - 1)];
    if (!f || !f.width) return null;
    return { w: f.width, h: f.height, name: f.name };
  }

  function clipInfoText() {
    var c = STC.view.normalizeClip(state.clipRect);
    if (STC.view.clipIsFull(c)) return '选区：整个画面（未切割）';
    var pct = Math.round(STC.view.clipArea(c) * 100);
    var fs = clipFrameSize();
    var px = fs
      ? '，本帧约 ' + Math.round((c.x1 - c.x0) * fs.w) + '×' + Math.round((c.y1 - c.y0) * fs.h) +
        ' 像素 @ (' + Math.round(c.x0 * fs.w) + ', ' + Math.round(c.y0 * fs.h) + ')'
      : '';
    return '选区：画面面积的 ' + pct + '%' + px;
  }

  function refreshClipUI() {
    var info = $('clipInfo');
    if (info) info.textContent = clipInfoText();
    var box = $('clip');
    if (box) {
      box.checked = !!state.clip;
      // 选区就是整幅画面时，勾上也没有任何效果 —— 直接置灰，避免"我勾了却没变化"
      var full = STC.view.clipIsFull(state.clipRect);
      box.disabled = full;
      box.parentNode && box.parentNode.classList &&
        box.parentNode.classList.toggle('dim', full);
    }
    var edit = $('clipEdit');
    if (edit) edit.textContent = STC.view.clipIsFull(state.clipRect) ? '框选区域…' : '重新框选…';
    var all = $('clipAll');
    if (all) all.disabled = STC.view.clipIsFull(state.clipRect);
    document.body.dataset.clip = state.clip ? '1' : '0';
  }

  /**
   * 设置选区（唯一入口）。
   * @param {object} r 归一化选区（任意方向都会被规整）
   * @param {boolean} [on] 是否同时打开切割；省略则保持当前开关
   */
  function setClipRect(r, on) {
    var c = STC.view.normalizeClip(r);
    var fs = clipFrameSize();
    // 至少留 1 像素，否则会出现"整幅都看不见"这种看起来像 bug 的状态
    state.clipRect = fs ? STC.view.clipAtLeastOnePixel(c, fs.w, fs.h) : c;
    if (on !== undefined) state.clip = !!on;
    if (STC.view.clipIsFull(state.clipRect)) state.clip = false;
    refreshClipUI();
    invalidate();
  }

  function clearClip() { setClipRect({ x0: 0, y0: 0, x1: 1, y1: 1 }, false); }

  /* ---- 框选面板：在一张照片上画矩形 ---- */
  var cropDraft = null;   // { rect, back, drag:{mode,a} }

  function cropOpen() {
    var fs = state.seq && state.seq.frames.length
      ? state.seq.frames[Math.min(state.frame, state.seq.frames.length - 1)] : null;
    var box = $('crop');
    if (!fs || !fs.bitmap) { appendFatal('还没有可框选的画面：请先打开一批照片或一段视频。'); return; }
    if (!box) return;
    var cv = $('cropCanvas');
    if (cv) {
      cv.width = fs.width;
      cv.height = fs.height;
      var c2 = cv.getContext ? cv.getContext('2d') : null;
      if (c2) {
        try { c2.drawImage(fs.bitmap, 0, 0, fs.width, fs.height); }
        catch (e) { appendFatal('这张照片画不出来，无法框选：' + (e && e.message || e)); return; }
      }
    }
    cropDraft = { rect: STC.view.normalizeClip(state.clipRect), back: state.clipRect, drag: null };
    box.hidden = false;
    document.body.dataset.crop = '1';
    cropLayout();
    cropInfo();
  }

  function cropClose(apply) {
    var box = $('crop');
    if (cropDraft && apply) setClipRect(cropDraft.rect, true);
    else if (cropDraft) setClipRect(cropDraft.back, state.clip);
    cropDraft = null;
    if (box) box.hidden = true;
    document.body.dataset.crop = '0';
  }

  /**
   * 画布（照片那块区域）在屏幕上的矩形。
   *
   * **一切坐标换算都必须以它为基准** —— 外层 `#cropWrap` 是 flex 子项，
   * 默认会被拉伸到整个面板的宽度，而画布受 max-width/max-height 限制常常窄得多。
   * 早先这里用的是 wrap 的矩形，于是"拖着鼠标画出来的框"看着跟手，
   * 换算出的 uv 却整体偏小 —— 用户看到的正是**选出来的区域被挪到了画面左边**。
   */
  function cropBox() {
    var cv = $('cropCanvas');
    if (cv && cv.getBoundingClientRect) {
      var r = cv.getBoundingClientRect();
      if (r && r.width > 0 && r.height > 0) return r;
    }
    var wrap = $('cropWrap');
    if (wrap && wrap.getBoundingClientRect) return wrap.getBoundingClientRect();
    return { left: 0, top: 0, width: 400, height: 300 };
  }

  /** 把选区画到面板上（px 定位，锚在画布的真实位置上，不受外面容器宽度影响） */
  function cropLayout() {
    var el = $('cropRect');
    if (!el || !cropDraft) return;
    var wrap = $('cropWrap');
    var wr = wrap && wrap.getBoundingClientRect ? wrap.getBoundingClientRect() : { left: 0, top: 0 };
    var cb = cropBox();
    var c = cropDraft.rect;
    var x0 = c.x0 * cb.width, y0 = c.y0 * cb.height;
    el.style.left = (cb.left - wr.left + x0) + 'px';
    el.style.top = (cb.top - wr.top + y0) + 'px';
    el.style.width = Math.max(0, (c.x1 - c.x0) * cb.width) + 'px';
    el.style.height = Math.max(0, (c.y1 - c.y0) * cb.height) + 'px';
  }

  function cropInfo() {
    var el = $('cropInfo');
    if (!el || !cropDraft) return;
    var c = cropDraft.rect;
    var fs = clipFrameSize();
    var px = fs ? '　' + Math.round((c.x1 - c.x0) * fs.w) + '×' + Math.round((c.y1 - c.y0) * fs.h) +
      ' px @ (' + Math.round(c.x0 * fs.w) + ', ' + Math.round(c.y0 * fs.h) + ')' : '';
    el.textContent = c.x0 <= 0 && c.y0 <= 0 && c.x1 >= 1 && c.y1 >= 1 ? '整个画面' : (Math.round(STC.view.clipArea(c) * 100) + '%' + px);
  }

  /** 鼠标坐标 → 归一化 uv（v=0 是图像顶部，与着色器一致）；基准是**画布** */
  function cropUv(ev) {
    var r = cropBox();
    var clamp = function (x) { return x < 0 ? 0 : (x > 1 ? 1 : x); };
    return {
      u: clamp((ev.clientX - r.left) / Math.max(1, r.width)),
      v: clamp((ev.clientY - r.top) / Math.max(1, r.height))
    };
  }

  /** 手柄的命中容差：按"屏幕像素"给，换算成 uv（同样以画布为准） */
  function cropTol() {
    var r = cropBox();
    return { du: 9 / Math.max(1, r.width), dv: 9 / Math.max(1, r.height) };
  }

  function cropDown(ev) {
    if (!cropDraft) return;
    var p = cropUv(ev);
    var tol = cropTol();
    // 手柄上按下时，手柄自己决定了模式（比坐标判定更准）
    var h = ev.target && ev.target.dataset && ev.target.dataset.h;
    var mode = h || STC.view.cropHit(cropDraft.rect, p.u, p.v, tol.du, tol.dv);
    cropDraft.drag = { mode: mode, a: p };
    if (mode === 'new') cropDraft.rect = { x0: p.u, y0: p.v, x1: p.u, y1: p.v };
    if (ev.preventDefault) ev.preventDefault();
    if (ev.stopPropagation) ev.stopPropagation();
    cropLayout();
    cropInfo();
  }

  function cropMove(ev) {
    if (!cropDraft || !cropDraft.drag) return;
    var p = cropUv(ev);
    cropDraft.rect = STC.view.cropDrag(cropDraft.rect, cropDraft.drag.mode, cropDraft.drag.a, p);
    cropLayout();
    cropInfo();
    if (ev.preventDefault) ev.preventDefault();
  }

  function cropUp(ev) {
    if (!cropDraft || !cropDraft.drag) return;
    var fs = clipFrameSize();
    // 拖出来的矩形小于 1 像素时视为"没选"，保持原样而不是给一个空选区
    var c = cropDraft.rect;
    if (fs && (c.x1 - c.x0) * fs.w < 1.5 && (c.y1 - c.y0) * fs.h < 1.5) {
      cropDraft.rect = STC.view.normalizeClip(state.clipRect);
    }
    cropDraft.drag = null;
    cropLayout();
    cropInfo();
    if (ev && ev.preventDefault) ev.preventDefault();
  }

  /* ============================================================== UI */

  function segOn(id, value) {
    var box = $(id);
    if (!box) return;
    var bs = box.querySelectorAll('button');
    for (var i = 0; i < bs.length; i++) {
      bs[i].classList.toggle('on', bs[i].dataset.v === value);
    }
  }

  function bindUI() {
    /*
     * 选文件的主路径**不在这里**，也不依赖 JS：
     * index.html 里「打开照片」是一个铺满按钮的透明 <input type="file">，
     * 用户点到的就是 input 本身，浏览器原生打开对话框。
     * 这里只补两件事：接住 change 事件、以及一个键盘/程序触发的备用入口。
     */
    var fileEl = $('file');
    if (fileEl) {
      fileEl.addEventListener('change', function (e) {
        if (e.target.files && e.target.files.length) loadFiles(e.target.files);
      });
    } else {
      appendFatal('界面里缺少 id="file" 的文件选择控件，无法加载照片。');
    }

    // 备用入口：Alt+O 或代码调用。正常点击走的是 input 原生行为。
    var openEl = $('open');
    if (openEl) {
      openEl.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openPicker(); }
      });
    }

    $('sort').addEventListener('change', function (e) {
      state.sort = e.target.value;
      if (state.files) ingest(state.files);
    });

    $('res').addEventListener('change', function (e) {
      state.resMode = e.target.value;
      if (state.files) ingest(state.files);
    });

    // 视频抽帧步长：1 = 每一帧都保留（默认）
    if ($('videoStep')) {
      $('videoStep').value = String(state.videoStep);
      $('videoStep').addEventListener('change', function (e) {
        state.videoStep = Math.max(1, parseInt(e.target.value, 10) || 1);
        if (state.files) ingest(state.files);
      });
    }

    // 「取消」：抽帧是实时的，长视频必须能中途停下来
    if ($('veilCancel')) {
      $('veilCancel').addEventListener('click', function () {
        if (state.signal) state.signal.cancelled = true;
        $('veilText').textContent = '正在取消…';
      });
    }

    $('frame').addEventListener('input', function (e) {
      state.frame = parseInt(e.target.value, 10) || 0;
      $('lbFrame').textContent = (state.frame + 1) + ' / ' + (state.seq ? state.seq.frames.length : '—');
      invalidate();
    });

    $('allGhost').addEventListener('change', function (e) { state.allGhost = e.target.checked; invalidate(); });

    slider('opCur', 'lbOpCur', function (v) { state.opCur = v; invalidate(); });
    slider('opOther', 'lbOpOther', function (v) { state.opOther = v; invalidate(); });

    segOn('otherMode', state.otherMode);
    $('otherMode').addEventListener('click', async function (e) {
      var v = e.target.dataset && e.target.dataset.v;
      if (!v) return;
      state.otherMode = v;
      segOn('otherMode', v);
      if (v === 'points') {
        veil(true, '正在建点云…', 0);
        await tick();
        await ensurePoints();
        veil(false);
      } else {
        dropAllPoints();
      }
      document.body.dataset.otherMode = v;
      invalidate();
    });

    segOn('edgeMode', state.edgeMode);
    $('edgeMode').addEventListener('click', function (e) {
      var v = e.target.dataset && e.target.dataset.v;
      if (!v) return;
      state.edgeMode = v;
      segOn('edgeMode', v);
      if (state.showBands) rebuildEdgeAtlas(v);
      else document.body.dataset.edgeMode = 'off';
    });

    /*
     * 「显示厚度条」这一个开关管两件事：画不画、以及要不要留那四张图集纹理。
     * 关掉时把图集释放掉（200 帧的图集也就几 MB，但没必要占着）。
     */
    $('showBands').addEventListener('change', function (e) {
      setBands(e.target.checked);
    });

    $('bandDebug').addEventListener('change', function (e) {
      state.bandDebug = e.target.checked;
      document.body.dataset.bandDebug = state.bandDebug ? '1' : '0';
      invalidate();
    });

    // 轮廓提取：一个开关 + 一个对比门槛
    if ($('outline')) {
      $('outline').addEventListener('change', function (e) {
        state.outline = !!e.target.checked;
        document.body.dataset.outline = state.outline ? '1' : '0';
        invalidate();
      });
    }
    if ($('edge')) {
      slider('edge', 'lbEdge', function (v) { state.edgeThreshold = v; invalidate(); });
    }

    slider('dot', 'lbDot', function (v) { state.dotSize = v; invalidate(); });
    slider('thick', 'lbThick', function (v) { state.thickness = v; invalidate(); }, thickText);
    slider('spacing', 'lbSpacing', function (v) {
      state.spacing = v;
      // 帧距改了要重排几何；不重新解码，只重算 layout，所以是瞬间的
      if (state.seq) {
        state.seq.geo = STC.seq.layout(1, state.seq.baseH / state.seq.baseW,
          state.seq.frames.length, v);
      }
      invalidate();
    });
    slider('lumW', 'lbLumW', function (v) { state.lumWeight = v; invalidate(); });
    slider('lumT', 'lbLumT', function (v) { state.lumThreshold = v; invalidate(); });

    segOn('lumDir', state.lumDir);
    $('lumDir').addEventListener('click', function (e) {
      var v = e.target.dataset && e.target.dataset.v;
      if (!v) return;
      state.lumDir = v;
      segOn('lumDir', v);
      document.body.dataset.lumDir = v;
      invalidate();
    });
    document.body.dataset.lumDir = state.lumDir;
    $('square').addEventListener('change', function (e) { state.square = e.target.checked; invalidate(); });
    $('showOutline').addEventListener('change', function (e) {
      state.showFrameOutline = e.target.checked; invalidate();
    });
    $('showCube').addEventListener('change', function (e) { state.showCube = e.target.checked; invalidate(); });
    $('showAxis').addEventListener('change', function (e) { state.showAxis = e.target.checked; invalidate(); });

    /*
     * 切割：一个开关 + 一个框选面板。
     * 开关只决定"选区生不生效"，选区本身存在 state.clipRect 里（归一化 uv），
     * 所以关掉再打开不会丢掉已经框好的区域。
     */
    if ($('clip')) {
      $('clip').addEventListener('change', function (e) {
        state.clip = !!e.target.checked && !STC.view.clipIsFull(state.clipRect);
        refreshClipUI();
        invalidate();
      });
    }
    if ($('clipEdit')) $('clipEdit').addEventListener('click', function () { cropOpen(); });
    if ($('clipAll')) $('clipAll').addEventListener('click', function () { clearClip(); });

    if ($('cropOk')) $('cropOk').addEventListener('click', function () { cropClose(true); });
    if ($('cropCancel')) $('cropCancel').addEventListener('click', function () { cropClose(false); });
    if ($('cropAll')) {
      $('cropAll').addEventListener('click', function () {
        if (!cropDraft) return;
        cropDraft.rect = { x0: 0, y0: 0, x1: 1, y1: 1 };
        cropLayout();
        cropInfo();
      });
    }
    // 框选面板上的鼠标/触摸：按下 → 拖动 → 松开
    if ($('cropWrap')) {
      $('cropWrap').addEventListener('mousedown', cropDown);
      // touchstart 在元素上是非 passive 的，可以 preventDefault 阻止滚动
      $('cropWrap').addEventListener('touchstart', cropDown, { passive: false });
    }
    if ($('crop')) {
      // 监听挂在 document 上：拖到面板外面也要跟得住（否则一松手就停在边界）。
      // touchmove 在 document 上默认是 passive 的，必须显式关掉才能 preventDefault。
      document.addEventListener('mousemove', cropMove);
      document.addEventListener('mouseup', cropUp);
      document.addEventListener('touchmove', cropMove, { passive: false });
      document.addEventListener('touchend', cropUp);
      // 遮罩外面点一下 = 取消（与 Esc 一致）
      $('crop').addEventListener('mousedown', function (e) {
        if (e.target === $('crop')) cropClose(false);
      });
    }
    refreshClipUI();

    segOn('viewMode', 'iso');
    $('viewMode').addEventListener('click', function (e) {
      var v = e.target.dataset && e.target.dataset.v;
      if (!v) return;
      applyView(v);
      invalidate();
    });

    $('shot').addEventListener('click', function () {
      canvas.toBlob(function (b) {
        var a = document.createElement('a');
        a.href = URL.createObjectURL(b);
        a.download = 'space-time-cube-' + Date.now() + '.png';
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
      }, 'image/png');
    });

    bindInput();
  }

  function slider(id, labelId, cb, fmt) {
    var s = $(id);
    if (!s) return;
    // 只为同步"格式化后的显示值"而解析（例如 1.6 → "1.60"）
    var parseLabel = function (text, fallback) {
      var v = parseFloat(text);
      return isFinite(v) ? v : fallback;
    };
    var show = function (v) { $(labelId).textContent = fmt ? fmt(v) : v.toFixed(2); };
    var f = function () {
      var v = parseFloat(s.value);
      if (!isFinite(v)) return;      // 拿不到有效数字就什么都不做
      show(v);
      cb(v);
    };
    s.addEventListener('input', f);
    if (String(s.value).trim() !== '') {
      f();
    } else {
      // 元素上没有值（或值是空的）——只有显示标签可按 HTML 文本同步，
      // 状态保持代码里的默认值。**绝不把 NaN 写进状态**：
      // 它一旦进入几何，depth 会变成 null，整条渲染链路静默失效。
      var fallback = parseLabel($(labelId).textContent, null);
      if (fallback !== null) show(fallback);
    }
  }

  /**
   * 帧厚度的显示文案。
   * 厚度是"占照片宽度的比例"，光看 0.020 没有直觉，所以同时给出两个换算法：
   *   ≈N px  —— 换算成**原图像素**（用户要的就是"一个像素或更厚一点"这个量级）；
   *   帧距的 X% —— 相对帧间距有多大，一眼能看出是不是被夹住了。
   */
  function thickText(v) {
    var parts = [v.toFixed(3)];
    if (state.seq) {
      parts.push('≈' + Math.round(v * state.seq.baseW) + ' px');
      var step = state.seq.geo && state.seq.frames.length > 1
        ? state.seq.geo.depth / (state.seq.frames.length - 1) : 0;
      if (step > 0) {
        var ratio = v / step;
        parts.push('帧距的 ' + Math.round(ratio * 100) + '%' + (ratio > 0.9 ? '（已夹到 90%）' : ''));
      }
    }
    return parts[0] + '（' + parts.slice(1).join(' · ') + '）';
  }

  function bindDrop() {
    if (dragArmed) return;      // 只能武装一次，避免重复监听
    dragArmed = true;
    /*
     * 拖放必须用**捕获阶段**绑在 document 上。
     *
     * 之前只绑了 window 的冒泡阶段，而且是在 bindUI() 末尾才绑 —— 一旦前面
     * 任何一行抛异常，这两个监听就完全不存在，浏览器于是执行默认行为：
     * 把拖入的每个文件当链接打开，一次拖 100 张照片就开出 100 个标签页。
     * 这就是用户遇到的那个现象的真正原因。
     *
     * 现在：监听在脚本求值时就注册（见文件末尾的 armDragGuard），不依赖 boot() 成功；
     * 用 capture: true，任何元素上的拖放都会被先拦下；
     * dragover 里设 dropEffect='copy'，给出正确的光标反馈。
     */
    document.addEventListener('dragover', onDragOver, true);
    document.addEventListener('dragenter', onDragOver, true);
    document.addEventListener('drop', onDrop, true);
    document.addEventListener('dragend', clearDragHint, true);
    document.addEventListener('dragleave', onDragLeave, true);
    // 双保险：万一有事件绕过捕获阶段，冒泡阶段也拦一次
    window.addEventListener('dragover', onDragOver, false);
    window.addEventListener('drop', swallowDrop, false);
  }

  var dragArmed = false;

  /** 在脚本求值阶段就武装拖放拦截，绝不等到 boot() */
  function armDragGuard() {
    try {
      bindDrop();
      document.body.dataset.dragArmed = '1';
    } catch (e) {
      // 连这个都失败就只能退回到不支持拖放，但至少说清楚
      try {
        document.body.dataset.dragArmed = '0';
        appendFatal('拖放拦截注册失败（拖入文件可能会被浏览器当链接打开）：' +
          (e && e.message || e));
      } catch (e2) { /* 无计可施 */ }
    }
  }

  function onDragOver(e) {
    var dt = e.dataTransfer;
    if (!dt) return;
    // 无条件阻止默认行为：默认行为就是"打开文件"
    e.preventDefault();
    e.stopPropagation();
    try { dt.dropEffect = 'copy'; } catch (err) { /* 某些浏览器只读，忽略 */ }
    hintDrag(true);
  }

  function clearDragHint() { hintDrag(false); }

  /** 拖出窗口时也要复位提示，否则"松手即可载入"会一直挂着 */
  function onDragLeave(e) {
    if (e.relatedTarget === null || e.target === document.documentElement) hintDrag(false);
  }

  var dragHintOn = false;
  function hintDrag(on) {
    if (on === dragHintOn) return;
    dragHintOn = on;
    if (on) status('松手即可载入这批照片' + hintLimits());
    else status('拖入一批照片，或点「打开照片」' + hintLimits());
  }

  /** 兜底：万一 drop 事件落在别的元素上，也绝不让浏览器去导航 */
  function swallowDrop(e) {
    if (e.defaultPrevented) return;
    e.preventDefault();
    var dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length) loadFiles(dt.files);
  }

  function onDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    hintDrag(false);
    var dt = e.dataTransfer;
    if (dt && dt.items && dt.items.length && !(dt.files && dt.files.length)) {
      // 极少数情况下 files 为空但 items 里有文件
      var picked = [];
      for (var i = 0; i < dt.items.length; i++) {
        if (dt.items[i].kind === 'file') {
          var f = dt.items[i].getAsFile();
          if (f) picked.push(f);
        }
      }
      if (picked.length) return loadFiles(picked);
    }
    if (dt && dt.files && dt.files.length) return loadFiles(dt.files);
    appendFatal('拖入的内容里没有文件。请按「打开照片」从文件对话框选择图片。');
  }

  /**
   * 以程序方式打开文件对话框（备用路径）。
   *
   * 正常点击「打开照片」走的是 index.html 里那个透明 input 的原生行为，
   * 不经过这里。这个函数用在：键盘触发、或用户在控制台里手动调用。
   * 两条路都试：直接 click 现有 input；不行就现场造一个再 click。
   */
  function openPicker() {
    var input = $('file');
    if (!input) { appendFatal('界面里缺少 id="file" 的文件选择控件。'); return; }
    try {
      input.click();
    } catch (err) {
      appendFatal('click() 打开文件对话框失败：' + (err && err.message || err) +
        '\n（正常点击「打开照片」按钮本身不受影响，那走的是浏览器原生行为。）');
    }
  }

  /** 现场造一个 input 再试一次；只在需要兜底时调用 */
  function openPickerFallback() {
    try {
      var tmp = document.createElement('input');
      tmp.type = 'file';
      tmp.accept = 'image/*';
      tmp.multiple = true;
      tmp.style.position = 'fixed';
      tmp.style.left = '-9999px';
      tmp.addEventListener('change', function () {
        if (tmp.files && tmp.files.length) loadFiles(tmp.files);
        if (tmp.parentNode) tmp.parentNode.removeChild(tmp);
      });
      document.body.appendChild(tmp);
      tmp.click();
      status('已尝试用备用方式打开文件对话框…');
    } catch (err) {
      appendFatal('备用方式也打不开文件对话框：' + (err && err.message || err));
    }
  }

  function bindInput() {
    var down = false, button = 0, lastX = 0, lastY = 0, moved = 0;
    canvas.addEventListener('contextmenu', function (e) { e.preventDefault(); });
    canvas.addEventListener('pointerdown', function (e) {
      down = true; button = e.button; lastX = e.clientX; lastY = e.clientY; moved = 0;
      canvas.classList.add('drag');
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener('pointermove', function (e) {
      if (!down) return;
      var dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      moved += Math.abs(dx) + Math.abs(dy);
      if (button === 2 || e.shiftKey) {
        cam.panU -= dx / viewport.h * 1.6;
        cam.panV += dy / viewport.h * 1.6;
      } else {
        cam.az -= dx * 0.28;
        cam.el = STC.math.clamp(cam.el + dy * 0.28, -89, 89);
      }
    });
    canvas.addEventListener('pointerup', function (e) {
      down = false;
      canvas.classList.remove('drag');
      if (moved < 4) { /* 单击不做事，避免误触 */ }
      try { canvas.releasePointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
    });
    canvas.addEventListener('wheel', function (e) {
      e.preventDefault();
      cam.zoom = STC.math.clamp(cam.zoom * Math.pow(0.999, e.deltaY * 1.6), 0.15, 12);
    }, { passive: false });
    canvas.addEventListener('dblclick', function () { applyView('reset'); invalidate(); });
  }

  function onKey(e) {
    // 框选面板打开时，Esc 取消、回车应用（这两个键在别处没有用途）
    if (cropDraft) {
      if (e.key === 'Escape') { cropClose(false); e.preventDefault(); return; }
      if (e.key === 'Enter') { cropClose(true); e.preventDefault(); return; }
      return;
    }
    if (e.key === 'r' || e.key === 'R') { applyView('reset'); invalidate(); }
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      if (!state.seq) return;
      var d = e.key === 'ArrowLeft' ? -1 : 1;
      state.frame = STC.math.clamp(state.frame + d, 0, state.seq.frames.length - 1);
      $('frame').value = String(state.frame);
      $('lbFrame').textContent = (state.frame + 1) + ' / ' + state.seq.frames.length;
      invalidate();
      e.preventDefault();
    }
  }

  /* --------------------------------------------------------- 对外接口 */
  /* 无头自检用；也方便在 F12 里直接操作 */

  window.STC.app = {
    state: state,
    cam: cam,
    resolve: resolve,
    loadFiles: loadFiles,
    loadPaths: loadPaths,
    setFrame: function (i) {
      state.frame = STC.math.clamp(i, 0, (state.seq ? state.seq.frames.length : 1) - 1);
      $('frame').value = String(state.frame);
      invalidate();
    },
    setAllGhost: function (on) { state.allGhost = !!on; $('allGhost').checked = !!on; invalidate(); },
    setOpacity: function (cur, other) {
      if (cur !== undefined) { state.opCur = cur; $('opCur').value = String(cur); $('lbOpCur').textContent = cur.toFixed(2); }
      if (other !== undefined) { state.opOther = other; $('opOther').value = String(other); $('lbOpOther').textContent = other.toFixed(2); }
      invalidate();
    },
    setView: function (v) { applyView(v); invalidate(); },
    setOtherMode: function (m) {
      state.otherMode = m; segOn('otherMode', m);
      document.body.dataset.otherMode = m; invalidate();
    },
    setEdgeMode: function (m) {
      state.edgeMode = m;
      segOn('edgeMode', m);
      state.showBands = true;
      if ($('showBands')) $('showBands').checked = true;
      rebuildEdgeAtlas(m);
    },
    /** 厚度条总开关（面板上那个复选框的程序入口） */
    setBands: setBands,
    /**
     * 诊断：把四个立面涂成红/绿/蓝/黄。
     * 用于回答"某个侧面到底有没有被画出来" —— 不依赖照片边缘的颜色。
     * 也可以直接用 `?banddebug=1` 打开。
     */
    setBandDebug: function (on) {
      state.bandDebug = !!on;
      if ($('bandDebug')) $('bandDebug').checked = state.bandDebug;
      document.body.dataset.bandDebug = state.bandDebug ? '1' : '0';
      invalidate();
    },
    setThickness: function (v) {
      state.thickness = v;
      $('thick').value = String(v); $('lbThick').textContent = thickText(v);
      invalidate();
    },
    setSpacing: function (v) {
      state.spacing = v;
      $('spacing').value = String(v); $('lbSpacing').textContent = v.toFixed(2);
      if (state.seq) {
        state.seq.geo = STC.seq.layout(1, state.seq.baseH / state.seq.baseW,
          state.seq.frames.length, v);
      }
      invalidate();
    },
    setLum: function (w, t) {
      if (w !== undefined) { state.lumWeight = w; $('lumW').value = String(w); $('lbLumW').textContent = w.toFixed(2); }
      if (t !== undefined) { state.lumThreshold = t; $('lumT').value = String(t); $('lbLumT').textContent = t.toFixed(2); }
      invalidate();
    },
    setLumDir: function (d) {
      state.lumDir = d === 'dark' ? 'dark' : 'bright';
      segOn('lumDir', state.lumDir);
      document.body.dataset.lumDir = state.lumDir;
      invalidate();
    },
    setFrameOutline: function (on) {
      state.showFrameOutline = !!on;
      $('showOutline').checked = !!on;
      invalidate();
    },
    setDotSize: function (v) {
      state.dotSize = v; $('dot').value = String(v); $('lbDot').textContent = v.toFixed(1);
      invalidate();
    },
    ensurePoints: ensurePoints,
    /** 渲染器实例（自检与排查用：能读到 geom / programs 的真实内容） */
    renderer: function () { return R; },
    diagnostics: function () {
      return {
        gl: glCtx ? glCtx.info : null,
        shaderErrors: glCtx ? glCtx.errors.slice() : [],
        frames: state.seq ? state.seq.frames.length : 0,
        baseSize: state.seq ? state.seq.baseW + 'x' + state.seq.baseH : null,
        origSize: state.seq ? state.seq.origW + 'x' + state.seq.origH : null,
        scaled: state.seq ? state.seq.scaled : false,
        longEdge: state.seq ? state.seq.longEdge : 0,
        autoChosen: state.seq ? state.seq.autoChosen : 0,
        budgetMB: state.seq ? Math.round(state.seq.budget / 1048576) : 0,
        resMode: state.resMode,
        thickness: state.thickness,
        spacing: state.spacing,
        depth: state.seq ? state.seq.geo.depth : 0,
        frameStep: state.seq && state.seq.frames.length > 1
          ? state.seq.geo.depth / (state.seq.frames.length - 1) : 0,
        lumWeight: state.lumWeight,
        lumThreshold: state.lumThreshold,
        lumDir: state.lumDir,
        showFrameOutline: state.showFrameOutline,
        dotSize: state.dotSize,
        textureBytes: state.seq ? state.seq.bytes : 0,
        failed: state.seq ? state.seq.failed : [],
        trimmed: state.seq ? state.seq.trimmed : 0,
        budgetHit: state.seq ? state.seq.budgetHit : null,
        noExif: state.seq ? state.seq.noExif : 0,
        frame: state.frame,
        stats: lastStats ? lastStats.res : null
      };
    },
    probe: probe,
    /**
     * 把一个世界坐标投影到画布像素坐标，返回 [x, y, 在视锥内?]。
     * 无头自检靠它算出「某个已知特征应该出现在哪个像素」，
     * 这样断言的不是「画面里有点东西」，而是「那个东西正好在该在的位置」。
     */
    projectPoint: function (x, y, z) {
      var p = STC.view.projectToPixel(camParams(), viewport, x, y, z).slice();
      p[2] = p[2] > -1 && p[2] < 1;
      return p;
    },
    viewport: function () { return viewport; },
    setResMode: function (m) {
      state.resMode = m;
      var el = $('res');
      if (el) el.value = m;
      if (state.files) ingest(state.files);
    },
    /** 立刻同步重画一次（无头自检在 probe 之前调用，避免读到上一帧） */
    renderNow: frame,
    /** 停掉渲染循环：Node 自检收尾时用，否则事件循环不会退出 */
    stop: stop,
    camParams: camParams,
    /** 备用入口：在控制台里执行 STC.app.openPicker() 也能打开文件对话框 */
    openPicker: openPicker,
    openPickerFallback: openPickerFallback,
    /** 输入通路自检：确认拖放与选文件这两个入口都活着 */
    inputDiagnostics: function () {
      var input = $('file');
      return {
        dragArmed: dragArmed,
        dragArmedAttr: document.body ? document.body.dataset.dragArmed : null,
        fileInputPresent: !!input,
        fileInputType: input ? input.type : null,
        fileInputMultiple: input ? !!input.multiple : null,
        fileInputAccept: input ? input.accept : null,
        // 透明覆盖式 input 的关键：它必须可见、且可点，否则原生点击不会触发
        fileInputVisible: input ? !input.hasAttribute('hidden') : false,
        openWrapPresent: !!$('openWrap')
      };
    },
    /** 等 rAF 真的画过一帧再返回，probe 读到的一定是这一帧 */
    settle: function () { return new Promise(function (r) { requestAnimationFrame(function () { requestAnimationFrame(r); }); }); },

    /*
     * 切割：只显示选区内的影像。
     * 选区一律用**归一化 uv**：{x0,y0,x1,y1}∈[0,1]，v=0 是图像**顶部**。
     * 正因为归一化，它对所有帧生效（混排不同尺寸的照片/视频也不会错位）。
     */
    setClipRect: function (r, on) { setClipRect(r, on); },
    clearClip: function () { clearClip(); },
    openClipEditor: function () { cropOpen(); },
    clipEditorOpen: function () { return !!cropDraft; },
    clipInfo: function () { return clipInfoText(); }
  };

  /**
   * 读回一个像素。无头自检用它来断言「正视图里看到的就是第一帧」。
   * 返回归一化的 RGBA（0..1）。
   */
  function probe(x, y) {
    var gl = glCtx.gl;
    var px = new Uint8Array(4);
    gl.readPixels(x, viewport.h - 1 - y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return [px[0] / 255, px[1] / 255, px[2] / 255, px[3] / 255];
  }

  if (document.readyState === 'loading') {
    // 先武装拖放拦截，再等 DOM：拖放不依赖任何 DOM 元素
    armDragGuard();
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    armDragGuard();
    boot();
  }
})(window.STC = window.STC || {});
