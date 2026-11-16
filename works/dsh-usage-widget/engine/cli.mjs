#!/usr/bin/env node
/**
 * Streaming data engine for the standalone DSH usage widget.
 *
 * One long-running process, one job: fold the durable session logs, price them,
 * and stream newline-delimited JSON to stdout — one object per line, flushed as
 * it is produced. The widget (or any other reader) parses the stream; nothing is
 * requested from it, and nothing else is printed to stdout.
 *
 * The first fold is a **baseline**: it produces the first snapshot but no
 * events, because the widget must not replay the entire history as a flood of
 * toasts on startup. Every later fold diffs its samples against the ids already
 * seen, so a session that grows, or a whole re-fold, emits exactly the calls
 * that were not there before.
 *
 * Emitted shapes:
 *
 *   {"type":"ready","at":<ms>,"pollMs":<ms>,"usdToCny":<rate>}
 *   {"type":"snapshot","at":<ms>,"peakNow":<bool>,"rate":<rate>,
 *    "today":{ "costUsd":n,"costCny":n,"calls":n,"tokens":{"hit":n,"miss":n,"out":n}},
 *    "total":{ "costUsd":n,"costCny":n,"calls":n,"sessions":n,"tokens":{...}},
 *    "balance":{"ok":true,"currency":"CNY","total":"8.47","granted":"0.00","toppedUp":"8.47","fetchedAt":<ms>}
 *             | {"ok":false,"error":"..."},
 *    "agents":[{"id":"<session>","label":"<descriptor label>","state":"running"|"idle",
 *               "model":"<id>"|null,"turn":n,"startedAt":<ms>,"elapsedMs":n,"sinceLastWriteMs":n}],
 *    "jobs":[{"id":"<callId>","session":"<session>","program":"pwsh","command":"<one line, ≤120 chars>",
 *             "startedAt":<ms>,"elapsedMs":n,
 *             "progress":{"percent":n,"etaMs":n,"source":"size"|"log"}|null,
 *             "progressNote":null|"<why nothing is observable>"}],
 *    "pet":{"state":"idle","label":"空闲","color":"#9DA7B3","detail":"","pose":"idle",
 *           "reason":"...","source":"snapshot"}}
 *
 *   `pet` is **additive** and is exactly `computeState()` from `pet/state.mjs`
 *   (the frozen contract in `pet/STATE-PROTOCOL.md`); a reader that does not know
 *   the key ignores it. The same object is published to
 *   `pet/renderer/state.json` on every poll, which is what the Live2D page
 *   polls — see `engine/pet-state.mjs`.
 *   {"type":"event","at":<ms>,"session":"<id>","turn":n,"step":n,"model":"<id>",
 *    "hit":n,"miss":n,"out":n,"costUsd":n,"costCny":n}
 *   {"type":"error","at":<ms>,"message":"..."}
 *
 * Usage:
 *   node cli.mjs [--config <path>] [--once]
 *
 * `--config` defaults to `../config.json` beside the engine directory; a
 * relative path is resolved against the working directory first and against the
 * engine directory second. `--once` emits the ready line, one snapshot, and then
 * exits 0.
 *
 * @module dsh-usage-widget/cli
 */

import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  FALLBACK_PRICE,
  PRICE_CARD,
  buildDashboard,
  isPeak,
  priceOf,
} from './usage.mjs'
import {
  DEFAULT_JOBS_MAX,
  collectActivity,
} from './activity.mjs'
import { readAllSessions, listSessionArtifacts } from './session-store.mjs'
import { readBalance } from './balance.mjs'
import { readBridgeJobs, defaultBridgePath } from './bridge-jobs.mjs'
import { computePet, createPetTracker, writePetState, writeSignals } from './pet-state.mjs'
import { toolActivity } from '../pet/state.mjs'

/** Absolute directory holding this engine. */
const ENGINE_DIR = dirname(fileURLToPath(import.meta.url))

/** Default config: `../config.json`, the widget's own file. */
export const DEFAULT_CONFIG_PATH = join(ENGINE_DIR, '..', 'config.json')

/** Config fallbacks, applied per key whenever the file omits or mistypes one. */
export const DEFAULTS = Object.freeze({
  pollMs: 2000,
  balanceMs: 60_000,
  usdToCny: 7.1,
  defaultModel: 'deepseek-flash',
  activityJobsMax: DEFAULT_JOBS_MAX,
  bridgePath: '',
  bridgeStaleMs: 10_000,
})

/**
 * Parse the command line.
 *
 * @param {string[]} argv - arguments after the script path.
 * @returns {{ configPath: string | undefined, once: boolean }} the parsed options.
 */
export function parseArgs(argv) {
  /** @type {{ configPath: string | undefined, once: boolean }} */
  const options = { configPath: undefined, once: false }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--once') {
      options.once = true
    } else if (arg === '--config') {
      const next = argv[index + 1]
      if (next !== undefined && !next.startsWith('--')) {
        options.configPath = next
        index += 1
      }
    } else if (arg.startsWith('--config=')) {
      options.configPath = arg.slice('--config='.length)
    }
  }
  return options
}

/**
 * Resolve `--config`: absolute as given, otherwise the working directory takes
 * precedence over the engine directory so the documented default (`../config.json`
 * beside the engine) still works from anywhere.
 *
 * @param {string | undefined} requested - the raw argument.
 * @returns {string} an absolute path (not necessarily an existing one).
 */
export function resolveConfigPath(requested) {
  if (requested === undefined || requested.length === 0) return DEFAULT_CONFIG_PATH
  if (isAbsolute(requested)) return requested
  const fromCwd = resolve(process.cwd(), requested)
  return existsSync(fromCwd) ? fromCwd : resolve(ENGINE_DIR, requested)
}

/**
 * Fill one config value, keeping the default when the file's value is unusable.
 * @param {any} value - the raw value.
 * @param {number} fallback - the default.
 * @param {{ integer?: boolean, min?: number }} [rules] - extra acceptance rules.
 * @returns {number} the accepted value.
 */
function numberOr(value, fallback, rules = {}) {
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return fallback
  if (rules.integer === true && !Number.isInteger(parsed)) return fallback
  if (rules.min !== undefined && parsed < rules.min) return fallback
  return parsed
}

/**
 * Normalize a raw config object onto the engine's honoured keys.
 *
 * `agentsMax` and `jobsMax` are the UI's caps and are deliberately *not* read
 * here: the engine returns every agent and as many unmatched calls as
 * `activityJobsMax` allows, and the widget decides how many to draw.
 *
 * @param {any} raw - the parsed config file.
 * @returns {{ pollMs: number, balanceMs: number, usdToCny: number, defaultModel: string, activityJobsMax: number }} the config.
 */
export function normalizeConfig(raw) {
  const source = raw !== null && typeof raw === 'object' ? raw : {}
  return {
    pollMs: numberOr(source.pollMs, DEFAULTS.pollMs, { integer: true, min: 50 }),
    balanceMs: numberOr(source.balanceMs, DEFAULTS.balanceMs, { min: 1000 }),
    usdToCny: numberOr(source.usdToCny, DEFAULTS.usdToCny, { min: 0 }),
    defaultModel:
      typeof source.defaultModel === 'string' && source.defaultModel.length > 0
        ? source.defaultModel
        : DEFAULTS.defaultModel,
    activityJobsMax: numberOr(source.activityJobsMax, DEFAULTS.activityJobsMax, {
      integer: true,
      min: 1,
    }),
    // Empty means "the bridge's own default", `$DSH_HOME/usage-widget/jobs.json`.
    bridgePath:
      typeof source.bridgePath === 'string' && source.bridgePath.length > 0 ? source.bridgePath : DEFAULTS.bridgePath,
    bridgeStaleMs: numberOr(source.bridgeStaleMs, DEFAULTS.bridgeStaleMs, { integer: true, min: 1000 }),
  }
}

/**
 * Read and normalize the config file. A missing or malformed file is *reported*
 * rather than fatal: the engine runs on defaults and says so on the stream.
 *
 * @param {string} path - absolute config path.
 * @returns {Promise<{ config: ReturnType<typeof normalizeConfig>, error: string | undefined }>}
 */
export async function loadConfig(path) {
  let text
  try {
    text = await readFile(path, 'utf8')
  } catch (error) {
    return {
      config: normalizeConfig(undefined),
      error: `cannot read ${path}: ${error instanceof Error ? error.message : String(error)}`,
    }
  }
  try {
    return { config: normalizeConfig(JSON.parse(text)), error: undefined }
  } catch (error) {
    return {
      config: normalizeConfig(undefined),
      error: `malformed JSON in ${path}: ${error instanceof Error ? error.message : String(error)}`,
    }
  }
}

/** The stable identity of one model call. */
export function sampleId(sessionId, turn, step) {
  return `${sessionId}:${turn}:${step}`
}

/**
 * Price one sample on its own timestamp, so its peak/off-peak split follows the
 * moment the call actually ran.
 *
 * @param {{ at: number, model: string, tokens: { cacheHit: number, cacheMiss: number, output: number } }} sample
 * @param {number} rate - USD -> CNY.
 * @returns {{ costUsd: number, costCny: number }} the call's cost.
 */
export function priceSample(sample, rate) {
  const price = PRICE_CARD[sample.model] ?? FALLBACK_PRICE
  const costUsd = priceOf(sample.tokens, price, isPeak(sample.at))
  return { costUsd, costCny: costUsd * rate }
}

/** The widget's compact token triple. */
function tokensOf(tokens) {
  return { hit: tokens.cacheHit, miss: tokens.cacheMiss, out: tokens.output }
}

/**
 * Project the dashboard view model onto the snapshot shape.
 *
 * Costs are emitted at full precision: the UI owns formatting, and rounding here
 * would destroy single-call differences that the model breakdown relies on.
 *
 * `agents` and `jobs` are *live* state derived from the same artifacts, not from
 * the dashboard: agents are the delegating sessions and jobs are the tool calls
 * with no result yet. Both arrays are always present, empty when there is
 * nothing to report, so a reader never has to test for the key.
 *
 * @param {any} dashboard - output of `buildDashboard`.
 * @param {number} at - the snapshot timestamp.
 * @param {number} rate - USD -> CNY.
 * @param {{ ok: boolean } & Record<string, any>} balance - the balance card.
 * @param {{ agents?: any[], jobs?: any[] }} [activity] - live agent and job rows.
 * @returns {any} the snapshot object.
 */
export function snapshotOf(dashboard, at, rate, balance, activity = {}) {
  const today = dashboard.today
  const totals = dashboard.totals
  return {
    type: 'snapshot',
    at,
    peakNow: dashboard.peakNow,
    rate,
    today: {
      costUsd: today.cost,
      costCny: today.cost * rate,
      calls: today.calls,
      tokens: tokensOf(today.tokens),
    },
    total: {
      costUsd: totals.cost,
      costCny: totals.cost * rate,
      calls: totals.calls,
      sessions: totals.sessions,
      tokens: tokensOf(totals.tokens),
    },
    balance,
    agents: activity.agents ?? [],
    jobs: activity.jobs ?? [],
    // Which source the job rows came from: the host bridge while its file is
    // fresh, otherwise the session logs. Handy when a row looks wrong.
    jobsSource: activity.jobsSource ?? 'logs',
  }
}

/**
 * Project one newly observed sample onto the event shape.
 *
 * @param {any} session - the folded session facts.
 * @param {any} sample - the sample.
 * @param {number} rate - USD -> CNY.
 * @returns {any} the event object.
 */
export function eventOf(session, sample, rate) {
  const { costUsd, costCny } = priceSample(sample, rate)
  return {
    type: 'event',
    at: sample.at,
    session: session.sessionId,
    turn: sample.turn,
    step: sample.step,
    model: sample.model,
    hit: sample.tokens.cacheHit,
    miss: sample.tokens.cacheMiss,
    out: sample.tokens.output,
    costUsd,
    costCny,
  }
}

/**
 * Build the stdout writer. Every line is written and dispatched immediately;
 * nothing is accumulated, so a reader sees each object as it happens.
 *
 * @param {NodeJS.WritableStream} stream - normally `process.stdout`.
 * @returns {(object: any) => void} the line writer.
 */
export function createEmitter(stream) {
  return (object) => {
    try {
      stream.write(`${JSON.stringify(object)}\n`)
    } catch {
      // A dead reader (EPIPE) is handled by the stream's own error handler; a
      // write failure must never take the fold down.
    }
  }
}

/**
 * The engine's mutable state: what has already been emitted, and whether the
 * baseline fold has happened.
 */
export function createState() {
  return {
    /** Sample ids already accounted for. */
    seen: new Set(),
    /** Failure keys already reported, so a persistent fault is reported once. */
    reported: new Set(),
    /** True until the first fold has been recorded: that fold emits no events. */
    baseline: true,
    /** Last balance error, to report a change of state rather than every poll. */
    lastBalanceError: undefined,
    /**
     * Per-job progress samples (first percentage, last byte count) that must
     * survive between polls, because a rate cannot be measured from one sample.
     */
    jobState: new Map(),
    /** Folded activity per unchanged artifact, keyed by path, mtime and size. */
    activityCache: new Map(),
    /**
     * The pet's cross-poll memory: the newest event it has emitted and the
     * panel's heartbeat cache. See `pet-state.mjs`.
     */
    pet: createPetTracker(),
  }
}

/**
 * Run exactly one poll: fold, price, emit the snapshot, then emit events for
 * samples that were not part of any earlier fold.
 *
 * @param {{ config: ReturnType<typeof normalizeConfig>, state: ReturnType<typeof createState>, emit: (object: any) => void }} context
 * @returns {Promise<void>}
 */
export async function poll({ config, state, emit }) {
  const at = Date.now()

  /** @type {any[]} */
  let sessions = []
  /**
   * Whether the sweep itself failed, so the live-state pump can be skipped
   * rather than reporting the same unreadable home twice.
   * @type {boolean}
   */
  let sweepFailed = false
  try {
    const sweep = await readAllSessions({ defaultModel: config.defaultModel })
    sessions = sweep.sessions
    for (const failure of sweep.failures) {
      const key = `artifact:${failure.sessionId}:${failure.error}`
      if (state.reported.has(key)) continue
      state.reported.add(key)
      emit({ type: 'error', at: Date.now(), message: `session ${failure.sessionId}: ${failure.error}` })
    }
  } catch (error) {
    // A sweep-level failure (an unreadable home, a permissions fault) still
    // yields a snapshot: the widget keeps its shape and shows zeroes.
    sweepFailed = true
    const message = error instanceof Error ? error.message : String(error)
    const key = `sweep:${message}`
    if (!state.reported.has(key)) {
      state.reported.add(key)
      emit({ type: 'error', at: Date.now(), message: `sweep: ${message}` })
    }
  }

  // Live state needs the artifact list itself (path, mtime, size), which the
  // usage sweep reports only as a count. The listing is a directory walk, and
  // the activity fold cache makes an unchanged artifact a map lookup, so this
  // second pass is cheap for a home with many idle sessions.
  let activity = { agents: [], jobs: [], unmatched: 0 }
  if (!sweepFailed) {
    try {
      const artifacts = await listSessionArtifacts()
      activity = await collectActivity(artifacts, {
        now: at,
        jobState: state.jobState,
        jobsMax: config.activityJobsMax,
        cache: state.activityCache,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const key = `activity:${message}`
      if (!state.reported.has(key)) {
        state.reported.add(key)
        emit({ type: 'error', at: Date.now(), message: `activity: ${message}` })
      }
    }
  }

  // The host bridge mirrors DSH's job registry, whose output ring is readable
  // while a command runs — progress the session logs only receive at settlement.
  // While its file is fresh it wins outright, including when it reports nothing
  // (that genuinely means nothing is running); the log-derived rows above are the
  // fallback for when it is absent, stale or unreadable.
  try {
    const bridge = await readBridgeJobs({
      path: config.bridgePath.length > 0 ? config.bridgePath : defaultBridgePath(),
      staleMs: config.bridgeStaleMs,
      now: at,
    })
    activity = bridge.fresh
      ? { ...activity, jobs: bridge.jobs, jobsSource: 'bridge' }
      : { ...activity, jobsSource: 'logs' }
  } catch {
    // readBridgeJobs never throws by contract; this keeps a future edit honest
    // without taking the poll down with it.
    activity = { ...activity, jobsSource: 'logs' }
  }

  const dashboard = buildDashboard(sessions, { now: at })

  const balance = await readBalance({ ttlMs: config.balanceMs })
  if (balance.ok) {
    state.lastBalanceError = undefined
  } else if (state.lastBalanceError !== balance.error) {
    state.lastBalanceError = balance.error
    emit({ type: 'error', at: Date.now(), message: `balance: ${balance.error}` })
  }

  /** @type {{ session: any, sample: any }[]} */
  const fresh = []
  const baseline = state.baseline
  for (const session of sessions) {
    for (const sample of session.samples) {
      const id = sampleId(session.sessionId, sample.turn, sample.step)
      if (state.seen.has(id)) continue
      state.seen.add(id)
      if (baseline) continue
      fresh.push({ session, sample })
    }
  }
  state.baseline = false

  // Oldest first, with a deterministic tie-break so a reader can rely on order
  // even when several calls share a millisecond.
  fresh.sort(
    (left, right) =>
      left.sample.at - right.sample.at ||
      (left.session.sessionId < right.session.sessionId ? -1 : left.session.sessionId > right.session.sessionId ? 1 : 0) ||
      left.sample.turn - right.sample.turn ||
      left.sample.step - right.sample.step,
  )

  // ---- reaction signals (additive; REACTIONS-SPEC §5.2 option B) ------------
  // The engine is the only reader of the session logs, so the pet's reaction
  // layer never re-folds them: the engine passes the compact facts through as
  // new NDJSON lines and as `pet/renderer/signals.json`.
  const reaction = activity.signals ?? { tool: null, turn: null, lastUserAt: 0, lastUserText: null, streaming: { active: false, at: 0 }, lastBusyAt: 0 }
  if (reaction.tool !== null && reaction.tool !== undefined) {
    const toolKey = `${reaction.tool.name}|${reaction.tool.at}|${reaction.tool.phase}`
    if (!state.reported.has(toolKey)) {
      state.reported.add(toolKey)
      emit({
        type: 'tool',
        at: reaction.tool.at,
        session: reaction.tool.session ?? null,
        name: reaction.tool.name,
        tool: reaction.tool.name,
        phase: reaction.tool.phase,
        ok: reaction.tool.ok,
        error: reaction.tool.error,
      })
    }
  }
  if (reaction.turn !== null && reaction.turn !== undefined) {
    const turnKey = `turn|${reaction.turn.phase}|${reaction.turn.at}`
    if (!state.reported.has(turnKey)) {
      state.reported.add(turnKey)
      emit({
        type: 'turn',
        at: reaction.turn.at,
        session: null,
        phase: reaction.turn.phase,
        reason: reaction.turn.reason,
        ms: reaction.turn.ms,
        tokens: reaction.turn.tokens,
      })
    }
  }
  // `idleMs` is how long nothing has happened at all: no event, no user message,
  // no open step. The reaction layer's idle brain keys off it.
  const lastBusy = Math.max(reaction.lastBusyAt ?? 0, state.pet.lastEventAt ?? 0)
  const signalsDoc = {
    at,
    tool: reaction.tool === null || reaction.tool === undefined
      ? null
      : { ...reaction.tool, state: toolActivity(reaction.tool.name) },
    lastError: reaction.lastError ?? null,
    turn: reaction.turn ?? null,
    streaming: reaction.streaming ?? { active: false, at: 0 },
    lastUserAt: reaction.lastUserAt ?? 0,
    lastUserText: reaction.lastUserText ?? null,
    idleMs: lastBusy > 0 ? Math.max(0, at - lastBusy) : 0,
    agents: (activity.agents ?? []).filter((a) => a.state === 'running' || a.state === 'busy').length,
    jobs: (activity.jobs ?? []).length,
  }

  // The pet's state line: folded from this poll's own snapshot, then published
  // twice — as the additive `pet` key on the snapshot, and as the state file the
  // renderer page polls. The events this poll is about to emit are counted
  // first (the engine is the only writer of `event` lines, so it owns
  // `lastEventAt`); the snapshot/event order on the wire is unchanged.
  const snapshot = snapshotOf(dashboard, at, config.usdToCny, balance, activity)
  // `state.pet` is created by `createState()`; the fallback keeps a hand-built
  // state object (a caller of this exported `poll`) from breaking the fold.
  if (state.pet === undefined) state.pet = createPetTracker()
  const pet = computePet(state.pet, snapshot, at, fresh, { signals: { ...signalsDoc, snapshot } })
  snapshot.pet = pet
  emit(snapshot)
  const published = writePetState(pet)
  if (!published.ok && published.error !== undefined) {
    const key = `pet-state:${published.error}`
    if (!state.reported.has(key)) {
      state.reported.add(key)
      emit({ type: 'error', at: Date.now(), message: `pet state file: ${published.error}` })
    }
  }
  const signalsWritten = writeSignals(signalsDoc)
  if (!signalsWritten.ok && signalsWritten.error !== undefined) {
    const key = `pet-signals:${signalsWritten.error}`
    if (!state.reported.has(key)) {
      state.reported.add(key)
      emit({ type: 'error', at: Date.now(), message: `pet signals file: ${signalsWritten.error}` })
    }
  }

  for (const { session, sample } of fresh) {
    emit(eventOf(session, sample, config.usdToCny))
  }
}

/**
 * Entry point: parse, announce, and either poll once or poll forever.
 *
 * @returns {Promise<void>}
 */
async function main() {
  const args = parseArgs(process.argv.slice(2))
  const configPath = resolveConfigPath(args.configPath)
  const { config, error } = await loadConfig(configPath)
  const emit = createEmitter(process.stdout)
  const state = createState()

  emit({ type: 'ready', at: Date.now(), pollMs: config.pollMs, usdToCny: config.usdToCny })
  if (error !== undefined) emit({ type: 'error', at: Date.now(), message: `config: ${error}` })

  if (args.once) {
    await poll({ config, state, emit })
    return
  }

  /** @type {NodeJS.Timeout | undefined} */
  let timer
  let stopped = false
  const stop = () => {
    stopped = true
    if (timer !== undefined) clearTimeout(timer)
  }
  process.on('SIGINT', stop)
  process.on('SIGTERM', stop)
  process.stdout.on('error', (streamError) => {
    stop()
    if (streamError.code !== 'EPIPE') process.exitCode = 1
  })

  const tick = async () => {
    timer = undefined
    await poll({ config, state, emit })
    if (stopped) return
    // setTimeout chaining, never setInterval: a fold slower than `pollMs`
    // delays the next poll instead of queueing a second one behind it.
    timer = setTimeout(() => {
      void tick()
    }, config.pollMs)
  }

  await tick()
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))

if (invokedDirectly) {
  main().catch((error) => {
    const message = error instanceof Error ? error.message : String(error)
    try {
      process.stdout.write(`${JSON.stringify({ type: 'error', at: Date.now(), message })}\n`)
    } catch {
      // Nothing else to do: the stream itself is gone.
    }
    process.exitCode = 1
  })
}
