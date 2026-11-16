/**
  * Host half of DSH Live Console — and its only half.
 *
 * It serves one self-contained HTML page from the DSH web carrier (the same
 * listener the GUI uses), plus the JSON/SSE/log endpoints that page consumes.
 * The page is deliberately not a client plugin: it is an ordinary browser tab,
 * reachable at `<gui-origin>/live-console`, and it auto-follows whichever
 * conversation is most recently active.
 *
 * Three data sources feed it, all observed from the host side:
 *
 *   - `ctx.jobs` — every background/foreground command the harness runs is a
 *     job with an output ring. The console reads the ring with the owning
 *     session as `caller` (the registry's isolation fence), so it sees live
 *     output without touching the model's own read cursor.
 *   - `session/event` — the post-commit durable event feed, used for the
 *     conversation timeline, titles, turn/step state, and tool calls.
 *   - `api-session/*` — the live session registry, used for the session list and
 *     running state. Subagent sessions are marked and hidden by default.
 *
 * Progress is the three-tier model in `progress.mjs`: explicit output progress,
 * then a history-based estimate (the same command's median duration/output size),
 * then an activity bar. Nothing pretends to be exact: the page labels the tier.
 *
 * The plugin also registers one global `systemPrompt` section. It tells every
 * agent how to make long commands observable (`[progress 3/10]` / `42%`), so the
 * explicit tier gets used without the user having to ask each conversation.
 *
 * Robustness rules, learned from the bridge plugin:
 *   - every event handler, tick, ring read, and write is contained;
 *   - a repeated failure logs once and the plugin keeps running;
 *   - route handlers never throw into the carrier;
 *   - the page route is loopback-only unless explicitly configured otherwise.
 *
 * @module dsh-live-console
 */

import { spawn } from 'node:child_process'
import { randomBytes, randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, isAbsolute, join } from 'node:path'

import {
  ProgressHistory,
  deriveEta,
  progressFromLine,
  progressFromText,
  signatureOf,
  stripAnsi,
} from './progress.mjs'
import { extractProgressTargets, readFileTail } from './file-progress.mjs'
import { collectUsage } from './usage-stats.mjs'
import { collectConversationGraph } from './graph.mjs'
import { buildContextArchive } from './context-archive.mjs'
import { readBalance } from './balance.mjs'

/** Cordis plugin identity: must match the loader row's `id`/`name` linkage. */
export const name = 'live-console'

/**
 * The only service that is required: the job registry. The web carrier and the
 * system-prompt registry are injected optionally, so the plugin still tracks
 * events (and still adds its prompt section) in compositions that serve no GUI.
 */
export const inject = ['jobs']

/** Default loader-row configuration. */
const DEFAULTS = {
  route: '/live-console',
  autoOpen: 'auto',
  openDelayMs: 2_500,
  progressPrompt: true,
  keepSettledMs: 60_000,
  maxLogBytes: 256 * 1024,
  history: true,
  fileProgress: true,
  usage: true,
  usageRefreshMs: 120_000,
  usdToCny: 7.1,
  balance: true,
  balanceRefreshMs: 60_000,
  allowNonLoopback: false,
  updateMs: 700,
  pageTitle: 'DSH Live Console',
  injectedLink: true,
}

/** Page/SSE protocol version; bump when the served HTML changes shape. */
const PAGE_VERSION = '8'


/** Headers shared by every console response. */
const SECURITY_HEADERS = {
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'no-referrer',
  'x-frame-options': 'DENY',
}

/** The console page's CSP: inline styling/scripting only, no network beyond itself. */
const PAGE_CSP =
  "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:"

/**
 * Injected into the application index page as a small, always-available entry
 * point. It deliberately has no client bundle: an index tap cannot break boot,
 * and it asks the authenticated host route for the console URL before opening.
 */
// The desktop shell consumes structured `webserver/index-inject` rows, not
// raw index taps; `LINK_JS` is the row body and `LINK_SCRIPT` the HTTP-page form.
const LINK_JS = `(function () {
  if (window.__dshLiveConsoleLink === true) return;
  window.__dshLiveConsoleLink = true;
  function install() {
    if (document.getElementById('dsh-live-console-link')) return;
    var button = document.createElement('button');
    button.id = 'dsh-live-console-link';
    button.type = 'button';
    button.textContent = '控制台';
    button.title = '打开 DSH Live Console（日志 / 进度 / 花费）';
    button.setAttribute('aria-label', '打开 DSH Live Console');
    button.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:2147483647;padding:6px 12px;border-radius:999px;border:1px solid rgba(125,125,125,.55);background:rgba(20,24,30,.85);color:#e6edf3;font:12px/1.4 system-ui;cursor:pointer;backdrop-filter:blur(6px);box-shadow:0 4px 16px rgba(0,0,0,.3);opacity:.86';
    button.onmouseenter = function () { button.style.opacity = '1'; };
    button.onmouseleave = function () { button.style.opacity = '.86'; };
    button.onclick = function () {
      button.disabled = true;
      fetch('/api/live-console/url', { credentials: 'same-origin', headers: { accept: 'application/json' } })
        .then(function (response) { return response.json(); })
        .then(function (body) { if (body && typeof body.url === 'string' && body.url.length > 0) window.open(body.url, '_blank', 'noopener,noreferrer'); })
        .catch(function () {})
        .finally(function () { button.disabled = false; });
    };
    document.body.appendChild(button);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();`;
const LINK_SCRIPT = `<script data-dsh-live-console-link><script data-dsh-live-console-link>
(function () {
  if (window.__dshLiveConsoleLink === true) return;
  window.__dshLiveConsoleLink = true;
  function install() {
    if (document.getElementById('dsh-live-console-link')) return;
    var button = document.createElement('button');
    button.id = 'dsh-live-console-link';
    button.type = 'button';
    button.textContent = '控制台';
    button.title = '打开 DSH Live Console（日志 / 进度 / 花费）';
    button.setAttribute('aria-label', '打开 DSH Live Console');
    button.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:2147483647;padding:6px 12px;border-radius:999px;border:1px solid rgba(125,125,125,.55);background:rgba(20,24,30,.85);color:#e6edf3;font:12px/1.4 system-ui;cursor:pointer;backdrop-filter:blur(6px);box-shadow:0 4px 16px rgba(0,0,0,.3);opacity:.86';
    button.onmouseenter = function () { button.style.opacity = '1'; };
    button.onmouseleave = function () { button.style.opacity = '.86'; };
    button.onclick = function () {
      button.disabled = true;
      fetch('/api/live-console/url', { credentials: 'same-origin', headers: { accept: 'application/json' } })
        .then(function (response) { return response.json(); })
        .then(function (body) { if (body && typeof body.url === 'string' && body.url.length > 0) window.open(body.url, '_blank', 'noopener,noreferrer'); })
        .catch(function () {})
        .finally(function () { button.disabled = false; });
    };
    document.body.appendChild(button);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
</script>`

/** How long one browser-open attempt is remembered, to avoid duplicate tabs. */
const OPEN_THROTTLE_MS = 20_000

/** Maximum number of durable events kept in memory. */
const MAX_EVENTS = 5_000

/** Most recent events included in one initial snapshot. */
const SNAPSHOT_EVENTS = 400

/** Durable session event types worth showing in the conversation timeline. */
const INFORMATIVE_EVENTS = new Set([
  'session/title',
  'turn/start',
  'turn/end',
  'step/start',
  'step/end',
  'user/message',
  'assistant/message',
  'tool/call',
  'tool/result',
  'job/registered',
  'job/settled',
])

/** System-prompt section: keeps the automatic progress convention short. */
const PROGRESS_INSTRUCTION = [
  '## Live progress reporting',
  'The user watches a live console that mirrors every command you run. When a command or script is likely to run longer than about 10 seconds, make its progress observable:',
  '- If you control the program/script, print a short progress line to stdout at least every few seconds, in one of these forms: `[progress 3/10]`, `step 3/10`, or `42%`. Keep the numbers truthful and monotonic.',
  '- If you do not control the program, do not fake progress; the console will show elapsed time and an estimate based on previous runs of the same command.',
  '- If the command writes its output to a file (`> run.log`, `-OutFile out.txt`), make sure the progress lines are written there as well; the console tails that file too.',
  'Never invent percentages; an honest activity indicator is better.',
].join('\n')

/**
 * Resolve the Harness home directory, matching host-side convention.
 * @returns {string} absolute `$DSH_HOME`.
 */
export function resolveDshHome() {
  const configured = process.env.DSH_HOME
  return typeof configured === 'string' && configured.length > 0 ? configured : join(homedir(), '.dsh')
}

/**
 * Defer one call.
 * @returns {{ promise: Promise<void>, resolve: () => void }} the deferral.
 */
function createDeferral() {
  let resolve = () => {}
  const promise = new Promise((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

/**
 * Convert one loader-row config object into bounded options.
 * @param {Record<string, unknown>} config - raw loader config.
 * @returns {typeof DEFAULTS & { statePath: string }} normalized options.
 */
export function normalizeOptions(config = {}) {
  const raw = config !== null && typeof config === 'object' ? config : {}
  const number = (value, fallback, min, max) => {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return fallback
    return Math.min(max, Math.max(min, parsed))
  }
  const text = (value, fallback) => (typeof value === 'string' && value.length > 0 ? value : fallback)
  let route = text(raw.route, DEFAULTS.route)
  if (!route.startsWith('/')) route = `/${route}`
  route = route.replace(/\/+$/, '')
  if (route.length === 0) route = DEFAULTS.route
  const autoOpen = ['auto', 'once', 'never'].includes(raw.autoOpen) ? raw.autoOpen : DEFAULTS.autoOpen
  return {
    ...DEFAULTS,
    route,
    autoOpen,
    openDelayMs: number(raw.openDelayMs, DEFAULTS.openDelayMs, 200, 60_000),
    progressPrompt: raw.progressPrompt !== false,
    keepSettledMs: number(raw.keepSettledMs, DEFAULTS.keepSettledMs, 5_000, 24 * 60 * 60 * 1_000),
    maxLogBytes: number(raw.maxLogBytes, DEFAULTS.maxLogBytes, 8_192, 4 * 1024 * 1024),
    history: raw.history !== false,
    fileProgress: raw.fileProgress !== false,
    usage: raw.usage !== false,
    usageRefreshMs: number(raw.usageRefreshMs, DEFAULTS.usageRefreshMs, 15_000, 60 * 60 * 1_000),
    usdToCny: number(raw.usdToCny, DEFAULTS.usdToCny, 0.01, 100),
    balance: raw.balance !== false,
    balanceRefreshMs: number(raw.balanceRefreshMs, DEFAULTS.balanceRefreshMs, 15_000, 60 * 60 * 1_000),
    allowNonLoopback: raw.allowNonLoopback === true,
    updateMs: number(raw.updateMs, DEFAULTS.updateMs, 200, 5_000),
    pageTitle: text(raw.pageTitle, DEFAULTS.pageTitle),
    injectedLink: raw.injectedLink !== false,
    statePath: text(raw.historyPath, join(resolveDshHome(), 'live-console', 'history.json')),
    capability: typeof raw.capability === 'string' && raw.capability.length >= 8 ? raw.capability : undefined,
  }
}

/**
 * Extract plain text from a message content value (string or content blocks).
 * @param {unknown} content - message content.
 * @returns {string} plain text, possibly empty.
 */
function textOfContent(content) {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  let out = ''
  for (const block of content) {
    if (block === null || typeof block !== 'object') continue
    if (block.type === 'text' && typeof block.text === 'string') out += block.text
    else if (block.type === 'reasoning' && typeof block.text === 'string') out += block.text
  }
  return out
}

/**
 * Extract only the model's *visible* reply text: unlike textOfContent it drops
 * reasoning blocks, so the compact conversation panel shows what the user saw.
 * @param {unknown} content - message content.
 * @returns {string} visible text, possibly empty.
 */
function visibleText(content) {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  let out = ''
  for (const block of content) {
    if (block === null || typeof block !== 'object') continue
    if (block.type === 'text' && typeof block.text === 'string') out += block.text
  }
  return out
}

/** Collapse text to one short display line. */
function oneLine(value, max = 160) {
  if (typeof value !== 'string') return ''
  const text = value.replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

/** Strip a session id down to something a human can scan. */
function shortId(value) {
  const text = typeof value === 'string' ? value : ''
  return text.length > 22 ? `${text.slice(0, 8)}…${text.slice(-6)}` : text
}

/**
 * A short Chinese action label for a tool name, so the timeline says what the
 * step *did* rather than which RPC was called.
 * @param {string} name - tool name.
 * @returns {string} display verb.
 */
function toolActionLabel(name) {
  const value = typeof name === 'string' ? name.toLowerCase() : ''
  if (value.includes('web_search')) return '搜索网页'
  if (value.includes('workflow')) return '工作流'
  if (value.includes('subagent') || value.includes('delegate')) return '子代理'
  if (value.includes('schedule')) return '安排任务'
  if (value === 'read' || value.includes('read_file') || value.includes('readfile')) return '读取文件'
  if (value.includes('write')) return '写入文件'
  if (value.includes('edit')) return '修改文件'
  if (value.includes('grep') || value.includes('search') || value.includes('glob') || value.includes('find')) return '搜索'
  if (value.includes('fetch')) return '抓取网页'
  if (value.includes('pwsh') || value.includes('bash') || value.includes('shell') || value.includes('terminal') || value.includes('powershell')) return '运行命令'
  if (value.includes('ask') || value.includes('question')) return '询问用户'
  return '调用工具'
}

/**
 * Format a short duration for one tool call.
 * @param {number} ms - elapsed milliseconds.
 * @returns {string} display duration, or '' when unusable.
 */
function formatMs(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value < 0) return ''
  if (value < 1_000) return `${Math.round(value)}ms`
  const seconds = value / 1_000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m${String(Math.round(seconds % 60)).padStart(2, '0')}s`
}

/**
 * Best preview of a tool call's arguments, without trusting its shape.
 * @param {string} toolName - registered tool name.
 * @param {string} rawArguments - JSON string as logged in the event.
 * @returns {string} display preview.
 */
function toolCallPreview(toolName, rawArguments) {
  let args
  try {
    args = typeof rawArguments === 'string' ? JSON.parse(rawArguments) : rawArguments
  } catch {
    args = undefined
  }
  const keys = ['command', 'cmd', 'script', 'path', 'file_path', 'query', 'pattern', 'url', 'description', 'title']
  if (args !== null && typeof args === 'object') {
    for (const key of keys) {
      if (typeof args[key] === 'string' && args[key].length > 0) return oneLine(args[key], 140)
    }
  }
  const fallback = typeof rawArguments === 'string' ? rawArguments : ''
  return oneLine(fallback, 140)
}

/**
 * Apply the plugin to a host context.
 *
 * @param {any} ctx - the Cordis host context.
 * @param {Record<string, unknown>} [config] - loader-row config.
 * @returns {(() => void) | undefined} disposer, or undefined when inert.
 */
export function apply(ctx, config = {}) {
  const options = normalizeOptions(config)
  const urlPath = join(dirname(options.statePath), 'url.txt')
  const keyPath = join(dirname(options.statePath), 'key.txt')
  /**
   * A stable per-Harness capability key, persisted so a browser tab keeps
   * working across host restarts (and the URL stays bookmarkable).
   * @returns {string | undefined}
   */
  const readPersistedCapability = () => {
    try {
      const text = readFileSync(keyPath, 'utf8').trim()
      return /^[A-Za-z0-9_-]{16,128}$/.test(text) ? text : undefined
    } catch {
      return undefined
    }
  }
  /** Per-process URL capability key; overridable only for tests/demos. */
  const capability = options.capability ?? readPersistedCapability() ?? randomBytes(18).toString('base64url')

  /** @type {((id: string) => any) | undefined} */
  let lookupAgent
  ctx.inject(['agents'], (agentsCtx) => {
    try {
      lookupAgent = (id) => agentsCtx.agents.get(id)
    } catch {
      lookupAgent = undefined
    }
  })
  const jobs = ctx.jobs
  if (jobs === null || jobs === undefined) return undefined
  if (typeof jobs.readAt !== 'function' || jobs.events === null || typeof jobs.events !== 'object') return undefined
  if (typeof jobs.events.subscribe !== 'function') return undefined

  const startedAt = Date.now()
  /** @type {Set<string>} */
  const logged = new Set()
  /** @type {{ promise: Promise<void>, resolve: () => void }} */
  let historyGate = createDeferral()
  historyGate.resolve()
  let historySerial = 0
  // ── usage / spend / balance ───────────────────────────────────────────────
  /** @type {any} */
  let usageView
  /** @type {string | undefined} */
  let usageError
  let usageSweeping = false
  /** @type {Promise<void> | undefined} */
  let usageFlight
  let usageAt = 0
  /** @type {{ ok: boolean, [key: string]: unknown }} */
  let balanceView = { ok: false, error: '余额尚未读取' }
  let balanceAt = 0
  let usageTimer
  let balanceTimer

  /** Round money to micro-dollars to keep JSON small. */
  const money = (value) => Math.round((Number(value) || 0) * 1e6) / 1e6
  /** USD -> the configured CNY rate. */
  const cnyOf = (value) => money((Number(value) || 0) * options.usdToCny)
  /** Keep only the three renderable token buckets. */
  const tokenView = (tokens) => ({
    cacheHit: Math.max(0, Math.round(Number(tokens?.cacheHit) || 0)),
    cacheMiss: Math.max(0, Math.round(Number(tokens?.cacheMiss) || 0)),
    output: Math.max(0, Math.round(Number(tokens?.output) || 0)),
  })

  /** Compact usage block for the page and its SSE feed. */
  const usageSnapshot = () => {
    if (options.usage !== true) {
      return { enabled: false, balance: options.balance === true ? balanceView : null, rate: options.usdToCny }
    }
    if (usageView === undefined) {
      return { enabled: true, sweeping: usageSweeping, error: usageError ?? null, balance: balanceView, rate: options.usdToCny }
    }
    const totals = usageView.totals ?? {}
    const today = usageView.today ?? {}
    return {
      enabled: true,
      sweeping: usageSweeping,
      at: usageAt,
      rate: options.usdToCny,
      peakNow: usageView.peakNow === true,
      today: {
        costUsd: money(today.cost),
        costCny: cnyOf(today.cost),
        calls: Math.round(Number(today.calls) || 0),
        tokens: tokenView(today.tokens),
      },
      totals: {
        costUsd: money(totals.cost),
        costCny: cnyOf(totals.cost),
        calls: Math.round(Number(totals.calls) || 0),
        sessions: Math.round(Number(totals.sessions) || 0),
        tokens: tokenView(totals.tokens),
        cacheHitShare: Number(totals.cacheHitShare) || 0,
      },
      models: (Array.isArray(usageView.models) ? usageView.models : []).slice(0, 10).map((row) => ({
        model: String(row.model ?? ''),
        label: String(row.label ?? row.model ?? ''),
        calls: Math.round(Number(row.calls) || 0),
        costUsd: money(row.cost),
        costCny: cnyOf(row.cost),
        tokens: tokenView(row.tokens),
      })),
      source: usageView.source ?? null,
      error: usageError ?? null,
      balance: balanceView,
    }
  }

  /** Re-fold every durable session log, single-flight. */
  const sweepUsage = () => {
    if (options.usage !== true) return Promise.resolve()
    if (usageFlight !== undefined) return usageFlight
    usageSweeping = true
    usageFlight = (async () => {
      try {
        usageView = await collectUsage({ home: resolveDshHome() })
        usageAt = Date.now()
        usageError = undefined
      } catch (error) {
        usageError = error instanceof Error ? error.message : String(error)
        complain('usage-sweep', error)
      } finally {
        usageSweeping = false
        usageFlight = undefined
        dirty = true
      }
    })()
    return usageFlight
  }

  /** Refresh the DeepSeek account balance (the module caches successes). */
  // ── conversation graph cache ──────────────────────────────────────────────
  /** @type {any} */
  let graphCache
  /** @type {Promise<any> | undefined} */
  let graphFlight
  let graphAt = 0

  /**
   * Build or reuse the conversation graph. Refolding every session log costs a
   * few seconds, so the result is bounded by a TTL and single-flighted.
   * @param {boolean} [force] - bypass the cache and rescan.
   * @returns {Promise<any>} graph payload.
   */
  const loadGraph = (force = false) => {
    if (force !== true && graphCache !== undefined && Date.now() - graphAt < 60_000) {
      return Promise.resolve(graphCache)
    }
    if (graphFlight !== undefined) return graphFlight
    graphFlight = collectConversationGraph({ home: resolveDshHome() })
      .then((value) => {
        graphCache = value
        graphAt = Date.now()
        return value
      })
      .finally(() => {
        graphFlight = undefined
      })
    return graphFlight
  }

  const refreshBalance = (force = false) => {
    if (options.balance !== true) return Promise.resolve()
    if (force !== true && Date.now() - balanceAt < options.balanceRefreshMs) return Promise.resolve()
    return readBalance({ home: resolveDshHome() })
      .then((value) => {
        balanceView = value
        balanceAt = Date.now()
        dirty = true
      })
      .catch((error) => complain('balance', error))
  }


  /**
   * Log a failure once per distinct key, so a wedged registry cannot flood the
   * host log. Never touches `ctx.logger` (not an injected service here).
   * @param {string} key - dedupe key.
   * @param {unknown} error - the failure.
   */
  const complain = (key, error) => {
    if (logged.has(key)) return
    logged.add(key)
    try {
      console.error(`live-console: ${key}: ${String(error)}`)
    } catch {
      /* Logging must never escalate a contained failure. */
    }
  }

  /**
   * Run contained synchronous work.
   * @param {string} key - dedupe key for failures.
   * @param {() => void} operation - the work.
   */
  const guard = (key, operation) => {
    try {
      operation()
    } catch (error) {
      complain(key, error)
    }
  }

  /** @type {Map<string, any>} */
  const jobsById = new Map()
  /** @type {Map<string, any>} */
  const sessions = new Map()
  /** @type {any[]} */
  const events = []
  let eventSeq = 0
  /** @type {Set<{ res: any, cursor: number }>} */
  const clients = new Set()
  let lastOpenAt = 0
  let dirty = true
  let disposed = false
  let tickTimer
  let heartbeatTimer
  let openTimer
  let historyTimer

  const history = new ProgressHistory({ enabled: options.history, path: options.statePath })

  /**
   * Schedule loading the persisted history without blocking activation.
   */
  const loadHistory = async () => {
    if (options.history !== true) return
    try {
      const text = await readFile(options.statePath, 'utf8')
      history.load(JSON.parse(text))
    } catch (error) {
      if (error?.code !== 'ENOENT') complain('history-load', error)
    }
  }

  /**
   * Flush the history to disk, atomically, serialized with the prior flush.
   */
  const saveHistory = () => {
    if (options.history !== true) return
    if (!history.dirty) return
    const previous = historyGate.promise
    const gate = createDeferral()
    historyGate = gate
    void previous.then(async () => {
      try {
        history.dirty = false
        historySerial += 1
        const body = `${JSON.stringify({ version: 1, at: Date.now(), entries: Object.fromEntries(history.entries) })}\n`
        await mkdir(dirname(options.statePath), { recursive: true })
        const temporary = `${options.statePath}.${process.pid}.${historySerial}.tmp`
        await writeFile(temporary, body, 'utf8')
        await rename(temporary, options.statePath)
        logged.delete('history-save')
      } catch (error) {
        history.dirty = true
        complain('history-save', error)
      } finally {
        gate.resolve()
      }
    })
  }

  /**
   * Watch a session by id, merging whatever facts a source reported.
   * @param {string} sessionId - the session id.
   * @returns {any} the tracked session record.
   */
  const ensureSession = (sessionId) => {
    const id = typeof sessionId === 'string' ? sessionId : ''
    let session = sessions.get(id)
    if (session === undefined) {
      session = {
        id,
        title: '',
        cwd: '',
        parentSessionId: undefined,
        origin: undefined,
        createdAt: undefined,
        running: false,
        lastActivity: Date.now(),
        currentTurn: undefined,
        currentStep: undefined,
        lastEventType: undefined,
        jobsStarted: false,
        removed: false,
        dialogue: [],
        backfilled: false,
      }
      sessions.set(id, session)
    }
    return session
  }

  /**
   * Fold one host session header/summary fact into the tracked record.
   * @param {string} sessionId - session id.
   * @param {Record<string, unknown>} facts - known fields.
   */
  const mergeSession = (sessionId, facts) => {
    if (typeof sessionId !== 'string' || sessionId.length === 0) return
    const session = ensureSession(sessionId)
    for (const [key, value] of Object.entries(facts)) {
      if (value !== undefined && value !== null && value !== '') session[key] = value
    }
    if (typeof facts.lastActivity !== 'number') session.lastActivity = Math.max(session.lastActivity, Date.now())
    dirty = true
  }

  /** How many recent messages one session keeps for the compact chat panel. */
  const DIALOGUE_LIMIT = 6
  /** Maximum visible characters kept per message. */
  const DIALOGUE_CHARS = 700

  /**
   * Append one user/assistant message to a session's compact transcript.
   * @param {any} session - tracked session.
   * @param {'user' | 'assistant'} role - speaker.
   * @param {number} time - message time.
   * @param {string} rawText - visible text.
   */
  const appendDialogue = (session, role, time, rawText) => {
    const clean = typeof rawText === 'string' ? rawText.trim() : ''
    if (clean.length === 0) return
    const clipped = clean.length > DIALOGUE_CHARS ? `${clean.slice(0, DIALOGUE_CHARS - 1)}…` : clean
    session.dialogue.push({ role, time, text: clipped })
    if (session.dialogue.length > DIALOGUE_LIMIT) session.dialogue = session.dialogue.slice(-DIALOGUE_LIMIT)
    dirty = true
  }

  const clipDialogueText = (rawText) => {
    const clean = typeof rawText === 'string' ? rawText.trim() : ''
    if (clean.length === 0) return ''
    return clean.length > DIALOGUE_CHARS ? `${clean.slice(0, DIALOGUE_CHARS - 1)}…` : clean
  }

  /**
   * Recover a restored session's title and recent dialogue from its own event
   * log. Safe to call repeatedly: a session is scanned once, and sessions that
   * appear after plugin activation are picked up by the periodic sweep below.
   * @param {any} session - a live Session object from ctx.sessions.
   */
  const backfillSessionRecord = (session) => {
    const header = session?.header ?? {}
    const id = session?.id ?? header?.id
    if (typeof id !== 'string' || id.length === 0) return
    const record = ensureSession(id)
    mergeSession(id, {
      cwd: header?.cwd,
      parentSessionId: header?.parentSession,
      origin: header?.origin,
      createdAt: header?.createdAt,
      agentPreset: header?.agentPreset,
    })
    if (record.backfilled === true) return
    if (header?.origin === 'subagent' || typeof session.ownEvents !== 'function') {
      record.backfilled = true
      return
    }
    try {
      const ownEvents = session.ownEvents()
      let title
      let lastActivity
      const dialogue = []
      for (const event of ownEvents) {
        if (Number.isFinite(event?.time)) lastActivity = Math.max(lastActivity ?? 0, event.time)
        if (event?.type === 'session/title' && typeof event.data?.title === 'string' && event.data.title.length > 0) {
          title = event.data.title
        } else if (event?.type === 'user/message') {
          const messageText = clipDialogueText(visibleText(event.data?.content))
          if (messageText.length > 0) dialogue.push({ role: 'user', time: event.time, text: messageText })
        } else if (event?.type === 'assistant/message') {
          const messageText = clipDialogueText(visibleText(event.data?.message?.content))
          if (messageText.length > 0) dialogue.push({ role: 'assistant', time: event.time, text: messageText })
        }
      }
      if (typeof title === 'string' && title.length > 0) mergeSession(id, { title })
      if (dialogue.length > 0) record.dialogue = dialogue.slice(-DIALOGUE_LIMIT)
      if (Number.isFinite(lastActivity)) record.lastActivity = Math.max(record.lastActivity, lastActivity)
      record.backfilled = true
      dirty = true
    } catch (error) {
      complain(`sessions-seed:${id}`, error)
    }
  }

  /**
   * Record one compact durable event for the conversation timeline, and derive
   * session state from it (title, turn/step, running).
   * @param {any} sessionArg - the scoped session argument.
   * @param {any} event - the SessionEvent.
   */
  const onSessionEvent = (sessionArg, event) => {
    guard('session-event', () => {
      if (event === null || typeof event !== 'object') return
      const sessionId =
        typeof sessionArg === 'string'
          ? sessionArg
          : sessionArg?.id ?? sessionArg?.header?.id ?? event?.sessionId ?? ''
      if (typeof sessionId !== 'string' || sessionId.length === 0) return
      const session = ensureSession(sessionId)
      const header = sessionArg?.header
      if (header !== null && typeof header === 'object') {
        mergeSession(sessionId, {
          cwd: header.cwd,
          parentSessionId: header.parentSession,
          origin: header.origin,
          createdAt: header.createdAt,
          agentPreset: header.agentPreset,
        })
      }
      const data = event.data !== null && typeof event.data === 'object' ? event.data : {}
      const time = Number.isFinite(event.time) ? event.time : Date.now()
      session.lastActivity = Math.max(session.lastActivity, time)
      session.lastEventType = String(event.type)

      let summary = ''
      /** @type {string | undefined} */
      let callIdForRow
      /** @type {string | undefined} */
      let toolForRow
      /**
       * Find the tool/call row that a tool/result belongs to.
       * @param {string} sid - session id.
       * @param {string} callId - tool call id.
       * @returns {any} the compact call event, or undefined.
       */
      const findCallEvent = (sid, callId) => {
        for (let index = events.length - 1; index >= 0; index -= 1) {
          const row = events[index]
          if (row.sessionId === sid && row.type === 'tool/call' && row.callId === callId) return row
        }
        return undefined
      }
      switch (event.type) {
        case 'session/title':
          if (typeof data.title === 'string' && data.title.length > 0) {
            session.title = data.title
            summary = `标题：${oneLine(data.title, 120)}`
          }
          break
        case 'turn/start':
          if (typeof data.turn === 'number') {
            session.currentTurn = data.turn
            session.currentStep = undefined
            session.running = true
            summary = `第 ${data.turn} 轮开始`
          }
          break
        case 'turn/end': {
          session.running = false
          session.currentStep = undefined
          const reason = data.reason !== null && typeof data.reason === 'object' ? data.reason.kind : undefined
          summary = `第 ${data.turn} 轮结束${typeof reason === 'string' ? `（${reason}）` : ''}`
          break
        }
        case 'step/start':
          if (typeof data.step === 'number') {
            session.currentStep = data.step
            session.currentTurn = typeof data.turn === 'number' ? data.turn : session.currentTurn
            summary = `第 ${data.turn ?? session.currentTurn ?? '?'} 轮 · 第 ${data.step} 步开始`
          }
          break
        case 'step/end':
          summary = `第 ${data.turn ?? session.currentTurn ?? '?'} 轮 · 第 ${data.step ?? session.currentStep ?? '?'} 步结束`
          break
        case 'user/message': {
          const raw = visibleText(data.content)
          const text = oneLine(raw, 120)
          summary = text.length > 0 ? `你：${text}` : '你发送了消息'
          appendDialogue(session, 'user', time, raw)
          break
        }
        case 'assistant/message': {
          const usage = data.usage
          const rawReply = visibleText(data.message?.content)
          appendDialogue(session, 'assistant', time, rawReply)
          const reply = oneLine(rawReply, 120)
          const tokens =
            usage !== null && typeof usage === 'object' && Number.isFinite(usage.outputTokens)
              ? ` · ${usage.outputTokens} tokens`
              : ''
          summary = reply.length > 0 ? `模型回复${tokens}：${reply}` : `模型回复${tokens}`
          break
        }
        case 'tool/call': {
          const toolName = typeof data.name === 'string' ? data.name : 'tool'
          const preview = toolCallPreview(toolName, data.arguments)
          callIdForRow = typeof data.callId === 'string' ? data.callId : undefined
          toolForRow = toolName
          summary = `${toolActionLabel(toolName)}${preview.length > 0 ? ` · ${preview}` : ` · ${toolName}`}`
          break
        }
        case 'tool/result': {
          const failed = data.error !== undefined || data.message?.isError === true
          const resultCallId = typeof data.message?.source?.callId === 'string' ? data.message.source.callId : undefined
          const call = resultCallId === undefined ? undefined : findCallEvent(sessionId, resultCallId)
          const callName = typeof call?.tool === 'string' ? call.tool : ''
          const elapsed = call === undefined ? '' : ` · ${formatMs(time - call.time)}`
          const body = oneLine(textOfContent(data.message?.content), 140)
          if (failed) {
            summary = `${callName.length > 0 ? `${callName} ` : ''}失败 · ${oneLine(data.error?.reason ?? data.error?.code ?? body ?? '', 120)}${elapsed}`
          } else {
            summary = `${callName.length > 0 ? `${callName} ` : ''}完成${body.length > 0 ? ` · ${body}` : ''}${elapsed}`
          }
          break
        }
        case 'job/registered': {
          const label = oneLine(data.label ?? data.job?.label ?? '', 140)
          summary = `启动命令${label.length > 0 ? ` · ${label}` : ''}`
          break
        }
        case 'job/settled': {
          const status = String(data.status ?? data.job?.status ?? 'settled')
          const detail = oneLine(data.detail ?? data.job?.detail ?? '', 100)
          summary = `命令结束 · ${status}${detail.length > 0 ? ` · ${detail}` : ''}`
          break
        }
        default:
          summary = String(event.type)
      }

      if (!INFORMATIVE_EVENTS.has(String(event.type)) && !/error|failed|aborted|compaction/i.test(String(event.type))) {
        return
      }
      eventSeq += 1
      events.push({
        seq: eventSeq,
        sessionId,
        time,
        type: String(event.type),
        summary: oneLine(summary, 300),
        callId: callIdForRow,
        tool: toolForRow,
        tone: event.type === 'tool/result' && (event.data?.error !== undefined || event.data?.message?.isError === true) ? 'error' : 'info',
      })
      while (events.length > MAX_EVENTS) events.shift()
      dirty = true
    })
  }

  /**
   * Create or refresh one tracked job record from a registry event.
   * @param {any} event - a JobEvent.
   */
  const onJobEvent = (event) => {
    guard('job-event', () => {
      if (event === null || typeof event !== 'object') return
      if (event.type === 'output') {
        const record = jobsById.get(String(event.id))
        if (record !== undefined) record.hasNewOutput = true
        return
      }
      const view = event.job
      if (view === null || typeof view !== 'object' || view.id === undefined) return
      const id = String(view.id)

      if (event.type === 'removed') {
        const existing = jobsById.get(id)
        if (existing !== undefined) {
          existing.removedAt = Date.now()
          if (existing.settledAt === undefined) existing.settledAt = existing.removedAt
          existing.job.status = existing.job.status ?? 'completed'
        }
        dirty = true
        return
      }

      let record = jobsById.get(id)
      if (record === undefined) {
        record = {
          id,
          job: {},
          owner: undefined,
          log: '',
          bytes: 0,
          lines: 0,
          cache: 0,
          truncated: false,
          lastLine: '',
          lastOutputAt: 0,
          explicitPercent: undefined,
          explicitSource: undefined,
          evidence: '',
          samples: [],
          etaMs: undefined,
          estimate: undefined,
          settledAt: undefined,
          finalized: false,
          hasNewOutput: false,
          fileTargets: undefined,
          fileCheckAt: 0,
          fileChecking: false,
        }
        jobsById.set(id, record)
      }
      record.job = { ...view }
      record.owner = typeof view.owner === 'string' && view.owner.length > 0 ? view.owner : undefined
      if (record.owner !== undefined) {
        const session = ensureSession(record.owner)
        const isChild = session.origin === 'subagent' || session.parentSessionId !== undefined
        if (session.jobsStarted !== true) {
          session.jobsStarted = true
          if (!isChild) maybeOpen('first-job')
        }
      }
      if (event.type === 'settled') {
        record.settledAt = Date.now()
        record.etaMs = undefined
        record.job.finishedAt = Number.isFinite(view.finishedAt) ? view.finishedAt : record.settledAt
      }
      dirty = true
    })
  }

  /**
   * Fold one explicit progress observation into a job, keeping it monotonic.
   * @param {any} record - tracked job.
   * @param {{ percent: number, evidence: string }} found - parsed progress.
   * @param {number} now - observation time.
   * @param {'output' | 'registry' | 'file'} source - where it came from.
   */
  const applyExplicit = (record, found, now, source) => {
    const previous = record.explicitPercent
    const percent = previous === undefined ? found.percent : Math.max(previous, found.percent)
    record.explicitPercent = percent
    record.explicitSource = record.explicitSource === 'file' && source !== 'file' ? record.explicitSource : source
    record.evidence = found.evidence
    if (previous === undefined || percent !== previous) {
      record.samples.push({ at: now, percent })
      if (record.samples.length > 8) record.samples.shift()
      record.etaMs = deriveEta(record.samples)
    }
    dirty = true
  }

  /**
   * Read one running (or newly settled) job's ring and fold it into the record.
   * The owner session is passed as `caller`: the registry's isolation fence
   * otherwise rejects every owned job with "belongs to another session". A
   * `readAt` observer read never advances the model's own cursor.
   * @param {any} record - tracked job record.
   * @param {number} now - current wall clock.
   */
  const pumpJob = (record, now) => {
    if (record.finalized) return
    try {
      const read =
        record.owner === undefined
          ? jobs.readAt(record.id, record.cache)
          : jobs.readAt(record.id, record.cache, record.owner)
      if (read === null || typeof read !== 'object') return
      const chunks = Array.isArray(read.chunks) ? read.chunks : []
      let appended = ''
      for (const chunk of chunks) {
        if (typeof chunk?.text === 'string' && chunk.text.length > 0) appended += chunk.text
      }
      if (appended.length > 0) {
        const text = stripAnsi(appended)
        record.bytes += Buffer.byteLength(appended, 'utf8')
        record.lines += text.split('\n').length - 1
        record.lastOutputAt = now
        record.log += text
        if (record.log.length > options.maxLogBytes) {
          record.log = record.log.slice(record.log.length - options.maxLogBytes)
          record.truncated = true
        }
        const lastLine = record.log.split('\n').filter((line) => line.trim().length > 0).pop()
        record.lastLine = oneLine(lastLine ?? '', 160)
      }
      if (Number.isSafeInteger(read.next) && read.next >= 0) record.cache = read.next
      if (read.lossy === true) record.truncated = true

      // Explicit progress: the registry's own progress line wins, then output.
      const declared = typeof record.job.progress === 'string' ? record.job.progress.trim() : ''
      const fromDeclared = declared.length > 0 ? progressFromLine(declared) : undefined
      const found = fromDeclared ?? progressFromText(record.log.slice(-4_096))
      if (found !== undefined) applyExplicit(record, found, now, fromDeclared !== undefined ? 'registry' : 'output')

      // History estimate for this command (used when explicit is absent).
      if (record.settledAt === undefined) {
        record.estimate = history.estimate(signatureOf(record.job.kind, record.job.label), {
          elapsedMs: now - Number(record.job.startedAt ?? now),
          bytes: record.bytes,
        })
      }

      if (record.settledAt !== undefined) {
        record.finalized = true
        const signature = signatureOf(record.job.kind, record.job.label)
        history.record(signature, {
          ms: Math.max(1, Number(record.job.finishedAt ?? now) - Number(record.job.startedAt ?? now)),
          bytes: record.bytes,
          lines: record.lines,
        })
        if (historyTimer !== undefined) clearTimeout(historyTimer)
        historyTimer = setTimeout(saveHistory, 2_000)
      }
    } catch (error) {
      // A settled job may already be gone from the registry; that is expected.
      if (record.settledAt !== undefined) record.finalized = true
      complain(`read:${record.id}`, error)
    }
  }

  /**
   * Tail a command's redirected output file, if it has one. Simulation and
   * pipeline commands often write progress to a file instead of stdout, so this
   * recovers the explicit tier for them. Throttled and contained.
   * @param {any} record - tracked job.
   * @param {number} now - current wall clock.
   */
  const checkFileProgress = (record, now) => {
    if (options.fileProgress !== true) return
    if (record.settledAt !== undefined || record.explicitPercent !== undefined) return
    if (record.owner === undefined) return
    const session = sessions.get(record.owner)
    if (session === undefined || typeof session.cwd !== 'string' || session.cwd.length === 0) return
    if (record.fileTargets === undefined) {
      const targets = extractProgressTargets(String(record.job.label ?? ''))
      record.fileTargets = targets.map((target) => (isAbsolute(target) ? target : join(session.cwd, target)))
    }
    if (record.fileTargets.length === 0) return
    if (record.fileChecking === true || now - record.fileCheckAt < 2_000) return
    record.fileCheckAt = now
    record.fileChecking = true
    void (async () => {
      try {
        for (const path of record.fileTargets) {
          const tail = await readFileTail(path)
          if (tail.length === 0) continue
          const lines = tail.split('\n').filter((line) => line.trim().length > 0)
          if (lines.length > 0) record.lastLine = oneLine(lines[lines.length - 1], 160)
          const found = progressFromText(tail)
          if (found !== undefined) {
            applyExplicit(record, found, Date.now(), 'file')
            break
          }
        }
      } catch (error) {
        complain(`file:${record.id}`, error)
      } finally {
        record.fileChecking = false
        dirty = true
      }
    })()
  }

  /**
   * Resolve the progress to render for one job, in tier order.
   * @param {any} record - tracked job.
   * @param {number} now - current wall clock.
   * @returns {{ percent: number | null, etaMs: number | null, source: string, evidence: string }}
   */
  const progressOf = (record, now) => {
    if (record.settledAt !== undefined) {
      return { percent: 100, etaMs: 0, source: 'settled', evidence: record.job.detail ?? '' }
    }
    if (record.explicitPercent !== undefined) {
      return {
        percent: Math.round(record.explicitPercent * 100) / 100,
        etaMs: record.etaMs ?? null,
        source: record.explicitSource ?? 'output',
        evidence: record.evidence ?? '',
      }
    }
    if (record.estimate !== undefined && record.estimate.percent !== undefined) {
      return {
        percent: Math.round(record.estimate.percent * 100) / 100,
        etaMs: record.estimate.etaMs ?? null,
        source: record.estimate.source ?? 'estimate',
        evidence: '',
      }
    }
    return { percent: null, etaMs: null, source: 'activity', evidence: '' }
  }

  /**
   * Project one job for the page. Output text stays in the per-job log endpoint,
   * so the metadata feed stays small even for verbose commands.
   * @param {any} record - tracked job.
   * @param {number} now - current wall clock.
   * @returns {Record<string, unknown>}
   */
  const jobMeta = (record, now) => {
    const progress = progressOf(record, now)
    const startedAt = Number(record.job.startedAt ?? now)
    const finishedAt = Number.isFinite(record.job.finishedAt) ? record.job.finishedAt : undefined
    const elapsedMs = Math.max(0, (finishedAt ?? now) - startedAt)
    return {
      id: record.id,
      kind: record.job.kind ?? 'job',
      label: typeof record.job.label === 'string' ? record.job.label : '',
      session: record.owner ?? null,
      status: record.job.status ?? 'running',
      startedAt,
      finishedAt: finishedAt ?? null,
      elapsedMs,
      percent: progress.percent,
      etaMs: progress.etaMs,
      progressSource: progress.source,
      evidence: progress.evidence,
      lastLine: record.lastLine,
      bytes: record.bytes,
      lines: record.lines,
      lastOutputAt: record.lastOutputAt || null,
      idleMs: record.lastOutputAt === 0 ? 0 : Math.max(0, now - record.lastOutputAt),
      settled: record.settledAt !== undefined,
      truncated: record.truncated,
    }
  }

  /**
   * Project one session for the page.
   * @param {any} session - tracked session.
   * @param {number} now - current wall clock.
   * @returns {Record<string, unknown>}
   */
  const sessionMeta = (session, now) => {
    let jobCount = 0
    let activeJobs = 0
    let lastJobActivity = 0
    for (const record of jobsById.values()) {
      if (record.owner !== session.id) continue
      jobCount += 1
      if (record.settledAt === undefined) activeJobs += 1
      lastJobActivity = Math.max(lastJobActivity, Number(record.job.startedAt ?? 0), record.lastOutputAt || 0)
    }
    return {
      id: session.id,
      short: shortId(session.id),
      title: session.title || '',
      cwd: session.cwd || '',
      parentSessionId: session.parentSessionId ?? null,
      origin: session.origin ?? null,
      isChild: session.origin === 'subagent' || session.parentSessionId !== undefined,
      createdAt: session.createdAt ?? null,
      running: session.running === true || activeJobs > 0,
      lastActivity: Math.max(session.lastActivity, lastJobActivity),
      currentTurn: session.currentTurn ?? null,
      currentStep: session.currentStep ?? null,
      lastEventType: session.lastEventType ?? null,
      dialogue: Array.isArray(session.dialogue) ? session.dialogue : [],
      jobCount,
      activeJobs,
    }
  }

  /**
   * The full page-facing snapshot.
   * @param {boolean} [withEvents] - include the recent event list.
   * @returns {Record<string, unknown>}
   */
  const snapshot = (withEvents = true) => {
    const now = Date.now()
    const liveSessions = [...sessions.values()].filter((session) => session.removed !== true)
    const sessionRows = liveSessions.map((session) => sessionMeta(session, now))
    sessionRows.sort((left, right) => right.lastActivity - left.lastActivity)
    const jobRows = [...jobsById.values()].map((record) => jobMeta(record, now))
    jobRows.sort((left, right) => {
      const leftActive = left.settled ? 1 : 0
      const rightActive = right.settled ? 1 : 0
      return leftActive - rightActive || right.startedAt - left.startedAt
    })
    return {
      at: now,
      version: PAGE_VERSION,
      startedAt,
      route: options.route,
      pageTitle: options.pageTitle,
      stats: {
        sessions: sessionRows.length,
        jobs: jobRows.length,
        events: eventSeq,
        clients: clients.size,
        uptimeMs: now - startedAt,
      },
      usage: usageSnapshot(),
      sessions: sessionRows,
      jobs: jobRows,
      events: withEvents ? events.slice(-SNAPSHOT_EVENTS) : [],
    }
  }

  /**
   * Broadcast one update to every connected page. Events are sent exactly once
   * per client (a cursor), while jobs/sessions are small and sent whole.
   */
  const broadcast = () => {
    if (clients.size === 0) return
    const now = Date.now()
    const sessionRows = [...sessions.values()].filter((session) => session.removed !== true).map((session) => sessionMeta(session, now))
    sessionRows.sort((left, right) => right.lastActivity - left.lastActivity)
    const jobRows = [...jobsById.values()].map((record) => jobMeta(record, now))
    jobRows.sort((left, right) => {
      const leftActive = left.settled ? 1 : 0
      const rightActive = right.settled ? 1 : 0
      return leftActive - rightActive || right.startedAt - left.startedAt
    })
    for (const client of [...clients]) {
      try {
        const newEvents = events.filter((event) => event.seq > client.cursor).slice(-60)
        if (newEvents.length > 0) client.cursor = newEvents[newEvents.length - 1].seq
        const payload = JSON.stringify({ type: 'update', at: now, usage: usageSnapshot(), sessions: sessionRows, jobs: jobRows, events: newEvents })
        client.res.write(`event: update\ndata: ${payload}\n\n`)
      } catch (error) {
        complain('sse-write', error)
        try {
          client.res.end()
        } catch {
          /* already closed */
        }
        clients.delete(client)
      }
    }
    dirty = false
  }

  /**
   * The periodic maintenance tick: read live output, expire settled cards,
   * refresh the page, and occasionally flush the history.
   */
  const tick = () => {
    if (disposed) return
    guard('tick', () => {
      const now = Date.now()
      for (const record of [...jobsById.values()]) {
        if (record.settledAt === undefined) {
          pumpJob(record, now)
          checkFileProgress(record, now)
        } else if (record.finalized !== true) {
          pumpJob(record, now)
        }
      }
      let removedAny = false
      for (const [id, record] of jobsById) {
        const endedAt = record.settledAt ?? record.removedAt
        if (endedAt !== undefined && now - endedAt > options.keepSettledMs) {
          jobsById.delete(id)
          removedAny = true
        }
      }
      if (removedAny) dirty = true
      if (dirty || clients.size > 0) broadcast()
    })
  }

  /**
   * Send one SSE frame to a page client.
   * @param {any} res - the ServerResponse.
   * @param {string} event - SSE event name.
   * @param {unknown} data - JSON-serializable payload.
   */
  const sseWrite = (res, event, data) => {
    res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
  }

  /**
   * Whether a request comes from the local machine.
   * @param {any} req - IncomingMessage.
   * @returns {boolean}
   */
  const isLoopback = (req) => {
    const address = typeof req?.socket?.remoteAddress === 'string' ? req.socket.remoteAddress : ''
    return address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1'
  }

  /**
   * Respond with JSON and never throw into the carrier.
   * @param {any} res - ServerResponse.
   * @param {number} status - HTTP status.
   * @param {unknown} body - JSON body.
   */
  const sendJson = (res, status, body) => {
    try {
      const text = JSON.stringify(body)
      res.writeHead(status, {
        ...SECURITY_HEADERS,
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-store',
        'content-length': Buffer.byteLength(text, 'utf8'),
      })
      res.end(text)
    } catch (error) {
      complain('respond', error)
    }
  }

  /**
   * Read one bounded JSON request body.
   * @param {any} req - IncomingMessage.
   * @param {number} [limit] - maximum bytes.
   * @returns {Promise<any>} parsed body.
   */
  const readJsonBody = (req, limit = 64 * 1024) =>
    new Promise((resolve, reject) => {
      const chunks = []
      let total = 0
      req.on('data', (chunk) => {
        total += chunk.length
        if (total > limit) {
          reject(new Error('request body too large'))
          req.destroy()
          return
        }
        chunks.push(chunk)
      })
      req.on('end', () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'))
        } catch (error) {
          reject(error)
        }
      })
      req.on('error', reject)
    })

  /**
   * Build the page HTML with the configured title folded in.
   * @returns {string}
   */
  const pageHtml = () => {
    // Read on every request: the page is 41 KB, one read per browser load, and
    // this keeps HTML/CSS/JS edits effective without another host reload.
    const html = readFileSync(new URL('./page.html', import.meta.url), 'utf8')
    return html
      .replaceAll('__LIVE_CONSOLE_TITLE__', options.pageTitle.replace(/[<>&"]/g, ''))
      .replaceAll('__LIVE_CONSOLE_KEY__', capability)
      .replaceAll('__LIVE_CONSOLE_VERSION__', PAGE_VERSION)
  }

  /**
   * Open the console in the default browser, throttled.
   * @param {string} reason - diagnostic reason.
   */
  const openBrowser = (reason) => {
    if (options.autoOpen === 'never' || disposed) return
    if (clients.size > 0) return
    if (originResolver === undefined) return
    const now = Date.now()
    if (now - lastOpenAt < OPEN_THROTTLE_MS) return
    lastOpenAt = now
    guard('open-browser', () => {
      const url = consoleUrl()
      if (process.platform === 'win32') {
        spawn(process.env.ComSpec ?? 'cmd.exe', ['/d', '/s', '/c', 'start', '""', url], {
          detached: true,
          stdio: 'ignore',
          windowsHide: true,
        }).unref()
      } else if (process.platform === 'darwin') {
        spawn('open', [url], { detached: true, stdio: 'ignore' }).unref()
      } else {
        spawn('xdg-open', [url], { detached: true, stdio: 'ignore' }).unref()
      }
    })
  }

  /**
   * Remember the last open attempt without logging a failure.
   * @param {string} reason - diagnostic reason.
   */
  const maybeOpen = (reason) => {
    openBrowser(reason)
  }

  /** @type {(() => string) | undefined} */
  let originResolver
  /**
   * Resolve the web carrier origin for links.
   * @returns {string}
   */
  const origin = () => {
    try {
      return originResolver !== undefined ? originResolver() : 'http://127.0.0.1:3080'
    } catch {
      return 'http://127.0.0.1:3080'
    }
  }

  /** The capability-carrying link to this console. */
  const consoleUrl = () => `${origin()}${options.route}?k=${encodeURIComponent(capability)}`

  /**
   * Publish the console URL (and the stable key) under `$DSH_HOME/live-console/`,
   * so the user can reopen the fixed page even after closing the browser tab.
   */
  const publishUrl = () => {
    guard('publish-url', () => {
      if (originResolver === undefined) return
      const url = consoleUrl()
      void mkdir(dirname(urlPath), { recursive: true })
        .then(async () => {
          await writeFile(urlPath, `${url}\n`, 'utf8')
          await writeFile(keyPath, `${capability}\n`, 'utf8')
        })
        .catch((error) => complain('publish-url', error))
    })
  }

  // ── job registry subscription ──────────────────────────────────────────────
  let unsubscribeJobs
  try {
    unsubscribeJobs = jobs.events.subscribe({ owners: 'all' }, onJobEvent)
  } catch (error) {
    complain('subscribe-jobs', error)
    return undefined
  }

  // ── durable session event feed (optional services are guarded) ─────────────
  /**
   * Subscribe to a host event across every scope. Scoped events such as
   * `session/event` are only dispatched to listeners that opted into `global`.
   * @param {string} eventName - Cordis event name.
   * @param {(...args: any[]) => void} listener - the handler.
   * @returns {(() => void) | undefined} disposer, when the event exists.
   */
  const subscribeHostEvent = (eventName, listener) => {
    try {
      return ctx.on(eventName, listener, { global: true })
    } catch {
      try {
        return ctx.on(eventName, listener)
      } catch (error) {
        complain(`listen:${eventName}`, error)
        return undefined
      }
    }
  }

  const eventDisposers = []
  for (const name of ['session/event', 'session/created', 'session/disposed', 'api-session/added', 'api-session/status', 'api-session/activity', 'api-session/removed']) {
    try {
      const listener = (...args) => {
        guard(`host-event:${name}`, () => {
          if (name === 'session/event') onSessionEvent(args[0], args[1])
          else if (name === 'api-session/added') {
            const summary = args[0] ?? {}
            mergeSession(summary.sessionId, {
              cwd: summary.cwd,
              parentSessionId: summary.parentSessionId,
              origin: summary.origin,
              running: summary.running,
              lastActivity: summary.updatedAt,
            })
          } else if (name === 'api-session/status') {
            const session = ensureSession(args[0])
            session.running = args[1] === true
            session.lastActivity = Date.now()
            dirty = true
          } else if (name === 'api-session/activity') {
            const session = ensureSession(args[0])
            if (Number.isFinite(args[1])) session.lastActivity = Math.max(session.lastActivity, args[1])
            dirty = true
          } else if (name === 'api-session/removed') {
            const session = sessions.get(args[0])
            if (session !== undefined) session.removed = true
            dirty = true
          } else if (name === 'session/created') {
            const sessionArg = args[0]
            const header = sessionArg?.header
            const id = sessionArg?.id ?? header?.id
            if (typeof id === 'string') {
              mergeSession(id, {
                cwd: header?.cwd,
                parentSessionId: header?.parentSession,
                origin: header?.origin,
                createdAt: header?.createdAt,
                agentPreset: header?.agentPreset,
              })
            }
          }
        })
      }
      const disposer = subscribeHostEvent(name, listener)
      if (typeof disposer === 'function') eventDisposers.push(disposer)
    } catch (error) {
      complain(`listen:${name}`, error)
    }
  }

  // ── web routes (optional: a CLI-only composition has no web carrier) ──────
  ctx.inject(['webServer'], (webCtx) => {
    try {
      originResolver = () => webCtx.webServer.getOrigin()
    } catch {
      originResolver = undefined
    }
    publishUrl()
    webCtx.effect(() => {
      const routes = []
      const guardRequest = (req, res) => {
        if (disposed) {
          sendJson(res, 503, { error: 'console disposed' })
          return false
        }
        if (options.allowNonLoopback !== true && isLoopback(req) === false) {
          sendJson(res, 403, { error: 'loopback only' })
          return false
        }
        let key = ''
        try {
          key = new URL(req.url ?? '/', 'http://console.invalid').searchParams.get('k') ?? ''
        } catch {
          key = ''
        }
        if (key !== capability) {
          sendJson(res, 401, { error: 'console link key missing or invalid' })
          return false
        }
        return true
      }

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: options.route,
        handler: (req, res) => {
          if (req.method !== 'GET' && req.method !== 'HEAD') {
            sendJson(res, 405, { error: 'GET only' })
            return
          }
          if (guardRequest(req, res) === false) return
          try {
            const html = pageHtml()
            res.writeHead(200, {
              ...SECURITY_HEADERS,
              'content-type': 'text/html; charset=utf-8',
              'content-security-policy': PAGE_CSP,
              'cache-control': 'no-store',
              'content-length': Buffer.byteLength(html, 'utf8'),
            })
            res.end(req.method === 'HEAD' ? undefined : html)
          } catch (error) {
            complain('page', error)
            try {
              res.writeHead(500)
              res.end('console page failed')
            } catch {
              /* already closed */
            }
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/state`,
        handler: (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            sendJson(res, 200, snapshot(true))
          } catch (error) {
            complain('state', error)
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/log`,
        handler: (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            const url = new URL(req.url ?? '/', 'http://console.invalid')
            const id = url.searchParams.get('job') ?? ''
            const record = jobsById.get(id)
            if (record === undefined) {
              sendJson(res, 404, { error: 'unknown job' })
              return
            }
            sendJson(res, 200, {
              id,
              status: record.job.status ?? 'running',
              text: record.log,
              bytes: record.bytes,
              lines: record.lines,
              truncated: record.truncated === true,
            })
          } catch (error) {
            complain('log', error)
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/usage`,
        handler: async (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            const url = new URL(req.url ?? '/', 'http://console.invalid')
            if (url.searchParams.get('refresh') === '1') {
              await sweepUsage()
              await refreshBalance(true)
            }
            sendJson(res, 200, { usage: usageSnapshot() })
          } catch (error) {
            complain('usage-route', error)
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/send`,
        handler: async (req, res) => {
          if (guardRequest(req, res) === false) return
          if (req.method !== 'POST') {
            sendJson(res, 405, { error: 'POST only' })
            return
          }
          try {
            const body = await readJsonBody(req)
            const sessionId = typeof body?.sessionId === 'string' ? body.sessionId : ''
            const messageText = typeof body?.text === 'string' ? body.text.trim() : ''
            if (sessionId.length === 0 || messageText.length === 0) {
              sendJson(res, 400, { error: 'sessionId and text are required' })
              return
            }
            if (messageText.length > 8_000) {
              sendJson(res, 400, { error: 'message is too long' })
              return
            }
            if (lookupAgent === undefined) {
              sendJson(res, 503, { error: 'agent service is not available in this composition' })
              return
            }
            const agent = lookupAgent(sessionId)
            if (agent === null || agent === undefined) {
              sendJson(res, 404, { error: 'no live agent for that session' })
              return
            }
            if (typeof agent.followup !== 'function') {
              sendJson(res, 501, { error: 'this agent cannot accept input' })
              return
            }
            // Same shape the session controller builds for a user prompt.
            agent.followup({
              role: 'user',
              id: randomUUID(),
              content: [{ type: 'text', text: messageText }],
              source: { kind: 'user' },
            })
            sendJson(res, 200, { ok: true })
          } catch (error) {
            complain('send', error)
            sendJson(res, 400, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/agent-info`,
        handler: (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            const url = new URL(req.url ?? '/', 'http://console.invalid')
            const sessionId = url.searchParams.get('session') ?? ''
            const agent = lookupAgent === undefined || sessionId.length === 0 ? undefined : lookupAgent(sessionId)
            sendJson(res, 200, {
              sessionId,
              agent: agent !== undefined && agent !== null,
              followup: typeof agent?.followup,
              send: typeof agent?.send,
              steer: typeof agent?.steer,
            })
          } catch (error) {
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/graph`,
        handler: (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            const html = readFileSync(new URL('./graph.html', import.meta.url), 'utf8')
            res.writeHead(200, {
              ...SECURITY_HEADERS,
              'content-type': 'text/html; charset=utf-8',
              'content-security-policy': PAGE_CSP,
              'cache-control': 'no-store',
              'content-length': Buffer.byteLength(html, 'utf8'),
            })
            res.end(req.method === 'HEAD' ? undefined : html)
          } catch (error) {
            complain('graph-page', error)
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/graph-data`,
        handler: async (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            const url = new URL(req.url ?? '/', 'http://console.invalid')
            const graph = await loadGraph(url.searchParams.get('refresh') === '1')
            sendJson(res, 200, graph)
          } catch (error) {
            complain('graph-data', error)
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/context-archive`,
        handler: async (req, res) => {
          if (guardRequest(req, res) === false) return
          if (req.method !== 'GET' && req.method !== 'HEAD') {
            sendJson(res, 405, { error: 'GET only' })
            return
          }
          try {
            const archive = await buildContextArchive({ home: resolveDshHome() })
            res.writeHead(200, {
              ...SECURITY_HEADERS,
              'content-type': 'application/gzip',
              'content-disposition': `attachment; filename="${archive.filename}"`,
              'cache-control': 'no-store',
              'content-length': archive.buffer.length,
              'x-archive-sessions': String(archive.stats.sessions),
              'x-archive-files': String(archive.stats.files),
              'x-archive-uncompressed-bytes': String(archive.stats.uncompressedTarBytes),
            })
            res.end(req.method === 'HEAD' ? undefined : archive.buffer)
          } catch (error) {
            complain('context-archive', error)
            sendJson(res, 500, { error: String(error) })
          }
        },
      }))

      routes.push(webCtx.webServer.register({
        kind: 'exact',
        path: `${options.route}/events`,
        handler: (req, res) => {
          if (guardRequest(req, res) === false) return
          try {
            // A page from a previous host version must not silently keep an old UI:
            // rejecting its stream drops it to zero clients, so activation/first-job
            // auto-open can hand the user the current page instead.
            if (new URL(req.url ?? '/', 'http://console.invalid').searchParams.get('v') !== PAGE_VERSION) {
              sendJson(res, 426, { error: 'console page is outdated; reopen the page to upgrade' })
              return
            }
            res.writeHead(200, {
              ...SECURITY_HEADERS,
              'content-type': 'text/event-stream; charset=utf-8',
              'cache-control': 'no-store',
              connection: 'keep-alive',
              'x-accel-buffering': 'no',
            })
            res.write('retry: 2500\n\n')
            const client = { res, cursor: eventSeq }
            clients.add(client)
            sseWrite(res, 'snapshot', snapshot(true))
            req.on('close', () => {
              clients.delete(client)
            })
            res.on('error', () => {
              clients.delete(client)
            })
            dirty = true
          } catch (error) {
            complain('events', error)
            try {
              res.end()
            } catch {
              /* already closed */
            }
          }
        },
      }))

      tickTimer = setInterval(tick, options.updateMs)
      heartbeatTimer = setInterval(() => {
        for (const client of [...clients]) {
          try {
            client.res.write(': ping\n\n')
          } catch {
            clients.delete(client)
          }
        }
      }, 15_000)

      if (options.autoOpen !== 'never') {
        openTimer = setTimeout(() => maybeOpen('activation'), options.openDelayMs)
      }

      if (options.usage === true) {
        setTimeout(() => void sweepUsage(), 1_500)
        usageTimer = setInterval(() => {
          if (clients.size > 0) void sweepUsage()
        }, options.usageRefreshMs)
      }
      if (options.balance === true) {
        setTimeout(() => void refreshBalance(false), 2_500)
        balanceTimer = setInterval(() => {
          if (clients.size > 0) void refreshBalance(false)
        }, options.balanceRefreshMs)
      }

      if (options.injectedLink !== false) {
        const disposeInject = webCtx.on('webserver/index-inject', (table) => {
          try {
            if (Array.isArray(table)) table.push({ kind: 'script', placement: 'head', text: LINK_JS })
          } catch {
            /* index injection is best-effort; never break the boot payload */
          }
        })
        if (typeof disposeInject === 'function') routes.push(disposeInject)
      }

      return () => {
        for (const dispose of routes) {
          try {
            dispose()
          } catch {
            /* routes may already be gone */
          }
        }
      }
    }, 'live-console: web routes')
  })

  // ── authenticated URL endpoint for the in-app console button ─────────────
  ctx.inject(['connection'], (connCtx) => {
    const fetchService = connCtx.connection?.fetch
    if (fetchService === null || typeof fetchService?.register !== 'function') return
    connCtx.effect(
      () =>
        fetchService.register({
          path: '/api/live-console/url',
          methods: ['GET'],
          requestBody: 'buffered',
          fetch: async () => {
            if (originResolver === undefined) {
              return new Response(JSON.stringify({ error: 'console not mounted' }), {
                status: 503,
                headers: { ...SECURITY_HEADERS, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
              })
            }
            return new Response(JSON.stringify({ url: consoleUrl() }), {
              status: 200,
              headers: { ...SECURITY_HEADERS, 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
            })
          },
        }),
      'live-console: authenticated url route',
    )
  })

  // ── automatic progress convention for every agent ────────────────────────
  if (options.progressPrompt !== false) {
    ctx.inject(['systemPrompt'], (promptCtx) => {
      promptCtx.effect(
        () => promptCtx.systemPrompt.section({
          name: 'live-console-progress',
          order: 950,
          text: () => PROGRESS_INSTRUCTION,
        }),
        'live-console: progress instruction',
      )
    })
  }

  loadHistory()

  // Backfill sessions that were already alive when the plugin activated, so the
  // page has a session list immediately instead of waiting for the next event.
  ctx.inject(['sessions'], (sessionCtx) => {
    const sweep = () => {
      guard('sessions', () => {
        if (typeof sessionCtx.sessions?.list !== 'function') return
        for (const session of sessionCtx.sessions.list()) backfillSessionRecord(session)
      })
    }
    sweep()
    // Restored sessions may be published after this plugin activates, so keep a
    // light periodic sweep; already-scanned sessions return immediately.
    const timer = setInterval(sweep, 2_000)
    ctx.effect(() => () => clearInterval(timer), 'live-console: session backfill')
  })

  /**
   * Full teardown: timers, clients, history flush.
   */
  const teardown = () => {
    disposed = true
    try {
      clearInterval(tickTimer)
      clearInterval(heartbeatTimer)
      clearTimeout(openTimer)
      clearTimeout(historyTimer)
      clearInterval(usageTimer)
      clearInterval(balanceTimer)
    } catch {
      /* best effort */
    }
    for (const client of [...clients]) {
      try {
        client.res.end()
      } catch {
        /* already closed */
      }
      clients.delete(client)
    }
    try {
      if (typeof unsubscribeJobs === 'function') unsubscribeJobs()
    } catch {
      /* best effort */
    }
    for (const dispose of eventDisposers) {
      try {
        dispose()
      } catch {
        /* best effort */
      }
    }
    saveHistory()
  }

  ctx.effect(() => teardown, 'live-console: lifecycle')
  return teardown
}

