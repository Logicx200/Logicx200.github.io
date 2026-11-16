/**
 * Host half of the DSH usage dashboard.
 *
 * Two jobs, both deliberately small. It **aggregates**: every request sweeps the
 * durable session artifacts, folds their provider-reported usage, and prices the
 * result, so the browser never needs the logs and the numbers are the same for
 * any browser session. And it **serves**: one exact authenticated Fetch route on
 * the shared `/api` channel that the browser half reads.
 *
 * The sweep is memoized behind a short TTL and single-flighted, because the tab
 * body polls and a full sweep costs roughly a second of decoding for every
 * reader otherwise.
 *
 * @module dsh-usage-dashboard
 */

import { buildDashboard } from './usage.mjs'
import { readAllSessions } from './session-store.mjs'

/** Cordis plugin identity. */
export const name = 'usage-dashboard'

/** Services the route needs; without the connection there is nothing to serve. */
export const inject = ['connection']

/** Exact route path; absolute below the shared `/api` channel. */
export const ROUTE_PATH = '/api/usage-dashboard/stats'

/** How long one sweep's result stays fresh, in milliseconds. */
const DEFAULT_TTL_MS = 15_000

/** Route a session log names no model for. */
const DEFAULT_MODEL = 'deepseek-flash'

/**
 * Resolve the route a session log without a recorded model should be priced as.
 * The adapter's advisory catalog is preferred when it is mounted, so a
 * deployment that renamed its default is not silently mislabelled.
 *
 * @param {import('@deepseek-ai/cordis').Context} ctx - the host context.
 * @returns {Promise<string>} the fallback model id.
 */
async function resolveDefaultModel(ctx) {
  const llm = ctx.get('llm')
  if (llm === undefined) return DEFAULT_MODEL
  try {
    const models = await llm.listModels('deepseek-official')
    const first = models?.[0]?.id
    return typeof first === 'string' && first.length > 0 ? first : DEFAULT_MODEL
  } catch {
    return DEFAULT_MODEL
  }
}

/**
 * One memoized, single-flighted view of the accounting.
 * @param {() => Promise<any>} produce - the expensive sweep.
 * @param {number} ttlMs - freshness window.
 * @returns {() => Promise<any>} a reader that reuses a fresh snapshot.
 */
function createCache(produce, ttlMs) {
  /** @type {{ at: number, value: any } | undefined} */
  let fresh
  /** @type {Promise<any> | undefined} */
  let inFlight
  return async () => {
    const now = Date.now()
    if (fresh !== undefined && now - fresh.at < ttlMs) return fresh.value
    if (inFlight !== undefined) return inFlight
    inFlight = (async () => {
      try {
        const value = await produce()
        fresh = { at: Date.now(), value }
        return value
      } finally {
        inFlight = undefined
      }
    })()
    return inFlight
  }
}

/**
 * JSON response helper with the no-store policy the live numbers need.
 * @param {unknown} body - JSON-serializable payload.
 * @param {number} [status] - HTTP status.
 * @returns {Response} the response to return from the route.
 */
function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  })
}

/**
 * Host plugin body: register the authenticated stats route.
 *
 * @param {any} ctx - the host context.
 * @param {{ ttlMs?: number, home?: string, defaultModel?: string }} [config] - optional row config.
 */
export function apply(ctx, config = {}) {
  const ttlMs = Number.isFinite(config.ttlMs) ? Number(config.ttlMs) : DEFAULT_TTL_MS
  const home = typeof config.home === 'string' && config.home.length > 0 ? config.home : undefined

  /** @type {string | undefined} */
  let defaultModel
  const load = async () => {
    if (defaultModel === undefined) defaultModel = await resolveDefaultModel(ctx)
    const sweep = await readAllSessions({ home, defaultModel })
    return {
      ...buildDashboard(sweep.sessions, { now: Date.now() }),
      source: {
        artifacts: sweep.artifacts,
        failures: sweep.failures,
        bytes: sweep.bytes,
        elapsedMs: sweep.elapsedMs,
        ttlMs,
        home: home ?? null,
      },
    }
  }
  const read = createCache(load, ttlMs)

  const dispose = ctx.connection.fetch.register({
    path: ROUTE_PATH,
    methods: ['GET', 'HEAD'],
    requestBody: 'buffered',
    fetch: async (request) => {
      const url = new URL(request.url)
      if (url.searchParams.get('refresh') === '1') {
        // A manual refresh bypasses the TTL by producing a fresh snapshot.
        const value = await load()
        return json(value)
      }
      try {
        const value = await read()
        if (request.method === 'HEAD') return new Response(null, { status: 200 })
        return json(value)
      } catch (error) {
        ctx.logger?.warn?.('usage-dashboard: sweep failed: %s', String(error))
        return json({ error: String(error) }, 500)
      }
    },
  })

  ctx.effect(() => () => void dispose(), 'usage-dashboard: /api route')
}
