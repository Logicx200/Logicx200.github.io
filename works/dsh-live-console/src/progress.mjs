/**
 * Progress engine for the live console.
 *
 * A program that reports nothing cannot yield a true percentage, so progress is
 * derived in three honest tiers and every job always has a bar:
 *
 *   1. `explicit` — the program (or its registry `progress` line) said so:
 *      `47.5%`, `step 120/500`, `[progress 3/10]`, tqdm-style ` 42%|`.
 *   2. `estimate` — the same command has run before. The median duration and
 *      median output size of earlier runs bound the current one: percent is
 *      `elapsed / medianDuration` or `bytes / medianBytes`, capped below 100 and
 *      clearly labelled as an estimate.
 *   3. `activity` — nothing numeric is known. The page animates an indeterminate
 *      bar plus elapsed time, output rate, and last-output age, and says so.
 *
 * Retry semantics: explicit progress never moves backwards within one job, so a
 * program that prints "5%" twice cannot make the bar jump back.
 *
 * @module dsh-live-console/progress
 */

/** Never claim completion from an estimate; only settlement does that. */
export const ESTIMATE_CAP = 95;

/** A ratio numerator/denominator above this is not real progress. */
const MAX_TOTAL = 1e12;

/** How many prior runs one command signature keeps for its medians. */
const HISTORY_SAMPLES = 20;

/** How many command signatures the persisted history keeps. */
const HISTORY_SIGNATURES = 600;

/** How long an unused signature survives before it is pruned, in ms. */
const HISTORY_TTL_MS = 30 * 24 * 60 * 60 * 1_000;

/** ANSI CSI/OSC escape sequences and carriage-return noise from progress bars. */
const ANSI_RE = /[\u001B\u009B][[\]()#;?]*(?:(?:(?:[a-zA-Z\d]*(?:;[-a-zA-Z\d/#&.:=?%@~_]+)*)?\u0007)|(?:(?:\d{1,4}(?:[;:]\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))/g;

/**
 * Strip terminal control sequences from one output chunk.
 * @param {string} text - raw chunk text.
 * @returns {string} plain text.
 */
export function stripAnsi(text) {
  if (typeof text !== 'string' || text.length === 0) return '';
  return text.replace(ANSI_RE, '').replace(/\r(?!\n)/g, '\n');
}

/**
 * Median of an unsorted numeric array.
 * @param {number[]} values - finite numbers.
 * @returns {number | undefined} the median, or undefined for an empty list.
 */
export function median(values) {
  if (!Array.isArray(values) || values.length === 0) return undefined
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle]
}

/**
 * Whether a `value/total` pair can be a real step ratio.
 * @param {number} value - numerator.
 * @param {number} total - denominator.
 * @returns {boolean} true when the pair is worth showing.
 */
function usableRatio(value, total) {
  if (!Number.isFinite(value) || !Number.isFinite(total)) return false
  if (total <= 0 || total > MAX_TOTAL) return false
  if (value < 0 || value > total) return false
  return true
}

/**
 * Extract explicit progress from a single line.
 *
 * Priority inside the line: a percentage *with a unit* beats a bare ratio, and
 * `[progress ...]` beats everything else. The last match on the line wins, because
 * a progress line normally reads left to right and the freshest figure is rightmost.
 *
 * @param {string} line - one line of retained output.
 * @returns {{ percent: number, kind: 'percent' | 'ratio', evidence: string } | undefined}
 */
export function progressFromLine(line) {
  if (typeof line !== 'string' || line.length === 0) return undefined
  const trimmed = line.trim()
  if (trimmed.length === 0) return undefined

  // `[progress 3/10]`, `progress: 42%`, `PROGRESS step 3 of 10`
  const tagged = /\[?\bprogress\b\s*[:=]?\s*(?:step\s+)?(\d+(?:\.\d+)?)\s*(%|\/|\||\s+of\s+)\s*(\d+(?:\.\d+)?)?/i.exec(trimmed)
  if (tagged !== null) {
    const first = Number(tagged[1])
    if (tagged[2] === '%') {
      if (Number.isFinite(first) && first >= 0 && first <= 100) {
        return { percent: first, kind: 'percent', evidence: trimmed.slice(0, 160) }
      }
    } else if (tagged[3] !== undefined) {
      const total = Number(tagged[3])
      if (usableRatio(first, total)) {
        return { percent: (first / total) * 100, kind: 'ratio', evidence: trimmed.slice(0, 160) }
      }
    }
  }

  // Percentages with a unit. Take the last plausible one on the line.
  const percents = [...trimmed.matchAll(/(\d+(?:\.\d+)?)\s*%/g)]
  for (let index = percents.length - 1; index >= 0; index -= 1) {
    const value = Number(percents[index][1])
    if (Number.isFinite(value) && value >= 0 && value <= 100) {
      return { percent: value, kind: 'percent', evidence: trimmed.slice(0, 160) }
    }
  }

  // Word-anchored ratios first (`step 120/500`, `phase 2 of 7`), then a bare one.
  const anchored = /(?:step|phase|part|frame|batch|task|progress)\s*[:=]?\s*(\d+)\s*(?:\/|\||\s+of\s+)\s*(\d+)/i.exec(trimmed)
  if (anchored !== null) {
    const value = Number(anchored[1])
    const total = Number(anchored[2])
    if (usableRatio(value, total)) {
      return { percent: (value / total) * 100, kind: 'ratio', evidence: trimmed.slice(0, 160) }
    }
  }
  const bare = /(?:\[|\()?\s*(\d+)\s*(?:\/|\|)\s*(\d+)\s*(?:\]|\))?/.exec(trimmed)
  if (bare !== null) {
    const value = Number(bare[1])
    const total = Number(bare[2])
    if (usableRatio(value, total)) {
      return { percent: (value / total) * 100, kind: 'ratio', evidence: trimmed.slice(0, 160) }
    }
  }
  return undefined
}

/**
 * Find the explicit progress carried by the *last* line that has one.
 * @param {string} text - retained output tail.
 * @returns {{ percent: number, kind: 'percent' | 'ratio', evidence: string } | undefined}
 */
export function progressFromText(text) {
  if (typeof text !== 'string' || text.length === 0) return undefined
  const lines = text.split('\n')
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const found = progressFromLine(lines[index])
    if (found !== undefined) return found
  }
  return undefined
}

/**
 * Derive a time-to-completion from the two most recent explicit samples. Anchoring
 * on the recent pair (rather than total elapsed) lets the ETA react to a changed
 * rate. Mirrors the bridge's proven heuristic.
 *
 * @param {{ at: number, percent: number }[]} samples - explicit samples, oldest first.
 * @returns {number | undefined} clamped milliseconds, or undefined.
 */
export function deriveEta(samples) {
  if (!Array.isArray(samples) || samples.length < 2) return undefined
  const first = samples[samples.length - 2]
  const last = samples[samples.length - 1]
  const deltaMs = last.at - first.at
  const gained = last.percent - first.percent
  if (!(deltaMs > 0) || !(gained > 0)) return undefined
  const eta = ((100 - last.percent) / (gained / deltaMs))
  if (!Number.isFinite(eta) || eta <= 0) return undefined
  return Math.round(Math.min(7 * 24 * 60 * 60 * 1_000, Math.max(1_000, eta)))
}

/**
 * Stable signature for one command. The label is the full command line, so a
 * repeated build/test/simulation command matches itself across runs.
 * @param {string} kind - job kind, e.g. `bash`.
 * @param {string} label - the job's command label.
 * @returns {string} history key.
 */
export function signatureOf(kind, label) {
  const clean = typeof label === 'string' ? label.replace(/\s+/g, ' ').trim().slice(0, 400) : ''
  return `${typeof kind === 'string' ? kind : 'job'}\u0000${clean}`
}

/**
 * One recorded completed run, used to estimate later runs of the same command.
 * @typedef {{ ms: number, bytes: number, lines: number }} HistorySample
 */

/**
 * Bounded per-signature history with on-disk persistence.
 */
export class ProgressHistory {
  /**
   * @param {object} [options] - store options.
   * @param {boolean} [options.enabled] - false keeps everything in memory.
   * @param {string} [options.path] - absolute JSON path.
   * @param {number} [options.now] - injectable clock for tests.
   */
  constructor(options = {}) {
    this.enabled = options.enabled !== false
    this.path = typeof options.path === 'string' && options.path.length > 0 ? options.path : undefined
    this.now = typeof options.now === 'function' ? options.now : Date.now
    /** @type {Map<string, { samples: HistorySample[], lastAt: number }>} */
    this.entries = new Map()
    this.dirty = false
  }

  /**
   * Replace the in-memory table from a parsed JSON document.
   * @param {unknown} parsed - previously persisted document.
   * @returns {void}
   */
  load(parsed) {
    this.entries.clear()
    const table = parsed !== null && typeof parsed === 'object' && parsed.entries !== null && typeof parsed.entries === 'object'
      ? parsed.entries
      : {}
    const now = this.now()
    for (const [key, value] of Object.entries(table)) {
      if (value === null || typeof value !== 'object') continue
      const samples = Array.isArray(value.samples) ? value.samples : []
      const cleaned = samples
        .filter((sample) => sample !== null && typeof sample === 'object' && Number.isFinite(sample.ms) && sample.ms > 0)
        .slice(-HISTORY_SAMPLES)
        .map((sample) => ({
          ms: sample.ms,
          bytes: Number.isFinite(sample.bytes) && sample.bytes >= 0 ? sample.bytes : 0,
          lines: Number.isFinite(sample.lines) && sample.lines >= 0 ? sample.lines : 0,
        }))
      if (cleaned.length === 0) continue
      const lastAt = Number.isFinite(value.lastAt) ? value.lastAt : now
      if (now - lastAt > HISTORY_TTL_MS) continue
      this.entries.set(key, { samples: cleaned, lastAt })
    }
  }

  /**
   * Record one completed run.
   * @param {string} signature - `signatureOf` result.
   * @param {{ ms: number, bytes: number, lines: number }} sample - this run.
   * @returns {void}
   */
  record(signature, sample) {
    if (!this.enabled) return
    if (!(sample.ms > 0)) return
    let entry = this.entries.get(signature)
    if (entry === undefined) entry = { samples: [], lastAt: this.now() }
    entry.samples.push({ ms: sample.ms, bytes: sample.bytes, lines: sample.lines })
    if (entry.samples.length > HISTORY_SAMPLES) entry.samples = entry.samples.slice(-HISTORY_SAMPLES)
    entry.lastAt = this.now()
    this.entries.set(signature, entry)
    this.dirty = true
    this.prune()
  }

  /**
   * Drop expired signatures and cap the table size.
   * @returns {void}
   */
  prune() {
    if (this.entries.size <= HISTORY_SIGNATURES) {
      const now = this.now()
      for (const [key, entry] of this.entries) {
        if (now - entry.lastAt > HISTORY_TTL_MS) {
          this.entries.delete(key)
          this.dirty = true
        }
      }
      return
    }
    const keep = [...this.entries.entries()].sort((left, right) => right[1].lastAt - left[1].lastAt).slice(0, HISTORY_SIGNATURES)
    this.entries = new Map(keep)
    this.dirty = true
  }

  /**
   * Estimate progress/ETA for one running job from its command's history.
   * @param {string} signature - `signatureOf` result.
   * @param {{ elapsedMs: number, bytes: number }} current - live measurement.
   * @returns {{ percent?: number, etaMs?: number, source?: 'estimate-time' | 'estimate-output' } | undefined}
   */
  estimate(signature, current) {
    if (!this.enabled) return undefined
    const entry = this.entries.get(signature)
    if (entry === undefined || entry.samples.length === 0) return undefined

    const medianMs = median(entry.samples.map((sample) => sample.ms))
    const byteSamples = entry.samples.map((sample) => sample.bytes).filter((bytes) => bytes >= 512)
    const medianBytes = median(byteSamples)

    let timePercent
    let timeEta
    if (medianMs !== undefined && medianMs >= 1_000 && current.elapsedMs > 0) {
      timePercent = Math.min(ESTIMATE_CAP, (current.elapsedMs / medianMs) * 100)
      timeEta = Math.max(1_000, Math.round(medianMs - current.elapsedMs))
    }
    let outputPercent
    if (medianBytes !== undefined && current.bytes >= 32) {
      outputPercent = Math.min(ESTIMATE_CAP, (current.bytes / medianBytes) * 100)
    }

    if (outputPercent === undefined && timePercent === undefined) return undefined
    if (outputPercent !== undefined && (timePercent === undefined || outputPercent >= timePercent)) {
      return { percent: outputPercent, etaMs: timeEta, source: 'estimate-output' }
    }
    return { percent: timePercent, etaMs: timeEta, source: 'estimate-time' }
  }
}
