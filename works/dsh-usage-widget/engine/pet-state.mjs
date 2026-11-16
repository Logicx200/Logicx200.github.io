/**
 * The engine's side of the pet integration: fold one poll into the pet's state
 * line and publish it where the renderer page can read it.
 *
 * Two jobs, both deliberately small:
 *
 *   1. **Own the inputs `pet/state.mjs` cannot know.** The model is pure and
 *      takes `snapshot`, `lastEventAt`, `dshRunning` and `now` from its caller.
 *      The engine is the only writer of `event` lines, so it is the honest owner
 *      of `lastEventAt`; `dshRunning` comes from the panel's heartbeat file
 *      (see below); `now` and `snapshot` are already in hand.
 *
 *   2. **Write `pet/renderer/state.json`** — the one file the renderer page
 *      polls — atomically, so a reader can never see half a document.
 *
 * The state *decision* itself is never re-implemented here: every answer comes
 * from `computeState()` in `pet/state.mjs`, the frozen contract documented in
 * `pet/STATE-PROTOCOL.md`.
 *
 * ## `dshRunning`: the panel's heartbeat file
 *
 * Three cheap candidates were on the table (a `tasklist` probe every ~5 s, a TCP
 * probe of the GUI port, or a small file the panel writes). The heartbeat file
 * wins on consistency and cost:
 *
 *   - The panel already runs `Get-Process 'DeepSeek Harness'` every 2 s to
 *     decide whether to show itself at all. Writing that same answer to a
 *     heartbeat file means the pet's `offline` state and the panel's visibility
 *     can never disagree — they are literally the same observation. A separate
 *     probe could report "up" while the panel hides, or the reverse.
 *   - It costs the engine one tiny `readFileSync` per poll and spawns **no**
 *     process (a `tasklist` probe would start a child every 5 s for the whole
 *     life of the widget).
 *   - The file is per-user and lives in `os.tmpdir()`, so the path is ASCII on a
 *     normal install; nothing is written into the project tree.
 *
 * When the file is missing, unreadable, malformed or older than
 * `HEARTBEAT_STALE_MS`, `dshRunning` is reported as **unknown** (not `false`):
 * `pet/state.mjs` then infers the state from a fresh snapshot and can never be
 * tricked into a false `offline` (or a stale `working`) by a heartbeat that
 * stopped. A standalone `node engine/cli.mjs --once` therefore keeps working
 * with no panel running at all.
 *
 * @module dsh-usage-widget/engine/pet-state
 */

import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { computeState } from '../pet/state.mjs'

/** This file's directory: `…/dsh-usage-widget/engine`. */
const ENGINE_DIR = dirname(fileURLToPath(import.meta.url))

/** The widget root: `…/dsh-usage-widget`. */
export const ROOT_DIR = join(ENGINE_DIR, '..')

/** Where the renderer page polls for the state line (`pet/renderer/state.json`). */
export const PET_STATE_PATH = join(ROOT_DIR, 'pet', 'renderer', 'state.json')

/** Where the reaction signals are published (`pet/renderer/signals.json`). */
export const SIGNALS_PATH = join(ROOT_DIR, 'pet', 'renderer', 'signals.json')

/** The heartbeat file the panel writes. Must match `Write-DshHeartbeat` in `ui/widget.ps1`. */
export const HEARTBEAT_FILE_NAME = 'dsh-usage-widget-dsh-running.json'

/**
 * The panel's heartbeat path: `os.tmpdir()`, so it is per-user and ASCII on a
 * normal Windows install.
 *
 * @returns {string} an absolute path.
 */
export function defaultHeartbeatPath() {
  return join(tmpdir(), HEARTBEAT_FILE_NAME)
}

/** A heartbeat older than this is disbelieved (`dshRunning` becomes unknown). */
export const HEARTBEAT_STALE_MS = 10_000

/** How long one heartbeat reading is reused. The panel writes every 2 s. */
export const HEARTBEAT_CACHE_MS = 2_000

/**
 * Parse a heartbeat document. Anything unexpected yields `null` — a malformed
 * file must degrade to "unknown", never to a wrong answer.
 *
 * @param {unknown} text - the file's contents.
 * @returns {{ running: boolean, at: number, pid: number | undefined } | null}
 */
export function parseHeartbeat(text) {
  if (typeof text !== 'string') return null
  let doc
  try {
    doc = JSON.parse(text)
  } catch {
    return null
  }
  if (doc === null || typeof doc !== 'object' || Array.isArray(doc)) return null
  if (typeof doc.running !== 'boolean') return null
  if (typeof doc.at !== 'number' || !Number.isFinite(doc.at)) return null
  return {
    running: doc.running,
    at: doc.at,
    pid: typeof doc.pid === 'number' && Number.isFinite(doc.pid) ? doc.pid : undefined,
  }
}

/**
 * The mutable per-engine state behind the pet line. One instance per engine
 * process, created by `createState()` in `cli.mjs` and carried across polls.
 *
 * @param {{ heartbeatPath?: string }} [options] - overrides, for tests.
 * @returns {{
 *   lastEventAt: number | null,
 *   heartbeat: { running: boolean, at: number, pid?: number } | null,
 *   heartbeatAt: number,
 *   heartbeatValue: boolean | undefined,
 *   heartbeatPath: string,
 * }} the tracker.
 */
export function createPetTracker(options = {}) {
  return {
    /** Newest `event` line this engine has emitted, in epoch ms. */
    lastEventAt: null,
    /** Last successfully parsed heartbeat (or null). */
    heartbeat: null,
    /** When the heartbeat was last read (0 = never). */
    heartbeatAt: 0,
    /** The cached `dshRunning` answer (undefined = unknown). */
    heartbeatValue: undefined,
    /** The panel's heartbeat file. */
    heartbeatPath:
      typeof options.heartbeatPath === 'string' && options.heartbeatPath.length > 0
        ? options.heartbeatPath
        : defaultHeartbeatPath(),
  }
}

/**
 * Record the events this poll is about to emit, so `working` can light up in the
 * same poll instead of one poll later.
 *
 * A baseline fold emits no events and must not be counted: a cold engine has no
 * event history, and the protocol is explicit that a cold poll must never fake
 * activity. `fresh` is therefore the list of *newly emitted* events only.
 *
 * @param {ReturnType<typeof createPetTracker>} tracker - the tracker.
 * @param {{ session: any, sample: { at: number } }[]} fresh - events about to be emitted.
 * @returns {number | null} the tracker's `lastEventAt` afterwards.
 */
export function noteEvents(tracker, fresh) {
  if (!Array.isArray(fresh)) return tracker.lastEventAt
  for (const item of fresh) {
    const at = item?.sample?.at
    if (typeof at !== 'number' || !Number.isFinite(at)) continue
    if (tracker.lastEventAt === null || at > tracker.lastEventAt) tracker.lastEventAt = at
  }
  return tracker.lastEventAt
}

/**
 * Read the panel's heartbeat, with a small cache.
 *
 * @param {ReturnType<typeof createPetTracker>} tracker - the tracker (caches the answer).
 * @param {number} now - poll time, epoch ms.
 * @param {{ cacheMs?: number, staleMs?: number }} [options] - overrides, for tests.
 * @returns {{ running: boolean, at: number, pid?: number } | null} the raw heartbeat, or null.
 */
export function readHeartbeat(tracker, now, options = {}) {
  const cacheMs = typeof options.cacheMs === 'number' ? options.cacheMs : HEARTBEAT_CACHE_MS
  if (tracker.heartbeatAt > 0 && now - tracker.heartbeatAt < cacheMs) return tracker.heartbeat
  tracker.heartbeatAt = now
  let text = null
  try {
    text = readFileSync(tracker.heartbeatPath, 'utf8')
  } catch {
    text = null
  }
  tracker.heartbeat = parseHeartbeat(text)
  return tracker.heartbeat
}

/**
 * The engine's `dshRunning` for one poll: `true`/`false` from a fresh heartbeat,
 * `undefined` (unknown) when there is none.
 *
 * @param {ReturnType<typeof createPetTracker>} tracker - the tracker.
 * @param {number} now - poll time, epoch ms.
 * @param {{ cacheMs?: number, staleMs?: number }} [options] - overrides, for tests.
 * @returns {boolean | undefined} the answer.
 */
export function observeDshRunning(tracker, now, options = {}) {
  const staleMs = typeof options.staleMs === 'number' ? options.staleMs : HEARTBEAT_STALE_MS
  const beat = readHeartbeat(tracker, now, options)
  let value
  if (beat === null || !(now - beat.at <= staleMs)) value = undefined
  else value = beat.running
  tracker.heartbeatValue = value
  return value
}

/**
 * Compute the pet's state line for one poll.
 *
 * @param {ReturnType<typeof createPetTracker>} tracker - the tracker.
 * @param {any} snapshot - the snapshot about to be emitted.
 * @param {number} now - poll time, epoch ms.
 * @param {{ session: any, sample: { at: number } }[]} [fresh] - events about to be emitted.
 * @param {{ cacheMs?: number, staleMs?: number }} [options] - overrides, for tests.
 * @returns {ReturnType<typeof computeState>} the state line (the frozen 7 fields).
 */
export function computePet(tracker, snapshot, now, fresh = [], options = {}) {
  noteEvents(tracker, fresh)
  const dshRunning = observeDshRunning(tracker, now, options)
  return computeState({
    snapshot,
    lastEventAt: tracker.lastEventAt,
    dshRunning,
    now,
    // Reaction signals (REACTIONS-SPEC §5): the activity category needs the newest
    // tool call/result, the turn end and whether the assistant is producing text.
    signals: options.signals,
  })
}

/**
 * Publish the reaction signals to `pet/renderer/signals.json`, atomically.
 *
 * Additive companion to `state.json`: `state.json` keeps the frozen seven-field
 * shape (STATE-PROTOCOL) while the page's reaction layer needs the raw facts
 * behind it (tool name/phase/ok, turn reason/ms/tokens, streaming, idle time).
 *
 * @param {any} signals - the signals document.
 * @param {string} [path] - the target file.
 * @returns {{ ok: boolean, error?: string }} the outcome.
 */
export function writeSignals(signals, path = SIGNALS_PATH) {
  return writeJsonAtomic(signals, path)
}

/**
 * Publish the state line to `pet/renderer/state.json`, atomically.
 *
 * Written to `<path>.<pid>.tmp` and renamed over the target, so the renderer's
 * 1.5 s poll either sees the previous document or the new one — never a partial
 * write. Failure is reported, never thrown: a read-only project directory must
 * not take the engine (and therefore the widget) down.
 *
 * @param {ReturnType<typeof computeState>} pet - the state line.
 * @param {string} [path] - the target file.
 * @returns {{ ok: boolean, error?: string }} the outcome.
 */
export function writePetState(pet, path = PET_STATE_PATH) {
  return writeJsonAtomic(pet, path)
}

/**
 * Write one JSON document to `path` through a temp file + rename.
 *
 * @param {any} value - the document.
 * @param {string} path - the target file.
 * @returns {{ ok: boolean, error?: string }} the outcome.
 */
function writeJsonAtomic(value, path) {
  const temp = `${path}.${process.pid}.tmp`
  try {
    mkdirSync(dirname(path), { recursive: true })
    writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
    renameSync(temp, path)
    return { ok: true }
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) }
  }
}

export default computePet
