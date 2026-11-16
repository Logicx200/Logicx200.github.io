/**
 * Restart the DSH Web GUI on this machine, from outside the server process.
 *
 * The Harness only reads a profile's `dsh.profile.bundles` at boot, so
 * composing a newly installed bundle layer into the running GUI — rather than
 * only into the next one — means replacing the process. This helper does that
 * without a console of its own: no-op when the GUI already answers, otherwise
 * start the same CLI entry the `dsh` shim uses, hidden, and poll for readiness.
 *
 * It is idempotent on purpose. Twice in a row is safe: the second run sees a
 * live GUI and exits 0 without touching it, which is what makes it safe to run
 * from an agent session that dies with the server.
 *
 * Usage: node scripts/restart-web.mjs [--url http://127.0.0.1:3080/] [--timeout 90000]
 *
 * @module dsh-usage-dashboard/scripts/restart-web
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'

/** Fallback install anchor for the `dsh` CLI when PATH carries no shim. */
const FALLBACK_BIN = 'D:\\Node.js\\node_cache\\_npx\\1e7f6d9597241db0\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js'

function parseArgs(argv) {
  const options = { url: 'http://127.0.0.1:3080/', timeoutMs: 90000 }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--url') options.url = argv[++index]
    else if (argv[index] === '--timeout') options.timeoutMs = Number(argv[++index])
  }
  return options
}

/**
 * Resolve the CLI entry to spawn.
 * @returns {string} path of an existing `dsh` entry script.
 * @throws when neither the shim nor the fallback anchor exists.
 */
function resolveCliEntry() {
  const shim = process.env.DSH_BIN_SHIM
  if (shim !== undefined && existsSync(shim)) return shim
  if (existsSync(FALLBACK_BIN)) return FALLBACK_BIN
  throw new Error(`cannot find the dsh CLI entry (looked for ${FALLBACK_BIN})`)
}

/**
 * Ask the GUI whether it is already serving.
 * @param {string} url - the canonical root URL.
 * @returns {Promise<boolean>} true when an HTTP status of any kind came back.
 */
async function isServing(url) {
  try {
    // 401 is the expected answer without a browser cookie, and still proves the
    // server is up; only a transport failure means "not serving".
    await fetch(url, { signal: AbortSignal.timeout(2000) })
    return true
  } catch {
    return false
  }
}

/**
 * Poll until the GUI answers or the deadline passes.
 * @param {string} url - the canonical root URL.
 * @param {number} timeoutMs - budget in milliseconds.
 * @returns {Promise<boolean>} whether it came up.
 */
async function waitForReady(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await isServing(url)) return true
    await new Promise((done) => setTimeout(done, 750))
  }
  return false
}

const options = parseArgs(process.argv.slice(2))

if (await isServing(options.url)) {
  console.log(`already serving: ${options.url} — nothing to do`)
  process.exit(0)
}

const entry = resolveCliEntry()
console.log(`starting: ${process.execPath} ${entry} web`)
const child = spawn(process.execPath, [entry, 'web'], {
  // Inherit the invoking directory: it becomes the server's cwd, exactly as a
  // hand-launched `dsh web` in that directory would.
  cwd: process.cwd(),
  detached: true,
  stdio: 'ignore',
  windowsHide: true,
})
child.unref()
console.log(`spawned pid ${child.pid}`)

const ready = await waitForReady(options.url, options.timeoutMs)
if (!ready) {
  console.error(`the GUI did not answer ${options.url} within ${options.timeoutMs} ms`)
  process.exit(1)
}

// The launching browser tab is only opened by the server's own startup path;
// this helper cannot reach the OS opener, so it prints the canonical URL the
// plugin's dashboard is reachable at once the page has its session cookie.
console.log(`ready: ${options.url}`)
