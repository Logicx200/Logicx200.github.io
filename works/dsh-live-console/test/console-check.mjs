/**
 * Offline integration check for the live console host plugin.
 *
 * The stub context is deliberately narrow: only `jobs`, `webServer`,
 * `systemPrompt`, `effect`, `inject`, and `on` exist, and the web carrier is a
 * real Node HTTP server so the page, JSON, log, and SSE routes are exercised
 * over actual requests. The fake job registry enforces the same owner fence as
 * the real registry (`job ... belongs to another session`), which is exactly
 * the failure the bridge plugin hit in production.
 *
 *   node test/console-check.mjs
 */

import assert from 'node:assert/strict'
import http from 'node:http'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { apply, normalizeOptions } from '../src/index.mjs'

let passed = 0
/** @param {string} label */
function ok(label) {
  passed += 1
  console.log(`ok    ${label}`)
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// ── a real HTTP carrier behind the stub webServer service ───────────────────
/** @type {Map<string, (req: any, res: any) => void>} */
const routes = new Map()
const server = http.createServer((req, res) => {
  const path = new URL(req.url, 'http://console.invalid').pathname
  const handler = routes.get(path)
  if (handler === undefined) {
    res.writeHead(404, { 'content-type': 'text/plain' })
    res.end('not found')
    return
  }
  try {
    handler(req, res)
  } catch (error) {
    res.writeHead(500, { 'content-type': 'text/plain' })
    res.end(String(error))
  }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`

// ── fake job registry with the real owner fence ─────────────────────────────
/** @type {Set<(event: any) => void>} */
const jobListeners = new Set()
/** @type {Map<string, { owner?: string, text: string, reads: { from: number, caller?: string }[] }>} */
const jobRecords = new Map()

const jobs = {
  events: {
    subscribe(_filter, listener) {
      jobListeners.add(listener)
      return () => jobListeners.delete(listener)
    },
  },
  /**
   * @param {string} id - job id.
   * @param {number} from - byte offset.
   * @param {string} [caller] - owning session id.
   */
  readAt(id, from, caller) {
    const record = jobRecords.get(id)
    if (record === undefined) throw new Error(`unknown job ${id}`)
    if (record.owner !== undefined && caller !== record.owner) {
      throw new Error(`job ${id} belongs to another session`)
    }
    record.reads.push({ from, caller })
    const buffer = Buffer.from(record.text, 'utf8')
    const start = Math.max(0, Math.min(from, buffer.length))
    const tail = buffer.subarray(start).toString('utf8')
    return {
      chunks: tail.length > 0 ? [{ text: tail, at: Date.now() }] : [],
      next: buffer.length,
      lossy: false,
    }
  },
}

/** @param {any} event */
const emitJob = (event) => {
  for (const listener of [...jobListeners]) listener(event)
}

// ── stub Cordis context ─────────────────────────────────────────────────────
/** @type {Map<string, Function[]>} */
const hostListeners = new Map()
/** @type {{ name: string, order: number, text: any }[]} */
const promptSections = []
/** @type {(() => void)[]} */
const cleanups = []
/** @type {Map<string, any>} */
const apiRoutes = new Map()

const postedMessages = []
const fakeAgent = { followup(message) { postedMessages.push(message) } }

const ctx = {
  jobs,
  agents: { get(id) { return id === 'session-root' ? fakeAgent : undefined } },
  connection: {
    fetch: {
      register(route) {
        apiRoutes.set(route.path, route)
        return () => apiRoutes.delete(route.path)
      },
    },
  },
  webServer: {
    getOrigin: () => origin,
    register(route) {
      if (routes.has(route.path)) throw new Error(`duplicate route ${route.path}`)
      routes.set(route.path, route.handler)
      return () => routes.delete(route.path)
    },
  },
  systemPrompt: {
    section(definition) {
      promptSections.push(definition)
      return () => {}
    },
  },
  effect(fn) {
    const result = fn()
    if (typeof result === 'function') cleanups.push(result)
    return () => {}
  },
  inject(_deps, callback) {
    callback(ctx)
  },
  on(name, listener) {
    const list = hostListeners.get(name) ?? []
    list.push(listener)
    hostListeners.set(name, list)
    return () => {
      const current = hostListeners.get(name) ?? []
      hostListeners.set(name, current.filter((entry) => entry !== listener))
    }
  },
  logger: {
    warn() {},
    info() {},
  },
}

/** @param {string} name */
function emitHost(name, ...args) {
  for (const listener of [...(hostListeners.get(name) ?? [])]) listener(...args)
}

const tempHome = await mkdtemp(join(tmpdir(), 'dsh-live-console-check-'))
const statePath = join(tempHome, 'history.json')
const KEY = 'test-capability-key-123'
/** @param {string} path */
const url = (path) => `${origin}${path}${path.includes('?') ? '&' : '?'}k=${KEY}`

// ── normalizeOptions ────────────────────────────────────────────────────────
const options = normalizeOptions({
  route: 'live-console/',
  autoOpen: 'never',
  updateMs: 200,
  keepSettledMs: 5_000,
  historyPath: statePath,
})
assert.equal(options.route, '/live-console')
assert.equal(options.autoOpen, 'never')
assert.equal(options.updateMs, 200)
ok('loader config normalises route and numeric options')

const defaults = normalizeOptions({ autoOpen: 'nonsense' })
assert.equal(defaults.autoOpen, 'auto')
ok('an unknown autoOpen falls back to auto')

// ── apply the plugin ────────────────────────────────────────────────────────
const teardown = apply(ctx, {
  autoOpen: 'never',
  updateMs: 200,
  keepSettledMs: 5_000,
  history: true,
  historyPath: statePath,
  usage: false,
  balance: false,
  capability: KEY,
  route: '/live-console',
})
assert.equal(typeof teardown, 'function')
ok('apply() returns a disposer')

assert.deepEqual([...routes.keys()].sort(), [
  '/live-console',
  '/live-console/agent-info',
  '/live-console/context-archive',
  '/live-console/events',
  '/live-console/graph',
  '/live-console/graph-data',
  '/live-console/log',
  '/live-console/send',
  '/live-console/state',
  '/live-console/usage',
])
ok('all console routes are registered')

// The in-app button asks this authenticated endpoint for the capability URL.
assert.ok(apiRoutes.has('/api/live-console/url'))
const urlResponse = await apiRoutes.get('/api/live-console/url').fetch(new Request('http://console.invalid/api/live-console/url'))
const urlBody = await urlResponse.json()
assert.equal(urlBody.url, `${origin}/live-console?k=${KEY}`)
ok('the authenticated URL endpoint returns the capability link')
const sendResponse = await fetch(url('/live-console/send'), {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ sessionId: 'session-root', text: '继续，把这步做完' }),
})
assert.equal(sendResponse.status, 200)
assert.deepEqual(await sendResponse.json(), { ok: true })
assert.equal(postedMessages.length, 1)
assert.equal(postedMessages[0].role, 'user')
assert.equal(postedMessages[0].content[0].text, '继续，把这步做完')
ok('the composer endpoint injects a user message into the live agent')

const emptySend = await fetch(url('/live-console/send'), {
  method: 'POST',
  headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ sessionId: 'session-root', text: '   ' }),
})
assert.equal(emptySend.status, 400)
ok('an empty composer submission is rejected')

const agentInfo = await (await fetch(url('/live-console/agent-info?session=session-root'))).json()
assert.equal(agentInfo.agent, true)
assert.equal(agentInfo.followup, 'function')
ok('the agent-info route reports a sendable live agent')

assert.equal(promptSections.length, 1)
assert.equal(promptSections[0].name, 'live-console-progress')
assert.ok(String(promptSections[0].text()).includes('[progress 3/10]'))
ok('the global progress convention is registered in the system prompt')

// ── page and state routes ───────────────────────────────────────────────────
const unauthorized = await fetch(`${origin}/live-console/state`)
assert.equal(unauthorized.status, 401)
ok('a data route without the link key is rejected')

const page = await fetch(url('/live-console'))
assert.equal(page.status, 200)
assert.ok((page.headers.get('content-type') ?? '').includes('text/html'))
assert.ok((page.headers.get('content-security-policy') ?? '').includes("script-src"))
const pageText = await page.text()
assert.ok(pageText.includes('DSH Live Console'))
assert.ok(!pageText.includes('__LIVE_CONSOLE_TITLE__'))
assert.ok(pageText.includes('BASE + "/state"'))
assert.ok(pageText.includes('EventSource'))
ok('the HTML page is served with the title substituted and a CSP')

const head = await fetch(url('/live-console'), { method: 'HEAD' })
assert.equal(head.status, 200)
ok('HEAD is supported on the page route')

const emptyState = await (await fetch(url('/live-console/state'))).json()
assert.equal(emptyState.jobs.length, 0)
assert.equal(emptyState.sessions.length, 0)
assert.equal(emptyState.usage.enabled, false)
ok('the state route answers with an empty snapshot')

// ── one running job, with explicit progress in its output ───────────────────
const firstStartedAt = Date.now() - 3_000
const baseView = {
  id: 'bash-1',
  kind: 'bash',
  label: 'python sim.py',
  owner: 'session-root',
  status: 'running',
  startedAt: firstStartedAt,
  finishedAt: null,
  output: { total: 0, earliest: 0 },
}
jobRecords.set('bash-1', { owner: 'session-root', text: '', reads: [] })
emitJob({ type: 'registered', job: baseView })

const sessionArg = {
  id: 'session-root',
  header: { id: 'session-root', cwd: tempHome, createdAt: firstStartedAt - 2_000 },
}
emitHost('session/event', sessionArg, {
  type: 'session/title',
  seq: 1,
  time: Date.now(),
  data: { title: '测试对话' },
})
emitHost('session/event', sessionArg, {
  type: 'tool/call',
  seq: 2,
  time: Date.now(),
  data: { turn: 1, step: 1, callId: 'call-1', name: 'pwsh', arguments: JSON.stringify({ command: 'python sim.py' }) },
})
emitHost('session/event', sessionArg, {
  type: 'tool/result',
  seq: 3,
  time: Date.now(),
  data: {
    turn: 1,
    step: 1,
    message: { role: 'tool', source: { callId: 'call-1' }, content: [{ type: 'text', text: 'ok result' }] },
  },
})

emitHost('session/event', sessionArg, {
  type: 'user/message',
  seq: 4,
  time: Date.now(),
  data: { role: 'user', content: [{ type: 'text', text: '帮我检查一下这两个插件' }] },
})
emitHost('session/event', sessionArg, {
  type: 'assistant/message',
  seq: 5,
  time: Date.now(),
  data: { message: { role: 'assistant', content: [{ type: 'text', text: '好的，先跑一遍自检。' }] }, usage: { outputTokens: 123 } },
})

const firstText = 'booting\n[progress 2/10] training…\n'
jobRecords.get('bash-1').text = firstText
emitJob({ type: 'output', id: 'bash-1', total: Buffer.byteLength(firstText) })

await wait(700)
const runningState = await (await fetch(url('/live-console/state'))).json()
const runningJob = runningState.jobs.find((job) => job.id === 'bash-1')
assert.ok(runningJob !== undefined)
assert.equal(runningJob.percent, 20)
assert.equal(runningJob.progressSource, 'output')
ok('explicit [progress 2/10] becomes a 20% output-progress bar')

const session = runningState.sessions.find((row) => row.id === 'session-root')
assert.equal(session.title, '测试对话')
assert.equal(session.cwd, tempHome)
assert.ok(Array.isArray(session.dialogue) && session.dialogue.some((message) => message.role === 'user' && message.text.includes('帮我检查')))
assert.ok(session.dialogue.some((message) => message.role === 'assistant' && message.text.includes('先跑一遍自检')))
ok('the session carries the compact user/assistant dialogue')
ok('the session list carries title and cwd from durable events')

assert.ok(runningState.events.some((event) => event.type === 'tool/call' && event.summary.includes('python sim.py')))
ok('the conversation timeline carries a tool-call event')

assert.ok(runningState.events.some((event) => event.type === 'tool/result' && event.summary.includes('ok result')))
ok('the tool result carries what the step actually produced')

// The fence is real: without the owner as caller the read would have thrown,
// leaving percent null. The fake registry records what caller was used.
const read = jobRecords.get('bash-1').reads.at(-1)
assert.equal(read.caller, 'session-root')
ok('the output ring is read with the owning session as caller')

const logResponse = await (await fetch(url('/live-console/log?job=bash-1'))).json()
assert.ok(logResponse.text.includes('training'))
assert.equal(logResponse.status, 'running')
ok('the per-job log endpoint returns live output')

// ── SSE snapshot ────────────────────────────────────────────────────────────
const controller = new AbortController()
const stale = await fetch(url('/live-console/events'))
assert.equal(stale.status, 426)
ok('a page from an older host version is refused its stream')

const sse = await fetch(`${url('/live-console/events')}&v=${emptyState.version}`, { signal: controller.signal })
assert.equal(sse.status, 200)
const reader = sse.body.getReader()
const first = await reader.read()
const firstChunk = new TextDecoder().decode(first.value)
assert.ok(firstChunk.includes('event: snapshot'))
controller.abort()
ok('the SSE route opens with a snapshot event')

// ── settle the job: 100% and a recorded history sample ──────────────────────
const finishedAt = Date.now()
jobRecords.get('bash-1').text += 'done\n'
emitJob({
  type: 'settled',
  job: { ...baseView, status: 'completed', finishedAt },
  cause: 'producer',
  awaited: false,
})
await wait(800)
const settledState = await (await fetch(url('/live-console/state'))).json()
const settledJob = settledState.jobs.find((job) => job.id === 'bash-1')
assert.equal(settledJob.percent, 100)
assert.equal(settledJob.progressSource, 'settled')
assert.equal(settledJob.status, 'completed')
ok('a settled job reports 100% and its final status')

await wait(1_800)
const historyDoc = JSON.parse(await readFile(statePath, 'utf8'))
assert.equal(Object.keys(historyDoc.entries).length, 1)
ok('a completed run is persisted to the history file')

// ── a second run of the same command gets a history estimate ────────────────
const secondStartedAt = Date.now()
jobRecords.set('bash-2', { owner: 'session-root', text: 'loading…\n', reads: [] })
emitJob({
  type: 'registered',
  job: { ...baseView, id: 'bash-2', label: 'python sim.py', startedAt: secondStartedAt },
})
emitJob({ type: 'output', id: 'bash-2', total: 9 })
await wait(700)
const estimateState = await (await fetch(url('/live-console/state'))).json()
const estimateJob = estimateState.jobs.find((job) => job.id === 'bash-2')
assert.ok(estimateJob !== undefined)
assert.ok(estimateJob.percent !== null)
assert.ok(String(estimateJob.progressSource).startsWith('estimate'))
ok('a repeated command gets a history-based estimate')

// ── a brand-new silent command falls back to the activity tier ──────────────
jobRecords.set('bash-3', { owner: 'session-root', text: '', reads: [] })
emitJob({
  type: 'registered',
  job: { ...baseView, id: 'bash-3', label: 'some-unique-command-xyz', startedAt: Date.now() },
})
await wait(500)
const activityState = await (await fetch(url('/live-console/state'))).json()
const activityJob = activityState.jobs.find((job) => job.id === 'bash-3')
assert.equal(activityJob.percent, null)
assert.equal(activityJob.progressSource, 'activity')
ok('a brand-new silent command reports the activity tier, not a fake percentage')

// ── progress written to a redirected output file ────────────────────────────
jobRecords.set('bash-4', { owner: 'session-root', text: '', reads: [] })
emitJob({
  type: 'registered',
  job: { ...baseView, id: 'bash-4', label: 'python train.py > run.log', startedAt: Date.now() },
})
await writeFile(join(tempHome, 'run.log'), 'epoch 1\n[progress 4/10] training…\n', 'utf8')
await wait(800)
const fileState = await (await fetch(url('/live-console/state'))).json()
const fileJob = fileState.jobs.find((job) => job.id === 'bash-4')
assert.equal(fileJob.percent, 40)
assert.equal(fileJob.progressSource, 'file')
assert.ok(String(fileJob.lastLine).includes('training'))
ok('progress redirected to an output file is tailed and parsed')

// ── teardown ────────────────────────────────────────────────────────────────
teardown()
for (const cleanup of cleanups) {
  try {
    cleanup()
  } catch {
    /* idempotent teardown */
  }
}
await new Promise((resolve) => server.close(resolve))
await rm(tempHome, { recursive: true, force: true })
ok('the plugin tears down and the test carrier closes')

console.log('')
console.log(`all console checks passed (${passed} assertions)`)
