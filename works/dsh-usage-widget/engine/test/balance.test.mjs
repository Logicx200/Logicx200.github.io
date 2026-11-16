/**
 * Self-contained test for engine/balance.mjs: CNY preference, exact result shape,
 * TTL caching, retry-window caching, and the never-throw contract.
 *
 * The network is stubbed, so this runs offline; the credential ref is read from the
 * real `$DSH_HOME` but is never printed (only its presence is asserted).
 *
 * Run: node test/balance.test.mjs
 */
import { clearBalanceCache, readBalance } from '../balance.mjs'

let calls = 0
let okCalls = 0
let seenAuth = ''

const ok = async (_url, init) => {
  calls += 1
  okCalls += 1
  seenAuth = String(init.headers.authorization)
  return new Response(
    JSON.stringify({
      is_available: true,
      balance_infos: [
        { currency: 'USD', total_balance: '1.00', granted_balance: '0.00', topped_up_balance: '1.00' },
        { currency: 'CNY', total_balance: '8.47', granted_balance: '0.00', topped_up_balance: '8.47' },
      ],
    }),
    { status: 200, headers: { 'content-type': 'application/json' } },
  )
}

const boom = async () => {
  calls += 1
  throw new Error('socket hang up')
}

const results = []
const check = (label, actual, expected) =>
  results.push([
    JSON.stringify(actual) === JSON.stringify(expected),
    `${label}: ${JSON.stringify(actual)}`,
  ])

clearBalanceCache()
const first = await readBalance({ fetch: ok, ttlMs: 60_000 })
check('cny preferred + exact shape', first, {
  ok: true,
  currency: 'CNY',
  total: '8.47',
  granted: '0.00',
  toppedUp: '8.47',
  fetchedAt: first.fetchedAt,
})
check('bearer header set, key never echoed', /^Bearer sk-\S+$/.test(seenAuth), true)
check('one network call', calls, 1)

await readBalance({ fetch: ok, ttlMs: 60_000 })
check('cache reused while fresh', calls, 1)

clearBalanceCache()
const failing = await readBalance({ fetch: boom, ttlMs: 60_000 })
check('network failure is a value, not a throw', failing, { ok: false, error: 'socket hang up' })

await readBalance({ fetch: ok, ttlMs: 60_000 })
check('failure stays cached: no refetch, no success call', { total: calls, okCalls }, { total: 2, okCalls: 1 })

const expired = await readBalance({ fetch: ok, ttlMs: 0, retryMs: 0 })
check('expired ttl refetches', { total: calls, okCalls }, { total: 3, okCalls: 2 })
check('recovered reading is ok', expired.ok, true)

clearBalanceCache()
const http = await readBalance({
  fetch: async () => new Response('nope', { status: 401 }),
  ttlMs: 0,
  retryMs: 0,
})
check('http error reported without a body echo', http, {
  ok: false,
  error: 'balance request failed: HTTP 401',
})

clearBalanceCache()
const bare = await readBalance({ fetch: async () => new Response('{}', { status: 200 }), ttlMs: 0, retryMs: 0 })
check('empty balance_infos is an error', bare, {
  ok: false,
  error: 'balance response carried no balance_infos',
})

for (const [pass, label] of results) console.log(`${pass ? 'PASS' : 'FAIL'} ${label}`)
const allPassed = results.every(([pass]) => pass)
console.log(allPassed ? 'ALL PASS' : 'SOME FAILED')
process.exitCode = allPassed ? 0 : 1
