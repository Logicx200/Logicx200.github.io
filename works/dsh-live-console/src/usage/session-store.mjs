/**
 * Durable session-artifact discovery and reading for the usage dashboard.
 *
 * The layout is owned by `@deepseek-ai/dsh-session-persistence-jsonl`:
 * `$DSH_HOME/sessions/<workspace-dir>/<session-id>/session.v<N>.jsonl.zstd`. The
 * number is the log *format* version and it moves: 0.2.0-rc.2 writes v4 while
 * sessions created earlier keep their v3 files. The frame container is unchanged
 * between the two, so discovery follows the version rather than pinning it.
 *
 * This module walks that tree, decodes each artifact, and hands the raw lines to
 * the usage fold — it holds no cache of its own so a read always reflects durable
 * state, and callers own any memoization.
 *
 * @module dsh-usage-dashboard/session-store
 */

import { readFile, readdir, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { homedir } from 'node:os'

import { readZstdJsonlLines } from './zstd.mjs'
import { foldSession } from './usage.mjs'

/**
 * The durable artifact name shape. The version is deliberately a capture rather
 * than a constant: the persistence layer bumps it when the log format changes,
 * so a session directory can hold several versions side by side after a
 * migration.
 */
export const SESSION_ARTIFACT_PATTERN = /^session\.v(\d+)\.jsonl\.zstd$/

/**
 * Resolve the Harness home directory.
 * @returns {string} absolute `$DSH_HOME`, defaulting to `~/.dsh`.
 */
export function resolveDshHome() {
  const configured = process.env.DSH_HOME
  return configured !== undefined && configured.length > 0
    ? configured
    : join(homedir(), '.dsh')
}

/**
 * Decode the workspace-bucket directory name back into its original path.
 *
 * The persistence layer encodes a workspace path by replacing every character
 * outside `[A-Za-z0-9._-]` with `~` followed by its uppercase hex code point,
 * which is lossy for display. The session log's own `cwd` field is the
 * authoritative path, so this is only the fallback label.
 *
 * @param {string} encoded - the directory name, e.g. `--F-DeepSeek~5DE5~4F5C~533A--`.
 * @returns {string} a best-effort display name.
 */
export function decodeWorkspaceDir(encoded) {
  const trimmed = encoded.replace(/^--/, '').replace(/--$/, '')
  let out = ''
  for (let index = 0; index < trimmed.length; index += 1) {
    const char = trimmed[index]
    if (char === '~') {
      const hex = trimmed.slice(index + 1, index + 5)
      if (/^[0-9A-Fa-f]{4}$/.test(hex)) {
        out += String.fromCharCode(Number.parseInt(hex, 16))
        index += 4
        continue
      }
    }
    out += char
  }
  return out
}

/**
 * Choose the artifact to read for one session directory.
 *
 * Exactly one file per session is folded. A session migrated to a newer log
 * format keeps the older artifact beside the new one, and the newer file is the
 * complete successor rather than a tail — measured on 0.2.0-rc.2, a migrated
 * session's v4 file carried every v3 line plus the lines written after the
 * migration, and a re-encoded session carried the same records in fewer bytes.
 * Folding both would double-count, so the highest version present wins.
 *
 * @param {string[]} entries - the session directory's file names.
 * @returns {{ name: string, version: number } | undefined} the chosen artifact.
 */
export function chooseArtifact(entries) {
  /** @type {{ name: string, version: number } | undefined} */
  let chosen
  for (const entry of entries) {
    const match = SESSION_ARTIFACT_PATTERN.exec(entry)
    if (match === null) continue
    const version = Number(match[1])
    if (chosen === undefined || version > chosen.version) {
      chosen = { name: entry, version }
    }
  }
  return chosen
}

/**
 * List every session artifact below the Harness home.
 *
 * @param {string} [home] - Harness home; resolved from the environment by default.
 * @returns {Promise<{ sessionId: string, workspace: string, workspaceDir: string, path: string, version: number, size: number, mtimeMs: number }[]>}
 *   one row per session, newest first.
 */
export async function listSessionArtifacts(home = resolveDshHome()) {
  const root = join(home, 'sessions')
  /** @type {any[]} */
  const rows = []
  /** @type {import('node:fs').Dirent[]} */
  let workspaceDirs
  try {
    workspaceDirs = await readdir(root, { withFileTypes: true })
  } catch (error) {
    if (error.code === 'ENOENT') return []
    throw error
  }
  for (const workspaceDir of workspaceDirs) {
    if (!workspaceDir.isDirectory()) continue
    const workspacePath = join(root, workspaceDir.name)
    /** @type {import('node:fs').Dirent[]} */
    let sessionDirs
    try {
      sessionDirs = await readdir(workspacePath, { withFileTypes: true })
    } catch {
      continue
    }
    for (const sessionDir of sessionDirs) {
      if (!sessionDir.isDirectory()) continue
      const sessionPath = join(workspacePath, sessionDir.name)
      /** @type {string[]} */
      let entries
      try {
        entries = await readdir(sessionPath)
      } catch {
        continue
      }
      const chosen = chooseArtifact(entries)
      if (chosen === undefined) continue
      const artifact = join(sessionPath, chosen.name)
      try {
        const info = await stat(artifact)
        if (!info.isFile()) continue
        rows.push({
          sessionId: sessionDir.name,
          workspaceDir: workspaceDir.name,
          workspace: decodeWorkspaceDir(workspaceDir.name),
          path: artifact,
          version: chosen.version,
          size: info.size,
          mtimeMs: info.mtimeMs,
        })
      } catch {
        continue
      }
    }
  }
  return rows.sort((left, right) => right.mtimeMs - left.mtimeMs)
}

/**
 * Read and fold one session artifact.
 *
 * A read that races the writer's rewrite can observe a torn trailing frame;
 * the decoder drops exactly that frame, so the facts returned always describe
 * durable bytes. A genuinely corrupt or unreadable artifact yields a row
 * carrying the error instead of failing the whole sweep.
 *
 * @param {{ sessionId: string, workspace: string, path: string, version: number, size: number, mtimeMs: number }} artifact
 * @param {string} defaultModel - route used when the log names none.
 * @returns {Promise<{ ok: true, facts: import('./usage.mjs').SessionFacts, bytes: number } | { ok: false, sessionId: string, error: string }>}
 */
export async function readSession(artifact, defaultModel) {
  try {
    const bytes = await readFile(artifact.path)
    const lines = readZstdJsonlLines(bytes)
    const facts = foldSession(lines, artifact.sessionId, artifact.workspace, defaultModel)
    return { ok: true, facts, bytes: bytes.length }
  } catch (error) {
    return {
      ok: false,
      sessionId: artifact.sessionId,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

/**
 * Fold every session artifact under the Harness home.
 *
 * @param {{ home?: string, defaultModel: string, concurrency?: number }} options
 * @returns {Promise<{ sessions: import('./usage.mjs').SessionFacts[], failures: { sessionId: string, error: string }[], artifacts: number, bytes: number, elapsedMs: number }>}
 */
export async function readAllSessions(options) {
  const started = Date.now()
  const artifacts = await listSessionArtifacts(options.home)
  const limit = Math.max(1, options.concurrency ?? 8)
  /** @type {import('./usage.mjs').SessionFacts[]} */
  const sessions = []
  /** @type {{ sessionId: string, error: string }[]} */
  const failures = []
  let bytes = 0
  let cursor = 0

  const worker = async () => {
    for (;;) {
      const index = cursor
      cursor += 1
      const artifact = artifacts[index]
      if (artifact === undefined) return
      const result = await readSession(artifact, options.defaultModel)
      if (result.ok) {
        sessions.push(result.facts)
        bytes += result.bytes
      } else {
        failures.push({ sessionId: result.sessionId, error: result.error })
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, artifacts.length) }, worker))
  return {
    sessions,
    failures,
    artifacts: artifacts.length,
    bytes,
    elapsedMs: Date.now() - started,
  }
}
