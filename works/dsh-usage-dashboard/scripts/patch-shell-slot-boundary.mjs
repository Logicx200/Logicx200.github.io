/**
 * Patch the packaged application's own slot error boundaries, so that a slot
 * *assembly* error is contained like any other slot failure instead of tearing
 * down the enclosing region.
 *
 * Why this exists
 * ---------------
 * `app.asar` contains two React error boundaries that guard slot entries:
 *
 *     var SlotErrorBoundary = class extends react.Component {
 *       static getDerivedStateFromError(error) {
 *         if (error instanceof SlotAssemblyError) throw error;
 *         return { failed: true };
 *       }
 *
 * and `FactoryErrorBoundary` with the same body. The throw is deliberate — an
 * assembly error means the slot system itself was used wrongly, so it is pushed
 * past every boundary — but it also means one missing scope binding unmounts the
 * whole enclosing region: the conversation panel and the session-scoped sidebar
 * both go blank, on a path the user reaches just by creating a new session, and
 * the packaged desktop build has no reload shortcut to escape it.
 *
 * The patch replaces the throw with an empty statement, so execution falls
 * through to the `return { failed: true };` that already follows. The failure is
 * then contained: one slot shows its crash face, everything around it renders.
 *
 * Both strings are exactly the same length, so the archive is edited in place
 * byte-for-byte and its structure (offsets, header, integrity fields) is
 * untouched. Electron's `EnableEmbeddedAsarIntegrityValidation` fuse is disabled
 * in this build, so an in-place edit does not fail startup — that was checked
 * before this script was written, and `--check` re-reports it.
 *
 * Usage
 * -----
 *   node scripts/patch-shell-slot-boundary.mjs --check     report only
 *   node scripts/patch-shell-slot-boundary.mjs             patch (backs up first)
 *   node scripts/patch-shell-slot-boundary.mjs --revert    restore the original
 *
 * @module dsh-usage-dashboard/scripts/patch-shell-slot-boundary
 */

import { closeSync, copyFileSync, openSync, readFileSync, statSync, writeSync } from 'node:fs'

/** The default install path on this machine. */
const DEFAULT_APP = 'D:\\DeepSeek Harness\\resources\\app.asar'

/** What the shell ships. */
const ORIGINAL = 'if (error instanceof SlotAssemblyError) throw error;'

/** What this patch writes: same byte length, no throw, falls through to the return. */
const PATCHED = 'if (error instanceof SlotAssemblyError) /*caught*/ ;'

if (ORIGINAL.length !== PATCHED.length) {
  throw new Error(`patch strings differ in length: ${ORIGINAL.length} vs ${PATCHED.length}`)
}

const argv = process.argv.slice(2)
const checkOnly = argv.includes('--check')
const revert = argv.includes('--revert')
const appIndex = argv.indexOf('--app')
const appPath = appIndex >= 0 ? argv[appIndex + 1] : DEFAULT_APP

/** Count non-overlapping occurrences of `needle` in `haystack`. */
function countOccurrences(haystack, needle) {
  const offsets = []
  let from = 0
  for (;;) {
    const at = haystack.indexOf(needle, from)
    if (at < 0) break
    offsets.push(at)
    from = at + needle.length
  }
  return offsets
}

const before = statSync(appPath)
console.log(`app.asar  ${appPath}`)
console.log(`size      ${before.size} bytes`)
console.log(`modified  ${before.mtime.toISOString()}`)

const buffer = readFileSync(appPath)
const originals = countOccurrences(buffer, Buffer.from(ORIGINAL, 'ascii'))
const patched = countOccurrences(buffer, Buffer.from(PATCHED, 'ascii'))

console.log('')
console.log(`original boundary lines found : ${originals.length}  ${originals.map((o) => '0x' + o.toString(16)).join(' ')}`)
console.log(`patched  boundary lines found : ${patched.length}`)

if (checkOnly) {
  console.log('')
  console.log(patched.length > 0 && originals.length === 0 ? 'STATE patched' : originals.length > 0 ? 'STATE original' : 'STATE unrecognised')
  process.exit(0)
}

const from = revert ? PATCHED : ORIGINAL
const to = revert ? ORIGINAL : PATCHED
const offsets = revert ? patched : originals

if (offsets.length === 0) {
  console.log('')
  console.log(`nothing to do: no ${revert ? 'patched' : 'original'} boundary line is present`)
  process.exit(0)
}

if (!revert) {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const backup = `${appPath}.bak-${stamp}`
  console.log('')
  console.log(`backing up to ${backup}`)
  copyFileSync(appPath, backup)
}

const handle = openSync(appPath, 'r+')
try {
  const replacement = Buffer.from(to, 'ascii')
  for (const offset of offsets) {
    writeSync(handle, replacement, 0, replacement.length, offset)
    console.log(`  wrote ${replacement.length} bytes at 0x${offset.toString(16)}`)
  }
} finally {
  closeSync(handle)
}

const after = readFileSync(appPath)
console.log('')
console.log(`verified: original left = ${countOccurrences(after, Buffer.from(ORIGINAL, 'ascii')).length}, patched now = ${countOccurrences(after, Buffer.from(PATCHED, 'ascii')).length}`)
console.log(`size unchanged: ${after.length === buffer.length}`)
console.log(revert ? 'REVERTED' : 'PATCHED')
