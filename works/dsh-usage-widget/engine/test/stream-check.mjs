/**
 * Stream check: show the `ready` line, the live snapshots (with the new arrays)
 * and any `event` lines, exactly as they leave the engine, then exit.
 *
 *   node test/stream-check.mjs [seconds]
 *
 * It starts the real engine against the real $DSH_HOME and forwards its stdout,
 * so "the contract is untouched" is checked on the wire and not only in a unit.
 */
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ENGINE = join(dirname(fileURLToPath(import.meta.url)), '..')
const WIDGET = join(ENGINE, '..')
const seconds = Number(process.argv[2] ?? '8')

const child = spawn(process.execPath, [join(ENGINE, 'cli.mjs')], {
  cwd: WIDGET,
  stdio: ['ignore', 'pipe', 'pipe'],
  windowsHide: true,
})

let stdout = ''
let stderr = ''
child.stdout.setEncoding('utf8')
child.stderr.setEncoding('utf8')
child.stdout.on('data', (chunk) => {
  stdout += chunk
})
child.stderr.on('data', (chunk) => {
  stderr += chunk
})

await new Promise((done) => setTimeout(done, seconds * 1000))
child.kill()
await new Promise((done) => setTimeout(done, 500))

const rows = stdout
  .split('\n')
  .filter((line) => line.length > 0)
  .map((line) => JSON.parse(line))

console.log(`lines=${rows.length}`)
for (const row of rows) {
  if (row.type === 'ready') {
    console.log(`READY   ${JSON.stringify(row)}`)
  } else if (row.type === 'error') {
    console.log(`ERROR   ${JSON.stringify(row)}`)
  } else if (row.type === 'event') {
    console.log(`EVENT   ${JSON.stringify(row)}`)
  } else {
    const { agents, jobs, ...rest } = row
    console.log(`SNAPSHOT ${JSON.stringify(rest)}`)
    console.log(`         agents=${agents.length} jobs=${jobs.length}`)
    for (const agent of agents) console.log(`           agent ${JSON.stringify(agent)}`)
    for (const job of jobs) console.log(`           job   ${JSON.stringify(job)}`)
  }
}

console.log('')
console.log(`stderr: ${stderr.length === 0 ? '(empty)' : stderr}`)
const eventRows = rows.filter((row) => row.type === 'event')
const ready = rows.find((row) => row.type === 'ready')
const snapshot = rows.find((row) => row.type === 'snapshot')
const eventFields = eventRows.length === 0 ? '(no event lines in this window)' : Object.keys(eventRows[0]).join(',')
console.log(`ready keys:    ${ready === undefined ? '(missing)' : Object.keys(ready).join(',')}`)
console.log(`snapshot keys: ${snapshot === undefined ? '(missing)' : Object.keys(snapshot).join(',')}`)
console.log(`event keys:    ${eventFields}`)
console.log(`every snapshot has agents and jobs arrays: ${rows.filter((r) => r.type === 'snapshot').every((r) => Array.isArray(r.agents) && Array.isArray(r.jobs))}`)
