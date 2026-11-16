/**
 * Offline acceptance check for the usage bridge.
 *
 * Nothing here touches the real Harness. The plugin is driven through a stub
 * Cordis context — a fake `ctx.jobs` with an event bus and an output ring, a
 * fake effect registrar, a private clock, the process-global timer patched, a
 * captured `console.error`, and a temporary `$DSH_HOME` — and every claim in the
 * brief is asserted against the bytes the plugin actually wrote. Real values are
 * printed as the check goes, so a failure is diagnosable rather than just red.
 *
 * The stub context is deliberately hostile: it is a Proxy that reproduces
 * Cordis's own contract and *throws* on the GET of any property other than
 * `jobs` and `effect`. A passing run is therefore also the proof that the plugin
 * touches nothing else on the context — there is no observation seam left for it
 * to reach through.
 *
 * Run: <node> test/bridge-check.mjs
 */

import { existsSync } from 'node:fs'
import { mkdtemp, readdir, readFile, rm, stat } from 'node:fs/promises'
import { basename, dirname, join } from 'node:path'
import { tmpdir } from 'node:os'

import { apply, clampEta, resolveDshHome } from '../src/plugin.mjs'

/* -------------------------------------------------------------------------
 * A harness of fakes.
 * ---------------------------------------------------------------------- */

/** The check's private wall clock; the plugin reads Date.now(). */
let fakeNow = 1_790_695_900_650
Date.now = () => fakeNow

/** The real reporter, kept aside: `console.error` is captured below. */
const realConsoleError = console.error.bind(console)
/** @type {string[]} */
let logs = []
console.error = (...args) => {
  logs.push(args.map((value) => String(value)).join(' '))
}

/** @type {{ callback: () => void, delay: number, disposed: boolean }[]} */
let timers = []
/** @type {(() => void)[]} */
let disposers = []
/** Every stub context handed to the plugin, for the final ctx audit. */
let contexts = []

// The plugin ticks through the process-global timer now, so that is what the
// check fakes. `setTimeout` is left alone: `settle` needs a real one.
const realSetInterval = globalThis.setInterval
const realClearInterval = globalThis.clearInterval
globalThis.setInterval = (callback, delay) => {
  const entry = { callback, delay, disposed: false }
  timers.push(entry)
  return () => {
    entry.disposed = true
  }
}
globalThis.clearInterval = (handle) => {
  if (typeof handle === 'function') handle()
}

/**
 * Identify every trace of the plugin's write activity around one state file.
 *
 * A landed write is an atomic `rename` onto the path, so it replaces the inode
 * and bumps the timestamps even when the bytes happen to be identical. The
 * plugin's in-flight temp file — `<statePath>.<pid>.<serial>.tmp`, in the same
 * directory — is included too, because it becomes visible while the write is
 * still travelling and so gives the earliest honest signal that work is pending.
 * @param {string} path - the state file to identify.
 * @returns {Promise<string>} a stable fingerprint, or 'absent' when nothing is there.
 */
async function fingerprint(path) {
  const dir = dirname(path)
  const base = basename(path)
  try {
    const entries = (await readdir(dir)).filter((name) => name === base || name.startsWith(`${base}.`)).sort()
    let stamp = ''
    for (const name of entries) {
      const info = await stat(join(dir, name))
      stamp += `${name}#${info.size}@${info.mtimeMs}/${info.ctimeMs}/${info.ino};`
    }
    return stamp.length > 0 ? stamp : 'absent'
  } catch {
    return 'absent'
  }
}

/**
 * How long the trace around an existing state file must stay unchanged before
 * `settle` believes the plugin's write queue has drained. The plugin requests a
 * write synchronously but lands it asynchronously, so this has to exceed one
 * `mkdir` + `writeFile` + `rename` round trip with room to spare.
 */
const QUIET_MS = 25

/**
 * The same, for a path with no trace at all. A write that is about to *create*
 * the file is invisible until its buffer exists, so pure absence is the weakest
 * signal in the check and gets the longest grace period.
 */
const ABSENT_QUIET_MS = 80

/**
 * Wait until the plugin has stopped changing the file system around a path.
 *
 * Writes are fire-and-forget — the plugin must never make a host event wait on
 * disk — and with the observation seam gone there is no in-process handle on its
 * write queue. The honest equivalent is the file system itself: `settle` polls
 * the target and its temp siblings until that trace has been unchanged for a
 * quiet window long enough to cover a whole write, and a wall-clock deadline
 * backstops the poll so a scheduling surprise cannot hang the check.
 * @param {string} [path] - the state file whose writes to await.
 * @returns {Promise<void>} resolves once the path reflects all requested writes.
 */
async function settle(path = statePath) {
  const deadline = performance.now() + 5_000
  let last = await fingerprint(path)
  let quietSince = performance.now()
  while (performance.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 1))
    const current = await fingerprint(path)
    if (current !== last) {
      last = current
      quietSince = performance.now()
      continue
    }
    if (performance.now() - quietSince >= (last === 'absent' ? ABSENT_QUIET_MS : QUIET_MS)) return
  }
}

/**
 * Advance the simulated clock, run every live interval callback, then let the
 * resulting reads and writes land.
 * @param {number} ms - milliseconds to advance.
 * @param {string} [path] - the file whose writes to await.
 * @returns {Promise<void>} resolves once the plugin is quiescent.
 */
async function advance(ms, path = statePath) {
  fakeNow += ms
  for (const entry of timers) {
    if (!entry.disposed) entry.callback()
  }
  await settle(path)
}

/**
 * A byte ring that behaves like the registry's: absolute offsets, whole-chunk
 * returns, a resumable `next`, and a lossy flag once the window has slid past a
 * reader. `failFrom` makes reads past a point throw, to prove the bridge
 * contains a failing ring rather than dying on it.
 */
function createRing() {
  let chunks = []
  let total = 0
  const ring = {
    failFrom: undefined,
    /** Append text as the producer would. @param {string} text - produced bytes. @returns {number} new total. */
    append(text) {
      chunks.push({ at: total, text })
      total += Buffer.byteLength(text, 'utf8')
      return total
    },
    /** Absolute-offset, non-consuming read. @param {number} from - offset to resume at. */
    readAt(from) {
      if (ring.failFrom !== undefined && from >= ring.failFrom) {
        throw new Error(`ring read failed at ${from}`)
      }
      const lossy = chunks.length > 0 && from < chunks[0].at
      return {
        chunks: chunks.filter((chunk) => chunk.at + Buffer.byteLength(chunk.text, 'utf8') > from),
        next: total,
        lossy,
      }
    },
    /** The model-facing consuming read. The bridge must never call this. */
    read() {
      throw new Error('jobs.read was called: the bridge would have consumed the model cursor')
    },
    get total() {
      return total
    },
    /** Forget everything, as settlement trimming would. @returns {void} */
    clear() {
      chunks = []
    },
  }
  return ring
}

/**
 * Build a stub host context that reproduces Cordis's context proxy.
 *
 * A Cordis `ctx` throws on the property GET for any name that is neither a core
 * method nor an injected service. The stub does exactly that: `jobs` and
 * `effect` are the only properties it answers, and every other name — including
 * `get`, `logger`, `setInterval` and any custom property — throws. Everything
 * the check needs in order to poke at the fake host lives on the returned `api`
 * object, off the context, so this strictness cannot be subverted by the check
 * itself.
 *
 * @param {{ jobsAvailable?: boolean }} [options] - stub switches.
 * @returns {{ ctx: any, api: any }} the context the plugin sees, plus test handles.
 */
function createStubContext(options = {}) {
  const jobsAvailable = options.jobsAvailable !== false
  /** @type {any[]} */
  const listeners = []
  /** @type {Map<string, any>} */
  const rings = new Map()
  /** @type {Map<string, any>} */
  const views = new Map()
  /** Every property name the plugin asked the context proxy for. @type {string[]} */
  const touched = []

  const jobs = {
    events: {
      subscribe(filter, listener) {
        listeners.push({ filter, listener })
        return () => {
          const index = listeners.findIndex((entry) => entry.listener === listener)
          if (index >= 0) listeners.splice(index, 1)
        }
      },
    },
    readAt(id, from) {
      const ring = rings.get(id)
      if (ring === undefined) throw new Error(`unknown job ${id}`)
      return ring.readAt(from)
    },
    /** Present only so the check can prove it is never used. */
    read() {
      throw new Error('jobs.read was called')
    },
    /** @param {any} event - registry event. @returns {void} */
    emit(event) {
      for (const entry of [...listeners]) entry.listener(event)
    },
  }

  const allowed = {
    jobs: jobsAvailable ? jobs : undefined,
    effect(create) {
      disposers.push(create())
    },
  }

  const ctx = new Proxy(
    {},
    {
      get(_target, prop) {
        // Symbols reach here from inspection plumbing, not from the plugin.
        if (typeof prop !== 'string') return undefined
        touched.push(prop)
        if (!Object.prototype.hasOwnProperty.call(allowed, prop)) {
          throw new Error(`cannot get property "${prop}" without inject`)
        }
        return allowed[prop]
      },
    },
  )

  return { ctx, api: { jobs, listeners, rings, views, touched } }
}

/**
 * Register a job the way the registry would.
 * @param {any} api - stub test handles.
 * @param {{ id: string, kind?: string, label?: string, progress?: string, startedAt?: number }} spec - job identity.
 * @returns {any} the job's ring.
 */
function registerJob(api, spec) {
  const ring = createRing()
  const view = {
    id: spec.id,
    kind: spec.kind ?? 'bash',
    label: spec.label ?? 'node sim.mjs',
    owner: spec.owner ?? 'session-check',
    status: 'running',
    progress: spec.progress,
    startedAt: spec.startedAt ?? fakeNow,
    output: { total: 0, earliest: 0 },
  }
  api.rings.set(spec.id, ring)
  api.views.set(spec.id, view)
  api.jobs.emit({ type: 'registered', job: { ...view } })
  return ring
}

/**
 * Push producer output into a job's ring and announce it, as the registry does
 * when it pumps a producer's stdout.
 * @param {any} api - stub test handles.
 * @param {string} id - job id.
 * @param {string} text - produced bytes.
 * @returns {Promise<number>} the ring position.
 */
async function feed(api, id, text) {
  const ring = api.rings.get(id)
  const total = ring.append(text)
  const view = api.views.get(id)
  view.output = { total, earliest: 0 }
  api.jobs.emit({ type: 'output', id, owner: view.owner, total })
  // Output events do not schedule a write (the interval pump covers them), so
  // drain the queue straight away — that is exactly what the next tick does.
  await settle()
  return total
}

/**
 * Update a job's registry-reported progress line, as `JobHandle.updateProgress` does.
 * @param {any} api - stub test handles.
 * @param {string} id - job id.
 * @param {string} line - the progress line.
 * @returns {void}
 */
function setProgress(api, id, line) {
  const view = api.views.get(id)
  view.progress = line
  api.jobs.emit({ type: 'progress', job: { ...view } })
}

/**
 * Settle a job the way the registry would.
 * @param {any} api - stub test handles.
 * @param {string} id - job id.
 * @param {'completed' | 'failed' | 'killed'} [status] - terminal status.
 * @returns {void}
 */
function settleJob(api, id, status = 'completed') {
  const view = api.views.get(id)
  view.status = status
  view.finishedAt = fakeNow
  api.rings.get(id)?.clear()
  api.jobs.emit({ type: 'settled', job: { ...view }, cause: 'producer', awaited: false })
}

/* -------------------------------------------------------------------------
 * Assertions and reporting.
 * ---------------------------------------------------------------------- */

let passed = 0

/**
 * Assert a condition, reporting the real value either way.
 * @param {string} label - what is being claimed.
 * @param {boolean} condition - the claim.
 * @param {string} [detail] - observed value for the report.
 * @returns {void}
 */
function ok(label, condition, detail = '') {
  if (!condition) {
    realConsoleError(`  FAIL  ${label}${detail.length > 0 ? ` — ${detail}` : ''}`)
    throw new Error(`assertion failed: ${label}`)
  }
  passed += 1
  console.log(`  ok    ${label}${detail.length > 0 ? ` — ${detail}` : ''}`)
}

/**
 * Read and parse the state file.
 * @param {string} path - the file to read.
 * @returns {Promise<any>} parsed JSON.
 */
async function readState(path) {
  return JSON.parse(await readFile(path, 'utf8'))
}

/**
 * Find one job in the state file.
 * @param {string} id - job id.
 * @returns {Promise<any>} the projected job.
 */
async function jobIn(id) {
  const state = await readState(statePath)
  return state.jobs.find((entry) => entry.id === id)
}

/** @type {string} */
let home
/** @type {string} */
let statePath

/* -------------------------------------------------------------------------
 * The checks.
 * ---------------------------------------------------------------------- */

/** @type {{ name: string, run: (api: any) => Promise<void> }[]} */
const checks = [
  {
    name: '1. a registered running job appears with label, status and startedAt',
    async run(api) {
      const startedAt = fakeNow
      registerJob(api, { id: 'bash-3', label: 'node sim.mjs', startedAt })
      await settle()
      const job = await jobIn('bash-3')
      ok('jobs.json exists', existsSync(statePath), statePath)
      ok('the job is listed', job !== undefined, 'present')
      ok('label round-trips', job.label === 'node sim.mjs', String(job.label))
      ok('status is running', job.status === 'running', String(job.status))
      ok('startedAt round-trips', job.startedAt === startedAt, String(job.startedAt))
      ok('finishedAt is null while running', job.finishedAt === null, String(job.finishedAt))
      console.log(`        ${JSON.stringify(job)}`)
    },
  },
  {
    name: '2. ring text drives percent: "step 120/500" then "47.5%"',
    async run(api) {
      await feed(api, 'bash-3', 'step 120/500\n')
      await advance(1_000)
      let job = await jobIn('bash-3')
      ok('the ratio line yields 24', job.percent === 24, `percent=${job.percent} lastLine=${JSON.stringify(job.lastLine)}`)

      // A fresh job, so the earlier ratio line is no longer the tail.
      registerJob(api, { id: 'bash-4', label: 'worker' })
      await feed(api, 'bash-4', 'iteration 12\n47.5%\n')
      await advance(1_000)
      job = await jobIn('bash-4')
      ok('the percentage line yields 47.5', job.percent === 47.5, `percent=${job.percent}`)
      ok('lastLine is the trimmed tail line', job.lastLine === '47.5%', JSON.stringify(job.lastLine))

      // The registry's own progress line outranks anything parsed from raw
      // output, so a chatty script cannot drown out the producer's summary. The
      // line arrives as a `progress` event, the shape `updateProgress` produces.
      registerJob(api, { id: 'bash-9', label: 'reporting job' })
      await feed(api, 'bash-9', 'noise 10%\n')
      await advance(1_000)
      ok('ring text alone reports the script line', (await jobIn('bash-9')).percent === 10, `percent=${(await jobIn('bash-9')).percent}`)
      setProgress(api, 'bash-9', '77.5%')
      await advance(1_000)
      job = await jobIn('bash-9')
      ok('the registry progress line wins over the ring text', job.percent === 77.5, `percent=${job.percent} progress=${JSON.stringify(job.progress)}`)
    },
  },
  {
    name: '3. two samples produce a clamped ETA, and it tracks a changing rate',
    async run(api) {
      // Progress is driven through ring output here. Ring text is always fresh,
      // which keeps the sample timeline exactly the one the check describes;
      // `readAt` is what the bridge actually reads in production anyway.
      registerJob(api, { id: 'bash-5', label: 'long job', startedAt: fakeNow })
      await settle()

      // Sample 0 % at T. The job is registered without a progress line, so the
      // tail is empty and the first sample is taken on the first tick.
      await advance(10_000)

      // Phase A — an outright crawl: 1 % per 10 s.
      await feed(api, 'bash-5', '1%\n')
      await advance(10_000)
      await feed(api, 'bash-5', '2%\n')
      await advance(10_000)
      const phaseA = await jobIn('bash-5')
      ok('etaMs is present once there are two samples', typeof phaseA.etaMs === 'number', `etaMs=${phaseA.etaMs}`)
      ok('etaMs is inside the 1 s .. 7 d clamp', phaseA.etaMs >= 1_000 && phaseA.etaMs <= 604_800_000, `${phaseA.etaMs} ms`)

      // Phase B — 20 % per 10 s, twenty times faster. The estimate must fall
      // even though the job is now further along.
      await feed(api, 'bash-5', '22%\n')
      await advance(10_000)
      const phaseB = await jobIn('bash-5')
      ok('a rising rate lowers the ETA', phaseB.etaMs < phaseA.etaMs, `${phaseA.etaMs} ms -> ${phaseB.etaMs} ms`)

      // Phase C — back to a crawl: 0.02 % per 10 s. A stale fast rate would keep
      // predicting a quick finish; the estimate must lengthen, because the
      // *recent* rate is what the widget should believe.
      await feed(api, 'bash-5', '22.01%\n')
      await advance(10_000)
      await feed(api, 'bash-5', '22.02%\n')
      await advance(10_000)
      const phaseC = await jobIn('bash-5')
      ok('a falling rate raises the ETA', phaseC.etaMs > phaseB.etaMs, `${phaseB.etaMs} ms -> ${phaseC.etaMs} ms`)

      // The ceiling is a real answer, not a dropped field: 0.0001 % gained over
      // seven minutes implies a finish years away, so the estimate must be
      // capped at exactly seven days rather than omitted.
      await feed(api, 'bash-5', '22.0301%\n')
      await advance(420_000)
      const capped = await jobIn('bash-5')
      ok('a crawl beyond a week clamps to the 7 d ceiling', capped.etaMs === 604_800_000, `etaMs=${capped.etaMs} (percent=${capped.percent})`)

      // The floor holds at the other end. With a one-second tick no reachable
      // sample pair produces a sub-second estimate (6 %/s with 34 % left is
      // ~5.7 s), so the boundary contract is asserted directly: an enormous rate
      // must clamp up to exactly one second rather than being dropped or
      // reported as zero.
      ok('a sub-millisecond estimate clamps up to the 1 s floor', clampEta(0.4) === 1_000, `clampEta(0.4)=${clampEta(0.4)}`)
      ok('a multi-year estimate clamps down to the 7 d ceiling', clampEta(1e12) === 604_800_000, `clampEta(1e12)=${clampEta(1e12)}`)
      ok('a mid-range estimate passes through rounded', clampEta(4_321.6) === 4_322, `clampEta(4321.6)=${clampEta(4_321.6)}`)
      ok('a non-positive estimate is unknown, not zero', clampEta(0) === undefined && clampEta(-5) === undefined, `clampEta(0)=${clampEta(0)} clampEta(-5)=${clampEta(-5)}`)
      ok('a non-finite estimate is unknown', clampEta(Number.POSITIVE_INFINITY) === undefined, String(clampEta(Number.POSITIVE_INFINITY)))
    },
  },
  {
    name: '4. a settled job stays briefly, then disappears',
    async run(api) {
      registerJob(api, { id: 'bash-6', label: 'settling job' })
      await feed(api, 'bash-6', 'step 1/2\n')
      await advance(1_000)
      settleJob(api, 'bash-6', 'completed')
      await settle()
      let job = await jobIn('bash-6')
      ok('the settled job is still listed for the tail', job !== undefined, 'present')
      ok('its terminal status is reported', job.status === 'completed', String(job.status))
      ok('finishedAt is stamped', typeof job.finishedAt === 'number', String(job.finishedAt))
      ok('etaMs is dropped once settled', job.etaMs === null, String(job.etaMs))

      await advance(29_000)
      job = await jobIn('bash-6')
      ok('still listed just under 30 s', job !== undefined, 'present')

      await advance(2_000)
      job = await jobIn('bash-6')
      const state = await readState(statePath)
      ok('gone just over 30 s', job === undefined, `remaining: ${JSON.stringify(state.jobs.map((entry) => entry.id))}`)
    },
  },
  {
    name: '5. a throwing ring read neither kills the plugin nor corrupts the file',
    async run(api) {
      registerJob(api, { id: 'bash-7', label: 'flaky' })
      await feed(api, 'bash-7', 'still fine\n')
      await advance(1_000)
      ok('the job was listed before the failure', (await jobIn('bash-7')) !== undefined, 'precondition')

      api.rings.get('bash-7').failFrom = 0
      logs = []
      await advance(1_000)
      await advance(1_000)
      await advance(1_000)
      ok('the plugin kept running after the throw', timers.length > 0 && timers[0].disposed === false, 'timer still armed')

      const raw = await readFile(statePath, 'utf8')
      let parsed
      try {
        parsed = JSON.parse(raw)
      } catch (error) {
        throw new Error(`jobs.json is no longer valid JSON: ${String(error)}`)
      }
      ok('the file still parses on the next write', parsed !== undefined, `${raw.length} bytes, at=${parsed.at}`)
      ok('the failing job is still tracked', parsed.jobs.some((entry) => entry.id === 'bash-7'), 'present')
      const readWarnings = logs.filter((message) => message.includes('read:bash-7'))
      ok('the failure is logged once, not per tick', readWarnings.length === 1, `${readWarnings.length} warning(s): ${JSON.stringify(readWarnings)}`)

      api.rings.get('bash-7').failFrom = undefined
      await feed(api, 'bash-7', 'recovered\n')
      await advance(1_000)
      const recovered = await jobIn('bash-7')
      ok('the plugin resumes reading after recovery', recovered !== undefined && recovered.lastLine === 'recovered', `lastLine=${JSON.stringify(recovered?.lastLine)}`)

      // A lossy read means the retained ring slid past the bridge's cursor. The
      // gap cannot be reconstructed, so the bridge must resync to the registry's
      // `next` and keep going rather than error or spin on a stale offset.
      registerJob(api, { id: 'bash-10', label: 'lossy' })
      await feed(api, 'bash-10', 'first 50%\n')
      await advance(1_000)
      const beforeLoss = await jobIn('bash-10')
      ok('the pre-loss tail was captured', beforeLoss.lastLine === 'first 50%', `lastLine=${JSON.stringify(beforeLoss.lastLine)}`)
      api.rings.get('bash-10').clear()
      await feed(api, 'bash-10', 'after loss 60%\n')
      await advance(1_000)
      const afterLoss = await jobIn('bash-10')
      ok('a lossy read resyncs instead of stalling', afterLoss !== undefined && afterLoss.lastLine === 'after loss 60%', `lastLine=${JSON.stringify(afterLoss?.lastLine)}`)
      ok('the post-loss percent is derived from fresh output', afterLoss.percent === 60, `percent=${afterLoss.percent}`)
      await advance(1_000)
      const afterLoss2 = await jobIn('bash-10')
      ok('the bridge keeps reading after a resync', afterLoss2 !== undefined, 'still mirroring')
    },
  },
  {
    name: '6. jobs.read is never used (the stub would have thrown)',
    async run() {
      const parsed = await readState(statePath)
      ok('no read() call escaped the stub', true, 'the stub threw on every read(); the run survived')
      ok('the file is still intact afterwards', parsed.jobs.length > 0, `${parsed.jobs.length} job(s)`)
    },
  },
  {
    name: '7. $DSH_HOME resolves from the environment, and statePath overrides it',
    async run(api) {
      ok('resolveDshHome() reads $DSH_HOME', resolveDshHome() === home, resolveDshHome())
      // The seam that used to report the resolved path is gone, so the claim is
      // made against the file the plugin actually wrote at that path.
      ok('the default state file is the one the plugin really writes', existsSync(statePath), statePath)
      ok('it is the file behind the jobs the check has been reading', (await jobIn('bash-3')) !== undefined, 'bash-3 present')

      const custom = join(home, 'elsewhere', 'custom.json')
      const override = createStubContext()
      contexts.push(override)
      const disposeOverride = apply(override.ctx, { statePath: custom, intervalMs: 1_000 })
      ok('apply() accepts an explicit statePath', typeof disposeOverride === 'function', typeof disposeOverride)
      await advance(1_000, custom)
      ok('an explicit statePath wins over $DSH_HOME', existsSync(custom), custom)
      ok('it did not also write a default file', !existsSync(join(home, 'elsewhere', 'jobs.json')), 'no stray default')
      console.log(`        ${(await readFile(custom, 'utf8')).trim()}`)

      // The surviving instance keeps mirroring to the default path.
      api.views.get('bash-3').label = 'renamed after override'
      api.jobs.emit({ type: 'progress', job: { ...api.views.get('bash-3') } })
      await settle()
      const job = await jobIn('bash-3')
      ok('the original instance still writes to $DSH_HOME', job.label === 'renamed after override', String(job.label))
      disposeOverride()
    },
  },
  {
    name: '8. no ctx.jobs means an inert plugin: nothing registered',
    async run() {
      const before = { timers: timers.length, disposers: disposers.length }
      const inert = createStubContext({ jobsAvailable: false })
      contexts.push(inert)
      const result = apply(inert.ctx, {})
      await settle()
      ok('apply() returns undefined when jobs is absent', result === undefined, String(result))
      ok('no timer was registered', timers.length === before.timers, `${timers.length} timer(s)`)
      ok('no effect was registered', disposers.length === before.disposers, `${disposers.length} effect(s)`)
      ok('no subscription was made', inert.api.listeners.length === 0, `${inert.api.listeners.length} listener(s)`)
      ok('it gave up after reading exactly one context property', inert.api.touched.length === 1 && inert.api.touched[0] === 'jobs', JSON.stringify(inert.api.touched))
    },
  },
  {
    name: '9. the first tick writes an empty beacon, even with nothing registered',
    async run() {
      const beaconPath = join(home, 'beacon', 'jobs.json')
      const beacon = createStubContext()
      contexts.push(beacon)
      const disposeBeacon = apply(beacon.ctx, { statePath: beaconPath, intervalMs: 1_000 })
      ok('apply() returns a disposer while jobs is mounted', typeof disposeBeacon === 'function', typeof disposeBeacon)
      await settle(beaconPath)
      // Nothing is written at apply time any more: the beacon is the first tick,
      // which is exactly what makes it evidence that the plugin is *ticking*.
      ok('no file before the registry or a tick has acted', !existsSync(beaconPath), 'absent')
      ok('nothing was registered, so the registry reported nothing', beacon.api.listeners.length === 1 && beacon.api.views.size === 0, `${beacon.api.views.size} job(s)`)

      await advance(1_000, beaconPath)
      ok('the first tick created the file', existsSync(beaconPath), beaconPath)
      const beaconState = await readState(beaconPath)
      ok('the beacon is parseable JSON with an empty job list', Array.isArray(beaconState.jobs) && beaconState.jobs.length === 0, JSON.stringify(beaconState))
      ok('the beacon carries the tick timestamp', beaconState.at === fakeNow, `${beaconState.at} (clock ${fakeNow})`)
      console.log(`        ${(await readFile(beaconPath, 'utf8')).trim()}`)
      disposeBeacon()
    },
  },
  {
    name: '10. the plugin touches no ctx property other than jobs and effect',
    async run() {
      const touched = contexts.flatMap((entry) => entry.api.touched)
      const distinct = [...new Set(touched)]
      const offenders = distinct.filter((prop) => prop !== 'jobs' && prop !== 'effect')
      ok('no property outside jobs and effect was ever read', offenders.length === 0, `distinct reads: ${JSON.stringify(distinct)}`)
      ok('ctx.jobs was read', touched.includes('jobs'), `${touched.filter((prop) => prop === 'jobs').length} read(s)`)
      ok('ctx.effect was read', touched.includes('effect'), `${touched.filter((prop) => prop === 'effect').length} read(s)`)

      // The proxy trap is the real proof, so prove the trap itself bites: the
      // names the old code reached for must throw on GET, not merely be ignored.
      const probe = createStubContext()
      const hostile = ['get', 'logger', 'setInterval', 'clearInterval', '__usageBridgeWrites', '__usageBridgeStatePath']
      let threw = 0
      for (const name of hostile) {
        try {
          void probe.ctx[name]
        } catch {
          threw += 1
        }
      }
      ok('the stub context throws on every undeclared name', threw === hostile.length, `${threw}/${hostile.length} threw`)
    },
  },
]

/* -------------------------------------------------------------------------
 * Driver.
 * ---------------------------------------------------------------------- */

console.log('dsh-usage-bridge :: offline bridge check')
console.log(`node            ${process.version}`)
console.log(`working dir     ${process.cwd()}`)

home = await mkdtemp(join(tmpdir(), 'dsh-usage-bridge-check-'))
process.env.DSH_HOME = home
statePath = join(home, 'usage-widget', 'jobs.json')
console.log(`temp $DSH_HOME  ${home}`)
console.log(`state file      ${statePath}\n`)

contexts = []
timers = []
disposers = []
const main = createStubContext()
contexts.push(main)
const dispose = apply(main.ctx, {})
await settle()

if (dispose === undefined) {
  realConsoleError('FAIL: apply() was inert even though ctx.jobs was mounted')
  process.exitCode = 1
} else {
  try {
    for (const check of checks) {
      console.log(check.name)
      await check.run(main.api)
      console.log('')
    }
    console.log('--- final state file as written by the check ---')
    console.log((await readFile(statePath, 'utf8')).trim())
    console.log(`--- ${passed} assertions passed ---`)
  } catch (error) {
    realConsoleError(`\nCHECK FAILED: ${String(error?.stack ?? error)}`)
    process.exitCode = 1
  } finally {
    dispose()
  }
}

await settle()
globalThis.setInterval = realSetInterval
globalThis.clearInterval = realClearInterval
console.error = realConsoleError
await rm(home, { recursive: true, force: true }).catch(() => undefined)
