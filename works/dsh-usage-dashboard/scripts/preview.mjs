/**
 * Development harness: fold every durable session and print the resulting
 * accounting as text, so the engine can be checked without the Web GUI.
 *
 * Usage: node scripts/preview.mjs [--json] [--home <dir>] [--model <id>]
 *
 * @module dsh-usage-dashboard/scripts/preview
 */

import { writeFileSync } from 'node:fs'

import { buildDashboard } from '../src/usage.mjs'
import { readAllSessions, resolveDshHome } from '../src/session-store.mjs'

function parseArgs(argv) {
  const options = { json: false, home: undefined, model: 'deepseek-flash', out: undefined }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--json') options.json = true
    else if (arg === '--home') options.home = argv[++index]
    else if (arg === '--model') options.model = argv[++index]
    else if (arg === '--out') options.out = argv[++index]
  }
  return options
}

const usd = (value) =>
  value >= 1
    ? `$${value.toFixed(4)}`
    : value >= 0.0001
      ? `$${value.toFixed(6)}`
      : `$${value.toFixed(8)}`

const int = (value) => value.toLocaleString('en-US')

const options = parseArgs(process.argv.slice(2))
const home = options.home ?? resolveDshHome()
const sweep = await readAllSessions({ home, defaultModel: options.model })
const dashboard = buildDashboard(sweep.sessions, { now: Date.now() })

if (options.json || options.out !== undefined) {
  const payload = JSON.stringify(dashboard, null, 2)
  if (options.out !== undefined) writeFileSync(options.out, payload, 'utf8')
  else console.log(payload)
  process.exit(0)
}

console.log(`home                ${home}`)
console.log(
  `artifacts           ${sweep.artifacts}  (${(sweep.bytes / 1024 / 1024).toFixed(1)} MiB raw, ${sweep.elapsedMs} ms)`,
)
console.log(`failures            ${sweep.failures.length}`)
for (const failure of sweep.failures) console.log(`  ! ${failure.sessionId}: ${failure.error}`)
console.log('')
console.log('── totals ──────────────────────────────────────────────')
console.log(`sessions            ${int(dashboard.totals.sessions)}`)
console.log(`model calls         ${int(dashboard.totals.calls)}`)
console.log(`turns               ${int(dashboard.totals.turns)}`)
console.log(`prompt (miss)       ${int(dashboard.totals.tokens.cacheMiss)}`)
console.log(`prompt (cache hit)  ${int(dashboard.totals.tokens.cacheHit)}`)
console.log(`completion          ${int(dashboard.totals.tokens.output)}`)
console.log(`reasoning (in out)  ${int(dashboard.totals.tokens.reasoning)}`)
console.log(`cache-hit share     ${(dashboard.totals.cacheHitShare * 100).toFixed(1)}%`)
console.log(`cost                ${usd(dashboard.totals.cost)}`)
console.log(
  `  peak / off-peak   ${usd(dashboard.totals.peakCost)} / ${usd(dashboard.totals.offPeakCost)}`,
)
console.log('')
console.log('── by model ────────────────────────────────────────────')
for (const row of dashboard.models) {
  console.log(
    `${row.model.padEnd(30)} calls ${int(row.calls).padStart(6)}  out ${int(row.tokens.output).padStart(10)}  ${usd(row.cost)}`,
  )
}
console.log('')
console.log('── by day (last 14) ────────────────────────────────────')
for (const row of dashboard.days.slice(-14)) {
  const total = row.tokens.cacheHit + row.tokens.cacheMiss + row.tokens.output
  console.log(
    `${row.day}  calls ${int(row.calls).padStart(5)}  tokens ${int(total).padStart(11)}  ${usd(row.cost).padStart(12)}`,
  )
}
console.log('')
console.log('── sessions ────────────────────────────────────────────')
for (const row of dashboard.sessions) {
  const total = row.tokens.cacheHit + row.tokens.cacheMiss + row.tokens.output
  console.log(
    `${row.sessionId.slice(0, 20)}  calls ${int(row.calls).padStart(4)}  tokens ${int(total).padStart(10)}  ${usd(row.cost).padStart(12)}  ${row.title.slice(0, 40)}`,
  )
}
