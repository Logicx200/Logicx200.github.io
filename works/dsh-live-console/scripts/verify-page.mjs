/**
 * Dev-only: render the live console page in headless Edge over the Chrome
 * DevTools Protocol, report what actually rendered, and save a screenshot.
 *
 *   node scripts/verify-page.mjs --url http://127.0.0.1:4622/live-console?k=... --out preview.png
 */

import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { tmpdir } from 'node:os'

const argv = process.argv.slice(2)
const option = (name, fallback) => {
  const index = argv.indexOf(`--${name}`)
  return index >= 0 ? argv[index + 1] : fallback
}
const url = option('url')
if (url === undefined) {
  console.error('usage: node scripts/verify-page.mjs --url <page-url> [--out screenshot.png]')
  process.exit(2)
}
const outPath = option('out', join(process.cwd(), 'console-preview.png'))
const waitMs = Number(option('wait', '2500'))
const openUsage = argv.includes('--open-usage')
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const port = 9333

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const profile = join(tmpdir(), `dsh-console-verify-${process.pid}`)
const edge = spawn(edgePath, [
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--disable-extensions',
  '--disable-background-networking',
  '--no-first-run',
  '--no-default-browser-check',
  '--hide-scrollbars',
  '--window-size=1600,1000',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  'about:blank',
], { stdio: 'ignore', windowsHide: true })

const cleanup = () => {
  try {
    edge.kill()
  } catch {
    /* already gone */
  }
}

let wsUrl
for (let attempt = 0; attempt < 60; attempt += 1) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/version`)
    if (response.ok) {
      const created = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })
      const target = await created.json()
      wsUrl = target.webSocketDebuggerUrl
      break
    }
  } catch {
    /* not ready yet */
  }
  await wait(250)
}
if (wsUrl === undefined) {
  cleanup()
  console.error('edge devtools never became ready')
  process.exit(1)
}

/** @type {Map<number, { resolve: (value: any) => void, reject: (error: Error) => void }>} */
const pending = new Map()
let nextId = 0
const consoleLines = []

const socket = new WebSocket(wsUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

socket.addEventListener('message', (event) => {
  let message
  try {
    message = JSON.parse(event.data)
  } catch {
    return
  }
  if (typeof message.id === 'number') {
    const waiter = pending.get(message.id)
    if (waiter === undefined) return
    pending.delete(message.id)
    if (message.error !== undefined) waiter.reject(new Error(JSON.stringify(message.error)))
    else waiter.resolve(message.result)
    return
  }
  if (message.method === 'Runtime.consoleAPICalled') {
    const text = (message.params.args ?? []).map((arg) => arg.value ?? arg.description ?? '').join(' ')
    consoleLines.push(`${message.params.type}: ${text}`)
  } else if (message.method === 'Runtime.exceptionThrown') {
    consoleLines.push(`exception: ${message.params.exceptionDetails?.text ?? ''}`)
  }
})

/** @param {string} method @param {Record<string, unknown>} [params] */
const send = (method, params = {}) =>
  new Promise((resolve, reject) => {
    nextId += 1
    pending.set(nextId, { resolve, reject })
    socket.send(JSON.stringify({ id: nextId, method, params }))
  })

await send('Page.enable')
await send('Runtime.enable')
await send('Log.enable').catch(() => {})
await send('Page.navigate', { url })
await wait(waitMs)
if (openUsage) {
  await send('Runtime.evaluate', { expression: "document.getElementById('usageBtn') && document.getElementById('usageBtn').click(); 'ok'" })
  await wait(500)
}

const evaluated = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const text = document.body.innerText.replace(/\\s+\\n/g, '\\n');
    const bars = [...document.querySelectorAll('.bar')].map((bar) => ({
      cls: bar.className,
      width: bar.querySelector('i') ? bar.querySelector('i').style.width : null,
    }));
    return {
      title: document.title,
      sessions: [...document.querySelectorAll('.session-item')].map((node) => node.innerText.replace(/\\n/g, ' | ')),
      jobs: [...document.querySelectorAll('.job')].map((node) => ({
        label: node.querySelector('.job-label')?.textContent ?? '',
        status: node.querySelector('.job-status')?.textContent ?? '',
        barLabel: node.querySelector('.bar-label')?.innerText ?? '',
      })),
      bars,
      events: [...document.querySelectorAll('.event .sum')].slice(0, 8).map((node) => node.textContent),
      spend: {
        cardHidden: document.getElementById('usageCard')?.hidden ?? null,
        today: document.getElementById('ucToday')?.textContent ?? '',
        total: document.getElementById('ucTotal')?.textContent ?? '',
        balance: document.getElementById('ucBalance')?.textContent ?? '',
        cache: document.getElementById('ucCache')?.textContent ?? '',
        calls: document.getElementById('ucCalls')?.textContent ?? '',
        peak: document.getElementById('ucPeak')?.textContent ?? '',
        detail: (document.getElementById('usageDetail')?.innerText ?? '').slice(0, 900),
      },
      conn: document.getElementById('connText')?.textContent ?? '',
      textLength: text.length,
    };
  })()`,
})

const summary = evaluated.result?.value ?? {}
console.log(JSON.stringify(summary, null, 2))
if (consoleLines.length > 0) {
  console.log('--- console ---')
  console.log(consoleLines.slice(-20).join('\n'))
}

const screenshot = await send('Page.captureScreenshot', { format: 'png' })
mkdirSync(dirname(outPath), { recursive: true })
writeFileSync(outPath, Buffer.from(screenshot.data, 'base64'))
console.log(`screenshot: ${outPath} (${Buffer.from(screenshot.data, 'base64').length} bytes)`)

try {
  socket.close()
} catch {
  /* ignore */
}
cleanup()
process.exit(0)
