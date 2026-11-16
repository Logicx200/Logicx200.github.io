/**
 * Real-Cordis integration test for the host half of the usage bridge.
 *
 * The package's own check (`test/bridge-check.mjs`) loads `src/plugin.mjs`
 * against a hand-written Proxy stub that reproduces Cordis' "throws on GET of
 * an unrecognised name" trap. That check cannot tell us whether the *real*
 * Cordis machinery accepts the plugin, because it is not Cordis: it does not
 * run a fiber, it does not resolve `inject`, and it does not report
 * `fiberPhase`.
 *
 * This test answers exactly one question — does `src/plugin.mjs` load and work
 * under a genuine Cordis context? It uses a real, unmodified build of
 * `@deepseek-ai/cordis` found on this machine, creates a real root context,
 * registers a real `jobs` service on it, loads the plugin through the same
 * `ctx.plugin(module, config)` call the Harness loader uses
 * (`cordis-plugin-loader/src/config/entry.ts`), drives it with one job event,
 * and inspects the resulting fiber state and JSON file.
 *
 * It writes nothing outside `test/` and a fresh OS temp directory used as
 * `DSH_HOME`. It does not install anything and does not touch any DSH profile.
 *
 * Run: `<node> test/real-cordis.test.mjs`
 */

import { existsSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { mkdtemp, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

/* ------------------------------------------------------------------ *
 * The real Cordis under test.
 *
 * Located per the brief: the npx cache carries a full, published copy of the
 * framework (`package.json` → `"main": "lib/index.js"`, `"type": "module"`),
 * so it is imported by absolute `file://` URL. Nothing in it is patched or
 * stubbed; `lib/index.js` is the shipped build.
 * ------------------------------------------------------------------ */

const CORDIS_URL = process.env.USAGE_BRIDGE_CORDIS_URL
  ?? 'file:///D:/Node.js/node_cache/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/cordis/lib/index.js'

/**
 * `FiberState` is a `const enum` in the Cordis source, so the shipped build
 * erases it and does not export it. These are the values from
 * `vendor/cordis/src/fiber.ts`, and they match the `FIBER_STATE` table that
 * `@deepseek-ai/dsh-host-plugin-inventory` uses to print `fiberPhase`.
 */
const FIBER_PHASE = {
  0: 'pending',
  1: 'loading',
  2: 'active',
  3: 'failed',
  4: 'disposed',
  5: 'unloading',
}
const ACTIVE = 2
const FAILED = 3

/* ------------------------------------------------------------------ *
 * Tiny assertion harness: every line below is real observed output.
 * ------------------------------------------------------------------ */

let passed = 0
let failed = 0

function check(label, ok, detail) {
  if (ok) {
    passed += 1
    console.log(`  PASS  ${label}`)
  } else {
    failed += 1
    console.log(`  FAIL  ${label}${detail === undefined ? '' : ` — ${detail}`}`)
  }
}

function section(title) {
  console.log(`\n=== ${title} ===`)
}

/** Render a thrown value the way a human needs to see it: the full stack. */
function renderError(error) {
  if (error instanceof Error) return error.stack ?? `${error.name}: ${error.message}`
  return `non-Error thrown: ${String(error)}`
}

/* ------------------------------------------------------------------ *
 * Step 1 — a fresh DSH_HOME, set before the plugin module is imported.
 * ------------------------------------------------------------------ */

const home = await mkdtemp(join(tmpdir(), 'usage-bridge-real-cordis-'))
process.env.DSH_HOME = home

section('environment')
console.log(`node          ${process.version}`)
console.log(`cordis url    ${CORDIS_URL}`)
const cordisRoot = dirname(dirname(fileURLToPath(CORDIS_URL)))
const cordisPkg = JSON.parse(await readFile(join(cordisRoot, 'package.json'), 'utf8'))
const entryPath = join(cordisRoot, cordisPkg.main ?? 'lib/index.js')
const entryBytes = await readFile(entryPath)
console.log(`cordis        ${cordisPkg.name}@${cordisPkg.version} (main ${cordisPkg.main})`)
console.log(`cordis entry  ${entryPath}`)
console.log(`cordis sha256 ${createHash('sha256').update(entryBytes).digest('hex')}`)
console.log(`DSH_HOME      ${home}   (fresh temp directory)`)
console.log(`plugin url    ${new URL('../src/plugin.mjs', import.meta.url).href}`)

const cordis = await import(CORDIS_URL)
const plugin = await import(new URL('../src/plugin.mjs', import.meta.url).href)

console.log(`cordis export Context=${typeof cordis.Context} Service=${typeof cordis.Service}`)
console.log(`plugin exports  ${Object.keys(plugin).join(', ')}`)
console.log(`plugin.name     ${JSON.stringify(plugin.name)}`)
console.log(`plugin.inject   ${JSON.stringify(plugin.inject)}`)

/* ------------------------------------------------------------------ *
 * Step 2 — a real root Cordis context, and a log exporter that keeps every
 * record the framework itself emits (so a startup failure cannot be missed).
 * ------------------------------------------------------------------ */

section('step 2: real root context')

const ctx = new cordis.Context()

// Level 3 = DEBUG, so nothing the framework logs is filtered out.
const emitted = []
ctx.logger.exporter({
  levels: { default: 3 },
  export(message) {
    emitted.push(message)
    const [first, ...rest] = message.args
    const text = first instanceof Error ? (first.stack ?? first.message) : String(first)
    console.log(`  [cordis ${message.type}] ${message.name}: ${text}${rest.length ? ' ' + rest.map(String).join(' ') : ''}`)
  },
})

check('root context is a genuine Cordis context (Context.is)', cordis.Context.is(ctx) === true)
check(`root fiber is active (state=${ctx.fiber.state}, ${FIBER_PHASE[ctx.fiber.state]})`, ctx.fiber.state === ACTIVE)

/* ------------------------------------------------------------------ *
 * Step 3 — the stub `jobs` service, registered as a real Cordis service.
 * ------------------------------------------------------------------ */

section('step 3: stub jobs service registered through ctx.provide()')

/** Ring contents per job id; `readAt` slices from the caller's own offset. */
const rings = new Map()
/** Every listener the plugin attached through `jobs.events.subscribe`. */
const listeners = new Set()
let readAtCalls = 0
let readCalls = 0

const jobsStub = {
  events: {
    /**
     * @param {{ owners: string }} filter - the plugin subscribes with `{ owners: 'all' }`.
     * @param {(event: any) => void} listener - the plugin's event sink.
     * @returns {() => void} unsubscribe.
     */
    subscribe(filter, listener) {
      if (typeof listener !== 'function') throw new TypeError('listener must be a function')
      listeners.add(listener)
      console.log(`  jobs.events.subscribe(${JSON.stringify(filter)}) -> listener attached`)
      return () => listeners.delete(listener)
    },
  },
  /** Non-consuming read; the plugin's own cursor is the `from` argument. */
  readAt(id, from) {
    readAtCalls += 1
    const ring = rings.get(String(id)) ?? ''
    const offset = Number.isFinite(from) && from >= 0 && from <= ring.length ? from : 0
    const text = ring.slice(offset)
    console.log(`  jobs.readAt(${JSON.stringify(String(id))}, ${offset}) -> ${JSON.stringify(text)}`)
    return { chunks: text.length ? [{ text }] : [], next: ring.length, lossy: false }
  },
  /** Advancing the model's own cursor would steal a running job's output. */
  read() {
    readCalls += 1
    throw new Error('jobs.read() must never be called: it would advance the model cursor')
  },
}

// `ctx.provide` is the mixed-in form of `ctx.reflect.provide(name, value)`.
const disposeJobs = ctx.provide('jobs', jobsStub)

check('ctx.get("jobs") returns the stub', ctx.get('jobs') === jobsStub)

// Proof that the stub is visible from inside a plugin's scoped context — a
// service on the root is only useful to the plugin if `inject` resolves it.
let seenByProbe = Symbol('not-run')
const probe = ctx.plugin({
  name: 'jobs-visibility-probe',
  inject: ['jobs'],
  apply(probeCtx) {
    seenByProbe = probeCtx.jobs
  },
})
await probe
check('a real Cordis plugin with inject:["jobs"] reads ctx.jobs as the stub', seenByProbe === jobsStub)

/* ------------------------------------------------------------------ *
 * Step 4 — load the plugin exactly the way the Harness loader does.
 *
 * `cordis-plugin-loader` first unwraps the module namespace (`unwrapExports`)
 * and then calls `ctx.registry.plugin(plugin, config, getOuterStack)` — that
 * is, the mixed-in `ctx.plugin(module, config)` — and keeps
 * `fiber = ....ctx.fiber` for `fiberPhase` reporting.
 * ------------------------------------------------------------------ */

section('step 4: ctx.plugin(module, config) — the loader call shape')

/** Mirrors `Loader.unwrapExports`. */
function unwrapExports(exports) {
  if (exports === null || exports === undefined) return exports
  exports = exports.default ?? exports
  if (!exports.__esModule) return exports
  return exports.default ?? exports
}

const config = { statePath: '', intervalMs: 1000 } // the cordis.patch.yml row
const fiber = ctx.plugin(unwrapExports(plugin), config)

let loadError
try {
  await fiber
} catch (error) {
  loadError = error
}

console.log(`\n  fiber.state        ${fiber.state} (${FIBER_PHASE[fiber.state]})`)
console.log(`  fiber.runtimeName  ${JSON.stringify(fiber.runtime?.name)}`)
console.log(`  fiber.inject       ${JSON.stringify(Object.keys(fiber.inject ?? {}))}`)
if (loadError) {
  console.log('  fiber.await() rejected with:')
  console.log(renderError(loadError).split('\n').map((line) => `    ${line}`).join('\n'))
}
if (fiber._error) {
  console.log('  fiber._error (the error the Cordis machinery recorded):')
  console.log(renderError(fiber._error).split('\n').map((line) => `    ${line}`).join('\n'))
}
if (!loadError && !fiber._error) console.log('  fiber.await() resolved; no startup error was recorded')

check(
  `plugin fiber reaches the active phase (state=${fiber.state}, ${FIBER_PHASE[fiber.state]})`,
  fiber.state === ACTIVE,
  loadError ? renderError(loadError) : `state=${fiber.state}`,
)
check('apply() subscribed to the registry events', listeners.size === 1, `listeners=${listeners.size}`)

/* ------------------------------------------------------------------ *
 * Step 5 — drive it: one `registered` job event whose ring carries "step 3/10",
 * then wait past a tick interval so the interval pump reads the ring.
 * ------------------------------------------------------------------ */

section('step 5: drive one job event and let the pump tick')

const JOB_ID = 'job-under-test'
rings.set(JOB_ID, 'booting\nstep 3/10\n')

// No `progress` field on purpose: the percent must come from the ring text,
// not from the registry's authoritative progress string.
const event = {
  type: 'registered',
  job: {
    id: JOB_ID,
    kind: 'pwsh',
    label: 'real-cordis integration test',
    owner: 'test',
    status: 'running',
    startedAt: Date.now(),
    finishedAt: null,
  },
}
console.log(`  emitting ${JSON.stringify(event)}`)
for (const listener of [...listeners]) listener(event)

const statePath = join(home, 'usage-widget', 'jobs.json')
console.log(`  waiting for ${statePath} to carry percent 30 (intervalMs=1000, write throttle) ...`)

let raw = null
let body = null
const deadline = Date.now() + 6000
while (Date.now() < deadline) {
  await new Promise((resolve) => setTimeout(resolve, 100))
  if (!existsSync(statePath)) continue
  raw = await readFile(statePath, 'utf8')
  try {
    body = JSON.parse(raw)
  } catch {
    body = null
  }
  if (body?.jobs?.some((job) => job.id === JOB_ID && job.percent === 30)) break
}
console.log(`  observed after ${6000 - (deadline - Date.now())}ms wait`)
if (raw !== null) console.log(`  jobs.json =\n${raw.trimEnd().split('\n').map((line) => `    ${line}`).join('\n')}`)
else console.log('  jobs.json was never created')

/* ------------------------------------------------------------------ *
 * Step 6 — assert the observable contract.
 * ------------------------------------------------------------------ */

section('step 6: assertions')

check('jobs.json exists under the temp DSH_HOME', raw !== null)
check('jobs.json parses as JSON', body !== null)

const record = body?.jobs?.find((job) => job.id === JOB_ID)
check('the job appears in the snapshot', record !== undefined)
check(`the job reports percent 30 (got ${JSON.stringify(record?.percent)})`, record?.percent === 30)
check(
  `the job reports a non-empty lastLine (got ${JSON.stringify(record?.lastLine)})`,
  typeof record?.lastLine === 'string' && record.lastLine.length > 0,
)
check(`the pump actually read the ring (readAt calls=${readAtCalls})`, readAtCalls > 0)
check(`jobs.read() was never called (calls=${readCalls})`, readCalls === 0)
check(
  'no "jobs.read()" complaint was logged',
  !emitted.some((message) => JSON.stringify(message.args ?? []).includes('must never be called')),
)
check(
  `the plugin survived the run (fiber state=${fiber.state}, ${FIBER_PHASE[fiber.state]})`,
  fiber.state === ACTIVE,
)

/* ------------------------------------------------------------------ *
 * Step 7 — the control: make real Cordis report a failure at least once.
 *
 * No copy of the *old* plugin implementation exists anywhere on this machine
 * (the only `plugin.mjs` on disk is the current fixed one — see the report),
 * so the previous failure mode is reproduced by loading minimal plugins that
 * perform exactly the context accesses the old implementation performed. Each
 * is a genuine Cordis plugin under the same real context, so whatever Cordis
 * reports here is the machinery's own verdict — including where it *does not*
 * fail, which is itself evidence about what the old code really tripped on.
 * ------------------------------------------------------------------ */

section('step 7: control — the removed accesses under the same real Cordis')

const legacyAccesses = [
  ['ctx.setInterval', (pluginCtx) => pluginCtx.setInterval(() => {}, 1000)],
  ['ctx.logger', (pluginCtx) => pluginCtx.logger],
  ['ctx.get', (pluginCtx) => pluginCtx.get],
  ['ctx.__usageBridgeState', (pluginCtx) => pluginCtx.__usageBridgeState],
]

const controlResults = []
for (const [label, body] of legacyAccesses) {
  const control = ctx.plugin({
    name: `legacy-access-control:${label}`,
    inject: [],
    apply(pluginCtx) {
      body(pluginCtx)
    },
  })
  let controlError
  try {
    await control
  } catch (error) {
    controlError = error
  }
  const message = controlError instanceof Error ? controlError.message : undefined
  console.log(`  ${label}: state=${control.state} (${FIBER_PHASE[control.state]})${message ? ` — ${message}` : ' — resolved, no error'}`)
  controlResults.push({ label, state: control.state, message })
  await control.dispose()
}

const setIntervalControl = controlResults.find((result) => result.label === 'ctx.setInterval')
check(
  'control ctx.setInterval fails under real Cordis (the proxy trap is real)',
  setIntervalControl?.state === FAILED
    && setIntervalControl.message === 'cannot get property "setInterval" without inject',
  `state=${setIntervalControl?.state} message=${JSON.stringify(setIntervalControl?.message)}`,
)
check(
  'control confirms ctx.logger / ctx.get / ctx.__usageBridge* do NOT trip the trap',
  ['ctx.logger', 'ctx.get', 'ctx.__usageBridgeState'].every(
    (label) => controlResults.find((result) => result.label === label)?.state === ACTIVE,
  ),
  controlResults.map((result) => `${result.label}=${FIBER_PHASE[result.state]}`).join(' '),
)

section('control reading')
console.log('  ctx.setInterval is undeclared, so the Cordis context proxy throws on the GET itself:')
console.log(`    ${setIntervalControl?.message ?? '(not observed)'}`)
console.log('  ctx.logger and ctx.get resolve because both are real context properties: `logger`')
console.log('  is a core service owned by the root Context, and `get` is a mixin accessor that')
console.log('  forwards to `ctx.reflect.get`. `__`-prefixed names never reach the trap either:')
console.log('  `ReflectService.handler` routes symbols, "prototype", "then", numeric strings and')
console.log('  `_`-prefixed names straight to Reflect.get (cordis/src/reflect.ts isSpecialProperty),')
console.log('  so `ctx.__usageBridge*` was inert rather than fatal. `ctx.setInterval` is therefore')
console.log('  the only removed access that could have put the old fiber in state 3 (failed).')

/* ------------------------------------------------------------------ *
 * Teardown and verdict.
 * ------------------------------------------------------------------ */

section('teardown')
await fiber.dispose()
check('disposing the plugin fiber removes the subscription', listeners.size === 0, `listeners=${listeners.size}`)
disposeJobs()

section('verdict')
console.log(`  ${passed} passed, ${failed} failed`)
console.log(`  evidence directory left in place: ${home}`)
console.log(`  src/plugin.mjs loads under real Cordis ${cordisPkg.name}@${cordisPkg.version}: ${failed === 0 ? 'YES' : 'NO'}`)
process.exitCode = failed === 0 ? 0 : 1
