/**
 * Self-contained end-to-end test for engine/cli.mjs on a synthetic $DSH_HOME.
 *
 * It proves the two semantics real traffic cannot prove deterministically:
 * (1) the first poll is a baseline and emits no events for pre-existing samples,
 * (2) a session that grows emits exactly the new calls, oldest first, exactly once.
 *
 * Run: node test/synthetic.test.mjs
 * Scratch is written only below test/.tmp/.
 */
import { spawn } from 'node:child_process'
import { appendFileSync, mkdirSync, openSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { zstdCompressSync } from 'node:zlib'

const NODE = process.execPath
const ENGINE = join(dirname(fileURLToPath(import.meta.url)), '..')
const WIDGET = join(ENGINE, '..')
const TMP = join(ENGINE, 'test', '.tmp')
const ROOT = join(TMP, 'synhome')
const SESSION_DIR = join(ROOT, 'sessions', '--F-SYN--', 'session-syn-1')
mkdirSync(SESSION_DIR, { recursive: true })
const artifact = join(SESSION_DIR, 'session.v4.jsonl.zstd')
const outFile = join(TMP, 'synthetic.ndjson')
const errFile = join(TMP, 'synthetic.err')

const jsonl = (rows) => rows.map((row) => `${JSON.stringify(row)}\n`).join('')
const frame = (rows) => zstdCompressSync(Buffer.from(jsonl(rows), 'utf8'))
const header = (t) => ({
  type: 'request/header',
  time: t,
  data: { header: { config: { provider: 'deepseek-official', model: 'deepseek-flash' } } },
})
const call = (t, step, input, output, cacheRead) => ({
  type: 'assistant/message',
  time: t,
  data: {
    turn: 1,
    step,
    usage: { inputTokens: input, outputTokens: output, cacheReadTokens: cacheRead, reasoningTokens: 0 },
    message: { source: { provider: 'deepseek-official', model: 'deepseek-flash' } },
  },
})

const t0 = Date.now() - 60_000
writeFileSync(
  artifact,
  frame([
    { type: 'session', id: 'session-syn-1', cwd: 'F:\\syn', createdAt: t0, time: t0 },
    { type: 'turn/start', time: t0, data: { turn: 1 } },
    header(t0),
    call(t0, 1, 1000, 500, 2000),
  ]),
  'utf8',
)
appendFileSync(artifact, frame([])) // an empty frame: re-encoding must not duplicate
appendFileSync(artifact, frame([call(t0 + 1000, 2, 10, 5, 20)])) // pre-existing: baseline only

const fd = openSync(outFile, 'w')
const errFd = openSync(errFile, 'w')
const child = spawn(NODE, [join(ENGINE, 'cli.mjs')], {
  cwd: WIDGET,
  env: { ...process.env, DSH_HOME: ROOT },
  stdio: ['ignore', fd, errFd],
  windowsHide: true,
})

const sleep = (ms) => new Promise((done) => setTimeout(done, ms))
await sleep(6000)
appendFileSync(artifact, frame([call(Date.now(), 3, 7, 3, 11)])) // the only genuinely new call

await sleep(9000)
child.kill()
await sleep(500)

const lines = readFileSync(outFile, 'utf8').split('\n').filter((row) => row.length > 0)
const parsed = lines.map((row) => JSON.parse(row))
const count = (type) => parsed.filter((row) => row.type === type).length
const summary = parsed.map((row) => {
  if (row.type === 'snapshot') {
    return `snapshot at=${row.at} total.calls=${row.total.calls} total.costUsd=${row.total.costUsd} today.calls=${row.today.calls} balance.ok=${row.balance.ok}`
  }
  if (row.type === 'event') {
    return `event at=${row.at} session=${row.session} turn=${row.turn} step=${row.step} hit=${row.hit} miss=${row.miss} out=${row.out} costUsd=${row.costUsd}`
  }
  return JSON.stringify(row)
})

console.log(`lines=${lines.length} ready=${count('ready')} snapshots=${count('snapshot')} events=${count('event')}`)
console.log('--- every line, compacted ---')
console.log(summary.join('\n'))
console.log('--- first five raw stdout lines ---')
console.log(lines.slice(0, 5).join('\n'))
console.log('--- stderr ---')
console.log(readFileSync(errFile, 'utf8') || '(empty)')

const baselineSnapshot = parsed.find((row) => row.type === 'snapshot')
const event = parsed.find((row) => row.type === 'event')
const checks = [
  ['first snapshot counts both pre-existing calls', baselineSnapshot.total.calls === 2],
  ['baseline emitted no events', baselineSnapshot.at < (event?.at ?? Infinity)],
  ['exactly one event for the one appended call', count('event') === 1],
  ['the event is the appended step', event?.step === 3 && event?.hit === 11 && event?.miss === 7 && event?.out === 3],
  ['old samples were never re-emitted', !parsed.some((row) => row.type === 'event' && row.step !== 3)],
  ['snapshots kept coming', count('snapshot') >= 3],
  ['stderr stayed empty', readFileSync(errFile, 'utf8').length === 0],
]
for (const [label, pass] of checks) console.log(`${pass ? 'PASS' : 'FAIL'} ${label}`)
console.log(checks.every(([, pass]) => pass) ? 'ALL PASS' : 'SOME FAILED')
process.exitCode = checks.every(([, pass]) => pass) ? 0 : 1
