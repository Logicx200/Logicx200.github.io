/**
 * build-states.mjs —— 为 11 个状态算出**契约真值**并写成 states.json，供拍图脚本使用。
 *
 * 为什么不手写 state.json：引擎每 2 s 会覆盖它。这里只是把 `pet/state.mjs` 的
 * `computeState()` 用「能触发该状态的观测」跑一遍，拿到权威的
 * `label / color / pose / detail / reason`，再由拍图脚本通过页面已有的
 * `postMessage({type:'pet-force'})` 通道注入（见 pet-app.js / reactions.js）。
 *
 * 输出：`pet/showcase/states.json`
 *   [{ state, label, color, pose, detail, reason, trigger, signals }]
 *   · trigger = 触发它的**日志字段**（给文档用）
 *   · signals = 注入给反应层的信号；其中所有 `at` 都是 0，拍图脚本会换成当前时间戳
 *     （TTL 状态必须"刚刚发生"才会亮）。
 *
 * 用法：node pet/showcase/build-states.mjs
 */
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const stateModule = await import(pathToFileURL(join(HERE, '..', 'state.mjs')).href)
const { computeState } = stateModule

const AT = 1_790_700_000_000
const snap = (over = {}) => ({ at: AT, agents: [], jobs: [], peakNow: false, ...over })
const AGENT = { id: 's1', state: 'running', sinceLastWriteMs: 500, label: 'Whale Girl showcase' }
const TOOL = { name: 'edit', phase: 'call', at: AT - 800, ok: null, error: null, summary: 'pet/renderer/reactions.js' }

/** state -> { obs, trigger, signals }（signals 里 at=0 由拍图脚本替换） */
const CASES = {
  offline: {
    obs: { dshRunning: false, snapshot: snap() },
    trigger: '心跳文件里 dshRunning === false（DSH 没在跑）',
    signals: null,
  },
  stale: {
    obs: { dshRunning: true, snapshot: snap({ at: AT - 600_000 }) },
    trigger: 'snapshot.at 距今 > SNAPSHOT_STALE_MS(45 000 ms)（引擎死了/快照没更新）',
    signals: null,
  },
  error: {
    obs: {
      dshRunning: true,
      snapshot: snap(),
      signals: {
        tool: { name: 'edit', phase: 'result', ok: false, error: 'FsError/FS_STALE_VERSION', at: AT - 400 },
        lastError: { name: 'edit', error: 'FsError/FS_STALE_VERSION', at: AT - 400 },
      },
    },
    trigger: 'tool/result data.error = {name:"FsError", code:"FS_STALE_VERSION"}（或 turn/end reason.kind="error"）',
    signals: { lastError: { name: 'edit', error: 'FsError/FS_STALE_VERSION', at: 0 } },
  },
  celebrating: {
    obs: {
      dshRunning: true,
      snapshot: snap(),
      signals: { turn: { phase: 'end', at: AT - 600, reason: 'completed', ms: 12_300, tokens: 41_380 } },
    },
    trigger: 'turn/end data.reason.kind = "completed"（引擎顺带算出 ms=12300 / tokens=41380）',
    signals: { turn: { phase: 'end', at: 0, reason: 'completed', ms: 12_300, tokens: 41_380 } },
  },
  listening: {
    obs: {
      dshRunning: true,
      snapshot: snap(),
      signals: { lastUserAt: AT - 500, lastUserText: '把表情交互加进去' },
    },
    trigger: 'user/message data.source.kind = "user"（引擎透传 lastUserAt；TTL 2 600 ms）',
    signals: { lastUserAt: 0, lastUserText: '把表情交互加进去' },
  },
  team: {
    obs: { dshRunning: true, snapshot: snap({ agents: [AGENT, { ...AGENT, id: 's2', label: '第二个分身' }] }) },
    trigger: '≥2 个 agent 的 state = "running"（snapshot.agents）',
    signals: null,
  },
  reading: {
    obs: {
      dshRunning: true,
      snapshot: snap(),
      signals: { tool: { name: 'web_search', phase: 'call', at: AT - 800, summary: 'live2d expression' } },
    },
    trigger: 'tool/call data.name = "web_search"（读类工具；上网类还会掏出小设备）',
    signals: { tool: { name: 'web_search', phase: 'call', at: 0, ok: null, error: null, summary: 'live2d expression' } },
  },
  writing: {
    obs: { dshRunning: true, snapshot: snap(), signals: { tool: { ...TOOL, at: AT - 800 } } },
    trigger: 'tool/call data.name = "edit"（写类：write / edit / todo_write）',
    signals: { tool: { name: 'edit', phase: 'call', at: 0, ok: null, error: null, summary: 'pet/renderer/reactions.js' } },
  },
  running: {
    obs: {
      dshRunning: true,
      snapshot: snap({ jobs: [{ program: 'pwsh', command: 'npm test', progress: { percent: 45.2, etaMs: 37_000 } }] }),
    },
    trigger: 'snapshot.jobs[] 非空（tool/call data.name = "pwsh" 的未配对调用）',
    signals: { tool: { name: 'pwsh', phase: 'call', at: 0, ok: null, error: null, summary: 'npm test' } },
  },
  thinking: {
    obs: { dshRunning: true, snapshot: snap(), signals: { streaming: { active: true, at: AT - 500 } } },
    trigger: 'assistant 步骤开着（step/start 未配对 step/end）或 event 距今 ≤ 30 000 ms',
    signals: { streaming: { active: true, at: 0 } },
  },
  idle: {
    obs: { dshRunning: true, snapshot: snap(), lastEventAt: AT - 600_000 },
    trigger: '以上都不成立（DSH 在跑、没工具、没任务、没出词）',
    signals: null,
  },
}

const ORDER = ['offline', 'stale', 'error', 'celebrating', 'listening', 'team', 'reading', 'writing', 'running', 'thinking', 'idle']
if (ORDER.length !== Object.keys(CASES).length) throw new Error('case table is out of sync with ORDER')

const rows = ORDER.map((state) => {
  const entry = CASES[state]
  const doc = computeState({ now: AT, ...entry.obs })
  if (doc.state !== state) throw new Error(`case ${state} actually resolved to ${doc.state}`)
  return {
    state,
    label: doc.label,
    color: doc.color,
    pose: doc.pose,
    detail: doc.detail,
    reason: doc.reason,
    trigger: entry.trigger,
    signals: entry.signals,
  }
})

const out = join(HERE, 'states.json')
writeFileSync(out, `${JSON.stringify(rows, null, 2)}\n`, 'utf8')
console.log(`wrote ${out} (${rows.length} states)`)
for (const row of rows) console.log(`  ${row.state.padEnd(12)} ${row.label.padEnd(6)} ${row.color}  pose=${row.pose.padEnd(9)} detail=${row.detail}`)
