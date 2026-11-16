'use strict';

/*
 * ASCII Studio — browser smoke test.
 *
 * Uses the Microsoft Edge / Google Chrome DevTools Protocol directly,
 * without Playwright or Puppeteer. It launches:
 *   1. the local zero-dependency server on an ephemeral port
 *   2. a headless browser with a throwaway profile
 *   3. a scripted tour through image, video, export and mobile layouts
 *
 * Run:  node tests/browser-smoke.js
 * Env:  BROWSER_PATH / EDGE_PATH, QA_PORT optional
 */

const fs = require('fs');
const path = require('path');
const net = require('net');
const { spawn } = require('child_process');

const ROOT = path.resolve(__dirname, '..');
const TMP = path.join(__dirname, '.tmp');
const PROFILE = path.join(TMP, 'edge-profile-' + process.pid + '-' + Date.now());
const DOWNLOADS = path.join(TMP, 'downloads-' + process.pid + '-' + Date.now());
const SHOTS = path.join(__dirname, 'screenshots');

const IS_WINDOWS = process.platform === 'win32';
const EDGE_CANDIDATES = [
  process.env.BROWSER_PATH,
  process.env.EDGE_PATH,
  IS_WINDOWS ? 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe' : '',
  IS_WINDOWS ? 'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe' : '',
  IS_WINDOWS ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' : '',
  IS_WINDOWS ? 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' : '',
  !IS_WINDOWS ? '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge' : '',
  !IS_WINDOWS ? '/usr/bin/microsoft-edge' : '',
  !IS_WINDOWS ? '/usr/bin/google-chrome' : ''
].filter(Boolean);

const PASSED = [];
const WARNINGS = [];
let edgeProcess = null;
let serverProcess = null;
let cdp = null;
let browserLog = '';
let pageErrors = [];
let networkErrors = [];
let baseUrl = '';
let screenshots = [];
let startedAt = Date.now();

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function log(message) {
  console.log(message);
}

function check(condition, label, detail) {
  if (!condition) throw new Error('检查失败：' + label + (detail ? ' — ' + detail : ''));
  PASSED.push(label);
  log('  ✓ ' + label);
}

function warn(message) {
  WARNINGS.push(message);
  log('  ! ' + message);
}

function findBrowser() {
  for (const candidate of EDGE_CANDIDATES) {
    try {
      if (fs.statSync(candidate).isFile()) return candidate;
    } catch (error) {
      /* keep looking */
    }
  }
  throw new Error('找不到 Edge 或 Chrome。请设置 BROWSER_PATH 环境变量指向浏览器 exe。');
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const port = server.address().port;
      server.close(() => resolve(port));
    });
  });
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error('HTTP ' + response.status + ' ' + url);
  return response.json();
}

async function waitForHttp(url, timeout) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeout) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2000) });
      if (response.ok) return true;
      lastError = new Error('HTTP ' + response.status);
    } catch (error) {
      lastError = error;
    }
    await delay(160);
  }
  throw new Error('本地服务没有启动：' + (lastError ? lastError.message : url));
}

async function waitForJson(url, timeout) {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeout) {
    if (edgeProcess && edgeProcess.exitCode != null) {
      throw new Error('浏览器提前退出（exit ' + edgeProcess.exitCode + '）\n' + browserLog.slice(-3000));
    }
    try {
      return await fetchJson(url);
    } catch (error) {
      lastError = error;
    }
    await delay(200);
  }
  throw new Error('调试端点不可用：' + (lastError ? lastError.message : url));
}

function pageTargetUrl(devtoolsUrl, targetId) {
  const parsed = new URL(devtoolsUrl);
  return 'ws://' + parsed.hostname + ':' + parsed.port + '/devtools/page/' + targetId;
}

async function findOrCreatePageTarget(devtoolsUrl) {
  log('  · 连接浏览器调试端点 ' + devtoolsUrl);
  const version = await waitForJson(devtoolsUrl + '/json/version', 20000);
  log('  · ' + version.Browser);

  // Explicitly create our own page target. This is more reliable than
  // depending on the initial tab in headless mode.
  let createError = null;
  try {
    const browser = await CdpConnection.connect(version.webSocketDebuggerUrl);
    try {
      const created = await browser.send('Target.createTarget', { url: baseUrl }, 15000);
      if (created && created.targetId) {
        log('  · 新页面目标 ' + created.targetId.slice(0, 8));
        return {
          id: created.targetId,
          type: 'page',
          url: baseUrl,
          webSocketDebuggerUrl: pageTargetUrl(devtoolsUrl, created.targetId)
        };
      }
    } finally {
      browser.close();
    }
  } catch (error) {
    createError = error;
    warn('Target.createTarget 失败：' + error.message);
  }

  // Fallback 1: the HTTP endpoint for creating a new tab.
  try {
    const page = await fetchJson(
      devtoolsUrl + '/json/new?' + encodeURIComponent(baseUrl),
      { method: 'PUT' }
    );
    if (page && page.webSocketDebuggerUrl) {
      log('  · 通过 /json/new 创建页面');
      return page;
    }
  } catch (error) {
    createError = createError || error;
  }

  // Fallback 2: reuse any existing page target.
  for (let attempt = 0; attempt < 25; attempt++) {
    try {
      const targets = await fetchJson(devtoolsUrl + '/json/list');
      const page = targets.find((entry) => entry.type === 'page' && entry.webSocketDebuggerUrl);
      if (page) return page;
    } catch (error) {
      createError = createError || error;
    }
    await delay(200);
  }

  throw new Error(
    '没有找到可调试的页面目标。' +
    (createError ? '\n原因：' + createError.message : '') +
    '\n' + browserLog.slice(-3000)
  );
}

async function readDevToolsPort(timeout) {
  const file = path.join(PROFILE, 'DevToolsActivePort');
  const started = Date.now();
  while (Date.now() - started < timeout) {
    // The stderr line is authoritative; the profile file can be delayed.
    const match = /DevTools listening on ws:\/\/127\.0\.0\.1:(\d+)\//.exec(browserLog);
    if (match) return Number(match[1]);

    try {
      const raw = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/);
      const port = Number(raw[0]);
      if (port > 0) return port;
    } catch (error) {
      /* browser still starting */
    }
    if (edgeProcess && edgeProcess.exitCode != null) {
      throw new Error('浏览器提前退出（exit ' + edgeProcess.exitCode + '）\n' + browserLog.slice(-4000));
    }
    await delay(160);
  }
  throw new Error('等待浏览器的 DevTools 端口超时\n' + browserLog.slice(-4000));
}

class CdpConnection {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Map();
    this.closed = false;

    ws.addEventListener('message', (event) => this.handleMessage(event));
    ws.addEventListener('close', () => {
      this.closed = true;
      for (const pending of this.pending.values()) {
        clearTimeout(pending.timer);
        pending.reject(new Error('CDP connection closed'));
      }
      this.pending.clear();
    });
  }

  static async connect(url) {
    const ws = new WebSocket(url);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('CDP WebSocket 连接超时')), 15000);
      ws.addEventListener('open', () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      ws.addEventListener('error', () => {
        clearTimeout(timer);
        reject(new Error('CDP WebSocket 连接失败'));
      }, { once: true });
    });
    return new CdpConnection(ws);
  }

  handleMessage(event) {
    let message;
    try {
      message = JSON.parse(typeof event.data === 'string' ? event.data : Buffer.from(event.data).toString('utf8'));
    } catch (error) {
      return;
    }

    if (message.id != null) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      clearTimeout(pending.timer);
      if (message.error) {
        pending.reject(new Error(pending.method + ' — ' + (message.error.message || 'CDP error')));
      } else {
        pending.resolve(message.result || {});
      }
      return;
    }

    const handlers = this.listeners.get(message.method);
    if (!handlers) return;
    for (const handler of handlers) {
      try {
        handler(message.params);
      } catch (error) {
        console.warn('CDP event handler error:', error.message);
      }
    }
  }

  on(method, handler) {
    if (!this.listeners.has(method)) this.listeners.set(method, new Set());
    this.listeners.get(method).add(handler);
  }

  send(method, params, timeout) {
    if (this.closed) return Promise.reject(new Error('CDP connection is closed'));
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(method + ' 超时'));
      }, timeout || 30000);
      this.pending.set(id, { resolve, reject, timer, method });
      try {
        this.ws.send(JSON.stringify({ id, method, params: params || {} }));
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  close() {
    try {
      this.ws.close();
    } catch (error) {
      /* ignore */
    }
  }
}

async function main() {
  const browserPath = findBrowser();
  fs.mkdirSync(TMP, { recursive: true });
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync(DOWNLOADS, { recursive: true });
  for (const entry of fs.readdirSync(SHOTS)) {
    fs.rmSync(path.join(SHOTS, entry), { force: true, recursive: true });
  }
  // Remove profiles/download dirs from interrupted runs; each run uses unique
  // directories so a stale file can never masquerade as a fresh export.
  for (const entry of fs.readdirSync(TMP)) {
    if (!entry.startsWith('edge-profile-') && !entry.startsWith('downloads-')) continue;
    const oldPath = path.join(TMP, entry);
    if (oldPath === PROFILE || oldPath === DOWNLOADS) continue;
    try {
      fs.rmSync(oldPath, { recursive: true, force: true });
    } catch (error) {
      /* A still-running old browser can hold locks; ignore. */
    }
  }

  const port = Number(process.env.QA_PORT) || (await freePort());
  baseUrl = 'http://127.0.0.1:' + port + '/';
  log(`\nASCII Studio browser QA\n  browser: ${browserPath}\n  url:     ${baseUrl}\n`);

  log('[qa 1/12] 启动本地服务…');
  serverProcess = spawn(process.execPath, [path.join(ROOT, 'server.js')], {
    cwd: ROOT,
    env: Object.assign({}, process.env, { NO_OPEN: '1', PORT: String(port) }),
    stdio: ['ignore', 'pipe', 'pipe']
  });
  let serverLog = '';
  serverProcess.stdout.on('data', (chunk) => { serverLog += chunk.toString(); });
  serverProcess.stderr.on('data', (chunk) => { serverLog += chunk.toString(); });
  await waitForHttp(baseUrl, 15000);

  log('[qa 2/12] 启动无头浏览器…');
  const args = [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--mute-audio',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--disable-sync',
    '--autoplay-policy=no-user-gesture-required',
    '--window-size=1440,960',
    '--user-data-dir=' + PROFILE,
    '--remote-debugging-port=0',
    '--disable-features=msEdgeFirstRunExperience',
    baseUrl
  ];
  edgeProcess = spawn(browserPath, args, {
    cwd: ROOT,
    stdio: ['ignore', 'ignore', 'pipe']
  });
  edgeProcess.stderr.on('data', (chunk) => {
    browserLog += chunk.toString();
    if (browserLog.length > 12000) browserLog = browserLog.slice(-12000);
  });

  const devtoolsPort = await readDevToolsPort(25000);
  const devtoolsUrl = 'http://127.0.0.1:' + devtoolsPort;
  const target = await findOrCreatePageTarget(devtoolsUrl);

  cdp = await CdpConnection.connect(target.webSocketDebuggerUrl);
  pageErrors = [];
  networkErrors = [];

  cdp.on('Runtime.exceptionThrown', (params) => {
    const details = params.exceptionDetails || {};
    const text = details.exception && details.exception.description
      ? details.exception.description
      : details.text || 'Unknown page exception';
    pageErrors.push(text);
  });
  cdp.on('Runtime.consoleAPICalled', (params) => {
    if (params.type !== 'error') return;
    const text = (params.args || []).map((arg) => {
      if (arg.value != null) return String(arg.value);
      if (arg.description) return arg.description;
      return '';
    }).filter(Boolean).join(' ');
    pageErrors.push(text);
  });
  cdp.on('Log.entryAdded', (params) => {
    const entry = params.entry || {};
    if (entry.level === 'error') pageErrors.push(entry.text || '');
  });
  cdp.on('Network.responseReceived', (params) => {
    const response = params.response || {};
    if (response.status >= 400) {
      networkErrors.push(response.status + ' ' + (response.url || ''));
    }
  });
  cdp.on('Network.loadingFailed', (params) => {
    if (params.errorText && params.errorText !== 'net::ERR_ABORTED') {
      networkErrors.push(params.errorText + ' ' + (params.type || ''));
    }
  });

  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Log.enable');
  await cdp.send('Network.enable');
  try {
    await cdp.send('Page.setDownloadBehavior', { behavior: 'allow', downloadPath: DOWNLOADS });
  } catch (error) {
    warn('浏览器不支持 Page.setDownloadBehavior，导出下载测试可能跳过：' + error.message);
  }

  await setViewport(1440, 960, 1, false);
  await cdp.send('Page.navigate', { url: baseUrl });

  log('[qa 3/12] 等待应用启动…');
  await waitFor('应用启动', async () => {
    return await evalJs('Boolean(window.__ASCII_STUDIO_READY__ && window.ASCII_STUDIO)');
  }, 20000);
  await delay(450);

  log('[qa 4/12] 检查空状态与示例入口…');
  const empty = await evalJs(`(() => ({
    samples: document.querySelectorAll('.sample-card').length,
    demoWidth: document.getElementById('demoCanvas').width,
    stageVisible: !document.getElementById('emptyState').hidden
  }))()`);
  check(empty.samples === 3, '三个示例素材入口存在', 'samples=' + empty.samples);
  check(empty.demoWidth > 20, '空状态演示动画画布已渲染', 'width=' + empty.demoWidth);
  check(empty.stageVisible, '空状态正常显示');
  await takeScreenshot('01-empty.png');

  log('[qa 5/12] 载入示例图片…');
  await click('[data-sample="dunes"]');
  const imageSnapshot = await waitForSnapshot(
    (snapshot) => snapshot.kind === 'image' && !snapshot.loading && snapshot.lineCount > 0,
    '示例图片完成转换',
    25000
  );
  check(imageSnapshot.cols > 20 && imageSnapshot.rows > 10, '图片生成字符网格', `${imageSnapshot.cols}x${imageSnapshot.rows}`);
  check(imageSnapshot.canvas.width > 100, '预览画布已绘制', String(imageSnapshot.canvas.width));
  check(imageSnapshot.settings.colorMode === 'mono', '默认按单色渲染');
  check(imageSnapshot.settings.autoLevels === true, '默认开启自动明暗增强');
  check(imageSnapshot.emptyVisible === false, '载入后隐藏空状态');
  await delay(450);
  await takeScreenshot('02-image.png');

  log('[qa 5b] 检查像素画模式…');
  await click('#renderModeTabs [data-render-mode="pixel"]');
  const pixelImage = await waitForSnapshot(
    (snapshot) => snapshot.renderMode === 'pixel' && snapshot.kind === 'image' && snapshot.rows > 0 && snapshot.pixel,
    '图片切换到像素画模式',
    15000
  );
  check(pixelImage.settings.pixelPalette === 'pico8', '像素模式默认使用 PICO-8 色板');
  check(pixelImage.pixel.palette === 'pico8' && pixelImage.pixel.colors === 16, 'PICO-8 色板包含 16 色');
  check(pixelImage.cols === 128 && pixelImage.rows === 80, '像素网格使用方形像素', `${pixelImage.cols}x${pixelImage.rows}`);
  check(await evalJs('document.body.classList.contains("mode-pixel")'), '像素模式切换了界面主题');
  check(
    await evalJs('document.getElementById("copyBtn").disabled && document.getElementById("txtBtn").disabled'),
    '像素模式禁用文本类导出'
  );
  check(
    await evalJs('document.getElementById("unitLabel").textContent === "像素"'),
    '底部计数单位切换为像素'
  );
  await delay(350);
  await takeScreenshot('02b-pixel.png');

  await click('.pixel-preset[data-palette="gameboy"]');
  const pixelGb = await waitForSnapshot(
    (snapshot) => snapshot.settings.pixelPalette === 'gameboy' && snapshot.pixel && snapshot.pixel.palette === 'gameboy',
    '切换 Game Boy 色板',
    15000
  );
  check(pixelGb.pixel.colors === 4, 'Game Boy 色板限制为 4 色');
  await delay(300);
  await takeScreenshot('02c-pixel-gameboy.png');

  await click('#pixelOutlineToggle');
  await waitForSnapshot((snapshot) => snapshot.settings.pixelOutline === false, '关闭像素描边', 10000);
  await click('#pixelOutlineToggle');
  await waitForSnapshot((snapshot) => snapshot.settings.pixelOutline === true, '重新开启像素描边', 10000);

  await click('#pngBtn');
  const pixelPng = await waitForDownload('.png', 15000, false, function (name) {
    return name.indexOf('-pixel-') >= 0;
  });
  check(fs.statSync(pixelPng.path).size > 1000, '像素 PNG 导出文件有效', pixelPng.name);
  for (const entry of fs.readdirSync(DOWNLOADS)) {
    fs.rmSync(path.join(DOWNLOADS, entry), { force: true, recursive: true });
  }

  await click('#renderModeTabs [data-render-mode="ascii"]');
  await waitForSnapshot(
    (snapshot) => snapshot.renderMode === 'ascii' && snapshot.lineCount > 0,
    '切回字符画模式',
    15000
  );
  check(
    await evalJs('!document.getElementById("copyBtn").disabled && !document.getElementById("txtBtn").disabled'),
    '字符模式恢复文本类导出'
  );

  log('[qa 6/12] 调整字符与观感参数…');
  await evalJs(`(() => {
    const range = document.getElementById('colsRange');
    range.value = '100';
    range.dispatchEvent(new Event('input', { bubbles: true }));
    return range.value;
  })()`);
  await waitForSnapshot((snapshot) => snapshot.settings.imageCols === 100 && snapshot.cols === 100, '网格列数变为 100', 10000);

  await click('.charset-chip[data-charset="blocks"]');
  await waitForSnapshot((snapshot) => snapshot.settings.charset === 'blocks' && snapshot.levels === 5, '切换方块字符集', 10000);

  await click('#colorModeSeg button[data-color="mono"]');
  await waitForSnapshot((snapshot) => snapshot.settings.colorMode === 'mono', '切换单色模式', 10000);

  await click('.swatch[data-accent="#ffbd6b"]');
  await waitForSnapshot((snapshot) => snapshot.settings.accent === '#ffbd6b', '切换字符颜色', 10000);

  await evalJs(`(() => {
    const range = document.getElementById('brightness');
    range.value = '24';
    range.dispatchEvent(new Event('input', { bubbles: true }));
    const contrast = document.getElementById('contrast');
    contrast.value = '16';
    contrast.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  await waitForSnapshot((snapshot) => snapshot.settings.brightness === 24 && snapshot.settings.contrast === 16, '亮度与对比度参数生效', 10000);
  await delay(300);
  await takeScreenshot('03-image-tuned.png');

  log('[qa 7/12] 测试自定义字符集…');
  await click('.charset-chip[data-charset="custom"]');
  await evalJs(`(() => {
    const input = document.getElementById('customChars');
    input.value = ' .oO@';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return input.value;
  })()`);
  const customSnapshot = await waitForSnapshot(
    (snapshot) => snapshot.settings.charset === 'custom' && snapshot.levels === 5,
    '自定义字符集生效',
    10000
  );
  check(customSnapshot.levels === 5, '自定义字符集层级正确');
  await click('#resetBtn');
  await waitForSnapshot(
    (snapshot) => snapshot.settings.imageCols === 140 && snapshot.settings.colorMode === 'mono' && snapshot.settings.autoLevels === true,
    '恢复默认参数',
    10000
  );

  log('[qa 8/12] 测试 PNG / TXT 导出…');
  await click('#pngBtn');
  const pngFile = await waitForDownload('.png', 15000);
  check(fs.statSync(pngFile.path).size > 1000, 'PNG 导出文件有效', fs.statSync(pngFile.path).size + ' bytes');
  await click('#txtBtn');
  const txtFile = await waitForDownload('.txt', 15000);
  const txtContent = fs.readFileSync(txtFile.path, 'utf8');
  check(txtContent.replace(/^\uFEFF/, '').trim().length > 50, 'TXT 导出包含字符画内容');
  check(txtFile.path !== pngFile.path, 'PNG 与 TXT 分别生成文件');

  await click('[data-sample="orb"]');
  await waitForSnapshot(
    (snapshot) => snapshot.kind === 'image' && snapshot.fileName === 'orb-sample.jpg' && snapshot.lineCount > 0 && !snapshot.loading,
    '载入第二个示例图片',
    20000
  );

  log('[qa 9/12] 载入示例视频…');
  await click('[data-sample="orbit"]');
  const videoSnapshot = await waitForSnapshot(
    (snapshot) => snapshot.kind === 'video' && !snapshot.loading && snapshot.lineCount > 0,
    '示例视频完成转换',
    30000
  );
  check(videoSnapshot.duration > 1, '视频时长读取正常', videoSnapshot.duration.toFixed(2) + 's');
  check(videoSnapshot.cols > 20 && videoSnapshot.rows > 10, '视频生成字符网格');
  const playerVisible = await evalJs('!document.getElementById("playerBar").hidden');
  check(playerVisible, '视频播放控制条显示');

  await waitForSnapshot((snapshot) => snapshot.playing, '视频自动播放', 12000);
  await delay(1100);
  await takeScreenshot('04-video.png');

  await click('#playBtn');
  const paused = await waitForSnapshot((snapshot) => !snapshot.playing, '视频暂停', 8000);
  check(paused.playing === false, '播放/暂停按钮工作');

  await evalJs(`(() => {
    const seek = document.getElementById('seekRange');
    seek.value = String(Number(seek.max) / 2);
    seek.dispatchEvent(new Event('input', { bubbles: true }));
    return seek.value;
  })()`);
  await waitForSnapshot(
    (snapshot) => snapshot.currentTime > snapshot.duration * 0.3,
    '视频进度可拖动',
    10000
  );
  await click('#playBtn');
  await waitForSnapshot((snapshot) => snapshot.playing, '视频恢复播放', 10000);

  await click('#peekBtn');
  await delay(300);
  check(await evalJs('document.getElementById("sourcePeek").classList.contains("is-visible")'), '原片对照面板打开');
  await click('#peekClose');

  await evalJs(`(() => {
    const select = document.getElementById('fpsSelect');
    select.value = '15';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return select.value;
  })()`);
  await waitForSnapshot((snapshot) => snapshot.settings.fps === 15, '渲染帧率调整为 15 FPS', 10000);
  check(true, '渲染帧率调整生效');

  log('[qa 10/12] 测试字符动画录制…');
  const recordSupported = await evalJs('window.ASCII_STUDIO.getSnapshot().recordSupported');
  if (recordSupported) {
    await click('#recordBtn');
    const recording = await waitForSnapshot((snapshot) => snapshot.recording === true, '开始录制', 10000);
    check(recording.recording === true, '录制状态进入');
    await delay(1600);
    await click('#recordBtn');
    await waitForSnapshot((snapshot) => snapshot.recording === false, '结束录制', 15000);
    const webm = await waitForDownload('.webm', 20000, true);
    if (webm) {
      check(fs.statSync(webm.path).size > 1000, '录制的 WebM 文件有效', fs.statSync(webm.path).size + ' bytes');
    } else {
      warn('无头环境没有产生录制下载文件；录制功能已可达但未验证文件。');
    }
  } else {
    warn('当前无头浏览器不支持 Canvas MediaRecorder，跳过录制文件验证。');
  }

  log('[qa 10b] 检查视频像素化…');
  await click('#renderModeTabs [data-render-mode="pixel"]');
  const pixelVideo = await waitForSnapshot(
    (snapshot) => snapshot.renderMode === 'pixel' && snapshot.kind === 'video' && snapshot.rows > 0 && snapshot.pixel,
    '视频切换到像素画模式',
    20000
  );
  check(pixelVideo.cols === 96 && pixelVideo.rows === 54, '视频像素网格为 96 × 54', `${pixelVideo.cols}x${pixelVideo.rows}`);
  await click('#playBtn');
  await waitForSnapshot((snapshot) => snapshot.playing, '像素视频播放', 12000);
  await delay(700);
  await takeScreenshot('04b-video-pixel.png');
  await click('#renderModeTabs [data-render-mode="ascii"]');
  await waitForSnapshot(
    (snapshot) => snapshot.renderMode === 'ascii' && snapshot.kind === 'video' && snapshot.lineCount > 0,
    '视频切回字符画模式',
    15000
  );

  await click('#helpBtn');
  await delay(320);
  check(await evalJs('document.getElementById("helpDialog").open === true'), '使用说明弹窗可打开');
  await takeScreenshot('06-help.png');
  await click('#helpStart');

  log('[qa 11/12] 检查移动端布局…');
  await setViewport(390, 844, 2, true);
  await cdp.send('Page.navigate', { url: baseUrl + '?sample=dunes' });
  await delay(350);
  await waitForSnapshot(
    (snapshot) => snapshot.kind === 'image' && !snapshot.loading && snapshot.emptyVisible === false,
    '移动端示例图片载入',
    25000
  );
  await delay(500);
  const mobileMetrics = await evalJs(`(() => {
    const snapshot = window.ASCII_STUDIO.getSnapshot();
    const canvas = document.getElementById('asciiCanvas').getBoundingClientRect();
    const mount = document.getElementById('canvasMount').getBoundingClientRect();
    const gridAspect = (snapshot.cols * snapshot.settings.cellAspect) / snapshot.rows;
    const expectedWidth = Math.min(mount.width, mount.height * gridAspect);
    return {
      innerWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      canvasWidth: canvas.width,
      canvasHeight: canvas.height,
      mountWidth: mount.width,
      mountHeight: mount.height,
      expectedWidth: expectedWidth,
      gridAspect: gridAspect,
      controlsTop: document.querySelector('.controls-panel').getBoundingClientRect().top,
      stageTop: document.querySelector('.stage-column').getBoundingClientRect().top
    };
  })()`);
  log('  · 移动端尺寸：' + JSON.stringify({
    canvas: [Math.round(mobileMetrics.canvasWidth), Math.round(mobileMetrics.canvasHeight)],
    mount: [Math.round(mobileMetrics.mountWidth), Math.round(mobileMetrics.mountHeight)],
    expectedWidth: Math.round(mobileMetrics.expectedWidth)
  }));
  check(mobileMetrics.scrollWidth <= mobileMetrics.innerWidth + 1, '移动端没有横向溢出', `${mobileMetrics.scrollWidth} > ${mobileMetrics.innerWidth}`);
  check(mobileMetrics.canvasWidth > 120, '移动端字符画可见', mobileMetrics.canvasWidth.toFixed(1) + 'px');
  check(
    Math.abs(mobileMetrics.canvasWidth - mobileMetrics.expectedWidth) <= 4,
    '移动端画布贴合可用区域',
    `actual=${mobileMetrics.canvasWidth.toFixed(1)} expected=${mobileMetrics.expectedWidth.toFixed(1)}`
  );
  check(mobileMetrics.stageTop < mobileMetrics.controlsTop, '移动端预览位于控制面板之前');
  await takeScreenshot('05-mobile.png');

  await click('[data-sample="orbit"]');
  const mobileVideo = await waitForSnapshot(
    (snapshot) => snapshot.kind === 'video' && !snapshot.loading && snapshot.lineCount > 0,
    '移动端视频载入',
    30000
  );
  await waitForSnapshot((snapshot) => snapshot.playing, '移动端视频播放', 12000);
  await delay(700);
  const mobileVideoMetrics = await evalJs(`(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    playerVisible: !document.getElementById('playerBar').hidden,
    playerHeight: document.getElementById('playerBar').getBoundingClientRect().height
  }))()`);
  check(mobileVideo.kind === 'video', '移动端视频转换正常');
  check(mobileVideoMetrics.playerVisible && mobileVideoMetrics.playerHeight > 40, '移动端播放控制条可用');
  check(mobileVideoMetrics.scrollWidth <= mobileVideoMetrics.innerWidth + 1, '移动端视频无横向溢出');
  await takeScreenshot('07-mobile-video.png');

  await click('#renderModeTabs [data-render-mode="pixel"]');
  await waitForSnapshot(
    (snapshot) => snapshot.renderMode === 'pixel' && snapshot.kind === 'video' && snapshot.rows > 0 && snapshot.pixel,
    '移动端切换像素模式',
    20000
  );
  await delay(500);
  const mobilePixelOverflow = await evalJs('document.documentElement.scrollWidth - window.innerWidth');
  check(mobilePixelOverflow <= 1, '移动端像素模式无横向溢出');
  await takeScreenshot('08-mobile-pixel.png');
  await click('#renderModeTabs [data-render-mode="ascii"]');

  log('[qa 12/12] 检查控制台与网络错误…');
  await delay(300);
  check(pageErrors.length === 0, '无页面 JavaScript 错误', pageErrors.slice(0, 3).join(' | '));
  check(networkErrors.length === 0, '无失败的网络资源', networkErrors.slice(0, 4).join(' | '));

  const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1);
  log('\n全部检查通过：' + PASSED.length + ' 项，用时 ' + elapsed + 's');
  if (WARNINGS.length) {
    log('警告：');
    for (const item of WARNINGS) log('  - ' + item);
  }
  log('\n截图：');
  for (const shot of screenshots) log('  ' + shot);
}

function evalJs(expression) {
  if (!cdp) return Promise.reject(new Error('CDP 尚未连接'));
  return cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true
  }, 30000).then((response) => {
    if (response.exceptionDetails) {
      const description = response.exceptionDetails.exception && response.exceptionDetails.exception.description
        ? response.exceptionDetails.exception.description
        : response.exceptionDetails.text || 'page evaluation error';
      throw new Error(description + '\n检查表达式：' + expression.slice(0, 220));
    }
    return response.result ? response.result.value : undefined;
  });
}

async function click(selector) {
  const escaped = JSON.stringify(selector);
  const found = await evalJs(`(() => {
    const element = document.querySelector(${escaped});
    if (!element) return false;
    element.click();
    return true;
  })()`);
  if (!found) throw new Error('找不到可点击元素：' + selector);
  await delay(90);
}

async function getSnapshot() {
  return evalJs('window.ASCII_STUDIO.getSnapshot()');
}

async function waitFor(label, probe, timeout) {
  const started = Date.now();
  let lastError = null;
  while (Date.now() - started < (timeout || 15000)) {
    try {
      const value = await probe();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await delay(110);
  }
  const suffix = lastError ? '（最后一次错误：' + lastError.message.split('\n')[0] + '）' : '';
  throw new Error('等待超时：' + label + suffix);
}

async function waitForSnapshot(predicate, label, timeout) {
  return waitFor(label, async () => {
    const snapshot = await getSnapshot();
    return predicate(snapshot) ? snapshot : null;
  }, timeout);
}

async function setViewport(width, height, deviceScaleFactor, mobile) {
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width,
    height,
    deviceScaleFactor,
    mobile,
    screenWidth: width,
    screenHeight: height
  });
  await delay(220);
}

async function takeScreenshot(name) {
  try {
    await evalJs('(() => { const stack = document.getElementById("toastStack"); if (stack) stack.replaceChildren(); return true; })()');
  } catch (error) {
    /* screenshots should still work if toast cleanup fails */
  }
  await delay(120);
  const response = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false
  }, 30000);
  const file = path.join(SHOTS, name);
  fs.writeFileSync(file, Buffer.from(response.data, 'base64'));
  screenshots.push(file);
  log('  · 截图 ' + file);
}

function findDownloadedFiles() {
  try {
    return fs.readdirSync(DOWNLOADS)
      .filter((name) => !name.endsWith('.crdownload'))
      .map((name) => ({ name, path: path.join(DOWNLOADS, name), stat: fs.statSync(path.join(DOWNLOADS, name)) }))
      .sort((a, b) => a.stat.mtimeMs - b.stat.mtimeMs);
  } catch (error) {
    return [];
  }
}

async function waitForDownload(extension, timeout, optional, nameFilter) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const files = findDownloadedFiles().filter((file) => {
      return file.name.endsWith(extension) && (!nameFilter || nameFilter(file.name));
    });
    if (files.length) return files[files.length - 1];
    await delay(180);
  }
  if (optional) return null;
  throw new Error('等待下载超时：' + extension);
}

async function cleanup() {
  try {
    if (cdp) {
      await Promise.race([
        cdp.send('Browser.close', {}, 4000),
        delay(4000)
      ]).catch(() => {});
      cdp.close();
    }
  } catch (error) {
    /* ignore */
  }
  await delay(500);
  if (edgeProcess && edgeProcess.exitCode == null) {
    if (IS_WINDOWS) {
      await new Promise((resolve) => {
        const killer = spawn('taskkill', ['/PID', String(edgeProcess.pid), '/T', '/F'], { stdio: 'ignore' });
        killer.on('close', resolve);
        killer.on('error', resolve);
        setTimeout(resolve, 3000);
      });
    } else {
      try { edgeProcess.kill(); } catch (error) { /* ignore */ }
    }
  }
  if (serverProcess && serverProcess.exitCode == null) {
    try { serverProcess.kill(); } catch (error) { /* ignore */ }
  }
  await delay(250);
  try {
    if (fs.existsSync(PROFILE)) fs.rmSync(PROFILE, { recursive: true, force: true });
  } catch (error) {
    /* 浏览器可能还短暂持有文件，留着即可 */
  }
}

(async function run() {
  let failure = null;
  try {
    await main();
  } catch (error) {
    failure = error;
    console.error('\n浏览器验收失败：');
    console.error(error && error.stack ? error.stack : error);
    if (pageErrors.length) {
      console.error('\n页面错误：\n' + pageErrors.slice(0, 8).join('\n'));
    }
    if (networkErrors.length) {
      console.error('\n网络错误：\n' + networkErrors.slice(0, 8).join('\n'));
    }
    if (browserLog) {
      console.error('\n浏览器日志（末尾）：\n' + browserLog.slice(-2500));
    }
    if (screenshots.length) {
      console.error('\n已生成的截图：\n' + screenshots.join('\n'));
    }
  } finally {
    await cleanup();
  }
  if (failure) process.exitCode = 1;
})();
