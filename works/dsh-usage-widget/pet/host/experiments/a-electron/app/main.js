// EXPERIMENT A -- minimal Electron transparent window.
// Reports everything the cost/behaviour measurement needs to a JSON file:
//   pid, t0 (module load), readyAt / showAt (startup), clickThrough mode, and every click the
//   PAGE actually received (forwarded over IPC from the preload bridge).
// Click-through is flipped at runtime by writing a-control.json, so one launch covers both modes.
const { app, BrowserWindow, ipcMain, screen } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

// NOTE: for a PACKAGED Electron app process.argv[1] is already the first switch, so
// process.argv.slice(2) silently swallows it -- that is how --x=60 went missing on the first
// run and the window ended up at the default position. Filter instead of slicing.
const argv = process.argv.filter((a) => a.startsWith('--'))
function arg(name, def) {
  const p = '--' + name + '='
  const hit = argv.find((a) => a.startsWith(p))
  return hit === undefined ? def : hit.slice(p.length)
}
const OUT = process.env.EXP_OUT || path.join(__dirname, 'a-state.json')
const CONTROL = process.env.EXP_CONTROL || path.join(__dirname, 'a-control.json')
const W = parseInt(arg('w', '460'), 10)
const H = parseInt(arg('h', '560'), 10)

const state = {
  pid: process.pid,
  electron: process.versions.electron,
  execPath: process.execPath,
  resourcesPath: process.resourcesPath,
  t0: Date.now(),
  readyAt: null,
  showAt: null,
  clickThrough: null,
  clicks: 0,
  events: [],
  error: null,
}
function dump() {
  try {
    fs.writeFileSync(OUT + '.tmp', JSON.stringify(state, null, 2))
    fs.renameSync(OUT + '.tmp', OUT)
  } catch (e) {}
}
process.on('uncaughtException', (e) => { state.error = String(e && e.stack); dump() })

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion')

app.whenReady().then(() => {
  const wa = screen.getPrimaryDisplay().workArea
  const win = new BrowserWindow({
    x: parseInt(arg('x', String(wa.x + wa.width - W - 8)), 10),
    y: parseInt(arg('y', String(wa.y + wa.height - H - 8)), 10),
    width: W,
    height: H,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    skipTaskbar: true,
    resizable: false,
    show: false,
    title: 'PET-EXP-A',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  })

  let ct = true
  try { win.setAlwaysOnTop(true, 'screen-saver') } catch (e) {}
  win.setIgnoreMouseEvents(ct, { forward: true })
  state.clickThrough = ct
  win.setMenuBarVisibility(false)
  try {
    const buf = win.getNativeWindowHandle()
    state.hwnd = '0x' + (buf.length >= 8 ? buf.readBigUInt64LE(0) : BigInt(buf.readUInt32LE(0))).toString(16)
  } catch (e) { state.hwnd = null }

  win.webContents.on('did-finish-load', () => { state.loadedAt = Date.now(); dump() })
  win.once('ready-to-show', () => {
    state.readyAt = Date.now()
    win.showInactive()
    state.showAt = Date.now()
    dump()
  })

  ipcMain.on('exp-click', (_e, p) => {
    state.clicks += 1
    state.events.push(Object.assign({ k: 'down', n: state.clicks, at: Date.now() }, p || {}))
    dump()
  })
  ipcMain.on('exp-move', (_e, p) => {
    state.events.push(Object.assign({ k: 'move', at: Date.now() }, p || {}))
    while (state.events.length > 80) state.events.shift()
    dump()
  })

  win.loadFile(path.join(__dirname, 'page.html'))
  dump()

  setInterval(() => {
    try {
      const c = JSON.parse(fs.readFileSync(CONTROL, 'utf8'))
      if (typeof c.clickThrough === 'boolean' && c.clickThrough !== ct) {
        ct = c.clickThrough
        win.setIgnoreMouseEvents(ct, { forward: true })
        state.clickThrough = ct
        state.events.push({ k: 'mode', clickThrough: ct, at: Date.now() })
        dump()
      }
      if (c.quit) app.quit()
    } catch (e) {}
  }, 200)

  const autoquit = parseInt(arg('autoquit', '0'), 10)
  if (autoquit > 0) setTimeout(() => app.quit(), autoquit)
})

app.on('window-all-closed', () => app.quit())
