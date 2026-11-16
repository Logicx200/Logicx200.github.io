/**
 * Host half of the DSH usage bridge — and its only half.
 *
 * The Harness already keeps a background-job registry behind `ctx.jobs`. This
 * plugin does not add a capability, a route, a service or a slot: it *mirrors*
 * that registry into one small JSON file so a standalone desktop widget can
 * render live progress without talking to the app at all.
 *
 * Three deliberate constraints shape the code below.
 *
 * 1. **It cannot affect the interface.** There is no `dsh.client` field, no
 *    bundle for the browser, no route and no tool. The only observable effect
 *    of loading this plugin is bytes appearing in one file.
 * 2. **It never consumes the model's output.** Live output is read through
 *    `jobs.readAt(id, from)`, an absolute-offset read that leaves the model's
 *    own cursor untouched. `jobs.read` is never called *anywhere* in this
 *    package, because it advances that cursor and would steal the output of a
 *    running job from the model that started it. The offline check proves this
 *    by making the stub's `read` throw.
 * 3. **It never throws into the host.** Every subscription callback, timer
 *    tick, ring read and file write is contained. A repeated failure is logged
 *    once and the plugin keeps running.
 *
 * The job registry is the only context property this plugin reads, so it is
 * declared in `inject`: Cordis then withholds `apply` entirely while no registry
 * is mounted, instead of letting the plugin trip the context proxy on an
 * undeclared name. `ctx.effect` is the other property it touches; that one is a
 * core Cordis method rather than a service, and needs no declaration.
 *
 * @module dsh-usage-bridge
 */

import { mkdir, rename, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'

/** Cordis plugin identity: must match the loader row's `id`/`name` linkage. */
export const name = 'usage-bridge'

/**
 * The one service this plugin consumes. Declaring it is what makes `ctx.jobs`
 * readable at all: a Cordis context is a proxy that throws on the property GET
 * itself for any name that is neither a core method nor an injected service, so
 * `?.` cannot make an undeclared lookup safe. Without a registry mounted, a
 * declared dependency leaves the plugin pending rather than failed.
 */
export const inject = ['jobs']

/** Poll period for ring reads and file writes, in milliseconds. */
const DEFAULT_INTERVAL_MS = 1_000

/** How much trailing output text is retained per job, in characters. */
const TAIL_LIMIT = 4_096

/** How long a settled job stays in the file so the widget can show a result. */
const SETTLED_TAIL_MS = 30_000

/** Hard cap on how much of one ring read is appended to the tail. */
const APPEND_CAP = 65_536

/** `lastLine` cap, per the widget contract. */
const LAST_LINE_LIMIT = 160

/** ETA clamp: below one second the estimate is noise, above a week it is a guess. */
const ETA_MIN_MS = 1_000
const ETA_MAX_MS = 7 * 24 * 60 * 60 * 1_000

/** Marker prepended when the retained tail is trimmed to stay bounded. */
const TRIM_MARKER = '…'

/**
 * Resolve the Harness home directory, matching the host-side convention used
 * by the other packages on this machine: `$DSH_HOME`, else `~/.dsh`.
 *
 * @returns {string} absolute Harness home.
 */
export function resolveDshHome() {
  const configured = process.env.DSH_HOME
  return typeof configured === 'string' && configured.length > 0
    ? configured
    : join(homedir(), '.dsh')
}

/**
 * Reject anything that cannot be a real `step 120/500`-style ratio.
 * @param {number} value - the numerator as written.
 * @param {number} total - the denominator as written.
 * @returns {boolean} whether the pair is worth reporting.
 */
function usableRatio(value, total) {
  if (!Number.isFinite(value) || !Number.isFinite(total)) return false
  if (total <= 0 || total > 1e12) return false
  if (value < 0 || value > total) return false
  return true
}

/**
 * Extract a completion percentage from one line of output.
 *
 * A percentage *with a unit* wins over a bare ratio, so `step 3/4 done 75%`
 * reports 75, and `47.5% of 12` reports 47.5 rather than the `of` ratio. The
 * *last* match on the line is the one reported, because a progress line
 * normally reads left to right and the freshest figure is on the right.
 *
 * @param {string} line - one line of retained output.
 * @returns {number | undefined} percent in `[0, 100]`, or undefined.
 */
function percentFromLine(line) {
  const percents = [...line.matchAll(/(\d+(?:\.\d+)?)\s*%/g)]
  for (let index = percents.length - 1; index >= 0; index -= 1) {
    const value = Number(percents[index][1])
    if (Number.isFinite(value) && value >= 0 && value <= 100) return value
  }
  const ratio = line.match(/(\d+)\s*(?:[/|]|\s+of\s+)\s*(\d+)/)
  if (ratio !== null) {
    const value = Number(ratio[1])
    const total = Number(ratio[2])
    if (usableRatio(value, total)) return (value / total) * 100
  }
  return undefined
}

/**
 * Find the percent carried by the *last* line in the retained tail that has
 * one, per the brief's "last progress-looking line" rule.
 *
 * @param {string} text - retained output tail.
 * @returns {number | undefined} percent in `[0, 100]`, or undefined.
 */
function parsePercent(text) {
  const lines = text.split('\n')
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const percent = percentFromLine(lines[index])
    if (percent !== undefined) return percent
  }
  return undefined
}

/**
 * Last non-empty line of the retained tail, trimmed and capped.
 * @param {string} text - retained output tail.
 * @returns {string | undefined} the display line, or undefined when empty.
 */
function parseLastLine(text) {
  const lines = text.split('\n')
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index].trim()
    if (line.length > 0) return line.slice(0, LAST_LINE_LIMIT)
  }
  return undefined
}

/**
 * Clamp a raw estimate into the reporting window.
 *
 * The ceiling is a real answer, not a rejection: a measured rate that implies
 * more than a week is still the best estimate available, it is merely capped.
 * Only a non-positive or non-finite estimate is unknown.
 *
 * Exported because it is the contract's boundary and is not otherwise
 * observable through the public surface: with a one-second tick, no reachable
 * sample pair produces an estimate below the floor.
 *
 * @param {number} eta - raw milliseconds.
 * @returns {number | undefined} clamped value, or undefined when implausible.
 */
export function clampEta(eta) {
  if (!Number.isFinite(eta) || eta <= 0) return undefined
  return Math.round(Math.min(ETA_MAX_MS, Math.max(ETA_MIN_MS, eta)))
}

/**
 * Fold one ring read into a job's cached state.
 *
 * The read is non-consuming: `from` is the last `next` observed for this job,
 * so the bridge's cursor is its own and independent of the model's. A lossy
 * read means the retained window has already slid past our cursor; the gap
 * cannot and should not be reconstructed, so the cursor resyncs to the
 * registry's `next` and the reader continues from live output.
 *
 * @param {{ offset: number, text: string }} cache - mutable per-job read cache.
 * @param {unknown} read - whatever the registry returned.
 * @returns {{ dropped: boolean }} whether the read was lossy or unusable.
 */
function foldRead(cache, read) {
  if (read === null || typeof read !== 'object') return { dropped: true }
  const chunks = Array.isArray(read.chunks) ? read.chunks : []
  const next = Number(read.next)
  let text = cache.text
  for (const chunk of chunks) {
    const piece = typeof chunk?.text === 'string' ? chunk.text : ''
    if (piece.length === 0) continue
    text += piece.length > APPEND_CAP ? piece.slice(piece.length - APPEND_CAP) : piece
  }
  if (text.length > TAIL_LIMIT) text = TRIM_MARKER + text.slice(text.length - TAIL_LIMIT)
  cache.text = text
  if (read.lossy === true) {
    // The retained window moved past us; resync rather than fabricate a gap.
    cache.offset = Number.isFinite(next) && next >= 0 ? next : 0
    return { dropped: true }
  }
  cache.offset = Number.isFinite(next) && next >= 0 ? next : cache.offset
  return { dropped: false }
}

/**
 * Fold one job's new output into its samples and re-derive `percent`/`etaMs`.
 *
 * The registry's own `progress` string, written through `JobHandle.updateProgress`,
 * is authoritative and preferred over anything parsed out of raw output. Only
 * when it is absent does the retained tail supply a percent.
 *
 * @param {object} record - the tracked job record.
 * @param {number} now - current wall clock.
 * @returns {void}
 */
function foldProgress(record, now) {
  const cache = record.cache
  const declared = typeof record.job.progress === 'string' ? record.job.progress.trim() : ''
  const fromProgress = declared.length > 0 ? parsePercent(declared) : undefined
  const percent = fromProgress ?? parsePercent(cache.text)

  if (percent === undefined) {
    record.percent = undefined
    record.etaMs = undefined
    record.samples = []
    return
  }

  record.percent = percent

  const samples = record.samples
  const last = samples[samples.length - 1]
  // A sample is only pushed when the percent actually moves: a repeated update
  // carries no rate information, and refreshing its timestamp would inflate the
  // measured rate of a job that has stalled. The window is bounded so an old
  // fast phase cannot dominate the recent pair.
  if (last === undefined) {
    samples.push({ at: now, percent })
  } else if (last.percent !== percent) {
    if (samples.length >= 8) samples.shift()
    samples.push({ at: now, percent })
  } else {
    last.at = now
  }

  record.etaMs = deriveEta(record)
}

/**
 * Derive a time-to-completion from the two most recent samples.
 *
 * The estimate is `remaining work / measured rate`, where the rate is percent
 * gained per millisecond across the last two samples. Anchoring only on the
 * recent pair — rather than on the job's total elapsed time — is what makes the
 * estimate respond to a *changed* rate: a job that has sped up reports a
 * shorter ETA than one that has stalled, even at the same percentage, and a job
 * that has stalled stops claiming the fast finish it once predicted.
 *
 * @param {object} record - the tracked job record.
 * @returns {number | undefined} clamped ETA in milliseconds.
 */
function deriveEta(record) {
  const samples = record.samples
  if (samples.length < 2) return undefined
  const first = samples[samples.length - 2]
  const last = samples[samples.length - 1]
  const deltaMs = last.at - first.at
  const gained = last.percent - first.percent
  if (deltaMs <= 0 || gained <= 0) return undefined
  const rate = gained / deltaMs
  if (!(rate > 0)) return undefined
  return clampEta((100 - last.percent) / rate)
}

/**
 * A promise whose settlement one caller can control later.
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
 * Apply the plugin to a host context.
 *
 * @param {any} ctx - the Cordis host context.
 * @param {{ statePath?: string, intervalMs?: number }} [config] - loader row config.
 * @returns {(() => void) | undefined} disposer, or undefined when inert.
 */
export function apply(ctx, config = {}) {
  // `inject` above already makes Cordis hold `apply` back until the registry is
  // mounted, so this read is legal under the context proxy. The guards only keep
  // a partial mount inert instead of fatal; every property they inspect belongs
  // to the service object, not to the proxy.
  const jobs = ctx.jobs
  if (jobs === null || jobs === undefined) return undefined
  if (typeof jobs.readAt !== 'function') return undefined
  if (jobs.events === null || typeof jobs.events !== 'object') return undefined
  if (typeof jobs.events.subscribe !== 'function') return undefined

  const intervalMs = Number.isFinite(config?.intervalMs) && Number(config.intervalMs) > 0
    ? Number(config.intervalMs)
    : DEFAULT_INTERVAL_MS
  const statePath = typeof config?.statePath === 'string' && config.statePath.length > 0
    ? config.statePath
    : join(resolveDshHome(), 'usage-widget', 'jobs.json')

  /** @type {Map<string, any>} */
  const tracked = new Map()
  /** @type {Set<string>} */
  const logged = new Set()
  /**
   * Serializes writes: each queued write owns its own gate and waits on the
   * gate of the write before it, so no two writers can be inside the critical
   * section at once. The head starts settled so the first write runs at once.
   * @type {{ promise: Promise<void>, resolve: () => void }}
   */
  let writeGate = createDeferral()
  writeGate.resolve()
  /** Monotonic discriminator so two concurrent writers can never share a temp name. */
  let serial = 0
  let disposed = false
  let lastWriteAt = 0
  /**
   * False until the first write has been dispatched. That first write is
   * unconditional, so the very first tick is a liveness beacon: a registry that
   * has reported nothing still produces `{"at":…,"jobs":[]}`, which answers
   * "is the bridge running?" without launching work. Every later write is
   * throttled to at most one per `intervalMs`.
   */
  let wrote = false

  /**
   * Log a failure once per distinct key, so a wedged registry or an
   * unwritable directory cannot flood the host log.
   * @param {string} key - dedupe key.
   * @param {unknown} error - the failure.
   * @returns {void}
   */
  const complain = (key, error) => {
    if (logged.has(key)) return
    logged.add(key)
    try {
      // Never `ctx.logger`: logging is not an injected service here, and the
      // context proxy throws on the GET itself, before any `?.` could help.
      console.error(`usage-bridge: ${key}: ${String(error)}`)
    } catch {
      /* Logging must never escalate a contained failure. */
    }
  }

  /**
   * Run a contained operation, reporting the first failure of its kind.
   * @param {string} key - dedupe key.
   * @param {() => void} operation - the contained work.
   * @returns {void}
   */
  const guard = (key, operation) => {
    try {
      operation()
    } catch (error) {
      complain(key, error)
    }
  }

  /**
   * Project the tracked records into the file body.
   * @param {number} now - current wall clock.
   * @returns {object} the JSON payload.
   */
  const snapshot = (now) => {
    const jobs = []
    for (const record of tracked.values()) {
      const job = record.job
      jobs.push({
        id: String(job.id),
        kind: typeof job.kind === 'string' ? job.kind : 'unknown',
        label: typeof job.label === 'string' ? job.label : '',
        owner: job.owner === undefined ? null : String(job.owner),
        status: typeof job.status === 'string' ? job.status : 'running',
        progress: typeof job.progress === 'string' && job.progress.length > 0 ? job.progress : null,
        detail: typeof job.detail === 'string' && job.detail.length > 0 ? job.detail : null,
        percent: record.percent === undefined ? null : Math.round(record.percent * 100) / 100,
        etaMs: record.etaMs === undefined ? null : record.etaMs,
        startedAt: Number.isFinite(job.startedAt) ? job.startedAt : now,
        finishedAt: Number.isFinite(job.finishedAt) ? job.finishedAt : null,
        lastLine: record.lastLine === undefined ? null : record.lastLine,
      })
    }
    return { at: now, jobs }
  }

  /**
   * Drop settled jobs whose display tail has expired.
   * @param {number} now - current wall clock.
   * @returns {void}
   */
  const prune = (now) => {
    for (const [id, record] of tracked) {
      if (record.settledAt !== undefined && now - record.settledAt >= SETTLED_TAIL_MS) tracked.delete(id)
    }
  }

  /**
   * Write the snapshot atomically: temp file in the same directory, then a
   * rename over the target, so the widget never observes a half-written file.
   *
   * Writes are serialized through {@link writeGate}. Two writers racing on one
   * rename pair can finish in the opposite order, which would leave the *older*
   * state on disk — and because the snapshot is projected inside the critical
   * section, serializing also guarantees the payload is current at the moment
   * it is written rather than when the write was requested.
   * @param {number} now - the instant this write request describes.
   * @param {boolean} forced - true when an event scheduled this write, which
   * bypasses the per-interval throttle.
   * @param {() => void} release - resolves *this* write's own gate. It is bound
   * at queue time on purpose: by the time this body runs, the gate field
   * already refers to the next writer's promise.
   * @returns {Promise<void>} resolves whether or not the write succeeded.
   */
  const writeNow = (now, forced, release) => {
    const attempt = async () => {
      // Both early exits sit inside the `try` on purpose: they still have to
      // release this write's gate, or the *next* writer would wait forever on a
      // promise nothing resolves and the mirror would stop updating for good.
      try {
        if (disposed) return
        if (forced !== true && wrote && now - lastWriteAt < intervalMs) return
        prune(now)
        lastWriteAt = now
        wrote = true
        const body = `${JSON.stringify(snapshot(now))}\n`
        await mkdir(dirname(statePath), { recursive: true })
        serial += 1
        const temporary = `${statePath}.${process.pid}.${serial}.tmp`
        await writeFile(temporary, body, 'utf8')
        await rename(temporary, statePath)
        logged.delete('write')
      } catch (error) {
        complain('write', error)
      } finally {
        release()
      }
    }
    return attempt()
  }

  /**
   * Queue a write behind any write already running.
   * @param {number} now - the instant to describe.
   * @param {boolean} forced - bypass the throttle when true.
   * @returns {void}
   */
  const write = (now, forced) => {
    if (disposed) return
    const previous = writeGate.promise
    const gate = createDeferral()
    writeGate = gate
    void previous
      .then(() => writeNow(now, forced, gate.resolve))
      .catch((error) => {
        // writeNow contains its own failures; this is a belt-and-braces guard so
        // a surprise can neither wedge the queue nor surface as a host rejection.
        gate.resolve()
        complain('write', error)
      })
  }

  /**
   * Read every live job's ring once. No job id is ever passed as `caller`, so
   * the read is the registry's own observer read and never a model read.
   * @returns {void}
   */
  const pump = () => {
    const now = Date.now()
    for (const record of tracked.values()) {
      if (record.settledAt !== undefined) continue
      guard(`read:${record.job.id}`, () => {
        const read = jobs.readAt(record.job.id, record.cache.offset)
        const folded = foldRead(record.cache, read)
        if (folded.dropped) complain(`lossy:${record.job.id}`, `ring read at ${record.cache.offset} was lossy`)
        record.lastLine = parseLastLine(record.cache.text)
        foldProgress(record, now)
      })
    }
    write(now, false)
  }

  /**
   * Take ownership of one registry event. Every branch is contained: a broken
   * projection from the registry must not become a broken host.
   * @param {any} event - a JobEvent.
   * @returns {void}
   */
  const onEvent = (event) => {
    if (disposed) return
    try {
      if (event === null || typeof event !== 'object') return
      if (event.type === 'output') {
        // Output notifications are covered by the interval pump; reading on
        // every append would read the ring far more often than anyone wants a
        // file on disk.
        return
      }
      const job = event.job
      if (job === null || typeof job !== 'object' || job.id === undefined) return
      const id = String(job.id)

      if (event.type === 'removed') {
        tracked.delete(id)
        write(Date.now(), true)
        return
      }

      let record = tracked.get(id)
      if (record === undefined) {
        record = {
          job: {},
          cache: { offset: 0, text: '' },
          samples: [],
          settledAt: undefined,
          percent: undefined,
          etaMs: undefined,
          lastLine: undefined,
        }
        tracked.set(id, record)
      }
      // Always keep the freshest projection; events are the only place some
      // fields (status, detail, finishedAt) are guaranteed to arrive.
      record.job = { ...job }

      if (event.type === 'registered') {
        // A fresh registration starts at the retained head. Ids are never
        // reused, so a first read from 0 is always correct.
        record.cache = { offset: 0, text: '' }
        record.samples = []
        record.percent = undefined
        record.etaMs = undefined
        record.lastLine = undefined
      }

      if (event.type === 'settled') {
        record.settledAt = Date.now()
        record.etaMs = undefined
        record.job.finishedAt = Number.isFinite(job.finishedAt) ? job.finishedAt : record.settledAt
      }

      write(Date.now(), true)
    } catch (error) {
      complain('event', error)
    }
  }

  let unsubscribe
  try {
    unsubscribe = jobs.events.subscribe({ owners: 'all' }, onEvent)
  } catch (error) {
    // Being unable to observe is not a reason to disturb the host.
    complain('subscribe', error)
    return undefined
  }

  // The process-global timer, not `ctx.setInterval`: the `timer` service exposes
  // `ctx.interval`, and reading any undeclared name off the context proxy throws
  // on the GET itself. The handle is released by the effect below, so the tick
  // lives exactly as long as the plugin does.
  const timer = setInterval(() => guard('tick', pump), intervalMs)

  /** Stop observing. Idempotent: both the effect and the returned disposer call it. */
  const teardown = () => {
    disposed = true
    try {
      clearInterval(timer)
    } catch {
      /* Disposal is best effort. */
    }
    try {
      unsubscribe?.()
    } catch {
      /* Disposal is best effort. */
    }
  }

  ctx.effect(() => teardown, 'usage-bridge: job mirror')

  // No write here: the first *tick* is the beacon, and it is unconditional (see
  // `wrote`), so an idle registry still leaves `{"at":…,"jobs":[]}` on disk
  // within one interval of load.
  return teardown
}
