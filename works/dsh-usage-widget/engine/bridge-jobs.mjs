/**
 * Read the host bridge's mirror of DSH's background-job registry.
 *
 * A running command's output reaches the session log only when it settles, so the
 * log-derived job rows in `activity.mjs` can say *that* something runs and what
 * its command is, but never how far along it is. The host-side bridge
 * (`dsh-usage-bridge`) subscribes to the real registry, whose output ring is
 * readable live, and mirrors it to one small JSON file:
 *
 *   $DSH_HOME/usage-widget/jobs.json
 *   {"at":…,"jobs":[{"id","kind","label","owner","status","progress",
 *                    "detail","percent","etaMs","startedAt","finishedAt","lastLine"}]}
 *
 * While that file is fresh it is the better source and wins outright — including
 * when it reports nothing, which genuinely means nothing is running. When it is
 * missing, stale or unreadable the caller keeps the log-derived rows.
 *
 * @module dsh-usage-dashboard-engine/bridge-jobs
 */

import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'

import { resolveDshHome } from './session-store.mjs'

/** How long the bridge file counts as current, in milliseconds. */
export const DEFAULT_BRIDGE_STALE_MS = 10_000

/** Longest command line carried into the snapshot, matching the log path. */
export const BRIDGE_COMMAND_MAX = 120

/**
 * The bridge's default state file, which is also what the plugin writes when its
 * `statePath` config is left empty.
 *
 * @param {string} [home] - Harness home; resolved from the environment by default.
 * @returns {string} absolute path of the bridge state file.
 */
export function defaultBridgePath(home = resolveDshHome()) {
  return join(home, 'usage-widget', 'jobs.json')
}

/**
 * Collapse any text to one trimmed, length-capped line.
 *
 * @param {unknown} value - the raw text.
 * @param {number} [max] - maximum length.
 * @returns {string} the rendered line, or an empty string.
 */
export function oneLine(value, max = BRIDGE_COMMAND_MAX) {
  if (typeof value !== 'string') return ''
  const text = value.replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

/**
 * Map one bridge row onto the job shape the widget already consumes.
 *
 * @param {any} row - a bridge job record.
 * @param {number} now - the observation time.
 * @returns {any} the snapshot job row.
 */
export function mapBridgeJob(row, now) {
  const startedAt = typeof row?.startedAt === 'number' && Number.isFinite(row.startedAt) ? row.startedAt : now
  const finishedAt = typeof row?.finishedAt === 'number' && Number.isFinite(row.finishedAt) ? row.finishedAt : null
  const running = row?.status === 'running' || row?.status === 'stopping'
  const end = running || finishedAt === null ? now : finishedAt
  const elapsedMs = Math.max(0, Math.round(end - startedAt))

  const percent =
    typeof row?.percent === 'number' && Number.isFinite(row.percent) && row.percent >= 0 && row.percent <= 100
      ? row.percent
      : null
  const etaMs =
    typeof row?.etaMs === 'number' && Number.isFinite(row.etaMs) && row.etaMs > 0 ? row.etaMs : null

  // Percent and note are mutually exclusive: a note only fills the gap when no
  // number is known, so the widget never prints both.
  const progress = percent === null ? null : { percent, etaMs, source: 'bridge' }
  let progressNote = null
  if (progress === null) {
    const detail = oneLine(row?.progress)
    const tail = oneLine(row?.lastLine)
    progressNote = detail.length > 0 ? detail : tail.length > 0 ? tail : '无进度输出'
  }

  const command = oneLine(row?.label)
  return {
    id: typeof row?.id === 'string' ? row.id : '',
    session: typeof row?.owner === 'string' && row.owner.length > 0 ? row.owner : undefined,
    program: typeof row?.kind === 'string' && row.kind.length > 0 ? row.kind : 'job',
    command,
    startedAt,
    elapsedMs,
    progress,
    progressNote,
  }
}

/**
 * Read the bridge file and project the jobs that are running now.
 *
 * Never throws and never blocks for long: one `stat` plus one small read, and any
 * failure reports `fresh: false` so the caller falls back to the logs.
 *
 * @param {{ path?: string, staleMs?: number, now?: number, home?: string }} [options]
 * @returns {Promise<{ fresh: boolean, jobs: any[], path: string, reason?: string }>}
 */
export async function readBridgeJobs(options = {}) {
  const now = typeof options.now === 'number' ? options.now : Date.now()
  const staleMs =
    typeof options.staleMs === 'number' && Number.isFinite(options.staleMs) && options.staleMs > 0
      ? options.staleMs
      : DEFAULT_BRIDGE_STALE_MS
  const path =
    typeof options.path === 'string' && options.path.length > 0
      ? options.path
      : defaultBridgePath(options.home)

  try {
    const info = await stat(path)
    if (now - info.mtimeMs > staleMs) return { fresh: false, jobs: [], path, reason: 'stale' }
    const parsed = JSON.parse(await readFile(path, 'utf8'))
    const rows = Array.isArray(parsed?.jobs) ? parsed.jobs : []
    const jobs = rows
      .filter((row) => row !== null && typeof row === 'object' && (row.status === 'running' || row.status === 'stopping'))
      .map((row) => mapBridgeJob(row, now))
    return { fresh: true, jobs, path }
  } catch (error) {
    const reason = error !== null && typeof error === 'object' && error.code === 'ENOENT' ? 'missing' : 'unreadable'
    return { fresh: false, jobs: [], path, reason }
  }
}
