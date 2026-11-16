/**
 * Development harness: assert the shipped browser bundle is intact — valid
 * UTF-8, complete dictionaries, and the chart geometry that keeps axis labels
 * undistorted.
 *
 * This exists because the bundle is authored as plain JS with no build step, so
 * a careless text round-trip (for example reading and rewriting it through a
 * shell that decodes as the system code page) can silently corrupt the copy
 * without breaking syntax in an obvious way.
 *
 * Usage: node scripts/bundle-check.mjs
 *
 * @module dsh-usage-dashboard/scripts/bundle-check
 */

import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const bundlePath = resolve(here, '..', 'lib', 'client.js')
const bytes = readFileSync(bundlePath)
const text = bytes.toString('utf8')

const zhKeys = [
  '用量与花费',
  '峰时',
  '谷时',
  '总花费',
  '总 tokens',
  '缓存命中率',
  '模型调用',
  '每日花费',
  '每日 tokens',
  '按模型',
  '按会话',
  '按工作区',
  '按 UTC 小时',
  '缓存命中',
  '缓存未命中',
  '输出',
  '刷新',
  '重试',
]

/** Every expected English key, to prove both dictionaries carry one key set. */
const enKeys = [
  'Usage & Spend',
  'peak',
  'off-peak',
  'Total spend',
  'Total tokens',
  'Cache-hit rate',
  'Model calls',
  'Daily spend',
  'Daily tokens',
  'By model',
  'By session',
  'By workspace',
  'By UTC hour',
  'cache hit',
  'cache miss',
  'output',
  'Refresh',
  'Retry',
]

const checks = [
  ['the file is valid UTF-8 with no replacement characters', !text.includes('\uFFFD')],
  ['every Chinese dictionary entry survived', zhKeys.every((key) => text.includes(key))],
  ['every English dictionary entry survived', enKeys.every((key) => text.includes(key))],
  ['the module loader wrapper is intact', text.startsWith('window.__ModuleLoader__.load(')],
  ['both hooks are exported', text.includes('exports.apply = apply') && text.includes('exports.inject = inject')],
  ['all three charts preserve their aspect ratio', (text.match(/preserveAspectRatio: FIT/g) ?? []).length === 3],
  ['no chart stretches its viewBox', !text.includes('preserveAspectRatio: "none"')],
  ['the lone-bucket bar cap exists', text.includes('function barWidth')],
  ['the locale-change subscription exists', text.includes('"locale/change"')],
  ['the dashboard endpoint matches the host route', text.includes('"/api/usage-dashboard/stats"')],
]

let failed = 0
for (const [label, ok] of checks) {
  if (!ok) failed += 1
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}`)
}

console.log(`\nbundle  ${bytes.length} bytes  ${text.split('\n').length} lines`)
console.log(failed === 0 ? 'all bundle checks passed' : `${failed} bundle check(s) failed`)
process.exitCode = failed === 0 ? 0 : 1
