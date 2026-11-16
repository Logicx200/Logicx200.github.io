"""task-15 patch A+D for reactions.js (robust, regex anchors)."""
import re
from pathlib import Path

p = Path(r'F:\dsh-usage-widget\pet\renderer\reactions.js')
t = p.read_text(encoding='utf-8')
n0 = len(t)
applied = []


def sub_once(pattern, repl, label, count=1):
    global t
    new, n = re.subn(pattern, repl, t, count=count)
    if n != count:
        raise SystemExit(f'anchor failed: {label} (matched {n})')
    t = new
    applied.append(label)


DIAG = r'''
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
'''

MOT = r'''
    /* ——————— 可见动作（task-15 A）———————
       模型真正声明的 motion 组：idle / aidale / selfie / selfieQuick / ketchup / openLid /
       bubble / splash。aidale、bubble 是原作者停用的（FORBIDDEN_MOTIONS），idle 是待机
       循环——都不许用。剩下 4 个一次性 clip（1.5~2.5 s）用来表达"她在做事"。 */
    var VISIBLE_MOTIONS = { selfie: 3600, selfieQuick: 2000, openLid: 2400, splash: 2200 }
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
        diag((name === 'idle' || name === 'aidale' || name === 'bubble') ? 'blockedMotion' : 'missingMotion', name, why || null)
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
'''

# 1. diagnostics before the ACT table comment
sub_once(r'(\n  /\*\* 活动 → \{ face 池)', DIAG + r'\1', 'diagnostics')
# 2. motion palette before userProps
sub_once(r'(\n\s*var userProps = \{\})', MOT + r'\1', 'motion palette')
# 3. a "last applied state" variable inside applyStateDoc, and the one-shot motion on change
sub_once(r'(\n(\s*)function applyStateDoc\(doc\) \{\n)', r'\1\2  var lastAppliedState = null\n', 'state var')
sub_once(r'(\n(\s*)lastStateApplyAt = now\(\))',
         r'''\1
\2if (doc.state && doc.state !== lastAppliedState) {
\2  lastAppliedState = doc.state
\2  playVisibleMotion(STATE_MOTION[doc.state], 'state=' + doc.state)
\2}''', 'state motion')
# 4. every tool call plays a motion
sub_once(r"(\n(\s*)if \(tool\.phase === 'result'\) \{\n\s*// 成功的工具)",
         r'''
\2// 每次工具调用都播一段完整动作（call 与 result 都试，内部 900 ms 防抖）
\2var toolAct = TOOL_MAP[tool.name] || 'reading'
\2playVisibleMotion(TOOL_MOTION[toolAct], 'tool=' + tool.name + '/' + tool.phase)
\1''', 'tool motion')
# 5. unknown prop name -> diag
sub_once(r'(\n\s*function propSpec\(key\) \{ return DECOR\[key\] \|\| SCENES\[key\] \|\| null \})',
         r'''
    function propSpec(key) {
      var s = DECOR[key] || SCENES[key] || null
      if (!s) { diag('unknownProp', key, 'not in DECOR or SCENES') }
      return s
    }''', 'propSpec diag')
# 6. expose the new API
sub_once(r'(\n\s*applySignals: applySignals,)', r'''\1
    diagnostics: diagnostics,
    visibleMotions: function () { return Object.keys(VISIBLE_MOTIONS) },
    stateMotion: function () { return STATE_MOTION },
    toolMotion: function () { return TOOL_MOTION },
    lastMotion: function () { return { at: lastMotionAt, name: lastMotionName } },
    playVisibleMotion: playVisibleMotion,''', 'expose')

p.write_text(t, encoding='utf-8')
print('applied:', ', '.join(applied))
print('bytes', n0, '->', len(t))
