/**
 * Token-usage and spend accounting for the live console.
 *
 * The harness records each model call's provider-reported token bucket in the
 * durable session logs; money is never recorded. This module folds every log
 * (v3 and v4), prices each call at its own timestamp against DeepSeek's
 * peak/off-peak rate card, and returns the same compact summary the page renders.
 *
 * It reuses the fold/pricing implementation proven by `dsh-usage-dashboard`
 * (copied under `./usage/` so this plugin stays self-contained). The sweep is
 * expensive (roughly a second of decoding per open log), so the caller owns
 * memoization: `collectUsage` is only invoked on activation and on the page's
 * refresh cadence, never per request.
 *
 * @module dsh-live-console/usage-stats
 */

import { readAllSessions } from './usage/session-store.mjs'
import { buildDashboard } from './usage/usage.mjs'

/** Route used when a session log names no model. */
const DEFAULT_MODEL = 'deepseek-flash'

/**
 * Fold every durable session log under `home` and build the dashboard summary.
 *
 * @param {{ home?: string, defaultModel?: string, now?: number }} [options]
 *   `home` defaults to the persisted Harness home inside session-store.
 * @returns {Promise<any>} the dashboard payload plus a `source` block describing
 *   the sweep (artifact count, bytes, duration, failures).
 */
export async function collectUsage(options = {}) {
  const now = typeof options.now === 'number' ? options.now : Date.now()
  const sweep = await readAllSessions({
    home: options.home,
    defaultModel: options.defaultModel ?? DEFAULT_MODEL,
  })
  const dashboard = buildDashboard(sweep.sessions, { now })
  return {
    ...dashboard,
    source: {
      artifacts: sweep.artifacts,
      bytes: sweep.bytes,
      elapsedMs: sweep.elapsedMs,
      failures: sweep.failures,
    },
  }
}
