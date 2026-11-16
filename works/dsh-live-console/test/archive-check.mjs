/**
 * Lossless context-archive checks: exact bytes, manifest hashes, tar/gzip round-trip.
 *
 *   node test/archive-check.mjs
 */

import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { gunzipSync, zstdCompressSync } from 'node:zlib'

import { buildContextArchive, CONTEXT_ARCHIVE_FORMAT, extractTarEntries } from '../src/context-archive.mjs'

let passed = 0
function ok(label) {
  passed += 1
  console.log(`ok    ${label}`)
}

const home = await mkdtemp(join(tmpdir(), 'dsh-context-archive-'))
try {
  const sessionId = 'session-archive-fixture'
  const sessionDir = join(home, 'sessions', '--F-ws--', sessionId)
  await mkdir(sessionDir, { recursive: true })
  const lines = [
    JSON.stringify({ type: 'session', version: 4, id: sessionId, createdAt: 1, cwd: 'F:\\ws', origin: 'user' }),
    JSON.stringify({ type: 'user/message', seq: 1, time: 2, data: { content: [{ type: 'text', text: '你好' }] } }),
    JSON.stringify({ type: 'assistant/message', seq: 2, time: 3, data: { message: { content: [{ type: 'text', text: '你好，有什么可以帮你？' }] } } }),
  ]
  const original = zstdCompressSync(Buffer.from(`${lines.join('\n')}\n`, 'utf8'))
  await writeFile(join(sessionDir, 'session.v4.jsonl.zstd'), original)

  const archive = await buildContextArchive({ home })
  assert.ok(archive.buffer.length > 0)
  assert.match(archive.filename, /\.tar\.gz$/)
  assert.equal(archive.stats.sessions, 1)
  ok('the archive builds one session and uses a .tar.gz name')

  const tar = gunzipSync(archive.buffer)
  const files = extractTarEntries(tar)
  assert.ok(files.has('manifest.json'))
  assert.ok(files.has('README.txt'))
  const manifest = JSON.parse(files.get('manifest.json').toString('utf8'))
  assert.equal(manifest.format, CONTEXT_ARCHIVE_FORMAT)
  assert.equal(manifest.sessionCount, 1)
  assert.equal(manifest.sessions[0].id, sessionId)
  ok('the manifest and README are inside the archive')

  const archived = files.get(manifest.sessions[0].archivePath)
  assert.ok(archived !== undefined)
  assert.equal(archived.equals(original), true)
  assert.equal(createHash('sha256').update(archived).digest('hex'), manifest.sessions[0].sha256)
  ok('the original session file is archived byte-for-byte and its SHA-256 matches')

  assert.equal(manifest.failures.length, 0)
  assert.equal(archive.stats.compressedBytes, archive.buffer.length)
  ok('no sessions are skipped or truncated')
} finally {
  await rm(home, { recursive: true, force: true })
}

console.log('')
console.log(`all archive checks passed (${passed} assertions)`)
