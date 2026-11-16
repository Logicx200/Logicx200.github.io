/** Dev check: print the client boot manifest and any live-console entries. */
import { createHash, createHmac } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const home = process.env.DSH_HOME ?? join(homedir(), '.dsh')
const secret = Buffer.from(/^\s*secret:\s*(\S+)\s*$/m.exec(readFileSync(join(home, '.credentials.yaml'), 'utf8'))[1], 'base64url')
const base64url = (buffer) => buffer.toString('base64url')
const authority = '127.0.0.1:4620'
const now = Date.now()
const payload = { version: 1, authority, issuedAt: now - 1000, expiresAt: now + 29 * 24 * 3600 * 1000 }
const body = base64url(Buffer.from(JSON.stringify(payload), 'utf8'))
const cookie = 'dsh-auth-' + base64url(createHash('sha256').update(authority).digest()) + '=v1.' + body + '.' + base64url(createHmac('sha256', secret).update(body).digest())

const response = await fetch('http://127.0.0.1:4620/', { headers: { cookie }, redirect: 'manual' })
const text = await response.text()
const marker = '__DSH_BOOT__"] = '
const start = text.indexOf(marker)
const end = text.indexOf('</script>', start)
if (start < 0 || end < 0) {
  console.error('boot manifest not found; status', response.status, 'bytes', text.length)
  process.exit(1)
}
const boot = JSON.parse(text.slice(start + marker.length, end))
const entries = Array.isArray(boot.entries) ? boot.entries : []
console.log('boot entries', entries.length)
console.log('live-console entries:', JSON.stringify(entries.filter((entry) => String(entry.id).includes('live-console'))))
console.log('all ids mentioning console:', entries.filter((entry) => String(entry.id).includes('console')).map((entry) => entry.id))
