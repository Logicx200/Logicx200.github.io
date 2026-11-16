'use strict';
/* 弹簧-磁铁-线圈 · 电磁阻尼谐振子 —— 移植自 F:\Project\电磁阻尼.py
 * ODE、磁通耦合项、能量记账逐项照搬源码；RK4 固定步长、Canvas 2D、零依赖。 */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var PI = Math.PI;
  var MU0 = 4e-7 * PI;          // 源码 "mu0": 4.0e-7*np.pi
  var H_STEP = 5e-5;            // 网页版固定 RK4 步长（已与 h=2e-6 参考解核对）

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
      renderAll();
    });
  }

  /* ============================ 物理模型（照搬源码） ============================ */
  // dphi_dz_one_turn(z, mu0, m_dipole, a) = -3*mu0*m*a^2*z / (2*(a^2+z^2)^2.5)
  function dphiDz(z, mDip, a) {
    var a2 = a * a;
    var num = -3.0 * MU0 * mDip * a2 * z;
    var den = 2.0 * Math.pow(a2 + z * z, 2.5);
    return num / den;
  }

  var S = [0, 0, 0];          // 状态 [y, v, i]
  var K1 = [0, 0, 0], K2 = [0, 0, 0], K3 = [0, 0, 0], K4 = [0, 0, 0], TMP = [0, 0, 0];

  function derivFinite(s, out, p, Rtot) {
    var dp = dphiDz(s[0] - p.z_coil, p.m_dipole, p.a);
    out[0] = s[1];
    out[1] = (-p.k * s[0] + p.N_turns * s[2] * dp) / p.m;
    out[2] = (-Rtot * s[2] - p.N_turns * dp * s[1]) / p.L;
  }
  function derivOpen(s, out, p) {
    out[0] = s[1];
    out[1] = -p.k * s[0] / p.m;
    out[2] = 0;
  }
  function rk4(s, h, p, Rtot, open) {
    var i;
    if (open) derivOpen(s, K1, p); else derivFinite(s, K1, p, Rtot);
    for (i = 0; i < 3; i++) TMP[i] = s[i] + 0.5 * h * K1[i];
    if (open) derivOpen(TMP, K2, p); else derivFinite(TMP, K2, p, Rtot);
    for (i = 0; i < 3; i++) TMP[i] = s[i] + 0.5 * h * K2[i];
    if (open) derivOpen(TMP, K3, p); else derivFinite(TMP, K3, p, Rtot);
    for (i = 0; i < 3; i++) TMP[i] = s[i] + h * K3[i];
    if (open) derivOpen(TMP, K4, p); else derivFinite(TMP, K4, p, Rtot);
    for (i = 0; i < 3; i++) s[i] += h / 6 * (K1[i] + 2 * K2[i] + 2 * K3[i] + K4[i]);
  }

  /* ============================ 参数 ============================ */
  var params = null;
  var sim = { t: 0, playing: true, speed: 1, tEnd: 8 };
  var CASES = {};              // key -> case data
  var CASE_KEYS = ['five', 'half', 'open'];
  var CASE_STYLE = {
    five: { color: '#c4633f', label: 'R_ext = 5 Ω（R_tot = 7 Ω）' },
    half: { color: '#7b6fae', label: 'R_ext = 0.5 Ω（R_tot = 2.5 Ω）' },
    open: { color: '#b08a2e', label: '断路 open（i ≡ 0）' }
  };
  var focusKey = 'five';

  function readParams() {
    function num(id, fallback) {
      var el = $(id);
      var v = el ? parseFloat(el.value) : NaN;
      return isFinite(v) ? v : fallback;
    }
    function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
    var p = {
      m: clamp(num('p_m', 0.05), 0.005, 2),
      k: clamp(num('p_k', 20), 1, 500),
      m_dipole: clamp(num('p_md', 0.3), 0.01, 5),
      N_turns: Math.round(clamp(num('p_N', 500), 10, 5000)),
      a: clamp(num('p_a', 0.01), 0.002, 0.05),
      L: clamp(num('p_L', 0.001), 0.0001, 0.1),
      R_coil: clamp(num('p_Rc', 2), 0.1, 50),
      y0: clamp(num('p_y0', 0.03), 0.002, 0.05),
      v0: clamp(num('p_v0', 0), -5, 5),
      t_end: clamp(num('p_tend', 8), 1, 20),
      z_coil: 0
    };
    // 回写输入框，避免非法值留在界面上
    var write = { p_m: p.m, p_k: p.k, p_md: p.m_dipole, p_N: p.N_turns, p_a: p.a, p_L: p.L, p_Rc: p.R_coil, p_y0: p.y0, p_v0: p.v0, p_tend: p.t_end };
    for (var k in write) { if ($(k)) $(k).value = String(write[k]); }
    return p;
  }

  /* ============================ 积分 ============================ */
  function integrateCase(p, Rext, nRecTarget) {
    var open = !isFinite(Rext);
    var Rtot = open ? Infinity : p.R_coil + Rext;
    var tEnd = p.t_end;
    var N = Math.round(tEnd / H_STEP);
    var stride = Math.max(1, Math.round(N / nRecTarget));
    var nRec = Math.floor(N / stride) + 1;
    var tArr = new Float32Array(nRec), yArr = new Float32Array(nRec), vArr = new Float32Array(nRec);
    var iArr = new Float32Array(nRec), emfArr = new Float32Array(nRec);
    var emArr = new Float32Array(nRec), elArr = new Float32Array(nRec), heatArr = new Float32Array(nRec);
    var s = [p.y0, p.v0, 0];
    var heat = 0;
    var pPrev = open ? 0 : s[2] * s[2] * Rtot;
    var rec = 0;
    tArr[0] = 0; yArr[0] = s[0]; vArr[0] = s[1]; iArr[0] = s[2];
    emfArr[0] = -p.N_turns * dphiDz(s[0] - p.z_coil, p.m_dipole, p.a) * s[1];
    emArr[0] = 0.5 * p.m * s[1] * s[1] + 0.5 * p.k * s[0] * s[0];
    elArr[0] = open ? 0 : 0.5 * p.L * s[2] * s[2];
    heatArr[0] = 0;
    for (var n = 0; n < N; n++) {
      rk4(s, H_STEP, p, Rtot, open);
      if (!open) {
        var pNow = s[2] * s[2] * Rtot;
        heat += 0.5 * (pPrev + pNow) * H_STEP;
        pPrev = pNow;
      }
      if ((n + 1) % stride === 0) {
        rec++;
        if (rec >= nRec) break;
        var t = (n + 1) * H_STEP;
        tArr[rec] = t;
        yArr[rec] = s[0]; vArr[rec] = s[1]; iArr[rec] = s[2];
        emfArr[rec] = -p.N_turns * dphiDz(s[0] - p.z_coil, p.m_dipole, p.a) * s[1];
        emArr[rec] = 0.5 * p.m * s[1] * s[1] + 0.5 * p.k * s[0] * s[0];
        elArr[rec] = open ? 0 : 0.5 * p.L * s[2] * s[2];
        heatArr[rec] = heat;
      }
    }
    var out = {
      key: '', label: '', Rext: Rext, Rtot: Rtot, open: open,
      t: tArr, y: yArr, v: vArr, i: iArr, emf: emfArr,
      Emech: emArr, EL: elArr, heat: heatArr,
      n: rec + 1, dtRec: stride * H_STEP,
      E0: 0.5 * p.k * p.y0 * p.y0 + 0.5 * p.m * p.v0 * p.v0,
      zeta: 0, bEnv: 0, peakCount: 0, drift: 0
    };
    // 包络拟合：|y| 的局部极大值 -> ln(A) = ln(A0) - b t，ζ = b/ω0
    var peaks = [];
    for (var j = 1; j < out.n - 1; j++) {
      var a0 = Math.abs(yArr[j - 1]), a1 = Math.abs(yArr[j]), a2 = Math.abs(yArr[j + 1]);
      if (a1 >= a0 && a1 > a2 && a1 > 1e-4) peaks.push(j);
    }
    out.peakCount = peaks.length;
    if (peaks.length >= 3) {
      var sx = 0, sy = 0, sxx = 0, sxy = 0, cnt = 0;
      for (var q = 0; q < peaks.length; q++) {
        var ti = tArr[peaks[q]], ai = Math.log(Math.abs(yArr[peaks[q]]));
        sx += ti; sy += ai; sxx += ti * ti; sxy += ti * ai; cnt++;
      }
      var den = cnt * sxx - sx * sx;
      if (Math.abs(den) > 1e-12) {
        var slope = (cnt * sxy - sx * sy) / den;
        var b = -slope;
        if (b > 0 && isFinite(b)) {
          out.bEnv = b;
          out.zeta = b / Math.sqrt(p.k / p.m);
        }
      }
    }
    // 能量守恒检查
    var maxDev = 0;
    for (var r = 0; r < out.n; r++) {
      var Et = emArr[r] + elArr[r] + heatArr[r];
      var dev = Math.abs(Et - out.E0);
      if (dev > maxDev) maxDev = dev;
    }
    out.drift = out.E0 > 1e-12 ? maxDev / out.E0 : 0;
    return out;
  }

  function computeAll() {
    params = readParams();
    sim.tEnd = params.t_end;
    var nRec = Math.min(4200, Math.max(800, Math.ceil(params.t_end / 0.002)));
    var specs = [
      ['five', 5.0],
      ['half', 0.5],
      ['open', Infinity]
    ];
    for (var i = 0; i < specs.length; i++) {
      var key = specs[i][0], Rext = specs[i][1];
      var c = integrateCase(params, Rext, nRec);
      c.key = key;
      c.label = CASE_STYLE[key].label;
      CASES[key] = c;
    }
    computeRanges();
    // 场景竖直范围（所有工况的位移包络 + 固定架余量）
    var maxY = -1e9, minY = 1e9;
    for (var j = 0; j < CASE_KEYS.length; j++) {
      var cd = CASES[CASE_KEYS[j]];
      for (var q = 0; q < cd.n; q++) {
        if (cd.y[q] > maxY) maxY = cd.y[q];
        if (cd.y[q] < minY) minY = cd.y[q];
      }
    }
    SCENE.top = Math.max(0.03, maxY) + 0.012;
    SCENE.bot = minY - 0.008;
    sim.t = 0;
    sim.playing = true;
    updatePlayState();
    updateCaseLegend();
    updateStaticReadouts();
    renderAll();
  }

  /* ============================ 曲线范围 ============================ */
  var RANGES = { y: 30, v: 1, i: 0.1, emf: 0.5 };
  function computeRanges() {
    var keys = CASE_KEYS, i, k, c;
    var yMax = 1e-6, vMax = 1e-6, iMax = 1e-9, eMax = 1e-9;
    for (i = 0; i < keys.length; i++) {
      c = CASES[keys[i]];
      for (k = 0; k < c.n; k++) {
        var ay = Math.abs(c.y[k]) * 1000;
        if (ay > yMax) yMax = ay;
        var av = Math.abs(c.v[k]);
        if (av > vMax) vMax = av;
        var ai = Math.abs(c.i[k]);
        if (ai > iMax) iMax = ai;
        var ae = Math.abs(c.emf[k]);
        if (ae > eMax) eMax = ae;
      }
    }
    RANGES.y = Math.max(1, yMax * 1.12);
    RANGES.v = Math.max(1e-3, vMax * 1.12);
    RANGES.i = Math.max(1e-3, iMax * 1.12);
    RANGES.emf = Math.max(1e-3, eMax * 1.12);
  }

  /* ============================ 画布与图表 ============================ */
  var scene = { canvas: null, ctx: null, w: 0, h: 0, dpr: 1 };

  function setupCanvas(obj) {
    var rect = obj.host.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) return false;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var W = Math.round(rect.width), H = Math.round(rect.height);
    if (W === obj.w && H === obj.h && dpr === obj.dpr) return false;
    obj.w = W; obj.h = H; obj.dpr = dpr;
    obj.canvas.width = Math.round(W * dpr);
    obj.canvas.height = Math.round(H * dpr);
    obj.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return true;
  }

  var charts = [];
  function makeChart(hostId, canvasId, key, label, fmt) {
    var canvas = $(canvasId);
    var ch = {
      key: key, label: label, fmt: fmt,
      canvas: canvas,
      ctx: canvas.getContext('2d'),
      host: canvas.parentElement,
      w: 0, h: 0, dpr: 1
    };
    charts.push(ch);
    if (typeof ResizeObserver !== 'undefined') {
      var ro = new ResizeObserver(function () { if (setupCanvas(ch)) { if (params && CASES[focusKey]) renderAll(); } });
      ro.observe(ch.host);
    }
    setupCanvas(ch);
    return ch;
  }

  function niceTick(v) {
    if (v === 0) return '0';
    var a = Math.abs(v);
    if (a >= 100) return v.toFixed(0);
    if (a >= 10) return v.toFixed(v % 1 === 0 ? 0 : 1);
    if (a >= 1) return v.toFixed(2);
    if (a >= 0.01) return v.toFixed(3);
    return v.toExponential(1);
  }

  function chartData(ch) {
    var c = CASES[focusKey];
    var scale = ch.key === 'y' ? 1000 : 1;    // y 用 mm
    return { caseData: c, scale: scale, range: RANGES[ch.key] };
  }

  function drawChart(ch) {
    if (!ch.w || !ch.h) return;
    var focusData = CASES[focusKey];
    if (!focusData || !focusData.n) return;
    var c = ch.ctx, W = ch.w, H = ch.h;
    c.clearRect(0, 0, W, H);
    var info = chartData(ch);
    var data = info.caseData;
    var range = info.range;
    var pad = { l: 44, r: 12, t: 8, b: 18 };
    var iw = Math.max(10, W - pad.l - pad.r);
    var ih = Math.max(10, H - pad.t - pad.b);
    var x0 = pad.l, y0 = pad.t;
    function mapX(t) { return x0 + t / sim.tEnd * iw; }
    function mapY(v) { return y0 + (1 - (v + range) / (2 * range)) * ih; }

    // 网格
    c.lineWidth = 1;
    c.strokeStyle = PAL.rule;
    c.font = '10px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    var xt = 4, k;
    for (k = 1; k < xt; k++) {
      var gx = Math.round(mapX(sim.tEnd * k / xt)) + 0.5;
      c.beginPath(); c.moveTo(gx, y0); c.lineTo(gx, y0 + ih); c.stroke();
    }
    var yt = [range, range / 2, 0, -range / 2, -range];
    for (k = 0; k < yt.length; k++) {
      var gy = Math.round(mapY(yt[k])) + 0.5;
      c.strokeStyle = yt[k] === 0 ? PAL.ruleStrong : PAL.rule;
      c.beginPath(); c.moveTo(x0, gy); c.lineTo(x0 + iw, gy); c.stroke();
    }
    // 刻度
    c.fillStyle = PAL.ink3;
    c.textAlign = 'right';
    c.fillText(niceTick(range), x0 - 5, y0 + 5);
    c.fillText('0', x0 - 5, y0 + ih / 2);
    c.fillText(niceTick(-range), x0 - 5, y0 + ih - 5);
    c.textAlign = 'center';
    c.fillText('0', x0, y0 + ih + 9);
    c.fillText(sim.tEnd.toFixed(1) + ' s', x0 + iw, y0 + ih + 9);

    // 其它工况（淡色）
    var showCompare = $('optCompare') ? $('optCompare').checked : true;
    var keys = CASE_KEYS.slice();
    function plotCase(key, alpha, width) {
      var cd = CASES[key];
      var arr = ch.key === 'y' ? cd.y : cd[ch.key];
      var sc = info.scale;
      c.beginPath();
      var nn = cd.n, step = Math.max(1, Math.floor(nn / 600));
      for (var j = 0; j < nn; j += step) {
        var px = mapX(cd.t[j]);
        var py = mapY(arr[j] * sc);
        if (j === 0) c.moveTo(px, py); else c.lineTo(px, py);
      }
      c.lineWidth = width;
      c.globalAlpha = alpha;
      c.strokeStyle = CASE_STYLE[key].color;
      c.stroke();
      c.globalAlpha = 1;
    }
    if (showCompare) {
      for (k = 0; k < keys.length; k++) {
        if (keys[k] !== focusKey) plotCase(keys[k], 0.34, 1);
      }
    }
    // 焦点工况：只画到当前时刻
    var arr = ch.key === 'y' ? data.y : data[ch.key];
    var sc = info.scale;
    var idx = Math.min(data.n - 1, Math.max(0, Math.round(sim.t / data.dtRec)));
    c.beginPath();
    var step = Math.max(1, Math.floor((idx + 1) / 700));
    for (var j = 0; j <= idx; j += step) {
      var px2 = mapX(data.t[j]);
      var py2 = mapY(arr[j] * sc);
      if (j === 0) c.moveTo(px2, py2); else c.lineTo(px2, py2);
    }
    c.lineWidth = 1.8;
    c.strokeStyle = PAL.accent;
    c.stroke();
    // 当前点
    var cx = mapX(data.t[idx]), cy = mapY(arr[idx] * sc);
    c.fillStyle = PAL.accent;
    c.beginPath(); c.arc(cx, cy, 2.6, 0, PI * 2); c.fill();
    c.fillStyle = PAL.paper;
    c.beginPath(); c.arc(cx, cy, 1.1, 0, PI * 2); c.fill();
  }

  function drawCharts() {
    for (var i = 0; i < charts.length; i++) drawChart(charts[i]);
  }

  /* ============================ 场景动画 ============================ */
  var SCENE = { top: 0.06, bot: -0.055 };
  function currentSample() {
    var cd = CASES[focusKey];
    var x = sim.t / cd.dtRec;
    var i0 = Math.floor(x);
    if (i0 < 0) i0 = 0;
    if (i0 > cd.n - 2) i0 = Math.max(0, cd.n - 2);
    var f = Math.min(1, Math.max(0, x - i0));
    var i1 = Math.min(cd.n - 1, i0 + 1);
    return {
      y: cd.y[i0] + (cd.y[i1] - cd.y[i0]) * f,
      v: cd.v[i0] + (cd.v[i1] - cd.v[i0]) * f,
      i: cd.i[i0] + (cd.i[i1] - cd.i[i0]) * f,
      emf: cd.emf[i0] + (cd.emf[i1] - cd.emf[i0]) * f,
      data: cd
    };
  }

  function drawScene() {
    var c = scene.ctx;
    if (!c || !params) return;
    var W = scene.w, H = scene.h;
    c.clearRect(0, 0, W, H);
    var smp = currentSample();
    var y = smp.y, cur = smp.i;
    var a = params.a;
    var coilH = Math.max(0.04, 4 * a);
    var wall = 0.004;
    var magnetH = 0.02;
    var magnetW = Math.min(0.8 * (2 * a), 0.03);
    var topAnchor = SCENE.top;      // 固定架高度（由位移包络决定，留有弹簧余量）
    var rangeY = SCENE.top - SCENE.bot;
    var scale = Math.min((H - 32) / rangeY, W * 0.9 / 0.13);
    var midX = W * 0.5;
    var topPix = 16 + (H - 32 - rangeY * scale) / 2;
    function px(x) { return midX + x * scale; }
    function py(yy) { return topPix + (SCENE.top - yy) * scale; }

    // 背景水平参考线
    c.lineWidth = 1;
    c.font = '10px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    c.textAlign = 'right';
    c.textBaseline = 'middle';
    for (var mm = -40; mm <= 60; mm += 20) {
      var yy = mm / 1000;
      var lineY = Math.round(py(yy)) + 0.5;
      c.strokeStyle = PAL.rule;
      c.beginPath(); c.moveTo(24, lineY); c.lineTo(W - 16, lineY); c.stroke();
      c.fillStyle = PAL.ink3;
      c.fillText(mm + '', 20, lineY);
    }
    // 线圈中心 / 平衡位置
    c.strokeStyle = PAL.ruleStrong;
    c.setLineDash([4, 4]);
    var eqY = Math.round(py(0)) + 0.5;
    c.beginPath(); c.moveTo(24, eqY); c.lineTo(W - 16, eqY); c.stroke();
    c.setLineDash([]);
    c.save();
    c.translate(10, py(0));
    c.rotate(-PI / 2);
    c.textAlign = 'center';
    c.fillStyle = PAL.ink3;
    c.fillText('y (mm)', 0, 0);
    c.restore();

    // 顶部固定架
    var topY = Math.round(py(topAnchor)) + 0.5;
    c.strokeStyle = PAL.ink;
    c.lineWidth = 3;
    c.beginPath();
    c.moveTo(px(-0.05), topY); c.lineTo(px(0.05), topY);
    c.stroke();
    c.lineWidth = 1;
    c.strokeStyle = PAL.ruleStrong;
    for (var s = -4; s <= 4; s++) {
      c.beginPath();
      c.moveTo(px(s * 0.011), topY);
      c.lineTo(px(s * 0.011 + 0.006), topY - 5);
      c.stroke();
    }

    // 弹簧（源码 spring_polyline：从固定点到磁铁上沿；折数随长度变化，避免压缩时糊成一片）
    var springBottom = y + magnetH / 2;
    var springLen = Math.max(0.002, topAnchor - springBottom);
    var nZigs = Math.max(4, Math.min(12, Math.round(springLen / 0.006)));
    c.strokeStyle = PAL.ink2;
    c.lineWidth = 1.4;
    c.beginPath();
    var steps = 2 * nZigs + 1;
    for (var k = 0; k < steps; k++) {
      var frac = k / (steps - 1);
      var sy = topAnchor + (springBottom - topAnchor) * frac;
      var sx;
      if (k === 0 || k === steps - 1) sx = 0;
      else sx = (k % 2 === 1 ? 1 : -1) * 0.011;
      var X = px(sx), Y = py(sy);
      if (k === 0) c.moveTo(X, Y); else c.lineTo(X, Y);
    }
    c.stroke();

    // 线圈（套管）
    var outerHalf = a + wall;
    var coilTop = py(0 + coilH / 2), coilBot = py(0 - coilH / 2);
    c.fillStyle = 'rgba(70, 130, 200, 0.13)';
    c.strokeStyle = 'rgb(70, 130, 200)';
    c.lineWidth = 1.6;
    c.beginPath();
    c.rect(px(-outerHalf), coilTop, (2 * outerHalf) * scale, coilBot - coilTop);
    c.fill(); c.stroke();
    // 内孔（用背景色盖住）
    c.fillStyle = PAL.paper;
    c.beginPath();
    c.rect(px(-a), coilTop, (2 * a) * scale, coilBot - coilTop);
    c.fill();
    c.strokeStyle = 'rgba(70, 130, 200, 0.55)';
    c.lineWidth = 1;
    c.setLineDash([3, 4]);
    c.beginPath();
    c.moveTo(px(-a), coilTop); c.lineTo(px(-a), coilBot);
    c.moveTo(px(a), coilTop); c.lineTo(px(a), coilBot);
    c.stroke();
    c.setLineDash([]);
    // 线圈标注
    c.fillStyle = 'rgb(70, 130, 200)';
    c.textAlign = 'left';
    c.textBaseline = 'middle';
    c.font = '10px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    c.fillText('N = ' + params.N_turns + ' 匝', px(outerHalf) + 8, coilTop + 10);
    c.fillText('a = ' + (a * 1000).toFixed(0) + ' mm', px(outerHalf) + 8, coilTop + 24);

    // 磁铁
    var mx = px(-magnetW / 2), my = py(y + magnetH / 2);
    c.fillStyle = '#c0392b';
    c.strokeStyle = '#7d2419';
    c.lineWidth = 1.2;
    c.beginPath();
    c.rect(mx, my, magnetW * scale, magnetH * scale);
    c.fill(); c.stroke();
    c.fillStyle = 'rgba(255,255,255,0.92)';
    c.font = 'bold 10px "Microsoft YaHei", system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    c.fillText('N', px(0), py(y + magnetH * 0.25));
    c.fillText('S', px(0), py(y - magnetH * 0.25));

    var dp = dphiDz(y, params.m_dipole, a);
    var dpMax = 0.4295 * MU0 * params.m_dipole / (a * a);   // |dΦ/dz| 的理论峰值

    // B 场 / 磁通箭头
    if ($('optB') && $('optB').checked) {
      // 外部偶极场线（示意）
      c.strokeStyle = 'rgba(70, 130, 200, 0.35)';
      c.lineWidth = 1;
      for (var side = -1; side <= 1; side += 2) {
        c.beginPath();
        c.moveTo(px(side * magnetW * 0.4), py(y + magnetH * 0.5));
        c.bezierCurveTo(
          px(side * 0.055), py(y + 0.03),
          px(side * 0.055), py(y - 0.03),
          px(side * magnetW * 0.4), py(y - magnetH * 0.5)
        );
        c.stroke();
      }
      // 线圈内磁通方向箭头：长度 ∝ |dΦ/dz|
      var mag = Math.min(1, Math.abs(dp) / (dpMax + 1e-30));
      var dir = dp >= 0 ? 1 : -1;
      var arrowLen = (coilH * 0.62) * (0.25 + 0.75 * mag);
      c.strokeStyle = 'rgba(47, 111, 94, 0.85)';
      c.fillStyle = 'rgba(47, 111, 94, 0.85)';
      c.lineWidth = 1.4;
      var arX = px(a * 0.5);
      var ay0 = py(0 + dir * arrowLen / 2), ay1 = py(0 - dir * arrowLen / 2);
      c.beginPath(); c.moveTo(arX, ay0); c.lineTo(arX, ay1); c.stroke();
      // 箭头
      c.beginPath();
      c.moveTo(arX, py(0 - dir * arrowLen / 2));
      c.lineTo(arX - 4, py(0 - dir * arrowLen / 2) + dir * 7);
      c.lineTo(arX + 4, py(0 - dir * arrowLen / 2) + dir * 7);
      c.closePath(); c.fill();
      c.fillStyle = PAL.ink3;
      c.textAlign = 'right';
      c.fillText('dΦ/dz ' + (dp >= 0 ? '+' : '−'), px(-outerHalf) - 8, coilTop + 24);
    }
    // 感应电流方向
    if ($('optI') && $('optI').checked && Math.abs(cur) > 1e-9) {
      var idir = cur >= 0 ? 1 : -1;
      c.strokeStyle = 'rgb(70, 130, 200)';
      c.fillStyle = 'rgb(70, 130, 200)';
      c.lineWidth = 1.6;
      var xl = px(-outerHalf), xr = px(outerHalf);
      function arrowAt(x, yPix, dirY, alpha) {
        c.globalAlpha = alpha;
        c.beginPath();
        c.moveTo(x, yPix + dirY * 6);
        c.lineTo(x - 4, yPix);
        c.lineTo(x + 4, yPix);
        c.closePath(); c.fill();
        c.globalAlpha = 1;
      }
      // 左边缘与右边缘电流方向相反（与 i 的符号有关）
      c.globalAlpha = 0.85;
      for (var q = 0; q < 3; q++) {
        var yc = coilTop + (coilBot - coilTop) * (0.25 + q * 0.25);
        arrowAt(xl, yc, idir, 0.85);
        arrowAt(xr, yc, -idir, 0.85);
      }
      c.globalAlpha = 1;
      c.fillStyle = 'rgb(70, 130, 200)';
      c.textAlign = 'right';
      c.fillText('I = ' + (cur * 1000).toFixed(1) + ' mA', px(-outerHalf) - 8, coilTop + 10);
    }

    // 电磁力箭头（F_em = N·i·dΦ/dz），画在磁铁左侧，避免和线圈参数标注重叠
    var fem = params.N_turns * cur * dp;
    if (Math.abs(fem) > 1e-4) {
      var fdir = fem >= 0 ? 1 : -1;
      var lenPx = Math.min(60, Math.max(8, Math.abs(fem) * 120));
      var fx = px(-magnetW * 0.5 - 0.008);
      var fy = py(y);
      c.strokeStyle = '#d98c3a';
      c.fillStyle = '#d98c3a';
      c.lineWidth = 1.6;
      c.beginPath(); c.moveTo(fx, fy); c.lineTo(fx, fy - fdir * lenPx); c.stroke();
      c.beginPath();
      c.moveTo(fx, fy - fdir * lenPx);
      c.lineTo(fx - 4, fy - fdir * lenPx + fdir * 7);
      c.lineTo(fx + 4, fy - fdir * lenPx + fdir * 7);
      c.closePath(); c.fill();
      c.textAlign = 'right';
      c.fillText('F = ' + fem.toFixed(3) + ' N', fx - 5, fy - fdir * lenPx - 8);
    }

    // 图例
    c.textAlign = 'left';
    c.textBaseline = 'middle';
    c.font = '10px "Microsoft YaHei", "PingFang SC", system-ui, sans-serif';
    c.fillStyle = PAL.ink3;
    c.fillText('t = ' + sim.t.toFixed(2) + ' s   y = ' + (y * 1000).toFixed(2) + ' mm   i = ' + (cur * 1000).toFixed(1) + ' mA', 26, H - 12);
  }

  /* ============================ 界面 ============================ */
  function setText(id, t) { var el = $(id); if (el) el.textContent = t; }

  function updatePlayState() {
    setText('playState', sim.playing ? '播放中' : (sim.t >= sim.tEnd - 1e-9 ? '播放结束' : '已暂停'));
    var b = $('btnPlay');
    if (b) b.textContent = sim.playing ? '暂停' : (sim.t >= sim.tEnd - 1e-9 ? '重播' : '继续');
    setText('sceneHint', 't = ' + sim.t.toFixed(2) + ' s');
    setText('chartsHint', 't = ' + sim.t.toFixed(2) + ' s / ' + sim.tEnd.toFixed(2) + ' s');
  }

  function updateCaseLegend() {
    var host = $('caseLegend');
    if (!host) return;
    var html = '';
    for (var i = 0; i < CASE_KEYS.length; i++) {
      var k = CASE_KEYS[i];
      var bold = k === focusKey ? ' style="color:var(--ink)"' : '';
      html += '<span' + bold + '><i style="background:' + CASE_STYLE[k].color + '"></i>' + CASE_STYLE[k].label + '</span>';
    }
    host.innerHTML = html;
  }

  function updateStaticReadouts() {
    var p = params;
    var wn = Math.sqrt(p.k / p.m);
    setText('roWn', wn.toFixed(2) + ' rad/s');
    setText('roTau', (p.L / (p.R_coil + 5)).toExponential(2) + ' s');
    var cd = CASES[focusKey];
    setText('roZeta', cd.open ? '0（无电流）' : cd.zeta.toFixed(4));
    setText('roDrift', (cd.drift * 100).toFixed(3) + ' %');
  }

  function updateReadouts() {
    var cd = CASES[focusKey];
    if (!params || !cd || !cd.n) return;
    var idx = Math.min(cd.n - 1, Math.max(0, Math.round(sim.t / cd.dtRec)));
    var y = cd.y[idx], v = cd.v[idx], i = cd.i[idx], emf = cd.emf[idx];
    var Emech = cd.Emech[idx], heat = cd.heat[idx], Et = Emech + cd.EL[idx] + heat;
    setText('roEmech', cd.E0 > 0 ? (Emech / cd.E0 * 100).toFixed(2) + ' %' : '—');
    setText('roHeat', cd.E0 > 0 ? (heat / cd.E0 * 100).toFixed(2) + ' %' : '—');
    setText('roY', (y * 1000).toFixed(2) + ' mm');
    setText('roV', v.toFixed(4) + ' m/s');
    setText('roI', (i * 1000).toFixed(2) + ' mA');
    setText('roEmf', emf.toFixed(4) + ' V');
    setText('valY', (y * 1000).toFixed(2));
    setText('valV', v.toFixed(3));
    setText('valI', i.toFixed(4));
    setText('valEMF', emf.toFixed(3));
    // 更新场景顶部提示
    setText('sceneHint', 't = ' + sim.t.toFixed(2) + ' s');
    setText('chartsHint', 't = ' + sim.t.toFixed(2) + ' s / ' + sim.tEnd.toFixed(2) + ' s');
  }

  function renderAll() {
    drawScene();
    drawCharts();
  }

  /* ============================ 播放循环 ============================ */
  var lastFrame = 0, lastUI = 0;
  function loop(now) {
    if (!lastFrame) lastFrame = now;
    var dt = (now - lastFrame) / 1000;
    lastFrame = now;
    if (dt > 0.1) dt = 0.1;
    if (dt < 0) dt = 0;
    if (sim.playing && params && CASES[focusKey]) {
      sim.t += dt * sim.speed;
      if (sim.t >= sim.tEnd) { sim.t = sim.tEnd; sim.playing = false; updatePlayState(); }
      renderAll();
      updatePlayState();
    }
    if (now - lastUI > 110 && params && CASES[focusKey]) { updateReadouts(); lastUI = now; }
    requestAnimationFrame(loop);
  }

  /* ============================ 交互 ============================ */
  function bindUI() {
    var btnApply = $('btnApply');
    if (btnApply) btnApply.addEventListener('click', applyParams);
    // 输入框回车/失焦后不自动重算，避免误触；按钮显式触发
    var inputs = document.querySelectorAll('.param-grid input[type="number"]');
    for (var i = 0; i < inputs.length; i++) {
      inputs[i].addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter') { ev.preventDefault(); applyParams(); }
      });
    }
    var rext = $('p_rext');
    if (rext) {
      rext.addEventListener('change', function () {
        focusKey = rext.value === 'open' ? 'open' : (rext.value === '0.5' ? 'half' : 'five');
        updateCaseLegend();
        updateStaticReadouts();
        updateReadouts();
        renderAll();
      });
    }
    var play = $('btnPlay');
    if (play) {
      play.addEventListener('click', function () {
        if (!CASES[focusKey]) return;
        if (sim.t >= sim.tEnd - 1e-9) { sim.t = 0; }
        sim.playing = !sim.playing;
        updatePlayState();
        renderAll();
      });
    }
    var replay = $('btnReplay');
    if (replay) {
      replay.addEventListener('click', function () {
        sim.t = 0; sim.playing = true;
        updatePlayState(); renderAll();
      });
    }
    var speed = $('playSpeed');
    if (speed) {
      speed.addEventListener('change', function () {
        sim.speed = parseFloat(speed.value) || 1;
      });
    }
    var toggles = ['optB', 'optI', 'optCompare'];
    for (var t = 0; t < toggles.length; t++) {
      var el = $(toggles[t]);
      if (el) el.addEventListener('change', renderAll);
    }
    // 空格暂停
    document.addEventListener('keydown', function (ev) {
      if (ev.code !== 'Space') return;
      var tg = ev.target;
      if (tg && tg.closest && tg.closest('input, select, textarea, button')) return;
      ev.preventDefault();
      var b = $('btnPlay'); if (b) b.click();
    });
  }

  var computing = false;
  function applyParams() {
    if (computing) return;
    computing = true;
    setText('playState', '计算中…');
    var btn = $('btnApply');
    if (btn) btn.disabled = true;
    // 让 UI 先显示“计算中”
    setTimeout(function () {
      try {
        computeAll();
        updateReadouts();
        setText('playState', '播放中');
      } catch (err) {
        setText('playState', '计算失败');
        if (window.console) console.error(err);
      } finally {
        computing = false;
        if (btn) btn.disabled = false;
      }
    }, 30);
  }

  /* ============================ 启动 ============================ */
  scene.canvas = $('cvScene');
  scene.ctx = scene.canvas.getContext('2d');
  scene.host = scene.canvas.parentElement;
  if (typeof ResizeObserver !== 'undefined') {
    var ro = new ResizeObserver(function () {
      if (setupCanvas(scene) && params && CASES[focusKey]) { renderAll(); }
    });
    ro.observe(scene.host);
  }
  setupCanvas(scene);
  makeChart('chYHost', 'chY', 'y', '位移 y (mm)', null);
  makeChart('chVHost', 'chV', 'v', '速度 v (m/s)', null);
  makeChart('chIHost', 'chI', 'i', '电流 i (A)', null);
  makeChart('chEMFHost', 'chEMF', 'emf', '电动势 EMF (V)', null);
  bindUI();
  applyParams();
  requestAnimationFrame(loop);
})();
