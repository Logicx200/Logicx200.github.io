/**
 * Offline checks for the live console progress engine.
 *
 * Run with the Node runtime that ships with Harness (or any recent Node):
 *   node test/progress-check.mjs
 */

import assert from 'node:assert/strict'

import {
  ESTIMATE_CAP,
  ProgressHistory,
  deriveEta,
  median,
  progressFromLine,
  progressFromText,
  signatureOf,
  stripAnsi,
} from '../src/progress.mjs'
import { extractProgressTargets } from '../src/file-progress.mjs'

let passed = 0
/** @param {string} label */
function ok(label) {
  passed += 1
  console.log(`ok    ${label}`)
}

// ── stripAnsi ───────────────────────────────────────────────────────────────
assert.equal(stripAnsi('\u001b[31mred\u001b[0m plain'), 'red plain')
ok('stripAnsi removes SGR colour codes')

assert.equal(stripAnsi('10%\r20%\r30%'), '10%\n20%\n30%')
ok('stripAnsi turns carriage-return rewrites into lines')

assert.equal(stripAnsi(123), '')
ok('stripAnsi tolerates non-strings')

// ── progressFromLine ────────────────────────────────────────────────────────
assert.deepEqual(progressFromLine('training 47.5% done'), { percent: 47.5, kind: 'percent', evidence: 'training 47.5% done' })
ok('percent with a unit parses')

assert.deepEqual(progressFromLine('step 120/500'), { percent: 24, kind: 'ratio', evidence: 'step 120/500' })
ok('word-anchored ratio parses')

assert.deepEqual(progressFromLine('frame 30 of 240'), { percent: 12.5, kind: 'ratio', evidence: 'frame 30 of 240' })
ok('N of M ratio parses')

assert.deepEqual(progressFromLine('[progress 3/10]'), { percent: 30, kind: 'ratio', evidence: '[progress 3/10]' })
ok('explicit [progress 3/10] convention parses')

assert.deepEqual(progressFromLine('[progress 42%]'), { percent: 42, kind: 'percent', evidence: '[progress 42%]' })
ok('explicit [progress 42%] convention parses')

assert.deepEqual(progressFromLine('progress: step 2 of 5'), { percent: 40, kind: 'ratio', evidence: 'progress: step 2 of 5' })
ok('tagged "progress: step N of M" parses')

assert.equal(progressFromLine('no numbers here'), undefined)
ok('a line without numbers yields nothing')

assert.equal(progressFromLine('123% complete'), undefined)
ok('percent above 100 is rejected')

assert.equal(progressFromLine('step 9/3'), undefined)
ok('ratio above its total is rejected')

assert.equal(progressFromLine('step 3/0'), undefined)
ok('zero denominator is rejected')

assert.equal(progressFromLine('3/1000000000000000'), undefined)
ok('absurd totals are rejected')

// Last figure on a line wins.
assert.equal(progressFromLine('step 3/4 done 75%').percent, 75)
ok('the last percentage on a line wins')

// ── progressFromText ────────────────────────────────────────────────────────
const text = 'booting\nstep 1/10\nnoise\nstep 3/10\nplain tail\n'
assert.equal(progressFromText(text).percent, 30)
ok('the last progress line in a tail wins')

assert.equal(progressFromText(''), undefined)
ok('empty tail yields nothing')

// ── median / signature / eta ────────────────────────────────────────────────
assert.equal(median([3, 1, 2]), 2)
assert.equal(median([4, 1, 3, 2]), 2.5)
assert.equal(median([]), undefined)
ok('median handles odd, even, and empty inputs')

assert.equal(signatureOf('bash', '  python   sim.py  '), signatureOf('bash', 'python sim.py'))
ok('signature normalises whitespace')
assert.notEqual(signatureOf('bash', 'a'), signatureOf('pwsh', 'a'))
ok('signature includes the job kind')

const eta = deriveEta([{ at: 0, percent: 20 }, { at: 1000, percent: 40 }])
assert.equal(eta, 3000)
ok('ETA from two explicit samples is remaining/rate')

assert.equal(deriveEta([{ at: 0, percent: 40 }, { at: 1000, percent: 40 }]), undefined)
ok('a stalled rate yields no ETA')
assert.equal(deriveEta([{ at: 0, percent: 40 }]), undefined)
ok('one sample yields no ETA')

// ── ProgressHistory ─────────────────────────────────────────────────────────
const history = new ProgressHistory({ now: () => 1_000 })
history.record('k\u0000cmd', { ms: 10_000, bytes: 2_000, lines: 100 })
assert.equal(history.entries.size, 1)
ok('history records a completed run')

const timeEstimate = history.estimate('k\u0000cmd', { elapsedMs: 5_000, bytes: 100 })
assert.equal(timeEstimate.source, 'estimate-time')
assert.equal(Math.round(timeEstimate.percent), 50)
assert.equal(timeEstimate.etaMs, 5_000)
ok('history estimates from elapsed time')

const outputEstimate = history.estimate('k\u0000cmd', { elapsedMs: 1_000, bytes: 1_500 })
assert.equal(outputEstimate.source, 'estimate-output')
assert.equal(outputEstimate.percent, 75)
ok('history estimates from output size when it leads')

assert.equal(history.estimate('k\u0000unknown', { elapsedMs: 1_000, bytes: 500 }), undefined)
ok('unknown command has no estimate')

history.record('k\u0000cmd', { ms: 40_000, bytes: 8_000, lines: 200 })
const capped = history.estimate('k\u0000cmd', { elapsedMs: 100_000, bytes: 100_000 })
assert.ok(capped.percent <= ESTIMATE_CAP)
ok('estimate never claims completion')

const reloaded = new ProgressHistory({ now: () => 1_000 })
reloaded.load({ version: 1, entries: { 'k\u0000cmd': { samples: [{ ms: 4_000, bytes: 1_000, lines: 20 }], lastAt: 500 } } })
assert.equal(reloaded.entries.size, 1)
ok('history reloads persisted entries')

const disabled = new ProgressHistory({ enabled: false })
disabled.record('x', { ms: 1_000, bytes: 10, lines: 1 })
assert.equal(disabled.entries.size, 0)
ok('disabled history records nothing')

// ── redirected output files ─────────────────────────────────────────────────
assert.deepEqual(extractProgressTargets('python sim.py > run.log'), ['run.log'])
assert.deepEqual(extractProgressTargets('python sim.py >> "out dir/run.log" 2>&1'), ['out dir/run.log'])
assert.deepEqual(extractProgressTargets('ffmpeg -i in.mp4 -o out.mp4'), ['out.mp4'])
assert.deepEqual(extractProgressTargets('python sim.py > /dev/null'), [])
assert.deepEqual(extractProgressTargets('cmd.exe -OutFile "C:\\x\\out.txt"'), ['C:\\x\\out.txt'])
assert.deepEqual(extractProgressTargets('node test.js | tee test.log'), ['test.log'])
assert.deepEqual(extractProgressTargets('echo hi'), [])
ok('redirected output files are extracted for progress tailing')

console.log('')
console.log(`all progress checks passed (${passed} assertions)`)
