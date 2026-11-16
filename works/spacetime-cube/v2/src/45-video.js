/* 时空立方体 · 视频抽帧
 *
 * 目标：**把一个视频变成一串帧**，交给下游的堆叠流程 —— 与照片完全同等对待。
 * 硬要求是「每一帧都要保留」，所以这里的默认行为是：
 *
 *   逐帧播放，每呈现一帧就抓一帧；抓不过来就主动降速/暂停，绝不丢帧。
 *
 * 为什么不用"按固定时间间隔 seek 抽帧"？因为 seek 只能落到关键帧附近再解码，
 * 抽出来的时间点既不均匀也不等于真实帧时刻，而且更慢。真正"每一帧"的定义只有一个：
 * **浏览器解码器实际呈现过的那些帧**，而那正好是 requestVideoFrameCallback 的回调。
 *
 * ⚠️ 这里有一个**必须**讲清楚的坑，也是第一版踩过的：
 * 把视频帧搬进内存要一次拷贝（createImageBitmap），4K 一帧就是 30 MB 量级。
 * 第一版在回调里 `await` 拷贝完才登记下一帧的回调 —— 那等于每帧都把整条回调链
 * 卡住几十毫秒，浏览器于是把"来不及呈现"的帧通通丢掉。用户实测：300 多帧的视频
 * 丢掉 233 帧，只剩 92 帧。
 *
 * 所以现在的做法是两条：
 *   1. **回调链永不被我们的处理阻塞**：进回调就先登记下一帧的回调，
 *      拷贝异步排队（多画布轮转，保证快照不会互相覆盖）；
 *   2. **背压**：积压到一定程度就降低播放速度（必要时暂停），
 *      解码器于是不再丢帧 —— 代价是总耗时可能超过视频时长，但一帧不少。
 */
(function (STC) {
  'use strict';

  var VIDEO_RE = /\.(mp4|m4v|mov|webm|ogv|ogg|mkv|avi|3gp|m2ts|mts)$/i;

  function isVideo(file) {
    return /^video\//.test(file.type || '') || VIDEO_RE.test(file.name || '');
  }

  var PROBE_SECONDS = 2.0;      // 探测：看够 2 秒媒体时间就足够反推帧率
  var PROBE_MAX_FRAMES = 150;   // 探测的帧数上限（高帧率视频也不会探太久）
  var FALLBACK_FPS = 30;        // 探测不出帧率时的保守估计

  function videoEl() {
    var v = document.createElement('video');
    v.muted = true;
    v.defaultMuted = true;
    v.playsInline = true;
    v.preload = 'auto';
    if (v.setAttribute) {
      v.setAttribute('muted', '');
      v.setAttribute('playsinline', '');
    }
    return v;
  }

  function once(el, name) {
    return new Promise(function (resolve, reject) {
      function ok() { off(); resolve(); }
      function bad() {
        off();
        var e = el.error;
        reject(new Error('视频加载失败' +
          (e && (e.message || e.code) ? '：' + (e.message || ('code ' + e.code)) : '（这个格式浏览器解不了？）')));
      }
      function off() {
        el.removeEventListener(name, ok);
        el.removeEventListener('error', bad);
      }
      el.addEventListener(name, ok);
      el.addEventListener('error', bad);
    });
  }

  /** 读元信息：尺寸与时长（不解码画面，很快） */
  async function meta(file) {
    var url = URL.createObjectURL(file);
    var v = videoEl();
    try {
      v.src = url;
      try {
        await once(v, 'loadedmetadata');
      } catch (e) {
        throw new Error((file.name || '视频') + '：' + (e && e.message || e));
      }
      var w = v.videoWidth || 0, h = v.videoHeight || 0;
      if (!w || !h) throw new Error('拿不到视频尺寸：' + (file.name || '') + '（格式不被浏览器支持？）');
      return {
        width: w, height: h,
        duration: isFinite(v.duration) ? v.duration : 0,
        name: file.name || ''
      };
    } finally {
      try { if (v.removeAttribute) v.removeAttribute('src'); if (v.load) v.load(); } catch (e) { /* 忽略 */ }
      URL.revokeObjectURL(url);
    }
  }

  /**
   * 跑一遍视频，按需要抓帧。
   *
   * @param {File} file
   * @param {object} o
   *   longEdge    目标长边（0 = 原始尺寸）
   *   limit       最多保留多少帧（0/undefined = 不限）
   *   keepEvery   每 N 个呈现帧保留 1 个（默认 1 = 全部保留）
   *   wantPixels  false 时只数帧、不建位图（探测用）
   *   stopAfter   媒体时间达到这个秒数就停（探测用）
   *   poolSize    画布池大小（默认 6；池子决定"能积压多少帧拷贝"）
   *   onProgress  ({frames, seen, time, duration, inflight, playbackRate}) => void
   *   signal      {cancelled}
   */
  async function run(file, o) {
    o = o || {};
    var url = URL.createObjectURL(file);
    var v = videoEl();
    var wantPixels = o.wantPixels !== false;
    var res = {
      frames: [], width: 0, height: 0, duration: 0,
      drawnW: 0, drawnH: 0,
      seen: 0, dropped: 0, decoded: 0,
      method: 'rvfc', stopped: false, mediaEnd: 0,
      keepEvery: Math.max(1, o.keepEvery || 1),
      limit: o.limit > 0 ? o.limit : Infinity,
      // 背压与吞吐的诊断信息（"为什么慢"必须可查）
      maxInflight: 0, throttles: 0, pauses: 0, direct: false, failedBitmaps: 0
    };
    try {
      v.src = url;
      try {
        await once(v, 'loadedmetadata');
      } catch (e) {
        throw new Error((file.name || '视频') + '：' + (e && e.message || e));
      }
      res.width = v.videoWidth || 0;
      res.height = v.videoHeight || 0;
      res.duration = isFinite(v.duration) ? v.duration : 0;
      if (!res.width || !res.height) {
        throw new Error('拿不到视频尺寸：' + (file.name || '') + '（格式不被浏览器支持？）');
      }

      var scale = o.longEdge > 0 ? Math.min(1, o.longEdge / Math.max(res.width, res.height)) : 1;
      res.drawnW = Math.max(1, Math.round(res.width * scale));
      res.drawnH = Math.max(1, Math.round(res.height * scale));

      /*
       * 画布池 + 背压。池子大小 - 1 就是暂停阈值，
       * 这样"下一个回调到来时一定有一块空画布"，绝不因为没画布而丢帧。
       */
      var POOL = Math.max(2, o.poolSize || 6);
      var SLOW_AT = 2;
      var PAUSE_AT = POOL - 1;
      var pool = [];
      var poolAt = 0;
      var pending = [];
      var inflight = 0;
      var paused = false;

      if (wantPixels) {
        for (var pi = 0; pi < POOL; pi++) {
          var cv = document.createElement('canvas');
          cv.width = res.drawnW;
          cv.height = res.drawnH;
          var c2d = cv.getContext('2d', { alpha: false });
          if (!c2d) throw new Error('拿不到 2D 上下文，无法抽取视频帧');
          pool.push({ canvas: cv, ctx: c2d });
        }
      }

      var stopResolve = null;
      var stopPromise = new Promise(function (r) { stopResolve = r; });
      function stop() {
        if (res.stopped) return;
        res.stopped = true;
        try { v.pause(); } catch (e) { /* 忽略 */ }
        if (stopResolve) stopResolve();
      }

      /** 按积压量调整播放速度：跟不上就降速，快用满池子就暂停 */
      function throttle() {
        if (!wantPixels || res.stopped) return;
        var want = inflight >= PAUSE_AT ? 0.0625 : (inflight >= SLOW_AT ? 0.25 : 1);
        if (Math.abs((v.playbackRate || 1) - want) > 1e-6) {
          try { v.playbackRate = want; res.throttles++; } catch (e) { /* 忽略 */ }
        }
        if (inflight >= PAUSE_AT && !paused && !v.paused) {
          paused = true;
          res.pauses++;
          try { v.pause(); } catch (e) { /* 忽略 */ }
        } else if (inflight <= 1 && paused) {
          paused = false;
          try { v.play(); } catch (e) { /* 忽略 */ }
        }
      }

      /** 抓当前这一帧：同步取快照，异步拷贝，**不阻塞回调链** */
      function grab() {
        if (o.signal && o.signal.cancelled) { stop(); return; }
        var keep = ((res.seen - 1) % res.keepEvery) === 0;
        var t = v.currentTime;
        res.seen++;
        res.mediaEnd = t;

        if (keep) {
          if (res.frames.length >= res.limit) { stop(); return; }
          var rec = {
            bitmap: null, width: res.drawnW, height: res.drawnH,
            time: t, index: res.frames.length
          };
          res.frames.push(rec);
          if (wantPixels) {
            var entry = pool[poolAt];
            poolAt = (poolAt + 1) % POOL;
            var p;
            if (res.direct) {
              // 一步到位：直接从 <video> 取快照并缩放，省掉整帧的 canvas 拷贝
              p = createImageBitmap(v, {
                resizeWidth: res.drawnW, resizeHeight: res.drawnH, resizeQuality: 'medium',
                premultiplyAlpha: 'none', colorSpaceConversion: 'none'
              });
            } else {
              entry.ctx.drawImage(v, 0, 0, res.drawnW, res.drawnH);
              p = createImageBitmap(entry.canvas, {
                premultiplyAlpha: 'none', colorSpaceConversion: 'none'
              });
            }
            inflight++;
            if (inflight > res.maxInflight) res.maxInflight = inflight;
            pending.push(p.then(function (bmp) {
              rec.bitmap = bmp;
              inflight--;
              throttle();
            }, function (err) {
              // 单帧拷贝失败不能拖垮整段：记下来，最后如实报告
              rec.error = err && err.message || String(err);
              res.failedBitmaps++;
              inflight--;
              throttle();
            }));
            throttle();
          }
        }

        if (o.onProgress) {
          o.onProgress({
            frames: res.frames.length, seen: res.seen, time: t, duration: res.duration,
            inflight: inflight, playbackRate: v.playbackRate || 1
          });
        }
        if (o.stopAfter > 0 && t >= o.stopAfter) stop();
      }

      function play() {
        var p = v.play();
        // 自动播放可能被拒（没有用户手势时）。被拒就直接报错，而不是静默卡住。
        if (p && p.catch) p.catch(function (e) { stop(); res.playError = e && e.message || String(e); });
      }

      /**
       * 探一下"能不能直接从 <video> 取快照并缩放"（Chrome 支持，个别浏览器不支持）。
       * 探到了就能省掉整帧 canvas 拷贝 —— 这是吞吐量最大的一项优化。
       */
      function probeDirect() {
        if (!wantPixels || res.direct || res.directTried) return;
        res.directTried = true;
        try {
          var t = createImageBitmap(v, { resizeWidth: 8, resizeHeight: 8, resizeQuality: 'low' });
          if (t && t.then) {
            t.then(function (b) {
              /*
               * 光"能解析"不够：还要它**真的按我们要的尺寸缩放**。
               * 个别实现会忽略 resize*（返回原生尺寸），那样帧的记账尺寸
               * 与实际位图就不一致了 —— 宁可退回 canvas 路径。
               */
              var ok = b && b.width === 8 && b.height === 8;
              res.direct = !!ok;
              if (b && b.close) b.close();
              if (!ok) res.directRejected = true;
            }, function () { res.direct = false; });
          }
        } catch (e) { res.direct = false; }
      }

      if (typeof v.requestVideoFrameCallback === 'function') {
        var onFrame = function () {
          if (res.stopped) return;
          /*
           * 【关键】先登记下一帧的回调，再处理这一帧。
           * 反过来写（await 完拷贝才登记）就是第一版那个丢 70% 帧的 bug。
           */
          v.requestVideoFrameCallback(onFrame);
          probeDirect();
          grab();
        };
        v.requestVideoFrameCallback(onFrame);
        play();
        await Promise.race([once(v, 'ended'), stopPromise]);
      } else {
        /*
         * 退化路径：没有 requestVideoFrameCallback 时用 rAF 采样。
         * 只在 currentTime 真的变化时抓，避免同一帧被存两次；
         * 但 60Hz 的采样对 60fps 视频仍可能漏帧 —— 方法名会如实报出去。
         */
        res.method = 'raf';
        var raf = (typeof requestAnimationFrame === 'function')
          ? requestAnimationFrame
          : function (f) { return setTimeout(f, 16); };
        var last = -1;
        var loop = function () {
          if (res.stopped) return;
          if (v.currentTime !== last) { last = v.currentTime; grab(); }
          raf(loop);
        };
        play();
        raf(loop);
        await Promise.race([once(v, 'ended'), stopPromise]);
      }

      if (res.playError) throw new Error('视频无法播放：' + res.playError);

      // 等所有在飞的拷贝落地 —— 否则会返回一堆 bitmap 还是 null 的帧
      if (pending.length) await Promise.all(pending);
      res.pending = pending.length;

      if (v.getVideoPlaybackQuality) {
        var q = v.getVideoPlaybackQuality();
        res.dropped = q.droppedVideoFrames || 0;
        res.decoded = q.totalVideoFrames || 0;
      }
      // 拷贝失败的帧不能留在序列里（宁缺勿假，并把数量报出去）
      if (res.failedBitmaps) {
        res.frames = res.frames.filter(function (f) { return f.bitmap; });
        for (var k = 0; k < res.frames.length; k++) res.frames[k].index = k;
      }
      res.kept = res.frames.length;
      return res;
    } catch (e) {
      closeFrames(res.frames);
      throw e;
    } finally {
      try { v.pause(); } catch (e) { /* 忽略 */ }
      try {
        if (v.removeAttribute) v.removeAttribute('src');
        if (v.load) v.load();
      } catch (e) { /* 忽略 */ }
      URL.revokeObjectURL(url);
    }
  }

  /**
   * 探测帧率：播放一小段，看每两帧之间隔了多少媒体时间。
   *
   * 用**相邻帧时间差的中间值**来反推帧率，而不是"帧数 / 总时长"：
   * 如果解码器偶尔丢一帧，时间差会变成 2/fps，取中间值仍然得到 1/fps，
   * 而"帧数/总时长"会被系统性拉低（于是估的总帧数偏小、选的分辨率偏大）。
   * 探测不建位图（wantPixels=false），所以几乎不占内存、也不会被拷贝拖慢。
   */
  async function probe(file, opts) {
    opts = opts || {};
    var r = await run(file, {
      wantPixels: false,
      keepEvery: 1,
      limit: opts.maxFrames || PROBE_MAX_FRAMES,
      stopAfter: opts.seconds || PROBE_SECONDS,
      signal: opts.signal,
      onProgress: opts.onProgress
    });
    var deltas = [];
    for (var i = 1; i < r.frames.length; i++) {
      var d = r.frames[i].time - r.frames[i - 1].time;
      if (d > 1e-6) deltas.push(d);
    }
    deltas.sort(function (a, b) { return a - b; });
    var median = deltas.length ? deltas[Math.floor(deltas.length / 2)] : 0;
    var span = r.mediaEnd;
    var fps = median > 1e-6 ? 1 / median : ((span > 0.2 && r.frames.length >= 2) ? (r.frames.length - 1) / span : 0);
    return {
      width: r.width, height: r.height, duration: r.duration,
      fps: fps || FALLBACK_FPS,
      fpsEstimated: !fps,
      probedFrames: r.frames.length,
      probedSpan: span,
      frameDelta: median,
      method: r.method,
      dropped: r.dropped
    };
  }

  /** 完整抽帧：把每一帧（或每 keepEvery 帧）抓成 ImageBitmap */
  async function extract(file, opts) {
    var r = await run(file, {
      longEdge: opts.longEdge || 0,
      limit: opts.limit || 0,
      keepEvery: opts.keepEvery || 1,
      wantPixels: true,
      poolSize: opts.poolSize,
      onProgress: opts.onProgress,
      signal: opts.signal
    });
    return {
      frames: r.frames,
      width: r.width, height: r.height,
      frameW: r.drawnW, frameH: r.drawnH,
      duration: r.duration,
      seen: r.seen, dropped: r.dropped, decoded: r.decoded,
      method: r.method, keepEvery: r.keepEvery,
      maxInflight: r.maxInflight, throttles: r.throttles, pauses: r.pauses,
      direct: r.direct, failedBitmaps: r.failedBitmaps, pending: r.pending,
      stoppedEarly: r.stopped && r.frames.length >= r.limit && isFinite(r.limit)
    };
  }

  function closeFrames(frames) {
    for (var i = 0; i < frames.length; i++) {
      if (frames[i] && frames[i].bitmap && frames[i].bitmap.close) frames[i].bitmap.close();
    }
    if (frames) frames.length = 0;
  }

  /** 估算一个视频有多少帧（抽帧前用它决定分辨率） */
  function estimateFrames(duration, fps, keepEvery) {
    var step = Math.max(1, keepEvery || 1);
    return Math.max(1, Math.round((duration || 0) * (fps || FALLBACK_FPS) / step));
  }

  STC.video = {
    isVideo: isVideo,
    meta: meta,
    probe: probe,
    extract: extract,
    estimateFrames: estimateFrames,
    closeFrames: closeFrames,
    PROBE_SECONDS: PROBE_SECONDS,
    PROBE_MAX_FRAMES: PROBE_MAX_FRAMES,
    FALLBACK_FPS: FALLBACK_FPS,
    defaultPoolSize: 6
  };
})(window.STC = window.STC || {});
