/**
 * End-to-end proof of the live-state engine against a synthetic $DSH_HOME.
 *
 * It builds four session artifacts that look like real ones — a lead whose turn
 * is open, a subagent whose newest turn is open, a subagent whose turn closed,
 * and a session whose job already finished — and three unmatched `tool/call`s:
 *
 * - a program redirecting its stdout to a file it keeps writing `NN%` lines to
 *   (the `"log"` progress source),
 * - a download writing into a file whose total a real `HEAD` request against a
 *   local HTTP server confirms (the `"size"` progress source),
 * - a silent program with nothing observable at all.
 *
 * Then it runs `cli.mjs` as a *background* process and reads the NDJSON it
 * streams. The `tool/result` for the first job is appended mid-run, to prove a
 * finished job leaves the `jobs` array.
 *
 * Run: node test/activity.test.mjs
 * Scratch is written only below test/.tmp/.
 */
import { spawn } from 'node:child_process'
import { appendFileSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { zstdCompressSync } from 'node:zlib'

const NODE = process.execPath
const ENGINE = join(dirname(fileURLToPath(import.meta.url)), '..')
const WIDGET = join(ENGINE, '..')
const TMP = join(ENGINE, 'test', '.tmp')
const ROOT = join(TMP, 'activity-home')
const OUT = join(TMP, 'activity.ndjson')
const ERR = join(TMP, 'activity.err')
const WRITER = join(TMP, 'progress-writer.mjs')
const DOWNLOADER = join(TMP, 'progress-downloader.mjs')
const PROGRESS_FILE = join(TMP, 'activity-progress.log')
const REDIRECTED_LOG = join(TMP, 'activity-redirect.log')
const DOWNLOAD_FILE = join(TMP, 'activity-download.bin')

rmSync(ROOT, { recursive: true, force: true })
for (const file of [PROGRESS_FILE, REDIRECTED_LOG, DOWNLOAD_FILE]) rmSync(file, { force: true })
mkdirSync(ROOT, { recursive: true })

const LEAD_ID = 'aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa'
const CHILD_ID = 'bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb'
const RUNNING_ID = 'dddddddd-4444-4444-8444-dddddddddddd'
const DONE_ID = 'cccccccc-3333-4333-8333-cccccccccccc'
const jobCallId = 'call_00_bgprogress0001'
const downloadCallId = 'call_02_bgdownload0004'
const silentCallId = 'call_01_bgsilent0002'
const doneCallId = 'call_00_donejob0003'

const sessionDir = (id) => join(ROOT, 'sessions', '--F-ACTIVITY--', id)
const artifactPath = (id) => join(sessionDir(id), 'session.v4.jsonl.zstd')
const frame = (rows) => zstdCompressSync(Buffer.from(rows.map((row) => `${JSON.stringify(row)}\n`).join(''), 'utf8'))

/** Stamped right before the artifacts are written, so ages are real. */
const t0 = Date.now()

/** The delegating session: depth 0, turn 1 still open, two job calls in flight. */
const leadRows = [
  { type: 'session', version: 4, id: LEAD_ID, createdAt: t0, cwd: TMP, origin: 'user', delegationDepth: 0, time: t0 },
  { type: 'turn/start', seq: 1, time: t0, data: { turn: 1 } },
  { type: 'request/context', seq: 2, time: t0, data: { provider: 'deepseek-official', model: 'deepseek-flash' } },
  { type: 'session/title', seq: 3, time: t0, data: { title: 'Activity harness lead', source: { kind: 'fallback' } } },
  {
    type: 'assistant/message',
    seq: 4,
    time: t0 + 10,
    data: {
      turn: 1,
      step: 1,
      usage: { inputTokens: 100, outputTokens: 50, cacheReadTokens: 200, reasoningTokens: 0 },
      message: { source: { provider: 'deepseek-official', model: 'deepseek-flash' } },
    },
  },
  {
    type: 'tool/call',
    seq: 5,
    time: t0 + 1000,
    data: {
      turn: 1,
      step: 1,
      callId: jobCallId,
      name: 'pwsh',
      arguments: JSON.stringify({
        command: `${NODE} "${WRITER}" --file "${PROGRESS_FILE}" --seconds 60 > "${REDIRECTED_LOG}" 2>&1`,
        description: 'Simulate a long render',
        run_in_background: true,
      }),
    },
  },
  {
    type: 'tool/call',
    seq: 6,
    time: t0 + 1200,
    data: {
      turn: 1,
      step: 1,
      callId: downloadCallId,
      name: 'pwsh',
      arguments: JSON.stringify({
        command: `curl.exe -sS --limit-rate 120k -o "${DOWNLOAD_FILE}" {URL}`,
        description: 'Simulate a download',
        run_in_background: true,
      }),
    },
  },
  {
    type: 'tool/call',
    seq: 7,
    time: t0 + 1500,
    data: {
      turn: 1,
      step: 1,
      callId: silentCallId,
      name: 'bash',
      arguments: JSON.stringify({ command: 'sleep 3600', description: 'Silent long sleep' }),
    },
  },
]

/** A finished subagent: depth 1, its single turn closed, so it must read `idle`. */
const childRows = [
  {
    type: 'session',
    version: 4,
    id: CHILD_ID,
    createdAt: t0 - 60_000,
    cwd: TMP,
    parentSession: LEAD_ID,
    origin: 'subagent',
    delegationDepth: 1,
    time: t0 - 60_000,
  },
  {
    type: 'subagent/descriptor',
    seq: 0,
    time: t0 - 60_000,
    data: {
      version: 3,
      mode: 'continuable',
      provider: 'spawn',
      label: 'Harness finished subagent',
      agentProvider: 'deepseek-official',
      agentModel: 'deepseek-flash',
      agentReasoningEffort: 'high',
    },
  },
  { type: 'turn/start', seq: 1, time: t0 - 60_000, data: { turn: 1 } },
  {
    type: 'assistant/message',
    seq: 2,
    time: t0 - 59_000,
    data: {
      turn: 1,
      step: 1,
      usage: { inputTokens: 10, outputTokens: 5, cacheReadTokens: 20, reasoningTokens: 0 },
      message: { source: { provider: 'deepseek-official', model: 'deepseek-flash' } },
    },
  },
  { type: 'turn/end', seq: 3, time: t0 - 58_000, data: { turn: 1, reason: { kind: 'completed' } } },
]

/**
 * A live subagent: depth 1, its turn still open. This is the row that must read
 * `running` — real subagents are exactly this shape.
 */
const runningRows = [
  {
    type: 'session',
    version: 4,
    id: RUNNING_ID,
    createdAt: t0 - 20_000,
    cwd: TMP,
    parentSession: LEAD_ID,
    origin: 'subagent',
    delegationDepth: 1,
    time: t0 - 20_000,
  },
  {
    type: 'subagent/descriptor',
    seq: 0,
    time: t0 - 20_000,
    data: {
      version: 3,
      mode: 'continuable',
      provider: 'spawn',
      label: 'Harness running subagent',
      agentProvider: 'deepseek-official',
      agentModel: 'deepseek-flash',
      agentReasoningEffort: 'high',
    },
  },
  { type: 'turn/start', seq: 1, time: t0 - 20_000, data: { turn: 1 } },
  { type: 'turn/end', seq: 2, time: t0 - 19_000, data: { turn: 1, reason: { kind: 'completed' } } },
  { type: 'turn/start', seq: 3, time: t0 - 10_000, data: { turn: 2 } },
  {
    type: 'assistant/message',
    seq: 4,
    time: t0 - 9_000,
    data: {
      turn: 2,
      step: 1,
      usage: { inputTokens: 30, outputTokens: 15, cacheReadTokens: 40, reasoningTokens: 0 },
      message: { source: { provider: 'deepseek-official', model: 'deepseek-flash' } },
    },
  },
]

/** A job whose result arrived: it must never appear in `jobs`. */
const doneRows = [
  { type: 'session', version: 4, id: DONE_ID, createdAt: t0 - 5_000, cwd: TMP, delegationDepth: 0, time: t0 - 5_000 },
  { type: 'turn/start', seq: 1, time: t0 - 5_000, data: { turn: 1 } },
  {
    type: 'tool/call',
    seq: 2,
    time: t0 - 4_000,
    data: { turn: 1, step: 1, callId: doneCallId, name: 'pwsh', arguments: '{"command":"echo done"}' },
  },
  {
    type: 'tool/result',
    seq: 3,
    time: t0 - 3_000,
    data: {
      turn: 1,
      step: 1,
      message: { role: 'tool', source: { kind: 'tool', callId: doneCallId }, toolCallId: doneCallId, content: [] },
    },
  },
  { type: 'turn/end', seq: 4, time: t0 - 2_000, data: { turn: 1, reason: { kind: 'completed' } } },
]

const sleep = (ms) => new Promise((done) => setTimeout(done, ms))

// --- a real HTTP endpoint, so the size probe has a real Content-Length -------
const BODY_BYTES = 2_400_000
const server = createServer((request, response) => {
  if (request.method === 'HEAD') {
    response.writeHead(200, { 'content-length': String(BODY_BYTES), 'content-type': 'application/octet-stream' })
    response.end()
    return
  }
  response.writeHead(200, { 'content-length': String(BODY_BYTES), 'content-type': 'application/octet-stream' })
  response.end(Buffer.alloc(BODY_BYTES, 7))
})
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const URL = `http://127.0.0.1:${server.address().port}/payload.bin`

for (const [id, rows] of [
  [LEAD_ID, leadRows],
  [CHILD_ID, childRows],
  [RUNNING_ID, runningRows],
  [DONE_ID, doneRows],
]) {
  mkdirSync(sessionDir(id), { recursive: true })
  writeFileSync(artifactPath(id), frame(rows.map((row) => JSON.parse(JSON.stringify(row).replace('{URL}', URL)))))
}

writeFileSync(
  WRITER,
  `import { appendFileSync } from 'node:fs'
const args = process.argv.slice(2)
const read = (name, fallback) => {
  const index = args.indexOf(name)
  return index === -1 ? fallback : args[index + 1]
}
const file = read('--file', 'progress.log')
const seconds = Number(read('--seconds', '60'))
const stepMs = 250
const steps = Math.round((seconds * 1000) / stepMs)
let step = 0
const timer = setInterval(() => {
  step += 1
  const percent = Math.min(100, Math.round(((step / steps) * 100) * 10) / 10)
  const line = \`rendering \${percent}% frame \${step}/\${steps}\\n\`
  appendFileSync(file, line)
  process.stdout.write(line)
  if (step >= steps) clearInterval(timer)
}, stepMs)
`,
)

writeFileSync(
  DOWNLOADER,
  `// The download in this harness is a real throttled curl; this file exists only
// so the scratch directory documents what the "size" probe is measuring.
`,
)

writeFileSync(
  join(ROOT, 'config.json'),
  JSON.stringify({ pollMs: 1000, balanceMs: 600000, usdToCny: 7.1, defaultModel: 'deepseek-flash', activityJobsMax: 50 }, null, 2),
)

// --- the writer runs for a minute, exactly like a real background job ---------
// Its stdout goes to the file the synthetic command redirects to, so the
// progress lines land exactly where the "log" probe looks for them.
const redirectFd = openSync(REDIRECTED_LOG, 'w')
const writer = spawn(NODE, [WRITER, '--file', PROGRESS_FILE, '--seconds', '60'], {
  stdio: ['ignore', redirectFd, redirectFd],
  windowsHide: true,
})
const writerPid = writer.pid

// --- the download: a real throttled curl into the file the job names ---------
const curl = spawn('curl.exe', ['-sS', '--limit-rate', '120k', '-o', DOWNLOAD_FILE, URL], {
  stdio: ['ignore', 'ignore', 'ignore'],
  windowsHide: true,
})

// --- the engine runs in the background, streaming NDJSON to a file -----------
const outFd = openSync(OUT, 'w')
const errFd = openSync(ERR, 'w')
const engine = spawn(NODE, [join(ENGINE, 'cli.mjs')], {
  cwd: WIDGET,
  env: { ...process.env, DSH_HOME: ROOT },
  stdio: ['ignore', outFd, errFd],
  windowsHide: true,
})

/** Read every complete line written so far. */
const readRows = () => {
  const text = readFileSync(OUT, 'utf8')
  const cut = text.lastIndexOf('\n')
  if (cut === -1) return []
  return text
    .slice(0, cut)
    .split('\n')
    .filter((line) => line.length > 0)
    .flatMap((line) => {
      try {
        return [JSON.parse(line)]
      } catch {
        return []
      }
    })
}

console.log('writer pid:', writerPid)
console.log('engine pid:', engine.pid)
console.log('synthetic DSH_HOME:', ROOT)
console.log('progress file:', PROGRESS_FILE)
console.log('redirected log:', REDIRECTED_LOG)
console.log('download file:', DOWNLOAD_FILE)
console.log('HEAD endpoint:', URL)
console.log('')

const snapshots = []
/** The download's size on disk at the moment each snapshot was read. */
const sizesByPoll = []
for (let index = 0; index < 12; index += 1) {
  await sleep(1000)
  const rows = readRows()
  const snapshot = rows.filter((row) => row.type === 'snapshot').pop()
  if (snapshot === undefined) {
    console.log(`t+${index + 1}s: no snapshot yet (rows=${rows.length})`)
    continue
  }
  snapshots.push(snapshot)
  sizesByPoll.push(readFileSync(DOWNLOAD_FILE).length)
  const describe = (id) => {
    const row = snapshot.jobs.find((job) => job.id === id)
    if (row === undefined) return 'absent'
    return `{percent:${row.progress?.percent ?? 'null'},etaMs:${row.progress?.etaMs ?? 'null'},source:${row.progress?.source ?? 'null'},note:${row.progressNote ?? 'null'}}`
  }
  console.log(
    `t+${index + 1}s jobs=${snapshot.jobs.length} log=${describe(jobCallId)} size=${describe(downloadCallId)} silent=${describe(silentCallId)}`,
  )
}

console.log('')
console.log('--- first snapshot: agents and jobs, verbatim ---')
const first = snapshots[0]
console.log(JSON.stringify({ agents: first.agents, jobs: first.jobs }, null, 2))

// --- the last poll, read together with the size it can only have observed ----
const sizeAtLastPoll = sizesByPoll[sizesByPoll.length - 1]
const last = snapshots[snapshots.length - 1]
const lastJob = last.jobs.find((row) => row.id === jobCallId)
const lastDownload = last.jobs.find((row) => row.id === downloadCallId)
console.log('')
console.log('--- last snapshot: the two observable jobs ---')
console.log(JSON.stringify(lastJob, null, 2))
console.log(JSON.stringify(lastDownload, null, 2))

const tail = readFileSync(PROGRESS_FILE, 'utf8').trim().split('\n')
console.log('')
console.log(`--- progress file after the run: ${tail.length} lines, last three ---`)
console.log(tail.slice(-3).join('\n'))
console.log('--- redirected log tail (what the "log" source reads) ---')
console.log(readFileSync(REDIRECTED_LOG, 'utf8').trim().split('\n').slice(-3).join('\n'))
console.log('--- download destination at the instant of that poll ---')
console.log(`${sizeAtLastPoll} bytes of ${BODY_BYTES}`)

// --- the job finishes: its result lands, so it must leave `jobs` --------------
appendFileSync(
  artifactPath(LEAD_ID),
  frame([
    {
      type: 'tool/result',
      seq: 90,
      time: Date.now(),
      data: {
        turn: 1,
        step: 1,
        message: { role: 'tool', source: { kind: 'tool', callId: jobCallId }, toolCallId: jobCallId, content: [] },
      },
    },
  ]),
)
await sleep(2500)
const afterFinish = readRows().filter((row) => row.type === 'snapshot').pop()
console.log('')
console.log(
  `--- after the result landed: jobs=${afterFinish.jobs.length} containsProgressJob=${afterFinish.jobs.some((row) => row.id === jobCallId)}`,
)

writer.kill()
curl.kill()
engine.kill()
server.close()
await sleep(400)

const errText = readFileSync(ERR, 'utf8')
console.log('')
console.log('--- stderr ---')
console.log(errText || '(empty)')

const agents = first.agents

/** The silent job must report `progress: null` plus an explanation, every poll. */
const silentIsComplete = () =>
  snapshots.every((snapshot) => {
    const row = snapshot.jobs.find((job) => job.id === silentCallId)
    return row !== undefined && row.progress === null && typeof row.progressNote === 'string' && row.progressNote.length > 0
  })

/** Every non-null progress object must be a well-formed, clamped one. */
const progressesAreSane = (snapshotsToCheck) =>
  snapshotsToCheck.every((snapshot) =>
    snapshot.jobs.every((row) => {
      if (row.progress === null) return typeof row.progressNote === 'string' && row.progressNote.length > 0
      const { percent, etaMs, source } = row.progress
      return (
        typeof percent === 'number' &&
        percent >= 0 &&
        percent <= 100 &&
        Math.round(percent * 10) === percent * 10 &&
        (source === 'log' || source === 'size') &&
        (etaMs === null || (Number.isInteger(etaMs) && etaMs >= 1000 && etaMs <= 604_800_000))
      )
    }),
  )

const checks = [
  ['only the two delegating sessions became agents', agents.length === 2],
  ['the open turn reads running', agents.some((row) => row.id === RUNNING_ID && row.state === 'running')],
  ['the closed turn reads idle', agents.some((row) => row.id === CHILD_ID && row.state === 'idle')],
  ['the depth-0 lead is not an agent', !agents.some((row) => row.id === LEAD_ID)],
  ['the descriptor label is used', agents.some((row) => row.label === 'Harness finished subagent')],
  ['the model comes from the log', agents.every((row) => row.model === 'deepseek-flash')],
  ['running sorts before idle', agents[0]?.state === 'running' && agents[agents.length - 1]?.state === 'idle'],
  ['elapsedMs is a plain duration, not an epoch', agents.every((row) => row.elapsedMs < 3_600_000)],
  ['idle elapsed is the closed turn duration', agents.find((row) => row.id === CHILD_ID)?.elapsedMs === 2000],
  ['the running turn is the newest one', agents.find((row) => row.id === RUNNING_ID)?.turn === 2],
  ['all three unmatched calls are jobs', first.jobs.length === 3],
  ['the finished call is not a job', !first.jobs.some((row) => row.id === doneCallId)],
  ['jobs are oldest first', first.jobs.every((row, index) => index === 0 || first.jobs[index - 1].startedAt <= row.startedAt)],
  ['program comes from the tool name', first.jobs.some((row) => row.program === 'bash')],
  ['command is one line and capped', first.jobs.every((row) => !row.command.includes('\n') && row.command.length <= 120)],
  ['command reads like a command', first.jobs.some((row) => row.command.includes('progress-writer') || row.command.includes('Silent long sleep'))],
  ['command carries no escaped JSON', first.jobs.every((row) => !row.command.includes('\\"'))],
  ['the redirected job reports log progress', lastJob?.progress?.source === 'log'],
  ['the download reports size progress', lastDownload?.progress?.source === 'size'],
  ['log percent is in range', typeof lastJob?.progress?.percent === 'number' && lastJob.progress.percent >= 0 && lastJob.progress.percent <= 100],
  ['size percent is in range', typeof lastDownload?.progress?.percent === 'number' && lastDownload.progress.percent >= 0 && lastDownload.progress.percent <= 100],
  ['both etas are sane integers', [lastJob, lastDownload].every((row) => Number.isInteger(row?.progress?.etaMs) && row.progress.etaMs >= 1000 && row.progress.etaMs <= 604_800_000)],
  ['percent advanced between the first and last snapshot', (lastJob?.progress?.percent ?? 0) > (first.jobs.find((row) => row.id === jobCallId)?.progress?.percent ?? -1)],
  ['the download percent advanced too', (lastDownload?.progress?.percent ?? 0) > (first.jobs.find((row) => row.id === downloadCallId)?.progress?.percent ?? -1)],
  ['every progress row is well formed', progressesAreSane(snapshots)],
  ['the silent job reports null progress plus a note', silentIsComplete()],
  ['the finished job left the jobs array', !afterFinish.jobs.some((row) => row.id === jobCallId)],
  ['stderr stayed empty', errText.length === 0],
]

console.log('')
for (const [label, pass] of checks) console.log(`${pass ? 'PASS' : 'FAIL'} ${label}`)

// The snapshot was rendered from the size at the moment the engine polled, while
// curl keeps writing, so the two are compared with one poll of slack: the row's
// percent may lag the bytes on disk, but it must never run ahead of them.
const sizePercentNow = (sizeAtLastPoll / BODY_BYTES) * 100
const sizePercentRow = lastDownload?.progress?.percent ?? -1
const sizePercentMatchesFile = sizePercentRow <= sizePercentNow + 0.05 && sizePercentRow >= sizePercentNow - 12
console.log(
  `${sizePercentMatchesFile ? 'PASS' : 'FAIL'} size percent tracks the real file against Content-Length (row ${sizePercentRow}% vs disk ${Math.round(sizePercentNow * 10) / 10}%)`,
)

const allPassed = checks.every(([, pass]) => pass) && sizePercentMatchesFile
console.log(allPassed ? 'ALL PASS' : 'SOME FAILED')
process.exitCode = allPassed ? 0 : 1
