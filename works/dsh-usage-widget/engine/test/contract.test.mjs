/**
 * Contract check: the two new snapshot arrays must not have disturbed a single
 * pre-existing field.
 *
 * It folds the real session logs once, then renders the same dashboard twice —
 * through the pre-existing implementation below (copied verbatim from the
 * engine's previous shape) and through the engine's current `snapshotOf` — and
 * compares the legacy keys exactly. The event shape is compared the same way,
 * field by field, against a reference built the same way it always was.
 *
 * Run: node test/contract.test.mjs
 * Read-only: it touches no file outside this directory.
 */
import { readAllSessions } from '../session-store.mjs'
import { eventOf, snapshotOf } from '../cli.mjs'
import { buildDashboard, isPeak, priceOf, PRICE_CARD, FALLBACK_PRICE } from '../usage.mjs'

const RATE = 7.1
const NOW = Date.now()

/** The snapshot shape exactly as it was before `agents` and `jobs` were added. */
function legacySnapshot(dashboard, at, rate, balance) {
  const today = dashboard.today
  const totals = dashboard.totals
  const tokensOf = (tokens) => ({ hit: tokens.cacheHit, miss: tokens.cacheMiss, out: tokens.output })
  return {
    type: 'snapshot',
    at,
    peakNow: dashboard.peakNow,
    rate,
    today: {
      costUsd: today.cost,
      costCny: today.cost * rate,
      calls: today.calls,
      tokens: tokensOf(today.tokens),
    },
    total: {
      costUsd: totals.cost,
      costCny: totals.cost * rate,
      calls: totals.calls,
      sessions: totals.sessions,
      tokens: tokensOf(totals.tokens),
    },
    balance,
  }
}

/** The event shape exactly as it was. */
function legacyEvent(session, sample, rate) {
  const price = PRICE_CARD[sample.model] ?? FALLBACK_PRICE
  const costUsd = priceOf(sample.tokens, price, isPeak(sample.at))
  return {
    type: 'event',
    at: sample.at,
    session: session.sessionId,
    turn: sample.turn,
    step: sample.step,
    model: sample.model,
    hit: sample.tokens.cacheHit,
    miss: sample.tokens.cacheMiss,
    out: sample.tokens.output,
    costUsd,
    costCny: costUsd * rate,
  }
}

const sweep = await readAllSessions({ defaultModel: 'deepseek-flash' })
const dashboard = buildDashboard(sweep.sessions, { now: NOW })
const balance = { ok: true, currency: 'CNY', total: '5.69', granted: '0.00', toppedUp: '5.69', fetchedAt: NOW }

const before = legacySnapshot(dashboard, NOW, RATE, balance)
const after = snapshotOf(dashboard, NOW, RATE, balance, { agents: [{}], jobs: [{}] })

console.log(`sessions folded: ${sweep.sessions.length}, artifacts: ${sweep.artifacts}`)
console.log('')
console.log('legacy snapshot fields:', JSON.stringify(before))
console.log('new snapshot fields   :', JSON.stringify({ ...after, agents: '[…]', jobs: '[…]' }))
console.log('new snapshot keys     :', Object.keys(after).join(','))
console.log('')

/** Deep equality over the legacy half only. */
const snapshotLegacyIdentical = JSON.stringify(before) === JSON.stringify({
  type: after.type,
  at: after.at,
  peakNow: after.peakNow,
  rate: after.rate,
  today: after.today,
  total: after.total,
  balance: after.balance,
})
console.log(`${snapshotLegacyIdentical ? 'PASS' : 'FAIL'} every legacy snapshot field is byte-identical`)
console.log(`${after.agents !== undefined && after.jobs !== undefined ? 'PASS' : 'FAIL'} the snapshot carries agents and jobs`)
console.log(`${Object.keys(before).length + 2 === Object.keys(after).length ? 'PASS' : 'FAIL'} exactly two keys were added`)
console.log('')

// --- one event per freshly observed sample, compared field by field ----------
let samples = 0
let mismatches = 0
for (const session of sweep.sessions) {
  for (const sample of session.samples) {
    const expected = legacyEvent(session, sample, RATE)
    const actual = eventOf(session, sample, RATE)
    samples += 1
    if (JSON.stringify(expected) !== JSON.stringify(actual)) {
      mismatches += 1
      if (mismatches <= 3) console.log(`  mismatch ${session.sessionId}:${sample.turn}:${sample.step}`)
    }
  }
}
const firstSession = sweep.sessions.find((session) => session.samples.length > 0)
const exampleEvent = firstSession === undefined ? undefined : eventOf(firstSession, firstSession.samples[0], RATE)
console.log(`events compared: ${samples}, mismatches: ${mismatches}`)
console.log(`example event: ${JSON.stringify(exampleEvent)}`)
console.log(`${mismatches === 0 && samples > 0 ? 'PASS' : 'FAIL'} every event field is unchanged for every sample`)
console.log('')

const tokensShape = (tokens) => Object.keys(tokens).join(',') === 'hit,miss,out'
const checks = [
  ['today carries costUsd, costCny, calls, tokens{hit,miss,out}', Object.keys(before.today).join(',') === 'costUsd,costCny,calls,tokens' && tokensShape(before.today.tokens)],
  ['total carries costUsd, costCny, calls, sessions, tokens', Object.keys(before.total).join(',') === 'costUsd,costCny,calls,sessions,tokens'],
  ['balance is passed through untouched', after.balance === balance],
  ['event keeps type, at, session, turn, step, model, hit, miss, out, costUsd, costCny', Object.keys(exampleEvent ?? {}).join(',') === 'type,at,session,turn,step,model,hit,miss,out,costUsd,costCny'],
  ['snapshotLegacyIdentical', snapshotLegacyIdentical],
  ['no event mismatch', mismatches === 0 && samples > 0],
]
console.log('')
for (const [label, pass] of checks) console.log(`${pass ? 'PASS' : 'FAIL'} ${label}`)
console.log(checks.every(([, pass]) => pass) ? 'ALL PASS' : 'SOME FAILED')
process.exitCode = checks.every(([, pass]) => pass) ? 0 : 1
