/**
 * The pet's work-state model.
 *
 * Pure, synchronous, dependency-free: one observation in, one state out. The
 * integration calls this on every widget poll (~2 s), so it must never touch the
 * filesystem, the clock or a timer. `now` is always an input, never read from the
 * wall clock, which also makes the model exactly testable.
 *
 * Importable two ways, both to `computeState` / `STATE_PRIORITY` / `pillFor`:
 *   import { computeState } from './state.mjs'          // ESM
 *   const m = await import(url)                          // dynamic, file URL
 *   const m = require('./state.mjs')                     // Node >= 22 (require(esm))
 *
 * The full contract — every state, colour, trigger, constant and the reason for
 * the priority order — lives in `STATE-PROTOCOL.md` beside this file. Treat the
 * `state` values and their colours as frozen: the renderer switches on them.
 *
 * @module dsh-usage-widget/pet/state
 */

/**
 * @typedef {'offline'|'stale'|'team'|'busy'|'working'|'peak'|'idle'} PetState
 * @typedef {'idle'|'busy'|'team'|'sleepy'|'happy'|'offline'} PetPose
 */

/**
 * The pet's state table. One entry per reachable state; `label`, `color` and
 * `pose` are part of the contract and must stay pairwise distinct (labels and
 * colours are asserted distinct by `test/state.test.mjs`).
 *
 * Colours avoid the panel's cache semantics: hit-green `#7EE787` and miss-red
 * `#FF7B72` are never used, and no state's colour is within a hair of them.
 * Every value below holds >= 6.8:1 contrast against the panel's
 * `#1B1F27` at 86% opacity (effective `~#272A31` on a typical desktop), so all
 * of them clear WCAG AA for 12–14 px text.
 *
 * @type {Readonly<Record<PetState, { label: string, color: string, pose: PetPose }>>}
 */
export const PET_STATES = Object.freeze({
  offline: { label: '离线', color: '#8B949E', pose: 'offline' },
  stale: { label: '数据过期', color: '#D2A8FF', pose: 'sleepy' },
  error: { label: '出错了', color: '#F85149', pose: 'gloomy' },
  celebrating: { label: '收工啦', color: '#E3B341', pose: 'happy' },
  listening: { label: '听主人说', color: '#79C0FF', pose: 'starry' },
  team: { label: '团队协作', color: '#56D4DD', pose: 'team' },
  reading: { label: '查资料', color: '#58A6FF', pose: 'reading' },
  writing: { label: '写文件', color: '#F0883E', pose: 'scribble' },
  running: { label: '跑命令', color: '#FFA657', pose: 'sleeves' },
  thinking: { label: '想事情', color: '#A5D6FF', pose: 'thinking' },
  idle: { label: '空闲', color: '#9DA7B3', pose: 'idle' },
})

/**
 * Total priority order, highest first. Exactly one state wins; states are never
 * combined. The rationale is in STATE-PROTOCOL.md; in short:
 *
 *   offline — no app, nothing else can be true (and there is nobody to report to)
 *   stale       — DSH is up but the picture is too old to trust: nothing derived
 *                 from a dead engine may ever read as "working"
 *   error       — a tool call or a whole turn failed: a 1.6 s black face
 *   celebrating — the turn *completed*: a 3 s stretch + a stats bubble
 *   listening   — the user just said something: 2.6 s of starry eyes
 *   team        — 2+ agents running is the strongest *live* signal DSH emits
 *   reading     — the newest tool reads something (glasses, board, pen)
 *   writing     — the newest tool writes files
 *   running     — the newest tool runs a command, or a background job is open
 *   thinking    — a turn is in progress without a named tool
 *   idle        — the fallback
 *
 * @type {readonly PetState[]}
 */
export const STATE_PRIORITY = Object.freeze([
  'offline',
  'stale',
  'error',
  'celebrating',
  'listening',
  'team',
  'reading',
  'writing',
  'running',
  'thinking',
  'idle',
])

/** How recently tokens must have been produced for `thinking`, in ms. */
export const EVENT_RECENT_MS = 30_000

/**
 * How long the black face lasts after a tool error, in ms.
 *
 * REACTIONS-SPEC §3.3 says 1 600 ms for the *face*, and the page's own override
 * still uses exactly that. The *state* window here is deliberately longer (3 200)
 * because the engine folds the session logs on a 2 s poll: a 1.6 s window can fall
 * entirely between two polls and then the label would never say 出错了 even though
 * she pulled the face. 3 200 > 2 000, so the poll always catches it.
 */
export const ERROR_TTL_MS = 3_200

/** How long the turn-failure face lasts, in ms. */
export const TURN_ERROR_TTL_MS = 3_200

/** How long the stretch after `aborted` lasts, in ms. */
export const ABORTED_TTL_MS = 2_800

/** How long the celebration after a completed turn lasts, in ms. */
export const CELEBRATE_TTL_MS = 3_000

/** How long starry eyes last after the user speaks, in ms. */
export const LISTEN_TTL_MS = 2_600

/** How long a tool call keeps naming the activity while it has no result, in ms. */
export const TOOL_ACTIVE_MS = 7_000

/**
 * How old the newest snapshot may be before it is disbelieved, in ms.
 * 15 missed 2 s polls: loose enough to survive a slow fold or a suspended
 * laptop, tight enough that a dead engine stops painting activity in < 1 min.
 */
export const SNAPSHOT_STALE_MS = 45_000

/**
 * A running agent with no write for this long contributes no activity signal.
 * Keeps a wedged or half-closed turn from pinning the pet at "working" forever.
 */
export const AGENT_ACTIVE_MS = 30_000

/** A running agent also counts as activity when `sinceLastWriteMs` is missing. */
export const ASSUME_ACTIVE_WHEN_AGE_MISSING = true

/** How many characters of free-form `detail` are kept. */
export const DETAIL_MAX_CHARS = 64

/** A job still in `stopping` for longer than this is reported as such. */
export const JOB_STOPPING_MS = 15_000

/** @type {PetState[]} every value `state` may take, in the documented order. */
export const STATE_VALUES = STATE_PRIORITY.slice()

/** @type {PetPose[]} every value `pose` may take (REACTIONS-SPEC §11). */
export const POSE_VALUES = Object.freeze([
  'offline', 'sleepy', 'team', 'starry', 'thinking', 'reading', 'scribble', 'sleeves', 'happy', 'gloomy', 'idle',
])

/** @type {readonly string[]} colours the pet must never use. */
export const RESERVED_COLORS = Object.freeze(['#7EE787', '#FF7B72'])

/** The pet area's background, for contrast checks and the doc. */
export const PANEL_BACKGROUND = '#1B1F27'

/**
 * True for a finite number.
 * @param {unknown} value - candidate.
 * @returns {boolean} whether it is usable arithmetic input.
 */
function isNum(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

/**
 * True when `value` is a non-null non-array object.
 * @param {unknown} value - candidate.
 * @returns {boolean} whether it is a record.
 */
function isRecord(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Count the usable rows of a possibly missing / mistyped array field.
 * A missing key, a non-array and an empty array all yield 0 — the same behaviour
 * the snapshot's own "both arrays are always present" contract guarantees today,
 * kept here so an older engine that omits them cannot break the pet.
 *
 * @param {unknown} value - the raw field.
 * @returns {any[]} the rows (never null).
 */
function rows(value) {
  return Array.isArray(value) ? value.filter(isRecord) : []
}

/**
 * Collapse text to one trimmed line of at most `DETAIL_MAX_CHARS` characters.
 * @param {unknown} value - raw text.
 * @returns {string} the rendered line, or ''.
 */
function oneLine(value) {
  if (typeof value !== 'string') return ''
  const text = value.replace(/\s+/g, ' ').trim()
  if (text.length <= DETAIL_MAX_CHARS) return text
  return `${text.slice(0, DETAIL_MAX_CHARS - 1)}…`
}

/**
 * Render milliseconds as `MM:SS`, rounding up so a live ETA never reads as 00:00.
 * @param {number} ms - duration.
 * @returns {string} the rendered duration.
 */
function formatDuration(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

/**
 * The panel's existing progress string, reproduced so the pet and the jobs
 * section cannot disagree: `45.2% 剩余 00:37`, or just `45.2%` when no ETA.
 *
 * @param {{ percent?: unknown, etaMs?: unknown } | null | undefined} progress - the job's progress.
 * @returns {string} '' when no usable percentage.
 */
export function formatProgress(progress) {
  if (!isRecord(progress)) return ''
  const percent = progress.percent
  if (!isNum(percent)) return ''
  const shown = `${Math.round(percent * 10) / 10}%`
  const eta = progress.etaMs
  if (isNum(eta) && eta > 0) return `${shown} 剩余 ${formatDuration(eta)}`
  return shown
}

/**
 * Identify one background job from a snapshot row.
 *
 * The snapshot's job rows carry `status` only on the bridge path, so a
 * `stopping` row is detected when present and assumed `running` otherwise. The
 * log-derived path only ever emits jobs that are still open.
 *
 * @param {any} job - a snapshot job row.
 * @param {number} now - observation time.
 * @returns {{ program: string, command: string, progressText: string, note: string, status: string, stopping: boolean }}
 */
export function jobFacts(job, now) {
  const program = oneLine(job?.program) || oneLine(job?.kind) || '任务'
  const command = oneLine(job?.command) || oneLine(job?.label)
  const progressText = formatProgress(job?.progress)
  const note = oneLine(job?.progressNote)
  const rawStatus = typeof job?.status === 'string' ? job.status.toLowerCase() : ''
  const status = rawStatus.length > 0 ? rawStatus : 'running'
  const startedAt = isNum(job?.startedAt) ? job.startedAt : null
  const stopping =
    status === 'stopping' && startedAt !== null && now - startedAt > JOB_STOPPING_MS
  return { program, command, progressText, note, status, stopping }
}

/**
 * Identify one agent row.
 *
 * `sinceLastWriteMs` is the only freshness the row carries, so it is what
 * distinguishes "the model is in a turn" from "a turn was opened and abandoned".
 * A missing age is treated as active: newer is never punished for being terse.
 *
 * @param {any} agent - a snapshot agent row.
 * @returns {{ label: string, running: boolean, active: boolean, model: string }}
 */
export function agentFacts(agent) {
  const label = oneLine(agent?.label) || oneLine(agent?.id) || '智能体'
  const state = typeof agent?.state === 'string' ? agent.state.toLowerCase() : ''
  const running = state === 'running' || state === 'busy'
  const age = agent?.sinceLastWriteMs
  const active = isNum(age) ? age <= AGENT_ACTIVE_MS : ASSUME_ACTIVE_WHEN_AGE_MISSING
  const model = oneLine(agent?.model)
  return { label, running, active, model }
}

/**
 * Which activity a tool name implies — the tool table of REACTIONS-SPEC §3.2,
 * collapsed onto the eleven states. `program` is useless for this (it is the
 * *inner* program name: `pwsh`/`node`/`python`), so classification uses the raw
 * tool name the engine passes through as `tool/call.data.name`.
 *
 * @type {Readonly<Record<string, PetState>>}
 */
export const TOOL_ACTIVITY = Object.freeze({
  read: 'reading', pdf_read: 'reading', docx_read: 'reading', xlsx_read: 'reading',
  pptx_read: 'reading', skill: 'reading', auto_cite: 'reading', grep: 'reading',
  web_search: 'reading', web_fetch: 'reading', browser: 'reading', fetch: 'reading',
  search_papers: 'reading', search_arxiv: 'reading', kb_search: 'reading', kb_rag: 'reading',
  search_semantic: 'reading', create_goal: 'thinking', update_goal: 'thinking', get_goal: 'thinking',
  glob: 'thinking', ls: 'thinking', list_dir: 'thinking',
  write: 'writing', edit: 'writing', todo_write: 'writing',
  bash: 'running', pwsh: 'running', shell: 'running', run_command: 'running',
  command: 'running', exec: 'running', job_output: 'running',
  subagent: 'team', subagent_fork: 'team', task: 'team', workflow: 'team', ralph: 'team',
  send_message: 'team', team_task_create: 'team', team_task_update: 'team',
  team_task_get: 'team', team_task_list: 'team', list_agents: 'team',
  present: 'celebrating', pdf_create: 'celebrating', docx_create: 'celebrating',
  pptx_create: 'celebrating', xlsx_write: 'celebrating', sci_draw: 'celebrating',
  ask_user_question: 'thinking',
})

/**
 * The activity a tool call implies, falling back to `reading` — the spec's
 * documented fallback for an unmatched tool (眼镜兜底).
 *
 * @param {unknown} name - the raw tool name.
 * @returns {PetState} one of `STATE_VALUES`.
 */
export function toolActivity(name) {
  if (typeof name !== 'string' || name.length === 0) return 'thinking'
  return TOOL_ACTIVITY[name] ?? 'reading'
}

/**
 * Normalize one raw observation into the facts the priority ladder needs.
 *
 * Everything here is defensive: the snapshot may be absent, a field may be
 * missing because the engine is older, an array may be `[]`, or the whole frame
 * may be minutes old because the engine died.
 *
 * @param {{ snapshot?: any, lastEventAt?: unknown, dshRunning?: unknown, now?: unknown }} [observation] - the raw input.
 * @returns {{
 *   now: number,
 *   dshRunning: boolean | undefined,
 *   hasSnapshot: boolean,
 *   snapshotAgeMs: number | null,
 *   stale: boolean,
 *   agents: { label: string, running: boolean, active: boolean, model: string }[],
 *   jobs: any[],
 *   jobFacts: { program: string, command: string, progressText: string, note: string, status: string, stopping: boolean }[],
 *   runningAgents: number,
 *   activeRunningAgents: number,
 *   latestEventAgeMs: number | null,
 *   eventRecent: boolean,
 *   peakNow: boolean,
 *   jobsSource: string,
 * }} the normalized facts.
 */
export function normalizeObservation(observation = {}) {
  const source = isRecord(observation) ? observation : /** @type {any} */ ({})
  const snapshot = isRecord(source.snapshot) ? source.snapshot : null
  const hasSnapshot = snapshot !== null
  const at = hasSnapshot && isNum(snapshot.at) ? snapshot.at : null
  const now = isNum(source.now) ? source.now : at !== null ? at : 0

  const dshRunning =
    source.dshRunning === true ? true : source.dshRunning === false ? false : undefined

  const snapshotAgeMs = at === null ? null : Math.max(0, now - at)
  const stale = snapshotAgeMs === null || snapshotAgeMs > SNAPSHOT_STALE_MS

  const agents = rows(snapshot?.agents).map(agentFacts)
  const rawJobs = rows(snapshot?.jobs)
  const jobFactsList = rawJobs.map((job) => jobFacts(job, now))

  const lastEventAt = source.lastEventAt
  // A negative age means the timestamp is in the future (clock skew between the
  // engine and the widget). That is not evidence of work: treat the event as
  // arriving "now" and let EVENT_RECENT_MS judge it, rather than clamping the
  // age to 0 and calling any future stamp recent.
  const latestEventAgeMs =
    isNum(lastEventAt) ? (lastEventAt > now ? -1 : now - lastEventAt) : null
  const eventRecent = latestEventAgeMs !== null && latestEventAgeMs >= 0 && latestEventAgeMs <= EVENT_RECENT_MS

  // ---- reaction signals (REACTIONS-SPEC §5): all optional, all defensive ----
  const signals = isRecord(source.signals) ? source.signals : null
  const tool = isRecord(signals?.tool) ? signals.tool : null
  const turn = isRecord(signals?.turn) ? signals.turn : null
  const age = (value) => (isNum(value) && value > 0 ? Math.max(0, now - value) : null)
  const toolAgeMs = age(tool?.at)
  const toolPhase = tool?.phase === 'call' || tool?.phase === 'result' ? tool.phase : null
  const toolOk = tool?.ok === true ? true : tool?.ok === false ? false : null
  const toolName = typeof tool?.name === 'string' && tool.name.length > 0 ? tool.name : null
  const toolState =
    typeof tool?.state === 'string' && STATE_PRIORITY.includes(/** @type {any} */ (tool.state))
      ? /** @type {PetState} */ (tool.state)
      : toolName === null ? null : toolActivity(toolName)
  const toolSummary = oneLine(tool?.summary)
  // The last *failure* is published separately, so a call that starts right after a
  // failed one cannot hide it (REACTIONS-SPEC §3.3: the black face must be visible;
  // with a 2 s fold a 1.6 s window would often fall between two polls).
  const lastError = isRecord(signals?.lastError) ? signals.lastError : null
  const lastErrorAgeMs = age(lastError?.at)
  const lastErrorName = typeof lastError?.name === 'string' && lastError.name.length > 0 ? lastError.name : null
  const lastErrorText = oneLine(lastError?.error)
  const toolError = oneLine(tool?.error)
  const turnAgeMs = age(turn?.at)
  const turnReason = turn === null ? null : (typeof turn.reason === 'string' ? turn.reason : null)
  const turnMs = isNum(turn?.ms) ? turn.ms : null
  const turnTokens = isNum(turn?.tokens) ? turn.tokens : null
  const lastUserAgeMs = age(signals?.lastUserAt)
  const streamingActive = isRecord(signals?.streaming) && signals.streaming.active === true
  const idleMs = isNum(signals?.idleMs) ? signals.idleMs : null
  // A tool call is "current" until its result lands (and only for a while, so a
  // crashed call cannot pin the label forever); a failed result is a 1.6 s face.
  const toolCurrent = toolPhase === 'call' && toolAgeMs !== null && toolAgeMs <= TOOL_ACTIVE_MS
  const toolFailed = lastErrorAgeMs !== null && lastErrorAgeMs <= ERROR_TTL_MS
  const turnCompleted =
    turnAgeMs !== null && turnAgeMs <= CELEBRATE_TTL_MS && (turnReason === null || turnReason === 'completed')
  const turnFailed = turnAgeMs !== null && turnAgeMs <= TURN_ERROR_TTL_MS && turnReason === 'error'
  const listeningNow = lastUserAgeMs !== null && lastUserAgeMs <= LISTEN_TTL_MS

  return {
    now,
    dshRunning,
    hasSnapshot,
    snapshotAgeMs,
    stale,
    agents,
    jobs: rawJobs,
    jobFacts: jobFactsList,
    runningAgents: agents.filter((agent) => agent.running).length,
    activeRunningAgents: agents.filter((agent) => agent.running && agent.active).length,
    latestEventAgeMs,
    eventRecent,
    peakNow: snapshot?.peakNow === true,
    jobsSource: typeof snapshot?.jobsSource === 'string' ? snapshot.jobsSource : 'unknown',
    // reaction facts
    signals,
    tool,
    toolName,
    toolPhase,
    toolOk,
    toolState,
    toolSummary,
    toolError,
    toolAgeMs,
    toolCurrent,
    toolFailed,
    turn,
    turnReason,
    turnMs,
    turnTokens,
    turnAgeMs,
    turnCompleted,
    turnFailed,
    lastUserAgeMs,
    listeningNow,
    lastError,
    lastErrorAgeMs,
    lastErrorName,
    lastErrorText,
    streamingActive,
    idleMs,
  }
}

/**
 * The `detail` line for a state that has one. Always ≤ `DETAIL_MAX_CHARS`, and
 * never a stray separator when a sub-value is empty.
 *
 * @param {PetState} state - the chosen state.
 * @param {ReturnType<typeof normalizeObservation>} facts - normalized facts.
 * @returns {string} the detail line, or '' when there is nothing to add.
 */
export function describe(state, facts) {
  if (state === 'team') {
    const active = facts.agents.filter((agent) => agent.running && agent.active)
    const head = active.length > 0 ? active[0] : facts.agents.find((agent) => agent.running)
    const count = `运行 ${facts.runningAgents} 个智能体`
    return oneLine(head !== undefined ? `${count} · ${head.label}` : count)
  }
  if (state === 'error') {
    const parts = []
    const failing = facts.lastErrorName ?? facts.toolName
    if (failing !== null) parts.push(failing)
    const errText = facts.lastErrorText.length > 0 ? facts.lastErrorText : facts.toolError
    if (errText.length > 0) parts.push(errText)
    else if (facts.turnReason === 'error') parts.push('整轮失败')
    return oneLine(parts.length > 0 ? `报错 · ${parts.join(' · ')}` : '出错了')
  }
  if (state === 'celebrating') {
    const parts = []
    if (isNum(facts.turnMs)) parts.push(`${Math.round(facts.turnMs / 100) / 10}s`)
    if (isNum(facts.turnTokens)) parts.push(`${facts.turnTokens} tokens`)
    return oneLine(parts.join(' · ') || '收工啦')
  }
  if (state === 'listening') return ''
  if (state === 'reading' || state === 'writing') {
    const parts = []
    if (facts.toolName !== null) parts.push(facts.toolName)
    if (facts.toolSummary.length > 0) parts.push(facts.toolSummary)
    return oneLine(parts.join(' · '))
  }
  if (state === 'running') {
    if (facts.toolCurrent && facts.toolName !== null) {
      const parts = [facts.toolName]
      if (facts.toolSummary.length > 0) parts.push(facts.toolSummary)
      return oneLine(parts.join(' · '))
    }
    const first = facts.jobFacts[0]
    if (first === undefined) return ''
    const parts = [first.program]
    if (first.progressText.length > 0) parts.push(first.progressText)
    else if (first.note.length > 0 && first.note !== '无进度输出') parts.push(first.note)
    if (facts.jobFacts.length > 1) parts.push(`+${facts.jobFacts.length - 1}`)
    if (facts.jobFacts.some((job) => job.stopping)) parts.push('stopping')
    if (facts.jobsSource === 'logs') parts.push('日志源')
    return oneLine(parts.join(' · '))
  }
  if (state === 'thinking') {
    if (facts.streamingActive) return '正在输出'
    if (facts.latestEventAgeMs !== null) {
      return `最近出词 ${Math.round(facts.latestEventAgeMs / 1000)}s 前`
    }
    return '正在想事情'
  }
  if (state === 'stale') {
    if (facts.snapshotAgeMs === null) return '未收到引擎快照'
    return `快照 ${Math.round(facts.snapshotAgeMs / 1000)}s 无更新`
  }
  if (state === 'offline') {
    return facts.hasSnapshot ? 'DSH 未在运行' : 'DSH 未在运行 · 无快照'
  }
  return ''
}

/**
 * Pick the winning state from normalized facts. Exported so a caller can reuse
 * the ladder (and so the tests can pin the order); most callers want
 * `computeState`.
 *
 * @param {ReturnType<typeof normalizeObservation>} facts - normalized facts.
 * @returns {{ state: PetState, reason: string }} the winner and why.
 */
export function selectState(facts) {
  // 1. offline — the app is gone; no other signal may outrank it.
  if (facts.dshRunning === false) return { state: 'offline', reason: 'dshRunning === false' }

  // 2. stale — DSH is up (or unknown) but the frame is too old / absent. When
  //    `dshRunning` is unknown a fresh snapshot is required before believing
  //    anything, otherwise the pet could act on a dead engine's last frame.
  if (facts.stale) {
    return {
      state: 'stale',
      reason:
        facts.snapshotAgeMs === null
          ? 'no snapshot'
          : `snapshot age ${Math.round(facts.snapshotAgeMs)}ms > SNAPSHOT_STALE_MS`,
    }
  }

  // 3. error — a tool that just failed (1.6 s black face) or a failed turn.
  if (facts.toolFailed) {
    return { state: 'error', reason: `tool ${facts.lastErrorName ?? facts.toolName ?? '?'} failed ${Math.round(facts.lastErrorAgeMs ?? 0)}ms ago` }
  }
  if (facts.turnFailed) {
    return { state: 'error', reason: 'turn ended with reason error' }
  }

  // 4. celebrating — the turn completed: 3 s of stretch + a stats bubble.
  if (facts.turnCompleted) {
    return { state: 'celebrating', reason: `turn completed ${Math.round(facts.turnAgeMs ?? 0)}ms ago` }
  }

  // 5. listening — the user just spoke: 2.6 s of starry eyes.
  if (facts.listeningNow) {
    return { state: 'listening', reason: `user message ${Math.round(facts.lastUserAgeMs ?? 0)}ms ago <= LISTEN_TTL_MS` }
  }

  // 6. team — two or more agents with a live turn. One running agent alone is
  //    not collaboration; it lands in `thinking`/`idle` below on its own merits.
  if (facts.runningAgents >= 2) {
    return { state: 'team', reason: `${facts.runningAgents} agents running` }
  }

  // 7. the newest tool names the activity while it has no result yet
  //    (reading/writing/running/celebrating/thinking), exactly as the tool table
  //    in REACTIONS-SPEC §3.2 says.
  if (facts.toolCurrent && facts.toolState !== null) {
    return { state: facts.toolState, reason: `tool ${facts.toolName ?? '?'} in flight (${facts.toolState})` }
  }

  // 8. running — at least one background job row is open.
  if (facts.jobs.length > 0) {
    return { state: 'running', reason: `${facts.jobs.length} job(s) present` }
  }

  // 9. thinking — a single live turn that is still producing (or streaming), or
  //    tokens that just landed. All of them are "she is working on something".
  if (facts.activeRunningAgents >= 1 || facts.eventRecent || facts.streamingActive) {
    return {
      state: 'thinking',
      reason:
        facts.streamingActive
          ? 'assistant step open'
          : facts.eventRecent && facts.latestEventAgeMs !== null
            ? `event ${Math.round(facts.latestEventAgeMs)}ms ago <= EVENT_RECENT_MS`
            : 'one running agent wrote recently',
    }
  }

  // 10. idle — the fallback. (`peak` intentionally has no label slot: peak
  //     pricing is the panel footer's story, not her working state.)
  return { state: 'idle', reason: 'nothing happening, DSH up' }
}

/**
 * Compute the pet's state for one observation.
 *
 * @param {{
 *   snapshot?: any,
 *   lastEventAt?: number | null,
 *   dshRunning?: boolean | null,
 *   now?: number,
 * }} [observation] - one poll's inputs. `now` is required for a meaningful
 *   answer; when omitted it falls back to the snapshot's own `at`, which keeps
 *   the call deterministic and never reaches for the wall clock.
 * @returns {{
 *   state: PetState,
 *   label: string,
 *   color: string,
 *   detail: string,
 *   pose: PetPose,
 *   reason: string,
 *   source: 'snapshot' | 'none',
 * }} the state line the renderer consumes.
 */
export function computeState(observation = {}) {
  const facts = normalizeObservation(observation)
  const { state, reason } = selectState(facts)
  const pill = PET_STATES[state]
  return {
    state,
    label: pill.label,
    color: pill.color,
    detail: describe(state, facts),
    pose: pill.pose,
    reason,
    source: facts.hasSnapshot ? 'snapshot' : 'none',
  }
}

/**
 * Return just the presentation triple for a state — handy for the renderer's
 * stylesheet. Throws on an unknown state so a typo surfaces at once.
 *
 * @param {PetState | string} state - one of `STATE_VALUES`.
 * @returns {{ label: string, color: string, pose: PetPose }} the frozen entry.
 */
export function pillFor(state) {
  const pill = PET_STATES[/** @type {PetState} */ (state)]
  if (pill === undefined) {
    throw new Error(`unknown pet state: ${String(state)} (expected one of ${STATE_VALUES.join(', ')})`)
  }
  return pill
}

/**
 * The priority index of a state, lowest = wins.
 * @param {PetState | string} state - a state value.
 * @returns {number} its index in `STATE_PRIORITY`, or -1.
 */
export function priorityOf(state) {
  return STATE_PRIORITY.indexOf(/** @type {PetState} */ (state))
}

export default computeState
