/**
 * Checks for `pet/state-cli.mjs`'s pure harness pieces.
 *
 * Spawning the engine is deliberately *not* part of this test — it needs the
 * live host and belongs to the manual reality check. Everything here is pure:
 * argument parsing, the ASCII-cwd rule, and the NDJSON fold, including the
 * observations that produce `stale` and `running`.
 *
 * Run with the bundled Node:
 *   node pet\test\state-cli.test.mjs
 *
 * @module dsh-usage-widget/pet/test/state-cli
 */

import { isAbsolute } from 'node:path'

import { computeState } from '../state.mjs'
import { asciiCandidates, describeSource, foldEngineStream, parseArgs, resolveChildCwd } from '../state-cli.mjs'

const NOW = 1_790_700_000_000

let passed = 0
/** @type {string[]} */
const failures = []

/**
 * Record one named claim.
 * @param {boolean} condition - the claim.
 * @param {string} name - check name.
 * @param {string} [extra] - failure context.
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

// --- parseArgs --------------------------------------------------------------

const defaults = parseArgs([])
ok(
  defaults.json === false && defaults.detail === false && defaults.config === undefined && defaults.cwd === undefined,
  'no flags yields defaults',
  JSON.stringify(defaults),
)
const all = parseArgs(['--json', '--detail', '--config', 'C:\\a.json', '--cwd', 'C:\\Temp'])
ok(all.json && all.detail && all.config === 'C:\\a.json' && all.cwd === 'C:\\Temp', 'flags parse', JSON.stringify(all))
ok(parseArgs(['--config']).config === undefined, 'a dangling --config is ignored')
ok(parseArgs(['-h']).help === true, '-h means help')

// --- ASCII cwd rule ---------------------------------------------------------

const candidates = asciiCandidates()
ok(candidates.length > 0, 'at least one ASCII working directory exists', candidates.join(' | '))
ok(
  candidates.every((dir) => /^[\x20-\x7E]+$/.test(dir) && isAbsolute(dir)),
  'every candidate is ASCII and absolute',
  candidates.join(' | '),
)
ok(resolveChildCwd(undefined) === candidates[0], 'resolveChildCwd picks the first candidate')

let rejected = false
try {
  resolveChildCwd('relative\\path')
} catch {
  rejected = true
}
ok(rejected, 'a relative --cwd is rejected')

let chineseRejected = false
try {
  // Absolute, so it is accepted: an absolute path is passed as an argument, not
  // through the code page, and is never mangled.
  // task-17: deliberate non-ASCII fixture - it must stay non-ASCII (that is the case under\n  // test since the 2026-10 outage); the deployed project path is F:\\dsh-usage-widget.\n  resolveChildCwd('F:\\DeepSeek工作区')
} catch {
  chineseRejected = true
}
ok(!chineseRejected, 'an absolute path is accepted regardless of characters')

// --- foldEngineStream -------------------------------------------------------

const snapshotLine = JSON.stringify({
  type: 'snapshot',
  at: NOW,
  peakNow: false,
  rate: 7.1,
  today: { costUsd: 1.52, costCny: 10.85, calls: 120, tokens: { hit: 9000, miss: 1200, out: 800 } },
  total: { costUsd: 8.1, costCny: 57.5, calls: 5220, sessions: 12, tokens: {} },
  balance: { ok: true, currency: 'CNY', total: '8.47' },
  agents: [{ id: 'sess-1', label: 'Apply widget UI feedback', state: 'running', sinceLastWriteMs: 1200 }],
  jobs: [
    {
      id: 'call_00_x',
      session: 'sess-1',
      program: 'pwsh',
      command: 'node sim.mjs --steps 500',
      startedAt: NOW - 65000,
      elapsedMs: 65000,
      progress: { percent: 45.2, etaMs: 37000, source: 'bridge' },
      progressNote: null,
    },
  ],
  jobsSource: 'bridge',
})

const withSnapshot = foldEngineStream(
  `${JSON.stringify({ type: 'ready', at: NOW, pollMs: 2000, usdToCny: 7.1 })}\n${snapshotLine}\n`,
)
ok(withSnapshot.facts.snapshot !== null, 'fold finds the snapshot')
ok(withSnapshot.facts.ready !== null, 'fold finds the ready line')
ok(withSnapshot.facts.at === NOW, 'fold reads snapshot.at')
ok(
  withSnapshot.observation.lastEventAt === null,
  'a cold --once run has no lastEventAt',
  String(withSnapshot.observation.lastEventAt),
)
ok(withSnapshot.observation.dshRunning === true, 'the CLI observes DSH as running')
const jobRun = computeState(withSnapshot.observation)
ok(jobRun.state === 'running', 'live-shaped stream with a job resolves to running', jobRun.state)
ok(jobRun.detail.includes('45.2% 剩余 00:37'), 'detail carries the progress string', jobRun.detail)

const withEvent = foldEngineStream(
  `${snapshotLine}\n${JSON.stringify({ type: 'event', at: NOW - 3000, session: 's', turn: 1, step: 2, out: 12 })}\n${JSON.stringify({ type: 'event', at: NOW - 1000, session: 's', turn: 1, step: 3, out: 40 })}\n`,
)
ok(withEvent.facts.events === 2, 'fold counts events', String(withEvent.facts.events))
ok(withEvent.facts.lastEventAt === NOW - 1000, 'fold keeps the newest event time', String(withEvent.facts.lastEventAt))

const noisy = foldEngineStream(
  `${JSON.stringify({ type: 'error', at: NOW, message: 'balance: nope' })}\nnot json at all\n{"type":"snapshot","at":${NOW},"agents":[],"jobs":[]}\n`,
)
ok(noisy.facts.errors.length === 1 && noisy.facts.errors[0] === 'balance: nope', 'fold collects error lines')
ok(noisy.facts.unparsed === 1, 'fold counts unparsed lines', String(noisy.facts.unparsed))

let noSnapshotThrew = false
try {
  foldEngineStream('{"type":"ready","at":1}\n')
} catch (error) {
  noSnapshotThrew = String(error).includes('no snapshot')
}
ok(noSnapshotThrew, 'fold refuses a stream with no snapshot')

// --- 6. describeSource ------------------------------------------------------

ok(describeSource(withSnapshot.facts.snapshot).includes('source=bridge'), 'describeSource names the bridge')
ok(describeSource({ jobs: [], agents: [] }).includes('source=unknown'), 'describeSource tolerates a sparse snapshot')

// ---------------------------------------------------------------------------

console.log('')
console.log(`ascii candidates: ${candidates.join(', ')}`)
console.log(`folded snapshot -> ${jobRun.state} / ${jobRun.label} / ${jobRun.detail}`)
console.log(`${passed} checks passed, ${failures.length} failed`)
if (failures.length > 0) {
  for (const failure of failures) console.log(`  FAIL ${failure}`)
  process.exitCode = 1
} else {
  console.log('OK')
}
