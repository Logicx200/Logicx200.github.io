/**
 * Conversation knowledge graph for the live console.
 *
 * Every durable session log becomes one node: its title, transcript excerpt,
 * keywords, cwd and time span. Two nodes are linked when they share a keyword,
 * and the link carries the shared terms so the page can explain why they are
 * connected.
 *
 * The log layout is owned by the session persistence package:
 * `$DSH_HOME/sessions/<workspace>/<session>/session.v<N>.jsonl.zstd`. Discovery
 * picks the highest version per session (a migrated session's newer artifact is
 * the complete successor, not a tail), the frame container is read by the same
 * reader the usage dashboard uses, and the fold tolerates a torn final frame.
 *
 * Keyword extraction is deliberately dependency-free: CJK bigrams/3-grams plus
 * Latin words, ranked by TF-IDF over the whole corpus. Runtime-context user
 * messages (the harness injects a long pseudo-prompt) are stripped first so
 * they do not pollute the graph.
 *
 * @module dsh-live-console/graph
 */

import { readdir, readFile, stat } from 'node:fs/promises'
import { basename, dirname, join, normalize } from 'node:path'

import { SESSION_ARTIFACT_PATTERN, chooseArtifact, decodeWorkspaceDir } from './usage/session-store.mjs'
import { readZstdJsonlLines } from './usage/zstd.mjs'

/** How many conversations one graph includes at most. */
const MAX_SESSIONS = 80

/** Transcript characters retained per node for the detail panel. */
const CONTENT_CHARS = 8_000

/** Excerpt characters used for the compact node tooltip. */
const EXCERPT_CHARS = 260

/** Keywords kept per node. */
const KEYWORDS_PER_NODE = Infinity

/** One CJK stop token that never becomes a keyword. */
const STOPWORDS = new Set([
  '一个', '一些', '一下', '这个', '那个', '这些', '那些', '这里', '那里', '什么', '怎么', '为什么',
  '可以', '可能', '应该', '需要', '使用', '进行', '通过', '已经', '现在', '还是', '就是', '因为',
  '所以', '但是', '如果', '然后', '而且', '并且', '以及', '不过', '只是', '不是', '没有', '我们',
  '你们', '他们', '自己', '东西', '时候', '问题', '方法', '情况', '内容', '部分', '时候', '一样',
  '这样', '那样', '多少', '几个', '一份', '这是', '那是', '这里', '里面', '出来', '起来', '上去',
  '下来', '看到', '知道', '觉得', '希望', '要求', '告诉', '确认', '检查', '看看', '试试', '能够',
  '是否', '其中', '目前', '之前', '之后', '以后', '以上', '以下', '对于', '关于', '根据', '按照',
  'let', 'const', 'var', 'function', 'return', 'class', 'async', 'await', 'import', 'export', 'window',
  'document', 'console', 'error', 'data', 'type', 'value', 'name', 'file', 'line', 'page', 'test', 'read',
  'write', 'add', 'get', 'set', 'use', 'this', 'that', 'null', 'true', 'false', 'undefined', 'string',
  'number', 'object', 'array', 'json', 'html', 'css', 'js', 'mjs', 'cjs', 'node', 'npm', 'pnpm', 'api',
  'url', 'http', 'https', 'host', 'client', 'plugin', 'service', 'index', 'lib', 'app', 'asar', 'module',
  'script', 'code', 'source', 'text', 'log', 'list', 'map', 'path', 'id', 'io', 'exe', 'cmd', 'sh',
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'your', 'you', 'are', 'was', 'were', 'have',
  'has', 'had', 'not', 'but', 'can', 'will', 'would', 'should', 'could', 'about', 'into', 'they',
  'them', 'their', 'there', 'here', 'what', 'when', 'where', 'which', 'while', 'then', 'than',
])

/** CJK characters that cannot start/end a meaningful bigram. */
const CJK_FILLER = new Set('的了是在有和与及就都而或把被让给对从向于以为所之其这那哪什么很更最又再还也但并如果因所以你我他她它们个种些点么吧呢啊呀哦嗯'.split(''))

/** Detect one runtime-context pseudo user message. */
const RUNTIME_CONTEXT_RE = /Current runtime context\.[\s\S]*?Current DeepSeek Harness Web GUI URL:[^\n]*\n?/i

/**
 * Extract only visible text blocks (text, not reasoning) from message content.
 * @param {unknown} content - message content.
 * @returns {string} visible text.
 */
function visibleText(content) {
  if (typeof content === 'string') return content
  if (!Array.isArray(content)) return ''
  let out = ''
  for (const block of content) {
    if (block !== null && typeof block === 'object' && block.type === 'text' && typeof block.text === 'string') {
      out += block.text
    }
  }
  return out
}

/**
 * Strip harness-injected context from a user message so it cannot dominate the
 * graph keywords. The actual request, when present, survives.
 * @param {string} text - raw user text.
 * @returns {string} cleaned text, possibly empty.
 */
export function cleanUserText(text) {
  if (typeof text !== 'string') return ''
  let value = text
  value = value.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/gi, ' ')
  value = value.replace(RUNTIME_CONTEXT_RE, ' ')
  value = value.replace(/You are an AI agent powered by DeepSeek Harness\.[\s\S]*?Current DeepSeek Harness implementation checkout:[^\n]*\n?/i, ' ')
  value = value.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
  return value.replace(/\s+/g, ' ').trim()
}

/**
 * Tokenize one document into candidate keywords.
 * @param {string} text - text to tokenize.
 * @returns {Map<string, number>} token -> count.
 */
export function tokenize(text) {
  const counts = new Map()
  if (typeof text !== 'string' || text.length === 0) return counts
  const add = (token, weight = 1) => {
    if (token.length < 2 || token.length > 12) return
    if (STOPWORDS.has(token)) return
    if (/\.(?:js|mjs|cjs|json|html|css|md|py|ps1|bat|cmd|zstd|asar|ts|tsx|jsx|txt|log)$/i.test(token)) return
    counts.set(token, (counts.get(token) ?? 0) + weight)
  }
  for (const match of text.matchAll(/[A-Za-z][A-Za-z0-9_+.-]{2,}/g)) add(match[0].toLowerCase())
  for (const run of text.match(/[\u4e00-\u9fff]{2,}/g) ?? []) {
    for (let index = 0; index <= run.length - 2; index += 1) {
      const bigram = run.slice(index, index + 2)
      if (CJK_FILLER.has(bigram[0]) || CJK_FILLER.has(bigram[1])) continue
      add(bigram, 1)
    }

  }
  return counts
}

/**
 * Rank keywords across one corpus with TF-IDF and return the top terms per doc.
 * @param {{ id: string, text: string, title?: string }[]} documents - one entry per session.
 * @param {number} [limit] - keywords per document.
 * @returns {Map<string, string[]>} document id -> keywords.
 */
export function rankKeywords(documents, limit = KEYWORDS_PER_NODE) {
  const perDocument = documents.map((document) => {
    const counts = tokenize(document.text)
    const titleCounts = tokenize(document.title ?? '')
    for (const [token, count] of titleCounts) {
      counts.set(token, (counts.get(token) ?? 0) + count * 2.5)
    }
    const title = String(document.title ?? '').trim()
    if (title.length >= 2 && title.length <= 20) {
      counts.set(title, (counts.get(title) ?? 0) + 4)
    }
    return counts
  })
  const documentFrequency = new Map()
  for (const counts of perDocument) {
    for (const token of counts.keys()) documentFrequency.set(token, (documentFrequency.get(token) ?? 0) + 1)
  }
  const total = Math.max(1, documents.length)
  /** @type {Map<string, string[]>} */
  const ranked = new Map()
  documents.forEach((document, index) => {
    const scored = [...perDocument[index]].map(([token, count]) => {
      const df = documentFrequency.get(token) ?? 1
      const idf = Math.log((total + 1) / (df + 0.5)) + 1
      return { token, score: count * idf * (token.length >= 3 ? 1.15 : 1) }
    })
    scored.sort((left, right) => right.score - left.score || right.token.length - left.token.length)
    // No fixed count cap: keep every term above an adaptive relevance floor, so
    // short chats still get keywords while huge logs don't keep every one-off
    // bigram. The floor scales with the document's strongest term.
    const floor = Math.max(1.2, (scored[0]?.score ?? 0) * 0.03)
    const picked = []
    for (const entry of scored) {
      if (picked.length >= limit) break
      if (entry.score < floor) continue
      picked.push(entry.token)
    }
    // Prefer the longer phrase: drop "传感"/"感器" when "传感器" is kept. Edges
    // are built from these visible keywords, so the graph and the panel agree.
    const pruned = picked.filter((token) => !picked.some((other) => other.length > token.length && other.includes(token)))
    ranked.set(document.id, pruned.length > 0 ? pruned : picked)
  })
  return ranked
}

/**
 * Build the graph payload from session documents.
 * @param {{ id: string, title: string, text: string, cwd: string, createdAt?: number, updatedAt?: number, messageCount?: number }[]} documents
 * @returns {{ nodes: any[], links: any[] }}
 */
export function buildGraph(documents) {
  const keywords = rankKeywords(documents)
  const nodes = documents.map((document) => {
    const terms = keywords.get(document.id) ?? []
    return {
      id: document.id,
      kind: 'conversation',
      typeLabel: '对话',
      short: document.id.length > 22 ? `${document.id.slice(0, 8)}…${document.id.slice(-6)}` : document.id,
      title: document.title || document.id,
      cwd: document.cwd,
      createdAt: document.createdAt ?? null,
      updatedAt: document.updatedAt ?? null,
      messageCount: document.messageCount ?? 0,
      keywords: terms,
      excerpt: document.text.slice(0, EXCERPT_CHARS),
      content: document.text.length > CONTENT_CHARS ? `${document.text.slice(0, CONTENT_CHARS)}…` : document.text,
    }
  })
  /** @type {Map<string, string[]>} */
  // All keywords stay on the node (no count cap). Edges use each node's top
  // keywords only: otherwise the corpus' common bigrams connect every pair and
  // the graph collapses into one black knot.
  const EDGE_KEYWORDS_PER_NODE = 24
  const byKeyword = new Map()
  for (const node of nodes) {
    for (const keyword of node.keywords.slice(0, EDGE_KEYWORDS_PER_NODE)) {
      const list = byKeyword.get(keyword) ?? []
      list.push(node.id)
      byKeyword.set(keyword, list)
    }
  }
  /** @type {Map<string, { source: string, target: string, shared: string[] }>} */
  const edgeMap = new Map()
  // Keywords this frequent describe the whole corpus ("模型", "说明") and would
  // turn the graph into a hairball. They stay as node keywords; only distinctive
  // terms create edges. The cutoff is relative, not a keyword-count limit.
  const genericCutoff = Math.max(3, Math.ceil(nodes.length * 0.4))
  for (const [keyword, ids] of byKeyword) {
    if (ids.length < 2 || ids.length > genericCutoff) continue
    for (let left = 0; left < ids.length; left += 1) {
      for (let right = left + 1; right < ids.length; right += 1) {
        const [source, target] = ids[left] < ids[right] ? [ids[left], ids[right]] : [ids[right], ids[left]]
        const key = `${source}\u0000${target}`
        const existing = edgeMap.get(key)
        if (existing === undefined) edgeMap.set(key, { source, target, shared: [keyword] })
        else if (!existing.shared.includes(keyword)) existing.shared.push(keyword)
      }
    }
  }
  const links = [...edgeMap.values()]
    .map((edge) => ({ ...edge, weight: edge.shared.length }))
    .sort((left, right) => right.weight - left.weight)
  return { nodes, links }
}

/** Tools whose argument paths mean the conversation actually touched a file. */
const FILE_TOOLS = new Set(['read', 'read_image', 'write', 'edit'])

/**
 * Recursively collect path-like values from a tool call's parsed arguments.
 * @param {unknown} value - argument value.
 * @param {string} key - parent key.
 * @param {string[]} out - collected values.
 */
function collectPathArguments(value, key, out) {
  if (typeof value === 'string') {
    if (/path|file/i.test(key) && value.length > 0 && value.length < 600) out.push(value)
    return
  }
  if (Array.isArray(value)) {
    for (const item of value) collectPathArguments(item, key, out)
    return
  }
  if (value !== null && typeof value === 'object') {
    for (const [childKey, childValue] of Object.entries(value)) collectPathArguments(childValue, childKey, out)
  }
}

/**
 * Resolve a tool argument into a stable absolute file path, rejecting URLs,
 * DSH internals, temporary files and obviously noisy values.
 * @param {string} raw - raw path from a tool argument.
 * @param {string} cwd - session working directory.
 * @returns {string | undefined} normalized path.
 */
function resolveFileReference(raw, cwd) {
  let value = raw.trim().replace(/^['"]|['"]$/g, '')
  if (value.length === 0 || value.length > 600) return undefined
  if (/^(?:https?|data|file):/i.test(value)) return undefined
  if (!/^[A-Za-z]:[\\/]/.test(value) && !value.startsWith('\\\\')) {
    value = join(cwd, value)
  }
  value = normalize(value)
  if (!/[\\/][^\\/]+$/.test(value)) return undefined
  if (/[\\/]\.dsh[\\/]|[\\/]app\.asar[\\/]|[\\/]sessions[\\/]|[\\/]Temp[\\/]|[\\/]node_modules[\\/]/i.test(value)) return undefined
  return value
}

/**
 * Read one session artifact and fold it into a graph document.
 * @param {string} path - absolute artifact path.
 * @param {string} sessionId - directory session id.
 * @param {string} cwd - decoded workspace path.
 * @returns {Promise<any | undefined>} the document, or undefined when unreadable.
 */
async function readSessionDocument(path, sessionId, cwd) {
  const lines = readZstdJsonlLines(await readFile(path))
  let meta
  try {
    const first = JSON.parse(lines[0] ?? 'null')
    if (first !== null && typeof first === 'object' && first.type === 'session') meta = first
  } catch {
    meta = undefined
  }
  // Teammates/subagents are internal work, not user conversations.
  if (meta?.origin === 'subagent') return undefined
  const effectiveCwd = typeof meta?.cwd === 'string' && meta.cwd.length > 0 ? meta.cwd : cwd
  let title = ''
  let createdAt = Number.isFinite(meta?.createdAt) ? meta.createdAt : undefined
  let updatedAt
  let messageCount = 0
  const pieces = []
  /** @type {Map<string, number>} */
  const fileRefs = new Map()
  for (const line of lines) {
    let event
    try {
      event = JSON.parse(line)
    } catch {
      continue
    }
    if (event === null || typeof event !== 'object') continue
    if (Number.isFinite(event.time)) {
      createdAt ??= event.time
      updatedAt = event.time
    }
    if (event.type === 'session/title' && typeof event.data?.title === 'string' && event.data.title.trim().length > 0) {
      title = event.data.title.trim()
      continue
    }
    if (event.type === 'tool/call' && FILE_TOOLS.has(event.data?.name)) {
      try {
        const args = typeof event.data.arguments === 'string' ? JSON.parse(event.data.arguments) : event.data.arguments
        const rawPaths = []
        collectPathArguments(args, '', rawPaths)
        for (const rawPath of rawPaths) {
          const resolved = resolveFileReference(rawPath, effectiveCwd)
          if (resolved !== undefined) fileRefs.set(resolved, (fileRefs.get(resolved) ?? 0) + 1)
        }
      } catch {
        /* malformed tool arguments are not a graph failure */
      }
    }
    if (event.type === 'user/message') {
      const text = cleanUserText(visibleText(event.data?.content))
      if (text.length > 0) {
        pieces.push(`你：${text}`)
        messageCount += 1
      }
    } else if (event.type === 'assistant/message') {
      const text = visibleText(event.data?.message?.content).trim()
      if (text.length > 0) {
        pieces.push(`模型：${text}`)
        messageCount += 1
      }
    }
  }
  if (pieces.length === 0 && title.length === 0) return undefined
  const text = pieces.join('\n')
  return {
    id: sessionId,
    title: title || (pieces[0] ?? '').replace(/^你：/, '').slice(0, 40) || sessionId,
    text,
    cwd: effectiveCwd,
    createdAt,
    updatedAt,
    messageCount,
    files: [...fileRefs.entries()],
  }
}

/**
 * Scan the durable session store and build the whole conversation graph.
 * @param {{ home?: string, maxSessions?: number }} [options] - sweep options.
 * @returns {Promise<{ nodes: any[], links: any[], stats: any }>} graph payload.
 */
export async function collectConversationGraph(options = {}) {
  const started = Date.now()
  const home = typeof options.home === 'string' && options.home.length > 0 ? options.home : undefined
  const sessionsRoot = join(home ?? (process.env.DSH_HOME ?? join((await import('node:os')).homedir(), '.dsh')), 'sessions')
  const maxSessions = Number.isFinite(options.maxSessions) ? Number(options.maxSessions) : MAX_SESSIONS
  /** @type {{ path: string, sessionId: string, cwd: string, mtimeMs: number }[]} */
  const artifacts = []
  try {
    for (const workspace of await readdir(sessionsRoot, { withFileTypes: true })) {
      if (!workspace.isDirectory()) continue
      const workspaceDir = join(sessionsRoot, workspace.name)
      for (const session of await readdir(workspaceDir, { withFileTypes: true })) {
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
          cwd: decodeWorkspaceDir(workspace.name),
          mtimeMs: info.mtimeMs,
        })
      }
    }
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error
  }
  artifacts.sort((left, right) => right.mtimeMs - left.mtimeMs)
  const selected = artifacts.slice(0, maxSessions)
  const documents = []
  const failures = []
  for (const artifact of selected) {
    try {
      const document = await readSessionDocument(artifact.path, artifact.sessionId, artifact.cwd)
      if (document !== undefined) documents.push(document)
    } catch (error) {
      failures.push({ sessionId: artifact.sessionId, error: String(error) })
    }
  }
  const graph = buildGraph(documents)
  // A file becomes a node only when at least two different conversations touch
  // the same normalized path. This is the one non-conversation type that clearly
  // passes the decision rule today: stable identity + cross-session reuse.
  /** @type {Map<string, { path: string, sessions: Set<string>, count: number, updatedAt?: number }>} */
  const fileIndex = new Map()
  for (const document of documents) {
    for (const [filePath, count] of document.files ?? []) {
      const entry = fileIndex.get(filePath) ?? { path: filePath, sessions: new Set(), count: 0, updatedAt: document.updatedAt }
      entry.sessions.add(document.id)
      entry.count += count
      if (Number.isFinite(document.updatedAt)) entry.updatedAt = Math.max(entry.updatedAt ?? 0, document.updatedAt)
      fileIndex.set(filePath, entry)
    }
  }
  const candidates = [...fileIndex.values()]
    .filter((entry) => entry.sessions.size >= 2)
    .sort((left, right) => right.sessions.size - left.sessions.size || right.count - left.count)
    .slice(0, 60)
  const fileNodes = []
  const fileLinks = []
  for (const entry of candidates) {
    let info
    try {
      info = await stat(entry.path)
      if (!info.isFile()) continue
    } catch {
      continue
    }
    const fileId = `file:${entry.path}`
    const fileName = basename(entry.path)
    const extension = /\.([A-Za-z0-9]{1,10})$/.exec(fileName)?.[1]?.toLowerCase() ?? ''
    const sessionTitles = [...entry.sessions]
      .map((sessionId) => documents.find((document) => document.id === sessionId)?.title || sessionId)
      .slice(0, 8)
    fileNodes.push({
      id: fileId,
      kind: 'file',
      typeLabel: '文件',
      short: fileName,
      title: fileName,
      cwd: dirname(entry.path),
      path: entry.path,
      createdAt: null,
      updatedAt: entry.updatedAt ?? info.mtimeMs,
      messageCount: entry.sessions.size,
      keywords: [fileName, extension, '文件'].filter(Boolean),
      excerpt: entry.path,
      content: `文件：${entry.path}\n被 ${entry.sessions.size} 个对话引用（${entry.count} 次）\n大小：${info.size} 字节\n更新：${new Date(info.mtimeMs).toLocaleString('zh-CN', { hour12: false })}\n\n引用它的对话：\n${sessionTitles.map((title) => `- ${title}`).join('\n')}`,
    })
    for (const sessionId of entry.sessions) {
      if (!graph.nodes.some((node) => node.id === sessionId)) continue
      fileLinks.push({ source: sessionId, target: fileId, shared: ['引用文件'], weight: 1, kind: 'file' })
    }
  }
  graph.nodes.push(...fileNodes)
  graph.links.push(...fileLinks)
  return {
    ...graph,
    stats: {
      sessions: documents.length,
      files: fileNodes.length,
      nodes: graph.nodes.length,
      links: graph.links.length,
      keywords: new Set(graph.nodes.flatMap((node) => node.keywords)).size,
      artifacts: artifacts.length,
      skipped: artifacts.length - selected.length,
      failures,
      elapsedMs: Date.now() - started,
    },
  }
}
