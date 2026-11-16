'use strict';
/* 双摆混沌 · 多轨迹相空间 —— 移植自 F:\Project\双摆.py
 * 运动方程逐项照搬源码；RK4 固定步长、Canvas 2D 手绘、零依赖。 */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var PI = Math.PI;
  var DEG = PI / 180;

  /* ============================ 主题色 ============================ */
  var PAL = null;
  function readPalette() {
    var cs = getComputedStyle(document.documentElement);
    function v(n, fb) {
      var s = cs.getPropertyValue(n).trim();
      return s || fb;
    }
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
      drawAll();
    });
  }

  /* ============================ 参数 ============================ */
  var cfg = {
    mode: 'perturb',          // perturb | wide
    base1: 90 * DEG,
    base2: 90 * DEG,
    delta: 0.573 * DEG,       // 微扰幅度（源码 0.01 rad）
    spread: 150 * DEG,        // 大角度散布
    L1: 1.0,
    L2: 1.0,
    ratio: 1.0,               // m2 / m1
    gamma: 0.0,
    count: 100,
    speed: 1.0,
    tEnd: 30.0,
    seed: 42
  };

  /* ============================ 随机数 ============================ */
  function mulberry32(seed) {
    var a = seed | 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /* ============================ plasma 色带 ============================ */
  var PLASMA = [
    [13, 8, 135], [84, 2, 163], [139, 10, 165], [185, 50, 137],
    [219, 92, 104], [244, 136, 73], [254, 188, 43], [240, 249, 33]
  ];
  function plasma(t, alpha) {
    t = t < 0 ? 0 : (t > 1 ? 1 : t);
    var x = t * (PLASMA.length - 1);
    var i = Math.floor(x), f = x - i;
    var a = PLASMA[i], b = PLASMA[Math.min(i + 1, PLASMA.length - 1)];
    var r = Math.round(a[0] + (b[0] - a[0]) * f);
    var g = Math.round(a[1] + (b[1] - a[1]) * f);
    var bl = Math.round(a[2] + (b[2] - a[2]) * f);
    return alpha == null ? 'rgb(' + r + ',' + g + ',' + bl + ')'
      : 'rgba(' + r + ',' + g + ',' + bl + ',' + alpha + ')';
  }

  /* ============================ 状态 ============================ */
  var sim = {
    t: 0, paused: false, ended: false,
    states: [],        // 每条轨迹一个 Float64Array(4): [θ1, ω1, θ2, ω2]
    colors: [],        // 每条轨迹的 css 颜色
    off1: [], off2: [],// 初始偏移（弧度）
    mags: [],          // 初始偏移模长
    n: 0
  };

  /* ============================ 画布 ============================ */
  var panelDefs = [
    { id: 'cvPhys', kind: 'phys' },
    { id: 'cvP1', kind: 'p1' },
    { id: 'cvP2', kind: 'p2' },
    { id: 'cvTheta', kind: 'config' },
    { id: 'cvOmega', kind: 'vel' }
  ];
  var panels = [];

  function makePanels() {
    for (var i = 0; i < panelDefs.length; i++) {
      (function (def) {
        var canvas = $(def.id);
        if (!canvas) return;
        var p = {
          kind: def.kind,
          canvas: canvas,
          ctx: canvas.getContext('2d'),
          host: canvas.parentElement,
          w: 0, h: 0, dpr: 1,
          trail: document.createElement('canvas'),
          tctx: null,
          g: null,
          prevX: null, prevY: null, prevOK: null
        };
        panels.push(p);
        if (typeof ResizeObserver !== 'undefined') {
          var ro = new ResizeObserver(function () { resizePanel(p); });
          ro.observe(p.host);
        }
        resizePanel(p);
      })(panelDefs[i]);
    }
  }

  function ensurePrev(p) {
    if (p.prevX && p.prevX.length === Math.max(1, sim.n)) return;
    p.prevX = new Float32Array(Math.max(1, sim.n));
    p.prevY = new Float32Array(Math.max(1, sim.n));
    p.prevOK = new Uint8Array(Math.max(1, sim.n));
    p.prevOK.fill(0);
  }

  function resizePanel(p) {
    var rect = p.host.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) return;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var W = Math.round(rect.width), H = Math.round(rect.height);
    if (W === p.w && H === p.h && dpr === p.dpr && p.tctx) return;
    p.w = W; p.h = H; p.dpr = dpr;
    p.canvas.width = Math.round(W * dpr);
    p.canvas.height = Math.round(H * dpr);
    p.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    p.trail.width = p.canvas.width;
    p.trail.height = p.canvas.height;
    p.tctx = p.trail.getContext('2d');
    p.tctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    p.tctx.lineCap = 'round';
    p.tctx.lineJoin = 'round';
    ensurePrev(p);
    computeGeometry(p);
    if (p.prevOK) p.prevOK.fill(0);
    drawAll();
  }

  function computeGeometry(p) {
    var pad = p.kind === 'phys'
      ? { l: 38, r: 15, t: 14, b: 28 }
      : { l: 46, r: 16, t: 14, b: 34 };
    var iw = Math.max(10, p.w - pad.l - pad.r);
    var ih = Math.max(10, p.h - pad.t - pad.b);
    var g = { pad: pad, iw: iw, ih: ih };
    if (p.kind === 'phys') {
      var half = (cfg.L1 + cfg.L2) * 1.22;
      g.half = half;
      g.cx = pad.l + iw / 2;
      g.cy = pad.t + ih / 2;
      g.scale = Math.min(iw, ih) / (2 * half);
    } else if (p.kind === 'p1' || p.kind === 'p2') {
      g.xr = PI; g.yr = 20;
    } else if (p.kind === 'config') {
      g.xr = PI; g.yr = PI;
    } else {
      g.xr = 20; g.yr = 20;
    }
    p.g = g;
  }

  /* 世界坐标 -> 屏幕坐标，结果写入 out[0], out[1] */
  function project(p, a, b, out) {
    var g = p.g;
    if (p.kind === 'phys') {
      out[0] = g.cx + a * g.scale;
      out[1] = g.cy - b * g.scale;
    } else {
      out[0] = g.pad.l + (a + g.xr) / (2 * g.xr) * g.iw;
      out[1] = g.pad.t + (1 - (b + g.yr) / (2 * g.yr)) * g.ih;
    }
    return out;
  }

  /* ============================ 初始条件 ============================ */
  function resetSim() {
    sim.t = 0;
    sim.paused = false;
    sim.ended = false;
    sim.n = cfg.count;
    var rng = mulberry32(cfg.seed);
    sim.states = new Array(sim.n);
    sim.colors = new Array(sim.n);
    sim.off1 = new Array(sim.n);
    sim.off2 = new Array(sim.n);
    sim.mags = new Array(sim.n);
    var amp = cfg.mode === 'wide' ? cfg.spread : cfg.delta;
    var maxMag = 1e-12;
    var i;
    for (i = 0; i < sim.n; i++) {
      var o1 = (rng() * 2 - 1) * amp;
      var o2 = (rng() * 2 - 1) * amp;
      var th1 = cfg.base1 + o1;
      var th2 = cfg.base2 + o2;
      sim.states[i] = Float64Array.from([th1, 0, th2, 0]);
      sim.off1[i] = th1 - cfg.base1;
      sim.off2[i] = th2 - cfg.base2;
      var mag = Math.sqrt(sim.off1[i] * sim.off1[i] + sim.off2[i] * sim.off2[i]);
      sim.mags[i] = mag;
      if (mag > maxMag) maxMag = mag;
    }
    // 颜色：按初始偏移模长排序后在 plasma 色带上渐变（与源码“颜色表示偏移大小”的语义一致）
    var order = [];
    for (i = 0; i < sim.n; i++) order.push(i);
    order.sort(function (a, b) { return sim.mags[a] - sim.mags[b]; });
    for (i = 0; i < sim.n; i++) {
      var rank = sim.n > 1 ? i / (sim.n - 1) : 1;
      sim.colors[order[i]] = plasma(0.14 + 0.86 * rank);
    }
    for (i = 0; i < panels.length; i++) {
      var p = panels[i];
      if (p.tctx) p.tctx.clearRect(0, 0, p.w, p.h);
      if (p.prevOK) p.prevOK.fill(0);
      computeGeometry(p);
      ensurePrev(p);
    }
    updateStats(true);
    drawAll();
    updatePlayButton();
  }

  /* ============================ RK4 积分 ============================ */
  var K1 = new Float64Array(4), K2 = new Float64Array(4), K3 = new Float64Array(4), K4 = new Float64Array(4);
  var TMP = new Float64Array(4), ACC = new Float64Array(2);

  function accel(s, out) {
    var L1 = cfg.L1, L2 = cfg.L2, m1 = 1, m2 = cfg.ratio, g = 9.81;
    var th1 = s[0], w1 = s[1], th2 = s[2], w2 = s[3];
    var delta = th2 - th1;
    var sd = Math.sin(delta), cd = Math.cos(delta);
    var denom1 = (m1 + m2) * L1 - m2 * L1 * cd * cd;   // 源码 denom1
    var denom2 = (L2 / L1) * denom1;                    // 源码 denom2
    var z1 = (m2 * L1 * w1 * w1 * sd * cd +
      m2 * g * Math.sin(th2) * cd +
      m2 * L2 * w2 * w2 * sd -
      (m1 + m2) * g * Math.sin(th1)) / denom1;
    var z2 = (-m2 * L2 * w2 * w2 * sd * cd +
      (m1 + m2) * (g * Math.sin(th1) * cd - L1 * w1 * w1 * sd - g * Math.sin(th2))) / denom2;
    out[0] = z1 - cfg.gamma * w1;   // 阻尼项为网页版新增，默认 γ=0 与源码一致
    out[1] = z2 - cfg.gamma * w2;
  }

  function rk4Step(s, h) {
    var i;
    K1[0] = s[1]; K1[2] = s[3];
    accel(s, ACC); K1[1] = ACC[0]; K1[3] = ACC[1];
    for (i = 0; i < 4; i++) TMP[i] = s[i] + 0.5 * h * K1[i];
    K2[0] = TMP[1]; K2[2] = TMP[3];
    accel(TMP, ACC); K2[1] = ACC[0]; K2[3] = ACC[1];
    for (i = 0; i < 4; i++) TMP[i] = s[i] + 0.5 * h * K2[i];
    K3[0] = TMP[1]; K3[2] = TMP[3];
    accel(TMP, ACC); K3[1] = ACC[0]; K3[3] = ACC[1];
    for (i = 0; i < 4; i++) TMP[i] = s[i] + h * K3[i];
    K4[0] = TMP[1]; K4[2] = TMP[3];
    accel(TMP, ACC); K4[1] = ACC[0]; K4[3] = ACC[1];
    for (i = 0; i < 4; i++) s[i] += h / 6 * (K1[i] + 2 * K2[i] + 2 * K3[i] + K4[i]);
  }

  /* ============================ 轨迹记录（离屏画布增量绘制） ============================ */
  var P0 = [0, 0], P1 = [0, 0];

  function clipPlot(p, ctx) {
    var g = p.g;
    ctx.save();
    ctx.beginPath();
    ctx.rect(g.pad.l, g.pad.t, g.iw, g.ih);
    ctx.clip();
  }

  function sampleTrails() {
    var i, j, p;
    for (j = 0; j < panels.length; j++) {
      p = panels[j];
      p.tctx.save();
      p.tctx.lineWidth = p.kind === 'phys' ? 0.8 : 0.55;
      p.tctx.globalAlpha = p.kind === 'phys' ? 0.45 : 0.32;
      clipPlot(p, p.tctx);
    }
    for (i = 0; i < sim.n; i++) {
      var s = sim.states[i];
      var col = sim.colors[i];
      var th1 = s[0], w1 = s[1], th2 = s[2], w2 = s[3];
      var x1 = cfg.L1 * Math.sin(th1);
      var y1 = -cfg.L1 * Math.cos(th1);
      var x2 = x1 + cfg.L2 * Math.sin(th2);
      var y2 = y1 - cfg.L2 * Math.cos(th2);
      for (j = 0; j < panels.length; j++) {
        p = panels[j];
        if (j === 0) project(p, x2, y2, P0);
        else if (j === 1) project(p, th1, w1, P0);
        else if (j === 2) project(p, th2, w2, P0);
        else if (j === 3) project(p, th1, th2, P0);
        else project(p, w1, w2, P0);
        if (p.prevOK[i]) {
          p.tctx.beginPath();
          p.tctx.moveTo(p.prevX[i], p.prevY[i]);
          p.tctx.lineTo(P0[0], P0[1]);
          p.tctx.strokeStyle = col;
          p.tctx.stroke();
        }
        p.prevX[i] = P0[0];
        p.prevY[i] = P0[1];
        p.prevOK[i] = 1;
      }
    }
    for (j = 0; j < panels.length; j++) {
      p = panels[j];
      p.tctx.restore();
      p.tctx.globalAlpha = 1;
    }
  }

  /* ============================ 绘制 ============================ */
  function line(x1, y1, x2, y2) {
    var c = this;
    c.beginPath(); c.moveTo(x1, y1); c.lineTo(x2, y2); c.stroke();
  }

  function drawPanelBackground(p) {
    var c = p.ctx, g = p.g;
    c.clearRect(0, 0, p.w, p.h);
    c.lineWidth = 1;
    c.strokeStyle = PAL.rule;
    c.fillStyle = PAL.ink3;
    c.font = '10.5px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';

    if (p.kind === 'phys') {
      var half = g.half;
      var k;
      // 背景网格
      for (k = -Math.floor(half); k <= Math.floor(half); k++) {
        var px = Math.round(project(p, k, 0, P0)[0]) + 0.5;
        line.call(c, px, g.pad.t, px, g.pad.t + g.ih);
        var py = Math.round(project(p, 0, k, P1)[1]) + 0.5;
        line.call(c, g.pad.l, py, g.pad.l + g.iw, py);
      }
      // 坐标轴
      c.strokeStyle = PAL.ruleStrong;
      c.setLineDash([4, 4]);
      var ox = Math.round(project(p, 0, 0, P0)[0]) + 0.5;
      var oy = Math.round(project(p, 0, 0, P1)[1]) + 0.5;
      line.call(c, g.pad.l, oy, g.pad.l + g.iw, oy);
      line.call(c, ox, g.pad.t, ox, g.pad.t + g.ih);
      c.setLineDash([]);
      // 刻度与轴名
      c.fillStyle = PAL.ink3;
      for (k = -Math.floor(half); k <= Math.floor(half); k++) {
        if (k === 0) continue;
        var tx = project(p, k, 0, P0)[0];
        if (tx > g.pad.l + 8 && tx < g.pad.l + g.iw - 8) {
          c.fillText(String(k), tx, g.pad.t + g.ih + 10);
        }
      }
      c.fillStyle = PAL.ink2;
      c.fillText('x (m)', g.pad.l + g.iw / 2, g.pad.t + g.ih + 22);
      c.save();
      c.translate(12, g.pad.t + g.ih / 2);
      c.rotate(-PI / 2);
      c.fillText('y (m)', 0, 0);
      c.restore();
    } else {
      var nx = 4, ny = 4, a, b;
      for (a = 1; a < nx; a++) {
        var gx = g.pad.l + g.iw * a / nx;
        line.call(c, Math.round(gx) + 0.5, g.pad.t, Math.round(gx) + 0.5, g.pad.t + g.ih);
      }
      for (b = 1; b < ny; b++) {
        var gy = g.pad.t + g.ih * b / ny;
        line.call(c, g.pad.l, Math.round(gy) + 0.5, g.pad.l + g.iw, Math.round(gy) + 0.5);
      }
      // 零轴
      c.strokeStyle = PAL.ruleStrong;
      c.setLineDash([4, 4]);
      var zx = Math.round(g.pad.l + g.iw / 2) + 0.5;
      var zy = Math.round(g.pad.t + g.ih / 2) + 0.5;
      line.call(c, zx, g.pad.t, zx, g.pad.t + g.ih);
      line.call(c, g.pad.l, zy, g.pad.l + g.iw, zy);
      c.setLineDash([]);
      // 刻度文字
      c.fillStyle = PAL.ink3;
      var xl, yl;
      if (p.kind === 'config') { xl = ['−π', '0', 'π']; yl = ['−π', '0', 'π']; }
      else if (p.kind === 'vel') { xl = ['−20', '0', '20']; yl = ['−20', '0', '20']; }
      else { xl = ['−π', '0', 'π']; yl = ['−20', '0', '20']; }
      var xs = [g.pad.l, g.pad.l + g.iw / 2, g.pad.l + g.iw];
      var ys = [g.pad.t + g.ih, g.pad.t + g.ih / 2, g.pad.t];
      for (a = 0; a < 3; a++) {
        c.fillText(xl[a], xs[a], g.pad.t + g.ih + 10);
        c.textAlign = 'right';
        c.fillText(yl[a], g.pad.l - 7, ys[a]);
        c.textAlign = 'center';
      }
      // 轴名
      var xn, yn;
      if (p.kind === 'p1') { xn = 'θ₁ (rad)'; yn = 'ω₁ (rad/s)'; }
      else if (p.kind === 'p2') { xn = 'θ₂ (rad)'; yn = 'ω₂ (rad/s)'; }
      else if (p.kind === 'config') { xn = 'θ₁ (rad)'; yn = 'θ₂ (rad)'; }
      else { xn = 'ω₁ (rad/s)'; yn = 'ω₂ (rad/s)'; }
      c.fillStyle = PAL.ink2;
      c.fillText(xn, g.pad.l + g.iw / 2, g.pad.t + g.ih + 25);
      c.save();
      c.translate(12, g.pad.t + g.ih / 2);
      c.rotate(-PI / 2);
      c.fillText(yn, 0, 0);
      c.restore();
    }
  }

  function drawLegend(p) {
    var c = p.ctx;
    var lines = [
      '轨迹总数 ' + sim.n,
      '基准 θ₁ = ' + (cfg.base1 / DEG).toFixed(1) + '°,  θ₂ = ' + (cfg.base2 / DEG).toFixed(1) + '°',
      cfg.mode === 'wide' ? '大角度散布 ±' + (cfg.spread / DEG).toFixed(0) + '°'
        : '初始偏移 ±' + (cfg.delta / DEG).toFixed(2) + '°',
      '颜色 = 初始偏移大小（排序渐变色带）',
      't = ' + sim.t.toFixed(1) + ' s'
    ];
    c.font = '10.5px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    var w = 0, i;
    for (i = 0; i < lines.length; i++) w = Math.max(w, c.measureText(lines[i]).width);
    var bw = w + 18, bh = lines.length * 15 + 10;
    var x = p.g.pad.l + 6, y = p.g.pad.t + 6;
    c.globalAlpha = 0.92;
    c.fillStyle = PAL.paper3;
    c.fillRect(x, y, bw, bh);
    c.globalAlpha = 1;
    c.strokeStyle = PAL.ruleStrong;
    c.lineWidth = 1;
    c.strokeRect(x + 0.5, y + 0.5, bw, bh);
    c.fillStyle = PAL.ink2;
    c.textAlign = 'left';
    c.textBaseline = 'middle';
    for (i = 0; i < lines.length; i++) {
      c.fillText(lines[i], x + 9, y + 12 + i * 15);
    }
    c.textAlign = 'center';
  }

  function drawPoints() {
    var i, j, p, s, th1, th2, w1, w2, x2, y2;
    for (j = 0; j < panels.length; j++) {
      p = panels[j];
      var c = p.ctx;
      clipPlot(p, c);
      c.globalAlpha = 0.82;
      for (i = 0; i < sim.n; i++) {
        s = sim.states[i];
        th1 = s[0]; w1 = s[1]; th2 = s[2]; w2 = s[3];
        if (p.kind === 'phys') {
          x2 = cfg.L1 * Math.sin(th1) + cfg.L2 * Math.sin(th2);
          y2 = -cfg.L1 * Math.cos(th1) - cfg.L2 * Math.cos(th2);
          project(p, x2, y2, P0);
          c.fillStyle = sim.colors[i];
          c.beginPath(); c.arc(P0[0], P0[1], 1.7, 0, PI * 2); c.fill();
        } else {
          var a, b;
          if (p.kind === 'p1') { a = th1; b = w1; }
          else if (p.kind === 'p2') { a = th2; b = w2; }
          else if (p.kind === 'config') { a = th1; b = th2; }
          else { a = w1; b = w2; }
          project(p, a, b, P0);
          c.fillStyle = sim.colors[i];
          c.beginPath(); c.arc(P0[0], P0[1], 1.35, 0, PI * 2); c.fill();
        }
      }
      c.globalAlpha = 1;
      c.restore();
    }
  }

  function drawPhysicalRods() {
    var p = null, i;
    for (i = 0; i < panels.length; i++) if (panels[i].kind === 'phys') { p = panels[i]; break; }
    if (!p) return;
    var c = p.ctx;
    project(p, 0, 0, P0);
    var ox = P0[0], oy = P0[1];
    c.lineWidth = 0.9;
    c.globalAlpha = 0.42;
    for (i = 0; i < sim.n; i++) {
      var s = sim.states[i];
      var x1 = cfg.L1 * Math.sin(s[0]);
      var y1 = -cfg.L1 * Math.cos(s[0]);
      var x2 = x1 + cfg.L2 * Math.sin(s[2]);
      var y2 = y1 - cfg.L2 * Math.cos(s[2]);
      project(p, x1, y1, P0);
      project(p, x2, y2, P1);
      c.strokeStyle = sim.colors[i];
      c.beginPath();
      c.moveTo(ox, oy);
      c.lineTo(P0[0], P0[1]);
      c.lineTo(P1[0], P1[1]);
      c.stroke();
      c.fillStyle = sim.colors[i];
      c.beginPath(); c.arc(P0[0], P0[1], 1.9, 0, PI * 2); c.fill();
      c.beginPath(); c.arc(P1[0], P1[1], 2.5, 0, PI * 2); c.fill();
    }
    c.globalAlpha = 1;
    // 悬挂点
    c.fillStyle = PAL.accent;
    c.beginPath(); c.arc(ox, oy, 3.6, 0, PI * 2); c.fill();
    c.strokeStyle = PAL.ink;
    c.lineWidth = 1;
    c.beginPath(); c.arc(ox, oy, 5.6, 0, PI * 2); c.stroke();
  }

  function drawAll() {
    var i;
    for (i = 0; i < panels.length; i++) {
      drawPanelBackground(panels[i]);
      var p = panels[i];
      p.ctx.drawImage(p.trail, 0, 0, p.w, p.h);
    }
    drawPoints();
    drawPhysicalRods();
    for (i = 0; i < panels.length; i++) {
      if (panels[i].kind === 'phys') drawLegend(panels[i]);
    }
  }

  /* ============================ 动画循环 ============================ */
  var lastFrame = 0;
  var lastStats = 0;

  function loop(now) {
    if (!lastFrame) lastFrame = now;
    var dtReal = (now - lastFrame) / 1000;
    lastFrame = now;
    if (dtReal > 0.06) dtReal = 0.06;
    if (dtReal < 0) dtReal = 0;

    var moved = false;
    if (!sim.paused && !sim.ended) {
      var remain = dtReal * cfg.speed;
      var guard = 0;
      while (remain > 1e-9 && guard < 200) {
        var h = remain > 0.0015 ? 0.0015 : remain;
        for (var i = 0; i < sim.n; i++) rk4Step(sim.states[i], h);
        remain -= h;
        guard++;
      }
      sim.t += dtReal * cfg.speed;
      if (sim.t >= cfg.tEnd) {
        sim.t = cfg.tEnd;
        sim.ended = true;
        updatePlayButton();
      }
      moved = true;
    }
    if (moved) sampleTrails();
    drawAll();
    if (now - lastStats > 140) {
      updateStats(false);
      lastStats = now;
    }
    requestAnimationFrame(loop);
  }

  /* ============================ 界面 ============================ */
  function setText(id, txt) {
    var el = $(id);
    if (el) el.textContent = txt;
  }

  function updateStats(full) {
    var maxOmega = 0, i;
    for (i = 0; i < sim.n; i++) {
      var s = sim.states[i];
      var w = Math.max(Math.abs(s[1]), Math.abs(s[3]));
      if (w > maxOmega) maxOmega = w;
    }
    setText('stStatus', sim.paused ? '已暂停' : (sim.ended ? '已结束' : '运行中'));
    setText('stTime', sim.t.toFixed(1));
    setText('stEnd', cfg.tEnd.toFixed(1));
    setText('stCount', String(sim.n));
    setText('stSeed', String(cfg.seed));
    setText('stOmega', maxOmega.toFixed(1) + ' rad/s');
    setText('physHint', 't = ' + sim.t.toFixed(1) + ' s');
    if (full) {
      var o1min = 0, o1max = 0, o2min = 0, o2max = 0;
      for (i = 0; i < sim.n; i++) {
        if (sim.off1[i] < o1min) o1min = sim.off1[i];
        if (sim.off1[i] > o1max) o1max = sim.off1[i];
        if (sim.off2[i] < o2min) o2min = sim.off2[i];
        if (sim.off2[i] > o2max) o2max = sim.off2[i];
      }
      var f = function (v) { return (v / DEG).toFixed(3) + '°'; };
      setText('stMode', cfg.mode === 'wide' ? '大角度宽散布' : '微扰模式');
      setText('stOff1', f(o1min) + ' ~ ' + f(o1max));
      setText('stOff2', f(o2min) + ' ~ ' + f(o2max));
    }
  }

  function updatePlayButton() {
    var b = $('btnPlay');
    if (!b) return;
    if (sim.ended) { b.textContent = '重新开始'; }
    else if (sim.paused) { b.textContent = '继续'; }
    else { b.textContent = '暂停'; }
  }

  function bindRange(id, onInput, onChange) {
    var el = $(id);
    if (!el) return;
    el.addEventListener('input', function () { onInput(el.value); });
    if (onChange) el.addEventListener('change', function () { onChange(el.value); });
  }

  function bindUI() {
    // 模式
    var modeSel = $('mode');
    if (modeSel) {
      modeSel.addEventListener('change', function () {
        cfg.mode = modeSel.value;
        $('deltaField').hidden = cfg.mode === 'wide';
        $('spreadField').hidden = cfg.mode !== 'wide';
        resetSim();
      });
    }
    bindRange('base1', function (v) { cfg.base1 = parseFloat(v) * DEG; setText('base1Out', parseFloat(v).toFixed(0) + '°'); }, resetSim);
    bindRange('base2', function (v) { cfg.base2 = parseFloat(v) * DEG; setText('base2Out', parseFloat(v).toFixed(0) + '°'); }, resetSim);
    bindRange('delta', function (v) { cfg.delta = parseFloat(v) * DEG; setText('deltaOut', parseFloat(v).toFixed(2) + '°'); }, resetSim);
    bindRange('spread', function (v) { cfg.spread = parseFloat(v) * DEG; setText('spreadOut', parseFloat(v).toFixed(0) + '°'); }, resetSim);
    bindRange('L1', function (v) { cfg.L1 = parseFloat(v); setText('L1Out', cfg.L1.toFixed(2) + ' m'); }, resetSim);
    bindRange('L2', function (v) { cfg.L2 = parseFloat(v); setText('L2Out', cfg.L2.toFixed(2) + ' m'); }, resetSim);
    bindRange('ratio', function (v) { cfg.ratio = parseFloat(v); setText('ratioOut', cfg.ratio.toFixed(2)); }, resetSim);
    bindRange('gamma', function (v) { cfg.gamma = parseFloat(v); setText('gammaOut', cfg.gamma.toFixed(2)); }, null);
    bindRange('count', function (v) { cfg.count = parseInt(v, 10); setText('countOut', String(cfg.count)); }, resetSim);
    bindRange('speed', function (v) { cfg.speed = parseFloat(v); setText('speedOut', cfg.speed.toFixed(2) + '×'); }, null);
    bindRange('tEnd', function (v) { cfg.tEnd = parseFloat(v); setText('tEndOut', cfg.tEnd.toFixed(0) + ' s'); }, resetSim);

    // 按钮
    var play = $('btnPlay');
    if (play) {
      play.addEventListener('click', function () {
        if (sim.ended) { resetSim(); return; }
        sim.paused = !sim.paused;
        updatePlayButton();
        updateStats(false);
      });
    }
    var reset = $('btnReset');
    if (reset) reset.addEventListener('click', function () { resetSim(); });
    var reseed = $('btnReseed');
    if (reseed) reseed.addEventListener('click', function () {
      cfg.seed = (cfg.seed * 16807 + 1) % 2147483647;
      resetSim();
    });

    // 空格暂停
    document.addEventListener('keydown', function (ev) {
      if (ev.code !== 'Space') return;
      var t = ev.target;
      if (t && t.closest && t.closest('input, select, textarea, button')) return;
      ev.preventDefault();
      if (sim.ended) { resetSim(); }
      else { sim.paused = !sim.paused; updatePlayButton(); }
    });
  }

  /* ============================ 启动 ============================ */
  makePanels();
  bindUI();
  $('deltaField').hidden = false;
  $('spreadField').hidden = true;
  resetSim();
  updateStats(true);
  requestAnimationFrame(loop);
})();
