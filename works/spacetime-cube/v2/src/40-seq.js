/* 时空立方体 · 序列加载
 *
 * 三件必须做对的事：
 *
 * 1. 原画质。解码只走 createImageBitmap，且**不传任何 resize 参数**；
 *    不进 canvas、不做 drawImage 缩放、不做任何有损编码。
 *    唯一的硬边界是 GPU 的 MAX_TEXTURE_SIZE —— 超了要明确报错，绝不偷偷缩图。
 *
 * 2. 排序要可靠。优先 EXIF 拍摄时间，其次文件名自然序，最后文件修改时间；
 *    前一个键相等时才用后一个键。
 *
 * 3. 显存要有账。每帧纹理是 w×h×4 字节，自己算清楚，超预算就明说超了多少，
 *    而不是让浏览器把显存吃爆、页面直接白掉。
 */
(function (STC) {
  'use strict';

  /*
   * 纹理预算是这个程序最硬的物理约束，必须算清楚：
   *   每帧纹理字节 = 宽 × 高 × 4
   *   12MP 照片（4000×3000）= 33 MB/帧
   *   于是 200 帧原画质 = 6.6 GB —— **没有任何 GPU 装得下**。
   *
   * 所以"200 帧 + 原画质 + 全部同时驻留"三者不可能同时成立，
   * 只能让用户明确选一个。默认预算给 2 GB（独显常见值，集显可能仍然吃紧），
   * 并按 deviceMemory 向上放宽。
   */
  var RAM_BUDGET = 2 * 1024 * 1024 * 1024;
  var MAX_FRAMES = 600;
  /* 视频是连续画面，"每帧都保留"是硬要求，所以给视频序列单独放宽帧数上限。
     真正卡住的是显存预算（见下），这个上限只是防止 UI/滑块彻底失控。 */
  var VIDEO_MAX_FRAMES = 2000;
  var POINT_BUDGET = 4.0e6;              // 点云总点数上限（所有帧加起来）
  var MAX_LONG_EDGE = 8192;              // 单帧长边硬上限（与 GPU 上限共同约束）
  var MIN_EDGE = 24;                     // 再小就没有可读性了

  /** 探测一个更贴近本机的默认预算 */
  function defaultBudget() {
    var dm = (typeof navigator !== 'undefined' && navigator.deviceMemory) || 0;
    if (dm >= 16) return 4 * 1024 * 1024 * 1024;
    if (dm >= 8) return 3 * 1024 * 1024 * 1024;
    return RAM_BUDGET;
  }

  /**
   * 在「帧数」与「单帧分辨率」之间解一个可行的长边。
   *
   * 约束：n × W × H × 4 ≤ budget，且 W/H 保持给定宽高比、长边不超过上限。
   * 解出长边 L 满足 n × L²/aspect' × 4 ≤ budget（aspect' = 长边/短边）。
   * 返回 0 表示"没有任何正解"（理论上不会，因为 L 可以很小）。
   */
  function fitLongEdge(n, aspect, budget) {
    if (n <= 0 || budget <= 0) return 0;
    var longRatio = Math.max(aspect, 1 / aspect);        // 长边 / 短边
    // n * L * (L/longRatio) * 4 <= budget   →   L <= sqrt(budget * longRatio / (4n))
    var L = Math.sqrt(budget * longRatio / (4 * n));
    return Math.max(MIN_EDGE, Math.min(MAX_LONG_EDGE, Math.floor(L)));
  }

  var IMAGE_RE = /\.(jpe?g|png|webp|bmp|gif|avif|jfif)$/i;

  function isImage(file) {
    return /^image\//.test(file.type || '') || IMAGE_RE.test(file.name || '');
  }

  function naturalCompare(a, b) {
    return String(a).localeCompare(String(b), 'zh-Hans-CN', { numeric: true, sensitivity: 'base' });
  }

  /**
   * 排序键的**唯一实现**：图片、视频块都走这一个比较器，
   * 避免"图片一套规则、视频又一套规则"这种早晚会对不上的写法。
   * a/b = {name, lastModified, date}
   */
  function compareEntries(a, b, mode) {
    if (mode === 'exif') {
      var da = a.date, db = b.date;
      if (da && db && da.getTime() !== db.getTime()) return da.getTime() - db.getTime();
      if (da && !db) return -1;              // 有拍摄时间的排前面
      if (!da && db) return 1;
      return naturalCompare(a.name, b.name);
    }
    if (mode === 'mtime') {
      return (a.lastModified - b.lastModified) || naturalCompare(a.name, b.name);
    }
    return naturalCompare(a.name, b.name) || (a.lastModified - b.lastModified);
  }

  /**
   * 决定顺序。返回 {list, keys} —— keys 里记下每张用的排序键，便于 UI 展示。
   * mode: 'exif' | 'name' | 'mtime'
   */
  async function order(files, mode, onProgress) {
    var list = Array.from(files).filter(isImage);
    if (!list.length) {
      throw new Error('没有找到可用的图片（支持 JPG / PNG / WebP / BMP / GIF / AVIF）');
    }

    var meta = new Array(list.length);
    if (mode === 'exif') {
      for (var i = 0; i < list.length; i++) {
        meta[i] = await STC.exif.read(list[i]);
        if (onProgress && (i % 16 === 15 || i === list.length - 1)) {
          onProgress({ phase: 'exif', done: i + 1, total: list.length });
        }
      }
    } else {
      for (var j = 0; j < list.length; j++) meta[j] = { date: null, orientation: 1 };
    }

    var idx = list.map(function (_, k) { return k; });
    idx.sort(function (a, b) {
      var A = list[a], B = list[b];
      return compareEntries(
        { name: A.name, lastModified: A.lastModified, date: meta[a].date },
        { name: B.name, lastModified: B.lastModified, date: meta[b].date },
        mode);
    });

    var sorted = idx.map(function (k) { return list[k]; });
    var sortedMeta = idx.map(function (k) { return meta[k]; });
    var noExif = 0;
    if (mode === 'exif') {
      for (var m = 0; m < sortedMeta.length; m++) if (!sortedMeta[m].date) noExif++;
    }
    return { files: sorted, meta: sortedMeta, noExif: noExif };
  }

  /** 解码一帧，保持原始像素尺寸 */
  async function decode(file) {
    return decodeAt(file, 0);
  }

  /** 所有帧统一的目标平面尺寸（世界单位，宽固定为 1，保持原始长宽比，不拉伸） */
  function layout(planeW, planeH, n, depthRatio) {
    var depth = (depthRatio === undefined ? 1.6 : depthRatio) * Math.max(planeW, planeH);
    return {
      planeW: planeW,
      planeH: planeH,
      depth: depth,
      step: n > 1 ? depth / (n - 1) : 0,
      zOf: function (i) { return n > 1 ? i * (depth / (n - 1)) : depth * 0.5; }
    };
  }

  /** 解码一帧；给了 longEdge 就按长边缩放（这是唯一的"降分辨率"入口，且由用户显式选择） */
  async function decodeAt(file, longEdge) {
    if (typeof createImageBitmap === 'function') {
      var bit = await createImageBitmap(file, {
        premultiplyAlpha: 'none',
        colorSpaceConversion: 'none'
      });
      if (!longEdge || Math.max(bit.width, bit.height) <= longEdge) return bit;
      // 只有确实需要缩小才走这一步；resizeQuality: 'high' 用较好的重采样
      var s = longEdge / Math.max(bit.width, bit.height);
      var tw = Math.max(1, Math.round(bit.width * s));
      var th = Math.max(1, Math.round(bit.height * s));
      try {
        var small = await createImageBitmap(file, {
          resizeWidth: tw, resizeHeight: th, resizeQuality: 'high',
          premultiplyAlpha: 'none', colorSpaceConversion: 'none'
        });
        if (bit.close) bit.close();
        return small;
      } catch (e) {
        return bit;                       // 缩放失败就退回原尺寸，绝不静默丢帧
      }
    }
    return decodeAtViaImg(file, longEdge);
  }

  function decodeAtViaImg(file, longEdge) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        if (!longEdge || Math.max(img.width, img.height) <= longEdge) return resolve(img);
        var s = longEdge / Math.max(img.width, img.height);
        var c = document.createElement('canvas');
        c.width = Math.max(1, Math.round(img.width * s));
        c.height = Math.max(1, Math.round(img.height * s));
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        resolve(c);
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('解码失败')); };
      img.src = url;
    });
  }

  /**
   * 加载整个序列。返回 frames[]，每帧带自己的 ImageBitmap。
   *
   * **关于分辨率**：默认（autoLongEdge 为假、longEdge 为 0）完全保持原始尺寸。
   * 帧数一多，原尺寸不可能同时驻留显存 —— 200 帧 12MP 需要 6.6 GB。
   * 所以提供了两条明确的出路，都由用户选择：
   *   - longEdge: N        → 统一缩到长边 N（用户指定）
   *   - autoLongEdge: true → 按预算与帧数自动解一个长边（并报告用了多少）
   * 两者都不给时，超预算就按原有逻辑"载入到装不下为止"并如实报告。
   *
   * **视频**：视频文件先被抽成一串帧（`STC.video`），再与照片一起堆叠。
   * 抽帧默认**每一帧都保留**；`opts.videoStep = N` 表示每 N 个呈现帧保留 1 个
   * （用户显式选择才会抽稀）。抽帧是实时的，进度里会报"已抓 N 帧 / 媒体时间"。
   */
  async function load(files, opts) {
    opts = opts || {};
    var maxTex = opts.maxTextureSize || 8192;
    var budget = opts.budget || defaultBudget();
    var onProgress = opts.onProgress || function () {};
    var signal = opts.signal || { cancelled: false };
    var wantLongEdge = opts.longEdge || 0;
    var autoLongEdge = !!opts.autoLongEdge;
    var sortMode = opts.sort || 'exif';
    var videoStep = Math.max(1, Math.round(opts.videoStep || 1));

    var all = Array.from(files);
    var imageFiles = all.filter(isImage);
    var videoFiles = all.filter(function (f) { return !isImage(f) && STC.video.isVideo(f); });
    if (!imageFiles.length && !videoFiles.length) {
      throw new Error('没有找到可用的图片或视频\n' +
        '图片：JPG / PNG / WebP / BMP / GIF / AVIF；视频：浏览器能解的 MP4 / WebM / MOV…');
    }

    /* ---- 1. 图片排序（EXIF 拍摄时间 → 文件名 → 修改时间）---- */
    var ordered = imageFiles.length
      ? await order(imageFiles, sortMode, onProgress)
      : { files: [], meta: [], noExif: 0 };

    var trimmed = 0;
    if (!videoFiles.length && ordered.files.length > MAX_FRAMES) {
      // 只有图片时才沿用"等间隔抽稀"的老行为（保住整段时间跨度）。
      // 有视频时绝不抽稀：那等于把"每一帧都保留"这条承诺偷偷改掉。
      var keep = [];
      var stepF = ordered.files.length / MAX_FRAMES;
      for (var k = 0; k < MAX_FRAMES; k++) keep.push(Math.floor(k * stepF));
      trimmed = ordered.files.length - keep.length;
      ordered.files = keep.map(function (i) { return ordered.files[i]; });
    }

    /* ---- 2. 视频元信息，然后与图片一起排序 ---- */
    var videos = [];
    for (var vi = 0; vi < videoFiles.length; vi++) {
      if (signal.cancelled) throw new Error('已取消');
      onProgress({ phase: 'video-meta', done: vi, total: videoFiles.length });
      videos.push({ file: videoFiles[vi], meta: await STC.video.meta(videoFiles[vi]) });
      await tick();
    }

    var entries = [];
    ordered.files.forEach(function (f, i) {
      entries.push({ kind: 'image', file: f, date: ordered.meta[i].date });
    });
    videos.forEach(function (v) {
      entries.push({ kind: 'video', file: v.file, meta: v.meta, date: null, probe: null });
    });
    entries.sort(function (a, b) {
      return compareEntries(
        { name: a.file.name, lastModified: a.file.lastModified, date: a.date },
        { name: b.file.name, lastModified: b.file.lastModified, date: b.date },
        sortMode);
    });

    /* ---- 3. 先量第一块的原始尺寸，据此定下目标长边 ---- */
    var firstEntry = entries[0];
    var firstBmp = null;
    var origW, origH;
    if (firstEntry.kind === 'image') {
      onProgress({ phase: 'measure', done: 0, total: entries.length });
      try { firstBmp = await decodeAt(firstEntry.file, 0); } catch (e) { firstBmp = null; }
      origW = firstBmp ? firstBmp.width : 0;
      origH = firstBmp ? firstBmp.height : 0;
    } else {
      origW = firstEntry.meta.width;
      origH = firstEntry.meta.height;
    }
    if (!origW || !origH) throw new Error('第一帧解码失败，无法确定序列尺寸');
    var origLong = Math.max(origW, origH);
    var origShort = Math.min(origW, origH);
    var aspect = origW / origH;

    /* ---- 4. "大概多少帧"：图片数已知，视频靠短探测反推帧率 ---- */
    var frameCap = videos.length ? VIDEO_MAX_FRAMES : MAX_FRAMES;
    var estFrames = entries.length;
    for (var pi = 0; pi < videos.length; pi++) {
      var pv = videos[pi];
      if (autoLongEdge) {
        onProgress({ phase: 'video-probe', done: pi, total: videos.length, name: pv.file.name });
        pv.probe = await STC.video.probe(pv.file, { signal: signal });
        pv.estFrames = STC.video.estimateFrames(pv.meta.duration, pv.probe.fps, videoStep);
      } else {
        pv.estFrames = 0;
      }
      if (pv.estFrames) estFrames += pv.estFrames - 1;   // 它自己已经算作 1 个 entry
    }
    var estCapped = Math.min(estFrames, frameCap);

    var longEdge = wantLongEdge;
    var autoChosen = 0;
    if (!longEdge && autoLongEdge) {
      autoChosen = fitLongEdge(estCapped, aspect, budget);
      longEdge = autoChosen;
    }
    if (longEdge) {
      longEdge = Math.max(MIN_EDGE, Math.min(longEdge, origLong, MAX_LONG_EDGE, maxTex));
    }
    var scaled = !!(longEdge && longEdge < origLong);
    var scale = scaled ? longEdge / origLong : 1;
    var targetW = Math.max(1, Math.round(origW * scale));
    var targetH = Math.max(1, Math.round(origH * scale));

    /* ---- 5. 逐块产出帧 ---- */
    var frames = [];
    var failed = [];
    var notes = [];
    var bytes = 0;
    var budgetHit = null;
    var videoInfo = [];
    var pendingFirst = firstBmp;

    function pushFrame(o) {
      bytes += o.bytes;
      frames.push({
        index: frames.length,
        name: o.name,
        lastModified: o.lastModified,
        width: o.width, height: o.height,
        bytes: o.bytes,
        bitmap: o.bitmap,
        texture: null,
        aspect: o.width / o.height,
        video: o.video || null,
        videoTime: o.videoTime,
        videoFrame: o.videoFrame
      });
    }

    for (var ei = 0; ei < entries.length; ei++) {
      if (signal.cancelled) throw new Error('已取消');
      var en = entries[ei];

      if (en.kind === 'image') {
        var bmp = null;
        try {
          if (pendingFirst && !scaled) {
            bmp = pendingFirst;                    // 尺寸就是原尺寸，直接复用
            pendingFirst = null;
          } else {
            bmp = await decodeAt(en.file, scaled ? longEdge : 0);
          }
        } catch (e) {
          failed.push(en.file.name + '：' + (e && e.message || e));
          continue;
        }
        if (bmp.width > maxTex || bmp.height > maxTex) {
          if (bmp.close) bmp.close();
          failed.push(en.file.name + '：' + bmp.width + '×' + bmp.height +
            ' 超过本机 GPU 单张纹理上限 ' + maxTex + '×' + maxTex + '，已跳过（不会替你做压缩）');
          continue;
        }
        var ifb = bmp.width * bmp.height * 4;
        if (bytes + ifb > budget) {
          if (bmp.close) bmp.close();
          budgetHit = {
            at: frames.length, total: estCapped, kind: 'image', name: en.file.name,
            usedMB: Math.round(bytes / 1048576),
            needMB: Math.round(ifb / 1048576),
            budgetMB: Math.round(budget / 1048576)
          };
          break;
        }
        pushFrame({
          name: en.file.name, lastModified: en.file.lastModified,
          width: bmp.width, height: bmp.height, bytes: ifb, bitmap: bmp
        });
        onProgress({ phase: 'decode', done: ei + 1, total: entries.length });
        if (ei % 2 === 1) await tick();
        continue;
      }

      /* ---- 视频块：抽帧 ---- */
      var vw = Math.max(1, Math.round(en.meta.width * scale));
      var vh = Math.max(1, Math.round(en.meta.height * scale));
      if (vw > maxTex || vh > maxTex) {
        failed.push(en.file.name + '：视频尺寸 ' + en.meta.width + '×' + en.meta.height +
          ' 超过本机 GPU 单张纹理上限 ' + maxTex + '×' + maxTex + '，已跳过');
        continue;
      }
      var vfb = vw * vh * 4;
      var roomByBudget = Math.floor((budget - bytes) / vfb);
      var roomByCap = frameCap - frames.length;
      var room = Math.min(roomByBudget, roomByCap);
      if (room < 1) {
        budgetHit = {
          at: frames.length, total: estCapped, kind: 'video', name: en.file.name,
          usedMB: Math.round(bytes / 1048576),
          needMB: Math.round(vfb / 1048576),
          budgetMB: Math.round(budget / 1048576)
        };
        break;
      }

      var ex = await STC.video.extract(en.file, {
        longEdge: longEdge || 0,
        keepEvery: videoStep,
        limit: room,
        signal: signal,
        onProgress: function (vn, p) {
          onProgress({
            phase: 'video', name: vn, done: ei, total: entries.length,
            frames: p.frames, seen: p.seen, time: p.time, duration: p.duration
          });
        }.bind(null, en.file.name)
      });

      var est = en.estFrames || STC.video.estimateFrames(en.meta.duration,
        STC.video.FALLBACK_FPS, videoStep);
      var info = {
        name: en.file.name,
        duration: ex.duration,
        method: ex.method,
        keepEvery: ex.keepEvery,
        seen: ex.seen,
        kept: ex.frames.length,
        dropped: ex.dropped,
        decoded: ex.decoded,
        estimated: est,
        truncated: ex.frames.length >= room && est > ex.frames.length,
        frameW: ex.frameW, frameH: ex.frameH,
        maxInflight: ex.maxInflight, throttles: ex.throttles, pauses: ex.pauses,
        direct: ex.direct, failedBitmaps: ex.failedBitmaps
      };
      videoInfo.push(info);

      if (!ex.frames.length) {
        failed.push(en.file.name + '：一帧都没抽到（解码失败或格式不支持）');
        continue;
      }

      for (var fi = 0; fi < ex.frames.length; fi++) {
        var vf = ex.frames[fi];
        pushFrame({
          name: en.file.name + ' #' + pad4(fi + 1),
          lastModified: en.file.lastModified,
          width: vf.width, height: vf.height,
          bytes: vf.width * vf.height * 4,
          bitmap: vf.bitmap,
          video: en.file.name,
          videoTime: vf.time,
          videoFrame: fi
        });
      }

      if (info.truncated) {
        var roomKind = (room === roomByCap) ? ('帧数上限 ' + frameCap + ' 帧') : '显存预算';
        if (!budgetHit) {
          budgetHit = {
            at: frames.length, total: est, kind: 'video', name: en.file.name,
            usedMB: Math.round(bytes / 1048576),
            needMB: Math.round(vfb / 1048576),
            budgetMB: Math.round(budget / 1048576),
            kept: ex.frames.length, estimate: est
          };
        }
        var needStep = Math.ceil(est / Math.max(1, ex.frames.length));
        notes.push(en.file.name + '：估计共 ' + est + ' 帧，本次只保留前 ' + ex.frames.length +
          ' 帧（' + roomKind + '）。' +
          (needStep <= 10
            ? '想留住整段的话，把「视频抽帧」改成每 ' + needStep + ' 帧取 1。'
            : '想留住整段的话，请把顶栏「分辨率」改成更小的值 —— ' +
              '当前分辨率下这个视频装不进显存预算。'));
      }
      /*
       * 丢帧与抽帧质量的报告。
       *
       * 现实一点说：在抢占式系统里**丢帧无法完全避免**（其它进程占着 CPU/GPU 时
       * 解码器就是来不及呈现），所以这里的语气是"报告"而不是"报错"：
       *   - 少量丢帧（< 5%）：一句话说清楚，不劝用户改配置；
       *   - 明显丢帧：给出具体比例和建议（调低分辨率），并明确"抽稀解决不了这个"。
       */
      if (ex.dropped > 0) {
        var denom = Math.max(1, ex.dropped + ex.seen);
        var lostPct = Math.round(ex.dropped / denom * 100);
        var how = ex.throttles
          ? '（已自动降速 ' + ex.throttles + ' 次' + (ex.pauses ? '、暂停 ' + ex.pauses + ' 次' : '') + '）'
          : '';
        notes.push(en.file.name + '：解码器报了 ' + ex.dropped + ' 个丢帧' + how +
          '，呈现 ' + ex.seen + ' 帧、保留 ' + ex.frames.length + ' 帧（丢帧率约 ' + lostPct + '%）。' +
          (lostPct <= 5
            ? '这个量级属于正常抖动（别的东西占着 CPU/GPU 时就会这样），可以忽略。'
            : '丢得有点多。请把顶栏「分辨率」调低（例如 1280 或 960）再抽一次 —— ' +
              '**不要**用「每 N 帧取 1」，那只是少抽样，丢掉的帧并不会回来。'));
      }
      if (ex.failedBitmaps) {
        notes.push(en.file.name + '：有 ' + ex.failedBitmaps + ' 帧拷贝失败，已从序列里剔除（不会拿假帧充数）。');
      }
      if (ex.throttles && !ex.dropped) {
        // 慢但没丢：这是预期行为，也告诉用户为什么花了比视频更长的时间
        notes.push(en.file.name + '：拷贝速度低于播放速度，已自动降速 ' + ex.throttles +
          ' 次' + (ex.pauses ? '、暂停 ' + ex.pauses + ' 次' : '') +
          '以保证一帧不丢（代价是耗时比视频本身长）。');
      }
      if (ex.method !== 'rvfc') {
        notes.push(en.file.name + '：这个浏览器没有 requestVideoFrameCallback，' +
          '已退化为 rAF 采样，帧数可能与真实帧数有出入。');
      }
      await tick();
    }

    if (frames.length < 2) {
      closeAll(frames);
      throw new Error('可用的照片/视频帧不足 2 张' +
        (failed.length ? '：\n' + failed.slice(0, 5).join('\n') : '') +
        (budgetHit ? '\n显存预算不足：已用 ' + budgetHit.usedMB + 'MB，本帧需要 ' +
          budgetHit.needMB + 'MB，上限 ' + budgetHit.budgetMB + 'MB' : ''));
    }

    var planeH = targetH / targetW;
    var geo = layout(1, planeH, frames.length, opts.depthRatio);

    return {
      frames: frames,
      geo: geo,
      bytes: bytes,
      failed: failed,
      notes: notes,
      trimmed: trimmed,
      budgetHit: budgetHit,
      noExif: ordered.noExif,
      video: videoInfo,
      videoStep: videoStep,
      estFrames: estFrames,
      // 实际用于渲染的尺寸（可能已被用户选择的分辨率策略缩小）
      baseW: targetW, baseH: targetH,
      // 原图尺寸与是否发生缩放 —— 界面要如实报告，不能偷偷降质
      origW: origW, origH: origH, origLong: origLong, origShort: origShort,
      scaled: scaled, longEdge: scaled ? longEdge : origLong, autoChosen: autoChosen,
      budget: budget, requested: all.length,
      sort: sortMode
    };
  }

  function pad4(n) {
    var s = String(n);
    while (s.length < 4) s = '0' + s;
    return s;
  }

  /** 点云密度：用总点数预算反推出采样步长（1 像素 1 个点时的步长是 1） */
  function pointStride(frames, budget) {
    var total = 0;
    for (var i = 0; i < frames.length; i++) {
      total += frames[i].width * frames[i].height;
    }
    return STC.view.pointStride(total, budget || POINT_BUDGET, frames.length);
  }

  function closeAll(frames) {
    for (var i = 0; i < frames.length; i++) {
      if (frames[i].bitmap && frames[i].bitmap.close) frames[i].bitmap.close();
    }
  }

  function release(seq) {
    if (!seq) return;
    closeAll(seq.frames);
    seq.frames.length = 0;
  }

  function tick() {
    return new Promise(function (r) { setTimeout(r, 0); });
  }

  STC.seq = {
    load: load,
    order: order,
    compareEntries: compareEntries,
    layout: layout,
    pointStride: pointStride,
    release: release,
    isImage: isImage,
    naturalCompare: naturalCompare,
    defaultBudget: defaultBudget,
    fitLongEdge: fitLongEdge,
    RAM_BUDGET: RAM_BUDGET,
    MAX_FRAMES: MAX_FRAMES,
    VIDEO_MAX_FRAMES: VIDEO_MAX_FRAMES,
    MAX_LONG_EDGE: MAX_LONG_EDGE,
    POINT_BUDGET: POINT_BUDGET
  };
})(window.STC = window.STC || {});
