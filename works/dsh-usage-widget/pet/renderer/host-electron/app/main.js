/**
 * main.js —— 透明桌宠宿主（Electron）
 *
 * 这是「能不能逐像素透明」这条路线的最小证明：
 *   frame:false + transparent:true + backgroundColor:'#00000000' + 页面背景透明
 * → Windows 上 Electron 会开一个分层窗口，真正带 alpha 合成到桌面上，
 *   模型轮廓以外的地方就是桌面本身。
 *
 * 复用 DSH 自带的 Electron 运行时：把 D:\DeepSeek Harness 里的运行时文件复制到
 * ..\runtime\，但**不带** resources\app.asar，于是 Electron 回落到自带的
 * resources\default_app.asar，按命令行参数把我们这个 app 目录当成应用加载。
 * 这样不用下载任何东西，也不影响正在运行的 DSH。
 *
 * 用法：
 *   runtime\DeepSeek Harness.exe <这个目录> [--x=.. --y=.. --w=.. --h=.. --clickthrough=1 --info=<path>]
 */
const { app, BrowserWindow, screen, ipcMain, protocol } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

// —— 早期日志：Electron 在 Windows 上是 GUI 子系统，stdout/stderr 常常抓不到，
//    所以关键步骤都写文件，排错只认这个文件。——
const LOG_PATH = process.env.PET_HOST_LOG || path.join(__dirname, 'boot.log')
try { fs.writeFileSync(LOG_PATH, '') } catch (e) {}
let logBroken = false
function log() {
  if (logBroken) return
  try {
    fs.appendFileSync(LOG_PATH, new Date().toISOString() + ' ' + Array.prototype.map.call(arguments, String).join(' ') + '\n')
  } catch (e) {
    logBroken = true // 日志自己出问题就闭嘴，绝不能在 uncaughtException 里递归
  }
}
log('boot', process.argv.slice(1).join(' '))
log('electron', process.versions.electron, 'type=' + process.type, 'defaultApp=' + process.defaultApp)
process.on('uncaughtException', (e) => { log('UNCAUGHT', e && e.stack) })
process.on('unhandledRejection', (e) => { log('UNHANDLED', e && e.stack) })


// 透明窗口在 Windows 上被「原生遮挡计算」判定为不可见时会被降帧，桌宠会看起来卡住
app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion')

// __dirname = ...\pet\renderer\host-electron\app  → 上三级就是 pet\
const PET_ROOT = path.resolve(__dirname, '..', '..', '..')
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.moc3': 'application/octet-stream',
  '.css': 'text/css; charset=utf-8',
}

protocol.registerSchemesAsPrivileged([
  { scheme: 'pet', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true, corsEnabled: true } },
])

// ————— 命令行 —————
const argv = process.argv.slice(2)
function arg(name, def) {
  const p = '--' + name + '='
  const hit = argv.find((a) => a.startsWith(p))
  return hit === undefined ? def : hit.slice(p.length)
}
const CLICK_THROUGH = arg('clickthrough', '1') === '1'
const ALWAYS_ON_TOP = arg('always-on-top', '1') === '1'
const RESIZABLE = arg('resizable', '0') === '1'
const WIN_W = parseInt(arg('w', '460'), 10)
const WIN_H = parseInt(arg('h', '560'), 10)
const AUTOQUIT = parseInt(arg('autoquit', '0'), 10)
const INFO_PATH = arg('info', '')
const PAGE_Q = arg('q', '')
// 面板矩形 "left,top,right,bottom"：给了就把桌宠摆到它的右下角，让约 1/4 落在面板里
const PANEL = arg('panel', '')

function defaultPos() {
  const wa = screen.getPrimaryDisplay().workArea
  if (PANEL) {
    const [l, t, r, b] = PANEL.split(',').map(Number)
    // 左上象限落在面板右下角之内 → 包围盒的 1/4 与面板重叠
    return { x: Math.round(r - WIN_W / 2), y: Math.round(b - WIN_H / 2) }
  }
  return { x: wa.x + wa.width - WIN_W - 8, y: wa.y + wa.height - WIN_H - 8 }
}

let win = null
let clickThrough = CLICK_THROUGH

function hwndOf(w) {
  try {
    const buf = w.getNativeWindowHandle()
    return '0x' + (buf.length >= 8 ? buf.readBigUInt64LE(0) : BigInt(buf.readUInt32LE(0))).toString(16)
  } catch (e) {
    return null
  }
}

function dumpInfo(extra) {
  if (!INFO_PATH || !win) return
  const b = win.getBounds()
  const info = Object.assign(
    {
      ok: true,
      hwnd: hwndOf(win),
      bounds: b,
      clickThrough,
      alwaysOnTop: win.isAlwaysOnTop(),
      petRoot: PET_ROOT,
      url: win.webContents.getURL(),
    },
    extra || {},
  )
  try {
    fs.writeFileSync(INFO_PATH, JSON.stringify(info, null, 2), 'utf8')
  } catch (e) {}
  log('info ' + JSON.stringify(info))
}

app.whenReady().then(() => {
  app.setAppUserModelId('local.dsh.usage.pet.proof')
  log('ready, petRoot=' + PET_ROOT)

  protocol.handle('pet', (request) => {
    const u = new URL(request.url)
    const rel = decodeURIComponent(u.pathname).replace(/^\/+/, '')
    const abs = path.normalize(path.join(PET_ROOT, rel))
    log('pet:// ' + u.pathname + ' -> ' + abs + ' exists=' + fs.existsSync(abs))
    if (!abs.startsWith(PET_ROOT) || !fs.existsSync(abs) || !fs.statSync(abs).isFile()) {
      return new Response('not found: ' + rel, { status: 404, headers: { 'content-type': 'text/plain' } })
    }
    return new Response(fs.readFileSync(abs), {
      status: 200,
      headers: { 'content-type': MIME[path.extname(abs).toLowerCase()] || 'application/octet-stream' },
    })
  })

  const pos = defaultPos()
  win = new BrowserWindow({
    x: parseInt(arg('x', String(pos.x)), 10),
    y: parseInt(arg('y', String(pos.y)), 10),
    width: WIN_W,
    height: WIN_H,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    resizable: RESIZABLE,
    hasShadow: false,
    skipTaskbar: true,
    show: false,
    title: 'DS 鲸鱼娘桌宠',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  })

  if (ALWAYS_ON_TOP) win.setAlwaysOnTop(true, 'screen-saver')
  win.setIgnoreMouseEvents(clickThrough, { forward: true })
  win.setMenuBarVisibility(false)

  const url = 'pet://app/renderer/index.html' + (PAGE_Q ? '?' + PAGE_Q : '')
  log('creating window at', pos.x, pos.y, url)
  win.webContents.on('console-message', (_e, lvl, msg) => log('[page] ' + msg))
  win.webContents.on('did-finish-load', () => log('did-finish-load'))
  win.webContents.on('did-fail-load', (_e, code, desc, u) => {
    log('did-fail-load ' + code + ' ' + desc + ' ' + u)
    dumpInfo({ ok: false, error: code + ' ' + desc })
  })
  win.webContents.on('did-finish-load', () => {
    setTimeout(() => {
      win.webContents
        .executeJavaScript('({ready: !!window.__PET_READY__, alpha: (window.PetAPI&&PetAPI.alphaProbe)?PetAPI.alphaProbe():null})')
        .then((r) => {
          log('page state ' + JSON.stringify(r))
          dumpInfo({ page: r })
        })
        .catch((e) => dumpInfo({ page: { error: String(e) } }))
    }, 3500)
  })

  win.loadURL(url)
  log('loadURL called')

  ipcMain.handle('pet:info', () => ({ hwnd: hwndOf(win), bounds: win.getBounds(), clickThrough, alwaysOnTop: win.isAlwaysOnTop() }))
  ipcMain.handle('pet:click-through', (_e, on) => {
    clickThrough = !!on
    win.setIgnoreMouseEvents(clickThrough, { forward: true })
    dumpInfo()
    return clickThrough
  })
  ipcMain.handle('pet:always-on-top', (_e, on) => {
    win.setAlwaysOnTop(!!on, 'screen-saver')
    dumpInfo()
    return win.isAlwaysOnTop()
  })
  ipcMain.handle('pet:move', (_e, x, y) => {
    win.setPosition(Math.round(x), Math.round(y))
    dumpInfo()
    return win.getBounds()
  })
  ipcMain.handle('pet:hit-test', (_e, x, y) => {
    return win.webContents
      .executeJavaScript('window.PetAPI.hitTest(' + Math.round(x) + ',' + Math.round(y) + ')')
      .catch(() => 'error')
  })
  ipcMain.handle('pet:quit', () => {
    app.quit()
    return true
  })

  win.once('ready-to-show', () => {
    win.showInactive()
    if (ALWAYS_ON_TOP) win.setAlwaysOnTop(true, 'screen-saver')
    dumpInfo()
  })
  // watchdog: never leave a stray window/process behind even if the page fails to load
  if (AUTOQUIT > 0) setTimeout(() => app.quit(), AUTOQUIT)
  // The panel itself is Topmost and re-asserts it on a timer. Among topmost windows Windows
  // orders by "most recently raised", so a one-shot setAlwaysOnTop can get covered. Re-assert
  // on a timer to keep winning the interleaving (SetWindowPos with SWP_NOACTIVATE: no focus steal).
  if (ALWAYS_ON_TOP) {
    setInterval(() => {
      if (win && !win.isDestroyed()) win.setAlwaysOnTop(true, 'screen-saver')
    }, 1500)
  }
  setTimeout(() => {
    if (!win.webContents.getURL() || win.webContents.isLoading()) {
      log('WARN page still loading after 8s: ' + win.webContents.getURL())
      dumpInfo({ warn: 'page still loading after 8s' })
    }
  }, 8000)
})

app.on('window-all-closed', () => app.quit())
