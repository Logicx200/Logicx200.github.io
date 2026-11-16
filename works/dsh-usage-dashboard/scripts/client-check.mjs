/**
 * Development harness: load the real browser bundle in Node against a minimal
 * `window.__ModuleLoader__`, stub `fetch` with a captured API payload, and
 * server-render both registered components.
 *
 * This is the offline proof that the client half mounts and renders: it
 * exercises the actual shipped `lib/client.js`, its module-loader wrapper, its
 * `apply`/`inject` exports, the slot registrations, and every component's
 * render path. Only React's host renderer and the framework services are
 * stubbed.
 *
 * Usage: node scripts/client-check.mjs --payload <stats.json>
 *
 * @module dsh-usage-dashboard/scripts/client-check
 */

import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { apply as applyHost, ROUTE_PATH } from '../src/index.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const packageRoot = resolve(here, '..')
const require = createRequire(import.meta.url)

function parseArgs(argv) {
  const options = { payload: undefined }
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--payload') options.payload = argv[++index]
  }
  return options
}

const options = parseArgs(process.argv.slice(2))

/**
 * Produce the payload the browser half will actually receive. Without
 * `--payload` the real host plugin is invoked against a stub context, so this
 * harness proves the two halves agree on the wire shape.
 *
 * @returns {Promise<any>} the API payload.
 */
async function resolvePayload() {
  if (options.payload !== undefined) {
    return JSON.parse(readFileSync(options.payload, 'utf8').replace(/^\uFEFF/, ''))
  }
  let route
  applyHost({
    connection: { fetch: { register(candidate) { route = candidate; return async () => {} } } },
    reflect: { provide() { return () => {} } },
    effect(callback) { callback(); return () => {} },
    logger: { warn: (...args) => console.warn('[warn]', ...args) },
    get() { return undefined },
  }, { ttlMs: 1000 })
  if (route === undefined || route.path !== ROUTE_PATH) throw new Error('the host plugin registered no route')
  const response = await route.fetch(new Request(`http://127.0.0.1${ROUTE_PATH}`))
  return response.json()
}

/* ── a minimal React ─────────────────────────────────────────────────────── */

/** Element factory: plain objects, enough for a recursive text renderer. */
function createElement(type, props, ...children) {
  const flat = []
  for (const child of children) {
    if (Array.isArray(child)) flat.push(...child.flat(Infinity))
    else if (child !== null && child !== undefined && child !== false) flat.push(child)
  }
  return { $$element: true, type, props: { ...(props || {}), children: flat } }
}

/**
 * A minimal stateful hook runtime: one cell list per mounted component, so a
 * `useState` setter re-renders the same hook order with new values — which is
 * what lets the harness observe the panel as data arrives.
 */
const hookState = {
  cells: [],
  cursor: 0,
  rendering: false,
  dirty: false,
  effects: [],
  cleanups: [],
}

function beginRender() {
  hookState.cursor = 0
  hookState.rendering = true
}

function endRender() {
  hookState.rendering = false
}

/**
 * Minimal `React.Component`, so a class-based error boundary can be mounted by
 * this harness. React itself dispatches `getDerivedStateFromError` during
 * reconciliation; this renderer never raises into it, so the class only has to
 * be constructible and renderable here.
 */
class Component {
  constructor(props) {
    this.props = props
    this.state = {}
  }

  setState(next) {
    const patch = typeof next === 'function' ? next(this.state) : next
    this.state = { ...this.state, ...patch }
  }
}
Component.prototype.isReactComponent = {}

const React = {
  Component,
  createElement,
  Fragment: Symbol('Fragment'),
  useState(initial) {
    const index = hookState.cursor++
    if (hookState.cells[index] === undefined) {
      hookState.cells[index] = typeof initial === 'function' ? initial() : initial
    }
    const setter = (next) => {
      const value = typeof next === 'function' ? next(hookState.cells[index]) : next
      if (Object.is(value, hookState.cells[index])) return
      hookState.cells[index] = value
      if (!hookState.rendering) hookState.dirty = true
    }
    return [hookState.cells[index], setter]
  },
  useRef(initial) {
    const index = hookState.cursor++
    if (hookState.cells[index] === undefined) hookState.cells[index] = { current: initial }
    return hookState.cells[index]
  },
  useMemo(factory) {
    hookState.cursor++
    return factory()
  },
  useEffect(effect) {
    const index = hookState.cursor++
    hookState.effects.push(effect)
    if (process.env.UD_DEBUG === '1') console.log(`  [debug] useEffect #${index} queued`)
    return () => {}
  },
  useCallback(fn) {
    hookState.cursor++
    return fn
  },
}

/** Cached module table: one instance per specifier, like the browser loader. */
const modules = new Map()
function load(specifier) {
  if (modules.has(specifier)) return modules.get(specifier)
  if (specifier === 'react') return React
  if (specifier === 'react/jsx-runtime') {
    const runtime = {
      jsx: (type, props, key) => createElement(type, key === undefined ? props : { ...props, key }),
      jsxs: (type, props, key) => createElement(type, key === undefined ? props : { ...props, key }),
    }
    modules.set(specifier, runtime)
    return runtime
  }
  throw new Error(`the bundle requested an unexpected module: ${specifier}`)
}

/* ── load the shipped bundle ─────────────────────────────────────────────── */

/** @type {Record<string, { id: string, factory: Function }>} */
const registry = {}
globalThis.window = {
  __ModuleLoader__: {
    load(entry) {
      registry[entry.id] = entry
    },
  },
}

/**
 * A truthful-enough DOM: the bundle injects one `<style>` element at module
 * scope, and that browser-only path is skipped entirely when `document` is
 * absent. Modelling the three members it touches keeps the check honest about
 * what the browser will actually do.
 */
const headChildren = []
globalThis.document = {
  querySelector(selector) {
    const match = /^style\[data-plugin-css="(.*)"\]$/.exec(selector)
    if (match === null) return null
    const wanted = JSON.parse('"' + match[1] + '"')
    return headChildren.find((child) => child.dataset.pluginCss === wanted) ?? null
  },
  createElement(tagName) {
    return { tagName, dataset: {}, textContent: undefined }
  },
  head: {
    appendChild(node) {
      headChildren.push(node)
    },
  },
}

const bundleSource = readFileSync(resolve(packageRoot, 'lib/client.js'), 'utf8')
// The bundle is an ESM-shaped IIFE over `window`; evaluating it only registers
// the factory, exactly as the browser kernel does. `document` is the stub
// installed above, `fetch` is forwarded to the stub installed below at call
// time, and the timers are the real globals.
new Function('window', 'document', 'fetch', 'setInterval', 'clearInterval', bundleSource)(
  globalThis.window,
  globalThis.document,
  (...args) => globalThis.fetch(...args),
  globalThis.setInterval,
  globalThis.clearInterval,
)

const entry = registry['dsh-usage-dashboard']
if (entry === undefined) throw new Error('the bundle registered no module')

/* ── stub the framework services ─────────────────────────────────────────── */

const payload = await resolvePayload()
console.log(
  `payload ${payload.sessions.length} sessions, ${payload.days.length} days, cost $${payload.totals.cost.toFixed(4)}`,
)

globalThis.fetch = async (url) => {
  fetchCount += 1
  console.log(`  [fetch] ${url}`)
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}
let fetchCount = 0

const dictionaries = new Map()
const effects = []
const tabTypes = []
const slotRegistrations = []
const injections = []

const ctx = {
  effect(callback, label) {
    const dispose = callback()
    effects.push({ label, dispose })
    return () => {}
  },
  on() {},
  off() {},
  locale: {
    register(ns, locale, dict) {
      dictionaries.set(`${ns}:${locale}`, dict)
      return () => {}
    },
    bind(ns) {
      return (key, params) => {
        const dict = dictionaries.get(`${ns}:zh`) || {}
        const template = dict[key] === undefined ? key : dict[key]
        if (params === undefined) return template
        return template.replace(/\{(\w+)\}/g, (match, name) =>
          name in params ? String(params[name]) : match,
        )
      }
    },
  },
  sidebarRightTabs: {
    register(definition) {
      tabTypes.push(definition)
      return () => {}
    },
  },
  sidebarRight: {
    openTab(kind) {
      opened.push(kind)
    },
  },
  slots: {
    inject(parent, register) {
      injections.push(parent)
      register()
    },
    register(definition, component) {
      slotRegistrations.push({ definition, component })
    },
  },
}
const opened = []

/** Assertion tally, declared before the plugin runs so the setup checks can use it. */
let failures = 0
const check = (label, ok) => {
  if (!ok) failures += 1
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${label}`)
}

/* ── run the plugin ──────────────────────────────────────────────────────── */

const clientModule = entry.factory(load)
if (typeof clientModule.apply !== 'function') throw new Error('the bundle exported no apply')
if (!Array.isArray(clientModule.inject)) throw new Error('the bundle exported no inject array')

console.log(`inject  ${clientModule.inject.join(', ')}`)
clientModule.apply(ctx)

// The style side effect runs at module materialization, which `factory(load)`
// above triggered; this is the one browser-only path a Node harness can miss.
const styleTag = headChildren[0]
check('the stylesheet was injected into <head>', styleTag !== undefined)
if (styleTag !== undefined) {
  check('the style tag is namespaced to this plugin', styleTag.dataset.plugin === 'dsh-usage-dashboard')
  check(
    'the stylesheet carries the panel rules',
    typeof styleTag.textContent === 'string' && styleTag.textContent.includes('.udsh-root'),
  )
  console.log(`style   ${styleTag.textContent.length} bytes, data-plugin=${styleTag.dataset.plugin}`)
}

console.log(`tab types    ${tabTypes.map((type) => `${type.kind} (${type.id})`).join(', ')}`)
console.log(`injections   ${injections.join(', ')}`)
console.log(`slots        ${slotRegistrations.map((row) => row.definition.name).join(', ')}`)
console.log(`dictionaries ${[...dictionaries.keys()].join(', ')}`)

/* ── render ──────────────────────────────────────────────────────────────── */

/**
 * Render one element tree to text, invoking function components the way React
 * does. Hook calls happen inside the component invocation, so the harness's
 * `beginRender`/`endRender` bracket has to cover the whole walk — that is what
 * makes the mount loop observe queued effects and state updates.
 *
 * @param {any} node - the element, array, or primitive.
 * @returns {string} the flattened text content.
 */
function render(node) {
  if (node === null || node === undefined || node === false || node === true) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map((child) => render(child)).join('')
  if (node.$$element !== true) return ''
  const { type, props } = node
  if (type === React.Fragment) return render(props.children)
  if (typeof type === 'function') {
    // A class component (built on the `Component` above) renders through an
    // instance, exactly as React does; a function component is called.
    if (type.prototype !== undefined && type.prototype.isReactComponent !== undefined) {
      return render(new type(props).render())
    }
    return render(type(props))
  }
  return render(props.children)
}

/**
 * Mount one registered component: render, run its effects once, then re-render
 * while any `useState` setter fired, which is how this harness observes the
 * panel across the store's load.
 *
 * @param {Function} component - the slot component.
 * @returns {Promise<string>} the flattened text of the final render.
 */
async function mount(component) {
  hookState.cells = []
  hookState.effects.length = 0
  hookState.cleanups.length = 0
  hookState.dirty = false
  const props = {
    useTabInfo: () => ({ tab: { id: 't1', actions: {}, visible: true } }),
    sessionId: 'session-test',
  }
  beginRender()
  let tree = component(props)
  const firstText = render(tree)
  endRender()

  let ranEffects = false
  let text = firstText
  for (let pass = 0; pass < 6; pass += 1) {
    if (!ranEffects) {
      ranEffects = true
      for (const effect of hookState.effects) {
        const cleanup = effect()
        if (typeof cleanup === 'function') hookState.cleanups.push(cleanup)
      }
    }
    await new Promise((done) => setTimeout(done, 40))
    if (hookState.dirty !== true) break
    hookState.dirty = false
    beginRender()
    tree = component(props)
    text = render(tree)
    endRender()
  }
  for (const cleanup of hookState.cleanups.splice(0)) cleanup()
  return text.replace(/\s+/g, ' ').trim()
}

console.log('\n── render ──────────────────────────────────────────────')
const rendered = new Map()
for (const registration of slotRegistrations) {
  const name = registration.definition.name
  try {
    const text = await mount(registration.component)
    rendered.set(name, text)
    check(`${name} renders (${text.length} chars)`, text.length > 0)
    console.log(`     ${text.slice(0, 220)}`)
  } catch (error) {
    check(`${name} renders`, false)
    console.log(`     ${error && error.stack ? error.stack.split('\n').slice(0, 5).join('\n     ') : error}`)
  }
}

/* ── assertions on the populated renders ─────────────────────────────────── */

const tabText = rendered.get('sidebar.right.pane.tab') || ''
const chipText = rendered.get('conversation.session.header.actions') || ''

console.log('\n── populated panel ─────────────────────────────────────')
console.log(`  ${tabText.slice(0, 900)}`)
console.log(`\n── populated chip ──────────────────────────────────────`)
console.log(`  ${chipText}`)

check('the panel rendered real numbers', /\$|%/.test(tabText) && tabText.length > 200)
check('the panel names a model', tabText.includes('deepseek-flash') || tabText.includes('DeepSeek'))
check('the panel lists sessions', tabText.includes('按会话') || /session-[0-9a-f]{8}/.test(tabText))
check('the panel renders the hourly section', tabText.includes('UTC'))
check('the chip shows a spend figure', /\$\d/.test(chipText))

/* ── the guide entry and the header action ───────────────────────────────── */

const guide = tabTypes[0] && tabTypes[0].guide && tabTypes[0].guide[0]
check('the tab type contributes a guide entry', guide !== undefined)
if (guide !== undefined) {
  console.log(`\nguide   title=${JSON.stringify(guide.title())}  description=${JSON.stringify(guide.description())}`)
  check('the guide entry renders a glyph', typeof guide.icon === 'function')
}

console.log(`\n${failures === 0 ? 'all client checks passed' : `${failures} client check(s) failed`}`)
process.exit(failures === 0 ? 0 : 1)
