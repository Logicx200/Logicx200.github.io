/**
 * Dev-only: click the first visible graph label's node, then verify the detail
 * panel opened and save a screenshot.
 *
 *   node scripts/graph-interact.mjs --url <graph-url> --out <png>
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
  console.error('usage: node scripts/graph-interact.mjs --url <graph-url> [--out screenshot.png]')
  process.exit(2)
}
const outPath = option('out', join(process.cwd(), 'graph-interact.png'))
const waitMs = Number(option('wait', '8000'))
const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const port = 9444
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const profile = join(tmpdir(), `dsh-graph-interact-${process.pid}`)
const edge = spawn(edgePath, [
  '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-extensions',
  '--disable-background-networking', '--no-first-run', '--no-default-browser-check',
  '--hide-scrollbars', '--window-size=1600,1000', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, 'about:blank',
], { stdio: 'ignore', windowsHide: true })
const cleanup = () => { try { edge.kill() } catch { /* gone */ } }

let wsUrl
for (let attempt = 0; attempt < 60; attempt += 1) {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json/version`)
    if (response.ok) {
      const created = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })
      wsUrl = (await created.json()).webSocketDebuggerUrl
      break
    }
  } catch { /* not ready */ }
  await wait(250)
}
if (wsUrl === undefined) { cleanup(); console.error('edge devtools never became ready'); process.exit(1) }

const pending = new Map()
let nextId = 0
const socket = new WebSocket(wsUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})
socket.addEventListener('message', (event) => {
  let message
  try { message = JSON.parse(event.data) } catch { return }
  if (typeof message.id === 'number') {
    const waiter = pending.get(message.id)
    if (!waiter) return
    pending.delete(message.id)
    if (message.error) waiter.reject(new Error(JSON.stringify(message.error)))
    else waiter.resolve(message.result)
  }
})
const send = (method, params = {}) => new Promise((resolve, reject) => {
  nextId += 1
  pending.set(nextId, { resolve, reject })
  socket.send(JSON.stringify({ id: nextId, method, params }))
})

await send('Page.enable')
await send('Runtime.enable')
await send('Page.navigate', { url })
await wait(waitMs)

const clicked = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const graph = window.__dshGraph;
    if (!graph) return { ok: false, reason: 'no debug hook' };
    const node = graph.state.nodes.slice().sort((a, b) => (b._scale || 1) - (a._scale || 1))[0];
    const point = graph.toScreen(node.x, node.y);
    const canvas = document.getElementById('canvas');
    const rect = canvas.getBoundingClientRect();
    const x = rect.left + point.x;
    const y = rect.top + point.y;
    canvas.dispatchEvent(new PointerEvent('pointerdown', { clientX: x, clientY: y, bubbles: true, pointerId: 1 }));
    window.dispatchEvent(new PointerEvent('pointerup', { clientX: x, clientY: y, bubbles: true, pointerId: 1 }));
    return { ok: true, x, y, node: node.title };
  })()`,
})
await wait(700)
const result = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const graph = window.__dshGraph;
    const selected = graph && graph.state.selected ? graph.state.byId.get(graph.state.selected) : null;
    return {
      asideOpen: document.querySelector('aside').classList.contains('open'),
      detailTitle: document.querySelector('aside h2')?.textContent ?? '',
      detailKeywords: document.querySelectorAll('aside .kw button').length,
      detailConnections: document.querySelectorAll('aside .connection').length,
      canvasWidth: document.getElementById('canvas').width,
      labelCount: document.querySelectorAll('.node-label.show').length,
      selected: selected ? { title: selected.title, kind: selected.kind, x: selected.x, y: selected.y, scale: selected._scale, screen: graph.toScreen(selected.x, selected.y) } : null,
      view: graph ? graph.state.view : null,
      size: graph ? { width: graph.state.width, height: graph.state.height } : null
    };
  })()`,
})
console.log('clicked', JSON.stringify(clicked.result?.value ?? {}))
console.log('result', JSON.stringify(result.result?.value ?? {}, null, 2))
const screenshot = await send('Page.captureScreenshot', { format: 'png' })
mkdirSync(dirname(outPath), { recursive: true })
writeFileSync(outPath, Buffer.from(screenshot.data, 'base64'))
console.log(`screenshot: ${outPath}`)
try { socket.close() } catch { /* ignore */ }
cleanup()
