/**
 * pet-app.js —— 最小 Live2D 渲染器（PIXI + pixi-live2d-display cubism4）
 *
 * 只做四件事：透明画布 / 加载 c_0120 模型 / 循环 idle / 暴露一个给宿主用的 API。
 * 任何窗口技术（Electron 透明窗口、WebView2）都只是这一页的容器。
 *
 * 调试参数：
 *   ?bg=checker   棋盘底（普通浏览器里肉眼检查 alpha 通道）
 *   ?bg=desk      桌面渐变底
 *   ?scale=1.2    手动缩放（默认自动铺满窗口）
 *   ?static=1     不播动作（截图时姿态稳定，便于复现）
 */
;(function () {
  'use strict'

  var q = new URLSearchParams(location.search)
  var bg = q.get('bg')
  if (bg === 'checker') document.body.classList.add('bg-checker')
  else if (bg === 'desk') document.body.classList.add('bg-desk')

  var statusEl = document.getElementById('status')
  var errEl = document.getElementById('err')
  // 那行「canvas … scale …」自检是开发信息，不是产品的一部分：默认不画，
  // 需要时用 ?hud=1 打开（错误 #err 永远不隐藏）。
  if (q.get('hud') !== '1' && statusEl) { statusEl.style.display = 'none' }
  function status(t) { statusEl.textContent = t }
  function fail(e) {
    errEl.textContent = 'RENDER ERROR: ' + (e && (e.stack || e.message) || e)
    console.error(e)
  }
  window.addEventListener('error', function (ev) { fail(ev.error || ev.message) })
  window.addEventListener('unhandledrejection', function (ev) { fail(ev.reason) })

  if (typeof PIXI === 'undefined') return fail(new Error('pixi.min.js 没加载上'))
  if (!PIXI.live2d) return fail(new Error('cubism4.min.js 没加载上（PIXI.live2d 不存在）'))
  if (typeof Live2DCubismCore === 'undefined') return fail(new Error('live2dcubismcore.min.js 没加载上'))

  var MODEL_URL = '../model/c_0120.model3.json'

  // backgroundAlpha:0 → 画布本身透明，不做任何底色填充
  var app = new PIXI.Application({
    backgroundAlpha: 0,
    antialias: true,
    autoStart: true,
    resizeTo: window,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
    autoDensity: true,
  })
  app.view.id = 'live2d-canvas'
  document.body.appendChild(app.view)

  var model = null
  var ready = false
  // 模型自身的（未缩放）画布尺寸：第一次 fit 时记下来，之后 resize 不会把 scale 叠乘。
  var NAT_W = 0, NAT_H = 0
  // ?anchor=br 把模型框贴在视口右下角（?fill=0..1 指自动适配尺寸的几分之一，?dx 再
  // 按视口宽度的比例左右平移），由宿主 pet/host/host.ps1 传入：桌宠窗口贴在工作区
  // 右下角，人物退到窗口右下，看板再按**实测的人物右边界**对齐自己的右边。
  // 默认居中、自动适配。
  var ANCHOR = q.get('anchor')
  var FILL = parseFloat(q.get('fill'))

  /* ══════════════════════════════════════════════════════════════════════
     人物包围盒测量 —— 标签定位与看板右对齐都以**人物**为基准，而不是窗口。

     getBounds() 给的是模型画布框（4068x4068 映射成 250x250 的那个方框），
     人物本体只占它的一部分，所以再渲染一次到离屏纹理、扫 alpha 求真实轮廓。
     取多帧的并集（待机时头顶会随呼吸浮动、换姿态会更宽），并集只增不减，
     这样标签不会跟着动画抖。窗口 resize 时重置并重新采样。
     ══════════════════════════════════════════════════════════════════════ */
  var BOX = null   // 画布框 {x,y,w,h}，页面 CSS px
  var SIL = null   // 人物轮廓并集 {x,y,w,h}，页面 CSS px
  var PROFILE = null  // 逐行轮廓：页面 px 行 -> [minX, maxX]（并集），用于和看板文字求交
  var SAMPLES = 0
  var ALPHA_MIN = 8
  var EXTRACT = { ok: false, error: null, width: 0, height: 0, alphaMax: 0, alphaCount: 0 }

  function unionBox(a, b) {
    if (a === null) return { x: b.x, y: b.y, w: b.w, h: b.h }
    var x = Math.min(a.x, b.x), y = Math.min(a.y, b.y)
    return {
      x: x, y: y,
      w: Math.max(a.x + a.w, b.x + b.w) - x,
      h: Math.max(a.y + a.h, b.y + b.h) - y,
    }
  }

  function measureOnce() {
    if (!model || !app.renderer) return null
    var b = null
    try { b = model.getBounds() } catch (e) { b = null }
    if (!b || !(b.width > 0) || !(b.height > 0)) return null
    BOX = { x: b.x, y: b.y, w: b.width, h: b.height }

    // 量真实轮廓：先把这一帧渲染出来，再直接读**主帧缓冲**。这条路和用户看到的
    // 是同一套绘制（掩膜/裁剪都正常），比 extract 到离屏纹理可靠——
    // pixi-live2d-display 的模型渲染进 RenderTexture 时掩膜不生效，只剩下几块碎片。
    var res = app.renderer.resolution || 1
    var rw = app.renderer.width, rh = app.renderer.height
    var src = 'framebuffer'
    var px = null, w = 0, h = 0
    try {
      app.renderer.render(app.stage)
      var buf = new Uint8Array(4 * rw * rh)
      var gl = app.renderer.gl
      gl.readPixels(0, 0, rw, rh, gl.RGBA, gl.UNSIGNED_BYTE, buf)
      px = buf; w = rw; h = rh
    } catch (e) {
      EXTRACT.error = String((e && e.message) || e)
      px = null
    }
    if (!px) {
      // 兜底：extract 到 canvas（掩膜可能不完整，但至少是个包围盒）
      var cv = null
      try { cv = app.renderer.extract.canvas(model) } catch (e) { EXTRACT.error = String((e && e.message) || e) }
      if (cv && cv.width > 0 && cv.height > 0) {
        try {
          var img = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height)
          px = img.data; w = cv.width; h = cv.height; src = 'extract'
        } catch (e) { EXTRACT.error = String((e && e.message) || e) }
      }
    }
    if (px) {
      var minX = w, minY = h, maxX = -1, maxY = -1
      var aMax = 0, aCount = 0
      var rowMin = new Array(h), rowMax = new Array(h)
      for (var i = 0; i < h; i++) { rowMin[i] = w; rowMax[i] = -1 }
      for (var y = 0; y < h; y++) {
        var off = y * w * 4
        for (var x = 0; x < w; x++) {
          var a = px[off + x * 4 + 3]
          if (a > aMax) aMax = a
          if (a > ALPHA_MIN) {
            aCount++
            if (x < minX) minX = x
            if (x > maxX) maxX = x
            if (y < minY) minY = y
            if (y > maxY) maxY = y
            if (x < rowMin[y]) rowMin[y] = x
            if (x > rowMax[y]) rowMax[y] = x
          }
        }
      }
      EXTRACT = { ok: maxX >= 0, error: null, source: src, width: w, height: h, alphaMax: aMax, alphaCount: aCount }
      if (maxX >= 0) {
        var box = null
        if (src === 'framebuffer') {
          // 主帧缓冲：设备 px -> 页面 px，y 轴要翻（GL 原点在左下）
          box = {
            x: minX / res,
            y: (h - 1 - maxY) / res,
            w: (maxX - minX + 1) / res,
            h: (maxY - minY + 1) / res,
          }
          // 逐行轮廓（页面 px；只用来看有没有压到看板文字，并集只增不减）
          if (PROFILE === null) { PROFILE = { rows: [] } }
          for (var ry = minY; ry <= maxY; ry++) {
            if (rowMax[ry] < 0) continue
            var py = Math.round((h - 1 - ry) / res)
            var lo = rowMin[ry] / res, hi = (rowMax[ry] + 1) / res
            var cell = PROFILE.rows[py]
            if (cell === undefined) { PROFILE.rows[py] = [lo, hi] }
            else { if (lo < cell[0]) cell[0] = lo; if (hi > cell[1]) cell[1] = hi }
          }
        } else {
          // extract 的 canvas 覆盖模型自己的包围盒，按比例映射回页面
          var sx = b.width / w, sy = b.height / h
          box = {
            x: b.x + minX * sx,
            y: b.y + minY * sy,
            w: (maxX - minX + 1) * sx,
            h: (maxY - minY + 1) * sy,
          }
        }
        SIL = unionBox(SIL, box)
      }
    }
    SAMPLES += 1
    placeState()
    return SIL
  }

  function measureLoop() {
    // 前 4.4s 采 8 帧（覆盖一个 idle 循环），之后按需（换姿态 / resize）再采
    var delays = [300, 800, 1400, 2000, 2600, 3200, 3800, 4400]
    for (var i = 0; i < delays.length; i++) { setTimeout(measureOnce, delays[i]) }
  }

  function fit() {
    if (!model) return
    var w = app.screen.width, h = app.screen.height
    var forced = parseFloat(q.get('scale'))
    if (NAT_W <= 0 || NAT_H <= 0) { NAT_W = model.width; NAT_H = model.height }
    var natW = NAT_W, natH = NAT_H
    var s = forced > 0 ? forced : Math.min(w / natW, h / natH)
    if (!(forced > 0) && ANCHOR === 'br' && FILL > 0 && FILL <= 1) { s = s * FILL }
    model.scale.set(s)
    model.anchor.set(0.5, 0.5)
    var dx = parseFloat(q.get('dx')) || 0
    var dy = parseFloat(q.get('dy')) || 0
    if (ANCHOR === 'br') {
      // 模型框的右下角 = 视口的右下角
      model.x = w - (natW * s) / 2 + dx * w
      model.y = h - (natH * s) / 2 + dy * h
    } else {
      model.x = w / 2 + dx * w
      model.y = h / 2 + dy * h
    }
    status(
      'canvas ' + Math.round(w) + 'x' + Math.round(h) +
      '  model ' + Math.round(natW) + 'x' + Math.round(natH) +
      '  scale ' + s.toFixed(4) +
      '  shown ' + Math.round(natW * s) + 'x' + Math.round(natH * s) +
      (ANCHOR === 'br' ? '  anchor=bottom-right fill=' + FILL : ''),
    )
  }

  PIXI.live2d.Live2DModel.from(MODEL_URL, {
    autoInteract: false,      // 不需要 PIXI 的鼠标互动，点击穿透由宿主控制
    // 注意：这里**故意不传 idleMotionGroup**。框架 Cubism4MotionManager 的默认
    // idle 组名是 "Idle"（大写 I），我们模型里没有这一组，所以自动待机循环不会播。
    // 原来传 'idle' 会把 motions/idle.motion3.json（Meta.Loop=true 的「猫爪摆手+爱心」
    // 循环，原作者明确停用）一直循环播——见 pet/REACTIONS-SPEC.md §1.2 / §10 坑 4。
  })
    .then(function (m) {
      model = m
      app.stage.addChild(model)
      // 物理（头发/鲸鱼鳍）默认开启，这里显式打开，避免不同版本默认值不一致
      try { model.internalModel.physics3Json = model.internalModel.physics3Json } catch (e) {}
      try { if (model.internalModel.physics) model.internalModel.physics.reset() } catch (e) {}
      // 帧内钩子：reactions.js 在 beforeModelUpdate（动作/表情写参之后、coreModel.update 之前）
      // 叠加自己的表情/道具/口型参数，这是框架里唯一能赢过动作与表情的时机。
      try {
        model.internalModel.on('beforeModelUpdate', function () {
          for (var i = 0; i < FRAME_HOOKS.length; i++) {
            try { FRAME_HOOKS[i]() } catch (e) { }
          }
        })
      } catch (e) { }
      fit()
      window.addEventListener('resize', function () {
        SIL = null                    // 视口变了，人物位置重新测
        fit()
        placeState()
        measureOnce()
        measureLoop()
      })
      if (q.get('static') === '1') {
        // 不播 idle（见上）；只冻结 ticker 便于截图
        try { app.ticker.stop() } catch (e) {}
        status('static pose (ticker stopped)')
      }
      ready = true
      window.__PET_READY__ = true
      document.title = 'DS 鲸鱼娘 · ready'
      // 表情/动作由 reactions.js 按 state.json + signals.json 驱动（本文件只管机制）
      if (window.PetReactions && PetReactions.applyStateDoc) {
        try { PetReactions.applyStateDoc(stateDoc) } catch (e) { }
      }
      // 量人物包围盒（标签与看板右对齐都靠它），并按测量值摆标签
      measureOnce()
      measureLoop()
      if (q.get('selftest') === '1') { setTimeout(startSelfTest, 400) }
    })
    .catch(fail)

  /* ——————— 给宿主窗口用的 API ———————
     hitTest：给「鼠标下面是不是她」用。返回 'model' / 'none'。
     精确到 alpha 的成本高，这里用 pixi-live2d-display 自带的 hitTest（基于模型命中区），
     再叠一层包围盒判断；对「点击穿透」这个用途足够。 */
  window.PetAPI = {
    isReady: function () { return ready },
    /** 宿主坐标系（CSS px，窗口左上角为原点）-> 'model' | 'none' */
    hitTest: function (x, y) {
      if (!model) return 'none'
      var b = model.getBounds()
      if (x < b.x || y < b.y || x > b.x + b.width || y > b.y + b.height) return 'none'
      try { if (model.hitTest(x, y)) return 'model' } catch (e) {}
      return 'model' // 命中包围盒但拿不到命中区时，保守地按「是她」处理
    },
    /** 手动播一组动作 */
    motion: function (group, index) {
      if (!model) return false
      try { model.motion(group, index); return true } catch (e) { return false }
    },
    /** 手动上表情（表情清单见 model/manifest.json） */
    expression: function (name) {
      if (!model) return false
      try { model.expression(name); return true } catch (e) { return false }
    },
    /** 当前状态对象（由 pet/state.mjs 的 computeState 产出，见 STATE-PROTOCOL.md） */
    getState: function () { return stateDoc },
    /** 机制层出口：reactions.js 用这些驱动表情/动作/道具（策略不在本文件） */
    model: function () { return model },
    /** PIXI Application（低性能档要改 ticker.maxFPS） */
    app: function () { return app },
    onFrame: onFrame,
    playMotion: playMotion,
    stopMotions: stopMotions,
    readParam: readParam,
    writeParam: writeParam,
    coreModel: coreModel,
    forbiddenMotions: function () { return FORBIDDEN_MOTIONS.slice() },
    /** 诊断：模型设置里声明的动作组（model3.json 的 FileReferences.Motions） */
    motionGroups: function () {
      var m = motionSettings()
      return m ? Object.keys(m) : null
    },
    settingsMotions: function () {
      var m = motionSettings()
      return m ? Object.keys(m) : null
    },
    /** 诊断：模型实际认识的表情名（model3.json 补了 Expressions 段之后应有 44 条） */
    expressions: function () {
      var names = expressionNames()
      return names.length ? names : null
    },
    /** ?selftest=1 的 44 表情实测报告（宿主通过 web message 收走，见 pet\host\page-message.json） */
    selfTestResult: function () { return selfTestSummary() },
    startSelfTest: function () { if (!SELFTEST) { startSelfTest() } return selfTestSummary() },
    /** 帧内参数取样（pet-watch 消息驱动），验收与"待机有没有在播动作"的判据 */
    startMotionWatch: function (ms, ids) { startMotionWatch(ms || 6000, ids); return motionWatchResult() },
    motionWatchResult: motionWatchResult,
    postToHost: postToHost,
    /** 人物包围盒 / 标签矩形（页面 CSS px，视口左上角为原点）——宿主据此对齐看板 */
    modelMetrics: function () {
      return {
        box: BOX ? { x: BOX.x, y: BOX.y, width: BOX.w, height: BOX.h } : null,
        model: SIL ? { x: SIL.x, y: SIL.y, width: SIL.w, height: SIL.h } : null,
        label: rectOf(labelEl),
        detail: rectOf(detailEl),
        samples: SAMPLES,
        extract: EXTRACT,
        // 看板发布的锚点（labelRightPage / labelTopPage），没拿到就是 null
        geom: GEOM,
        // 逐行轮廓（页面 px）：[y, minX, maxX]，只给有内容的行。用来和看板文字求交。
        profile: PROFILE ? PROFILE.rows.map(function (r, i) { return r ? [i, Math.round(r[0] * 10) / 10, Math.round(r[1] * 10) / 10] : null }).filter(Boolean) : [],
        viewport: { width: window.innerWidth, height: window.innerHeight },
      }
    },
    /** 透明自检：随机取几个画布像素的 alpha，全 0 = 这一页真的没有底色 */
    alphaProbe: function () {
      var gl = app.renderer.gl
      var w = app.renderer.width, h = app.renderer.height
      var px = new Uint8Array(4 * 4)
      var pts = [[2, 2], [w - 3, 2], [2, h - 3], [w - 3, h - 3]]
      var out = []
      for (var i = 0; i < pts.length; i++) {
        gl.readPixels(pts[i][0], h - pts[i][1], 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px.subarray(i * 4, i * 4 + 4))
        out.push(px[i * 4 + 3])
      }
      return out // 期望 [0,0,0,0]
    },
  }

  /* ══════════════════════════════════════════════════════════════════════
     状态标签 —— 契约见 pet/STATE-PROTOCOL.md（由 pet/state.mjs computeState 决定）

     这一页**不判断状态**：它只读一个极小的状态契约文件 state.json
     （与 index.html 同目录，即 pet/renderer/state.json），把里面的
     label / color / detail 原样画出来。

     位置由 placeState() 按**实测的人物包围盒**绝对定位（不是挂在窗口角）：
     标签上边缘 = 人物上边缘 + 2px（不高于头顶），右边缘 = 人物右边缘 - 2px
     （不超过尾巴），detail 同一右边缘、跟在标签下一行。

     状态 JSON 的形状就是 computeState() 的返回值：
       { state, label, color, detail, pose, reason, source }

     其他注入方式（都在这里实现好了）：
       ?state=working        用查询参数强制一个状态（调试用）
       window.postMessage({type:'pet-state', payload:{...}})   宿主直接推
     ══════════════════════════════════════════════════════════════════════ */

  // 冻结色表的**兜底副本**：只有当 state.json 缺 label/color 时才用它。
  // 权威来源始终是 pet/state.mjs；页面不在这里做任何状态判断。
  var FROZEN = {
    offline:     { label: '离线',     color: '#8B949E', pose: 'offline' },
    stale:       { label: '数据过期', color: '#D2A8FF', pose: 'sleepy' },
    error:       { label: '出错了',   color: '#F85149', pose: 'gloomy' },
    celebrating: { label: '收工啦',   color: '#E3B341', pose: 'happy' },
    listening:   { label: '听主人说', color: '#79C0FF', pose: 'starry' },
    team:        { label: '团队协作', color: '#56D4DD', pose: 'team' },
    reading:     { label: '查资料',   color: '#58A6FF', pose: 'reading' },
    writing:     { label: '写文件',   color: '#F0883E', pose: 'scribble' },
    running:     { label: '跑命令',   color: '#FFA657', pose: 'sleeves' },
    thinking:    { label: '想事情',   color: '#A5D6FF', pose: 'thinking' },
    idle:        { label: '空闲',     color: '#9DA7B3', pose: 'idle' },
  }

  /* ══════════════════════════════════════════════════════════════════════
     动作 / 表情的**机制**层（策略在 reactions.js，规格见 pet/REACTIONS-SPEC.md）

     本文件只提供：动作组与表情名清单、播放/停止（含 clearMotionPose 的坑）、
     帧内参数读写、逐帧钩子。**禁止清单**在这里双拦一次（清单 + 播放入口）。
     ══════════════════════════════════════════════════════════════════════ */
  var FORBIDDEN_MOTIONS = ['aidale', 'bubble']   // aidale 内部驱动 15 个表情参数；bubble=吹泡泡糖
  var FRAME_HOOKS = []
  var SELFTEST = null

  function onFrame(fn) { if (typeof fn === 'function') FRAME_HOOKS.push(fn) }

  function motionSettings() {
    try { return (model.internalModel && model.internalModel.settings && model.internalModel.settings.motions) || null } catch (e) { return null }
  }
  function motionGroupExists(group) {
    var m = motionSettings()
    if (m) { return !!m[group] }
    try {
      var mm = model.internalModel && model.internalModel.motionManager
      return !!(mm && mm.motionGroups && mm.motionGroups[group] && mm.motionGroups[group].length > 0)
    } catch (e) { return false }
  }
  function expressionNames() {
    try {
      var em = model.internalModel.motionManager.expressionManager
      if (!em || !em.definitions) return []
      // 注意：pixi-live2d-display 的 definitions 是**数组**（下标就是索引），
      // 名字在每项的 .Name 里；Object.keys() 只会得到 "0".."43"。
      return em.definitions.map(function (d) { return d && d.Name }).filter(function (n) { return typeof n === 'string' && n.length > 0 })
    } catch (e) { return [] }
  }
  function expressionDefined(name) {
    try {
      var em = model.internalModel.motionManager.expressionManager
      if (!em || !em.definitions) return false
      if (typeof em.getExpressionIndex === 'function') { return em.getExpressionIndex(name) > -1 }
      return !!em.definitions[name]
    } catch (e) { return false }
  }
  function coreModel() {
    try { return model.internalModel.coreModel } catch (e) { return null }
  }
  /** 播一个动作组；hold=true 表示要求定格（框架没有 hold，由 reactions.js 抽样保持）。*/
  function playMotion(group, hold) {
    if (!model || !group) return null
    if (FORBIDDEN_MOTIONS.indexOf(group) >= 0) { return { motion: null, blocked: group } }
    if (!motionGroupExists(group)) { return { motion: null, missing: group } }
    try { model.motion(group); return { motion: group, hold: !!hold } } catch (e) { return { motion: null, error: String(e) } }
  }
  /** 停动作：必须 stopMotion + clearMotionPose，否则最后一帧会被一直装回来（SPEC §10 坑 6）。*/
  function stopMotions() {
    if (!model) return
    try {
      var mm = model.internalModel.motionManager
      if (mm && typeof mm.stopAllMotions === 'function') { mm.stopAllMotions() }
      if (mm && typeof mm.clearMotionPose === 'function') { mm.clearMotionPose() }
    } catch (e) { }
  }
  /** 帧内读一个参数（必须在 beforeModelUpdate 里调用，帧外拿到的是基线）。*/
  function readParam(id) {
    var core = coreModel()
    if (!core || typeof core.getParameterValueById !== 'function') return null
    try { return core.getParameterValueById(id) } catch (e) { return null }
  }
  /** 帧内写一个参数。*/
  function writeParam(id, value) {
    var core = coreModel()
    if (!core || typeof core.setParameterValueById !== 'function') return false
    try { core.setParameterValueById(id, value); return true } catch (e) { return false }
  }

  /* ——————— ?selftest=1：44 个表情逐个实测（生产页面 + 生产模型 + 真实 ticker）
     读参数必须在帧内（beforeModelUpdate），并且让 now 连续推进 ~1.6 s，否则会误报
     0/44——见 pet/REACTIONS-SPEC.md §0.2 / §10 坑 1-3。 */
  function startSelfTest() {
    var names = expressionNames()
    if (!names.length) {
      SELFTEST = { ok: false, error: 'expressionManager undefined or 0 definitions' }
      postToHost({ selftest: SELFTEST })
      return
    }
    names.sort()
    SELFTEST = { ok: true, definitions: names.length, order: names, index: 0, results: [], neutral: null, t0: Date.now() }
    onFrame(function () {
      if (!SELFTEST || !SELFTEST.want) return
      var core = coreModel()
      if (!core || typeof core.getParameterCount !== 'function') return
      var n = core.getParameterCount(), sum = 0
      for (var i = 0; i < n; i++) { sum += core.getParameterValueByIndex(i) }
      SELFTEST.want = false
      SELFTEST.lastFingerprint = Math.round(sum * 1000) / 1000
    })
    var em = null
    try { em = model.internalModel.motionManager.expressionManager } catch (e) { em = null }
    if (!em) { SELFTEST.ok = false; SELFTEST.error = 'expressionManager undefined'; postToHost({ selftest: SELFTEST }); return }
    try { em.resetExpression() } catch (e) { }
    setTimeout(function () { SELFTEST.want = true; setTimeout(selfTestReadNeutral, 60) }, 1600)
  }
  function selfTestReadNeutral() {
    SELFTEST.neutral = SELFTEST.lastFingerprint
    selfTestNext()
  }
  function selfTestNext() {
    if (!SELFTEST) return
    var i = SELFTEST.index
    if (i >= SELFTEST.order.length) {
      SELFTEST.ms = Date.now() - SELFTEST.t0
      postToHost({ selftest: selfTestSummary() })
      return
    }
    var name = SELFTEST.order[i]
    var em = null
    try { em = model.internalModel.motionManager.expressionManager } catch (e) { em = null }
    var accepted = expressionDefined(name)
    if (accepted && em) { try { em.setExpression(name) } catch (e) { accepted = false } }
    SELFTEST.pending = { name: name, accepted: accepted }
    setTimeout(function () {
      SELFTEST.want = true
      setTimeout(function () {
        var fp = SELFTEST.lastFingerprint
        var delta = Math.round((fp - SELFTEST.neutral) * 1000) / 1000
        // A real expression moves the frame sum; 0.05 is the noise floor (the
        // smallest genuine move observed is +0.21: `whaleOnDesk` adds 1 to a
        // parameter that is already near its clamped maximum).
        SELFTEST.results.push({ name: SELFTEST.pending.name, accepted: SELFTEST.pending.accepted, fingerprint: fp, delta: delta, changed: Math.abs(delta) > 0.05 })
        SELFTEST.index += 1
        selfTestNext()
      }, 60)
    }, 1600)
  }
  function selfTestSummary() {
    if (!SELFTEST) return null
    var out = { ok: SELFTEST.ok, definitions: SELFTEST.definitions, neutral: SELFTEST.neutral, ms: SELFTEST.ms, phase: SELFTEST.phase }
    if (SELFTEST.results) {
      out.done = SELFTEST.results.length
      out.accepted = SELFTEST.results.filter(function (r) { return r.accepted }).length
      out.changed = SELFTEST.results.filter(function (r) { return r.changed }).length
      out.failures = SELFTEST.results.filter(function (r) { return !r.changed }).map(function (r) { return r.name })
      out.results = SELFTEST.results
    }
    return out
  }
  function postToHost(payload) {
    try {
      if (window.chrome && chrome.webview && chrome.webview.postMessage) { chrome.webview.postMessage(payload) }
    } catch (e) { }
    // 同时在页面里留一份，方便直接看
    try { window.__PET_SELFTEST__ = payload } catch (e) { }
  }

  /* ——————— pet-watch：帧内参数取样（验收证据用，也是"待机到底有没有在播动作"的判据）
     为什么必须帧内：帧外读到的参数是引擎每帧还原后的基线，动作在播也会读成"不动"
     （REACTIONS-SPEC §10 坑 1）。这里挂在 beforeModelUpdate 钩子里，200 ms 一个点。
     同时记录 motionManager 的 playing / 队列长度 / 每组的 idle 名，用来判断
     "有没有常驻动作在循环"。 */
  var WATCH = null
  function startMotionWatch(ms, ids) {
    var params = ids && ids.length ? ids : ['ParamAngleX', 'ParamAngleY', 'ParamAngleZ', 'ParamBodyAngleX', 'ParamBodyAngleZ', 'ParamArmLA', 'ParamArmRA', 'ParamMouthOpenY', 'ParamBreath', 'ParamEyeLOpen', 'ParamEyeROpen']
    var mm = null
    try { mm = model.internalModel.motionManager } catch (e) { mm = null }
    var em = null
    try { em = mm ? mm.expressionManager : null } catch (e) { em = null }
    WATCH = { ms: ms, params: params, samples: [], t0: Date.now(), last: 0, done: false }
    WATCH.meta = {
      idleGroup: mm && mm.groups ? mm.groups.idle : null,
      motionGroupsLoaded: mm && mm.motionGroups ? Object.keys(mm.motionGroups).filter(function (k) { return mm.motionGroups[k] && mm.motionGroups[k].length }).join(',') : null,
      expressions: em && em.definitions ? em.definitions.length : null,
    }
    onFrame(function () {
      if (!WATCH || WATCH.done) return
      var t = Date.now()
      if (t - WATCH.last < 200) return
      WATCH.last = t
      var row = { t: t - WATCH.t0 }
      for (var i = 0; i < params.length; i++) { row[params[i]] = readParam(params[i]) }
      try {
        row._playing = !!(mm && mm.playing)
        row._queued = mm && mm._motions ? mm._motions.length : null
      } catch (e) { }
      WATCH.samples.push(row)
      // 短 TTL 的一次性动作/报错会在取样窗口末尾就过期，所以把**第一个样本**的层级
      // 快照也留下来（验收读数用的是它）。
      if (!WATCH.firstReactions && window.PetReactions && window.PetReactions.snapshot) {
        WATCH.firstReactions = window.PetReactions.snapshot()
        WATCH.firstApplied = (stateDoc && stateDoc.applied) ? stateDoc.applied : null
      }
      if (t - WATCH.t0 >= ms) {
        WATCH.done = true
        var ranges = {}
        for (var p = 0; p < params.length; p++) {
          var id = params[p], lo = Infinity, hi = -Infinity
          for (var s = 0; s < WATCH.samples.length; s++) {
            var v = WATCH.samples[s][id]
            if (typeof v === 'number') { if (v < lo) lo = v; if (v > hi) hi = v }
          }
          ranges[id] = (lo === Infinity) ? null : { min: Math.round(lo * 1000) / 1000, max: Math.round(hi * 1000) / 1000, span: Math.round((hi - lo) * 1000) / 1000 }
        }
        var report = {
          ok: true, ms: ms, samples: WATCH.samples.length, meta: WATCH.meta,
          playingSeen: WATCH.samples.some(function (r) { return r._playing === true }),
          queuedMax: WATCH.samples.reduce(function (a, r) { return Math.max(a, r._queued || 0) }, 0),
          ranges: ranges,
          moving: Object.keys(ranges).filter(function (k) { return ranges[k] && ranges[k].span > 0.5 }),
          // 反应层当时的层级快照：base/override/anim/userProps/applied（验收读数）
          reactions: (window.PetReactions && window.PetReactions.snapshot) ? window.PetReactions.snapshot() : null,
          applied: (stateDoc && stateDoc.applied) ? stateDoc.applied : null,
          firstReactions: WATCH.firstReactions || null,
          firstApplied: WATCH.firstApplied || null,
        }
        postToHost({ motionWatch: report })
        return
      }
    })
  }
  function motionWatchResult() { return WATCH && WATCH.done ? WATCH : null }

  var labelEl = document.getElementById('state-label')
  var detailEl = document.getElementById('state-detail')
  var stateDoc = null

  /** 一个元素的视口矩形（页面 CSS px）。 */
  function rectOf(el) {
    if (!el) return null
    var r = el.getBoundingClientRect()
    return { left: r.left, top: r.top, width: r.width, height: r.height, text: el.textContent || '', color: el.style ? el.style.color : '' }
  }

  /* ——————— 标签定位：以人物包围盒 + 看板实测文字为基准 ———————
     硬约束（任务书 task-5 之后）：
       labelTop   >= modelTop    标签上边缘不得高于人物包围盒上边缘
       labelRight <= modelRight  标签右边缘不得超出人物包围盒右边缘
       labelRight == 看板右对齐文字的右边缘（±1）
       labelTop    == 看板上方那一行文字底边 + 10~14px

     前两条靠人物测量，后两条靠看板侧的实测值：面板每 1.5s 把它的
     content Grid 右边缘（= 321.8M tok / 后台进度值所在列的右边缘）与
     TodayTok 底边写进 ./panel-geometry.json（页面 CSS px，视口原点），
     页面在这里取用。文件缺失/过期时退回「贴人物包围盒」的老规则。 */
  var LABEL_GAP = 2          // 与人物边界的余量
  var GEOM_URL = './panel-geometry.json'
  var GEOM = null            // {labelRightPage, labelTopPage, at}
  var GEOM_STALE_MS = 15000

  function applyGeometry(doc) {
    if (!doc || typeof doc !== 'object') return
    var at = typeof doc.at === 'number' ? doc.at : null
    if (at !== null && Date.now() - at > GEOM_STALE_MS) return
    var right = typeof doc.labelRightPage === 'number' ? doc.labelRightPage : null
    var top = typeof doc.labelTopPage === 'number' ? doc.labelTopPage : null
    if (right === null || top === null) return
    GEOM = { right: right, top: top, at: at, gapY: doc.gapY }
    placeState()
  }

  function placeState() {
    var b = SIL || BOX
    if (!b || !labelEl) { return false }   // 还没量到人物：先不显示，免得标签飘在窗口角上
    var vw = window.innerWidth, vh = window.innerHeight
    labelEl.style.right = 'auto'
    if (detailEl) detailEl.style.right = 'auto'
    // 先摆到原点量自然尺寸（固定定位元素因此拿到真实宽高）
    labelEl.style.left = '0px'
    labelEl.style.top = '0px'
    var lw = labelEl.offsetWidth || 0
    var lh = labelEl.offsetHeight || 0
    // 右边缘：优先看板实测的右对齐文字右边缘，但绝不超过人物右边界
    var right = b.x + b.w - LABEL_GAP
    if (GEOM && GEOM.right < right) { right = GEOM.right }
    // 上边缘：优先看板的「上方那行文字底边 + gap」，但不高于人物上边界
    var top = b.y + LABEL_GAP
    if (GEOM && GEOM.top > top) { top = GEOM.top }
    var left = right - lw
    if (left < 0) left = 0
    if (left + lw > vw) left = Math.max(0, vw - lw)
    if (top < 0) top = 0
    if (top + lh > vh) top = Math.max(0, vh - lh)
    labelEl.style.left = Math.round(left) + 'px'
    labelEl.style.top = Math.round(top) + 'px'
    labelEl.classList.add('on')
    if (detailEl) {
      detailEl.style.left = '0px'
      detailEl.style.top = '0px'
      var dw = Math.min(detailEl.offsetWidth || 0, vw)
      var dleft = right - dw
      if (dleft < 0) dleft = 0
      var dtop = top + lh + 2
      if (dtop + (detailEl.offsetHeight || 0) > vh) dtop = Math.max(0, vh - (detailEl.offsetHeight || 0))
      detailEl.style.left = Math.round(dleft) + 'px'
      detailEl.style.top = Math.round(dtop) + 'px'
      detailEl.classList.toggle('on', (detailEl.textContent || '').length > 0)
    }
    return true
  }

  function applyState(doc) {
    if (!doc || typeof doc !== 'object') return
    stateDoc = doc
    var key = String(doc.state || '')
    var frozen = FROZEN[key]
    var text = doc.label || (frozen && frozen.label) || key
    var color = doc.color || (frozen && frozen.color) || '#9DA7B3'
    var pose = doc.pose || (frozen && frozen.pose) || 'idle'
    stateDoc.pose = pose

    labelEl.textContent = text
    labelEl.style.color = color
    detailEl.textContent = doc.detail || ''
    // 可见性也交给 placeState：量到人物包围盒之前不显示（避免先飘在窗口右上角）
    placeState()
    // 表情/动作策略在 reactions.js（本文件只提供机制）
    if (window.PetReactions && PetReactions.applyStateDoc) {
      try { PetReactions.applyStateDoc(stateDoc) } catch (e) { }
    }
    document.title = 'DS 鲸鱼娘 · ' + key + ' ' + text
  }

  var forced = q.get('state')
  // `?state=` 会关掉 state.json 轮询；展示拍图的强制通道（见下）也会，两者共用一个开关。
  var FORCED = !!forced
  if (forced) applyState({ state: forced, label: (FROZEN[forced] || {}).label, color: (FROZEN[forced] || {}).color })

  window.addEventListener('message', function (ev) {
    var d = ev && ev.data
    if (!d || typeof d !== 'object') return
    if (d.type === 'pet-state') { applyState(d.payload || d.state); return }
    /* 帧内参数取样：{type:'pet-watch', payload:{ms, params}} -> 结果 postMessage 回宿主
       （pet\host\page-message.json）。用来判"待机有没有在播动作"和给动作/表情取实测读数。 */
    if (d.type === 'pet-watch') {
      var w = d.payload || {}
      startMotionWatch(w.ms || 6000, w.params)
      return
    }
    if (d.type === 'pet-force') {
      var p = d.payload
      if (!p) {
        FORCED = false
        if (window.PetReactions && PetReactions.setForced) { try { PetReactions.setForced(null) } catch (e) { } }
        return
      }
      FORCED = true
      applyState({
        state: p.state, label: p.label, color: p.color,
        detail: p.detail === undefined ? '' : p.detail,
        pose: p.pose, reason: p.reason, source: 'forced',
      })
      if (window.PetReactions) {
        try {
          // task-15 A: a forced state must play its visible motion too, otherwise the
          // showcase shots (which are taken through this very channel) stay identical.
          if (PetReactions.playVisibleMotion && PetReactions.stateMotion) {
            PetReactions.playVisibleMotion((PetReactions.stateMotion() || {})[p.state], 'forced:' + p.state)
          }
          if (PetReactions.setForced) { PetReactions.setForced(p.signals || null, p.state, !!p.clearBubble) }
          // 上游能力的宿主/展示通道（没有鼠标，所以用参数驱动；UPSTREAM-GAP §5.3）
          if (p.props && PetReactions.setProps) { PetReactions.setProps(p.props) }
          if (p.act && PetReactions.act) { PetReactions.act(p.act, 'forced') }
          if (p.lowPower !== undefined && PetReactions.setLowPower) { PetReactions.setLowPower(!!p.lowPower) }
        } catch (e) { }
      }
    }
  })

  // 轮询 state.json（不存在就安静地什么都不显示，不影响桌宠本身）
  var STATE_URL = './state.json'
  function pollState() {
    if (forced || FORCED) return
    fetch(STATE_URL + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null })
      .then(function (j) { if (j) applyState(j) })
      .catch(function () { /* 没有 state.json 是正常情况 */ })
  }
  setTimeout(pollState, 300)
  setInterval(pollState, 1500)

  // 轮询看板侧发布的两个标签锚点（存在 panel-geometry.json 里）
  function pollGeometry() {
    fetch(GEOM_URL + '?t=' + Date.now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null })
      .then(function (j) { if (j) applyGeometry(j) })
      .catch(function () { /* 没有这个文件就退回贴人物包围盒 */ })
  }
  pollGeometry()
  setInterval(pollGeometry, 1500)
})()
