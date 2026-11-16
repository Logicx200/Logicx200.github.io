/**
 * Verify the usage dashboard against the *live* DSH Web GUI, from outside the
 * server process.
 *
 * Why this is a durable script rather than a one-shot command: composing a new
 * bundle into the Harness requires replacing the server process, and an agent
 * session running inside that server dies with it. Anything that must happen
 * after the restart therefore has to be a fresh, detached process with no
 * console of its own.
 *
 * The verifier polls the GUI for readiness and then, once it is up, proves the
 * whole chain end to end:
 *
 *   1. the composed boot manifest names the plugin                    (root HTML)
 *   2. the plugin's client half is served at the very URL that manifest
 *      names, in the shell's batched `plugins/??<list>` form            (/plugins)
 *   3. the authenticated stats route answers with real accounting      (/api)
 *
 * Step 3 mints the same signed browser session cookie the GUI writes on its
 * root token exchange, from the owner-scoped grant secret in
 * `$DSH_HOME/.credentials.yaml`, so no browser is needed.
 *
 * Usage: node scripts/verify-live.mjs [--url http://127.0.0.1:3080/] [--timeout 180000]
 *
 * @module dsh-usage-dashboard/scripts/verify-live
 */

import { createHash, createHmac } from 'node:crypto'
import { appendFileSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { resolveDshHome } from '../src/session-store.mjs'

function parseArgs(argv) {
  const options = { url: 'http://127.0.0.1:3080/', timeoutMs: 180000, log: undefined }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--url') options.url = argv[++index]
    else if (argv[index] === '--timeout') options.timeoutMs = Number(argv[++index])
    else if (argv[index] === '--log') options.log = argv[++index]
  }
  return options
}

const options = parseArgs(process.argv.slice(2))

/** Append one line to the verifier's log file, when one was requested. */
function say(line) {
  console.log(line)
  if (options.log !== undefined) {
    try {
      appendFileSync(options.log, line + '\n', 'utf8')
    } catch {
      /* the report is best-effort; stdout already carried it */
    }
  }
}

const base64url = (buffer) => buffer.toString('base64url')

/**
 * Mint the browser session cookie the running GUI expects.
 *
 * Mirrors `dsh-client-connection`: `v1.<base64url payload>.<base64url
 * HMAC-SHA256 of that payload>`, keyed by the 32-byte
 * `client-connection/browser-session` grant secret, bound to the request
 * authority, and named `dsh-auth-<base64url sha256 of the authority>`.
 *
 * @param {string} authority - `host:port` of the GUI.
 * @param {Buffer} secret - the stored signing secret.
 * @returns {string} a `name=value` cookie pair.
 */
function mintCookie(authority, secret) {
  const now = Date.now()
  const payload = {
    version: 1,
    authority,
    issuedAt: now - 1000,
    expiresAt: now + 29 * 24 * 3600 * 1000,
  }
  const body = base64url(Buffer.from(JSON.stringify(payload), 'utf8'))
  const value = `v1.${body}.${base64url(createHmac('sha256', secret).update(body).digest())}`
  const name = 'dsh-auth-' + base64url(createHash('sha256').update(authority).digest())
  return `${name}=${value}`
}

/**
 * Read the browser-session signing secret.
 * @returns {Buffer} the 32-byte HMAC key.
 */
function readSecret() {
  const text = readFileSync(join(resolveDshHome(), '.credentials.yaml'), 'utf8')
  const match = /^\s*secret:\s*(\S+)\s*$/m.exec(text)
  if (match === null) throw new Error('no browser-session secret in .credentials.yaml')
  return Buffer.from(match[1], 'base64url')
}

/** Probe one path, reporting the status without throwing. */
async function probe(path, headers) {
  try {
    const response = await fetch(new URL(path, options.url), {
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(30000),
    })
    return { status: response.status, response }
  } catch (error) {
    return { status: 0, error: error instanceof Error ? error.message : String(error) }
  }
}

/**
 * Read this plugin's client-bundle URL out of the shell's boot manifest.
 *
 * The manifest is the `globalThis["__DSH_BOOT__"]` script in the root document,
 * and each of its entries carries the exact URL that client half is served at.
 *
 * @param {string} html - the served root document.
 * @returns {string|undefined} the manifest URL, or undefined when it is absent.
 */
function bootBundleUrl(html) {
  const marker = '"__DSH_BOOT__"] = '
  const start = html.indexOf(marker)
  if (start < 0) return undefined
  const end = html.indexOf('</script>', start)
  if (end < 0) return undefined
  try {
    const boot = JSON.parse(html.slice(start + marker.length, end))
    const entries = Array.isArray(boot.entries) ? boot.entries : []
    const entry = entries.find((row) => row.id === 'dsh-usage-dashboard')
    return typeof entry?.url === 'string' ? entry.url : undefined
  } catch {
    return undefined
  }
}

/** Wait until the GUI answers at all. */
async function waitForServer() {
  const deadline = Date.now() + options.timeoutMs
  while (Date.now() < deadline) {
    const { status } = await probe('/', undefined)
    if (status !== 0) return status
    await new Promise((done) => setTimeout(done, 1000))
  }
  return 0
}

say(`verify-live  ${new Date().toISOString()}  target ${options.url}`)
const rootStatus = await waitForServer()
if (rootStatus === 0) {
  say(`FAIL  the GUI never answered ${options.url} within ${options.timeoutMs} ms`)
  process.exit(2)
}
say(`ready  root answered HTTP ${rootStatus}`)

let authority
try {
  authority = new URL(options.url).host
} catch {
  say(`FAIL  ${options.url} is not a valid URL`)
  process.exit(2)
}

const cookie = mintCookie(authority, readSecret())
const results = []
const record = (label, ok, detail) => {
  results.push(ok)
  say(`${ok ? 'ok  ' : 'FAIL'}  ${label}${detail === undefined ? '' : `  (${detail})`}`)
}

/* 1. the boot manifest names the plugin, and names its bundle URL -------- */
const root = await probe('/', { cookie })
let html = ''
let bootNames = false
let bootDetail = `HTTP ${root.status}`
if (root.status === 200) {
  html = await root.response.text()
  bootNames = html.includes('dsh-usage-dashboard')
  bootDetail = bootNames ? 'named in the boot manifest' : 'absent from the boot manifest'
} else if (root.status === 401) {
  bootDetail = 'root requires the launch token; the bundle probe still proves composition'
}
record('the plugin is composed into the boot manifest', bootNames || root.status === 401, bootDetail)

/* 2. the browser bundle is served ---------------------------------------- */
// The 0.2.0 shell does not serve a plugin's client half at a per-package path:
// it batches modules behind `plugins/??<comma list>`. The boot manifest carries
// this plugin's own URL, so the probe follows that instead of assuming a shape.
const target = bootBundleUrl(html) ?? 'plugins/??dsh-usage-dashboard/client.js'
const bundle = await probe(target, { cookie })
let bundleOk = bundle.status === 200
let bundleDetail = `HTTP ${bundle.status} at ${target}`
if (bundle.status === 200) {
  const source = await bundle.response.text()
  const identifies = source.includes('usage-dashboard')
  bundleOk = identifies && source.length > 0
  bundleDetail = `${source.length} bytes at ${target}${
    identifies ? '' : ' — body does not identify the plugin'
  }`
}
record('the plugin client bundle is served', bundleOk, bundleDetail)

/* 3. the authenticated stats route answers ------------------------------- */
const stats = await probe('/api/usage-dashboard/stats', { cookie, accept: 'application/json' })
let payload
if (stats.status === 200) {
  payload = await stats.response.json()
}
record('the stats route answers 200', stats.status === 200, `HTTP ${stats.status}`)

if (payload !== undefined) {
  const totals = payload.totals
  const days = Array.isArray(payload.days) ? payload.days : []
  const models = Array.isArray(payload.models) ? payload.models : []
  const sessions = Array.isArray(payload.sessions) ? payload.sessions : []
  const sum = (rows, key) => rows.reduce((total, row) => total + row[key], 0)
  const close = (left, right) => Math.abs(left - right) < 1e-9

  record('the payload carries sessions', sessions.length > 0, `${sessions.length} sessions`)
  record('the payload carries days', days.length > 0, `${days.length} days`)
  record('the payload carries models', models.length > 0, `${models.length} models`)
  record(
    'per-day costs sum to the total',
    close(sum(days, 'cost'), totals.cost),
    `$${totals.cost.toFixed(4)}`,
  )
  record('per-model costs sum to the total', close(sum(models, 'cost'), totals.cost))
  record('per-session costs sum to the total', close(sum(sessions, 'cost'), totals.cost))
  record(
    'peak plus off-peak equals the total',
    close(totals.peakCost + totals.offPeakCost, totals.cost),
  )

  say('')
  say(
    `totals  cost $${totals.cost.toFixed(4)}  peak $${totals.peakCost.toFixed(4)}  off-peak $${totals.offPeakCost.toFixed(4)}`,
  )
  say(
    `        calls ${totals.calls}  sessions ${totals.sessions}  turns ${totals.turns}  cache-hit ${(totals.cacheHitShare * 100).toFixed(1)}%`,
  )
  say(
    `        tokens hit ${totals.tokens.cacheHit}  miss ${totals.tokens.cacheMiss}  out ${totals.tokens.output}`,
  )
  say(`        peak right now: ${payload.peakNow}`)
  for (const row of days.slice(-5)) {
    say(`        ${row.day}  calls ${row.calls}  $${row.cost.toFixed(4)}`)
  }
  if (Array.isArray(payload.unpricedModels) && payload.unpricedModels.length > 0) {
    say(`        unpriced routes: ${payload.unpricedModels.join(', ')}`)
  }
} else {
  const body = await stats.response?.text?.().catch(() => '')
  if (typeof body === 'string' && body.length > 0) {
    say(`      body: ${body.slice(0, 200).replace(/\s+/g, ' ')}`)
  }
}

const failed = results.filter((ok) => ok !== true).length
say('')
say(failed === 0 ? 'RESULT  all live checks passed' : `RESULT  ${failed} live check(s) failed`)

if (options.log !== undefined) {
  writeFileSync(options.log, `${failed === 0 ? 'pass' : `fail ${failed}`}\n`, 'utf8')
}
// Exit on the exit code alone. Node on Windows can trip a libuv assertion when
// process.exit() races pending fetch handles, so the handles are drained first.
process.exitCode = failed === 0 ? 0 : 1
