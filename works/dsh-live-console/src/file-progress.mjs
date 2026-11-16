/**
 * Progress written to a file instead of stdout.
 *
 * A very common shape for long simulations is `python run.py > run.log` (or
 * `-OutFile out.txt`). The harness's job ring then carries no progress at all,
 * yet the file the command writes usually does. This module extracts candidate
 * progress files from a command line; the plugin reads their tails and feeds the
 * same explicit-progress parser used for stdout.
 *
 * Extraction is deliberately conservative: redirections and explicit
 * output-file options only, no shell expansion, and terminal sinks are ignored.
 * A missed file only costs an activity bar; a wrong file is re-checked cheaply.
 *
 * @module dsh-live-console/file-progress
 */

import { open, stat } from 'node:fs/promises'

/** Targets that never carry progress. */
const IGNORED_TARGETS = new Set([
  '/dev/null',
  '/dev/stdout',
  '/dev/stderr',
  'nul',
  '$null',
  'con',
])

/** How much of the tail to read from a progress file. */
const TAIL_BYTES = 64 * 1024

/**
 * Normalise one extracted path: strip quotes, reject empty/ignored/expansion forms.
 * @param {string | undefined} value - raw capture.
 * @returns {string | undefined} a usable path.
 */
function cleanTarget(value) {
  if (typeof value !== 'string') return undefined
  const text = value.trim().replace(/^["']|["']$/g, '')
  if (text.length === 0) return undefined
  if (IGNORED_TARGETS.has(text.toLowerCase())) return undefined
  if (text.startsWith('$') || text.startsWith('%')) return undefined
  if (text.includes('&') || text.includes('|')) return undefined
  return text
}

/**
 * Extract candidate progress-file paths from a command label.
 *
 * Recognises POSIX/bash redirections (`> f`, `>> f`, `2> f`, `*>`), `tee`, and
 * the common explicit-output options (`--output`, `-o`, `-OutFile`, `-Out`).
 *
 * @param {string} label - the job's command line.
 * @returns {string[]} unique candidate paths, in priority order.
 */
export function extractProgressTargets(label) {
  if (typeof label !== 'string' || label.length === 0) return []
  /** @type {string[]} */
  const targets = []

  const redirects = /(?:^|[^0-9&|])(?:1?>>?|2>>?|&>>?|\*>>?)\s*(?:"([^"]+)"|'([^']+)'|([^\s|;&<>]+))/g
  for (const match of label.matchAll(redirects)) {
    const target = cleanTarget(match[1] ?? match[2] ?? match[3])
    if (target !== undefined) targets.push(target)
  }

  const tee = /\|\s*tee\s+(?:-a\s+)?(?:"([^"]+)"|'([^']+)'|([^\s|;&<>]+))/g
  for (const match of label.matchAll(tee)) {
    const target = cleanTarget(match[1] ?? match[2] ?? match[3])
    if (target !== undefined) targets.push(target)
  }

  const options = [
    /--output(?:=|\s+)(?:"([^"]+)"|'([^']+)'|(\S+))/g,
    /-OutFile\s+(?:"([^"]+)"|'([^']+)'|(\S+))/gi,
    /(?:^|\s)-Out\s+(?:"([^"]+)"|'([^']+)'|(\S+))/g,
    /(?:^|\s)-o(?:=|\s+)(?:"([^"]+)"|'([^']+)'|(\S+))/g,
  ]
  for (const pattern of options) {
    for (const match of label.matchAll(pattern)) {
      const target = cleanTarget(match[1] ?? match[2] ?? match[3])
      if (target !== undefined) targets.push(target)
    }
  }

  return [...new Set(targets)].slice(0, 4)
}

/**
 * Read the tail of one file, returning an empty string when it is missing, empty,
 * unreadable, or not a regular file. Never throws.
 *
 * @param {string} path - absolute path.
 * @param {number} [maxBytes] - tail budget.
 * @returns {Promise<string>} the decoded tail, or ''.
 */
export async function readFileTail(path, maxBytes = TAIL_BYTES) {
  try {
    const info = await stat(path)
    if (!info.isFile() || info.size <= 0) return ''
    const length = Math.min(info.size, maxBytes)
    const handle = await open(path, 'r')
    try {
      const buffer = Buffer.alloc(length)
      await handle.read(buffer, 0, length, info.size - length)
      return buffer.toString('utf8')
    } finally {
      await handle.close()
    }
  } catch {
    return ''
  }
}
