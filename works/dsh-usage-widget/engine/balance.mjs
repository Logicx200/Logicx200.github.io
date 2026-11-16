/**
 * Live DeepSeek account balance for the usage widget.
 *
 * Spend is *derived* from the durable session logs, but the remaining prepaid
 * credit exists only at DeepSeek, so this module reads the account endpoint and
 * nothing else. The widget shows the two side by side: computed cost tells the
 * user what the history burned, the balance tells them what is left.
 *
 * The API key lives in `$DSH_HOME/.credentials.yaml` as a `refs:` entry. It is
 * read here, sent as the bearer token, and never logged: every failure path
 * reports the *reason* (missing ref, HTTP status, timeout, malformed body) and
 * never the secret, and the response body is never echoed verbatim.
 *
 * `readBalance()` never throws. It caches its last outcome — a success for the
 * caller's TTL, a failure for a much shorter window so a transient network fault
 * is not re-attempted on every poll — and returns the cached copy while fresh.
 *
 * @module dsh-usage-widget/balance
 */

import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

import { resolveDshHome } from './session-store.mjs'

/** The account-balance endpoint. */
export const BALANCE_URL = 'https://api.deepseek.com/user/balance'

/** Credentials file name below the Harness home. */
export const CREDENTIALS_FILE_NAME = '.credentials.yaml'

/** Name of the `refs:` entry holding the API key. */
export const API_KEY_REF = 'DEEPSEEK_API_KEY'

/**
 * The `refs:` line matcher, applied to the raw credentials text. The key is a
 * single whitespace-free token, so the credential never spans lines and the
 * capture cannot swallow neighbouring YAML.
 */
export const API_KEY_PATTERN = /^\s*DEEPSEEK_API_KEY\s*:\s*(\S+)\s*$/m

/** How long a successful reading stays fresh, in milliseconds. */
export const DEFAULT_TTL_MS = 60_000

/**
 * How long a *failed* reading stays fresh. Deliberately short: long enough that
 * a widget polling every couple of seconds does not hammer a failing endpoint,
 * short enough that the next success is not hidden behind a stale error.
 */
export const DEFAULT_RETRY_MS = 5_000

/** Per-request timeout, in milliseconds. */
export const REQUEST_TIMEOUT_MS = 10_000

/**
 * @typedef {{ ok: true, currency: string, total: string, granted: string, toppedUp: string, fetchedAt: number }
 *   | { ok: false, error: string }} BalanceResult
 */

/** @type {{ at: number, value: BalanceResult } | undefined} */
let cache

/** Discard the memoized reading; the next call hits the network. */
export function clearBalanceCache() {
  cache = undefined
}

/**
 * Read the DeepSeek API key out of `$DSH_HOME/.credentials.yaml`.
 *
 * @param {string} [home] - Harness home; resolved from the environment by default.
 * @returns {Promise<string>} the bearer token.
 * @throws {Error} when the file is unreadable or carries no key ref. The thrown
 *   message names the file, never its contents.
 */
export async function readApiKey(home = resolveDshHome()) {
  const path = join(home, CREDENTIALS_FILE_NAME)
  const text = await readFile(path, 'utf8')
  const match = API_KEY_PATTERN.exec(text)
  if (match === null) {
    throw new Error(`no ${API_KEY_REF} ref in ${path}`)
  }
  return match[1]
}

/** A message safe to expose: never carries credentials. */
function messageOf(error) {
  if (error instanceof Error) {
    if (error.name === 'AbortError' || error.name === 'TimeoutError') {
      return `balance request timed out after ${REQUEST_TIMEOUT_MS}ms`
    }
    return error.message
  }
  return String(error)
}

/** One money field, always a string, as the API reports it. */
function money(value) {
  if (typeof value === 'string' && value.length > 0) return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return '0.00'
}

/**
 * Project a raw `/user/balance` body onto the widget's balance shape.
 *
 * The CNY entry is preferred because that is the account's own currency and the
 * widget's CNY figures are derived from it; any other single-currency account
 * falls back to the first entry so the card still shows a real number.
 *
 * @param {any} body - the parsed JSON response.
 * @param {number} fetchedAt - when the response was received.
 * @returns {BalanceResult} the projected result.
 */
export function projectBalance(body, fetchedAt) {
  if (body === null || typeof body !== 'object') {
    return { ok: false, error: 'balance response was not a JSON object' }
  }
  const infos = Array.isArray(body.balance_infos) ? body.balance_infos : []
  if (infos.length === 0) {
    return { ok: false, error: 'balance response carried no balance_infos' }
  }
  const entry =
    infos.find(
      (info) =>
        info !== null &&
        typeof info === 'object' &&
        typeof info.currency === 'string' &&
        info.currency.toUpperCase() === 'CNY',
    ) ?? infos[0]
  if (entry === null || typeof entry !== 'object') {
    return { ok: false, error: 'balance response carried an unusable balance_infos entry' }
  }
  return {
    ok: true,
    currency: typeof entry.currency === 'string' ? entry.currency : '',
    total: money(entry.total_balance),
    granted: money(entry.granted_balance),
    toppedUp: money(entry.topped_up_balance),
    fetchedAt,
  }
}

/**
 * Perform one network read, without touching the cache.
 *
 * @param {{ home?: string, fetch?: typeof fetch, now?: number, timeoutMs?: number }} [options]
 * @returns {Promise<BalanceResult>} the outcome; failures are values, not throws.
 */
export async function fetchBalance(options = {}) {
  const fetchedAt = options.now ?? Date.now()
  const request = options.fetch ?? globalThis.fetch
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS
  if (typeof request !== 'function') {
    return { ok: false, error: 'no fetch implementation available' }
  }

  let key
  try {
    key = await readApiKey(options.home)
  } catch (error) {
    return { ok: false, error: `credentials: ${messageOf(error)}` }
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await request(BALANCE_URL, {
      method: 'GET',
      headers: {
        authorization: `Bearer ${key}`,
        accept: 'application/json',
      },
      signal: controller.signal,
    })
    if (!response.ok) {
      return { ok: false, error: `balance request failed: HTTP ${response.status}` }
    }
    let body
    try {
      body = await response.json()
    } catch {
      return { ok: false, error: 'balance response was not valid JSON' }
    }
    return projectBalance(body, fetchedAt)
  } catch (error) {
    return { ok: false, error: messageOf(error) }
  } finally {
    clearTimeout(timer)
  }
}

/**
 * Read the account balance, reusing a fresh cached reading.
 *
 * Never throws and never rejects: a missing home, a missing credential, a
 * network fault, a timeout, an HTTP error, or a malformed body all come back as
 * `{ ok: false, error }`, which is exactly what the widget renders.
 *
 * @param {{ home?: string, ttlMs?: number, retryMs?: number, fetch?: typeof fetch, now?: number, timeoutMs?: number }} [options]
 *   `ttlMs` is how long a success stays fresh; `retryMs` how long a failure does.
 * @returns {Promise<BalanceResult>} the current reading.
 */
export async function readBalance(options = {}) {
  const now = options.now ?? Date.now()
  const ttlMs = Number.isFinite(options.ttlMs) ? Number(options.ttlMs) : DEFAULT_TTL_MS
  const retryMs = Number.isFinite(options.retryMs) ? Number(options.retryMs) : DEFAULT_RETRY_MS

  if (cache !== undefined) {
    const age = now - cache.at
    const window = cache.value.ok ? ttlMs : retryMs
    if (age >= 0 && age < window) return cache.value
  }

  try {
    const value = await fetchBalance(options)
    cache = { at: Date.now(), value }
    return value
  } catch (error) {
    // `fetchBalance` reports failures as values; this is the belt-and-braces
    // path that guarantees the "never throws" contract.
    const value = { ok: false, error: messageOf(error) }
    cache = { at: Date.now(), value }
    return value
  }
}
