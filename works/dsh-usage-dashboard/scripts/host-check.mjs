/**
 * Development harness: invoke the host plugin's route handler directly against
 * a stubbed Cordis context, so the sweep, the pricing fold, and the response
 * shape can be checked without a running Harness.
 *
 * Usage: node scripts/host-check.mjs [--home <dir>] [--out <file>]
 *
 * @module dsh-usage-dashboard/scripts/host-check
 */

import { writeFileSync } from 'node:fs'

import { apply, ROUTE_PATH } from '../src/index.mjs'

function parseArgs(argv) {
  const options = { home: undefined, out: undefined }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--home') options.home = argv[++index]
    else if (argv[index] === '--out') options.out = argv[++index]
  }
  return options
}

const options = parseArgs(process.argv.slice(2))

/** Minimal host context: what the plugin actually touches. */
const registered = []
const provided = new Map()
const ctx = {
  connection: {
    fetch: {
      register(route) {
        registered.push(route)
        return async () => {}
      },
    },
  },
  reflect: {
    provide(name, value) {
      provided.set(name, value)
      return () => {}
    },
  },
  effect(callback, label) {
    const dispose = callback()
    return typeof dispose === 'function' ? dispose : () => {}
  },
  logger: { warn: (...args) => console.warn('[warn]', ...args) },
  get(name) {
    if (name === 'llm') return undefined
    return undefined
  },
}

apply(ctx, { ttlMs: 1000, home: options.home })

if (registered.length !== 1) throw new Error(`expected one route, got ${registered.length}`)
const route = registered[0]
console.log(`route   ${route.path}  methods=${route.methods.join(',')}  body=${route.requestBody}`)
if (route.path !== ROUTE_PATH) throw new Error(`route path mismatch: ${route.path}`)

const response = await route.fetch(new Request(`http://127.0.0.1${ROUTE_PATH}`, { method: 'GET' }))
console.log(`status  ${response.status} ${response.headers.get('content-type')}`)
const payload = await response.json()

const checks = [
  ['totals.cost is a number', typeof payload.totals.cost === 'number'],
  ['totals.calls > 0', payload.totals.calls > 0],
  ['days is a non-empty array', Array.isArray(payload.days) && payload.days.length > 0],
  ['models is a non-empty array', Array.isArray(payload.models) && payload.models.length > 0],
  ['sessions is a non-empty array', Array.isArray(payload.sessions) && payload.sessions.length > 0],
  ['hours has 24 buckets', Array.isArray(payload.hours) && payload.hours.length === 24],
  ['source.artifacts reported', typeof payload.source.artifacts === 'number'],
  ['peakNow is boolean', typeof payload.peakNow === 'boolean'],
  ['cost equals sum of days', Math.abs(payload.days.reduce((sum, day) => sum + day.cost, 0) - payload.totals.cost) < 1e-9],
  [
    'cost equals sum of models',
    Math.abs(payload.models.reduce((sum, row) => sum + row.cost, 0) - payload.totals.cost) < 1e-9,
  ],
  [
    'cost equals sum of sessions',
    Math.abs(payload.sessions.reduce((sum, row) => sum + row.cost, 0) - payload.totals.cost) < 1e-9,
  ],
  ['peak + off-peak equals total', Math.abs(payload.totals.peakCost + payload.totals.offPeakCost - payload.totals.cost) < 1e-9],
]

let failed = 0
for (const [label, ok] of checks) {
  if (!ok) failed += 1
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}`)
}

console.log(
  `\ntotals  cost $${payload.totals.cost.toFixed(4)}  calls ${payload.totals.calls}  sessions ${payload.totals.sessions}  cache-hit ${(payload.totals.cacheHitShare * 100).toFixed(1)}%`,
)

if (options.out !== undefined) {
  writeFileSync(options.out, JSON.stringify(payload, null, 2), 'utf8')
  console.log(`wrote   ${options.out}`)
}
process.exit(failed === 0 ? 0 : 1)
