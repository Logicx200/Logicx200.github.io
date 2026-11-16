/**
 * Lossless context archive for every durable DSH session.
 *
 * The archive is one `.tar.gz` containing:
 *
 *   manifest.json                 counts, per-file SHA-256, session headers
 *   README.txt                    extraction / inspection notes
 *   sessions/<workspace>/<session>/session.vN.jsonl.zstd
 *
 * The session files are copied byte-for-byte from `$DSH_HOME/sessions`; they are
 * never decoded, summarized, truncated, reordered, or re-encoded. The DSH log
 * format is itself lossless Zstandard-compressed JSONL, so the outer gzip only
 * packs the collection — the original context remains exactly recoverable.
 *
 * `extractTarEntries` is exported for tests and for anyone who wants to open the
 * archive without external tooling.
 *
 * @module dsh-live-console/context-archive
 */

import { createHash } from 'node:crypto'
import { readdir, readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { gzipSync, zstdDecompressSync } from 'node:zlib'

import { SESSION_ARTIFACT_PATTERN, chooseArtifact } from './usage/session-store.mjs'
import { scanZstdFrames } from './usage/zstd.mjs'

/** Archive format tag, embedded in the manifest. */
export const CONTEXT_ARCHIVE_FORMAT = 'dsh-live-console/context-archive-tar@1'

/** Gzip level for the outer container. Gzip is lossless at every level. */
const GZIP_LEVEL = 9

/**
 * Read the first JSONL line of a session artifact without decoding the full log.
 * @param {Buffer} raw - compressed artifact bytes.
 * @returns {object | undefined} parsed session header, when readable.
 */
function readHeader(raw) {
  try {
    const { frames } = scanZstdFrames(raw)
    const first = frames[0]
    if (first === undefined) return undefined
    const plain = zstdDecompressSync(raw.subarray(first.start, first.end)).toString('utf8')
    const line = plain.split('\n', 1)[0]
    const parsed = JSON.parse(line)
    return parsed !== null && typeof parsed === 'object' ? parsed : undefined
  } catch {
    return undefined
  }
}

/**
 * Build a POSIX ustar header block.
 * @param {string} name - archive path.
 * @param {number} size - file byte length.
 * @param {number} mtime - POSIX seconds.
 * @returns {Buffer} 512-byte header.
 */
function tarHeader(name, size, mtime) {
  const header = Buffer.alloc(512, 0)
  let pathField = name
  let prefixField = ''
  if (Buffer.byteLength(name, 'utf8') > 100) {
    const split = name.lastIndexOf('/', 99)
    if (split > 0) {
      prefixField = name.slice(0, split)
      pathField = name.slice(split + 1)
    }
  }
  header.write(pathField, 0, 100, 'utf8')
  header.write(prefixField, 345, 155, 'utf8')
  header.write('0000644\0', 100, 8, 'ascii')
  header.write('0000000\0', 108, 8, 'ascii')
  header.write('0000000\0', 116, 8, 'ascii')
  header.write(`${size.toString(8).padStart(11, '0')}\0`, 124, 12, 'ascii')
  header.write(`${Math.max(0, Math.floor(mtime)).toString(8).padStart(11, '0')}\0`, 136, 12, 'ascii')
  header.write('        ', 148, 8, 'ascii')
  header.write('0', 156, 1, 'ascii')
  header.write('ustar\0', 257, 6, 'ascii')
  header.write('00', 263, 2, 'ascii')
  header.write('root', 265, 32, 'ascii')
  header.write('root', 297, 32, 'ascii')
  header.write('0000000\0', 329, 8, 'ascii')
  header.write('0000000\0', 337, 8, 'ascii')
  let checksum = 0
  for (const byte of header) checksum += byte
  header.write(`${checksum.toString(8).padStart(6, '0')}\0 `, 148, 8, 'ascii')
  return header
}

/**
 * Build a tar buffer from file entries.
 * @param {{ name: string, data: Buffer, mtime: number }[]} entries - files.
 * @returns {Buffer} tar bytes.
 */
export function createTar(entries) {
  const blocks = []
  for (const entry of entries) {
    blocks.push(tarHeader(entry.name, entry.data.length, entry.mtime))
    blocks.push(entry.data)
    const padding = (512 - (entry.data.length % 512)) % 512
    if (padding > 0) blocks.push(Buffer.alloc(padding, 0))
  }
  blocks.push(Buffer.alloc(1024, 0))
  return Buffer.concat(blocks)
}

/**
 * Parse a tar buffer into a name -> bytes map (ustar, regular files only).
 * Exported so tests can prove the archive is exact.
 * @param {Buffer} buffer - tar bytes.
 * @returns {Map<string, Buffer>} archived files.
 */
export function extractTarEntries(buffer) {
  const files = new Map()
  let offset = 0
  while (offset + 512 <= buffer.length) {
    const header = buffer.subarray(offset, offset + 512)
    if (header.every((byte) => byte === 0)) break
    const name = header.toString('utf8', 0, 100).replace(/\0.*$/s, '')
    const prefix = header.toString('utf8', 345, 500).replace(/\0.*$/s, '')
    const fullName = prefix.length > 0 ? `${prefix}/${name}` : name
    const size = Number.parseInt(header.toString('ascii', 124, 136).replace(/\0.*$/s, '').trim() || '0', 8)
    const dataStart = offset + 512
    const dataEnd = dataStart + size
    if (!Number.isFinite(size) || dataEnd > buffer.length) break
    files.set(fullName, buffer.subarray(dataStart, dataEnd))
    offset = dataStart + Math.ceil(size / 512) * 512
  }
  return files
}

/**
 * Enumerate the highest-version artifact of every session.
 * @param {string} home - DSH home.
 * @returns {Promise<{ path: string, sessionId: string, workspace: string, artifact: string, mtimeMs: number }[]>}
 */
async function listArtifacts(home) {
  const sessionsRoot = join(home, 'sessions')
  /** @type {{ path: string, sessionId: string, workspace: string, artifact: string, mtimeMs: number }[]} */
  const artifacts = []
  let workspaces
  try {
    workspaces = await readdir(sessionsRoot, { withFileTypes: true })
  } catch (error) {
    if (error?.code === 'ENOENT') return artifacts
    throw error
  }
  for (const workspace of workspaces) {
    if (!workspace.isDirectory()) continue
    const workspaceDir = join(sessionsRoot, workspace.name)
    let sessions
    try {
      sessions = await readdir(workspaceDir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const session of sessions) {
      if (!session.isDirectory()) continue
      const sessionDir = join(workspaceDir, session.name)
      const entries = await readdir(sessionDir).catch(() => [])
      const chosen = chooseArtifact(entries)
      if (chosen === undefined || !SESSION_ARTIFACT_PATTERN.test(chosen.name)) continue
      const artifactPath = join(sessionDir, chosen.name)
      const info = await stat(artifactPath).catch(() => undefined)
      if (info === undefined) continue
      artifacts.push({
        path: artifactPath,
        sessionId: session.name,
        workspace: workspace.name,
        artifact: chosen.name,
        mtimeMs: info.mtimeMs,
      })
    }
  }
  artifacts.sort((left, right) => left.mtimeMs - right.mtimeMs || left.sessionId.localeCompare(right.sessionId))
  return artifacts
}

/**
 * Build the lossless `.tar.gz` context archive.
 * @param {{ home: string, maxSessions?: number }} options - archive options.
 * @returns {Promise<{
 *   buffer: Buffer,
 *   filename: string,
 *   manifest: any,
 *   stats: { sessions: number, files: number, uncompressedTarBytes: number, compressedBytes: number, elapsedMs: number },
 * }>}
 */
export async function buildContextArchive(options) {
  const started = Date.now()
  if (typeof options?.home !== 'string' || options.home.length === 0) {
    throw new Error('buildContextArchive: home is required')
  }
  const maxSessions = Number.isFinite(options.maxSessions) ? Number(options.maxSessions) : Infinity
  const artifacts = await listArtifacts(options.home)
  const selected = artifacts.slice(0, maxSessions)
  /** @type {{ name: string, data: Buffer, mtime: number }[]} */
  const entries = []
  const sessions = []
  const failures = []
  for (const artifact of selected) {
    try {
      const raw = await readFile(artifact.path)
      const header = readHeader(raw)
      const archivePath = `sessions/${artifact.workspace}/${artifact.sessionId}/${artifact.artifact}`
      entries.push({ name: archivePath, data: raw, mtime: Math.floor(artifact.mtimeMs / 1000) })
      sessions.push({
        id: artifact.sessionId,
        workspace: artifact.workspace,
        cwd: typeof header?.cwd === 'string' ? header.cwd : undefined,
        parentSession: typeof header?.parentSession === 'string' ? header.parentSession : undefined,
        origin: typeof header?.origin === 'string' ? header.origin : undefined,
        agentPreset: typeof header?.agentPreset === 'string' ? header.agentPreset : undefined,
        artifact: artifact.artifact,
        archivePath,
        byteLength: raw.length,
        sha256: createHash('sha256').update(raw).digest('hex'),
        mtime: new Date(artifact.mtimeMs).toISOString(),
      })
    } catch (error) {
      failures.push({ sessionId: artifact.sessionId, error: String(error) })
    }
  }
  const manifest = {
    format: CONTEXT_ARCHIVE_FORMAT,
    createdAt: new Date().toISOString(),
    compression: 'gzip',
    notes:
      'Session files are copied byte-for-byte from $DSH_HOME/sessions. Each session.v*.jsonl.zstd is a concatenated Zstandard-frame JSONL log; decompress with zstd or a compatible tool. Missing/torn final frames are left exactly as found.',
    sessionCount: sessions.length,
    artifacts: artifacts.length,
    skipped: artifacts.length - selected.length,
    failures,
    sessions,
  }
  const readme = [
    'DSH Live Console — lossless context archive',
    '',
    `Created: ${manifest.createdAt}`,
    `Sessions: ${manifest.sessionCount}`,
    '',
    'This archive contains the original DSH session log files, byte-for-byte,',
    'under sessions/<workspace>/<session>/session.vN.jsonl.zstd.',
    '',
    'Each session file is a sequence of Zstandard frames containing JSONL.',
    'It is already lossless; the outer gzip only bundles the collection.',
    '',
    'Extract:',
    '  tar -xzf <archive>.tar.gz',
    '  # or use 7-Zip / Windows Explorer with tar support',
    '',
    'Inspect one log:',
    '  zstd -d session.v4.jsonl.zstd',
    '',
    'manifest.json lists the original SHA-256 of every archived session file.',
    '',
  ].join('\n')
  entries.push({ name: 'manifest.json', data: Buffer.from(`${JSON.stringify(manifest, null, 2)}\n`, 'utf8'), mtime: Math.floor(Date.now() / 1000) })
  entries.push({ name: 'README.txt', data: Buffer.from(readme, 'utf8'), mtime: Math.floor(Date.now() / 1000) })
  const tar = createTar(entries)
  const compressed = gzipSync(tar, { level: GZIP_LEVEL })
  const stamp = manifest.createdAt.replace(/[-:T]/g, '').replace(/\..*$/, '')
  return {
    buffer: compressed,
    filename: `dsh-context-archive-${stamp}.tar.gz`,
    manifest,
    stats: {
      sessions: sessions.length,
      files: entries.length,
      uncompressedTarBytes: tar.length,
      compressedBytes: compressed.length,
      elapsedMs: Date.now() - started,
    },
  }
}
