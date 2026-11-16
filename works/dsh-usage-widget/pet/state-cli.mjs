#!/usr/bin/env node
/**
 * Run the real engine once and print the pet state it implies.
 *
 * A human-readable reality check for `state.mjs`: it spawns
 * `node engine/cli.mjs --once` (exactly the way the panel does, one poll),
 * collects the NDJSON, builds the observation the integration would build, and
 * prints the state line. It is a *verification* tool, not part of the render
 * path — the widget calls `computeState` directly.
 *
 * Usage:
 *   node pet\state-cli.mjs                 # one compact line
 *   node pet\state-cli.mjs --json          # raw observation + result + stream facts
 *   node pet\state-cli.mjs --detail        # the compact line plus the raw snapshot summary
 *   node pet\state-cli.mjs --config <path> # forwarded to the engine
 *
 * Two Windows traps this tool exists to avoid:
 *   - Chinese paths passed to a Node subprocess get mangled through the legacy
 *     code page, so the child is always spawned from an **ASCII working
 *     directory** (`--cwd` overrides it) and every path argument is absolute.
 *   - The engine's own import graph is resolved from its file path, not the
 *     child's cwd, so running it from a temp directory is safe.
 *
 * Nothing here reads or writes the widget's files; the engine's own stdout is
 * the only input. The panel running concurrently is unaffected.
 *
 * @module dsh-usage-widget/pet/state-cli
 */

import { execFile } from 'node:child_process'
import { accessSync, constants, statSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { computeState } from './state.mjs'

/** This file's directory: `…/dsh-usage-widget/pet`. */
const PET_DIR = dirname(fileURLToPath(import.meta.url))

/** The widget root: `…/dsh-usage-widget`. */
const ROOT_DIR = resolve(PET_DIR, '..')

/** The streaming engine's entry point. */
const ENGINE = join(ROOT_DIR, 'engine', 'cli.mjs')

/** The widget's config, passed explicitly so the child never guesses. */
const CONFIG = join(ROOT_DIR, 'config.json')

/**
 * Candidate working directories for the child, ASCII only.
 *
 * `os.tmpdir()` is the primary: it is ASCII on a normal Windows install, it
 * exists, and it has no relationship to the Chinese project path. The
 * fallbacks cover a machine whose TEMP itself contains non-ASCII characters.
 *
 * @returns {string[]} absolute, existing, ASCII-only directories.
 */
export function asciiCandidates() {
  const candidates = [process.env.TEMP, process.env.TMP, tmpdir(), 'C:\\Windows\\Temp', process.cwd()]
  const usable = []
  for (const candidate of candidates) {
    if (typeof candidate !== 'string' || candidate.length === 0) continue
    if (!/^[\x20-\x7E]+$/.test(candidate)) continue
    if (!isAbsolute(candidate)) continue
    try {
      if (!statSync(candidate).isDirectory()) continue
      accessSync(candidate, constants.W_OK)
    } catch {
      continue
    }
    if (!usable.includes(candidate)) usable.push(candidate)
  }
  return usable
}

/**
 * Pick the child's working directory, honouring an explicit override.
 *
 * @param {string | undefined} override - `--cwd` value.
 * @returns {string} an absolute ASCII directory.
 */
export function resolveChildCwd(override) {
  if (typeof override === 'string' && override.length > 0) {
    if (!isAbsolute(override)) throw new Error(`--cwd must be absolute, got ${override}`)
    return override
  }
  const candidates = asciiCandidates()
  if (candidates.length === 0) {
    throw new Error(
      'no ASCII working directory found (checked TEMP/TMP/os.tmpdir()/C:\\Windows\\Temp); pass --cwd <ascii dir>',
    )
  }
  return candidates[0]
}

/**
 * Parse the command line.
 * @param {string[]} argv - arguments after the script.
 * @returns {{ json: boolean, detail: boolean, config: string | undefined, cwd: string | undefined, help: boolean }} options.
 */
export function parseArgs(argv) {
  /** @type {any} */
  const options = { json: false, detail: false, config: undefined, cwd: undefined, help: false }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--json') options.json = true
    else if (arg === '--detail') options.detail = true
    else if (arg === '--help' || arg === '-h') options.help = true
    else if (arg === '--config') {
      const next = argv[index + 1]
      if (next !== undefined && !next.startsWith('--')) {
        options.config = next
        index += 1
      }
    } else if (arg === '--cwd') {
      const next = argv[index + 1]
      if (next !== undefined && !next.startsWith('--')) {
        options.cwd = next
        index += 1
      }
    }
  }
  return options
}

/**
 * Spawn the engine once and return its stdout lines.
 *
 * @param {{ cwd: string, configPath: string }} options - child cwd (ASCII) and config path.
 * @returns {Promise<{ code: number | null, stdout: string, stderr: string, error: string | undefined }>}
 */
export function runEngineOnce(options) {
  return new Promise((settle) => {
    execFile(
      process.execPath,
      [ENGINE, '--once', '--config', options.configPath],
      {
        cwd: options.cwd,
        windowsHide: true,
        maxBuffer: 8 * 1024 * 1024,
        timeout: 120_000,
        env: { ...process.env, DSH_HOME: process.env.DSH_HOME || join(homedir(), '.dsh') },
      },
      (error, stdout, stderr) => {
        settle({
          code: error === null ? 0 : typeof error.code === 'number' ? error.code : 1,
          stdout: typeof stdout === 'string' ? stdout : '',
          stderr: typeof stderr === 'string' ? stderr : '',
          error: error === null ? undefined : error.message,
        })
      },
    )
  })
}

/**
 * Fold an engine stream into the observation `computeState` needs.
 *
 * The one-poll (`--once`) run has no stream history, so `lastEventAt` is only
 * ever set by an `event` line that happens to be in this run. That is the honest
 * answer for a cold poll: "working" needs a *recent* event, and no event has
 * been seen yet.
 *
 * @param {string} stdout - the engine's NDJSON.
 * @returns {{
 *   observation: { snapshot: any, lastEventAt: number | null, dshRunning: true, now: number },
 *   facts: { ready: any, snapshot: any, events: number, lastEventAt: number | null, errors: string[], unparsed: number, at: number | null },
 * }} the observation and a summary of what the stream contained.
 * @throws {Error} when no snapshot line was produced.
 */
export function foldEngineStream(stdout) {
  let ready = null
  let snapshot = null
  let lastEventAt = null
  let events = 0
  /** @type {string[]} */
  const errors = []
  let unparsed = 0

  for (const line of stdout.split(/\r?\n/)) {
    const text = line.trim()
    if (text.length === 0) continue
    let message
    try {
      message = JSON.parse(text)
    } catch {
      unparsed += 1
      continue
    }
    if (message === null || typeof message !== 'object') {
      unparsed += 1
      continue
    }
    if (message.type === 'ready') ready = message
    else if (message.type === 'snapshot') snapshot = message
    else if (message.type === 'event') {
      events += 1
      if (typeof message.at === 'number' && Number.isFinite(message.at)) {
        if (lastEventAt === null || message.at > lastEventAt) lastEventAt = message.at
      }
    } else if (message.type === 'error') {
      errors.push(typeof message.message === 'string' ? message.message : JSON.stringify(message))
    } else {
      unparsed += 1
    }
  }

  if (snapshot === null) {
    throw new Error(`engine produced no snapshot line (${errors.length} error line(s): ${errors.join('; ') || 'none'})`)
  }

  const at = typeof snapshot.at === 'number' && Number.isFinite(snapshot.at) ? snapshot.at : null
  return {
    observation: { snapshot, lastEventAt, dshRunning: true, now: at ?? 0 },
    facts: { ready, snapshot, events, lastEventAt, errors, unparsed, at },
  }
}

/**
 * The widget's own job-progress string, reused for the human line.
 * @param {any} snapshot - the snapshot.
 * @returns {string} the one-line source description.
 */
export function describeSource(snapshot) {
  const jobs = Array.isArray(snapshot?.jobs) ? snapshot.jobs.length : 0
  const agents = Array.isArray(snapshot?.agents) ? snapshot.agents.length : 0
  const source = typeof snapshot?.jobsSource === 'string' ? snapshot.jobsSource : 'unknown'
  return `jobs=${jobs} (source=${source}), agents=${agents}`
}

/**
 * Entry point.
 * @returns {Promise<void>}
 */
async function main() {
  const options = parseArgs(process.argv.slice(2))
  if (options.help) {
    console.log('usage: node pet\\state-cli.mjs [--json] [--detail] [--config <path>] [--cwd <ascii dir>]')
    console.log('  runs `node engine\\cli.mjs --once` from an ASCII working directory and prints the pet state')
    return
  }

  const cwd = resolveChildCwd(options.cwd)
  const configPath = options.config === undefined ? CONFIG : isAbsolute(options.config) ? options.config : resolve(process.cwd(), options.config)

  if (!options.json) {
    console.log(`engine   ${ENGINE}`)
    console.log(`cwd      ${cwd}  (ASCII; avoids the Chinese-path subprocess trap)`)
    console.log(`config   ${configPath}`)
  }

  const run = await runEngineOnce({ cwd, configPath })
  if (run.stdout.trim().length === 0) {
    const reason = run.error ?? run.stderr.trim() ?? 'no stdout'
    throw new Error(`engine produced no output (exit ${run.code}): ${reason}`)
  }

  const { observation, facts } = foldEngineStream(run.stdout)
  const result = computeState(observation)
  const seenAt = facts.at ?? observation.now

  if (options.json) {
    console.log(
      JSON.stringify(
        {
          cwd,
          configPath,
          engineExit: run.code,
          stream: {
            ready: facts.ready,
            events: facts.events,
            lastEventAt: facts.lastEventAt,
            errors: facts.errors,
            unparsed: facts.unparsed,
            snapshotAt: facts.at,
            jobsSource: facts.snapshot?.jobsSource ?? null,
            jobs: Array.isArray(facts.snapshot?.jobs) ? facts.snapshot.jobs.length : 0,
            agents: Array.isArray(facts.snapshot?.agents) ? facts.snapshot.agents.length : 0,
            peakNow: facts.snapshot?.peakNow === true,
          },
          observation: {
            snapshot: facts.snapshot,
            lastEventAt: observation.lastEventAt,
            dshRunning: observation.dshRunning,
            now: observation.now,
          },
          result,
        },
        null,
        2,
      ),
    )
    return
  }

  const age = observation.now - seenAt
  const ageText = age === 0 ? 'fresh' : `${Math.round(age / 1000)}s old`
  console.log('')
  console.log(`state    ${result.state}`)
  console.log(`label    ${result.label}  ${result.color}  pose=${result.pose}`)
  console.log(`detail   ${result.detail.length > 0 ? result.detail : '(none)'}`)
  console.log(`why      ${result.reason}`)
  console.log(`source   ${result.source} · ${describeSource(facts.snapshot)} · snapshot ${ageText} · events this run=${facts.events}`)
  if (facts.errors.length > 0) console.log(`errors   ${facts.errors.join(' | ')}`)
  if (run.stderr.trim().length > 0) console.log(`stderr   ${run.stderr.trim().split(/\r?\n/)[0]}`)
  if (options.detail) {
    console.log('')
    console.log('snapshot summary')
    const snapshot = facts.snapshot ?? {}
    console.log(`  at=${snapshot.at} peakNow=${snapshot.peakNow} jobsSource=${snapshot.jobsSource}`)
    for (const job of Array.isArray(snapshot.jobs) ? snapshot.jobs : []) {
      console.log(`  job ${job.program} ${job.command} progress=${JSON.stringify(job.progress)} note=${job.progressNote ?? ''}`)
    }
    for (const agent of Array.isArray(snapshot.agents) ? snapshot.agents : []) {
      console.log(`  agent ${agent.state} "${agent.label}" elapsedMs=${agent.elapsedMs} sinceLastWriteMs=${agent.sinceLastWriteMs}`)
    }
    console.log(`  today calls=${snapshot.today?.calls} costCny=${snapshot.today?.costCny}`)
  }
}

const invokedDirectly =
  process.argv[1] !== undefined && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))

if (invokedDirectly) {
  main().catch((error) => {
    console.error(`state-cli: ${error instanceof Error ? error.message : String(error)}`)
    process.exitCode = 1
  })
}
