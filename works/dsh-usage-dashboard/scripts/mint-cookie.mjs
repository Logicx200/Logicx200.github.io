/**
 * Development harness: mint the browser session cookie the running Harness
 * expects, so the dashboard's authenticated route can be exercised with the
 * same request policy a real browser goes through.
 *
 * The cookie is exactly what `dsh-client-connection` writes on the root token
 * exchange: `v1.<base64url payload>.<base64url HMAC-SHA256>`, signed with the
 * owner-scoped `client-connection/browser-session` grant secret in
 * `$DSH_HOME/.credentials.yaml`, bound to the request authority.
 *
 * Usage: node scripts/mint-cookie.mjs [--url http://127.0.0.1:3080/]
 *
 * @module dsh-usage-dashboard/scripts/mint-cookie
 */

import { createHash, createHmac } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { resolveDshHome } from '../src/session-store.mjs'

function parseArgs(argv) {
  const options = { url: 'http://127.0.0.1:3080/' }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--url') options.url = argv[++index]
  }
  return options
}

const base64url = (buffer) => buffer.toString('base64url')

/**
 * Read the signing secret out of the credentials document.
 *
 * The stored value is base64url of 32 random bytes — the local credential
 * provider's canonical form, verified against the running GUI's own
 * verification path.
 *
 * @returns {Buffer} the 32-byte HMAC key.
 */
function readSecret() {
  const text = readFileSync(join(resolveDshHome(), '.credentials.yaml'), 'utf8')
  const match = /^\s*secret:\s*(\S+)\s*$/m.exec(text)
  if (match === null) throw new Error('no browser-session secret in .credentials.yaml')
  const decoded = Buffer.from(match[1], 'base64url')
  if (decoded.byteLength !== 32) throw new Error(`secret is ${decoded.byteLength} bytes, expected 32`)
  return decoded
}

const options = parseArgs(process.argv.slice(2))
const authority = new URL(options.url).host
const secret = readSecret()
const now = Date.now()
const payload = {
  version: 1,
  authority,
  issuedAt: now - 1000,
  // The carrier rejects any cookie whose lifetime reaches 30 days: measured on
  // 0.2.0-rc.2, 29 days answers 200 and 30 days answers 401. Keep this under the
  // bound rather than at it.
  expiresAt: now + 29 * 24 * 3600 * 1000,
}
const body = base64url(Buffer.from(JSON.stringify(payload), 'utf8'))
const value = `v1.${body}.${base64url(createHmac('sha256', secret).update(body).digest())}`
const name = 'dsh-auth-' + base64url(createHash('sha256').update(authority).digest())

console.log(`${name}=${value}`)
