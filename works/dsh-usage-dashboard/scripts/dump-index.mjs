/**
 * One-shot diagnostic: fetch the live root document with a minted browser
 * session cookie and report what the boot manifest says about this plugin —
 * the exact bundle URL it references, plus every script/module src on the page.
 *
 * Usage: node scripts/dump-index.mjs [--url http://127.0.0.1:19387/]
 *
 * @module dsh-usage-dashboard/scripts/dump-index
 */

import { createHash, createHmac } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { resolveDshHome } from '../src/session-store.mjs'

function parseArgs(argv) {
  const options = { url: 'http://127.0.0.1:19387/' }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--url') options.url = argv[++index]
  }
  return options
}

const base64url = (buffer) => buffer.toString('base64url')

function readSecret() {
  const text = readFileSync(join(resolveDshHome(), '.credentials.yaml'), 'utf8')
  const match = /^\s*secret:\s*(\S+)\s*$/m.exec(text)
  if (match === null) throw new Error('no browser-session secret in .credentials.yaml')
  return Buffer.from(match[1], 'base64url')
}

const options = parseArgs(process.argv.slice(2))
const authority = new URL(options.url).host
const now = Date.now()
const payload = {
  version: 1,
  authority,
  issuedAt: now - 1000,
  expiresAt: now + 29 * 24 * 3600 * 1000,
}
const body = base64url(Buffer.from(JSON.stringify(payload), 'utf8'))
const cookie =
  'dsh-auth-' +
  base64url(createHash('sha256').update(authority).digest()) +
  '=v1.' +
  body +
  '.' +
  base64url(createHmac('sha256', readSecret()).update(body).digest())

const response = await fetch(new URL('/', options.url), {
  headers: { cookie },
  redirect: 'manual',
  signal: AbortSignal.timeout(30000),
})
console.log(`root  HTTP ${response.status}`)
const html = await response.text()
console.log(`bytes ${html.length}`)

console.log('')
console.log('--- occurrences of "usage-dashboard" ---')
let index = 0
let found = 0
while ((index = html.indexOf('usage-dashboard', index)) >= 0) {
  found += 1
  const start = Math.max(0, index - 220)
  const chunk = html.slice(start, start + 440).replace(/\s+/g, ' ')
  console.log(`[${found}] ...${chunk}...`)
  index += 'usage-dashboard'.length
}
if (found === 0) console.log('(none)')

console.log('')
console.log('--- every src / href on the page ---')
const seen = new Set()
for (const match of html.matchAll(/(?:src|href)="([^"]+)"/g)) seen.add(match[1])
for (const url of seen) console.log('  ' + url)

console.log('')
console.log('--- every "/plugins" mention ---')
for (const match of html.matchAll(/\/plugins[^"'\s)]*/g)) console.log('  ' + match[0])

/*
 * `--bundle` fetches this plugin's own client bundle, so the code the shell is
 * actually serving can be compared with the file on disk. That is the only way
 * to tell a stale bundle cache from a genuinely applied edit.
 */
if (process.argv.includes('--bundle')) {
  let bundleUrl
  const manifest = /"__DSH_BOOT__"\] = (\{.*?\})<\/script>/s.exec(html)
  if (manifest !== null) {
    try {
      const boot = JSON.parse(manifest[1])
      const entry = (boot.entries || []).find((row) => row.id === 'dsh-usage-dashboard')
      bundleUrl = entry === undefined ? undefined : entry.url
    } catch {
      /* fall back to the conventional path */
    }
  }
  if (bundleUrl === undefined) bundleUrl = 'plugins/??dsh-usage-dashboard/client.js'

  const response = await fetch(new URL(bundleUrl, options.url), {
    headers: { cookie },
    signal: AbortSignal.timeout(30000),
  })
  const body = await response.text()
  console.log('')
  console.log(`--- served bundle  ${bundleUrl}`)
  console.log(`status ${response.status}   bytes ${body.length}`)
  console.log(`sha256 ${createHash('sha256').update(body).digest('hex')}`)
  for (const marker of ['installDiagnostics', 'SlotGuard', 'container-type', 'udsh-metrics']) {
    console.log(`  contains ${JSON.stringify(marker)}: ${body.includes(marker)}`)
  }
}
