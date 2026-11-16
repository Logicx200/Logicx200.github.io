/**
 * Standalone preview server for the live console page.
 *
 * It runs the real plugin against a stub context and a real HTTP server, with
 * simulated jobs covering all three progress tiers:
 *   - explicit progress parsed from command output,
 *   - a history estimate for a repeated command,
 *   - an activity bar for a silent command.
 *
 * Useful for iterating on the HTML without reloading the DSH host process:
 *
 *   node scripts/demo.mjs [--port 4622] [--open]
 *
 * Then open http://127.0.0.1:4622/live-console
 */

import http from 'node:http'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { apply } from '../src/index.mjs'

const argv = process.argv.slice(2)
const portIndex = argv.indexOf('--port')
const port = portIndex >= 0 ? Number(argv[portIndex + 1]) : 4622
const shouldOpen = argv.includes('--open')

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

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
await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${port}`

/** @type {Set<(event: any) => void>} */
const jobListeners = new Set()
/** @type {Map<string, { owner?: string, text: string }>} */
const jobRecords = new Map()

const jobs = {
  events: {
    subscribe(_filter, listener) {
      jobListeners.add(listener)
      return () => jobListeners.delete(listener)
    },
  },
  readAt(id, from, caller) {
    const record = jobRecords.get(id)
    if (record === undefined) throw new Error(`unknown job ${id}`)
    if (record.owner !== undefined && caller !== record.owner) throw new Error(`job ${id} belongs to another session`)
    const buffer = Buffer.from(record.text, 'utf8')
    const start = Math.max(0, Math.min(from, buffer.length))
    const tail = buffer.subarray(start).toString('utf8')
    return { chunks: tail.length > 0 ? [{ text: tail, at: Date.now() }] : [], next: buffer.length, lossy: false }
  },
}

const emitJob = (event) => {
  for (const listener of [...jobListeners]) listener(event)
}

/** @type {Map<string, Function[]>} */
const hostListeners = new Map()
const ctx = {
  jobs,
  webServer: {
    getOrigin: () => origin,
    register(route) {
      routes.set(route.path, route.handler)
      return () => routes.delete(route.path)
    },
  },
  systemPrompt: { section: () => () => {} },
  effect(fn) {
    const result = fn()
    return () => {
      if (typeof result === 'function') result()
    }
  },
  inject(_deps, callback) {
    callback(ctx)
  },
  on(name, listener) {
    const list = hostListeners.get(name) ?? []
    list.push(listener)
    hostListeners.set(name, list)
    return () => {}
  },
  logger: { warn() {} },
}

const emitHost = (name, ...args) => {
  for (const listener of [...(hostListeners.get(name) ?? [])]) listener(...args)
}

apply(ctx, {
  autoOpen: 'never',
  updateMs: 400,
  history: true,
  historyPath: join(tmpdir(), 'dsh-live-console-demo-history.json'),
  capability: 'demo-console-key-123',
  route: '/live-console',
})

const now = Date.now()
const sessionA = {
  id: 'session-demo-a1b2c3d4-1111-2222-3333-444455556666',
  header: { id: 'session-demo-a1b2c3d4-1111-2222-3333-444455556666', cwd: 'F:\\DeepSeek工作区', createdAt: now - 900_000 },
}
const sessionB = {
  id: 'session-demo-b7c8d9e0-aaaa-bbbb-cccc-ddddeeeeffff',
  header: { id: 'session-demo-b7c8d9e0-aaaa-bbbb-cccc-ddddeeeeffff', cwd: 'F:\\DeepSeek工作区\\irsim', createdAt: now - 3_600_000 },
}
const emitSession = (session, type, data, seq) =>
  emitHost('session/event', session, { type, seq, time: Date.now(), data })
const view = (id, label, owner, startedAt, status = 'running', finishedAt = null) => ({
  id,
  kind: 'pwsh',
  label,
  owner,
  status,
  startedAt,
  finishedAt: status === 'running' ? null : finishedAt,
  output: { total: 0, earliest: 0 },
})

emitSession(sessionA, 'session/title', { title: '检查两个文件夹' }, 1)
emitSession(sessionA, 'user/message', { role: 'user', content: [{ type: 'text', text: '把两个插件的状态检查一下' }] }, 2)
emitSession(sessionA, 'turn/start', { turn: 3 }, 3)
emitSession(sessionA, 'step/start', { turn: 3, step: 2 }, 4)
emitSession(sessionA, 'tool/call', { turn: 3, step: 2, callId: 'call-a1', name: 'pwsh', arguments: JSON.stringify({ command: 'python run_sim.py --steps 500' }) }, 5)

emitSession(sessionB, 'session/title', { title: '红外目标探测仿真' }, 1)
emitSession(sessionB, 'tool/call', { turn: 7, step: 1, callId: 'call-b1', name: 'pwsh', arguments: JSON.stringify({ command: 'python irsim/run.py' }) }, 2)

// A finished run first, so the console has a duration/output sample to estimate.
jobRecords.set('pwsh-hist', { owner: sessionA.id, text: 'step 400/500\ndone\n' })
emitJob({ type: 'registered', job: view('pwsh-hist', 'python run_sim.py --steps 500', sessionA.id, now - 24_000) })
await wait(900)
emitJob({ type: 'settled', job: view('pwsh-hist', 'python run_sim.py --steps 500', sessionA.id, now - 24_000, 'completed', now - 4_000), cause: 'producer', awaited: false })
await wait(1_200)

// Explicit progress: 24%.
jobRecords.set('pwsh-explicit', { owner: sessionA.id, text: 'booting model\n[progress 120/500] step 120/500\n' })
emitJob({ type: 'registered', job: view('pwsh-explicit', 'python run_sim.py --steps 500', sessionA.id, now - 9_000) })

// History estimate: same command, no explicit progress.
jobRecords.set('pwsh-estimate', { owner: sessionA.id, text: 'loading checkpoint…\n' })
emitJob({ type: 'registered', job: view('pwsh-estimate', 'python run_sim.py --steps 500', sessionA.id, now - 7_000) })

// Activity tier: silent command.
jobRecords.set('pwsh-silent', { owner: sessionA.id, text: '' })
emitJob({ type: 'registered', job: view('pwsh-silent', 'ffmpeg -i demo.mp4 -c:v libx264 -crf 20 out.mp4', sessionA.id, now - 12_000) })

// Second session: explicit step ratio 45%.
jobRecords.set('pwsh-b', { owner: sessionB.id, text: 'frame 45/100 rendered\n' })
emitJob({ type: 'registered', job: view('pwsh-b', 'python irsim/run.py', sessionB.id, now - 15_000) })

console.log(`live-console demo: ${origin}/live-console?k=demo-console-key-123`)
console.log('Ctrl+C to stop.')

if (shouldOpen) {
  const { spawn } = await import('node:child_process')
  spawn('cmd.exe', ['/d', '/s', '/c', 'start', '""', `${origin}/live-console?k=demo-console-key-123`], { detached: true, stdio: 'ignore', windowsHide: true }).unref()
}
