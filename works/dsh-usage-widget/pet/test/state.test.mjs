/**
 * Checks for the pet's state model.
 *
 * Run with the bundled Node:
 *   node pet\test\state.test.mjs
 *
 * Plain assertions, no framework: prints one line per case, then a compact
 * state -> label -> colour -> pose -> trigger table, then exits non-zero if any
 * check failed. Every case is deterministic — `now` is always supplied, never
 * read from the clock.
 *
 * @module dsh-usage-widget/pet/test/state
 */

import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  AGENT_ACTIVE_MS,
  DETAIL_MAX_CHARS,
  EVENT_RECENT_MS,
  PANEL_BACKGROUND,
  PET_STATES,
  POSE_VALUES,
  RESERVED_COLORS,
  SNAPSHOT_STALE_MS,
  STATE_PRIORITY,
  STATE_VALUES,
  TOOL_ACTIVE_MS,
  ERROR_TTL_MS,
  CELEBRATE_TTL_MS,
  LISTEN_TTL_MS,
  computeState,
  formatProgress,
  normalizeObservation,
  pillFor,
  priorityOf,
  selectState,
} from '../state.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const STATE_MODULE = resolve(HERE, '..', 'state.mjs')

/** A fixed observation time so every expected age below is exact. */
const NOW = 1_790_700_000_000

/** One friendly job row, bridge-shaped. */
const JOB = {
  id: 'call_00_abc',
  session: 'sess-1',
  program: 'pwsh',
  command: 'node sim.mjs --steps 500',
  startedAt: NOW - 65_000,
  elapsedMs: 65_000,
  progress: { percent: 45.2, etaMs: 37_000, source: 'bridge' },
  progressNote: null,
}

/** One friendly running agent row. */
const AGENT = {
  id: 'sess-1',
  label: 'Apply widget UI feedback',
  state: 'running',
  model: 'deepseek-flash',
  turn: 1,
  startedAt: NOW - 412_000,
  elapsedMs: 412_000,
  sinceLastWriteMs: 1_200,
}

/**
 * A snapshot with sane defaults.
 * @param {any} [overrides] - fields to replace.
 * @returns {any} the snapshot.
 */
function snapshot(overrides = {}) {
  return {
    type: 'snapshot',
    at: NOW,
    peakNow: false,
    rate: 7.1,
    agents: [],
    jobs: [],
    jobsSource: 'bridge',
    ...overrides,
  }
}

let passed = 0
/** @type {string[]} */
const failures = []
/** @type {{ case: string, state: string, label: string, color: string, pose: string, detail: string }[]} */
const table = []

/**
 * Assert one condition, recording a named failure when it does not hold.
 * @param {boolean} condition - the claim.
 * @param {string} name - the check's name.
 * @param {string} [extra] - context printed on failure.
 * @returns {boolean} the condition.
 */
function ok(condition, name, extra = '') {
  if (condition) {
    passed += 1
    return true
  }
  failures.push(extra.length > 0 ? `${name} — ${extra}` : name)
  return false
}

/**
 * Assert deep equality for the fields worth comparing.
 * @param {any} actual - observed.
 * @param {any} expected - required.
 * @param {string} name - the check's name.
 * @returns {boolean} whether they matched.
 */
function eq(actual, expected, name) {
  const a = JSON.stringify(actual)
  const b = JSON.stringify(expected)
  return ok(a === b, name, `expected ${b}, got ${a}`)
}

/**
 * Run one named case and record it for the summary table.
 * @param {string} caseName - what the observation represents.
 * @param {any} observation - the input.
 * @param {string} expectedState - the state the ladder must pick.
 * @returns {ReturnType<typeof computeState>} the result, for further assertions.
 */
function check(caseName, observation, expectedState) {
  const result = computeState(observation)
  ok(
    result.state === expectedState,
    `case "${caseName}" -> ${expectedState}`,
    `got ${result.state} (${result.reason})`,
  )
  table.push({
    case: caseName,
    state: result.state,
    label: result.label,
    color: result.color,
    pose: result.pose,
    detail: result.detail,
  })
  return result
}

// ---------------------------------------------------------------------------
// 1. Every state is reachable, through the documented trigger.
// ---------------------------------------------------------------------------

const offline = check('DSH 未运行', { now: NOW, dshRunning: false, snapshot: snapshot() }, 'offline')
eq(offline.detail, 'DSH 未在运行', 'offline detail')
eq(offline.pose, 'offline', 'offline pose')

const offlineNoFrame = check('DSH 未运行且无快照', { now: NOW, dshRunning: false }, 'offline')
eq(offlineNoFrame.detail, 'DSH 未在运行 · 无快照', 'offline/no-frame detail')
ok(offlineNoFrame.source === 'none', 'offline/no-frame source === none')

const stale = check(
  '快照超过 SNAPSHOT_STALE_MS',
  { now: NOW, dshRunning: true, lastEventAt: NOW - 1_000, snapshot: snapshot({ at: NOW - SNAPSHOT_STALE_MS - 1, agents: [AGENT], jobs: [JOB] }) },
  'stale',
)
ok(stale.detail.includes(String(Math.round((SNAPSHOT_STALE_MS + 1) / 1000))), 'stale detail states the age', stale.detail)
eq(stale.pose, 'sleepy', 'stale pose')

const staleNoSnapshot = check('DSH 在跑但从未收到快照', { now: NOW, dshRunning: true, snapshot: null }, 'stale')
eq(staleNoSnapshot.detail, '未收到引擎快照', 'stale/no-snapshot detail')
ok(staleNoSnapshot.source === 'none', 'stale/no-snapshot source === none')

const team = check(
  '两个 running 的 agent',
  { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [AGENT, { ...AGENT, id: 'sess-2', label: '核对配色', sinceLastWriteMs: 400 }] }) },
  'team',
)
eq(team.pose, 'team', 'team pose')
ok(team.detail.includes('2 个智能体'), 'team detail counts agents', team.detail)

const jobRun = check('一个 jobs 条目', { now: NOW, dshRunning: true, snapshot: snapshot({ jobs: [JOB] }) }, 'running')
eq(jobRun.pose, 'sleeves', 'running pose')
ok(jobRun.detail.includes('pwsh'), 'running detail names the program', jobRun.detail)
ok(jobRun.detail.includes('45.2% 剩余 00:37'), 'running detail carries percent + ETA', jobRun.detail)

const workingEvent = check(
  '最近的 event（10s 前）',
  { now: NOW, dshRunning: true, lastEventAt: NOW - 10_000, snapshot: snapshot() },
  'thinking',
)
eq(workingEvent.pose, 'thinking', 'thinking pose')

const workingAgent = check(
  '单个 running 且刚写过文件的 agent',
  { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [AGENT] }) },
  'thinking',
)
ok(!workingAgent.detail.includes('智能体'), 'single-agent thinking detail stays short', workingAgent.detail)

// peakNow deliberately has no state of its own since task-7 (peak pricing is the
// panel footer's story): it falls through to idle.
const peak = check('peakNow 且无其他信号', { now: NOW, dshRunning: true, snapshot: snapshot({ peakNow: true }) }, 'idle')
eq(peak.pose, 'idle', 'peakNow pose')
eq(peak.detail, '', 'peakNow detail is empty')

const idle = check('DSH 在跑，无信号', { now: NOW, dshRunning: true, snapshot: snapshot() }, 'idle')
eq(idle.detail, '', 'idle detail is empty')
eq(idle.pose, 'idle', 'idle pose')

// ---------------------------------------------------------------------------
// 1b. task-7: the tool-driven and one-shot categories (REACTIONS-SPEC §2-§4).
// ---------------------------------------------------------------------------

const tool = (extra) => ({ now: NOW, dshRunning: true, snapshot: snapshot(), signals: { tool: extra } })
// A failed result is published twice: as the tool's own result and as `lastError`
// (kept apart so a call that starts right after cannot hide the failure).
const toolFail = (name, error, at) => ({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot(),
  signals: {
    tool: { name, phase: 'result', ok: false, error, at },
    lastError: { name, error, at },
  },
})

const reading = check(
  '工具调用：read（在飞，还没有结果）',
  tool({ name: 'read', phase: 'call', at: NOW - 2_000, summary: 'src/foo.ts' }),
  'reading',
)
eq(reading.pose, 'reading', 'reading pose')
eq(reading.color, '#58A6FF', 'reading colour')
ok(reading.detail.includes('read') && reading.detail.includes('src/foo.ts'), 'reading detail names tool + args', reading.detail)

check('工具调用：grep 也是查资料', tool({ name: 'grep', phase: 'call', at: NOW - 1_000 }), 'reading')
check('工具调用：未匹配的工具兜底成查资料', tool({ name: 'some_new_tool', phase: 'call', at: NOW - 1_000 }), 'reading')

const writing = check('工具调用：edit', tool({ name: 'edit', phase: 'call', at: NOW - 1_000 }), 'writing')
eq(writing.pose, 'scribble', 'writing pose')
check('工具调用：write', tool({ name: 'write', phase: 'call', at: NOW - 1_000 }), 'writing')

const running = check('工具调用：pwsh', tool({ name: 'pwsh', phase: 'call', at: NOW - 1_000 }), 'running')
eq(running.pose, 'sleeves', 'running pose')
check('工具调用：web_search 上网也算查资料', tool({ name: 'web_search', phase: 'call', at: NOW - 1_000 }), 'reading')
check('工具调用：present 交付', tool({ name: 'present', phase: 'call', at: NOW - 1_000 }), 'celebrating')
check('工具调用：subagent 分身', tool({ name: 'subagent', phase: 'call', at: NOW - 1_000 }), 'team')
check('工具调用：glob 找文件', tool({ name: 'glob', phase: 'call', at: NOW - 1_000 }), 'thinking')

// a call that never returns a result stops naming the activity after 60 s
check('工具调用超过 TOOL_ACTIVE_MS 就不再代表活动', tool({ name: 'read', phase: 'call', at: NOW - TOOL_ACTIVE_MS - 1 }), 'idle')
// a successful result is NOT a celebration: she goes back to the work state
// (a live turn keeps `lastEventAt` fresh; here that is what says "still working")
const okResult = check(
  '工具成功的结果 → 想事情',
  { ...tool({ name: 'read', phase: 'result', ok: true, at: NOW - 500 }), lastEventAt: NOW - 500 },
  'thinking',
)
eq(okResult.pose, 'thinking', 'success result pose')

// a failed result is the 1.6 s black face
const failed = check('工具报错 → 出错了', toolFail('edit', 'FsError/FS_STALE_VERSION', NOW - 500), 'error')
eq(failed.pose, 'gloomy', 'error pose')
eq(failed.color, '#F85149', 'error colour')
ok(failed.detail.includes('edit') && failed.detail.includes('FsError'), 'error detail names tool + error', failed.detail)
ok(
  computeState(toolFail('edit', 'x', NOW - ERROR_TTL_MS - 1)).state !== 'error',
  'a tool error older than ERROR_TTL_MS falls back (never stuck)',
)
ok(
  computeState(toolFail('edit', 'x', NOW - ERROR_TTL_MS + 1)).state === 'error',
  'a tool error exactly inside ERROR_TTL_MS still counts',
)

// turn end: completed -> celebrating (3 s), error -> error, aborted -> no state change
const turn = (extra) => ({ now: NOW, dshRunning: true, snapshot: snapshot(), signals: { turn: extra } })
const done = check(
  '整轮完成 → 收工啦',
  turn({ phase: 'end', at: NOW - 1_000, reason: 'completed', ms: 12_300, tokens: 41_380 }),
  'celebrating',
)
eq(done.pose, 'happy', 'celebrating pose')
eq(done.detail, '12.3s · 41380 tokens', 'celebrating detail carries the stats line')
check(
  '整轮 error → 出错了',
  turn({ phase: 'end', at: NOW - 1_000, reason: 'error' }),
  'error',
)
ok(
  computeState(turn({ phase: 'end', at: NOW - 1_000, reason: 'aborted' })).state === 'idle',
  'aborted 不改状态（只由页面黑一下脸/哭一下，随后回落）',
)
ok(
  computeState(turn({ phase: 'end', at: NOW - CELEBRATE_TTL_MS - 1, reason: 'completed' })).state === 'idle',
  'celebration expires (never stuck)',
)

// the user speaking outranks the work: listening for 2.6 s
const listening = check(
  '主人刚说话 → 听主人说',
  { now: NOW, dshRunning: true, snapshot: snapshot({ jobs: [JOB] }), signals: { lastUserAt: NOW - 1_000 } },
  'listening',
)
eq(listening.pose, 'starry', 'listening pose')
ok(
  computeState({ now: NOW, dshRunning: true, snapshot: snapshot({ jobs: [JOB] }), signals: { lastUserAt: NOW - LISTEN_TTL_MS - 1 } }).state === 'running',
  'listening expires back to the tool/job state (never stuck)',
)

// error outranks celebrating/team; celebrating outranks team
check(
  '工具报错 且 整轮完成 同时成立 → 报错优先',
  { now: NOW, dshRunning: true, snapshot: snapshot(), signals: { tool: { name: 'edit', phase: 'result', ok: false, error: 'x', at: NOW - 500 }, lastError: { name: 'edit', error: 'x', at: NOW - 500 }, turn: { phase: 'end', at: NOW - 500, reason: 'completed' } } },
  'error',
 )
check(
  '两个 agent 且工具在飞 → 团队协作优先于工具类别（REACTIONS-SPEC §2 的优先级表）',
  { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [AGENT, { ...AGENT, id: 's2', label: '另一个' }] }), signals: { tool: { name: 'read', phase: 'call', at: NOW - 1_000 } } },
  'team',
 )
check(
  'assistant 步骤打开（正在输出）且无工具 → 想事情',
  { now: NOW, dshRunning: true, snapshot: snapshot(), signals: { streaming: { active: true, at: NOW - 500 } } },
  'thinking',
 )

// The rows above plus the tool/one-shot cases below must be exactly the contract's
// set, no more, no less.
eq(
  [...new Set(table.map((row) => row.state))].sort(),
  STATE_VALUES.slice().sort(),
  'all eleven states reachable and none extra',
)

// ---------------------------------------------------------------------------
// 2. Priority conflicts — exactly one winner, never a combination.
// ---------------------------------------------------------------------------

check(
  'agent running 且同时有 job',
  { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [AGENT, { ...AGENT, id: 's2', label: '另一个', sinceLastWriteMs: 100 }], jobs: [JOB] }) },
  'team',
)

check(
  '单个 agent running 且同时有 job',
  { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [AGENT], jobs: [JOB] }) },
  'running',
)

check(
  'job 存在 且 event 刚发生',
  { now: NOW, dshRunning: true, lastEventAt: NOW - 1_000, snapshot: snapshot({ jobs: [JOB] }) },
  'running',
)

check(
  'peakNow 且 job 存在',
  { now: NOW, dshRunning: true, snapshot: snapshot({ jobs: [JOB], peakNow: true }) },
  'running',
)

check(
  'peakNow 且 event 刚发生',
  { now: NOW, dshRunning: true, lastEventAt: NOW - 1_000, snapshot: snapshot({ peakNow: true }) },
  'thinking',
)

check(
  'agent running 且 peakNow',
  { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [AGENT, { ...AGENT, id: 's2', label: '另一个' }], peakNow: true }) },
  'team',
)

check(
  'DSH 未运行 但快照里一切都在跑',
  { now: NOW, dshRunning: false, lastEventAt: NOW - 100, snapshot: snapshot({ agents: [AGENT, { ...AGENT, id: 's2' }], jobs: [JOB] }) },
  'offline',
)

check(
  '快照过期 但里面有 running agent 和 job',
  { now: NOW, dshRunning: true, lastEventAt: NOW - 100, snapshot: snapshot({ at: NOW - 10 * SNAPSHOT_STALE_MS, agents: [AGENT], jobs: [JOB] }) },
  'stale',
)

const conflict = computeState({
  now: NOW,
  dshRunning: true,
  lastEventAt: NOW - 1_000,
  snapshot: snapshot({ agents: [AGENT, { ...AGENT, id: 's2' }], jobs: [JOB], peakNow: true }),
})
ok(conflict.state === 'team', 'four-way conflict resolves to team', conflict.state)
ok(STATE_PRIORITY.indexOf(conflict.state) === 5, 'team is index 5 in STATE_PRIORITY (below the three one-shot tiers)')

// The ladder never returns two states: pick exactly one value.
ok(STATE_VALUES.includes(conflict.state), 'winner is a single enum member')
ok(priorityOf('offline') === 0 && priorityOf('idle') === STATE_PRIORITY.length - 1, 'priorityOf endpoints')
ok(priorityOf('nonsense') === -1, 'priorityOf rejects an unknown state')

// ---------------------------------------------------------------------------
// 3. Constants and their boundaries.
// ---------------------------------------------------------------------------

const atRecentEdge = computeState({
  now: NOW,
  dshRunning: true,
  lastEventAt: NOW - EVENT_RECENT_MS,
  snapshot: snapshot(),
})
ok(atRecentEdge.state === 'thinking', 'event exactly EVENT_RECENT_MS old still counts (inclusive)', atRecentEdge.state)

const pastRecent = computeState({
  now: NOW,
  dshRunning: true,
  lastEventAt: NOW - EVENT_RECENT_MS - 1,
  snapshot: snapshot(),
})
ok(pastRecent.state === 'idle', 'event one ms past EVENT_RECENT_MS is idle', pastRecent.state)

const atStaleEdge = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ at: NOW - SNAPSHOT_STALE_MS }),
})
ok(atStaleEdge.state === 'idle', 'snapshot exactly SNAPSHOT_STALE_MS old is still trusted', atStaleEdge.state)

const pastStaleEdge = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ at: NOW - SNAPSHOT_STALE_MS - 1, agents: [AGENT] }),
})
ok(pastStaleEdge.state === 'stale', 'one ms past SNAPSHOT_STALE_MS is stale', pastStaleEdge.state)

const atAgentEdge = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ agents: [{ ...AGENT, sinceLastWriteMs: AGENT_ACTIVE_MS }] }),
})
ok(atAgentEdge.state === 'thinking', 'write exactly AGENT_ACTIVE_MS old still counts', atAgentEdge.state)

const dormantAgent = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ agents: [{ ...AGENT, sinceLastWriteMs: AGENT_ACTIVE_MS + 1 }] }),
})
ok(dormantAgent.state === 'idle', 'a wedged running agent reads as idle, not working', dormantAgent.state)

const missingAge = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ agents: [{ id: 'sess-1', label: '旧引擎的 agent', state: 'running' }] }),
})
ok(missingAge.state === 'thinking', 'missing sinceLastWriteMs is assumed active', missingAge.state)

// A future timestamp is clock skew, not proof of future work.
const futureEvent = computeState({
  now: NOW,
  dshRunning: true,
  lastEventAt: NOW + 60_000,
  snapshot: snapshot(),
})
ok(futureEvent.state === 'idle', 'a future lastEventAt is treated as old, not working', futureEvent.state)

const futureSnapshot = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ at: NOW + 60_000 }),
})
ok(futureSnapshot.state === 'idle', 'a future snapshot.at does not read as activity', futureSnapshot.state)

// ---------------------------------------------------------------------------
// 4. Missing / empty / mistyped fields — the older-engine and edge cases.
// ---------------------------------------------------------------------------

check('空 agents 与 jobs 数组', { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [], jobs: [] }) }, 'idle')

check('agents 全为 idle', { now: NOW, dshRunning: true, snapshot: snapshot({ agents: [{ ...AGENT, state: 'idle', elapsedMs: 120_000 }] }) }, 'idle')

check('agents 缺失整个键', { now: NOW, dshRunning: true, snapshot: { type: 'snapshot', at: NOW, peakNow: false } }, 'idle')

check('jobs 缺失整个键', { now: NOW, dshRunning: true, snapshot: { type: 'snapshot', at: NOW, peakNow: false, agents: [] } }, 'idle')

check('agents 不是数组', { now: NOW, dshRunning: true, snapshot: snapshot({ agents: 'nope', jobs: null }) }, 'idle')

check('jobs 里全是 null', { now: NOW, dshRunning: true, snapshot: snapshot({ jobs: [null, undefined, 7, 'x'] }) }, 'idle')

check('snapshot 完全缺失', { now: NOW, dshRunning: true }, 'stale')

check('snapshot 不是对象', { now: NOW, dshRunning: true, snapshot: 'boom' }, 'stale')

check('snapshot.at 不是数字', { now: NOW, dshRunning: true, snapshot: { type: 'snapshot', agents: [AGENT] } }, 'stale')

check('stopping 的 job 仍算后台任务', {
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ jobs: [{ ...JOB, status: 'stopping' }] }),
}, 'running')

const stoppingLong = computeState({
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ jobs: [{ ...JOB, status: 'stopping', startedAt: NOW - 60_000 }] }),
})
ok(stoppingLong.detail.includes('stopping'), 'a long-stopping job is called out in detail', stoppingLong.detail)

check('jobsSource: logs 会在 detail 里标注', {
  now: NOW,
  dshRunning: true,
  snapshot: snapshot({ jobs: [JOB], jobsSource: 'logs' }),
}, 'running')

// Empty observation: no snapshot, no process knowledge.
const empty = computeState({})
ok(empty.state === 'stale', 'empty observation is stale, never working', empty.state)
ok(empty.source === 'none', 'empty observation reports source none')

const noArg = computeState()
ok(noArg.state === 'stale', 'no argument at all still returns a state', noArg.state)

// dshRunning unknown + fresh snapshot: infer, never guess offline.
const inferred = computeState({ now: NOW, snapshot: snapshot({ jobs: [JOB] }) })
ok(inferred.state === 'running', 'unknown dshRunning + fresh snapshot is still believed', inferred.state)

// dshRunning unknown + fresh-but-empty snapshot: idle, not stale.
const inferredIdle = computeState({ now: NOW, snapshot: snapshot() })
ok(inferredIdle.state === 'idle', 'unknown dshRunning + fresh empty snapshot is idle', inferredIdle.state)

// Agent with a blank label falls back to a placeholder.
const blankLabel = computeState({ now: NOW, dshRunning: true, snapshot: snapshot({ agents: [{ ...AGENT, label: '   ' }] }) })
ok(blankLabel.state === 'thinking', 'blank agent label still works')

// peakNow truthiness: only literal true counts.
const peakString = computeState({ now: NOW, dshRunning: true, snapshot: snapshot({ peakNow: 'yes' }) })
ok(peakString.state === 'idle', 'non-boolean peakNow is not peak (peak is not a state)', peakString.state)

// ---------------------------------------------------------------------------
// 5. Presentation contract: distinct labels, distinct colours, safe colours.
// ---------------------------------------------------------------------------

const labels = STATE_VALUES.map((state) => PET_STATES[state].label)
const colors = STATE_VALUES.map((state) => PET_STATES[state].color)
const poses = STATE_VALUES.map((state) => PET_STATES[state].pose)

eq([...new Set(labels)].length, labels.length, 'every state has a distinct label')
eq([...new Set(colors)].length, colors.length, 'every state has a distinct colour')
ok(
  poses.every((pose) => POSE_VALUES.includes(pose)),
  'every pose is in the documented pose set',
  poses.join(','),
)
ok(
  labels.every((label) => label.length <= 6),
  'every label is <= 6 characters',
  labels.join(','),
)
ok(
  colors.every((color) => /^#[0-9A-F]{6}$/.test(color)),
  'every colour is #RRGGBB upper-case',
  colors.join(','),
)
ok(
  RESERVED_COLORS.every((reserved) => !colors.includes(reserved)),
  'no state reuses the cache hit/miss colours',
  colors.join(','),
)
ok(
  STATE_VALUES.every((state) => PET_STATES[state] !== undefined),
  'PET_STATES covers every STATE_PRIORITY entry',
)

// Contrast against the panel background, WCAG AA for small text (>= 4.5).
/**
 * Relative luminance of an #RRGGBB colour.
 * @param {string} hex - the colour.
 * @returns {number} luminance in 0..1.
 */
function luminance(hex) {
  const channels = [1, 3, 5].map((offset) => {
    const value = Number.parseInt(hex.slice(offset, offset + 2), 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

/**
 * WCAG contrast ratio between two opaque colours.
 * @param {string} a - colour.
 * @param {string} b - colour.
 * @returns {number} the ratio.
 */
function contrast(a, b) {
  const la = luminance(a)
  const lb = luminance(b)
  const light = Math.max(la, lb)
  const dark = Math.min(la, lb)
  return (light + 0.05) / (dark + 0.05)
}

// #1B1F27 at 86% over a light desktop is lighter than #1B1F27 itself; checking
// against the pure background is the conservative bound for light text.
const contrasts = colors.map((color) => contrast(color, PANEL_BACKGROUND))
ok(
  contrasts.every((ratio) => ratio >= 4.5),
  'every colour clears WCAG AA (4.5:1) on the panel background',
  contrasts.map((ratio) => ratio.toFixed(2)).join(', '),
)

// ---------------------------------------------------------------------------
// 6. Details are always usable strings.
// ---------------------------------------------------------------------------

for (const row of table) {
  const result = computeState(
    row.state === 'offline'
      ? { now: NOW, dshRunning: false, snapshot: snapshot() }
      : { now: NOW, dshRunning: true, lastEventAt: NOW - 1_000, snapshot: snapshot({ jobs: [JOB], peakNow: true, agents: [AGENT, { ...AGENT, id: 's2' }] }) },
  )
  ok(typeof result.detail === 'string', `detail of ${row.state} is a string`)
  ok(result.detail.length <= DETAIL_MAX_CHARS, `detail of ${row.state} is <= ${DETAIL_MAX_CHARS} chars`, result.detail)
  ok(!/undefined|NaN|null/.test(result.detail), `detail of ${row.state} has no leaked placeholder`, result.detail)
  ok(result.label.length > 0 && result.color.length === 7, `label/colour of ${row.state} are present`)
}

eq(formatProgress({ percent: 45.2, etaMs: 37_000 }), '45.2% 剩余 00:37', 'formatProgress with ETA')
eq(formatProgress({ percent: 100 }), '100%', 'formatProgress without ETA')
eq(formatProgress({ percent: 0, etaMs: 0 }), '0%', 'formatProgress ignores a zero ETA')
eq(formatProgress(null), '', 'formatProgress on null')
eq(formatProgress({ percent: '45' }), '', 'formatProgress rejects a string percent')

// ---------------------------------------------------------------------------
// 7. Purity: the module may not reach for the clock, fs, net or timers.
// ---------------------------------------------------------------------------

const source = readFileSync(STATE_MODULE, 'utf8')
for (const forbidden of ['Date.now', 'process.', 'setTimeout', 'setInterval', 'node:fs', 'node:net', 'node:http', 'Math.random', 'node:child_process']) {
  ok(!source.includes(forbidden), `state.mjs does not use ${forbidden}`)
}
const importLines = source.split('\n').filter((line) => /^\s*import\s/.test(line))
ok(importLines.length === 0, 'state.mjs has no import statements at all', importLines.join(' | '))

eq(pillFor('idle'), { label: '空闲', color: '#9DA7B3', pose: 'idle' }, 'pillFor returns the frozen entry')
let threw = false
try {
  pillFor('nope')
} catch {
  threw = true
}
ok(threw, 'pillFor throws on an unknown state')

eq(
  selectState(normalizeObservation({ now: NOW, dshRunning: true, snapshot: snapshot() })).state,
  'idle',
  'selectState is usable directly',
)

// normalizeObservation is the public seam the renderer can debug against.
const factsShape = normalizeObservation({ now: NOW, snapshot: snapshot({ jobs: [JOB], agents: [AGENT] }) })
eq(
  {
    now: factsShape.now,
    dshRunning: factsShape.dshRunning ?? null,
    hasSnapshot: factsShape.hasSnapshot,
    stale: factsShape.stale,
    runningAgents: factsShape.runningAgents,
    activeRunningAgents: factsShape.activeRunningAgents,
    jobCount: factsShape.jobs.length,
    eventRecent: factsShape.eventRecent,
    peakNow: factsShape.peakNow,
  },
  {
    now: NOW,
    dshRunning: null,
    hasSnapshot: true,
    stale: false,
    runningAgents: 1,
    activeRunningAgents: 1,
    jobCount: 1,
    eventRecent: false,
    peakNow: false,
  },
  'normalizeObservation exposes the documented facts',
)

// ---------------------------------------------------------------------------
// Report.
// ---------------------------------------------------------------------------

/**
 * Pad a string to a display width, counting CJK characters as two columns.
 * @param {string} text - the text.
 * @param {number} width - target columns.
 * @returns {string} padded text.
 */
function pad(text, width) {
  let columns = 0
  for (const char of text) columns += /[\u2E80-\u9FFF\uFF00-\uFF60]/.test(char) ? 2 : 1
  return text + ' '.repeat(Math.max(0, width - columns))
}

console.log('')
console.log('state -> label -> colour -> pose -> trigger')
console.log('─'.repeat(112))
console.log(`${pad('STATE', 10)}${pad('LABEL', 12)}${pad('COLOUR', 10)}${pad('POSE', 9)}${pad('CASE', 40)}DETAIL`)
console.log('─'.repeat(112))
for (const row of table) {
  console.log(
    `${pad(row.state, 10)}${pad(row.label, 12)}${pad(row.color, 10)}${pad(row.pose, 9)}${pad(row.case, 40)}${row.detail}`,
  )
}
console.log('─'.repeat(112))
console.log(
  `constants: EVENT_RECENT_MS=${EVENT_RECENT_MS} SNAPSHOT_STALE_MS=${SNAPSHOT_STALE_MS} AGENT_ACTIVE_MS=${AGENT_ACTIVE_MS} DETAIL_MAX_CHARS=${DETAIL_MAX_CHARS}`,
)
console.log(`priority:  ${STATE_PRIORITY.join(' > ')}`)
console.log(`contrast on ${PANEL_BACKGROUND}: ${colors.map((c, i) => `${c}=${contrasts[i].toFixed(2)}`).join(' ')}`)
console.log('')
console.log(`${passed} checks passed, ${failures.length} failed`)
if (failures.length > 0) {
  for (const failure of failures) console.log(`  FAIL ${failure}`)
  process.exitCode = 1
} else {
  console.log('OK')
}
