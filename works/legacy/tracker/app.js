'use strict';
/* 视频标志物跟踪 · 阻尼分析 —— 移植自 F:\Project\Tracker on Opencv.py
 * 原版：OpenCV LK 光流 + matplotlib 曲线 + scipy curve_fit。
 * 网页版：Canvas 读帧 + NCC 模板匹配 + 自写指数拟合，零依赖。 */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var PI = Math.PI;
  var TAU = PI * 2;

  /* ============================ 主题色 ============================ */
  var PAL = null;
  function readPalette() {
    var cs = getComputedStyle(document.documentElement);
    function v(n, fb) { var s = cs.getPropertyValue(n).trim(); return s || fb; }
    PAL = {
      paper: v('--paper', '#fbfaf7'),
      paper2: v('--paper-2', '#f4f1ea'),
      paper3: v('--paper-3', '#ece8de'),
      ink: v('--ink', '#1c1c1a'),
      ink2: v('--ink-2', '#57544c'),
      ink3: v('--ink-3', '#918c7f'),
      rule: v('--rule', '#e3ded2'),
      ruleStrong: v('--rule-strong', '#cfc8b8'),
      accent: v('--accent', '#2f6f5e'),
      dark: document.documentElement.getAttribute('data-theme') === 'dark'
    };
  }
  readPalette();
  var themeBtn = $('themeToggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('xz-theme', next); } catch (e) { }
      readPalette();
      drawDisplay(S.viewFrame);
      drawCharts();
    });
  }

  /* ============================ 全局状态 ============================ */
  var MARKER_COLORS = ['#c0392b', '#2f6f5e', '#7b6fae'];

  var S = {
    source: 'demo',          // demo | video
    ready: false,
    procW: 640, procH: 480,
    fps: 30, step: 1, tplSize: 25, searchR: 10, thresh: 0.5,
    scale: 0.05,             // cm / px
    calibrated: true,
    frameCount: 600,
    duration: 20,
    markers: [],             // {id, x, y, tpl}
    result: null,            // {markers:[{...series}]}
    viewFrame: 0,
    uiMode: 'idle',          // select | calib | reticle
    calibPts: [],
    busy: false,
    fit: null,
    replay: { active: false, t: 0, lastFrame: -1, lastTs: 0 },
    videoURL: null
  };

  /* ============================ 内置演示（合成弹簧振子） ============================ */
  var DEMO = {
    W: 640, H: 480, fps: 30, frames: 600,
    eqY: 240, amp: 140, b: 0.10, freq: 1.1, x: 320,
    markerR: 10
  };
  function demoMarkerY(frame) {
    var t = frame / DEMO.fps;
    return DEMO.eqY + DEMO.amp * Math.exp(-DEMO.b * t) * Math.sin(TAU * DEMO.freq * t);
  }
  function demoMarkerX(frame) {
    var t = frame / DEMO.fps;
    return DEMO.x + 18 * Math.sin(TAU * 0.35 * t + 0.6);
  }
  function mulberry32(seed) {
    var a = seed | 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function renderSynthFrame(g, frame) {
    var W = DEMO.W, H = DEMO.H;
    var rng = mulberry32(frame * 7919 + 17);
    // 背景
    var grad = g.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, '#111827');
    grad.addColorStop(1, '#1d2733');
    g.fillStyle = grad;
    g.fillRect(0, 0, W, H);
    // 静态网格
    g.strokeStyle = 'rgba(160, 180, 205, 0.07)';
    g.lineWidth = 1;
    for (var x = 40; x < W; x += 40) {
      g.beginPath(); g.moveTo(x + 0.5, 0); g.lineTo(x + 0.5, H); g.stroke();
    }
    for (var y = 30; y < H; y += 30) {
      g.beginPath(); g.moveTo(0, y + 0.5); g.lineTo(W, y + 0.5); g.stroke();
    }
    // 左侧刻度尺（每 10 px 一格，注意这是 30 px 网格背景之上的标注）
    g.strokeStyle = 'rgba(200, 215, 230, 0.35)';
    g.fillStyle = 'rgba(200, 215, 230, 0.5)';
    g.font = '9px "Cascadia Code", Consolas, monospace';
    g.textAlign = 'left';
    g.textBaseline = 'middle';
    for (var yy = 60; yy <= H - 20; yy += 30) {
      var major = (yy - 60) % 90 === 0;
      g.beginPath(); g.moveTo(14, yy + 0.5); g.lineTo(major ? 30 : 22, yy + 0.5); g.stroke();
      if (major) g.fillText(String((yy - 240) * 0.05).replace('-', '−') + 'cm', 32, yy);
    }
    // 顶部固定架
    g.fillStyle = '#8b93a3';
    g.fillRect(DEMO.x - 52, 26, 104, 9);
    g.fillStyle = '#5c6372';
    g.fillRect(DEMO.x - 60, 35, 120, 4);
    // 弹簧 + 磁铁（红色标志物）
    var my = demoMarkerY(frame) + (rng() * 1.6 - 0.8);
    var mx = demoMarkerX(frame) + (rng() * 1.2 - 0.6);
    var springBottom = my - DEMO.markerR - 2;
    var mountX = DEMO.x;
    g.strokeStyle = '#aab4c3';
    g.lineWidth = 1.6;
    g.beginPath();
    var nZ = 13;
    for (var k = 0; k <= nZ * 2; k++) {
      var frac = k / (nZ * 2);
      var sy = 39 + (springBottom - 39) * frac;
      var axisX = mountX + (mx - mountX) * frac;
      var sx = axisX + (k === 0 || k === nZ * 2 ? 0 : (k % 2 ? 13 : -13));
      if (k === 0) g.moveTo(sx, sy); else g.lineTo(sx, sy);
    }
    g.stroke();
    // 标志物本体（红圆 + 白环 + 高光），模板匹配靠这些边缘
    g.fillStyle = '#c0392b';
    g.beginPath(); g.arc(mx, my, DEMO.markerR, 0, TAU); g.fill();
    g.strokeStyle = 'rgba(245, 248, 250, 0.92)';
    g.lineWidth = 2;
    g.beginPath(); g.arc(mx, my, DEMO.markerR + 1, 0, TAU); g.stroke();
    g.fillStyle = 'rgba(255, 255, 255, 0.55)';
    g.beginPath(); g.arc(mx - 3.4, my - 3.4, 2.6, 0, TAU); g.fill();
    // 标记标签
    g.fillStyle = 'rgba(245, 248, 250, 0.9)';
    g.font = 'bold 10px "Microsoft YaHei", system-ui, sans-serif';
    g.textAlign = 'center';
    g.fillText('M1', mx, my - DEMO.markerR - 12);
    // 画面噪点（让跟踪置信度不再恒等于 1）
    for (var n = 0; n < 260; n++) {
      var nx = (rng() * W) | 0, ny = (rng() * H) | 0;
      var a = 0.05 + rng() * 0.06;
      g.fillStyle = rng() > 0.5 ? 'rgba(255,255,255,' + a + ')' : 'rgba(0,0,0,' + a + ')';
      g.fillRect(nx, ny, 1, 1);
    }
    // 帧号
    g.fillStyle = 'rgba(200, 215, 230, 0.75)';
    g.font = '11px "Cascadia Code", Consolas, monospace';
    g.textAlign = 'left';
    g.fillText('FRAME ' + String(frame).padStart(4, '0') + ' / ' + DEMO.frames, 14, 16);
    g.textAlign = 'right';
    g.fillText('SYNTHETIC SPRING-DAMPER', W - 14, 16);
  }

  /* ============================ 画布 ============================ */
  var main = null, mctx = null, proc = null, pctx = null;
  var mainW = 0, mainH = 0, mainDpr = 1;
  var gray = null;

  function setupMain() {
    var host = main.parentElement;
    var rect = host.getBoundingClientRect();
    if (rect.width < 20) return;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    mainW = Math.round(rect.width);
    mainH = Math.round(rect.height);
    mainDpr = dpr;
    main.width = Math.round(mainW * dpr);
    main.height = Math.round(mainH * dpr);
    mctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function displayMap() {
    var s = Math.min(mainW / S.procW, mainH / S.procH);
    return { s: s, dx: (mainW - S.procW * s) / 2, dy: (mainH - S.procH * s) / 2 };
  }
  function procToDisp(x, y) {
    var m = displayMap();
    return [m.dx + x * m.s, m.dy + y * m.s];
  }
  function dispToProc(px, py) {
    var m = displayMap();
    return [(px - m.dx) / m.s, (py - m.dy) / m.s];
  }

  function ensureProc(w, h) {
    S.procW = w; S.procH = h;
    proc.width = w; proc.height = h;
    gray = new Uint8ClampedArray(w * h);
  }

  function extractGray() {
    var data = pctx.getImageData(0, 0, S.procW, S.procH).data;
    var n = S.procW * S.procH;
    if (!gray || gray.length !== n) gray = new Uint8ClampedArray(n);
    for (var i = 0, j = 0; j < n; i += 4, j++) {
      gray[j] = data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114;
    }
    return gray;
  }

  /* ============================ 显示与叠加 ============================ */
  function drawDisplay(frameIdx, showTrail) {
    if (!main || !mctx) return;
    if (mainW === 0) setupMain();
    if (mainW === 0) return;
    var m = displayMap();
    mctx.clearRect(0, 0, mainW, mainH);
    mctx.fillStyle = PAL.paper3;
    mctx.fillRect(0, 0, mainW, mainH);
    // 帧
    if (proc.width > 0) {
      mctx.imageSmoothingEnabled = true;
      mctx.drawImage(proc, 0, 0, S.procW, S.procH, m.dx, m.dy, S.procW * m.s, S.procH * m.s);
    }
    // 边框
    mctx.strokeStyle = PAL.ruleStrong;
    mctx.lineWidth = 1;
    mctx.strokeRect(m.dx + 0.5, m.dy + 0.5, S.procW * m.s, S.procH * m.s);

    // 轨迹
    if (showTrail !== false && S.result) {
      var series = S.result.markers;
      for (var mi = 0; mi < series.length; mi++) {
        var sdata = series[mi];
        if (!sdata || !sdata.n) continue;
        var upto = Math.min(sdata.n - 1, frameIdx == null ? sdata.n - 1 : nearestIndex(sdata, frameIdx));
        mctx.strokeStyle = MARKER_COLORS[mi % MARKER_COLORS.length];
        mctx.globalAlpha = 0.8;
        mctx.lineWidth = 1.4;
        mctx.beginPath();
        for (var k = 0; k <= upto; k++) {
          var p = procToDisp(sdata.x[k], sdata.y[k]);
          if (k === 0) mctx.moveTo(p[0], p[1]); else mctx.lineTo(p[0], p[1]);
        }
        mctx.stroke();
        mctx.globalAlpha = 1;
      }
    }
    // 当前点 / 待选点
    if (S.result) {
      for (var mj = 0; mj < S.result.markers.length; mj++) {
        var sd2 = S.result.markers[mj];
        if (!sd2 || !sd2.n) continue;
        var idx = nearestIndex(sd2, frameIdx == null ? S.viewFrame : frameIdx);
        var pt = procToDisp(sd2.x[idx], sd2.y[idx]);
        drawMarkerDot(mctx, pt[0], pt[1], MARKER_COLORS[mj % MARKER_COLORS.length], 'M' + (mj + 1));
      }
    } else {
      for (var mk = 0; mk < S.markers.length; mk++) {
        var pos = procToDisp(S.markers[mk].x, S.markers[mk].y);
        drawMarkerDot(mctx, pos[0], pos[1], MARKER_COLORS[mk % MARKER_COLORS.length], 'M' + (mk + 1));
      }
    }
    // 标定参考点
    if (S.uiMode === 'calib') {
      var pts = S.calibPts;
      for (var ci = 0; ci < pts.length; ci++) {
        var q = procToDisp(pts[ci][0], pts[ci][1]);
        mctx.strokeStyle = '#3fa36f';
        mctx.fillStyle = '#3fa36f';
        mctx.lineWidth = 1.4;
        mctx.beginPath(); mctx.arc(q[0], q[1], 6, 0, TAU); mctx.stroke();
        mctx.beginPath(); mctx.arc(q[0], q[1], 2, 0, TAU); mctx.fill();
        mctx.fillStyle = 'rgba(255,255,255,0.95)';
        mctx.font = '10px "Microsoft YaHei", system-ui, sans-serif';
        mctx.textAlign = 'left';
        mctx.fillText('P' + (ci + 1), q[0] + 9, q[1] - 8);
      }
      if (pts.length === 2) {
        var a = procToDisp(pts[0][0], pts[0][1]);
        var b = procToDisp(pts[1][0], pts[1][1]);
        mctx.strokeStyle = '#3fa36f';
        mctx.setLineDash([5, 4]);
        mctx.beginPath(); mctx.moveTo(a[0], a[1]); mctx.lineTo(b[0], b[1]); mctx.stroke();
        mctx.setLineDash([]);
      }
    }
  }

  function drawMarkerDot(ctx, x, y, color, label) {
    ctx.strokeStyle = color;
    ctx.fillStyle = 'rgba(250, 250, 250, 0.95)';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 7, 0, TAU); ctx.fill(); ctx.stroke();
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(x, y, 3.4, 0, TAU); ctx.fill();
    ctx.fillStyle = 'rgba(250, 250, 250, 0.95)';
    ctx.font = 'bold 10px "Microsoft YaHei", system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(label, x + 10, y - 10);
  }

  function nearestIndex(sdata, frame) {
    // sdata.frames 单调递增
    var lo = 0, hi = sdata.n - 1;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (sdata.frames[mid] < frame) lo = mid + 1; else hi = mid;
    }
    if (lo > 0 && Math.abs(sdata.frames[lo - 1] - frame) <= Math.abs(sdata.frames[lo] - frame)) lo--;
    return lo;
  }

  /* ============================ NCC 模板匹配 ============================ */
  function makeTemplate(cx, cy) {
    var ts = S.tplSize;
    if (ts % 2 === 0) ts += 1;
    var hs = (ts - 1) / 2;
    var x0 = Math.round(cx), y0 = Math.round(cy);
    x0 = Math.max(hs, Math.min(S.procW - 1 - hs, x0));
    y0 = Math.max(hs, Math.min(S.procH - 1 - hs, y0));
    var t = new Float32Array(ts * ts);
    var idx = 0, sum = 0, sum2 = 0;
    for (var dy = -hs; dy <= hs; dy++) {
      var row = (y0 + dy) * S.procW;
      for (var dx = -hs; dx <= hs; dx++) {
        var v = gray[row + x0 + dx];
        t[idx++] = v; sum += v; sum2 += v * v;
      }
    }
    return { data: t, ts: ts, hs: hs, sum: sum, sum2: sum2, cx: x0, cy: y0 };
  }

  function nccAt(x, y, tpl) {
    var ts = tpl.ts, hs = tpl.hs, n = ts * ts;
    var sumI = 0, sumI2 = 0, sumIT = 0, idx = 0;
    for (var dy = -hs; dy <= hs; dy++) {
      var row = (y + dy) * S.procW + (x - hs);
      for (var dx = 0; dx < ts; dx++) {
        var v = gray[row + dx];
        sumI += v; sumI2 += v * v;
        sumIT += v * tpl.data[idx++];
      }
    }
    var num = n * sumIT - sumI * tpl.sum;
    var denI = n * sumI2 - sumI * sumI;
    var denT = n * tpl.sum2 - tpl.sum * tpl.sum;
    var den = Math.sqrt((denI > 0 ? denI : 1e-9) * (denT > 0 ? denT : 1e-9));
    return num / den;
  }

  function matchInWindow(cx, cy, R, tpl) {
    var hs = tpl.hs;
    var minX = hs, maxX = S.procW - 1 - hs, minY = hs, maxY = S.procH - 1 - hs;
    var bcx = Math.max(minX, Math.min(maxX, Math.round(cx)));
    var bcy = Math.max(minY, Math.min(maxY, Math.round(cy)));
    var best = -2, bx = bcx, by = bcy;
    var ddx, ddy;
    // 粗搜（步长 2）
    for (ddy = -R; ddy <= R; ddy += 2) {
      for (ddx = -R; ddx <= R; ddx += 2) {
        var x = bcx + ddx, y = bcy + ddy;
        if (x < minX || x > maxX || y < minY || y > maxY) continue;
        var s = nccAt(x, y, tpl);
        if (s > best) { best = s; bx = x; by = y; }
      }
    }
    // 细搜（步长 1，±2）
    var fx = bx, fy = by;
    for (ddy = -2; ddy <= 2; ddy++) {
      for (ddx = -2; ddx <= 2; ddx++) {
        var nx = bx + ddx, ny = by + ddy;
        if (nx < minX || nx > maxX || ny < minY || ny > maxY) continue;
        if (nx === bx && ny === by) continue;
        var s2 = nccAt(nx, ny, tpl);
        if (s2 > best) { best = s2; fx = nx; fy = ny; }
      }
    }
    // 抛物线亚像素修正
    var x0 = fx, y0 = fy;
    var sC = nccAt(x0, y0, tpl);
    var sxm = x0 > minX ? nccAt(x0 - 1, y0, tpl) : sC;
    var sxp = x0 < maxX ? nccAt(x0 + 1, y0, tpl) : sC;
    var sym = y0 > minY ? nccAt(x0, y0 - 1, tpl) : sC;
    var syp = y0 < maxY ? nccAt(x0, y0 + 1, tpl) : sC;
    var subx = 0, suby = 0;
    var denx = sxm - 2 * sC + sxp;
    if (Math.abs(denx) > 1e-9) subx = 0.5 * (sxm - sxp) / denx;
    if (subx > 0.7) subx = 0.7; if (subx < -0.7) subx = -0.7;
    var deny = sym - 2 * sC + syp;
    if (Math.abs(deny) > 1e-9) suby = 0.5 * (sym - syp) / deny;
    if (suby > 0.7) suby = 0.7; if (suby < -0.7) suby = -0.7;
    return { x: x0 + subx, y: y0 + suby, score: sC };
  }

  function updateTemplate(tpl, cx, cy) {
    var ts = tpl.ts, hs = tpl.hs;
    var x0 = Math.round(cx), y0 = Math.round(cy);
    var minX = hs, maxX = S.procW - 1 - hs, minY = hs, maxY = S.procH - 1 - hs;
    if (x0 < minX || x0 > maxX || y0 < minY || y0 > maxY) return;
    var idx = 0, sum = 0, sum2 = 0;
    for (var dy = -hs; dy <= hs; dy++) {
      var row = (y0 + dy) * S.procW;
      for (var dx = -hs; dx <= hs; dx++) {
        var v = gray[row + x0 + dx];
        var nv = tpl.data[idx] * 0.82 + v * 0.18;
        tpl.data[idx] = nv;
        sum += nv; sum2 += nv * nv;
        idx++;
      }
    }
    tpl.sum = sum; tpl.sum2 = sum2;
  }

  /* ============================ 帧准备 ============================ */
  var video = null;

  function seekVideo(t) {
    return new Promise(function (resolve) {
      if (!video || !isFinite(t)) { resolve(); return; }
      if (Math.abs(video.currentTime - t) < 1e-4) { resolve(); return; }
      var done = false;
      function onSeek() {
        if (done) return;
        done = true;
        video.removeEventListener('seeked', onSeek);
        resolve();
      }
      video.addEventListener('seeked', onSeek);
      try { video.currentTime = Math.max(0, t); } catch (e) { onSeek(); }
      setTimeout(function () { if (!done) onSeek(); }, 600);
    });
  }

  function prepareFrame(frameIdx) {
    if (S.source === 'demo') {
      renderSynthFrame(pctx, frameIdx);
      return Promise.resolve();
    }
    var t = frameIdx / S.fps;
    return seekVideo(t).then(function () {
      try {
        pctx.drawImage(video, 0, 0, S.procW, S.procH);
      } catch (e) { /* 视频尚未解码时忽略 */ }
    });
  }

  /* ============================ 跟踪主流程 ============================ */
  function readOptions() {
    function num(id, fb, lo, hi) {
      var el = $(id);
      var v = el ? parseFloat(el.value) : NaN;
      if (!isFinite(v)) v = fb;
      return Math.min(hi, Math.max(lo, v));
    }
    S.fps = Math.round(num('optFps', 30, 1, 240));
    S.step = Math.round(num('optStep', 1, 1, 30));
    S.tplSize = Math.round(num('optTpl', 25, 9, 41));
    if (S.tplSize % 2 === 0) S.tplSize += 1;
    S.searchR = Math.round(num('optSearch', 10, 3, 40));
    S.thresh = num('optConf', 0.5, 0.1, 0.95);
    S.scale = num('optScale', 0.05, 0.0001, 10);
  }

  function setStatus(txt) { var el = $('statusText'); if (el) el.textContent = txt; }
  function setHint(txt) { var el = $('videoHint'); if (el) el.innerHTML = txt; }
  function setProg(frac) { var el = $('progBar'); if (el) el.style.width = Math.max(0, Math.min(1, frac)) * 100 + '%'; }

  function clearResults() {
    S.result = null;
    S.fit = null;
    $('valDX').textContent = '—';
    $('valDY').textContent = '—';
    $('valD').textContent = '—';
    $('valConf').textContent = '—';
    $('fitB').textContent = '—';
    $('fitA').textContent = '—';
    $('fitY0').textContent = '—';
    $('fitR2').textContent = '—';
    $('fitN').textContent = '—';
    $('fitTau').textContent = '—';
    drawCharts();
  }

  function startTracking(isAuto) {
    if (S.busy) return;
    if (!S.markers.length) {
      setHint('还没有标志物：在画面上点击要跟踪的标志物（最多 3 个）。');
      return;
    }
    readOptions();
    var totalFrames = S.source === 'demo' ? DEMO.frames : S.frameCount;
    var lastF = totalFrames - 1;
    var frames = [];
    for (var f = 0; f <= lastF; f += S.step) frames.push(f);
    if (frames.length > 1800) {
      setStatus('帧数过多（' + frames.length + ' 帧）：请增大「抽帧步长」或缩短视频后再跟踪');
      setHint('视频共 ' + totalFrames + ' 帧，逐帧 NCC 匹配太慢。把右上「抽帧步长」调到 2~5（例如 30fps 视频设 2 → 15 个采样/秒）再试。');
      return;
    }
    S.busy = true;
    setProg(0);
    var trackBtn = $('btnTrack');
    if (trackBtn) trackBtn.disabled = true;
    // 初始化：第一帧 + 模板
    var state = {
      frameList: frames,
      pos: 1,                  // 第 0 帧已作为模板初始化帧处理
      markers: S.markers.map(function (m, i) {
        return { id: i, x: m.x, y: m.y, vx: 0, vy: 0, x0: m.x, y0: m.y, tpl: null };
      })
    };
    var results = S.markers.map(function () { return { frames: [], x: [], y: [], conf: [] }; });

    return prepareFrame(0).then(function () {
      extractGray();
      for (var i = 0; i < state.markers.length; i++) {
        state.markers[i].tpl = makeTemplate(state.markers[i].x, state.markers[i].y);
        results[i].frames.push(0);
        results[i].x.push(state.markers[i].x);
        results[i].y.push(state.markers[i].y);
        results[i].conf.push(1);
      }
      setStatus('跟踪中… 0 / ' + frames.length + ' 帧');
      drawDisplay(0);
      setProg(1 / frames.length);
      return tick();

      function tick() {
        if (state.pos >= state.frameList.length) return finish();
        var frameIdx = state.frameList[state.pos];
        return prepareFrame(frameIdx).then(function () {
          extractGray();
          for (var i = 0; i < state.markers.length; i++) {
            var m = state.markers[i];
            var predX = m.x + m.vx;
            var predY = m.y + m.vy;
            // 开头两帧还没有速度估计，先用更大的搜索窗捕获首帧位移
            var R = state.pos <= 2 ? Math.max(S.searchR, 40) : S.searchR;
            var hit = matchInWindow(predX, predY, R, m.tpl);
            var nvx = hit.x - m.x, nvy = hit.y - m.y;
            // 限制单帧跳动，避免匹配到错误目标后飞出去
            var maxJump = Math.max(20, R * 4);
            var jump = Math.sqrt(nvx * nvx + nvy * nvy);
            if (jump > maxJump) {
              nvx = nvx / jump * maxJump;
              nvy = nvy / jump * maxJump;
            }
            m.x = m.x + nvx;
            m.y = m.y + nvy;
            m.vx = nvx; m.vy = nvy;
            m.x = Math.max(2, Math.min(S.procW - 3, m.x));
            m.y = Math.max(2, Math.min(S.procH - 3, m.y));
            results[i].frames.push(frameIdx);
            results[i].x.push(m.x);
            results[i].y.push(m.y);
            results[i].conf.push(hit.score);
            if (hit.score > 0.85) updateTemplate(m.tpl, m.x, m.y);
          }
          state.pos++;
          if (state.pos % 6 === 0 || state.pos === state.frameList.length) {
            setProg(state.pos / state.frameList.length);
            setStatus('跟踪中… ' + state.pos + ' / ' + state.frameList.length + ' 帧');
            S.viewFrame = frameIdx;
            return new Promise(function (r) { setTimeout(r, 0); }).then(tick);
          }
          return tick();
        });
      }

      function finish() {
        buildResults(results, frames);
        S.busy = false;
        if (trackBtn) trackBtn.disabled = false;
        S.viewFrame = lastF;
        setProg(1);
        var avg = 0, cnt = 0;
        for (var i = 0; i < results.length; i++) {
          for (var j = 0; j < results[i].conf.length; j++) { avg += results[i].conf[j]; cnt++; }
        }
        avg = cnt ? avg / cnt : 0;
        setStatus('跟踪完成：' + frames.length + ' 帧 · ' + results.length + ' 个标志物 · 平均置信度 ' + avg.toFixed(3));
        setHint('跟踪完成。<b>回放</b> 查看跟踪过程；在下方面板选择区间做阻尼拟合；<b>重新标记</b> 可回到首帧重新点选。');
        // 填充阻尼控件
        var sel = $('dampMarker');
        var maxFrame = lastF;
        $('dampStart').value = '0';
        $('dampEnd').value = String(maxFrame);
        if (sel) {
          sel.innerHTML = '';
          for (var k = 0; k < results.length; k++) {
            var opt = document.createElement('option');
            opt.value = String(k);
            opt.textContent = '标记 ' + (k + 1);
            sel.appendChild(opt);
          }
        }
        drawDisplay(S.viewFrame);
        drawCharts();
        // 跟踪完成后自动做一次包络拟合，打开页面即可看到阻尼系数
        runFit();
        var fitMsg = '';
        if (S.fit) {
          fitMsg = ' · 自动包络拟合 b = ' + S.fit.b.toFixed(4) + ' s⁻¹（R² = ' + S.fit.r2.toFixed(3) + '）';
        }
        setStatus('跟踪完成：' + frames.length + ' 帧 · ' + results.length + ' 个标志物 · 平均置信度 ' + avg.toFixed(3) + fitMsg);
        if (isAuto) {
          updateChartValues();
          setTimeout(startReplay, 400);
        } else {
          startReplay();
        }
      }
    }).catch(function (err) {
      S.busy = false;
      if (trackBtn) trackBtn.disabled = false;
      setStatus('跟踪失败：' + (err && err.message ? err.message : err));
      if (window.console) console.error(err);
    });
  }

  function buildResults(raw, frames) {
    var out = { markers: [], frameCount: frames.length, lastFrame: frames[frames.length - 1] };
    for (var i = 0; i < raw.length; i++) {
      var r = raw[i];
      var n = r.x.length;
      var framesArr = new Float64Array(n);
      var x = new Float64Array(n), y = new Float64Array(n), conf = new Float64Array(n);
      for (var j = 0; j < n; j++) {
        framesArr[j] = r.frames[j];
        x[j] = r.x[j]; y[j] = r.y[j]; conf[j] = r.conf[j];
      }
      // 移动平均（与原版 smooth_positions 的 5 点窗口一致）
      var xs = smooth(x, 5), ys = smooth(y, 5);
      var t = new Float64Array(n), xcm = new Float64Array(n), ycm = new Float64Array(n);
      var dx = new Float64Array(n), dy = new Float64Array(n), dm = new Float64Array(n);
      for (var k = 0; k < n; k++) {
        t[k] = framesArr[k] / S.fps;
        xcm[k] = xs[k] * S.scale;
        ycm[k] = ys[k] * S.scale;
        dx[k] = xcm[k] - x[0] * S.scale;
        dy[k] = ycm[k] - y[0] * S.scale;
        dm[k] = Math.sqrt(dx[k] * dx[k] + dy[k] * dy[k]);
      }
      out.markers.push({
        n: n, frames: framesArr, t: t, x: x, y: y, conf: conf,
        xs: xs, ys: ys, xcm: xcm, ycm: ycm, dx: dx, dy: dy, dm: dm
      });
    }
    S.result = out;
  }

  function smooth(arr, win) {
    var n = arr.length, out = new Float64Array(n);
    var half = (win - 1) / 2;
    for (var i = 0; i < n; i++) {
      var a = Math.max(0, i - half), b = Math.min(n - 1, i + half), sum = 0;
      for (var j = a; j <= b; j++) sum += arr[j];
      out[i] = sum / (b - a + 1);
    }
    return out;
  }

  /* ============================ 图表 ============================ */
  var charts = [];
  function makeChart(canvasId, kind) {
    var canvas = $(canvasId);
    var ch = { canvas: canvas, ctx: canvas.getContext('2d'), host: canvas.parentElement, kind: kind, w: 0, h: 0, dpr: 1 };
    charts.push(ch);
    var ro = new ResizeObserver(function () { if (setupChart(ch)) drawCharts(); });
    ro.observe(ch.host);
    setupChart(ch);
    return ch;
  }
  function setupChart(ch) {
    var rect = ch.host.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) return false;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var W = Math.round(rect.width), H = Math.round(rect.height);
    if (W === ch.w && H === ch.h && dpr === ch.dpr) return false;
    ch.w = W; ch.h = H; ch.dpr = dpr;
    ch.canvas.width = Math.round(W * dpr);
    ch.canvas.height = Math.round(H * dpr);
    ch.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return true;
  }

  function chartRange(kind) {
    var r = 0.5;
    if (S.result) {
      for (var i = 0; i < S.result.markers.length; i++) {
        var m = S.result.markers[i];
        if (!m || !m.n) continue;
        for (var j = 0; j < m.n; j++) {
          var v;
          if (kind === 'x') v = Math.abs(m.dx[j]);
          else if (kind === 'y') v = Math.abs(m.dy[j]);
          else if (kind === 'd') v = m.dm[j];
          else v = 1;
          if (v > r) r = v;
        }
      }
    }
    if (kind === 'conf') return { min: 0, max: 1 };
    if (kind === 'd') return { min: 0, max: Math.max(0.5, r * 1.12) };
    return { min: -Math.max(0.5, r * 1.12), max: Math.max(0.5, r * 1.12) };
  }

  function drawCharts() {
    for (var i = 0; i < charts.length; i++) drawChart(charts[i]);
  }

  function drawChart(ch) {
    if (!ch.w || !ch.h) return;
    var c = ch.ctx, W = ch.w, H = ch.h;
    c.clearRect(0, 0, W, H);
    var pad = { l: 46, r: 12, t: 10, b: 24 };
    var iw = Math.max(10, W - pad.l - pad.r);
    var ih = Math.max(10, H - pad.t - pad.b);
    var kind = ch.kind;
    var rng = chartRange(kind);
    var lastFrame = S.source === 'demo' ? (DEMO.frames - 1) : Math.max(1, S.frameCount - 1);
    var useFrames = kind === 'conf';
    var xMax = useFrames ? lastFrame : lastFrame / S.fps;
    var xMin = 0;
    function mapX(v) { return pad.l + (v - xMin) / (xMax - xMin) * iw; }
    function mapY(v) { return pad.t + (1 - (v - rng.min) / (rng.max - rng.min)) * ih; }

    // 网格
    c.lineWidth = 1;
    c.font = '10px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    var k;
    for (k = 1; k < 4; k++) {
      var gx = Math.round(pad.l + iw * k / 4) + 0.5;
      c.strokeStyle = PAL.rule;
      c.beginPath(); c.moveTo(gx, pad.t); c.lineTo(gx, pad.t + ih); c.stroke();
    }
    for (k = 1; k < 4; k++) {
      var gy = Math.round(pad.t + ih * k / 4) + 0.5;
      c.strokeStyle = PAL.rule;
      c.beginPath(); c.moveTo(pad.l, gy); c.lineTo(pad.l + iw, gy); c.stroke();
    }
    // 零轴 / 阈值
    if (kind === 'x' || kind === 'y') {
      var zy = Math.round(mapY(0)) + 0.5;
      c.strokeStyle = PAL.ruleStrong;
      c.beginPath(); c.moveTo(pad.l, zy); c.lineTo(pad.l + iw, zy); c.stroke();
    }
    if (kind === 'conf') {
      var ty = Math.round(mapY(S.thresh)) + 0.5;
      c.strokeStyle = '#c9973f';
      c.setLineDash([5, 4]);
      c.beginPath(); c.moveTo(pad.l, ty); c.lineTo(pad.l + iw, ty); c.stroke();
      c.setLineDash([]);
      c.fillStyle = PAL.ink3;
      c.textAlign = 'left';
      c.fillText('阈值 ' + S.thresh.toFixed(2), pad.l + 4, ty - 7);
    }
    // 坐标刻度
    c.fillStyle = PAL.ink3;
    c.textAlign = 'right';
    function fmt(v) {
      var a = Math.abs(v);
      if (a >= 100) return v.toFixed(0);
      if (a >= 10) return v.toFixed(1);
      if (a >= 1) return v.toFixed(2);
      return v.toFixed(2);
    }
    c.fillText(fmt(rng.max), pad.l - 5, pad.t + 5);
    c.fillText(fmt((rng.max + rng.min) / 2), pad.l - 5, pad.t + ih / 2);
    c.fillText(fmt(rng.min), pad.l - 5, pad.t + ih - 5);
    c.textAlign = 'center';
    c.fillText('0', pad.l, pad.t + ih + 10);
    var xLabel = useFrames ? String(Math.round(xMax)) + ' 帧' : xMax.toFixed(1) + ' s';
    c.fillText(xLabel, pad.l + iw, pad.t + ih + 10);
    c.fillStyle = PAL.ink3;
    c.textAlign = 'left';
    c.fillText(kind === 'conf' ? '置信度' : 'cm', pad.l + 2, pad.t + 8);

    if (!S.result) return;
    // 曲线
    for (var mi = 0; mi < S.result.markers.length; mi++) {
      var m = S.result.markers[mi];
      if (!m || !m.n) continue;
      var color = MARKER_COLORS[mi % MARKER_COLORS.length];
      var arr, xarr;
      if (kind === 'x') { arr = m.dx; xarr = m.t; }
      else if (kind === 'y') { arr = m.dy; xarr = m.t; }
      else if (kind === 'd') { arr = m.dm; xarr = m.t; }
      else { arr = m.conf; xarr = m.frames; }
      c.strokeStyle = color;
      c.lineWidth = 1.5;
      c.beginPath();
      for (var j = 0; j < m.n; j++) {
        var px = mapX(xarr[j]);
        var py = mapY(arr[j]);
        if (j === 0) c.moveTo(px, py); else c.lineTo(px, py);
      }
      c.stroke();
    }
    // 拟合曲线（只画在 Y 位移图上）
    if (kind === 'y' && S.fit) {
      var f = S.fit;
      var seg = S.result.markers[f.marker];
      if (seg && seg.n) {
        var t0 = seg.t[f.start];
        var t1 = seg.t[Math.min(f.end, seg.n - 1)];
        c.strokeStyle = PAL.accent;
        c.lineWidth = 1.6;
        c.setLineDash([6, 4]);
        if (f.method === 'direct') {
          c.beginPath();
          var first = true;
          for (var q = 0; q <= 80; q++) {
            var tt = t0 + (t1 - t0) * q / 80;
            var vv = f.A0 * Math.exp(-f.b * (tt - t0)) + f.y0;
            var px2 = mapX(tt), py2 = mapY(vv);
            if (first) { c.moveTo(px2, py2); first = false; } else c.lineTo(px2, py2);
          }
          c.stroke();
        } else {
          for (var sgn = -1; sgn <= 1; sgn += 2) {
            c.beginPath();
            var first2 = true;
            for (var q2 = 0; q2 <= 80; q2++) {
              var tt2 = t0 + (t1 - t0) * q2 / 80;
              var vv2 = f.y0 + sgn * f.A0 * Math.exp(-f.b * (tt2 - t0));
              var px3 = mapX(tt2), py3 = mapY(vv2);
              if (first2) { c.moveTo(px3, py3); first2 = false; } else c.lineTo(px3, py3);
            }
            c.stroke();
          }
        }
        c.setLineDash([]);
        // 标注拟合区间
        c.fillStyle = 'rgba(47,111,94,0.08)';
        c.fillRect(mapX(t0), pad.t, Math.max(1, mapX(t1) - mapX(t0)), ih);
      }
    }
  }

  function updateChartValues() {
    if (!S.result) return;
    var m = S.result.markers[0];
    if (!m || !m.n) return;
    var idx = Math.min(m.n - 1, nearestIndex(m, S.viewFrame));
    $('valDX').textContent = m.dx[idx].toFixed(2);
    $('valDY').textContent = m.dy[idx].toFixed(2);
    $('valD').textContent = m.dm[idx].toFixed(2);
    $('valConf').textContent = m.conf[idx].toFixed(2);
  }

  /* ============================ 指数拟合（阻尼系数） ============================ */
  function solve3(A, rhs) {
    var a = A[0][0], b = A[0][1], c = A[0][2];
    var d = A[1][0], e = A[1][1], f = A[1][2];
    var g = A[2][0], h = A[2][1], i = A[2][2];
    var det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
    if (!isFinite(det) || Math.abs(det) < 1e-18) return null;
    var x = (rhs[0] * (e * i - f * h) - b * (rhs[1] * i - f * rhs[2]) + c * (rhs[1] * h - e * rhs[2])) / det;
    var y = (a * (rhs[1] * i - f * rhs[2]) - rhs[0] * (d * i - f * g) + c * (d * rhs[2] - rhs[1] * g)) / det;
    var z = (a * (e * rhs[2] - rhs[1] * h) - b * (d * rhs[2] - rhs[1] * g) + rhs[0] * (d * h - e * g)) / det;
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) return null;
    return [x, y, z];
  }

  function fitDirect(tt, yy) {
    var n = tt.length;
    var maxv = -1e30, minv = 1e30, sumLast = 0, lastN = Math.max(1, Math.round(n * 0.1));
    for (var i = 0; i < n; i++) {
      if (yy[i] > maxv) maxv = yy[i];
      if (yy[i] < minv) minv = yy[i];
    }
    for (var l = n - lastN; l < n; l++) sumLast += yy[l];
    var p = [(maxv - minv) / 2 || 1, 0.3, sumLast / lastN];
    var lambda = 1e-3;
    function ssOf(pp) {
      var ss = 0;
      for (var q = 0; q < n; q++) {
        var model = pp[0] * Math.exp(-pp[1] * tt[q]) + pp[2];
        var r = yy[q] - model;
        ss += r * r;
      }
      return ss;
    }
    var ss = ssOf(p);
    for (var iter = 0; iter < 120; iter++) {
      var JtJ = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
      var Jtr = [0, 0, 0];
      for (var j = 0; j < n; j++) {
        var ex = Math.exp(-p[1] * tt[j]);
        var model2 = p[0] * ex + p[2];
        var r2 = yy[j] - model2;
        var dA = -ex;
        var db = p[0] * tt[j] * ex;
        var dy = -1;
        JtJ[0][0] += dA * dA; JtJ[0][1] += dA * db; JtJ[0][2] += dA * dy;
        JtJ[1][1] += db * db; JtJ[1][2] += db * dy;
        JtJ[2][2] += dy * dy;
        Jtr[0] += dA * r2; Jtr[1] += db * r2; Jtr[2] += dy * r2;
      }
      JtJ[1][0] = JtJ[0][1]; JtJ[2][0] = JtJ[0][2]; JtJ[2][1] = JtJ[1][2];
      var M = [[JtJ[0][0] * (1 + lambda), JtJ[0][1], JtJ[0][2]],
        [JtJ[1][0], JtJ[1][1] * (1 + lambda), JtJ[1][2]],
        [JtJ[2][0], JtJ[2][1], JtJ[2][2] * (1 + lambda)]];
      var delta = solve3(M, Jtr);
      if (!delta) break;
      var cand = [p[0] + delta[0], p[1] + delta[1], p[2] + delta[2]];
      if (cand[1] < 0) cand[1] = 0;
      if (cand[1] > 50) cand[1] = 50;
      if (!isFinite(cand[0]) || Math.abs(cand[0]) > 1e6) break;
      var ssCand = ssOf(cand);
      if (ssCand < ss) {
        p = cand; ss = ssCand; lambda *= 0.4;
        if (Math.abs(delta[0]) + Math.abs(delta[1]) + Math.abs(delta[2]) < 1e-12) break;
      } else {
        lambda *= 6;
        if (lambda > 1e10) break;
      }
    }
    // R²
    var mean = 0;
    for (var q2 = 0; q2 < n; q2++) mean += yy[q2];
    mean /= n;
    var ssTot = 0;
    for (var q3 = 0; q3 < n; q3++) { var d = yy[q3] - mean; ssTot += d * d; }
    var r2 = ssTot > 1e-18 ? 1 - ss / ssTot : 0;
    return { A0: p[0], b: p[1], y0: p[2], r2: r2, n: n };
  }

  function fitEnvelope(tt, yy) {
    var n = tt.length, peaks = [], i;
    for (i = 1; i < n - 1; i++) {
      var a0 = Math.abs(yy[i - 1]), a1 = Math.abs(yy[i]), a2 = Math.abs(yy[i + 1]);
      if (a1 >= a0 && a1 > a2 && a1 > 1e-6) peaks.push(i);
    }
    if (peaks.length < 3) return null;
    var sx = 0, sy = 0, sxx = 0, sxy = 0, cnt = 0;
    var t0 = tt[peaks[0]];
    for (i = 0; i < peaks.length; i++) {
      var ts = tt[peaks[i]] - t0;
      var ls = Math.log(Math.abs(yy[peaks[i]]));
      sx += ts; sy += ls; sxx += ts * ts; sxy += ts * ls; cnt++;
    }
    var den = cnt * sxx - sx * sx;
    if (Math.abs(den) < 1e-12) return null;
    var slope = (cnt * sxy - sx * sy) / den;
    var intercept = (sy - slope * sx) / cnt;
    var b = -slope;
    if (!(b > 0) || !isFinite(b)) {
      return { A0: Math.exp(intercept), b: 0, y0: 0, r2: 0, n: cnt, peaks: peaks, t0: t0 };
    }
    var A0 = Math.exp(intercept);
    // 对数域 R²
    var mean = sy / cnt, ssRes = 0, ssTot = 0;
    for (i = 0; i < peaks.length; i++) {
      var ts2 = tt[peaks[i]] - t0;
      var ls2 = Math.log(Math.abs(yy[peaks[i]]));
      var model = intercept + slope * ts2;
      ssRes += (ls2 - model) * (ls2 - model);
      ssTot += (ls2 - mean) * (ls2 - mean);
    }
    var r2 = ssTot > 1e-18 ? 1 - ssRes / ssTot : 0;
    // 平均位移作为 y0（包络拟合不直接给平衡位置）
    var sumY = 0;
    for (i = 0; i < n; i++) sumY += yy[i];
    return { A0: A0, b: b, y0: sumY / n, r2: r2, n: cnt, peaks: peaks, t0: t0 };
  }

  function runFit() {
    if (!S.result) { setStatus('请先完成跟踪'); return; }
    var mi = parseInt($('dampMarker').value, 10) || 0;
    var m = S.result.markers[mi];
    if (!m || !m.n) return;
    var start = Math.max(0, Math.min(m.n - 1, parseInt($('dampStart').value, 10) || 0));
    var reqEnd = parseInt($('dampEnd').value, 10);
    if (!isFinite(reqEnd)) reqEnd = m.n - 1;
    var end = Math.min(m.n - 1, Math.max(start + 2, Math.min(m.n - 1, reqEnd)));
    var method = $('dampMethod').value;
    var tt = new Float64Array(end - start + 1);
    var yy = new Float64Array(end - start + 1);
    for (var i = 0; i <= end - start; i++) {
      tt[i] = m.t[start + i] - m.t[start];
      yy[i] = m.dy[start + i];
    }
    var fit = method === 'direct' ? fitDirect(tt, yy) : fitEnvelope(tt, yy);
    if (!fit) {
      setStatus('拟合失败：请扩大拟合区间或更换方法');
      return;
    }
    fit.start = start; fit.end = end; fit.marker = mi; fit.method = method;
    S.fit = fit;
    $('fitB').textContent = fit.b.toFixed(4) + ' s⁻¹';
    $('fitA').textContent = fit.A0.toFixed(3) + ' cm';
    $('fitY0').textContent = fit.y0.toFixed(3) + ' cm';
    $('fitR2').textContent = fit.r2.toFixed(4);
    $('fitN').textContent = fit.n + ' 点';
    $('fitTau').textContent = fit.b > 1e-9 ? (1 / fit.b).toFixed(3) + ' s' : '∞';
    setStatus('阻尼拟合完成：b = ' + fit.b.toFixed(4) + ' s⁻¹（' + (method === 'direct' ? '原版直接拟合' : '包络拟合') + '，R² = ' + fit.r2.toFixed(3) + '）');
    drawCharts();
  }

  /* ============================ 回放 ============================ */
  function startReplay() {
    if (!S.result) return;
    S.replay.active = true;
    S.replay.lastFrame = -1;
    S.replay.lastTs = 0;
    S.replay.t = 0;
    if (S.source === 'video' && video) {
      try { video.currentTime = 0; } catch (e) { }
      var pr = video.play();
      if (pr && pr.catch) pr.catch(function () { });
    }
    setStatus('回放跟踪过程…');
    requestAnimationFrame(replayTick);
  }

  function replayTick(now) {
    if (!S.replay.active) return;
    if (!S.replay.lastTs) S.replay.lastTs = now;
    var dt = (now - S.replay.lastTs) / 1000;
    S.replay.lastTs = now;
    if (dt > 0.2) dt = 0.2;
    S.replay.t += dt;
    var f;
    if (S.source === 'video') {
      f = Math.round((video ? video.currentTime : S.replay.t) * S.fps);
    } else {
      f = Math.round(S.replay.t * DEMO.fps);
    }
    if (f > S.frameCount - 1) f = S.frameCount - 1;
    if (f !== S.replay.lastFrame) {
      S.replay.lastFrame = f;
      S.viewFrame = f;
      if (S.source === 'demo') {
        renderSynthFrame(pctx, f);
      } // 视频模式：proc 已由下面的 drawImage 更新
      if (S.source === 'video' && video) {
        try { pctx.drawImage(video, 0, 0, S.procW, S.procH); } catch (e) { }
      }
      drawDisplay(f);
      updateChartValues();
    }
    var ended = S.source === 'video' ? (video && (video.ended || f >= S.frameCount - 1)) : (f >= S.frameCount - 1);
    if (ended) {
      S.replay.active = false;
      try { if (video) video.pause(); } catch (e) { }
      setStatus('回放结束');
      setHint('回放结束。可在「阻尼系数拟合」面板选择区间并拟合阻尼系数。');
      return;
    }
    requestAnimationFrame(replayTick);
  }

  /* ============================ 视频加载与演示数据 ============================ */
  function resetMarkers() {
    S.markers = [];
    clearResults();
  }

  function setupDemo() {
    S.source = 'demo';
    S.fps = 30;
    S.step = 1;
    S.frameCount = DEMO.frames;
    S.duration = DEMO.frames / DEMO.fps;
    S.scale = parseFloat($('optScale').value) || 0.05;
    S.calibrated = true;
    ensureProc(DEMO.W, DEMO.H);
    resetMarkers();
    S.uiMode = 'idle';
    S.viewFrame = 0;
    renderSynthFrame(pctx, 0);
    drawDisplay(0);
    S.markers = [{ x: demoMarkerX(0), y: demoMarkerY(0), tpl: null }];
    $('sourceLabel').textContent = '内置演示（合成弹簧振子，b = 0.10 s⁻¹）';
    $('videoHint2').textContent = '640 × 480 · 30 fps · 600 帧';
    setHint('内置演示：合成弹簧振子。已自动选中标志物 M1 并开始跟踪——<b>回放</b> 可重现跟踪过程；也可点 <b>加载本地视频</b> 试试自己的视频。');
    setStatus('内置演示：自动跟踪中…');
    readOptions();
    setProg(0);
    S.ready = true;
    startTracking(true);
  }

  function loadVideoFile(file) {
    if (!file) return;
    if (S.videoURL) { try { URL.revokeObjectURL(S.videoURL); } catch (e) { } }
    S.videoURL = URL.createObjectURL(file);
    S.source = 'video';
    S.ready = false;
    resetMarkers();
    setStatus('正在读取视频信息…');
    setProg(0);
    var onMeta = function () {
      readOptions();
      var scale = Math.min(1, 720 / Math.max(1, video.videoWidth));
      var pw = Math.max(2, Math.round(video.videoWidth * scale));
      var ph = Math.max(2, Math.round(video.videoHeight * scale));
      ensureProc(pw, ph);
      S.duration = isFinite(video.duration) ? video.duration : 0;
      S.frameCount = Math.max(2, Math.floor(S.duration * S.fps));
      S.calibrated = false;
      S.uiMode = 'select';
      S.viewFrame = 0;
      S.markers = [];
      $('sourceLabel').textContent = '本地视频：' + file.name + '（' + video.videoWidth + '×' + video.videoHeight + '）';
      $('videoHint2').textContent = pw + ' × ' + ph + ' · 帧数 ' + S.frameCount;
      var drawFirst = function () {
        seekVideo(0).then(function () {
          try { pctx.drawImage(video, 0, 0, S.procW, S.procH); } catch (e) { }
          drawDisplay(0);
          setStatus('已加载视频。请在首帧点击标志物（可点多个），再按「开始跟踪」。');
          setHint('① 在画面上点击要跟踪的标志物（最多 3 个）；② 需要真实尺寸请先「标定坐标系」：点两个参考点并输入实际距离；③ 按「开始跟踪」。' + (S.calibrated ? '' : ' 当前比例尺为默认 ' + S.scale + ' cm/px，可在右上输入框修改。'));
          S.ready = true;
        });
      };
      if (video.readyState >= 2) drawFirst();
      else video.addEventListener('loadeddata', drawFirst, { once: true });
    };
    video.onloadedmetadata = onMeta;
    video.onerror = function () {
      setStatus('视频加载失败：浏览器可能不支持该编码格式。可改用内置演示。');
    };
    video.src = S.videoURL;
  }

  /* ============================ 点击交互 ============================ */
  function onCanvasClick(ev) {
    var rect = main.getBoundingClientRect();
    var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
    var pc = dispToProc(mx, my);
    if (pc[0] < 0 || pc[1] < 0 || pc[0] > S.procW || pc[1] > S.procH) return;
    if (S.busy) { setHint('正在跟踪/计算，请稍候…'); return; }
    if (S.uiMode === 'calib') {
      if (S.calibPts.length >= 2) S.calibPts = [];
      S.calibPts.push([pc[0], pc[1]]);
      drawDisplay(S.viewFrame);
      if (S.calibPts.length === 1) {
        setHint('已选第一个参考点，请点击第二个参考点。');
      } else {
        var dx = S.calibPts[1][0] - S.calibPts[0][0];
        var dy = S.calibPts[1][1] - S.calibPts[0][1];
        var pxDist = Math.sqrt(dx * dx + dy * dy);
        var cm = window.prompt('像素距离 ' + pxDist.toFixed(1) + ' px。请输入两点之间的实际距离（cm）：', '10');
        var cmv = parseFloat(cm);
        if (isFinite(cmv) && cmv > 0) {
          S.scale = cmv / pxDist;
          S.calibrated = true;
          $('optScale').value = S.scale.toFixed(4);
          setStatus('标定完成：1 像素 = ' + S.scale.toFixed(4) + ' cm（' + (1 / S.scale).toFixed(1) + ' px/cm）');
          setHint('标定完成：1 像素 = <b>' + S.scale.toFixed(4) + ' cm</b>。重新跟踪后曲线会按新比例尺换算。');
        } else {
          setHint('未输入有效距离，标定取消。');
        }
        S.uiMode = 'idle';
        S.calibPts = [];
        drawDisplay(S.viewFrame);
      }
      return;
    }
    if (S.uiMode === 'reticle') {
      if (!S.markers.length) S.markers = [{ x: pc[0], y: pc[1], tpl: null }];
      else { S.markers[0].x = pc[0]; S.markers[0].y = pc[1]; }
      clearResults();
      S.uiMode = 'idle';
      drawDisplay(0);
      setStatus('已重新标记标志物 1。按「开始跟踪」重新跟踪。');
      setHint('已重新标记 M1（<b>' + pc[0].toFixed(0) + ', ' + pc[1].toFixed(0) + '</b>）。按「开始跟踪」从首帧重新跟踪。');
      return;
    }
    if (S.uiMode === 'select') {
      if (S.markers.length >= 3) { setHint('最多同时跟踪 3 个标志物。'); return; }
      S.markers.push({ x: pc[0], y: pc[1], tpl: null });
      drawDisplay(0);
      setHint('已选择 ' + S.markers.length + ' 个标志物。继续点击添加（最多 3 个），或按「开始跟踪」。');
    }
  }

  /* ============================ 保存 CSV ============================ */
  function saveCSV() {
    if (!S.result) { setStatus('还没有可保存的跟踪结果'); return; }
    var lines = ['marker,frame,time_s,x_px,y_px,x_cm,y_cm,confidence'];
    for (var i = 0; i < S.result.markers.length; i++) {
      var m = S.result.markers[i];
      for (var j = 0; j < m.n; j++) {
        lines.push([i + 1, m.frames[j], m.t[j].toFixed(5), m.x[j].toFixed(3), m.y[j].toFixed(3),
          m.xcm[j].toFixed(5), m.ycm[j].toFixed(5), m.conf[j].toFixed(4)].join(','));
      }
    }
    var blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'tracker_result.csv';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    setStatus('已导出 CSV（' + (lines.length - 1) + ' 行）');
  }

  /* ============================ 绑定 ============================ */
  function bindUI() {
    $('btnDemo').addEventListener('click', function () {
      if (S.busy) return;
      try { if (video) video.pause(); } catch (e) { }
      setupDemo();
    });
    $('btnLoadVideo').addEventListener('click', function () { $('fileVideo').click(); });
    $('fileVideo').addEventListener('change', function (ev) {
      var f = ev.target.files && ev.target.files[0];
      if (f) loadVideoFile(f);
      ev.target.value = '';
    });
    $('btnTrack').addEventListener('click', function () {
      if (S.busy) return;
      clearResults();
      startTracking(false);
    });
    $('btnReplay').addEventListener('click', function () {
      if (!S.result) { setStatus('请先完成跟踪'); return; }
      startReplay();
    });
    $('btnSave').addEventListener('click', saveCSV);
    $('btnCalib').addEventListener('click', function () {
      if (S.busy) return;
      S.uiMode = 'calib';
      S.calibPts = [];
      drawDisplay(S.viewFrame);
      setHint('标定坐标系：在画面上依次点击 <b>两个参考点</b>（比如标尺两端），然后输入它们的实际距离（cm）。');
      setStatus('标定坐标系：请点击两个参考点');
    });
    $('btnReticle').addEventListener('click', function () {
      if (S.busy) return;
      if (S.source === 'video') {
        seekVideo(0).then(function () {
          try { pctx.drawImage(video, 0, 0, S.procW, S.procH); } catch (e) { }
          S.viewFrame = 0;
          drawDisplay(0);
        });
      } else {
        renderSynthFrame(pctx, 0);
        S.viewFrame = 0;
        drawDisplay(0);
      }
      S.uiMode = 'reticle';
      setHint('重新标记：点击画面设置标志物 M1 的<b>新位置</b>（从首帧开始重新跟踪）。');
      setStatus('重新标记：请在首帧点击 M1 的新位置');
    });
    $('btnFit').addEventListener('click', runFit);
    main.addEventListener('click', onCanvasClick);
    // 数字参数限制
    var numInputs = document.querySelectorAll('#optFps,#optStep,#optTpl,#optSearch,#optConf,#optScale');
    for (var i = 0; i < numInputs.length; i++) {
      numInputs[i].addEventListener('change', function () { readOptions(); if (S.result) drawCharts(); });
    }
    var ro = new ResizeObserver(function () {
      var before = mainW;
      setupMain();
      if (before !== mainW) { drawDisplay(S.viewFrame); drawCharts(); }
    });
    ro.observe(main.parentElement);
    window.addEventListener('resize', function () { setupMain(); drawDisplay(S.viewFrame); drawCharts(); });
  }

  /* ============================ 启动 ============================ */
  main = $('cvMain');
  mctx = main.getContext('2d');
  proc = document.createElement('canvas');
  pctx = proc.getContext('2d', { willReadFrequently: true });
  video = $('vid');
  setupMain();
  bindUI();
  makeChart('chX', 'x');
  makeChart('chY', 'y');
  makeChart('chD', 'd');
  makeChart('chConf', 'conf');
  // 内置演示作为默认数据，打开即可玩
  setTimeout(setupDemo, 120);
})();
