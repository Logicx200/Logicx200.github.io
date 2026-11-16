/**
 * Offline checks for conversation-graph keyword extraction and linking.
 *
 *   node test/graph-check.mjs
 */

import assert from 'node:assert/strict'

import { buildGraph, cleanUserText, rankKeywords, tokenize } from '../src/graph.mjs'

let passed = 0
function ok(label) {
  passed += 1
  console.log(`ok    ${label}`)
}

assert.equal(
  cleanUserText('Current runtime context. foo\nCurrent DeepSeek Harness Web GUI URL: "http://x"\n\n你检查一下这两个文件夹'),
  '你检查一下这两个文件夹',
)
ok('runtime-context pseudo prompts are stripped')

assert.equal(cleanUserText('<system-reminder>noise</system-reminder>真正的请求'), '真正的请求')
ok('system reminders are stripped')

const tokens = tokenize('红外目标探测仿真 infrared target simulation 的 了')
assert.ok(tokens.has('红外'))
assert.ok(tokens.has('目标'))
assert.ok(tokens.has('infrared'))
assert.ok(!tokens.has('的'))
ok('CJK bigrams and Latin words are extracted, stopwords dropped')

const documents = [
  { id: 'a', title: '红外探测', text: '红外目标探测仿真 传感器 传感器 大气' },
  { id: 'b', title: '红外仿真', text: '红外目标仿真 传感器 传感器 模型' },
  { id: 'c', title: '照片整理', text: '照片 时间轴 文件夹' },
]
const ranked = rankKeywords(documents)
assert.ok(ranked.get('a').some((keyword) => ['红外', '探测', '红外探测', '传感器', '仿真'].includes(keyword)))
ok('TF-IDF ranks topic terms per document')

const graph = buildGraph(documents)
assert.equal(graph.nodes.length, 3)
assert.ok(graph.links.some((link) => link.source === 'a' && link.target === 'b'))
assert.ok(graph.links.every((link) => link.shared.length > 0))
ok('nodes with a shared keyword are linked')

const linkAB = graph.links.find((link) => link.source === 'a' && link.target === 'b')
assert.ok(linkAB.shared.some((keyword) => ['红外', '目标', '仿真', '传感器'].includes(keyword)))
ok('the link carries the shared keywords')

assert.equal(graph.nodes[0].content.length > 0, true)
assert.ok(Array.isArray(graph.nodes[0].keywords))
ok('nodes carry content and keywords for the detail panel')

console.log('')
console.log(`all graph checks passed (${passed} assertions)`)
