/**
 * Print the `turn/start` / `turn/end` evidence behind every real `agents` entry.
 *
 * The engine claims an agent is `running` when the newest `turn/start` in its
 * log has no later `turn/end`. This prints, per delegating session, the turn
 * events in order and the state derived from them, so the claim can be checked
 * by eye against the durable log.
 *
 *   node test/agent-evidence.mjs [--session <id>]
 */
import { readFile } from 'node:fs/promises'

import { listSessionArtifacts } from '../session-store.mjs'
import { readZstdJsonlLines } from '../zstd.mjs'
import { buildAgents, foldActivity } from '../activity.mjs'

const only = process.argv.includes('--session') ? process.argv[process.argv.indexOf('--session') + 1] : undefined
const now = Date.now()
const artifacts = await listSessionArtifacts()

/** @type {any[]} */
const rows = []
/** @type {Map<string, any[]>} */
const turnsById = new Map()
/** @type {Map<string, string[]>} */
const toolTurnsById = new Map()

for (const artifact of artifacts) {
  let lines
  try {
    lines = readZstdJsonlLines(await readFile(artifact.path))
  } catch (error) {
    console.log(`# unreadable ${artifact.sessionId}: ${error.message}`)
    continue
  }
  const fold = foldActivity(lines, artifact)
  rows.push(fold)
  const turns = []
  const toolIds = []
  for (const line of lines) {
    let record
    try {
      record = JSON.parse(line)
    } catch {
      continue
    }
    const time = record.time
    if (record.type === 'turn/start') turns.push({ kind: 'start', turn: record.data?.turn, time })
    else if (record.type === 'turn/end') turns.push({ kind: 'end', turn: record.data?.turn, time })
    else if (record.type === 'tool/call') toolIds.push(`${record.data?.name}`)
  }
  turnsById.set(artifact.sessionId, turns)
  toolTurnsById.set(artifact.sessionId, toolIds)
  void fold
}

const agents = buildAgents(rows, now)
console.log(`now=${now} artifacts=${artifacts.length} agents=${agents.length}`)
console.log('')
for (const agent of agents) {
  const turns = turnsById.get(agent.id) ?? []
  const header = rows.find((row) => row.sessionId === agent.id)
  console.log(`AGENT ${agent.id}`)
  console.log(`  label          ${agent.label}`)
  console.log(`  state          ${agent.state}`)
  console.log(`  model          ${agent.model}`)
  console.log(`  turn           ${agent.turn}   (turn/start count = ${turns.filter((row) => row.kind === 'start').length})`)
  console.log(`  startedAt      ${agent.startedAt}`)
  console.log(`  elapsedMs      ${agent.elapsedMs}`)
  console.log(`  sinceLastWrite ${agent.sinceLastWriteMs}`)
  console.log(`  delegationDepth ${header?.depth}`)
  console.log(`  turn events    ${turns.map((row) => `${row.kind}#${row.turn}@${row.time}`).join('  ') || '(none)'}`)
  const derived = turns.length === 0 ? 'idle (no turn events)' : turns[turns.length - 1].kind === 'start' ? 'running (newest turn/start has no later turn/end)' : 'idle (newest turn closed)'
  console.log(`  derived        ${derived}`)
  console.log('')
}
if (only !== undefined) {
  const match = agents.find((agent) => agent.id === only)
  console.log(match === undefined ? `no agent ${only}` : JSON.stringify(match))
}
