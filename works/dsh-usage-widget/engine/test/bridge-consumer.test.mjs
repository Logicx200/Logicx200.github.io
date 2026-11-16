/**
 * Offline checks for the bridge consumer: the mapping from the host bridge's
 * `jobs.json` onto the snapshot's job rows, and the freshness rule that decides
 * whether that file wins over the log-derived rows.
 *
 * No real Harness is involved — a temp `$DSH_HOME` holds a hand-written
 * `jobs.json` and the module is asked what it makes of it.
 *
 * Run: node test/bridge-consumer.test.mjs
 */
import { mkdir, mkdtemp, rm, writeFile, utimes } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

import { defaultBridgePath, mapBridgeJob, readBridgeJobs, BRIDGE_COMMAND_MAX } from '../bridge-jobs.mjs'

let passed = 0
let failed = 0

function check(name, ok, detail = '') {
  if (ok) {
    passed += 1
    console.log(`  ok    ${name}${detail ? ` — ${detail}` : ''}`)
  } else {
    failed += 1
    console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ''}`)
  }
}

const NOW = 1790695900000

console.log('bridge consumer :: offline checks')
console.log(`node         ${process.version}`)

const home = await mkdtemp(join(tmpdir(), 'bridge-consumer-'))
const statePath = join(home, 'usage-widget', 'jobs.json')
console.log(`temp home    ${home}`)
console.log('')

/** Write a bridge file and, optionally, backdate its mtime. */
async function writeBridge(jobs, { ageMs = 0 } = {}) {
  await mkdir(dirname(statePath), { recursive: true })
  await writeFile(statePath, JSON.stringify({ at: NOW, jobs }), 'utf8')
  if (ageMs > 0) {
    const seconds = (NOW - ageMs) / 1000
    await utimes(statePath, seconds, seconds)
  }
}

// ---------------------------------------------------------------------------
console.log('1. a fresh file with two running jobs maps onto the snapshot shape')
await writeBridge([
  {
    id: 'bash-3',
    kind: 'bash',
    label: 'node sim.mjs --steps 500',
    owner: 'session-abc',
    status: 'running',
    progress: 'step 120/500',
    detail: null,
    percent: 24,
    etaMs: 95000,
    startedAt: NOW - 60_000,
    finishedAt: null,
    lastLine: 'step 120/500',
  },
  {
    id: 'bash-4',
    kind: 'pwsh',
    label: 'curl.exe -o big.bin https://example.invalid/big.bin',
    owner: 'session-def',
    status: 'running',
    progress: null,
    detail: null,
    percent: null,
    etaMs: null,
    startedAt: NOW - 5_000,
    finishedAt: null,
    lastLine: 'downloading … 12%',
  },
])
let result = await readBridgeJobs({ path: statePath, now: NOW, staleMs: 10_000 })
check('the file counts as fresh', result.fresh === true, `reason=${result.reason ?? '-'}`)
check('both running jobs are present', result.jobs.length === 2, `count=${result.jobs.length}`)
const first = result.jobs[0]
check('id round-trips', first.id === 'bash-3', first.id)
check('session comes from owner', first.session === 'session-abc', String(first.session))
check('program comes from kind', first.program === 'bash', first.program)
check('command comes from label', first.command === 'node sim.mjs --steps 500', first.command)
check('startedAt round-trips', first.startedAt === NOW - 60_000, String(first.startedAt))
check('elapsedMs is now minus startedAt', first.elapsedMs === 60_000, String(first.elapsedMs))
check('progress carries percent', first.progress !== null && first.progress.percent === 24, JSON.stringify(first.progress))
check('progress carries etaMs', first.progress !== null && first.progress.etaMs === 95000, String(first.progress?.etaMs))
check('progress is tagged as coming from the bridge', first.progress !== null && first.progress.source === 'bridge')
check('a job with a percent has no note', first.progressNote === null, String(first.progressNote))
const second = result.jobs[1]
check('a job without a percent has no progress object', second.progress === null, JSON.stringify(second.progress))
check('its note falls back to lastLine', second.progressNote === 'downloading … 12%', String(second.progressNote))
console.log('')

// ---------------------------------------------------------------------------
console.log('2. a fresh file that reports nothing wins outright (nothing is running)')
await writeBridge([])
result = await readBridgeJobs({ path: statePath, now: NOW, staleMs: 10_000 })
check('still fresh', result.fresh === true, `reason=${result.reason ?? '-'}`)
check('the job list is empty rather than missing', Array.isArray(result.jobs) && result.jobs.length === 0)
console.log('')

// ---------------------------------------------------------------------------
console.log('3. an older file is stale, so the caller keeps the log-derived rows')
await writeBridge([{ id: 'bash-9', kind: 'bash', label: 'stale', status: 'running', startedAt: NOW - 1000 }], {
  ageMs: 30_000,
})
result = await readBridgeJobs({ path: statePath, now: NOW, staleMs: 10_000 })
check('a 30 s old file is not fresh', result.fresh === false, `reason=${result.reason}`)
check('it reports no jobs to merge', result.jobs.length === 0)
result = await readBridgeJobs({ path: statePath, now: NOW, staleMs: 60_000 })
check('the same file is fresh with a longer window', result.fresh === true, `reason=${result.reason ?? '-'}`)
console.log('')

// ---------------------------------------------------------------------------
console.log('4. missing and malformed files fall back instead of throwing')
result = await readBridgeJobs({ path: join(home, 'nope', 'jobs.json'), now: NOW })
check('a missing file is not fresh', result.fresh === false, `reason=${result.reason}`)
check('and yields no jobs', result.jobs.length === 0)
await writeFile(statePath, '{ this is not json', 'utf8')
result = await readBridgeJobs({ path: statePath, now: NOW })
check('a malformed file is not fresh', result.fresh === false, `reason=${result.reason}`)
check('and yields no jobs', result.jobs.length === 0)
await writeFile(statePath, JSON.stringify({ at: NOW, jobs: 'not an array' }), 'utf8')
result = await readBridgeJobs({ path: statePath, now: NOW })
check('a jobs field that is not an array is fresh-but-empty', result.fresh === true && result.jobs.length === 0)
console.log('')

// ---------------------------------------------------------------------------
console.log('5. only running rows are shown, and the numbers are clamped')
const filtered = await readBridgeJobs({
  path: await (async () => {
    await writeBridge([
      { id: 'a', status: 'running', startedAt: NOW - 1000 },
      { id: 'b', status: 'stopping', startedAt: NOW - 1000 },
      { id: 'c', status: 'completed', startedAt: NOW - 1000, finishedAt: NOW - 500 },
      { id: 'd', status: 'killed', startedAt: NOW - 1000 },
      { id: 'e', status: 'failed', startedAt: NOW - 1000 },
    ])
    return statePath
  })(),
  now: NOW,
})
check('running and stopping are kept', filtered.jobs.length === 2, `count=${filtered.jobs.length}`)
check('settled rows are dropped', filtered.jobs.every((job) => job.id === 'a' || job.id === 'b'))

check('an out-of-range percent is ignored', mapBridgeJob({ percent: 140, status: 'running', startedAt: NOW }, NOW).progress === null)
check('a negative percent is ignored', mapBridgeJob({ percent: -3, status: 'running', startedAt: NOW }, NOW).progress === null)
check('a null eta stays null inside a real percent', (() => {
  const row = mapBridgeJob({ percent: 12, etaMs: null, status: 'running', startedAt: NOW }, NOW)
  return row.progress !== null && row.progress.percent === 12 && row.progress.etaMs === null
})())
check('a settled row measures elapsed from finishedAt', (() => {
  const row = mapBridgeJob({ status: 'completed', startedAt: NOW - 9000, finishedAt: NOW - 2000 }, NOW)
  return row.elapsedMs === 7000
})())
check('a very long command is capped', (() => {
  const row = mapBridgeJob({ label: 'x'.repeat(500), status: 'running', startedAt: NOW }, NOW)
  return row.command.length === BRIDGE_COMMAND_MAX
})(), String(mapBridgeJob({ label: 'x'.repeat(500) }, NOW).command.length))
check('a missing kind falls back to a generic program', mapBridgeJob({ status: 'running', startedAt: NOW }, NOW).program === 'job')
check('no percent and no text gives the unknown-progress note', mapBridgeJob({ status: 'running', startedAt: NOW }, NOW).progressNote === '无进度输出')
console.log('')

// ---------------------------------------------------------------------------
console.log('6. the default path is the plugin default')
const def = defaultBridgePath(join(home, 'home'))
check('default path is $DSH_HOME/usage-widget/jobs.json', def === join(home, 'home', 'usage-widget', 'jobs.json'), def)

await rm(home, { recursive: true, force: true })

console.log('')
console.log(`--- ${passed} passed, ${failed} failed ---`)
process.exitCode = failed === 0 ? 0 : 1
