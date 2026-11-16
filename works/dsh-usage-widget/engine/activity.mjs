/**
 * Live agent and background-job derivation for the standalone usage widget.
 *
 * The usage fold answers "what has been spent". This module answers "what is
 * happening right now", and it answers it from exactly the same durable
 * artifacts, with no live connection to the Harness: whatever is true is written
 * down in the session log, and whatever is *not* written down cannot be claimed.
 *
 * Three log facts carry the whole picture:
 *
 * - `session.delegationDepth` — 0 for a lead session, > 0 for a subagent or
 *   teammate. A `subagent/descriptor` beside it carries the human label.
 * - `turn/start` / `turn/end` pairs, per session. A newest `turn/start` with no
 *   later `turn/end` means that agent is running *now*.
 * - `tool/call` / `tool/result`, correlated by call id. A call with no matching
 *   result is a program that is still running — a background job is exactly
 *   that, and it is the *only* trace, because a job's output does not reach
 *   disk until it finishes.
 *
 * Progress is the honest part. Nothing streams a percentage to the log, so only
 * two situations are reported: a download whose `Content-Length` a `HEAD`
 * request can confirm, and a progress *line* the command itself writes into a
 * file. Everything else is `progress: null` plus a short note saying why. Probing
 * is bounded (one cached HEAD per URL, a tail read of at most `TAIL_BYTES`) and
 * is skipped entirely when the command names no candidate path.
 *
 * Nothing here throws. A log that cannot be read, a file that vanished, a URL
 * that does not answer: each degrades to a missing row or a `null` progress with
 * a note, never to a failed poll.
 *
 * @module dsh-usage-widget/activity
 */

import { open, readFile, stat } from 'node:fs/promises'

import { readZstdJsonlLines } from './zstd.mjs'

/** Longest rendered command line in a `jobs` entry. */
export const COMMAND_MAX = 120

/**
 * Places to look for a program name inside `tool/call.data.arguments`, in order.
 * The tool name is used when none of them is a string.
 */
const PROGRAM_KEYS = ['program', 'shell', 'executable', 'binary']

/** Keys that hold the runnable text of a call, in preference order. */
const COMMAND_KEYS = ['command', 'cmd', 'script', 'code', 'input', 'expression']

/** Keys that carry a human sentence about the call rather than its program. */
const SUMMARY_KEYS = ['description', 'label', 'title', 'summary', 'reason']

/**
 * Argument keys the pet's reaction layer shows as a one-line bubble summary, in
 * preference order (REACTIONS-SPEC §3.2). `queries[0]` is the last resort and is
 * read from the array form.
 */
export const SUMMARY_ORDER = ['command', 'file_path', 'path', 'pattern', 'query', 'url', 'title', 'description', 'prompt', 'queries']

/** Longest tail read used to look for a progress line. */
export const TAIL_BYTES = 512 * 1024

/** How many trailing lines of a redirect target are examined. */
export const TAIL_LINES = 200

/** Short timeout for the one `HEAD` request that may confirm a download total. */
export const HEAD_TIMEOUT_MS = 4000

/** Clamp for any reported ETA: never below one second, never above seven days. */
export const ETA_MIN_MS = 1000
export const ETA_MAX_MS = 7 * 24 * 60 * 60 * 1000

/** A step total outside this range is noise, not progress. */
const TOTAL_MAX = 1e12

/** Unmatched calls folded per poll. The widget config's `jobsMax` is a UI cap. */
export const DEFAULT_JOBS_MAX = 200

/** Entries kept in each fold cache; the live set is a handful of sessions. */
const FOLD_CACHE_MAX = 512

/** @type {Map<string, { at: number, sealed: boolean, promise: Promise<{ ok: boolean, total?: number, error?: string }> }>} */
const headCache = new Map()

/** @type {Map<string, { key: string, value: any }>} */
const foldCache = new Map()

/** Drop every memoized HEAD result, so a probe re-asks the network. */
export function clearHeadCache() {
  headCache.clear()
}

/** Drop every memoized activity fold, so every artifact is decoded again. */
export function clearFoldCache() {
  foldCache.clear()
}

/** Round to at most one decimal. */
function oneDecimal(value) {
  return Math.round(value * 10) / 10
}

/**
 * Clamp an ETA into the sane band.
 * @param {number} value - a raw milliseconds estimate.
 * @returns {number} an integer between one second and seven days.
 */
export function clampEta(value) {
  if (!Number.isFinite(value) || value <= 0) return ETA_MIN_MS
  return Math.round(Math.min(ETA_MAX_MS, Math.max(ETA_MIN_MS, value)))
}

/**
 * Clamp a percentage into 0-100 with at most one decimal, or return undefined.
 * @param {number} value - a raw percentage.
 * @returns {number | undefined} the accepted percentage.
 */
export function clampPercent(value) {
  if (!Number.isFinite(value) || value < 0 || value > 100) return undefined
  return oneDecimal(value)
}

/**
 * Decode `tool/call.data.arguments` into an object, a plain string, or undefined.
 *
 * The field is a JSON *string* in real logs, but a tool may declare an object
 * schema, so both are accepted.
 *
 * @param {any} raw - the stored arguments.
 * @returns {any} the decoded value.
 */
export function parseArguments(raw) {
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (text.startsWith('{') || text.startsWith('[')) {
      try {
        return JSON.parse(text)
      } catch {
        return text
      }
    }
    return text
  }
  return raw
}

/**
 * The runnable text of a call: the command itself when the arguments separate
 * one from a description, the raw arguments otherwise.
 *
 * @param {any} parsed - output of `parseArguments`.
 * @returns {string} the command text (possibly empty).
 */
export function commandTextOf(parsed) {
  if (typeof parsed === 'string') return parsed
  if (parsed === null || typeof parsed !== 'object') return ''
  for (const key of COMMAND_KEYS) {
    const value = parsed[key]
    if (typeof value === 'string' && value.length > 0) return value
  }
  let best = ''
  for (const value of Object.values(parsed)) {
    if (typeof value === 'string' && value.length > best.length) best = value
  }
  return best
}

/** The program a call runs: an explicit field, else the tool name. */
export function programOf(parsed, toolName) {
  const fallback = typeof toolName === 'string' && toolName.length > 0 ? toolName : 'tool'
  if (parsed !== null && typeof parsed === 'object') {
    for (const key of PROGRAM_KEYS) {
      const value = parsed[key]
      if (typeof value === 'string' && value.length > 0) return value
    }
  }
  return fallback
}

/**
 * Render one command string as a single capped line.
 *
 * Newlines become spaces, runs of whitespace collapse, and the JSON quoting
 * around the text is stripped, so the result reads like a command rather than
 * like a serialized object.
 *
 * @param {string} text - the command itself, already unwrapped from its JSON.
 * @returns {string} the rendered line.
 */
export function renderCommandLine(text) {
  const collapsed = text.replace(/\s+/g, ' ').replace(/"/g, "'").trim()
  return collapsed.length > COMMAND_MAX ? `${collapsed.slice(0, COMMAND_MAX - 1)}…` : collapsed
}

/**
 * Collapse one call's command onto a single line, capped at `COMMAND_MAX`.
 *
 * A description that accompanies the real command is annotated rather than
 * dropped, so several `pwsh` calls stay distinguishable.
 *
 * @param {any} raw - the stored arguments.
 * @returns {string} the rendered line.
 */
export function renderCommand(raw) {
  const parsed = parseArguments(raw)
  const collapsed = renderCommandLine(commandTextOf(parsed))
  if (parsed !== null && typeof parsed === 'object') {
    for (const key of SUMMARY_KEYS) {
      const summary = parsed[key]
      if (typeof summary !== 'string' || summary.length === 0) continue
      return renderCommandLine(`${collapsed} (${summary})`)
    }
  }
  return collapsed
}

/**
 * Blank out single- and double-quoted regions.
 *
 * Argument text is PowerShell-flavoured: `>` appears inside format operators and
 * inside string literals, so redirect detection runs on this cleaned copy while
 * size/URL detection runs on the raw text.
 *
 * @param {string} text - the rendered command line.
 * @returns {string} the same line with quoted regions replaced by a space.
 */
export function stripQuoted(text) {
  return text.replace(/'[^']*'|"[^"]*"/g, ' ')
}

/** Strip one layer of surrounding quotes from a captured path. */
function unquote(value) {
  if (value.length >= 2) {
    const first = value[0]
    const last = value[value.length - 1]
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return value.slice(1, -1)
    }
  }
  return value
}

/** A quoted path (`"..."` / `'...'`) or a whitespace-delimited token. */
const PATH_TOKEN = /("[^"]+"|'[^']+'|[^\s]+)/.source

/**
 * Find the destination of a `>` / `>>` redirect, skipping shell file-descriptor
 * forms such as `2>&1`, which name a stream rather than a file.
 *
 * A quoted target is matched before quoting is stripped, because the whole file
 * name lives inside the quotes.
 *
 * @param {string} text - the command line.
 * @returns {string | undefined} the destination path.
 */
function redirectTarget(text) {
  const matches = new RegExp(`>>?\\s*${PATH_TOKEN}`, 'g')
  let match
  while ((match = matches.exec(text)) !== null) {
    const raw = match[1]
    if (/^&\d+$/.test(raw)) continue
    const candidate = unquote(raw.trim())
    if (candidate.length > 0) return candidate
  }
  return undefined
}

/**
 * The value of an output flag (`-o`, `--output`, `-OutFile`, `-Out`).
 *
 * The quoted form is read from the original text and every other form from a
 * copy with quoted regions blanked, so neither a quoted path nor a flag followed
 * by an unrelated quoted fragment is misread.
 *
 * @param {string} text - the command line.
 * @returns {string | undefined} the destination path.
 */
function outputFlagValue(text) {
  const quoted = new RegExp(`(?:^|\\s)(?:--output|-OutFile|-Out|-o)\\s*[=:]?\\s*("[^"]+"|'[^']+')`, 'i').exec(text)
  if (quoted !== null) {
    const candidate = unquote(quoted[1].trim())
    if (candidate.length > 0) return candidate
  }
  const bare = new RegExp(`(?:^|\\s)(?:--output|-OutFile|-Out|-o)\\s*[=:]?\\s*(${PATH_TOKEN})`, 'i').exec(stripQuoted(text))
  if (bare !== null) {
    const candidate = bare[1].trim()
    if (candidate.length > 0) return candidate
  }
  return undefined
}

/**
 * The destination file a call writes to, when it names one.
 *
 * `-o <path>`, `--output <path>`, `--output=<path>`, `-OutFile <path>` and the
 * `>` / `>>` redirects are recognised. The `>` form is only trusted when a
 * destination and a separator follow it, so neither a PowerShell format operator
 * nor a file-descriptor redirect is mistaken for an output file.
 *
 * @param {string} text - the command line.
 * @returns {string | undefined} the destination path.
 */
export function detectOutputPath(text) {
  return outputFlagValue(text) ?? redirectTarget(text)
}

/** The first `http(s)` URL in a command, when it names one. */
export function detectUrl(text) {
  const match = /https?:\/\/[^\s"'<>()|;]+/i.exec(text)
  return match === null ? undefined : match[0]
}

/**
 * Resolve a command-relative path against a working directory.
 * @param {string} path - the candidate path.
 * @param {string | undefined} cwd - the session's working directory.
 * @returns {string} an absolute path.
 */
export function resolveCandidate(path, cwd) {
  const looksAbsolute = /^[A-Za-z]:[\\/]/.test(path) || path.startsWith('\\\\') || path.startsWith('/')
  if (looksAbsolute || typeof cwd !== 'string' || cwd.length === 0) return path
  const separator = cwd.includes('\\') ? '\\' : '/'
  return `${cwd.replace(/[\\/]+$/, '')}${separator}${path.replace(/^\.?[\\/]/, '')}`
}

/**
 * Confirm a download's total size with one short `HEAD` request, cached for the
 * life of the process.
 *
 * @param {string} url - the download URL.
 * @param {{ fetch?: typeof fetch, timeoutMs?: number, now?: number }} [options]
 * @returns {Promise<{ ok: boolean, total?: number, error?: string }>} the outcome.
 */
export async function headTotal(url, options = {}) {
  const cached = headCache.get(url)
  const now = options.now ?? Date.now()
  if (cached !== undefined && (cached.sealed || now - cached.at < 60_000)) {
    const value = await cached.promise
    if (value.ok || cached.sealed) return value
  }
  const request = options.fetch ?? globalThis.fetch
  if (typeof request !== 'function') return { ok: false, error: 'no fetch implementation' }
  const timeoutMs = options.timeoutMs ?? HEAD_TIMEOUT_MS
  /** @type {{ at: number, sealed: boolean, promise: Promise<{ ok: boolean, total?: number, error?: string }> }} */
  const entry = { at: now, sealed: false, promise: Promise.resolve({ ok: false, error: 'pending' }) }
  entry.promise = (async () => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await request(url, { method: 'HEAD', signal: controller.signal, redirect: 'follow' })
      if (!response.ok) return { ok: false, error: `HEAD HTTP ${response.status}` }
      const raw = response.headers?.get?.('content-length')
      const total = raw === null || raw === undefined ? NaN : Number(raw)
      if (!Number.isFinite(total) || total <= 0) return { ok: false, error: 'no Content-Length' }
      entry.sealed = true
      return { ok: true, total }
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) }
    } finally {
      clearTimeout(timer)
    }
  })()
  headCache.set(url, entry)
  if (headCache.size > 64) {
    for (const [key, value] of headCache) {
      if (!value.sealed) continue
      headCache.delete(key)
      if (headCache.size <= 32) break
    }
  }
  return entry.promise
}

/**
 * Read the tail of a file as text, or report why that was not possible.
 *
 * At most `TAIL_BYTES` are read, the handle is shared (never exclusive), and the
 * first partial line of a mid-file window is dropped.
 *
 * @param {string} path - the file to read.
 * @param {number} [bytes] - window size.
 * @returns {Promise<{ ok: true, text: string, size: number } | { ok: false, error: string }>}
 */
export async function readTail(path, bytes = TAIL_BYTES) {
  let handle
  try {
    handle = await open(path, 'r')
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) }
  }
  try {
    const info = await handle.stat()
    if (!info.isFile()) return { ok: false, error: 'not a regular file' }
    const start = info.size > bytes ? info.size - bytes : 0
    const length = info.size - start
    if (length <= 0) return { ok: true, text: '', size: info.size }
    const buffer = Buffer.allocUnsafe(length)
    const read = await handle.read(buffer, 0, length, start)
    let text = buffer.subarray(0, read.bytesRead).toString('utf8')
    if (start > 0) {
      const newline = text.indexOf('\n')
      text = newline === -1 ? '' : text.slice(newline + 1)
    }
    return { ok: true, text, size: info.size }
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) }
  } finally {
    await handle.close().catch(() => {})
  }
}

/**
 * A percentage read from a progress line.
 * @typedef {{ percent: number, total?: number }} LogReading
 */

/**
 * Find the last progress reading in a log tail.
 *
 * A step count (`120/500`, `step 3|8`, `120 of 500`) is preferred over a bare
 * percentage because it also yields the total; the last valid match of either
 * kind wins, and impossible numbers (a total of zero, a total beyond `TOTAL_MAX`)
 * are ignored rather than clamped.
 *
 * @param {string} text - the tail text.
 * @returns {LogReading | undefined} the reading.
 */
export function parseLogProgress(text) {
  /** @type {LogReading | undefined} */
  let reading
  for (const line of text.split('\n')) {
    let match
    const percentAll = /(\d+(?:\.\d+)?)\s*%/g
    while ((match = percentAll.exec(line)) !== null) {
      const percent = clampPercent(Number(match[1]))
      if (percent !== undefined) reading = { percent }
    }
    const stepPatterns = [/(\d+)\s*[/|]\s*(\d+)/g, /(\d+)\s+of\s+(\d+)/g]
    for (const pattern of stepPatterns) {
      while ((match = pattern.exec(line)) !== null) {
        const done = Number(match[1])
        const total = Number(match[2])
        if (!Number.isFinite(done) || !Number.isFinite(total)) continue
        if (total <= 0 || total > TOTAL_MAX) continue
        if (done < 0 || done > total) continue
        const percent = clampPercent((done / total) * 100)
        if (percent !== undefined) reading = { percent, total }
      }
    }
  }
  return reading
}

/**
 * Keep one job's rate samples, pruned once the job disappears.
 *
 * @param {Map<string, any>} jobState - the poll-crossing map.
 * @param {string} id - the call id.
 * @param {number} now - the poll time.
 * @returns {any} this job's record.
 */
function jobRecord(jobState, id, now) {
  let record = jobState.get(id)
  if (record === undefined) {
    record = { samplePercent: undefined, sampleAt: undefined, sampleSize: undefined }
    jobState.set(id, record)
  }
  record.seenAt = now
  return record
}

/**
 * Estimate an ETA from the change between two observations of one percentage.
 *
 * The rate is measured between *observed* samples rather than from the job's
 * start: a program that does nothing for five seconds and then prints `5%` has a
 * real rate of 5% per the interval since that first line, and charging it for
 * the startup would produce an ETA that is far too long. `null` means not enough
 * has been seen yet, which is the honest answer for the first one or two polls.
 *
 * @param {any} record - the job's rate record, updated in place.
 * @param {number} percent - the percentage observed now.
 * @param {number} at - the observation time.
 * @returns {number | null} a clamped ETA, or null when it cannot be estimated.
 */
export function estimateEta(record, percent, at) {
  const previousPercent = record.samplePercent
  const previousAt = record.sampleAt
  record.samplePercent = percent
  record.sampleAt = at
  if (previousPercent === undefined || previousAt === undefined) return null
  const gained = percent - previousPercent
  const elapsed = at - previousAt
  // A stalled job yields no rate; a finished one needs no ETA.
  if (!(gained > 0) || !(elapsed > 0) || percent >= 100) return null
  return clampEta((100 - percent) / (gained / elapsed))
}

/** Drop rate samples for jobs that are no longer running. */
export function pruneJobState(jobState, now, keep = 512) {
  for (const [id, record] of jobState) {
    if (now - (record.seenAt ?? 0) > 300_000) jobState.delete(id)
  }
  while (jobState.size > keep) {
    const oldest = jobState.keys().next()
    if (oldest.done) break
    jobState.delete(oldest.value)
  }
}

/**
 * Progress from a command that writes its own progress into a file.
 *
 * @param {{ path: string, call: any, record: any, now: number, cwd?: string }} input
 * @returns {Promise<{ progress: any, note: string | null }>}
 */
async function probeLog(input) {
  const absolute = resolveCandidate(input.path, input.cwd)
  const tail = await readTail(absolute)
  if (!tail.ok) return { progress: null, note: `无法读取进度文件 (${tail.error})` }
  if (tail.size === 0) return { progress: null, note: '进度文件为空' }
  const reading = parseLogProgress(tail.text.split('\n').slice(-TAIL_LINES).join('\n'))
  if (reading === undefined) return { progress: null, note: '无可识别的进度输出' }
  return {
    progress: {
      percent: reading.percent,
      etaMs: estimateEta(input.record, reading.percent, input.now),
      source: 'log',
    },
    note: null,
  }
}

/**
 * Progress from a download whose total a `HEAD` request can confirm.
 *
 * @param {{ url: string, path: string, call: any, record: any, now: number, options: any, cwd?: string }} input
 * @returns {Promise<{ progress: any, note: string | null }>}
 */
async function probeSize(input) {
  const absolute = resolveCandidate(input.path, input.cwd)
  /** @type {number} */
  let size
  try {
    const info = await stat(absolute)
    if (!info.isFile()) return { progress: null, note: '下载目标不是文件' }
    size = info.size
  } catch (error) {
    return { progress: null, note: `下载目标尚不可用 (${error instanceof Error ? error.message : String(error)})` }
  }
  const head = await headTotal(input.url, input.options)
  if (!head.ok) return { progress: null, note: `无法取得总大小 (${head.error})` }
  const total = head.total ?? 0
  if (total <= 0) return { progress: null, note: '总大小为零' }
  const percent = clampPercent((size / total) * 100)
  if (percent === undefined) return { progress: null, note: '进度超出 0-100' }

  // The rate comes from the file's growth between two observations; the ETA then
  // follows the percentage, which is why neither appears on the first sample.
  const record = input.record
  const previousSize = record.sampleSize
  const previousAt = record.sampleAt
  record.sampleSize = size
  record.sampleAt = input.now
  let etaMs = null
  if (previousSize !== undefined && previousAt !== undefined) {
    const gained = ((size - previousSize) / total) * 100
    const elapsed = input.now - previousAt
    if (gained > 0 && elapsed > 0 && percent < 100) etaMs = clampEta((100 - percent) / (gained / elapsed))
  }
  return { progress: { percent, etaMs, source: 'size' }, note: null }
}

/**
 * Choose the one note that best explains an empty `progress`.
 *
 * "There is nothing to read" beats "here is why the file I guessed at could not
 * be read": a command with no recognisable output path is simply not observable,
 * and saying so is more honest than reporting an ENOENT for a path that was
 * derived from a redirect to `nul` or from a quoted fragment.
 *
 * @param {string[]} notes - candidate explanations, best first.
 * @returns {string} the note.
 */
function bestNote(notes) {
  const usable = notes.filter((note) => typeof note === 'string' && note.length > 0)
  const specific = usable.find((note) => !note.startsWith('无法读取进度文件'))
  return specific ?? usable[0] ?? '无进度输出'
}

/**
 * Decide one unmatched call's observable progress.
 *
 * The two sources are tried cheapest-first: a redirect target that actually
 * carries a progress line wins, otherwise a URL plus a destination becomes a
 * size probe, and otherwise the row is reported with `progress: null` and a note.
 *
 * @param {any} call - `{ id, session, name, raw, time, cwd }`.
 * @param {any} record - the job's poll-crossing rate record.
 * @param {{ now: number, jobState: Map<string, any>, fetch?: typeof fetch, timeoutMs?: number }} context
 * @returns {Promise<{ progress: any, progressNote: string | null }>}
 */
export async function probeProgress(call, record, context) {
  // Detection runs on the *raw* command itself: never on the rendered line,
  // which is capped for display and would truncate a trailing redirect, and
  // never on the stored JSON, whose escaped quotes would make `> "out.log"`
  // look like a redirect to `\"out.log\"`.
  const command = commandTextOf(parseArguments(call.raw))
  const url = detectUrl(command)
  const rawOutputPath = detectOutputPath(command)
  const outputPath =
    rawOutputPath !== undefined && rawOutputPath.toLowerCase() !== 'nul' ? rawOutputPath : undefined

  const notes = []
  if (outputPath !== undefined) {
    const logged = await probeLog({ path: outputPath, call, record, now: context.now, cwd: call.cwd })
    if (logged.progress !== null) return logged
    notes.push(logged.note)
  }
  if (url !== undefined && outputPath !== undefined) {
    const sized = await probeSize({
      url,
      path: outputPath,
      call,
      record,
      now: context.now,
      cwd: call.cwd,
      options: { fetch: context.fetch, timeoutMs: context.timeoutMs },
    })
    if (sized.progress !== null) return sized
    notes.push(sized.note)
  }
  if (notes.length === 0) return { progress: null, progressNote: '无进度输出' }
  return { progress: null, progressNote: `无进度输出（${bestNote(notes)}）` }
}

/**
 * Extract the correlation id a `tool/result` reports.
 *
 * The id lives at `data.message.toolCallId` in the log format this build reads,
 * with `data.message.source.callId` as the equivalent beside it; the two
 * flat spellings are also accepted so a format change cannot silently turn every
 * finished call into a phantom job.
 *
 * @param {any} data - `tool/result.data`.
 * @returns {string | undefined} the call id.
 */
export function resultCallId(data) {
  if (data === null || typeof data !== 'object') return undefined
  if (typeof data.toolCallId === 'string') return data.toolCallId
  if (typeof data.callId === 'string') return data.callId
  const message = data.message
  if (message !== null && typeof message === 'object') {
    if (typeof message.toolCallId === 'string') return message.toolCallId
    const source = message.source
    if (source !== null && typeof source === 'object' && typeof source.callId === 'string') return source.callId
  }
  return undefined
}

/**
 * Fold one artifact's already-decoded lines into activity facts.
 *
 * @param {string[]} lines - the artifact's JSONL lines.
 * @param {{ sessionId: string, path: string, mtimeMs: number }} artifact
 * @returns {{ sessionId: string, path: string, mtimeMs: number, depth: number, label: string | undefined, model: string | undefined, cwd: string | undefined, running: boolean, turn: number | null, turnStartedAt: number | null, turnCount: number, lastActivityAt: number, calls: any[] }}
 */
export function foldActivity(lines, artifact) {
  let depth = 0
  let label
  let cwd
  let descriptorModel
  let routeModel
  let turnStarts = 0
  /** @type {number | null} */
  let currentTurn = null
  /**
   * Start of the newest turn *seen*, kept after that turn closes so an idle
   * agent can still report how long its last turn ran. `currentTurn` is what
   * distinguishes "that turn closed" from "that turn is still open".
   * @type {number | null}
   */
  let lastTurnStartedAt = null
  let lastTurnEndedAt
  let lastActivityAt = 0
  /** @type {Map<string, any>} */
  const calls = new Map()
  /** @type {Set<string>} */
  const results = new Set()
  // ---- reaction facts (additive; the pet's reaction layer reads them) --------
  /** Every call of this artifact, by id, so a tool/result can name its tool. */
  const callsById = new Map()
  /** @type {any} */
  let newestCall = null
  /** @type {any} */
  let newestResult = null
  /** Newest *failing* result: a later successful call must not hide the error. */
  /** @type {any} */
  let newestFailed = null
  /** @type {any} */
  let turnStart = null
  /** @type {any} */
  let turnEnd = null
  /** tokens per turn number, summed from assistant/message usage. */
  const usageByTurn = new Map()
  let lastUserAt = 0
  /** @type {string | null} */
  let lastUserText = null
  let lastStepStart = 0
  let lastStepEnd = 0
  let lastAssistantAt = 0

  for (const line of lines) {
    /** @type {any} */
    let record
    try {
      record = JSON.parse(line)
    } catch {
      continue
    }
    if (record === null || typeof record !== 'object') continue
    const time = typeof record.time === 'number' ? record.time : 0
    if (time > lastActivityAt) lastActivityAt = time
    switch (record.type) {
      case 'session': {
        depth = typeof record.delegationDepth === 'number' ? record.delegationDepth : 0
        if (typeof record.cwd === 'string') cwd = record.cwd
        break
      }
      case 'subagent/descriptor': {
        const data = record.data
        if (data !== null && typeof data === 'object') {
          if (typeof data.label === 'string' && data.label.length > 0) label = data.label
          if (typeof data.agentModel === 'string' && data.agentModel.length > 0) descriptorModel = data.agentModel
        }
        break
      }
      case 'request/context': {
        if (typeof record.data?.model === 'string') routeModel = record.data.model
        break
      }
      case 'request/header': {
        const model = record.data?.header?.config?.model
        if (typeof model === 'string') routeModel = model
        break
      }
      case 'turn/start': {
        turnStarts += 1
        const turn = record.data?.turn
        currentTurn = typeof turn === 'number' ? turn : turnStarts
        lastTurnStartedAt = time
        turnStart = { time, turn: currentTurn }
        break
      }
      case 'turn/end': {
        lastTurnEndedAt = time
        const turn = typeof record.data?.turn === 'number' ? record.data.turn : currentTurn
        const reason = record.data?.reason
        turnEnd = {
          time,
          turn,
          reason: typeof reason?.kind === 'string' ? reason.kind : null,
          ms: lastTurnStartedAt !== null ? Math.max(0, time - lastTurnStartedAt) : null,
          tokens: usageByTurn.get(turn) ?? null,
        }
        currentTurn = null
        break
      }
      case 'tool/call': {
        const data = record.data
        if (data === null || typeof data !== 'object') break
        const id = typeof data.callId === 'string' ? data.callId : undefined
        if (id === undefined) break
        const call = {
          id,
          session: artifact.sessionId,
          name: typeof data.name === 'string' ? data.name : 'tool',
          raw: data.arguments,
          time,
          cwd,
        }
        calls.set(id, call)
        callsById.set(id, call)
        if (newestCall === null || time >= newestCall.time) newestCall = call
        break
      }
      case 'tool/result': {
        const id = resultCallId(record.data)
        if (id !== undefined) results.add(id)
        const data = record.data
        const error = data !== null && typeof data === 'object' ? data.error : undefined
        const isError = data?.message?.isError === true || (error !== null && error !== undefined)
        const result = {
          id,
          time,
          ok: !isError,
          error: error === null || error === undefined
            ? null
            : (typeof error === 'string' ? error : [error.name, error.code].filter(Boolean).join('/') || 'error'),
        }
        if (newestResult === null || time >= newestResult.time) newestResult = result
        if (!result.ok && (newestFailed === null || time >= newestFailed.time)) newestFailed = result
        break
      }
      case 'assistant/message': {
        lastAssistantAt = time
        const usage = record.data?.usage
        const turn = record.data?.turn
        if (usage !== null && usage !== undefined && typeof turn === 'number') {
          const total = typeof usage.totalTokens === 'number'
            ? usage.totalTokens
            : (usage.inputTokens ?? 0) + (usage.outputTokens ?? 0)
          usageByTurn.set(turn, (usageByTurn.get(turn) ?? 0) + total)
        }
        break
      }
      case 'user/message': {
        if (record.data?.source?.kind === 'user') {
          lastUserAt = time
          const part = (Array.isArray(record.data?.content) ? record.data.content : []).find(
            (c) => c !== null && typeof c === 'object' && c.type === 'text' && typeof c.text === 'string',
          )
          if (part !== undefined) lastUserText = String(part.text).replace(/\s+/g, ' ').trim().slice(0, 120)
        }
        break
      }
      case 'step/start': {
        lastStepStart = time
        break
      }
      case 'step/end': {
        lastStepEnd = time
        break
      }
      default:
        break
    }
  }

  /** @type {any[]} */
  const unmatched = []
  for (const [id, call] of calls) {
    if (results.has(id)) continue
    unmatched.push(call)
  }
  unmatched.sort((left, right) => left.time - right.time)

  return {
    sessionId: artifact.sessionId,
    path: artifact.path,
    mtimeMs: artifact.mtimeMs,
    depth,
    label,
    model: descriptorModel ?? routeModel,
    cwd,
    running: currentTurn !== null,
    turn: currentTurn,
    turnStartedAt: lastTurnStartedAt,
    turnEndedAt: currentTurn === null ? lastTurnEndedAt : undefined,
    turnCount: turnStarts,
    lastActivityAt: lastActivityAt > 0 ? lastActivityAt : artifact.mtimeMs,
    calls: unmatched,
    // reaction facts (additive)
    newestCall,
    newestResult: newestResult === null ? null : { ...newestResult, name: newestResult.id !== undefined ? (callsById.get(newestResult.id)?.name ?? null) : null },
    newestFailed: newestFailed === null ? null : { ...newestFailed, name: newestFailed.id !== undefined ? (callsById.get(newestFailed.id)?.name ?? null) : null },
    turnStart,
    turnEnd,
    lastUserAt,
    lastUserText,
    lastStepStart,
    lastStepEnd,
    lastAssistantAt,
  }
}

/**
 * Summarise the newest tool call/result facts across sessions for the pet's
 * reaction layer (REACTIONS-SPEC §3.2/§5).
 *
 * @param {any[]} rows - folded activity rows.
 * @param {number} now - the poll time.
 * @returns {{ tool: any, turn: any, lastUserAt: number, lastUserText: string | null, streaming: { active: boolean, at: number }, lastBusyAt: number }}
 */
export function buildSignals(rows, now) {
  /** @type {any} */
  let call = null
  /** @type {any} */
  let result = null
  /** @type {any} */
  let failed = null
  /** @type {any} */
  let turnEnd = null
  let lastUserAt = 0
  /** @type {string | null} */
  let lastUserText = null
  let lastStepStart = 0
  let lastStepEnd = 0
  let lastBusyAt = 0
  for (const row of rows) {
    if (row.newestCall !== null && row.newestCall !== undefined && (call === null || row.newestCall.time > call.time)) call = row.newestCall
    if (row.newestResult !== null && row.newestResult !== undefined && (result === null || row.newestResult.time > result.time)) result = row.newestResult
    if (row.newestFailed !== null && row.newestFailed !== undefined && (failed === null || row.newestFailed.time > failed.time)) failed = row.newestFailed
    if (row.turnEnd !== null && row.turnEnd !== undefined && (turnEnd === null || row.turnEnd.time > turnEnd.time)) turnEnd = row.turnEnd
    if (row.lastUserAt > lastUserAt) { lastUserAt = row.lastUserAt; lastUserText = row.lastUserText }
    if (row.lastStepStart > lastStepStart) lastStepStart = row.lastStepStart
    if (row.lastStepEnd > lastStepEnd) lastStepEnd = row.lastStepEnd
    if (row.lastActivityAt > lastBusyAt) lastBusyAt = row.lastActivityAt
  }
  // The tool's phase is whichever of call/result is newer, and the result names
  // its own tool (kept above), so a read that failed still reports `read`.
  /** @type {any} */
  let tool = null
  if (call !== null) {
    tool = {
      name: call.name,
      at: call.time,
      phase: result !== null && result.time >= call.time ? 'result' : 'call',
      ok: null,
      error: null,
      summary: summariseArguments(call.raw),
      session: call.session,
    }
    if (tool.phase === 'result') {
      tool.ok = result.ok
      tool.error = result.error
      tool.name = result.name ?? call.name
    }
  } else if (result !== null) {
    tool = { name: result.name ?? 'tool', at: result.time, phase: 'result', ok: result.ok, error: result.error, summary: null, session: null }
  }
  return {
    tool,
    // The newest *failure*, kept apart from `tool`: a call that starts right after
    // a failed one must not hide the error (it still gets its 1.6 s face).
    lastError: failed === null
      ? null
      : { name: failed.name ?? 'tool', at: failed.time, error: failed.error, session: null },
    turn: turnEnd === null ? null : { phase: 'end', at: turnEnd.time, reason: turnEnd.reason, ms: turnEnd.ms, tokens: turnEnd.tokens },
    lastUserAt,
    lastUserText,
    streaming: { active: lastStepStart > lastStepEnd && now - lastStepStart < 120000, at: lastStepStart },
    lastBusyAt: Math.max(lastBusyAt, lastUserAt, lastStepStart),
  }
}

/**
 * The one-line argument summary the reaction layer shows under a bubble
 * (REACTIONS-SPEC §3.2: command -> file_path -> path -> pattern -> query -> url
 * -> title -> description -> prompt, then `queries[0]`, flattened to 46 chars).
 *
 * @param {any} raw - `tool/call.data.arguments`.
 * @returns {string | null} the summary, or null when there is nothing to show.
 */
export function summariseArguments(raw) {
  const parsed = parseArguments(raw)
  if (parsed === undefined || parsed === null) return null
  let value
  if (typeof parsed === 'string') value = parsed
  else if (typeof parsed === 'object') {
    for (const key of SUMMARY_ORDER) {
      const candidate = parsed[key]
      if (typeof candidate === 'string' && candidate.length > 0) { value = candidate; break }
      if (Array.isArray(candidate) && typeof candidate[0] === 'string' && candidate[0].length > 0) { value = candidate[0]; break }
    }
  }
  if (typeof value !== 'string') return null
  const flat = value.replace(/\s+/g, ' ').trim()
  if (flat.length === 0) return null
  return flat.length > 46 ? `${flat.slice(0, 46)}…` : flat
}

/**
 * Fold one artifact, reusing the previous fold while the artifact is unchanged.
 *
 * The key carries the artifact's modification time and size, so a session that
 * grows is re-decoded and an idle one costs a map lookup. That matters because
 * every poll re-reads *all* artifacts for live state while only the growing ones
 * can have changed.
 *
 * @param {{ sessionId: string, path: string, mtimeMs: number, size?: number }} artifact
 * @param {{ cache?: Map<string, any> }} [options]
 * @returns {Promise<{ rows: any[], cached: boolean }>} the folded rows.
 */
export async function foldArtifact(artifact, options = {}) {
  const cache = options.cache ?? foldCache
  const key = `${artifact.path}|${artifact.mtimeMs}|${artifact.size ?? ''}`
  const cached = cache.get(key)
  if (cached !== undefined) return { rows: cached.value, cached: true }
  const bytes = await readFile(artifact.path)
  const lines = readZstdJsonlLines(bytes)
  const rows = [foldActivity(lines, artifact)]
  cache.set(key, { key, value: rows })
  while (cache.size > FOLD_CACHE_MAX) {
    const oldest = cache.keys().next()
    if (oldest.done) break
    cache.delete(oldest.value)
  }
  return { rows, cached: false }
}

/**
 * Project folded activity onto the snapshot's `agents` array.
 *
 * Every `delegationDepth > 0` session appears, running first and then most
 * recently active. The widget's own `agentsMax` decides how many are drawn.
 *
 * @param {any[]} rows - folded activity rows.
 * @param {number} now - the snapshot timestamp.
 * @returns {any[]} the agent rows.
 */
export function buildAgents(rows, now) {
  /** @type {any[]} */
  const agents = []
  for (const row of rows) {
    if (!(row.depth > 0)) continue
    const startedAt = row.turnStartedAt ?? row.lastActivityAt
    /** Duration of the last turn that actually closed; 0 when the log has none. */
    const idleElapsed =
      row.turnStartedAt !== undefined && row.turnEndedAt !== undefined
        ? row.turnEndedAt - row.turnStartedAt
        : 0
    const elapsed = row.running ? now - startedAt : idleElapsed
    agents.push({
      id: row.sessionId,
      label: row.label ?? row.sessionId,
      state: row.running ? 'running' : 'idle',
      model: row.model ?? null,
      turn: row.turn ?? row.turnCount,
      startedAt,
      elapsedMs: Math.max(0, Math.round(elapsed)),
      sinceLastWriteMs: Math.max(0, Math.round(now - row.mtimeMs)),
      activityAt: row.lastActivityAt,
    })
  }
  agents.sort(
    (left, right) =>
      (left.state === right.state ? 0 : left.state === 'running' ? -1 : 1) ||
      right.activityAt - left.activityAt,
  )
  return agents.map((agent) => ({
    id: agent.id,
    label: agent.label,
    state: agent.state,
    model: agent.model,
    turn: agent.turn,
    startedAt: agent.startedAt,
    elapsedMs: agent.elapsedMs,
    sinceLastWriteMs: agent.sinceLastWriteMs,
  }))
}

/**
 * Project every unmatched call onto the snapshot's `jobs` array, oldest first.
 *
 * @param {any[]} calls - unmatched calls across all sessions, oldest first.
 * @param {number} now - the snapshot timestamp.
 * @returns {any[]} the job rows, without progress (that is added by the caller).
 */
export function buildJobs(calls, now) {
  return calls.map((call) => ({
    id: call.id,
    session: call.session,
    // The raw tool name (`read` / `write` / `pwsh` / `web_search` …): the panel's
    // `program` is the *inner* program (`pwsh`/`node`/`python`), and the pet's
    // reaction layer classifies by tool, not by program (REACTIONS-SPEC §10 坑 7).
    name: call.name ?? null,
    tool: call.name ?? null,
    program: programOf(parseArguments(call.raw), call.name),
    command: renderCommand(call.raw),
    startedAt: call.time,
    elapsedMs: Math.max(0, now - call.time),
    progress: null,
    progressNote: null,
  }))
}

/**
 * Collect the agents and jobs of one poll.
 *
 * @param {any[]} artifacts - `listSessionArtifacts()` rows.
 * @param {{ now: number, jobState: Map<string, any>, jobsMax?: number, fetch?: typeof fetch, timeoutMs?: number, cache?: Map<string, any>, concurrency?: number, tailProbe?: boolean }} options
 * @returns {Promise<{ agents: any[], jobs: any[], folds: number, skipped: number, unmatched: number }>}
 */
export async function collectActivity(artifacts, options) {
  const now = options.now
  const limit = Math.max(1, options.concurrency ?? 8)
  const jobsMax = Math.max(1, options.jobsMax ?? DEFAULT_JOBS_MAX)
  /** @type {any[]} */
  const rows = []
  let folds = 0
  let skipped = 0
  let cursor = 0

  const worker = async () => {
    for (;;) {
      const index = cursor
      cursor += 1
      const artifact = artifacts[index]
      if (artifact === undefined) return
      try {
        const folded = await foldArtifact(artifact, { cache: options.cache })
        folds += 1
        if (folded.cached) skipped += 1
        for (const row of folded.rows) rows.push(row)
      } catch {
        // An artifact that cannot be decoded contributes nothing; the usage fold
        // reports the same failure on its own error channel.
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, artifacts.length) }, worker))

  /** @type {any[]} */
  const calls = []
  for (const row of rows) for (const call of row.calls) calls.push(call)
  calls.sort((left, right) => left.time - right.time || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0))

  const agents = buildAgents(rows, now)
  const selected = calls.slice(0, jobsMax)
  const jobs = buildJobs(selected, now)

  if (options.tailProbe !== false) {
    for (let index = 0; index < jobs.length; index += 1) {
      const job = jobs[index]
      const call = selected[index]
      const record = jobRecord(options.jobState, job.id, now)
      try {
        const probed = await probeProgress(call, record, {
          now,
          jobState: options.jobState,
          fetch: options.fetch,
          timeoutMs: options.timeoutMs,
        })
        job.progress = probed.progress
        job.progressNote = probed.progressNote
      } catch (error) {
        job.progress = null
        job.progressNote = `无法探测进度 (${error instanceof Error ? error.message : String(error)})`
      }
    }
  }
  pruneJobState(options.jobState, now)

  return { agents, jobs, folds, skipped, unmatched: calls.length, signals: buildSignals(rows, now) }
}
