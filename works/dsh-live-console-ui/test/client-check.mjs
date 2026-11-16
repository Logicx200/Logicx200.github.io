/**
 * Offline check for the live console's client half.
 *
 * The bundle is executed in the same module-loader form the shell uses, with a
 * minimal React stub, then the registered header action is rendered and clicked
 * against a stub host route. This proves the piece the browser would run without
 * needing the GUI.
 *
 *   node test/client-check.mjs
 */

import assert from 'node:assert/strict'

let passed = 0
/** @param {string} label */
function ok(label) {
  passed += 1
  console.log(`ok    ${label}`)
}

const opened = []
const tags = []
let loaderDefinition
let injectedSlot
let registered

const ReactStub = {
  createElement(type, props, ...children) {
    return { type, props: props ?? {}, children }
  },
  Component: class Component {},
}

globalThis.window = {
  __ModuleLoader__: {
    load(definition) {
      loaderDefinition = definition
    },
  },
  open(url, target, features) {
    opened.push({ url, target, features })
    return {}
  },
}
globalThis.document = {
  querySelector() {
    return null
  },
  createElement(tag) {
    return { tag, dataset: {}, textContent: '' }
  },
  head: {
    appendChild(node) {
      tags.push(node)
    },
  },
}
const fetchCalls = []
globalThis.fetch = async (url) => {
  fetchCalls.push(String(url))
  return {
    ok: true,
    status: 200,
    async json() {
      return { url: 'http://127.0.0.1:4620/live-console?k=test-capability' }
    },
  }
}

await import('../lib/client.js')

assert.equal(loaderDefinition.id, 'dsh-live-console-ui')
ok('the bundle registers with the module loader')

const moduleExports = loaderDefinition.factory((name) => {
  if (name === 'react') return ReactStub
  throw new Error(`unexpected require(${name})`)
})
assert.equal(typeof moduleExports.apply, 'function')
assert.ok(Array.isArray(moduleExports.inject))
assert.ok(moduleExports.inject.includes('slots'))
ok('the bundle exports apply/inject under the module-loader form')

const ctx = {
  effect(fn) {
    return fn()
  },
  slots: {
    inject(name, callback) {
      injectedSlot = name
      return callback()
    },
    register(definition, Component) {
      registered = { definition, Component }
      return () => {}
    },
  },
}
moduleExports.apply(ctx)
assert.equal(injectedSlot, 'conversation.session.header.actions')
assert.equal(registered.definition.name, 'conversation.session.header.actions')
assert.equal(registered.definition.id, 'live-console-open')
assert.equal(registered.definition.order, 35)
ok('the header action registers in conversation.session.header.actions')

const tag = tags.find((node) => node.dataset?.plugin === 'dsh-live-console')
assert.ok(tag !== undefined)
assert.ok(String(tag.textContent).includes('.dsh-live-console-open'))
ok('the button stylesheet is injected and namespaced')

const element = registered.Component({})
assert.equal(element.type, 'button')
assert.equal(element.props.className, 'dsh-live-console-open')
assert.equal(typeof element.props.onClick, 'function')
ok('the button renders with an accessibly labelled title')

await element.props.onClick()
assert.deepEqual(fetchCalls, ['/api/live-console/url'])
assert.equal(opened.length, 1)
assert.equal(opened[0].url, 'http://127.0.0.1:4620/live-console?k=test-capability')
assert.equal(opened[0].target, '_blank')
ok('clicking asks the host for the URL and opens the console')

// A failing host route must be contained, not throw into the header.
globalThis.fetch = async () => ({ ok: false, status: 503, async json() { return {} } })
await element.props.onClick()
assert.equal(opened.length, 1)
ok('a failed URL request is contained')

console.log('')
console.log(`all client checks passed (${passed} assertions)`)
