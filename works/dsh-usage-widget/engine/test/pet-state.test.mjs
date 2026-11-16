/**
 * Checks for `engine/pet-state.mjs`: the heartbeat reader, the event clock and
 * the published state line.
 *
 * Run: node test/pet-state.test.mjs
 * Exits non-zero on failure. Writes only inside a temp directory it creates.
 *
 * The point of this file is that the engine never re-decides a pet state: every
 * case below compares the published line against `computeState()` itself for the
 * same observation, so `pet/state.mjs` stays the only place the ladder lives.
 */
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import {
  computePet,
  createPetTracker,
  defaultHeartbeatPath,
  observeDshRunning,
  parseHeartbeat,
  writePetState,
  HEARTBEAT_FILE_NAME,
} from '../pet-state.mjs'
import { computeState } from '../../pet/state.mjs'

const NOW = 1_790_000_000_000
let failures = 0
let checks = 0

/**
 * One check.
 * @param {string} label - what is being asserted.
 * @param {boolean} pass - the result.
 * @param {string} [detail] - extra context on failure.
 */
function check(label, pass, detail = '') {
  checks += 1
  if (!pass) failures += 1
  console.log(`${pass ? 'PASS' : 'FAIL'} ${label}${pass || detail.length === 0 ? '' : `  (${detail})`}`)
}

/** Write a heartbeat. @param {string} path @param {boolean|string} running @param {number} at */
function beat(path, running, at) {
  writeFileSync(path, JSON.stringify({ running, pid: 7, at }))
}

const dir = mkdtempSync(join(tmpdir(), 'dsh-pet-state-'))
const heartbeatPath = join(dir, HEARTBEAT_FILE_NAME)
const statePath = join(dir, 'state.json')

try {
  // ---- parseHeartbeat ------------------------------------------------------
  check('parseHeartbeat accepts a well-formed beat', parseHeartbeat('{"running":true,"pid":7,"at":1}')?.running === true)
  check('parseHeartbeat rejects malformed JSON', parseHeartbeat('{nope') === null)
  check('parseHeartbeat rejects a missing running flag', parseHeartbeat('{"at":1}') === null)
  check('parseHeartbeat rejects a non-numeric at', parseHeartbeat('{"running":true,"at":"x"}') === null)
  check('parseHeartbeat rejects an array', parseHeartbeat('[1,2]') === null)
  check('parseHeartbeat rejects a non-string', parseHeartbeat(undefined) === null)

  // ---- the heartbeat file --------------------------------------------------
  // Times are explicit: the reader caches for HEARTBEAT_CACHE_MS (2 s), including
  // a "no file" answer, so a test that wants a re-read must step past the cache.
  const tracker = createPetTracker({ heartbeatPath })
  check('the default heartbeat lives in the temp directory', defaultHeartbeatPath().startsWith(tmpdir()))
  check('a missing heartbeat is unknown, not false', observeDshRunning(tracker, NOW) === undefined)

  beat(heartbeatPath, true, NOW)
  check('a fresh "running" beat is true', observeDshRunning(tracker, NOW + 2_100) === true)

  // within the cache window the file is not re-read at all
  beat(heartbeatPath, false, NOW + 2_200)
  check('the answer is cached for HEARTBEAT_CACHE_MS', observeDshRunning(tracker, NOW + 2_500) === true)
  check('past the cache the file is read again', observeDshRunning(tracker, NOW + 5_000) === false)
  check('a stale beat is unknown again', observeDshRunning(tracker, NOW + 60_000) === undefined)

  // ---- noteEvents / lastEventAt -------------------------------------------
  const fired = createPetTracker({ heartbeatPath })
  beat(heartbeatPath, true, NOW)
  check('no events yet means lastEventAt is null', fired.lastEventAt === null)
  computePet(fired, { at: NOW, agents: [], jobs: [] }, NOW, [{ session: {}, sample: { at: NOW - 3_000 } }])
  check('an emitted event sets lastEventAt', fired.lastEventAt === NOW - 3_000)
  computePet(fired, { at: NOW, agents: [], jobs: [] }, NOW, [{ session: {}, sample: { at: NOW - 9_000 } }])
  check('an older event does not move the clock back', fired.lastEventAt === NOW - 3_000)
  computePet(fired, { at: NOW, agents: [], jobs: [] }, NOW, [])
  check('a poll with no events keeps the clock', fired.lastEventAt === NOW - 3_000)

  // ---- computePet is exactly computeState ---------------------------------
  /** @type {[string, { dshRunning: boolean | undefined, snapshot: any }][]} */
  const observations = [
    ['offline wins over a snapshot full of work', { dshRunning: false, snapshot: { at: NOW, peakNow: false, agents: [{ state: 'running' }], jobs: [{}] } }],
    ['team for two running agents', { dshRunning: true, snapshot: { at: NOW, peakNow: false, agents: [{ state: 'running' }, { state: 'running' }], jobs: [] } }],
    ['busy for one job', { dshRunning: true, snapshot: { at: NOW, peakNow: false, agents: [], jobs: [{ program: 'pwsh' }] } }],
    ['idle when nothing happens', { dshRunning: true, snapshot: { at: NOW, peakNow: false, agents: [], jobs: [] } }],
    ['stale when the frame is old', { dshRunning: true, snapshot: { at: NOW - 120_000, peakNow: false, agents: [], jobs: [] } }],
    ['peak when only the price band is interesting', { dshRunning: true, snapshot: { at: NOW, peakNow: true, agents: [], jobs: [] } }],
    ['unknown dshRunning with no snapshot is stale', { dshRunning: undefined, snapshot: null }],
  ]
  for (const [label, observation] of observations) {
    if (observation.dshRunning === undefined) rmSync(heartbeatPath, { force: true })
    else beat(heartbeatPath, observation.dshRunning, NOW)
    const track = createPetTracker({ heartbeatPath })
    const expected = computeState({ snapshot: observation.snapshot, lastEventAt: null, dshRunning: observation.dshRunning, now: NOW })
    const actual = computePet(track, observation.snapshot, NOW, [])
    check(`${label} -> ${expected.state}`, actual.state === expected.state, JSON.stringify(actual))
    check(`${label}: identical to computeState()`, JSON.stringify(actual) === JSON.stringify(expected))
  }

  // the event clock is what turns a quiet poll into 想事情 (task-7 category)
  beat(heartbeatPath, true, NOW)
  const working = createPetTracker({ heartbeatPath })
  const withEvent = computePet(working, { at: NOW, peakNow: false, agents: [], jobs: [] }, NOW, [{ session: {}, sample: { at: NOW - 2_000 } }])
  check('a fresh event reads as thinking', withEvent.state === 'thinking' && withEvent.color === '#A5D6FF', JSON.stringify(withEvent))

  // ---- writePetState -------------------------------------------------------
  const written = writePetState({ state: 'idle', label: '空闲', color: '#9DA7B3', detail: '', pose: 'idle', reason: 'r', source: 'snapshot' }, statePath)
  check('writePetState reports success', written.ok === true, JSON.stringify(written))
  const roundTrip = JSON.parse(readFileSync(statePath, 'utf8'))
  check('the published file parses back', roundTrip.state === 'idle' && roundTrip.color === '#9DA7B3')
  check('no .tmp file is left behind (rename, not write-in-place)', readdirSync(dir).filter((name) => name.includes('.tmp')).length === 0)

  const nested = writePetState({ state: 'idle' }, join(dir, 'nested', 'deep', 'state.json'))
  check('a missing directory is created', nested.ok === true && existsSync(join(dir, 'nested', 'deep', 'state.json')), JSON.stringify(nested))

  // a file where a directory is needed: the publish must report, not throw
  const blocker = join(dir, 'blocker')
  writeFileSync(blocker, 'not a directory')
  const unwritable = writePetState({ state: 'idle' }, join(blocker, 'state.json'))
  check('an unwritable target degrades to ok:false', unwritable.ok === false && typeof unwritable.error === 'string', JSON.stringify(unwritable))
} finally {
  rmSync(dir, { recursive: true, force: true })
}

console.log('')
console.log(`${checks} checks, ${failures} failed`)
console.log(failures === 0 ? 'OK' : 'FAILED')
process.exitCode = failures === 0 ? 0 : 1
