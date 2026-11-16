/**
 * reactions.js —— 她怎么反应（**策略层**）
 *
 * 机制在 pet-app.js（帧内参数叠加、动作播放、口型、DOM 气泡），本文件只决定
 * 「现在该是什么脸、什么道具、说什么话、定格什么动作」，输入两个文件：
 *
 *   state.json    活动类别（由 ENGINE 用 pet/state.mjs 算好，页面不判断状态）
 *   signals.json  反应信号（同一个 engine 从 DSH 会话日志折叠出来的紧凑信号：
 *                 最新工具名/成败/摘要、回合结束与用时花销、是否正在逐字输出、久闲时长）
 *
 * 规格：pet/REACTIONS-SPEC.md（§3 对应表 / §4 优先级与打断 / §10 坑）。
 * 四条硬规则（SPEC §4）：
 *   1. 只有一个 base 表情，override 是一次性的、带 TTL，到点必回落；
 *   2. 工具报错只黑 1.6 s 且不叠任何别的东西，随后回到当时的活动；
 *   3. 每秒都查一次看门狗：空闲时 base 必须回到平常脸，不允许卡在某个表情上；
 *   4. 素材缺失一律静默退回（不抛错）。
 *
 * 交互（摸头/摸身体/连点炸毛）不做：桌宠窗口按架构天生鼠标穿透，
 * 收不到点击（REACTIONS-SPEC §7.5 已标注为「受架构限制，不做」）。
 */
;(function () {
  'use strict'

  var q = new URLSearchParams(location.search)
  var SIGNALS_URL = './signals.json'
  var Pet = function () { return window.PetAPI || null }

  /* ——————— 台词（原文照抄 REACTIONS-SPEC §3.2/§3.4 的语气，取短的） ——————— */
  var SAY = {
    reading: ['（凑近看）先读一下这份', '人家看看里面写了啥', '翻开看看…', '（认真脸）读一下'],
    grep: ['（眯着眼）搜一下关键词', '人家查查哪里用到了', '（翻）搜搜看'],
    glob: ['（翻箱倒柜）找找在哪儿', '人家找找这个文件', '翻一下目录'],
    web: ['（掏手机）上网查一下', '人家搜搜看', '（划手机）查查这个', '网上应该有答案'],
    fetch: ['（点开链接）读读这页', '人家看看这个网页', '（凑近屏幕）'],
    writing: ['好，人家写出来', '（奋笔疾书）写上了', '这就给你落成文件', '写成文件啦'],
    edit: ['（改改改）这里调一下', '人家修一下这行', '（落笔）改好了'],
    running: ['（挽袖子）跑个命令试试', '让人家敲两行命令', '命令行交给人家', '（噼里啪啦）跑起来了'],
    todo: ['（列清单）先排个计划', '人家记一下要做啥', '（在本子上划拉）'],
    team: ['（招手）叫个分身来帮忙', '人家派个分身去办', '（分工）这就安排'],
    present: ['（举起来）喏，给你', '人家交付啦', '（递过去）弄好了'],
    done: ['搞定啦，收工！', '（伸懒腰）总算做完了', '都弄好了，主人看看？'],
    fail: ['呜…这个报错了', '（脸黑了）出问题了', '好像不太对…'],
    aborted: ['诶…人家还没做完呢', '被打断了…'],
    idle: ['（发呆）…', '人家在呢', '（东张西望）', '…要不要喝点水？'],
    hungry: ['（肚子叫）有点饿了…', '人家想吃蛋包饭', '（看着零食）'],
    nopang: ['人家才不胖！', '（生气）不许说这个'],
    sleep: ['（打哈欠）困了…', '（趴下）眯一会儿'],
  }

  /* ——————— 工具名 → 活动（SPEC §3.2；我们实际会看到的工具名都列上） ——————— */
  var TOOL_MAP = {
    read: 'reading', pdf_read: 'reading', docx_read: 'reading', xlsx_read: 'reading', pptx_read: 'reading',
    skill: 'reading', auto_cite: 'reading', grep: 'grep', glob: 'glob', ls: 'glob', list_dir: 'glob',
    web_search: 'web', web_fetch: 'fetch', browser: 'fetch', fetch: 'fetch',
    search_papers: 'web', search_arxiv: 'web', kb_search: 'web', kb_rag: 'web', kb_ingest: 'reading',
    write: 'writing', edit: 'edit', todo_write: 'todo', present: 'present',
    bash: 'running', pwsh: 'running', shell: 'running', run_command: 'running', command: 'running', exec: 'running',
    subagent: 'team', subagent_fork: 'team', task: 'team', workflow: 'team', ralph: 'team',
    team_task_create: 'team', team_task_update: 'team', team_task_get: 'thinking', team_task_list: 'thinking',
    send_message: 'team', list_agents: 'thinking',
    ask_user_question: 'asking', create_goal: 'goal', update_goal: 'thinking', get_goal: 'thinking',
    job_output: 'running', job_list: 'thinking', present_files: 'present',
  }
  /* ——————— 诊断登记处（task-15 D：静默失败清零） ———————
     任何"名字不认识"都必须留痕：console.warn + 可查字段 + 推给宿主。task-14 的教训是
     传了不存在的 pose 名，页面安静回退，画面零变化而没有任何人知道。 */
  var DIAG = { unknownPose: [], unknownProp: [], unknownExpression: [], missingMotion: [], blockedMotion: [], errors: [], lastAt: 0 }
  function diag(kind, name, extra) {
    try {
      var row = { at: now(), kind: kind, name: String(name), extra: extra || null }
      if (!DIAG[kind]) { DIAG[kind] = [] }
      DIAG[kind].push(row)
      while (DIAG[kind].length > 40) { DIAG[kind].shift() }
      DIAG.lastAt = row.at
      if (window.console && console.warn) { console.warn('[pet-diag] ' + kind + ': ' + name, extra || '') }
      var api = Pet()
      if (api && api.postToHost) { api.postToHost({ diag: row }) }
    } catch (e) { }
  }
  function diagnostics() {
    return {
      unknownPose: DIAG.unknownPose.slice(), unknownProp: DIAG.unknownProp.slice(),
      unknownExpression: DIAG.unknownExpression.slice(), missingMotion: DIAG.missingMotion.slice(),
      blockedMotion: DIAG.blockedMotion.slice(), errors: DIAG.errors.slice(), lastAt: DIAG.lastAt,
      counts: { pose: DIAG.unknownPose.length, prop: DIAG.unknownProp.length, expr: DIAG.unknownExpression.length,
                motion: DIAG.missingMotion.length + DIAG.blockedMotion.length, errors: DIAG.errors.length },
    }
  }

  /** 活动 → { face 池, 道具, 视线 bias, 台词池 }（SPEC §3.1/§3.2） */
  var ACT = {
    reading: { faces: ['glassesRound', 'glassesSquare', 'null', 'glassesOval'], weights: [34, 28, 28, 10], props: ['menuPress', 'brush'], gazeY: -0.32, say: 'reading' },
    grep: { faces: ['glassesRound', 'glassesSquare', 'null', 'glassesOval'], weights: [34, 28, 28, 10], props: ['menuPress', 'brush'], gazeY: -0.32, say: 'grep' },
    glob: { faces: ['null'], props: ['menuPress', 'brush'], gazeY: -0.18, say: 'glob' },
    web: { faces: ['glassesRound', 'glassesSquare', 'null'], weights: [40, 30, 30], props: [], device: true, gazeY: -0.2, say: 'web' },
    fetch: { faces: ['glassesRound', 'null'], weights: [50, 50], props: [], device: true, gazeY: -0.2, say: 'fetch' },
    writing: { faces: ['null'], props: ['menuPress', 'brush'], gazeY: -0.1, say: 'writing' },
    edit: { faces: ['null'], props: ['menuPress', 'brush'], gazeY: -0.1, say: 'edit' },
    todo: { faces: ['stickerCat'], props: ['menuPress', 'brush'], say: 'todo' },
    running: { faces: ['null'], props: ['menuPress', 'brush'], say: 'running' },
    team: { faces: ['null'], props: ['menuPress', 'brush'], say: 'team' },
    present: { faces: ['excited'], props: [], say: 'present' },
    asking: { faces: ['question'], props: ['menuPress', 'brush'], say: 'idle' },
    goal: { faces: ['exclaim'], props: [], say: 'idle' },
    thinking: { faces: ['null'], props: ['menuPress', 'brush'] },
    neutral: { faces: ['null'], props: ['menuPress', 'brush'] },
    celebrating: { faces: ['excited'], props: [], oneShot: 3000 },
    error: { faces: ['gloomy'], props: [], oneShot: 1600 },
    listening: { faces: ['starry'], props: [], oneShot: 2600 },
    sleepy: { faces: ['drool'], props: [] },
    offline: { faces: ['gloomy'], props: [] },
    idle: { faces: ['null'], props: [] },
  }

  /* ══════════════════════════════════════════════════════════════════════════
     上游三张表（零新增素材：全部由 44 个表情 + 8 个动作驱动）
       DECOR   装饰：每项占一个 slot，**同 slot 互斥**（上游 `PROPS 116-128` / `setProp 892` 的 group）
       SCENES  场景：常驻，可带 `needs` 前置（上游 `SCENES 137-145`）
       ACTIONS 一次性动作：`act()` 合成「一个表情 + 至多一个动作 + 时长记账」（上游 `ACTIONS 176-221` / `act 1351`）
     素材名一律照抄 `REACTIONS-SPEC.md` §1.1 的短英文名（= model3.json 里声明的 Name）。
     ══════════════════════════════════════════════════════════════════════════ */
  var DECOR = {
    // 眼镜（4 副互斥，组 glasses）
    glassesRound: { slot: 'glasses', expr: 'glassesRound' },
    glassesSquare: { slot: 'glasses', expr: 'glassesSquare' },
    glassesOval: { slot: 'glasses', expr: 'glassesOval' },
    sunglasses: { slot: 'glasses', expr: 'sunglasses' },
    // 贴纸（3 张互斥，组 sticker）
    stickerCat: { slot: 'sticker', expr: 'stickerCat' },
    stickerRabbit: { slot: 'sticker', expr: 'stickerRabbit' },
    stickerBow: { slot: 'sticker', expr: 'stickerBow' },
    // 头部（情绪花花与头箍互斥，组 headwear）
    sparkle: { slot: 'headwear', expr: 'sparkle' },
    headband: { slot: 'headwear', expr: 'headband' },
    // 发型（组 hair）
    ponytail: { slot: 'hair', expr: 'ponytail' },
    whaleHat: { slot: 'hair', expr: 'whaleHat' },
  }
  var SCENES = {
    darkCloth: { slot: 'cloth', expr: 'darkCloth' },
    whaleOnDesk: { slot: 'deskWhale', expr: 'whaleOnDesk' },
    parfait: { slot: 'deskParfait', expr: 'parfait' },
    claw: { slot: 'claw', expr: 'claw' },
    clawRecolor: { slot: 'clawColor', expr: 'clawRecolor', needs: 'claw' },
    phone: { slot: 'device', motion: 'openLid', hold: true },
    phoneRecolor: { slot: 'deviceColor', expr: 'phoneRecolor', needs: 'phone' },
  }
  var ACTIONS = {
    // 上游 ACTIONS.paw 播的就是 idle 那一支（猫爪摆手 + 爱心），4 400 ms —— 只播一次，
    // 绝不当待机循环（上游已停用常驻；见 §5.4）。
    paw: { motion: 'idle', ms: 4400, say: null },
    catPaw: { expr: 'catPaws', ms: 3000 },
    doubleV: { expr: 'doubleV', ms: 2800 },
    love: { expr: 'heartPop', ms: 3200, pulse: true },
    heartbeat: { expr: 'heartbeat', ms: 3200, pulse: true },
    squeeze: { expr: 'squeeze', ms: 2600 },
    eraser: { expr: 'eraser', ms: 2600 },
    undo: { expr: 'undo', ms: 2600 },
    omurice: { expr: 'omurice', motion: 'ketchup', ms: 6200 },
    selfie: { motion: 'selfie', ms: 3600, needs: 'phone' },
    selfieQuick: { motion: 'selfieQuick', ms: 2000, needs: 'phone' },
    splash: { motion: 'splash', ms: 2200 },
  }
  var ACTION_ORDER = ['paw', 'catPaw', 'doubleV', 'love', 'heartbeat', 'squeeze', 'eraser', 'undo', 'omurice', 'selfie', 'selfieQuick', 'splash']

  /* ——————— 用户常驻层（上游 `rig.user` / `userProps`，最高优先级、不限期） ———————
     装饰与场景是"用户的"，不吃 TTL、不随活动变化；工具事件只改 base 或给短 TTL，
     绝不写这里（否则就会出现上游反复修的"道具赖着不走"）。localStorage 持久化。 */
    /* ——————— 可见动作（task-15 A）———————
       模型声明的 motion 组有八个，其中**两个是原作者明确停用的**（见 pet-app.js 的
       FORBIDDEN_MOTIONS，运行时由 PetAPI.forbiddenMotions() 提供，不在本文件里硬编码），
       idle 是待机循环——这三类都不许用；剩下四个一次性 clip（1.5~2.5 s）用来表达"她在做事"。 */
    var VISIBLE_MOTIONS = { selfie: 3600, selfieQuick: 2000, openLid: 2400, splash: 2200 }
    /* 与 pet/state.mjs 的 POSE_VALUES 对齐：传了表外的姿势名 = 安静回退，必须留痕（D）。 */
    var KNOWN_POSES = ['idle', 'reading', 'scribble', 'sleeves', 'thinking', 'gloomy', 'happy',
      'starry', 'team', 'sleepy', 'offline']
    var STATE_MOTION = {
      celebrating: 'selfie', listening: 'selfieQuick', team: 'selfie',
      reading: 'openLid', writing: 'selfieQuick', running: 'splash', thinking: 'openLid',
      error: 'splash', stale: 'openLid', offline: 'splash', idle: null,
    }
    var TOOL_MOTION = {
      running: 'splash', reading: 'openLid', grep: 'openLid', glob: 'openLid', web: 'openLid',
      fetch: 'openLid', writing: 'selfieQuick', edit: 'selfieQuick', todo: 'selfieQuick',
      team: 'selfie', present: 'selfie',
    }
    var lastMotionAt = 0
    var lastMotionName = null
    /** 播一段完整动作（hold=false：走完自己回落，不循环）。返回是否真的播了。 */
    function playVisibleMotion(name, why) {
      if (!name) { return false }
      var api = Pet()
      if (!api || !api.playMotion) { return false }
      if (!VISIBLE_MOTIONS[name]) {
        // ask the mechanism layer which names are blocked instead of hard-coding them
        var fb = (typeof api.forbiddenMotions === 'function') ? api.forbiddenMotions() : api.forbiddenMotions
        var blocked = !!(fb && fb.length && fb.indexOf(name) >= 0)
        diag(blocked ? 'blockedMotion' : 'missingMotion', name, why || null)
        return false
      }
      var t0 = now()
      if (t0 - lastMotionAt < 900) { return false }
      var r = null
      try { r = api.playMotion(name, false) } catch (e) { r = { error: String(e) } }
      if (!r || !r.motion) {
        diag('missingMotion', name, r ? (r.missing ? 'motionGroupExists=false' : (r.error || r.blocked)) : 'null')
        return false
      }
      lastMotionAt = t0
      lastMotionName = name
      log({ t: t0, kind: 'motion', motion: name, why: why || null })
      return true
    }

  var userProps = {}                       // slot -> key
  var STORE_KEY = 'dsh-live2d-pet:props'
    function propSpec(key) {
      var s = DECOR[key] || SCENES[key] || null
      if (!s) { diag('unknownProp', key, 'not in DECOR or SCENES') }
      return s
    }
  function isOn(key) { var s = propSpec(key); return !!(s && userProps[s.slot] === key) }
  function propsOn() { return Object.keys(userProps).map(function (slot) { return userProps[slot] }) }
  function loadUserProps() {
    try {
      var raw = window.localStorage ? window.localStorage.getItem(STORE_KEY) : null
      if (raw) { var o = JSON.parse(raw); if (o && typeof o === 'object' && !Array.isArray(o)) { userProps = o } }
    } catch (e) { }
  }
  function saveUserProps() {
    try { if (window.localStorage) window.localStorage.setItem(STORE_KEY, JSON.stringify(userProps)) } catch (e) { }
  }

  /**
   * 开关一个装饰/场景。同 slot 自动互斥；`needs` 前置自动补齐；关掉前置时依赖它的
   * 一起关（上游 `setProp 892-946` 的 group/needs/clears）。
   * @param {string} key - DECOR / SCENES 的键。
   * @param {boolean} on - true 打开，false 关闭。
   * @returns {{key: string, on: boolean, props: string[]} | null}
   */
  function setProp(key, on, why) {
    var spec = propSpec(key)
    if (!spec) return null
    if (on) {
      if (spec.needs && !isOn(spec.needs)) { setProp(spec.needs, true, 'needs ' + key) }
      userProps[spec.slot] = key
      if (spec.motion && !held) { startDevice() }
    } else {
      if (userProps[spec.slot] === key) { delete userProps[spec.slot] }
      Object.keys(userProps).forEach(function (slot) {
        var k = userProps[slot]
        var s = propSpec(k)
        if (s && s.needs === key) { delete userProps[slot] }
      })
      if (spec.motion && held) { clearDevice('prop off') }
    }
    saveUserProps()
    applyLayers()
    log({ t: now(), kind: 'prop', key: key, on: !!on, props: propsOn(), why: why || null })
    return { key: key, on: !!on, props: propsOn() }
  }
  /** 用一份清单**替换**用户层（展示/调试用；空数组=全部摘下）。 */
  function setProps(list) {
    userProps = {}
    Object.keys(DECOR).forEach(function (k) { })
    ;(list || []).forEach(function (k) { var s = propSpec(k); if (s) { userProps[s.slot] = k } })
    // 补齐前置
    Object.keys(userProps).forEach(function (slot) {
      var s = propSpec(userProps[slot])
      if (s && s.needs) { var n = propSpec(s.needs); if (n) { userProps[n.slot] = s.needs } }
    })
    if (isOn('phone') && !held) { startDevice() } else if (!isOn('phone') && held) { clearDevice('props replaced') }
    saveUserProps()
    applyLayers()
    return propsOn()
  }

  /* ——————— 一次性动作：act() 合成「一个表情 + 至多一个动作 + 粒子脉冲」 ——————— */
  var anim = null                          // { name, spec, until, face }
  var pulseTimer = null
  /**
   * 归零协议（上游 `stopActing 1151`）：先停动作、清姿势，再上新的。
   */
  function stopActing(why) {
    var api = Pet()
    if (api && api.stopMotions) { api.stopMotions() }
    if (pulseTimer) { clearInterval(pulseTimer); pulseTimer = null }
    if (anim) { log({ t: now(), kind: 'act-stop', name: anim.name, why: why || null }); anim = null }
  }
  /**
   * 播一个一次性动作。动作素材自带表情时以动作为准（上游 `FACE_DRIVING_MOTIONS 1108`）；
   * 时长按上游 `ACTIONS` 记账，到点自动回落。
   * @param {string} name - ACTIONS 的键。
   * @returns {{name: string, ms: number, expr: string|null, motion: string|null} | null}
   */
  function act(name, why) {
    var spec = ACTIONS[name]
    if (!spec) return null
    if (spec.needs && !isOn(spec.needs)) { setProp(spec.needs, true, 'needs act ' + name) }
    stopActing('act ' + name)
    if (spec.motion) { var r = Pet().playMotion(spec.motion, !!spec.hold) }
    anim = { name: name, spec: spec, until: now() + spec.ms, face: spec.expr || null }
    if (spec.pulse && spec.expr) {
      // 爱心/心跳的"脉冲"：重复上脸三次（上游 love/heartbeat 靠粒子，我们用表情再触发）
      var n = 0
      pulseTimer = setInterval(function () {
        n += 1
        if (n >= 3 || !anim || anim.name !== name) { clearInterval(pulseTimer); pulseTimer = null; return }
        mergePulse()
      }, 480)
    }
    applyLayers()
    log({ t: now(), kind: 'act', name: name, ms: spec.ms, expr: spec.expr || null, motion: spec.motion || null, why: why || null })
    return { name: name, ms: spec.ms, expr: spec.expr || null, motion: spec.motion || null }
  }
  function mergePulse() { applyLayers() }

  /* ——————— qBounce：收工蹦一下（纯 CSS 位移，不碰模型参数；往下弹，不往看板方向） ——————— */
  function qBounce() {
    var el = document.querySelector('canvas')
    if (!el || !el.classList) { return false }
    el.classList.remove('qbounce')
    void el.offsetWidth                        // 强制重排，让动画能重播
    el.classList.add('qbounce')
    setTimeout(function () { el.classList.remove('qbounce') }, 520)
    log({ t: now(), kind: 'qbounce' })
    return true
  }

  /* ——————— 低性能档（上游 `applyPerf 1451`：20 fps、关自主动作） ——————— */
  var lowPower = false
  function setLowPower(on) {
    lowPower = !!on
    try {
      var app = Pet().app && Pet().app()
      if (app && app.ticker) { app.ticker.maxFPS = lowPower ? 20 : 0 }
    } catch (e) { }
    log({ t: now(), kind: 'perf', lowPower: lowPower })
    return lowPower
  }

  /* ——————— 同池不重复抽取（上游 `pickFresh 502`），避免连着两次同一句 ——————— */
  var lastPick = {}
  function pickFresh(key, pool) {
    if (!pool || !pool.length) return ''
    if (pool.length === 1) return pool[0]
    var prev = lastPick[key]
    var tries = 0, chosen = pool[Math.floor(Math.random() * pool.length)]
    while (chosen === prev && tries < 8) { chosen = pool[Math.floor(Math.random() * pool.length)]; tries += 1 }
    lastPick[key] = chosen
    return chosen
  }

  /* ——————— 运行时状态 ——————— */
  var stateDoc = null
  var signals = null
  var signalSeen = { tool: null, turn: null, user: null, errorAt: 0, doneAt: 0, listenAt: 0 }
  var base = { act: 'idle', face: 'null' }
  var override = null            // { act, until, reason }
  var held = null                // 定格动作的参数快照
  var heldUntil = 0
  var faceDefs = {}              // name -> [{ id, value, blend }]
  var current = {}               // 参数当前值（做淡入）
  var target = {}                // 参数目标值
  var bubble = { text: '', foot: '', typed: 0, typing: false, until: 0 }
  var lastSignalsAt = 0
  var lastApplyAt = 0
  var lastStateApplyAt = 0
  var idleNextAt = Date.now() + 4000
  var workNextAt = Date.now() + 9000
  var lastIdleAction = ''
  var lastLog = []

  function now() { return Date.now() }
  function pick(list, weights) {
    if (!list.length) return null
    if (!weights) return list[Math.floor(Math.random() * list.length)]
    var total = 0
    for (var i = 0; i < weights.length; i++) total += weights[i]
    var r = Math.random() * total
    for (var j = 0; j < list.length; j++) { r -= weights[j]; if (r <= 0) return list[j] }
    return list[list.length - 1]
  }
  function pickLine(key) {
    var pool = SAY[key]
    // 同池不重复（上游 pickFresh 502）：连着两次同一句很出戏
    return pickFresh(key, pool)
  }
  function log(entry) {
    lastLog.push(entry)
    while (lastLog.length > 24) lastLog.shift()
    try { window.__PET_REACTIONS__ = lastLog } catch (e) { }
  }

  /* ——————— 表情参数表：从模型自己声明的 Expressions 读文件并解析 ——————— */
  function loadFaceDefs() {
    var api = Pet()
    if (!api || !api.model()) return
    var settings = null
    try { settings = api.model().internalModel.settings.expressions || [] } catch (e) { settings = [] }
    settings.forEach(function (d) {
      var name = d.Name
      var file = '../model/' + String(d.File).replace(/\\/g, '/')
      fetch(file)
        .then(function (r) { return r.ok ? r.json() : null })
        .then(function (j) {
          if (!j || !j.Parameters) return
          faceDefs[name] = j.Parameters.map(function (p) {
            return { id: p.Id, value: p.Value, blend: p.Blend || 'Add' }
          })
        })
        .catch(function () { })
    })
  }

  function mergeParams(into, name) {
    var def = faceDefs[name]
    if (!def) return
    for (var i = 0; i < def.length; i++) into[def[i].id] = def[i]
  }

  /* ——————— 选择：base（持续态）——SPEC §3.1/§3.2 ——————— */
  function actForState(state, pose) {
    switch (state) {
      case 'offline': return 'offline'
      case 'stale': return 'sleepy'
      case 'error': return 'error'
      case 'celebrating': return 'celebrating'
      case 'listening': return 'listening'
      case 'team': return 'team'
      case 'reading': return 'reading'
      case 'writing': return 'writing'
      case 'running': return 'running'
      case 'thinking': return 'thinking'
      default:
        if (pose === 'sleepy') return 'sleepy'
        return 'idle'
    }
  }

  function setBase(act, why) {
    if (base.act === act) return
    var spec = ACT[act] || ACT.neutral
    var face = pick(spec.faces, spec.weights)
    base = { act: act, face: face, spec: spec }
    applyLayers()
    log({ t: now(), kind: 'base', act: act, face: face, why: why })
  }

  function startOverride(act, ttl, why, say) {
    var spec = ACT[act] || ACT.neutral
    var face = pick(spec.faces, spec.weights)
    override = { act: act, face: face, spec: spec, until: now() + ttl }
    if (say) sayLine(say, null, ttl > 3000 ? 4200 : ttl + 900)
    applyLayers()
    log({ t: now(), kind: 'override', act: act, face: face, ttl: ttl, why: why })
  }

  /** 重新算层（后写的赢）：
      ① base 活动的常态道具（本子+笔）
      ② 用户常驻层 userProps（装饰/场景，同 slot 互斥）
      ③ override 的脸（error/celebrating/listening，带 TTL）
      ④ 一次性动作的脸（act()，最高）
      `exclusive:true` 的 override（上游报错那档）**连本子笔与用户的装饰/场景都放下**，
      并把定格的小设备收起来——"砸的时候就只砸一下"（UPSTREAM-GAP §5.4-2）。 */
  function applyLayers() {
    var api = Pet()
    if (!api || !api.model()) return
    var t = now()
    var inOverride = !!(override && t < override.until)
    var exclusive = !!(inOverride && override.exclusive)
    var params = {}
    var actState = inOverride ? override : base
    var spec = actState.spec || ACT.neutral
    var propsOnList = []
    if (!exclusive) {
      ;(spec.props || []).forEach(function (p) { propsOnList.push(p); mergeParams(params, p) })
      propKeysOn().forEach(function (k) {
        var s = propSpec(k)
        if (s && s.expr) { propsOnList.push(k); mergeParams(params, s.expr) }
      })
      if ((spec.device || isOn('phone')) && !held) { startDevice() }
    } else if (held) {
      clearDevice('exclusive', true)
    }
    if (actState.face && actState.face !== 'null') mergeParams(params, actState.face)
    if (anim && t < anim.until && anim.face) { mergeParams(params, anim.face); propsOnList.push('act:' + anim.name) }
    target = params
    var api2 = Pet()
    if (api2 && api2.getState && api2.getState()) {
      api2.getState().applied = {
        act: actState.act,
        face: (anim && t < anim.until && anim.face) ? anim.face : actState.face,
        props: propsOnList,
        override: inOverride,
        exclusive: exclusive,
        anim: anim && t < anim.until ? anim.name : null,
        userProps: propsOn(),
      }
    }
  }
  /** 装配层的键（不含 base 活动自身）——诊断与验收用。 */
  function propKeysOn() { return propsOn() }

  /* ——————— 道具动作：掏出小设备（openLid 定格）——————— */
  function startDevice() {
    var api = Pet()
    if (!api) return
    var r = api.playMotion('openLid', true)
    if (!r || !r.motion) { return }
    held = { sampling: true, at: now() }
    heldUntil = now() + 12000
    log({ t: now(), kind: 'device', motion: 'openLid', hold: true })
  }

  /** 动作播完后把当前参数冻住（框架没有 hold，我们自己保持最后一帧）*/
  function tickHeld() {
    if (!held) return
    var api = Pet()
    if (!api) return
    if (held.sampling) {
      if (now() - held.at < 1000) return          // openLid 时长 1.0 s
      var snapshot = {}
      // 在帧内读：这里由 onFrame 调用，正是 beforeModelUpdate 之后
      try {
        var core = api.coreModel()
        if (!core) return
        var n = core.getParameterCount()
        for (var i = 0; i < n; i++) {
          var id = core.getParameterId(i)
          snapshot[id] = { id: id, value: core.getParameterValueByIndex(i), blend: 'Overwrite' }
        }
      } catch (e) { return }
      held = { params: snapshot, at: held.at }
      log({ t: now(), kind: 'hold', params: Object.keys(snapshot).length })
    }
  }
  function clearDevice(why, noApply) {
    if (!held) return
    held = null
    var api = Pet()
    if (api && api.stopMotions) { api.stopMotions() }
    if (!noApply) { applyLayers() }
    log({ t: now(), kind: 'device-off', why: why })
  }

  /* ——————— 气泡（台词 + 脚注；逐字输出时逐字冒）——————— */
  function sayLine(text, foot, ttl) {
    if (!text) return
    bubble.text = text
    bubble.foot = foot || ''
    bubble.typed = 0
    bubble.typing = true
    bubble.until = now() + (ttl || 4000)
    renderBubble()
  }
  function sayIdle(text, foot) {
    // 空闲自言自语：不打断、只是冒一句
    if (bubble.until > now() + 1200) return
    sayLine(text, foot, 4000)
    log({ t: now(), kind: 'say', text: text })
  }
  function renderBubble() {
    var el = document.getElementById('bubble')
    if (!el) return
    var on = bubble.text && bubble.until > now()
    el.classList.toggle('on', !!on)
    if (!on) return
    var shown = bubble.typing ? bubble.text.slice(0, bubble.typed) : bubble.text
    el.innerHTML = '<div class="b-line"></div>' + (bubble.foot ? '<div class="b-foot"></div>' : '')
    var line = el.querySelector('.b-line')
    if (line) line.textContent = shown
    var foot = el.querySelector('.b-foot')
    if (foot) foot.textContent = bubble.foot
    positionBubble()
  }
  function positionBubble() {
    /* 气泡摆位：**必须落在看板下边缘以下、人物左侧的透明区**。
       上面两个位置都会踩到东西：
         · 头顶上方 —— 那里是看板正文（消息条/智能体/页脚），气泡会把面板文字盖住；
         · 人物身上 —— 遮住她自己。
       看板把 panelBottomPage（它自己的下边缘，页面 px）一起发布出来，气泡就贴在那条线
       之下、窗口左下角；宽度限制在人物左边缘以内（box.x - 10），所以两边都不碰。 */
    var el = document.getElementById('bubble')
    var api = Pet()
    if (!el || !api || !api.modelMetrics) return
    var m = api.modelMetrics()
    var box = m && m.model
    if (!box) return
    var floorY = (m.geom && typeof m.geom.panelBottomPage === 'number') ? m.geom.panelBottomPage + 6 : 200
    var maxW = Math.max(88, Math.round(box.x) - 10)
    el.style.maxWidth = maxW + 'px'
    var h = el.offsetHeight || 0
    var top = window.innerHeight - 8 - h
    if (top < floorY) top = floorY
    el.style.left = '6px'
    el.style.top = Math.round(top) + 'px'
    el.style.maxHeight = Math.max(40, window.innerHeight - 12 - floorY) + 'px'
  }

  /* ——————— 反应主循环（每帧）：把 target 淡入、叠定格、口型 ——————— */
  function tickFrame() {
    var api = Pet()
    if (!api || !api.model()) return
    var dt = 1 / 60
    var frames = FRAME_DT || dt
    tickHeld()
    // 淡入到 target
    var ids = Object.keys(target)
    for (var i = 0; i < ids.length; i++) {
      var id = ids[i]
      var t = target[id]
      var cur = current[id]
      if (cur === undefined) { cur = { id: id, value: t.value, blend: t.blend } }
      var delta = (t.value - cur.value) * Math.min(1, frames * 6)
      if (Math.abs(delta) < 0.001) delta = t.value - cur.value
      cur.value += delta
      cur.blend = t.blend
      current[id] = cur
      api.writeParam(id, cur.value)
    }
    // 定格层覆盖
    if (held && held.params) {
      var hids = Object.keys(held.params)
      for (var h = 0; h < hids.length; h++) { api.writeParam(hids[h], held.params[hids[h]].value) }
    }
    // 口型（逐字输出 / 说话中）
    var talking = !!(signals && signals.streaming && signals.streaming.active) || (override && override.act === 'listening')
    var mouth = 0
    if (talking) {
      var tt = now() / 1000
      mouth = 0.5 + 0.5 * Math.sin(tt * 9) * (0.6 + 0.4 * Math.sin(tt * 3.7))
      if (mouth < 0) mouth = 0
    }
    api.writeParam('ParamMouthOpenY', mouth)
    // 视线（久闲时自己漂）
    if (signals && typeof signals.idleMs === 'number' && signals.idleMs > 20000) {
      var t2 = now() / 1000
      api.writeParam('ParamEyeBallX', Math.sin(t2 * 0.31) * 0.5)
      api.writeParam('ParamEyeBallY', Math.sin(t2 * 0.23) * 0.3)
    } else if (base.spec && typeof base.spec.gazeY === 'number') {
      api.writeParam('ParamEyeBallY', base.spec.gazeY)
      api.writeParam('ParamEyeBallX', 0)
    }
  }

  /* ——————— 看门狗（每 2 s）：回落、不卡表情、气泡到期 ——————— */
  function tickWatchdog() {
    var t = now()
    if (override && t >= override.until) {
      log({ t: t, kind: 'fallback', from: override.act, to: base.act })
      override = null
      applyLayers()
    }
    // 一次性动作到点：停动作 + 归零（上游按 ACTIONS 的时长记账）
    if (anim && t >= anim.until) {
      var done = anim.name
      anim = null
      var apiA = Pet()
      if (apiA && apiA.stopMotions) { apiA.stopMotions() }
      applyLayers()
      log({ t: t, kind: 'act-end', name: done })
    }
    if (held && t >= heldUntil) { clearDevice('ttl') }
    if (bubble.text && t >= bubble.until) { bubble.text = ''; renderBubble() }
    // 工作轮播（上游 WORK_CYCLE 2206：9000 + rand*5000 慢切一次脸）：
    // 干活时不要钉在同一张脸上；低性能档下不跑（上游 applyPerf 关自主动作）。
    var wState = stateDoc && stateDoc.state
    var working = (wState === 'reading' || wState === 'writing' || wState === 'running' || wState === 'thinking' || wState === 'team')
    if (working && !lowPower && !override && !anim && t >= workNextAt) {
      workNextAt = t + 9000 + Math.random() * 5000
      setBase(base.act, 'work cycle')
      log({ t: t, kind: 'work-cycle', act: base.act })
    }
    // 空闲大脑（SPEC §3.4）：只在她空闲且没有 override 时跑
    var state = stateDoc && stateDoc.state
    var idle = !override && (state === 'idle' || state === 'thinking' || state === 'reading' || state === 'writing' || state === 'running' || state === 'team')
    var ms = signals && typeof signals.idleMs === 'number' ? signals.idleMs : 0
    if (state === 'idle' && !override && !lowPower && t >= idleNextAt) {
      idleNextAt = t + 3500 + Math.random() * 4000
      var roll = Math.random()
      if (ms > 180000) {
        setBase('sleepy', 'idle 180s')
        if (lastIdleAction !== 'sleep') { sayIdle(pickLine('sleep')); lastIdleAction = 'sleep' }
      } else if (ms > 99000 && roll < 0.35) {
        sayIdle(pickLine('sleep')); lastIdleAction = 'yawn'
      } else if (roll < 0.3) {
        // 换表情几秒：只换「不改眼型」的那几个（上游 idleExpress 4123 的约束）
        var f = pick(['tongueOut', 'naughty', 'question', 'blush', 'excited'])
        override = { act: 'idle', face: f, spec: ACT.idle, until: t + 3200 }
        applyLayers(); log({ t: t, kind: 'idle-face', face: f }); lastIdleAction = 'face'
      } else if (roll < 0.6) {
        sayIdle(pickLine('idle')); lastIdleAction = 'mutter'
      } else if (roll < 0.75) {
        sayIdle(pickLine('hungry')); lastIdleAction = 'hungry'
      } else {
        lastIdleAction = 'none'
      }
    } else if (idle && !lastIdleAction) {
      lastIdleAction = 'none'
    }
  }

  /* ——————— 信号 → 反应（SPEC §3.2/§3.3/§4）——————— */
  function applySignals(sig) {
    if (!sig || typeof sig !== 'object') return
    signals = sig
    lastSignalsAt = now()
    var t = now()

    // 用户说话（2.6 s 星星眼 + 原话）
    if (sig.lastUserAt && sig.lastUserAt > signalSeen.user) {
      signalSeen.user = sig.lastUserAt
      override = { act: 'listening', face: 'starry', spec: ACT.listening, until: t + 2600 }
      sayLine(sig.lastUserText ? String(sig.lastUserText).slice(0, 60) : pickLine('done'), null, 3500)
      applyLayers()
      log({ t: t, kind: 'listen', at: sig.lastUserAt })
    }

    // 工具调用 / 结果
    var tool = sig.tool
    var lastError = sig.lastError
    if (lastError && lastError.at && lastError.at !== signalSeen.errorAt) {
      // 报错：黑一下脸 1.6 s，`props:[]` **+ exclusive**（连本子笔和用户装饰都放下）、
      // 不叠任何别的东西（SPEC §3.3；UPSTREAM-GAP §5.4-2）。
      signalSeen.errorAt = lastError.at
      override = { act: 'error', face: 'gloomy', spec: ACT.error, until: t + 1600, exclusive: true }
      stopActing('tool error')
      sayLine('（脸黑了）这个工具报错了：' + (lastError.name || '') + (lastError.error ? ' · ' + lastError.error : ''), null, 2600)
      applyLayers()
      log({ t: t, kind: 'tool-error', name: lastError.name || null, error: lastError.error || null, exclusive: true })
    }
    if (tool && tool.at && tool.at !== signalSeen.tool) {
      signalSeen.tool = tool.at
      var act = TOOL_MAP[tool.name] || 'reading'
      // 新目标（create_goal）：戴个心跳（UPSTREAM-GAP §5.3）
      if (tool.name === 'create_goal' && tool.phase === 'call') { act('heartbeat', 'create_goal') }
      // 每次工具调用都播一段完整动作（call 与 result 都试，内部 900 ms 防抖）
      var toolAct = TOOL_MAP[tool.name] || 'reading'
      playVisibleMotion(TOOL_MOTION[toolAct], 'tool=' + tool.name + '/' + tool.phase)

      if (tool.phase === 'result') {
        // 成功的工具**不是**庆祝（SPEC §3.3），但也不能直接把脸抹成「想事情」：
        // 引擎按 2 s 折叠会话日志，`read`/`edit` 这类快工具被看到时往往已经是
        // result 了，只在 call 阶段挂脸的话眼镜/笔/手机几乎永远不出现。
        // 所以这里给「该活动的脸」一段短 TTL（2.5 s），随后由 state.json 的
        // base（想事情/跑命令…）接管——脸的粒度比标签细，是有意为之。
        if (held && act !== 'web' && act !== 'fetch') { clearDevice('tool-result') }
        var spec2 = ACT[act] || ACT.neutral
        override = { act: act, face: pick(spec2.faces, spec2.weights), spec: spec2, until: t + 2500 }
        applyLayers()
        log({ t: t, kind: 'tool-result-face', name: tool.name, act: act, ok: tool.ok })
        return
      }
      // call：按工具换脸换动作 + 台词 + 参数摘要
      var spec = ACT[act] || ACT.neutral
      var face = pick(spec.faces, spec.weights)
      override = null
      base = { act: act, face: face, spec: spec }
      applyLayers()
      var line = pickLine(spec.say || act) || pickLine('reading')
      sayLine(line, tool.summary ? String(tool.summary).slice(0, 46) + (tool.name ? ' · ' + tool.name : '') : (tool.name || ''), 3600)
      log({ t: t, kind: 'tool-call', name: tool.name, act: act, face: face, summary: tool.summary || null })
    }

    // 回合结束（收工 3 s，统计行）
    var turn = sig.turn
    if (turn && turn.at && turn.at !== signalSeen.turn && turn.phase === 'end') {
      signalSeen.turn = turn.at
      var kind = turn.reason || null
      if (kind === 'error') {
        override = { act: 'error', face: pick(['sweat', 'sad']), spec: ACT.error, until: t + 3200, exclusive: true }
        sayLine(pickFresh('fail', SAY.fail), null, 4200)
      } else if (kind === 'aborted') {
        override = { act: 'error', face: 'sad', spec: ACT.error, until: t + 2800, exclusive: true }
        sayLine(pickFresh('aborted', SAY.aborted), null, 3600)
      } else if (kind === 'completed' || kind === null || kind === undefined) {
        // 收工：伸懒腰比耶 + 随机装饰 + 纯 CSS 蹦一下 + 统计行（上游 'turn-end' 3961-4019）
        override = { act: 'celebrating', face: 'excited', spec: ACT.celebrating, until: t + 3000 }
        var deco = pick(['stickerCat', 'stickerRabbit', 'sparkle', 'heartbeat'])
        if (faceDefs[deco]) { setTimeout(function () { if (override && override.act === 'celebrating') { override.face = deco; applyLayers() } }, 900) }
        qBounce()
        if (ACTIONS.doubleV) { act('doubleV', 'turn completed') }
        var stat = (turn.ms ? (Math.round(turn.ms / 100) / 10) + 's' : '') + (turn.tokens ? ' · ' + turn.tokens + ' tokens' : '')
        sayLine(pickFresh('done', SAY.done), stat || null, 4200)
      } else {
        override = { act: 'idle', face: 'naughty', spec: ACT.idle, until: t + 2600 }
      }
      applyLayers()
      log({ t: t, kind: 'turn-end', reason: kind, ms: turn.ms || null, tokens: turn.tokens || null })
    }
  }

  /* ——————— 状态变化 → base（SPEC §4.1：base 层一直在）——————— */
  function applyStateDoc(doc) {
    var lastAppliedState = null
    if (!doc || typeof doc !== 'object') return
    stateDoc = doc
    lastStateApplyAt = now()
    if (doc.pose && KNOWN_POSES.indexOf(String(doc.pose)) < 0) {
      diag('unknownPose', doc.pose, 'state=' + String(doc.state || ''))
    }
    if (doc.state && doc.state !== lastAppliedState) {
      lastAppliedState = doc.state
      playVisibleMotion(STATE_MOTION[doc.state], 'state=' + doc.state)
    }
    var act = actForState(String(doc.state || ''), String(doc.pose || ''))
    if (doc.state === 'error' || doc.state === 'celebrating' || doc.state === 'listening') {
      // 这三档由信号层负责 TTL，这里只保证 base 不被它们污染
      if (!override || now() >= override.until) { setBase('thinking', 'ttl state ' + doc.state) }
    } else if (!override || now() >= override.until) {
      setBase(act, 'state ' + doc.state)
    }
    if (doc.detail && !bubble.text && doc.state !== 'idle') { /* detail 行已经画了，不再重复气泡 */ }
  }

  /* ——————— 初始化 ——————— */
  var FORCED = false

  /**
   * 展示拍图用的强制模式：关掉 signals.json 轮询，改用注入的信号（或只按注入的状态
   * 摆 base 脸）。传 null 恢复生产行为。入口是 pet-app.js 的 pet-force 消息。
   */
  function setForced(signals, state, clear) {
    FORCED = !!signals || !!state
    if (!FORCED) { return }
    override = null
    if (clear) {
      // 拍图之间把上一状态的气泡清掉，否则串味（showcase 的每张图只该有它自己的台词）
      bubble.text = ''
      bubble.foot = ''
      bubble.typing = false
      bubble.until = 0
      renderBubble()
    }
    if (state) { setBase(actForState(String(state), ''), 'forced ' + state) }
    if (signals) { applySignals(signals) }
  }

  function pollSignals() {
    if (FORCED) return
    fetch(SIGNALS_URL + '?t=' + now(), { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null })
      .then(function (j) { if (j) applySignals(j) })
      .catch(function () { /* 没有 signals.json 时只跑状态驱动 */ })
  }

  function boot() {
    var api = Pet()
    if (!api) { setTimeout(boot, 200); return }
    if (!api.model()) { setTimeout(boot, 200); return }
    loadUserProps()
    loadFaceDefs()
    api.onFrame(tickFrame)
    setInterval(tickWatchdog, 2000)
    // the typing reveal runs on its own fast clock (16 chars/s), not on the 2 s watchdog
    setInterval(function () {
      if (!bubble.text || !bubble.typing) return
      bubble.typed += 1
      if (bubble.typed >= bubble.text.length) {
        bubble.typing = false
        bubble.until = Math.max(bubble.until, now() + 2600)
      }
      renderBubble()
    }, 60)
    setInterval(function () { if (now() - lastSignalsAt > 6000) { /* 信号停更：base 仍在 */ } }, 5000)
    pollSignals()
    setInterval(pollSignals, 1500)
    var forced = q.get('state')
    if (forced) applyStateDoc({ state: forced, pose: null })
    log({ t: now(), kind: 'boot' })
  }

  window.PetReactions = {
    applyStateDoc: applyStateDoc,
    applySignals: applySignals,
    diagnostics: diagnostics,
    visibleMotions: function () { return Object.keys(VISIBLE_MOTIONS) },
    stateMotion: function () { return STATE_MOTION },
    toolMotion: function () { return TOOL_MOTION },
    lastMotion: function () { return { at: lastMotionAt, name: lastMotionName } },
    playVisibleMotion: playVisibleMotion,
    setForced: setForced,
    /** 诊断：最近的反应日志（宿主可读取） */
    trace: function () { return lastLog.slice() },
    snapshot: function () {
      return {
        base: { act: base.act, face: base.face },
        override: override ? { act: override.act, face: override.face, leftMs: Math.max(0, override.until - now()), exclusive: !!override.exclusive } : null,
        anim: anim ? { name: anim.name, face: anim.face, leftMs: Math.max(0, anim.until - now()) } : null,
        held: !!held,
        bubble: bubble.text ? { text: bubble.text, foot: bubble.foot, typed: bubble.typed } : null,
        faceDefs: Object.keys(faceDefs).length,
        params: Object.keys(target).length,
        userProps: propsOn(),
        lowPower: lowPower,
        tables: { decor: Object.keys(DECOR).length, scenes: Object.keys(SCENES).length, actions: Object.keys(ACTIONS).length },
      }
    },
    say: function (text) { sayLine(text, null, 4000) },
    // —— 上游能力的开关入口（没有鼠标，所以由事件/宿主通道驱动；见 UPSTREAM-GAP §5.3）——
    act: act,
    stopActing: stopActing,
    setProp: setProp,
    setProps: setProps,
    props: propsOn,
    setLowPower: setLowPower,
    qBounce: qBounce,
    actionNames: function () { return ACTION_ORDER.slice() },
    tables: function () {
      return {
        decor: Object.keys(DECOR).map(function (k) { return { key: k, slot: DECOR[k].slot, expr: DECOR[k].expr } }),
        scenes: Object.keys(SCENES).map(function (k) { return { key: k, slot: SCENES[k].slot, expr: SCENES[k].expr || null, motion: SCENES[k].motion || null, needs: SCENES[k].needs || null } }),
        actions: ACTION_ORDER.map(function (k) { return { key: k, ms: ACTIONS[k].ms, expr: ACTIONS[k].expr || null, motion: ACTIONS[k].motion || null, needs: ACTIONS[k].needs || null } }),
      }
    },
  }

  setTimeout(boot, 300)
})()
