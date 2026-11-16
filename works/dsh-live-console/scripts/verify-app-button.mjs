/**
 * Dev check: load the real DSH app page in headless Edge with a minted browser
 * cookie, then report whether the "控制台" header action from the
 * dsh-live-console-ui client bundle actually rendered. This simulates the page
 * refresh a user needs after the client bundle is hot-composed.
 *
 *   node scripts/verify-app-button.mjs [--out app-button.png]
 */

import { spawn } from 'node:child_process'
import { createHash, createHmac } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { dirname, join } from 'node:path'

const argv = process.argv.slice(2)
const option = (name, fallback) => {
  const index = argv.indexOf(`--${name}`)
  return index >= 0 ? argv[index + 1] : fallback
}
const outPath = option('out', join(process.cwd(), 'app-button.png'))
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const port = 9336
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const home = process.env.DSH_HOME ?? join(homedir(), '.dsh')
const secret = Buffer.from(/^\s*secret:\s*(\S+)\s*$/m.exec(readFileSync(join(home, '.credentials.yaml'), 'utf8'))[1], 'base64url')
const base64url = (buffer) => buffer.toString('base64url')
const authority = '127.0.0.1:4620'
const now = Date.now()
const payload = { version: 1, authority, issuedAt: now - 1000, expiresAt: now + 29 * 24 * 3600 * 1000 }
const body = base64url(Buffer.from(JSON.stringify(payload), 'utf8'))
const cookieValue = `v1.${body}.${base64url(createHmac('sha256', secret).update(body).digest())}`
const cookieName = 'dsh-auth-' + base64url(createHash('sha256').update(authority).digest())

const edge = spawn(edgePath, [
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-extensions',
  '--disable-background-networking',
  '--no-first-run',
  '--no-default-browser-check',
  '--hide-scrollbars',
  '--window-size=1500,950',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${join(tmpdir(), `dsh-app-check-${process.pid}`)}`,
  'about:blank',
], { stdio: 'ignore', windowsHide: true })

const cleanup = () => {
  try {
    edge.kill()
  } catch {
    /* gone */
  }
}

let wsUrl
for (let attempt = 0; attempt < 60; attempt += 1) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/version`)
    if (response.ok) {
      const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json()
      wsUrl = target.webSocketDebuggerUrl
      break
    }
  } catch {
    /* not ready */
  }
  await wait(250)
}
if (wsUrl === undefined) {
  cleanup()
  console.error('edge devtools never became ready')
  process.exit(1)
}

const pending = new Map()
let nextId = 0
const socket = new WebSocket(wsUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data)
  if (typeof message.id !== 'number') return
  const waiter = pending.get(message.id)
  if (waiter === undefined) return
  pending.delete(message.id)
  if (message.error !== undefined) waiter.reject(new Error(JSON.stringify(message.error)))
  else waiter.resolve(message.result)
})
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    nextId += 1
    pending.set(nextId, { resolve, reject })
    socket.send(JSON.stringify({ id: nextId, method, params }))
  })

await send('Page.enable')
await send('Runtime.enable')
await send('Network.enable')
await send('Network.setCookie', {
  name: cookieName,
  value: cookieValue,
  url: 'http://127.0.0.1:4620/',
  path: '/',
  httpOnly: true,
})
await send('Page.navigate', { url: 'http://127.0.0.1:4620/' })
await wait(12000)

const evaluated = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const buttons = [...document.querySelectorAll('button')].map((node) => (node.innerText || node.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim()).filter(Boolean);
    return {
      title: document.title,
      bodyLength: document.body.innerText.length,
      hasConsoleButton: buttons.some((text) => text.includes('控制台')),
      buttons: buttons.slice(0, 30),
    };
  })()`,
})
console.log(JSON.stringify(evaluated.result?.value ?? {}, null, 2))

const screenshot = await send('Page.captureScreenshot', { format: 'png' })
writeFileSync(outPath, Buffer.from(screenshot.data, 'base64'))
console.log(`screenshot: ${outPath}`)
try {
  socket.close()
} catch {
  /* ignore */
}
cleanup()
process.exit(0)
