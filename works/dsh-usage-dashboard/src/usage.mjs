/**
 * Token-usage and cost engine for the DSH usage dashboard.
 *
 * The durable session log is the single source of truth: every model call that
 * reported usage appended one `assistant/message` carrying that call's
 * provider-reported `usage` bucket, and every request envelope is described by
 * the `request/header` / `request/context` pair that precedes it. Folding those
 * two event kinds yields exact per-turn, per-day, per-model accounting with no
 * model calls and no dependence on live session state.
 *
 * Cost is *computed*, not recorded: the harness logs tokens, never money. The
 * price table below is DeepSeek's published per-million rate card, applied to
 * each step's own timestamp so the peak/off-peak split follows the moment the
 * call actually ran.
 *
 * @module dsh-usage-dashboard/usage
 */

/**
 * One model route's price card, in USD per one million tokens.
 * @typedef {object} ModelPrice
 * @property {string} label - display name for the route.
 * @property {number} cacheHit - USD per 1M prompt tokens served from cache.
 * @property {number} cacheMiss - USD per 1M prompt tokens that missed cache.
 * @property {number} output - USD per 1M completion tokens.
 */

/**
 * Published DeepSeek price card, USD per 1M tokens.
 *
 * Source: DeepSeek "Models & Pricing", effective 2026-09-10 (the V4.1-Flash
 * repricing). Peak is exactly double off-peak; peak runs Monday through Friday
 * in two UTC blocks, 01:00-04:00 and 06:00-10:00, and every other hour —
 * including all weekend — bills off-peak.
 *
 * The legacy ids `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` are
 * still accepted by the API and are served by V4.1-Flash at Flash prices.
 */
export const PRICE_CARD = {
  'deepseek-flash': {
    label: 'DeepSeek-V4.1-Flash',
    cacheHit: 0.003,
    cacheMiss: 0.15,
    output: 0.6,
  },
  'deepseek-v4-flash': {
    label: 'DeepSeek-V4.1-Flash (legacy id)',
    cacheHit: 0.003,
    cacheMiss: 0.15,
    output: 0.6,
  },
  'deepseek-v4-flash-vision-exp': {
    label: 'DeepSeek-V4.1-Flash (vision, legacy id)',
    cacheHit: 0.003,
    cacheMiss: 0.15,
    output: 0.6,
  },
  'deepseek-v4-pro': {
    label: 'DeepSeek-V4-Pro',
    cacheHit: 0.022,
    cacheMiss: 0.66,
    output: 1.98,
  },
}

/**
 * Fallback card for a route this build does not know: priced at the Flash
 * off-peak card so an unknown model inflates nothing silently, and reported
 * separately as `unpricedModels` for the UI to flag.
 */
export const FALLBACK_PRICE = {
  label: 'unknown route',
  cacheHit: 0.003,
  cacheMiss: 0.15,
  output: 0.6,
}

/** UTC hours that bill at the peak rate (Monday-Friday only). */
const PEAK_HOUR_BLOCKS = [
  [1, 4],
  [6, 10],
]

/** Round one hour block's [start, end) range test. */
function inHourBlock(hour, [start, end]) {
  return hour >= start && hour < end
}

/**
 * Whether one instant bills at the peak rate.
 *
 * Peak is Monday-Friday 01:00-04:00 and 06:00-10:00 UTC; weekends are wholly
 * off-peak. Chinese public holidays are also off-peak by DeepSeek's policy but
 * carry no published machine-readable calendar, so they are not modelled and
 * those days are billed at peak here.
 *
 * @param {number} epochMs - the model call's timestamp in epoch milliseconds.
 * @returns {boolean} true when the instant falls inside a peak window.
 */
export function isPeak(epochMs) {
  const at = new Date(epochMs)
  const day = at.getUTCDay()
  if (day === 0 || day === 6) return false
  const hour = at.getUTCHours()
  return PEAK_HOUR_BLOCKS.some((block) => inHourBlock(hour, block))
}

/**
 * Price one provider usage bucket at one instant.
 * @param {{ cacheHit: number, cacheMiss: number, output: number }} tokens - raw counts.
 * @param {ModelPrice} price - the route's off-peak card.
 * @param {boolean} peak - whether the call billed at peak.
 * @returns {number} cost in USD.
 */
export function priceOf(tokens, price, peak) {
  const multiplier = peak ? 2 : 1
  return (
    ((tokens.cacheMiss * price.cacheMiss +
      tokens.cacheHit * price.cacheHit +
      tokens.output * price.output) /
      1e6) *
    multiplier
  )
}

/** An all-zero usage bucket. */
export function emptyTokens() {
  return { cacheHit: 0, cacheMiss: 0, output: 0, reasoning: 0 }
}

/**
 * Add one bucket into another in place.
 * @param {ReturnType<typeof emptyTokens>} target - accumulator.
 * @param {ReturnType<typeof emptyTokens>} source - bucket to add.
 */
export function addTokens(target, source) {
  target.cacheHit += source.cacheHit
  target.cacheMiss += source.cacheMiss
  target.output += source.output
  target.reasoning += source.reasoning
}

/** Total tokens of one bucket (prompt + completion + reasoning). */
export function sumTokens(tokens) {
  return (
    tokens.cacheHit + tokens.cacheMiss + tokens.output + tokens.reasoning
  )
}

/**
 * Extract the raw bucket from one `assistant/message` event.
 *
 * `inputTokens` is the provider's uncached (cache-miss) prompt count while
 * `cacheReadTokens` is the cached (cache-hit) prompt count — DeepSeek reports
 * the two disjointly — and `outputTokens` already includes `reasoningTokens`,
 * which is kept separately only as a reported share.
 *
 * @param {any} usage - the event's `data.usage`.
 * @returns {{ cacheHit: number, cacheMiss: number, output: number, reasoning: number } | undefined}
 *   the bucket, or undefined when the event carries no usable usage.
 */
export function bucketFromUsage(usage) {
  if (usage === null || typeof usage !== 'object') return undefined
  const cacheMiss = count(usage.inputTokens)
  const output = count(usage.outputTokens)
  if (cacheMiss === undefined || output === undefined) return undefined
  return {
    cacheMiss,
    cacheHit: count(usage.cacheReadTokens) ?? 0,
    output,
    reasoning: count(usage.reasoningTokens) ?? 0,
  }
}

/** A non-negative safe integer, or undefined for anything else. */
function count(value) {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
    ? value
    : undefined
}

/**
 * Fold one session's JSONL event lines into accounting facts.
 *
 * The fold keeps the *last* usage sample of each (turn, step) because a
 * retried step replaces its sample rather than adding a second call, and it
 * reads the model route from the request envelope in force — the newest
 * `request/header` for the provider/model pair, falling back to the assistant
 * message's own `source`. Sessions whose logs predate a recorded route fall
 * back to the configured default so their history is still priced.
 *
 * @param {string[]} lines - JSONL event lines of one session log.
 * @param {string} sessionId - the session id (the directory name).
 * @param {string} workspace - the workspace bucket the session belongs to.
 * @param {string} defaultModel - route used when a session log names none.
 * @returns {SessionFacts} folded facts for this session.
 */
export function foldSession(lines, sessionId, workspace, defaultModel) {
  /** @type {any} */
  let meta
  /** @type {{ provider: string, model: string }} */
  let route = { provider: 'deepseek-official', model: defaultModel }
  /** @type {string | undefined} */
  let title
  /** @type {Map<string, { at: number, turn: number, step: number, model: string, provider: string, tokens: ReturnType<typeof emptyTokens> }>} */
  const steps = new Map()
  let turns = 0
  let maxStep = 0
  let firstAt
  let lastAt

  for (const line of lines) {
    /** @type {any} */
    let event
    try {
      event = JSON.parse(line)
    } catch {
      continue
    }
    if (event === null || typeof event !== 'object') continue
    const time = typeof event.time === 'number' ? event.time : undefined
    if (time !== undefined) {
      if (firstAt === undefined || time < firstAt) firstAt = time
      if (lastAt === undefined || time > lastAt) lastAt = time
    }
    switch (event.type) {
      case 'session': {
        meta = event
        if (typeof event.agentPreset === 'string' && route.model === defaultModel) {
          // no-op: the preset never names the model route; kept for clarity
        }
        break
      }
      case 'session/title': {
        const data = event.data
        if (data !== null && typeof data === 'object' && typeof data.title === 'string') {
          title = data.title
        }
        break
      }
      case 'request/header': {
        const config = event.data?.header?.config
        if (config !== null && typeof config === 'object') {
          if (typeof config.provider === 'string' && typeof config.model === 'string') {
            route = { provider: config.provider, model: config.model }
          }
        }
        break
      }
      case 'request/context': {
        const data = event.data
        if (data !== null && typeof data === 'object') {
          if (typeof data.provider === 'string' && typeof data.model === 'string') {
            route = { provider: data.provider, model: data.model }
          }
        }
        break
      }
      case 'turn/start': {
        const turn = event.data?.turn
        if (typeof turn === 'number') turns = Math.max(turns, turn)
        break
      }
      case 'assistant/message': {
        const data = event.data
        if (data === null || typeof data !== 'object') break
        const tokens = bucketFromUsage(data.usage)
        if (tokens === undefined) break
        const turn = typeof data.turn === 'number' ? data.turn : 0
        const step = typeof data.step === 'number' ? data.step : 0
        maxStep = Math.max(maxStep, step)
        const source = data.message?.source
        const model =
          typeof source?.model === 'string' ? source.model : route.model
        const provider =
          typeof source?.provider === 'string' ? source.provider : route.provider
        // Last sample wins for one (turn, step): a retry replaces, never adds.
        steps.set(`${turn}:${step}`, {
          at: time ?? lastAt ?? 0,
          turn,
          step,
          model,
          provider,
          tokens,
        })
        break
      }
      default:
        break
    }
  }

  const samples = [...steps.values()].sort(
    (left, right) => left.turn - right.turn || left.step - right.step,
  )

  return {
    sessionId,
    workspace,
    title: title ?? meta?.id ?? sessionId,
    cwd: typeof meta?.cwd === 'string' ? meta.cwd : undefined,
    preset: typeof meta?.agentPreset === 'string' ? meta.agentPreset : undefined,
    createdAt: typeof meta?.createdAt === 'number' ? meta.createdAt : firstAt,
    firstAt,
    lastAt,
    turns,
    steps: maxStep,
    samples,
  }
}

/**
 * @typedef {object} SessionFacts
 * @property {string} sessionId
 * @property {string} workspace
 * @property {string} title
 * @property {string | undefined} cwd
 * @property {string | undefined} preset
 * @property {number | undefined} createdAt
 * @property {number | undefined} firstAt
 * @property {number | undefined} lastAt
 * @property {number} turns
 * @property {number} steps
 * @property {{ at: number, turn: number, step: number, model: string, provider: string, tokens: ReturnType<typeof emptyTokens> }[]} samples
 */

/** UTC `YYYY-MM-DD` key of one instant. */
export function dayKey(epochMs) {
  return new Date(epochMs).toISOString().slice(0, 10)
}

/**
 * Group a set of session facts into the dashboard's view model.
 *
 * @param {SessionFacts[]} sessions - every folded session.
 * @param {{ priceCard?: Record<string, ModelPrice>, now?: number }} [options]
 * @returns {Dashboard} the complete dashboard payload.
 */
export function buildDashboard(sessions, options = {}) {
  const priceCard = options.priceCard ?? PRICE_CARD
  const now = options.now ?? Date.now()

  /** @type {ReturnType<typeof emptyTokens>} */
  const totalTokens = emptyTokens()
  let totalCost = 0
  let peakCost = 0
  let offPeakCost = 0
  let peakSamples = 0
  /** @type {Set<string>} */
  const unpricedModels = new Set()
  /** @type {Map<string, any>} */
  const byModel = new Map()
  /** @type {Map<string, any>} */
  const byDay = new Map()
  /** @type {Map<string, any>} */
  const byHour = new Map()
  /** @type {Map<string, any>} */
  const byWorkspace = new Map()
  /** @type {any[]} */
  const recent = []

  for (const session of sessions) {
    const sessionTokens = emptyTokens()
    let sessionCost = 0

    for (const sample of session.samples) {
      const price = priceCard[sample.model] ?? FALLBACK_PRICE
      if (priceCard[sample.model] === undefined) unpricedModels.add(sample.model)
      const peak = isPeak(sample.at)
      const cost = priceOf(sample.tokens, price, peak)

      addTokens(sessionTokens, sample.tokens)
      addTokens(totalTokens, sample.tokens)
      sessionCost += cost
      totalCost += cost
      if (peak) {
        peakCost += cost
        peakSamples += 1
      } else {
        offPeakCost += cost
      }

      const day = dayKey(sample.at)
      const dayRow =
        byDay.get(day) ??
        (() => {
          const row = {
            day,
            tokens: emptyTokens(),
            cost: 0,
            peakCost: 0,
            offPeakCost: 0,
            calls: 0,
          }
          byDay.set(day, row)
          return row
        })()
      addTokens(dayRow.tokens, sample.tokens)
      dayRow.cost += cost
      dayRow.calls += 1
      if (peak) dayRow.peakCost += cost
      else dayRow.offPeakCost += cost

      const hour = new Date(sample.at).getUTCHours()
      const hourRow = byHour.get(hour) ?? { hour, tokens: emptyTokens(), cost: 0, calls: 0 }
      addTokens(hourRow.tokens, sample.tokens)
      hourRow.cost += cost
      hourRow.calls += 1
      byHour.set(hour, hourRow)

      const modelRow =
        byModel.get(sample.model) ??
        (() => {
          const row = {
            model: sample.model,
            label: price.label,
            provider: sample.provider,
            priced: priceCard[sample.model] !== undefined,
            tokens: emptyTokens(),
            cost: 0,
            calls: 0,
          }
          byModel.set(sample.model, row)
          return row
        })()
      addTokens(modelRow.tokens, sample.tokens)
      modelRow.cost += cost
      modelRow.calls += 1
    }

    const workspaceRow =
      byWorkspace.get(session.workspace) ??
      (() => {
        const row = {
          workspace: session.workspace,
          tokens: emptyTokens(),
          cost: 0,
          sessions: 0,
          calls: 0,
        }
        byWorkspace.set(session.workspace, row)
        return row
      })()
    workspaceRow.sessions += 1
    workspaceRow.calls += session.samples.length
    addTokens(workspaceRow.tokens, sessionTokens)
    workspaceRow.cost += sessionCost

    if (session.samples.length > 0) {
      recent.push({
        sessionId: session.sessionId,
        title: session.title,
        workspace: session.workspace,
        cwd: session.cwd,
        preset: session.preset,
        turns: session.turns,
        steps: session.steps,
        calls: session.samples.length,
        firstAt: session.firstAt,
        lastAt: session.lastAt,
        tokens: sessionTokens,
        cost: sessionCost,
      })
    }
  }

  const days = [...byDay.values()].sort((left, right) => (left.day < right.day ? -1 : 1))
  const coveredDays = days.length
  const startOfToday = Date.UTC(
    new Date(now).getUTCFullYear(),
    new Date(now).getUTCMonth(),
    new Date(now).getUTCDate(),
  )
  const today = byDay.get(dayKey(now)) ?? {
    day: dayKey(now),
    tokens: emptyTokens(),
    cost: 0,
    peakCost: 0,
    offPeakCost: 0,
    calls: 0,
  }

  return {
    generatedAt: now,
    totals: {
      sessions: recent.length,
      calls: recent.reduce((sum, row) => sum + row.calls, 0),
      turns: recent.reduce((sum, row) => sum + row.turns, 0),
      tokens: totalTokens,
      cost: totalCost,
      peakCost,
      offPeakCost,
      peakSamples,
      cacheHitShare:
        totalTokens.cacheHit + totalTokens.cacheMiss > 0
          ? totalTokens.cacheHit / (totalTokens.cacheHit + totalTokens.cacheMiss)
          : 0,
    },
    coverage: {
      firstAt: sessions.reduce(
        (min, session) =>
          session.firstAt !== undefined && (min === undefined || session.firstAt < min)
            ? session.firstAt
            : min,
        undefined,
      ),
      lastAt: sessions.reduce(
        (max, session) =>
          session.lastAt !== undefined && (max === undefined || session.lastAt > max)
            ? session.lastAt
            : max,
        undefined,
      ),
      activeDays: coveredDays,
      spanDays:
        sessions.length === 0
          ? 0
          : Math.max(1, Math.round((now - startOfToday) / 86_400_000) + 1),
    },
    today,
    days: days.slice(-60),
    models: [...byModel.values()].sort((left, right) => right.cost - left.cost),
    workspaces: [...byWorkspace.values()].sort((left, right) => right.cost - left.cost),
    hours: Array.from({ length: 24 }, (_, hour) => {
      const row = byHour.get(hour) ?? { hour, tokens: emptyTokens(), cost: 0, calls: 0 }
      return row
    }),
    sessions: recent.sort((left, right) => (right.lastAt ?? 0) - (left.lastAt ?? 0)),
    priceCard,
    fallbackPrice: FALLBACK_PRICE,
    unpricedModels: [...unpricedModels],
    peakNow: isPeak(now),
  }
}

/**
 * @typedef {object} Dashboard
 * @property {number} generatedAt
 * @property {any} totals
 * @property {any} coverage
 * @property {any} today
 * @property {any[]} days
 * @property {any[]} models
 * @property {any[]} workspaces
 * @property {any[]} hours
 * @property {any[]} sessions
 * @property {Record<string, ModelPrice>} priceCard
 * @property {ModelPrice} fallbackPrice
 * @property {string[]} unpricedModels
 * @property {boolean} peakNow
 */
