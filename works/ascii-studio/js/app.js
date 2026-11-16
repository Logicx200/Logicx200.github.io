/*!
 * ASCII Studio — application logic
 * 纯浏览器端实现，无外部依赖。
 */
(function () {
  'use strict';

  var core = window.AsciiCore;
  var renderer = window.AsciiRenderer;
  var pixelCore = window.PixelCore;
  var pixelRenderer = window.PixelRenderer;

  var VERSION = '1.0.0';
  var STORAGE_KEY = 'ascii-studio:settings:v1';
  var BACKGROUND = '#080a07';
  var MAX_RECORD_SECONDS = 180;

  var ACCENTS = [
    { id: 'acid', name: '酸性绿', value: '#d7ff64' },
    { id: 'ivory', name: '骨白', value: '#f1eee2' },
    { id: 'cyan', name: '电光青', value: '#75e6ff' },
    { id: 'amber', name: '琥珀', value: '#ffbd6b' },
    { id: 'rose', name: '胭脂粉', value: '#ff92b0' }
  ];

  var SAMPLES = [
    {
      id: 'dunes',
      label: '月升沙丘',
      displayName: 'moonrise-dunes.jpg',
      type: 'image',
      ext: 'JPG',
      src: 'samples/dusk-dunes.jpg',
      thumb: 'samples/thumbs/dusk-dunes.jpg'
    },
    {
      id: 'orb',
      label: '浮游星球',
      displayName: 'orb-sample.jpg',
      type: 'image',
      ext: 'JPG',
      src: 'samples/floating-orb.jpg',
      thumb: 'samples/thumbs/floating-orb.jpg'
    },
    {
      id: 'orbit',
      label: '星环漫游',
      displayName: 'orbital-drift.webm',
      type: 'video',
      ext: 'WEBM',
      src: 'samples/orbital-drift.webm',
      thumb: 'samples/thumbs/orbital-drift.jpg'
    }
  ];

  var DEFAULT_SETTINGS = {
    renderMode: 'ascii',
    imageCols: 140,
    videoCols: 104,
    pixelImageCols: 128,
    pixelVideoCols: 96,
    pixelPalette: 'pico8',
    pixelOutline: true,
    charset: 'classic',
    customChars: '',
    invert: false,
    dither: 'off',
    cellAspect: 0.58,
    colorMode: 'mono',
    accent: '#f1eee2',
    autoLevels: true,
    brightness: 0,
    contrast: 0,
    fps: 24,
    loop: true
  };

  var IMAGE_FILE_RE = /\.(jpe?g|png|gif|webp|avif|bmp|svg)$/i;
  var VIDEO_FILE_RE = /\.(mp4|m4v|webm|mov|ogv|ogg|mkv)$/i;

  var els = {};
  var settings = null;
  var saveTimer = 0;
  var statusTimer = 0;
  var customTimer = 0;
  var toastTimers = new WeakMap();
  var dragDepth = 0;

  var state = {
    kind: null,
    width: 0,
    height: 0,
    duration: 0,
    file: null,
    fileName: '',
    sampleId: null,
    imageEl: null,
    videoEl: null,
    objectUrl: null,
    workCanvas: null,
    workCtx: null,
    grid: null,
    result: null,
    loading: false,
    loadToken: 0,
    lastError: null,
    isPlaying: false,
    renderRaf: 0,
    videoRaf: 0,
    resizeRaf: 0,
    lastVideoRender: 0,
    lastProgressUi: 0,
    fps: 0,
    fpsFrames: 0,
    fpsStamp: 0,
    perfMs: 0,
    lastPerfUi: 0,
    lastGridKey: '',
    videoAutoRange: null,
    videoPixelAutoRange: null,
    canRecord: false,
    recording: false,
    stopRequested: false,
    recorder: null,
    recChunks: [],
    capturedStream: null,
    recordTimer: 0,
    recordStartedAt: 0,
    lockedBox: null
  };

  var demo = {
    running: false,
    raf: 0,
    ctx: null,
    width: 0,
    height: 0,
    cols: 0,
    rows: 0,
    cellW: 0,
    cellH: 0,
    dpr: 1,
    start: 0,
    lastDraw: 0,
    lastCoord: 0,
    reduced: false,
    observer: null,
    chars: null
  };

  /* ======================================================================
   * Bootstrap
   * ====================================================================== */

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }

  function boot() {
    cacheDom();
    closeSourcePeek();

    if (!core || !renderer || !pixelCore || !pixelRenderer || !els.asciiCanvas) {
      showFatal('核心脚本没有正确载入，请确认 js 目录完整。');
      return;
    }

    try {
      demo.chars = Array.from(core.CHARSETS.classic.chars);
      settings = sanitizeSettings(loadStoredSettings());
      buildSampleGrid();
      buildCharsetGrid();
      buildPalette();
      buildPixelPaletteGrid();
      bindEvents();
      syncSettingsToUi();
      initRecordingSupport();
      initResizeObserver();
      initDemo();
      updateActionAvailability();
      updatePlaybackUi();
      setEngineStatus('ready', '本地引擎');
      setPerfLabel('就绪', true);
    } catch (error) {
      console.error('[ASCII Studio] boot failed', error);
      showFatal('初始化失败，请刷新页面重试。');
      return;
    }

    if (location.protocol === 'file:') {
      window.setTimeout(function () {
        toast('正在以 file:// 打开。建议双击 start.cmd 启动本地服务，示例素材与视频会更稳定。', 'info', 6200);
      }, 900);
    }

    exposeDebugApi();
    window.__ASCII_STUDIO_READY__ = true;
    document.documentElement.setAttribute('data-ascii-studio', 'ready');

    var requestedSample = new URLSearchParams(location.search).get('sample');
    if (requestedSample) {
      window.setTimeout(function () {
        loadSample(requestedSample, { silentMissing: true });
      }, 120);
    }
  }

  function cacheDom() {
    els.asciiCanvas = byId('asciiCanvas');
    els.canvasMount = byId('canvasMount');
    els.stageSurface = byId('stageSurface');
    els.stage = byId('stage');
    els.stageHead = byId('stageHead');
    els.stageActions = byId('stageActions');
    els.kindBadge = byId('kindBadge');
    els.kindText = byId('kindText');
    els.kindIcon = byId('kindIcon');
    els.fileName = byId('fileName');
    els.fileMeta = byId('fileMeta');
    els.emptyState = byId('emptyState');
    els.demoFrame = byId('demoFrame');
    els.demoCanvas = byId('demoCanvas');
    els.demoCoord = byId('demoCoord');
    els.livePill = byId('livePill');
    els.liveFps = byId('liveFps');
    els.recPill = byId('recPill');
    els.recTime = byId('recTime');
    els.sourcePeek = byId('sourcePeek');
    els.peekBody = byId('peekBody');
    els.peekClose = byId('peekClose');
    els.peekBtn = byId('peekBtn');
    els.busyOverlay = byId('busyOverlay');
    els.busyText = byId('busyText');

    els.controlsPanel = byId('controlsPanel');
    els.controlsScroll = byId('controlsScroll');
    els.engineStatus = byId('engineStatus');
    els.renderModeTabs = byId('renderModeTabs');
    els.pixelPaletteGrid = byId('pixelPaletteGrid');
    els.pixelPaletteMeta = byId('pixelPaletteMeta');
    els.pixelOutlineToggle = byId('pixelOutlineToggle');
    els.sourceMeta = byId('sourceMeta');
    els.charsetMeta = byId('charsetMeta');
    els.colorMeta = byId('colorMeta');
    els.sampleGrid = byId('sampleGrid');
    els.charsetGrid = byId('charsetGrid');
    els.customWrap = byId('customWrap');
    els.customChars = byId('customChars');
    els.invertToggle = byId('invertToggle');
    els.colsRange = byId('colsRange');
    els.colsOutput = byId('colsOutput');
    els.gridCells = byId('gridCells');
    els.ditherSelect = byId('ditherSelect');
    els.aspectRange = byId('aspectRange');
    els.aspectOutput = byId('aspectOutput');
    els.colorModeSeg = byId('colorModeSeg');
    els.paletteBlock = byId('paletteBlock');
    els.palette = byId('palette');
    els.accentName = byId('accentName');
    els.autoLevelToggle = byId('autoLevelToggle');
    els.brightness = byId('brightness');
    els.brightnessOutput = byId('brightnessOutput');
    els.contrast = byId('contrast');
    els.contrastOutput = byId('contrastOutput');
    els.resetBtn = byId('resetBtn');

    els.dropZone = byId('dropZone');
    els.fileInput = byId('fileInput');
    els.emptyUploadBtn = byId('emptyUploadBtn');
    els.trySampleBtn = byId('trySampleBtn');
    els.dropOverlay = byId('dropOverlay');

    els.peekBtn = byId('peekBtn');
    els.copyBtn = byId('copyBtn');
    els.txtBtn = byId('txtBtn');
    els.pngBtn = byId('pngBtn');

    els.playerBar = byId('playerBar');
    els.playBtn = byId('playBtn');
    els.playIcon = byId('playIcon');
    els.currentTime = byId('currentTime');
    els.durationTime = byId('durationTime');
    els.seekRange = byId('seekRange');
    els.muteBtn = byId('muteBtn');
    els.muteIcon = byId('muteIcon');
    els.loopBtn = byId('loopBtn');
    els.fpsSelect = byId('fpsSelect');
    els.recordBtn = byId('recordBtn');
    els.recordLabel = byId('recordLabel');

    els.gridDims = byId('gridDims');
    els.charCount = byId('charCount');
    els.unitLabel = byId('unitLabel');
    els.perfInfo = byId('perfInfo');
    els.footTip = document.querySelector('.foot-tip');

    els.helpBtn = byId('helpBtn');
    els.helpDialog = byId('helpDialog');
    els.helpClose = byId('helpClose');
    els.helpStart = byId('helpStart');

    els.toastStack = byId('toastStack');
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function showFatal(message) {
    var box = document.createElement('div');
    box.className = 'noscript';
    box.textContent = message;
    document.body.appendChild(box);
  }

  /* ======================================================================
   * Settings
   * ====================================================================== */

  function defaultSettings() {
    return Object.assign({}, DEFAULT_SETTINGS);
  }

  function loadStoredSettings() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return defaultSettings();
      return Object.assign(defaultSettings(), JSON.parse(raw));
    } catch (error) {
      return defaultSettings();
    }
  }

  function sanitizeSettings(input) {
    var next = defaultSettings();
    var source = input && typeof input === 'object' ? input : {};

    next.renderMode = source.renderMode === 'pixel' ? 'pixel' : 'ascii';
    next.imageCols = snapColumns(source.imageCols, DEFAULT_SETTINGS.imageCols);
    next.videoCols = snapColumns(source.videoCols, DEFAULT_SETTINGS.videoCols);
    next.pixelImageCols = snapColumns(source.pixelImageCols, DEFAULT_SETTINGS.pixelImageCols);
    next.pixelVideoCols = snapColumns(source.pixelVideoCols, DEFAULT_SETTINGS.pixelVideoCols);
    next.pixelPalette = pixelCore.PALETTES[source.pixelPalette]
      ? source.pixelPalette
      : DEFAULT_SETTINGS.pixelPalette;
    next.pixelOutline = source.pixelOutline !== false;
    next.charset = source.charset === 'custom' || core.CHARSETS[source.charset]
      ? source.charset
      : DEFAULT_SETTINGS.charset;
    next.customChars = String(source.customChars || '').replace(/[\r\n\t\u0000]/g, '').slice(0, 96);
    next.invert = Boolean(source.invert);
    next.dither = source.dither === 'ordered' || source.dither === 'fs' ? source.dither : 'off';
    next.cellAspect = clamp(Math.round((Number(source.cellAspect) || DEFAULT_SETTINGS.cellAspect) * 100) / 100, 0.45, 0.8);
    next.colorMode = source.colorMode === 'color' ? 'color' : 'mono';
    next.accent = ACCENTS.some(function (item) { return item.value === source.accent; })
      ? source.accent
      : DEFAULT_SETTINGS.accent;
    next.autoLevels = source.autoLevels !== false;
    next.brightness = Math.round(clamp(Number(source.brightness) || 0, -100, 100));
    next.contrast = Math.round(clamp(Number(source.contrast) || 0, -100, 100));
    next.fps = [10, 15, 20, 24, 30].indexOf(Number(source.fps)) >= 0 ? Number(source.fps) : DEFAULT_SETTINGS.fps;
    next.loop = source.loop !== false;
    return next;
  }

  function snapColumns(value, fallback) {
    var number = Number(value);
    if (!Number.isFinite(number)) number = fallback;
    return Math.round(clamp(Math.round(number / 4) * 4, 40, 220));
  }

  function persistSettings() {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(function () {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
      } catch (error) {
        /* 隐私模式或 file:// 下可能不可用，不影响使用 */
      }
    }, 200);
  }

  function activeColumns() {
    var isVideo = state.kind === 'video';
    if (settings.renderMode === 'pixel') {
      return isVideo ? settings.pixelVideoCols : settings.pixelImageCols;
    }
    return isVideo ? settings.videoCols : settings.imageCols;
  }

  function setActiveColumns(value) {
    var columns = snapColumns(value, activeColumns());
    if (settings.renderMode === 'pixel') {
      if (state.kind === 'video') settings.pixelVideoCols = columns;
      else settings.pixelImageCols = columns;
    } else if (state.kind === 'video') {
      settings.videoCols = columns;
    } else {
      settings.imageCols = columns;
    }
    return columns;
  }

  function pixelOptions(autoRange) {
    var options = {
      palette: settings.pixelPalette,
      autoLevels: settings.autoLevels,
      autoClip: 0.015,
      toneGamma: 1.12,
      brightness: (settings.brightness / 100) * 0.45,
      contrast: Math.pow(2, settings.contrast / 100),
      dither: settings.dither,
      ditherStrength: 0.9,
      outline: settings.pixelOutline,
      outlineThreshold: 0.18
    };
    if (autoRange) options.autoRange = autoRange;
    return options;
  }

  function coreOptions(autoRange) {
    var options = {
      charset: core.resolveCharset(settings.charset, settings.customChars),
      color: settings.colorMode === 'color',
      invert: settings.invert,
      brightness: (settings.brightness / 100) * 0.45,
      contrast: Math.pow(2, settings.contrast / 100),
      autoLevels: settings.autoLevels,
      autoClip: 0.015,
      autoGamma: 1.32,
      dither: settings.dither,
      ditherStrength: 0.9
    };
    if (autoRange) options.autoRange = autoRange;
    return options;
  }

  /* ======================================================================
   * Dynamic UI
   * ====================================================================== */

  function buildSampleGrid() {
    els.sampleGrid.innerHTML = SAMPLES.map(function (sample) {
      return (
        '<button type="button" class="sample-card" data-sample="' + escapeHtml(sample.id) + '"' +
        ' data-kind="' + escapeHtml(sample.type) + '"' +
        ' aria-label="载入示例：' + escapeHtml(sample.label) + '"' +
        ' title="载入示例：' + escapeHtml(sample.label) + '">' +
        '<span class="sample-thumb"><img src="' + escapeHtml(sample.thumb) + '" alt="" loading="lazy" decoding="async"></span>' +
        '<span class="sample-meta"><span class="sample-name">' + escapeHtml(sample.label) + '</span>' +
        '<span class="sample-type">' + escapeHtml(sample.ext) + '</span></span>' +
        '</button>'
      );
    }).join('');
  }

  function charsetPreview(chars) {
    var visible = Array.from(String(chars || '')).filter(function (ch) {
      return ch.trim() !== '';
    });
    if (!visible.length) return 'Aa';
    if (visible.length <= 6) return visible.join('');
    var picks = [];
    for (var i = 0; i < 6; i++) {
      picks.push(visible[Math.round((i * (visible.length - 1)) / 5)]);
    }
    return picks.join('');
  }

  function buildCharsetGrid() {
    var entries = core.CHARSET_LIST.concat([
      { id: 'custom', label: '自定义', hint: '你的字符' }
    ]);
    els.charsetGrid.innerHTML = entries.map(function (entry) {
      var preview = entry.id === 'custom' ? 'Aa' : charsetPreview(entry.chars);
      return (
        '<button type="button" class="charset-chip" role="radio" aria-checked="false"' +
        ' data-charset="' + escapeHtml(entry.id) + '" title="' + escapeHtml(entry.label) + '">' +
        '<span class="charset-glyph">' + escapeHtml(preview) + '</span>' +
        '<span class="charset-name">' + escapeHtml(entry.label) + '</span>' +
        '</button>'
      );
    }).join('');
  }

  function buildPalette() {
    els.palette.innerHTML = ACCENTS.map(function (accent) {
      return (
        '<button type="button" class="swatch" role="radio" aria-checked="false"' +
        ' data-accent="' + escapeHtml(accent.value) + '" title="' + escapeHtml(accent.name) + '"' +
        ' aria-label="' + escapeHtml(accent.name) + '" style="--swatch:' + escapeHtml(accent.value) + '"></button>'
      );
    }).join('');
  }

  function buildPixelPaletteGrid() {
    els.pixelPaletteGrid.innerHTML = pixelCore.PALETTE_LIST.map(function (palette) {
      var swatches = palette.colors.map(function (color) {
        return '<i style="--swatch-color:' + escapeHtml(color) + '"></i>';
      }).join('');
      return (
        '<button type="button" class="pixel-preset" data-palette="' + escapeHtml(palette.id) + '"' +
        ' role="radio" aria-checked="false" aria-label="' + escapeHtml(palette.label + '，' + palette.hint) + '"' +
        ' title="' + escapeHtml(palette.label + ' · ' + palette.hint) + '">' +
        '<span class="preset-swatches" style="grid-template-columns:repeat(' + palette.colors.length + ',minmax(0,1fr))">' +
        swatches + '</span>' +
        '<span class="preset-name">' + escapeHtml(palette.label) + '</span>' +
        '<span class="preset-hint">' + escapeHtml(palette.hint) + '</span>' +
        '</button>'
      );
    }).join('');
  }

  function syncSettingsToUi() {
    syncRenderModeUi();
    syncColumnsUi();
    syncCharsetUi();
    syncColorUi();
    syncLookUi();

    els.ditherSelect.value = settings.dither;
    els.invertToggle.checked = settings.invert;
    els.autoLevelToggle.checked = settings.autoLevels;
    els.aspectRange.value = String(settings.cellAspect);
    els.aspectOutput.textContent = settings.cellAspect.toFixed(2);
    updateRangeFill(els.aspectRange);

    els.fpsSelect.value = String(settings.fps);
    els.loopBtn.setAttribute('aria-pressed', String(Boolean(settings.loop)));
    els.loopBtn.classList.toggle('is-active', Boolean(settings.loop));

    syncMuteUi();
    syncRecordTitle();
    updatePlaybackUi();
    updateGridReadouts(true);
  }

  function syncRenderModeUi() {
    var pixel = settings.renderMode === 'pixel';
    document.body.classList.toggle('mode-pixel', pixel);
    document.body.classList.toggle('mode-ascii', !pixel);
    var tabs = els.renderModeTabs.querySelectorAll('.mode-tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].setAttribute('aria-selected', String(tabs[i].getAttribute('data-render-mode') === settings.renderMode));
    }
    syncPixelUi();
    if (state.kind) {
      els.sourceMeta.textContent =
        (state.kind === 'video' ? '视频素材' : '图片素材') +
        (pixel ? ' · 像素' : '');
    }
  }

  function syncPixelUi() {
    var palette = pixelCore.PALETTES[settings.pixelPalette] || pixelCore.PALETTES.pico8;
    els.pixelPaletteMeta.textContent = palette.label + ' · ' + palette.colors.length + ' 色';
    els.pixelOutlineToggle.checked = Boolean(settings.pixelOutline);
    var presets = els.pixelPaletteGrid.querySelectorAll('.pixel-preset');
    for (var i = 0; i < presets.length; i++) {
      presets[i].setAttribute('aria-checked', String(presets[i].getAttribute('data-palette') === settings.pixelPalette));
    }
  }

  function syncColumnsUi() {
    var value = activeColumns();
    var pixel = settings.renderMode === 'pixel';
    var unit = pixel ? '像素' : '字符';
    els.colsRange.value = String(value);
    els.colsOutput.textContent = value + (pixel ? ' px' : ' 列');
    updateRangeFill(els.colsRange);
    if (state.grid) {
      els.gridCells.textContent = formatNumber(state.grid.cols * state.grid.rows) + ' ' + (pixel ? '像素' : '字符');
    } else {
      els.gridCells.textContent = '— ' + unit;
    }
  }

  function syncCharsetUi() {
    var chips = els.charsetGrid.querySelectorAll('.charset-chip');
    for (var i = 0; i < chips.length; i++) {
      chips[i].setAttribute('aria-checked', String(chips[i].getAttribute('data-charset') === settings.charset));
    }

    var isCustom = settings.charset === 'custom';
    els.customWrap.hidden = !isCustom;
    if (document.activeElement !== els.customChars && els.customChars.value !== settings.customChars) {
      els.customChars.value = settings.customChars;
    }
    updateCharsetMeta();
  }

  function updateCharsetMeta() {
    var isCustom = settings.charset === 'custom';
    var validCustom = countUsableChars(settings.customChars) >= 2;
    var resolved = core.resolveCharset(settings.charset, settings.customChars);

    if (isCustom) {
      els.charsetMeta.textContent = validCustom
        ? '自定义 · ' + resolved.length + ' 级'
        : '自定义 · 至少需 2 个字符';
      els.customChars.classList.toggle('is-invalid', !validCustom);
    } else {
      var preset = core.CHARSETS[settings.charset] || core.CHARSETS.classic;
      els.charsetMeta.textContent = preset.label + ' · ' + resolved.length + ' 级';
      els.customChars.classList.remove('is-invalid');
    }

    var customChip = els.charsetGrid.querySelector('.charset-chip[data-charset="custom"] .charset-glyph');
    if (customChip) {
      var customPreview = validCustom ? charsetPreview(settings.customChars) : 'Aa';
      customChip.textContent = customPreview;
    }
  }

  function countUsableChars(value) {
    var seen = Object.create(null);
    var count = 0;
    var iterator = String(value || '')[Symbol.iterator]();
    var step;
    while (!(step = iterator.next()).done) {
      var ch = step.value;
      if (ch === '\n' || ch === '\r' || ch === '\t' || ch === '\u0000') continue;
      if (seen[ch]) continue;
      seen[ch] = true;
      count++;
    }
    return count;
  }

  function syncColorUi() {
    var buttons = els.colorModeSeg.querySelectorAll('button');
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].setAttribute('aria-checked', String(buttons[i].getAttribute('data-color') === settings.colorMode));
    }

    var mono = settings.colorMode === 'mono';
    var accent = ACCENTS.filter(function (item) { return item.value === settings.accent; })[0] || ACCENTS[0];
    if (settings.renderMode === 'pixel') {
      var palette = pixelCore.PALETTES[settings.pixelPalette] || pixelCore.PALETTES.pico8;
      els.colorMeta.textContent = palette.label + ' · ' + palette.colors.length + ' 色';
    } else {
      els.colorMeta.textContent = mono ? '单色' : '原色';
    }
    els.accentName.textContent = mono ? accent.name : '跟随原图';
    els.paletteBlock.classList.toggle('is-disabled', !mono);
    els.paletteBlock.setAttribute('aria-disabled', String(!mono));

    var swatches = els.palette.querySelectorAll('.swatch');
    for (var j = 0; j < swatches.length; j++) {
      swatches[j].setAttribute('aria-checked', String(swatches[j].getAttribute('data-accent') === settings.accent));
    }
  }

  function syncLookUi() {
    els.brightness.value = String(settings.brightness);
    els.brightnessOutput.textContent = formatSigned(settings.brightness);
    updateRangeFill(els.brightness);

    els.contrast.value = String(settings.contrast);
    els.contrastOutput.textContent = formatSigned(settings.contrast);
    updateRangeFill(els.contrast);
  }

  function updateActionAvailability() {
    var hasResult = Boolean(state.result);
    var asciiMode = settings.renderMode === 'ascii';
    els.copyBtn.disabled = !hasResult || !asciiMode;
    els.txtBtn.disabled = !hasResult || !asciiMode;
    els.pngBtn.disabled = !hasResult;
    els.peekBtn.disabled = !state.kind;
    els.copyBtn.title = asciiMode ? '复制字符' : '像素模式没有文本可复制';
    els.copyBtn.setAttribute('aria-label', asciiMode ? '复制字符' : '像素模式没有文本可复制');
    els.txtBtn.title = asciiMode ? '导出 TXT' : '像素模式没有 TXT 输出';
    els.txtBtn.setAttribute('aria-label', asciiMode ? '导出 TXT' : '像素模式没有 TXT 输出');
    els.pngBtn.title = settings.renderMode === 'pixel' ? '导出像素 PNG' : '导出 PNG';
    els.pngBtn.setAttribute('aria-label', settings.renderMode === 'pixel' ? '导出像素 PNG' : '导出 PNG');
    syncRecordTitle();
  }

  function modeWord() {
    return settings.renderMode === 'pixel' ? '像素' : '字符';
  }

  function syncRecordTitle() {
    if (!els.recordBtn) return;
    var word = modeWord();
    if (state.recording) {
      els.recordBtn.disabled = false;
      els.recordBtn.title = '停止录制并保存';
      els.recordBtn.setAttribute('aria-label', '停止录制并保存');
      return;
    }
    els.recordBtn.setAttribute('aria-label', '录制' + word + '动画');
    if (!state.canRecord) {
      els.recordBtn.disabled = true;
      els.recordBtn.title = '当前浏览器不支持 Canvas 录制';
      return;
    }
    els.recordBtn.disabled = !(state.kind === 'video' && state.videoEl && !state.loading);
    if (state.kind !== 'video') {
      els.recordBtn.title = '视频载入后可录制' + word + '动画';
    } else if (state.videoEl && !state.videoEl.muted) {
      els.recordBtn.title = '录制' + word + '动画，包含当前原声';
    } else {
      els.recordBtn.title = '录制' + word + '动画（当前静音，不包含原声）';
    }
  }

  function markActiveSample(sampleId) {
    var cards = els.sampleGrid.querySelectorAll('.sample-card');
    for (var i = 0; i < cards.length; i++) {
      if (sampleId && cards[i].getAttribute('data-sample') === sampleId) {
        cards[i].setAttribute('aria-current', 'true');
      } else {
        cards[i].removeAttribute('aria-current');
      }
    }
  }

  /* ======================================================================
   * Events
   * ====================================================================== */

  function bindEvents() {
    els.fileInput.addEventListener('change', function (event) {
      var file = event.target.files && event.target.files[0];
      event.target.value = '';
      if (file) openFile(file);
    });

    els.dropZone.addEventListener('click', function () { chooseFile(); });
    els.emptyUploadBtn.addEventListener('click', function () { chooseFile(); });

    els.sampleGrid.addEventListener('click', function (event) {
      var card = event.target.closest('.sample-card');
      if (!card) return;
      loadSample(card.getAttribute('data-sample'));
    });

    els.trySampleBtn.addEventListener('click', function () {
      loadSample(SAMPLES[0].id);
    });

    els.renderModeTabs.addEventListener('click', function (event) {
      var tab = event.target.closest('.mode-tab');
      if (!tab) return;
      var mode = tab.getAttribute('data-render-mode') === 'pixel' ? 'pixel' : 'ascii';
      if (mode === settings.renderMode) return;
      settings.renderMode = mode;
      persistSettings();
      syncSettingsToUi();
      updateActionAvailability();
      scheduleRender();
    });

    els.charsetGrid.addEventListener('click', function (event) {
      var chip = event.target.closest('.charset-chip');
      if (!chip) return;
      settings.charset = chip.getAttribute('data-charset');
      persistSettings();
      syncCharsetUi();
      scheduleRender();
    });

    els.pixelPaletteGrid.addEventListener('click', function (event) {
      var preset = event.target.closest('.pixel-preset');
      if (!preset) return;
      settings.pixelPalette = preset.getAttribute('data-palette');
      persistSettings();
      syncPixelUi();
      syncColorUi();
      scheduleRender();
    });

    els.pixelOutlineToggle.addEventListener('change', function () {
      settings.pixelOutline = els.pixelOutlineToggle.checked;
      persistSettings();
      scheduleRender();
    });

    els.customChars.addEventListener('input', function () {
      settings.customChars = els.customChars.value.slice(0, 96);
      updateCharsetMeta();
      persistSettings();
      window.clearTimeout(customTimer);
      customTimer = window.setTimeout(scheduleRender, 140);
    });

    els.invertToggle.addEventListener('change', function () {
      settings.invert = els.invertToggle.checked;
      persistSettings();
      scheduleRender();
    });

    els.colsRange.addEventListener('input', function () {
      setActiveColumns(Number(els.colsRange.value));
      syncColumnsUi();
      persistSettings();
      scheduleRender();
    });

    els.ditherSelect.addEventListener('change', function () {
      settings.dither = els.ditherSelect.value;
      persistSettings();
      scheduleRender();
    });

    els.aspectRange.addEventListener('input', function () {
      settings.cellAspect = clamp(Number(els.aspectRange.value) || 0.58, 0.45, 0.8);
      els.aspectOutput.textContent = settings.cellAspect.toFixed(2);
      updateRangeFill(els.aspectRange);
      persistSettings();
      scheduleRender();
    });

    els.colorModeSeg.addEventListener('click', function (event) {
      var button = event.target.closest('button[data-color]');
      if (!button) return;
      settings.colorMode = button.getAttribute('data-color') === 'mono' ? 'mono' : 'color';
      syncColorUi();
      persistSettings();
      scheduleRender();
    });

    els.palette.addEventListener('click', function (event) {
      var swatch = event.target.closest('.swatch');
      if (!swatch || settings.colorMode !== 'mono') return;
      settings.accent = swatch.getAttribute('data-accent');
      syncColorUi();
      persistSettings();
      scheduleRender();
    });

    els.autoLevelToggle.addEventListener('change', function () {
      settings.autoLevels = els.autoLevelToggle.checked;
      persistSettings();
      scheduleRender();
    });

    els.brightness.addEventListener('input', function () {
      settings.brightness = Math.round(clamp(Number(els.brightness.value), -100, 100));
      els.brightnessOutput.textContent = formatSigned(settings.brightness);
      updateRangeFill(els.brightness);
      persistSettings();
      scheduleRender();
    });

    els.contrast.addEventListener('input', function () {
      settings.contrast = Math.round(clamp(Number(els.contrast.value), -100, 100));
      els.contrastOutput.textContent = formatSigned(settings.contrast);
      updateRangeFill(els.contrast);
      persistSettings();
      scheduleRender();
    });

    els.resetBtn.addEventListener('click', function () {
      var currentMode = settings.renderMode;
      settings = defaultSettings();
      settings.renderMode = currentMode;
      if (state.videoEl) {
        state.videoEl.loop = Boolean(settings.loop);
        if (!state.recording) state.videoEl.muted = true;
      }
      syncSettingsToUi();
      persistSettings();
      scheduleRender();
      updateActionAvailability();
      toast('参数已恢复默认', 'success');
    });

    els.peekBtn.addEventListener('click', function () {
      if (!state.kind) return;
      if (els.sourcePeek.classList.contains('is-visible')) closeSourcePeek();
      else openSourcePeek();
    });

    els.peekClose.addEventListener('click', closeSourcePeek);

    els.copyBtn.addEventListener('click', copyAscii);
    els.txtBtn.addEventListener('click', exportTxt);
    els.pngBtn.addEventListener('click', exportPng);

    els.playBtn.addEventListener('click', togglePlay);
    els.seekRange.addEventListener('input', function () {
      var video = state.videoEl;
      if (!video || state.recording) return;
      var duration = Number.isFinite(video.duration) ? video.duration : 0;
      var target = clamp(Number(els.seekRange.value) || 0, 0, duration);
      video.currentTime = target;
      els.currentTime.textContent = formatTime(target);
      updateRangeFill(els.seekRange);
    });

    els.muteBtn.addEventListener('click', function () {
      var video = state.videoEl;
      if (!video) return;
      video.muted = !video.muted;
      syncMuteUi();
      syncRecordTitle();
    });

    els.loopBtn.addEventListener('click', function () {
      if (state.recording) return;
      settings.loop = !settings.loop;
      if (state.videoEl) state.videoEl.loop = settings.loop;
      els.loopBtn.setAttribute('aria-pressed', String(settings.loop));
      els.loopBtn.classList.toggle('is-active', settings.loop);
      persistSettings();
    });

    els.fpsSelect.addEventListener('change', function () {
      if (state.recording) return;
      var value = Number(els.fpsSelect.value);
      settings.fps = [10, 15, 20, 24, 30].indexOf(value) >= 0 ? value : 24;
      persistSettings();
      toast('渲染帧率已调整为 ' + settings.fps + ' FPS', 'info', 1800);
    });

    els.recordBtn.addEventListener('click', function () {
      if (state.recording) stopRecording('manual');
      else startRecording();
    });

    els.helpBtn.addEventListener('click', openHelp);
    els.helpClose.addEventListener('click', closeHelp);
    els.helpStart.addEventListener('click', closeHelp);
    els.helpDialog.addEventListener('click', function (event) {
      if (event.target === els.helpDialog) closeHelp();
    });

    window.addEventListener('dragenter', handleDragEnter);
    window.addEventListener('dragover', handleDragOver);
    window.addEventListener('dragleave', handleDragLeave);
    window.addEventListener('drop', handleDrop);
    window.addEventListener('dragend', hideDropOverlay);

    document.addEventListener('paste', handlePaste);
    document.addEventListener('keydown', handleKeydown);
  }

  function chooseFile() {
    if (state.loading) {
      toast('正在处理上一个素材，请稍候…', 'info', 1600);
      return;
    }
    if (state.recording) {
      toast('录制中，请先停止录制再更换素材。', 'error');
      return;
    }
    els.fileInput.click();
  }

  function handleDragEnter(event) {
    if (!isFileDrag(event) || state.recording) return;
    event.preventDefault();
    dragDepth++;
    els.dropOverlay.hidden = false;
  }

  function handleDragOver(event) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  }

  function handleDragLeave(event) {
    if (!isFileDrag(event)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) els.dropOverlay.hidden = true;
  }

  function hideDropOverlay() {
    dragDepth = 0;
    els.dropOverlay.hidden = true;
  }

  function handleDrop(event) {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    hideDropOverlay();
    if (state.recording) {
      toast('录制中，请先停止录制再更换素材。', 'error');
      return;
    }
    var file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
    if (file) openFile(file);
  }

  function handlePaste(event) {
    var files = event.clipboardData && event.clipboardData.files;
    if (!files || !files.length) {
      var items = event.clipboardData && event.clipboardData.items;
      if (items) {
        for (var i = 0; i < items.length; i++) {
          if (items[i].kind === 'file' && items[i].type.indexOf('image/') === 0) {
            var pasted = items[i].getAsFile();
            if (pasted) {
              event.preventDefault();
              openFile(pasted);
              return;
            }
          }
        }
      }
      return;
    }
    for (var j = 0; j < files.length; j++) {
      if (classifyFile(files[j])) {
        event.preventDefault();
        openFile(files[j]);
        return;
      }
    }
  }

  function handleKeydown(event) {
    if (event.defaultPrevented || event.isComposing) return;
    var key = event.key;
    var target = event.target;
    var typing = isTypingTarget(target);

    if (key === 'Escape') {
      if (els.helpDialog.open) return; /* 交给原生 dialog 处理 */
      closeSourcePeek();
      return;
    }

    if (els.helpDialog.open) return;
    if (typing) return;

    if (event.code === 'Space' && !event.ctrlKey && !event.metaKey && !event.altKey) {
      if (state.kind === 'video' && !state.recording) {
        event.preventDefault();
        togglePlay();
      }
      return;
    }

    if (!event.ctrlKey && !event.metaKey && !event.altKey) {
      if (key === 'p' || key === 'P') {
        if (state.result) {
          event.preventDefault();
          exportPng();
        }
        return;
      }
      if (key === 'c' || key === 'C') {
        if (state.result && settings.renderMode === 'ascii') {
          event.preventDefault();
          copyAscii();
        }
        return;
      }
      if (key === '?') {
        event.preventDefault();
        openHelp();
      }
    }
  }

  function isTypingTarget(target) {
    if (!target || !target.tagName) return false;
    var tag = target.tagName.toLowerCase();
    return (
      tag === 'input' ||
      tag === 'textarea' ||
      tag === 'select' ||
      tag === 'button' ||
      target.isContentEditable
    );
  }

  function isFileDrag(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) return false;
    for (var i = 0; i < types.length; i++) {
      if (types[i] === 'Files') return true;
    }
    return false;
  }

  /* ======================================================================
   * Help / toast
   * ====================================================================== */

  function openHelp() {
    if (!els.helpDialog) return;
    if (typeof els.helpDialog.showModal === 'function') {
      if (!els.helpDialog.open) els.helpDialog.showModal();
    } else {
      els.helpDialog.setAttribute('open', '');
    }
  }

  function closeHelp() {
    if (!els.helpDialog) return;
    if (typeof els.helpDialog.close === 'function') {
      if (els.helpDialog.open) els.helpDialog.close();
    } else {
      els.helpDialog.removeAttribute('open');
    }
  }

  function toast(message, type, duration) {
    if (!els.toastStack) return;
    var node = document.createElement('div');
    node.className = 'toast' + (type ? ' ' + type : '');
    node.textContent = message;
    node.setAttribute('role', type === 'error' ? 'alert' : 'status');
    els.toastStack.appendChild(node);

    while (els.toastStack.children.length > 4) {
      els.toastStack.removeChild(els.toastStack.firstElementChild);
    }

    node.addEventListener('click', function () {
      dismissToast(node);
    });

    var timer = window.setTimeout(function () {
      dismissToast(node);
    }, duration || 3400);
    toastTimers.set(node, timer);
  }

  function dismissToast(node) {
    if (!node || !node.parentNode || node.classList.contains('is-leaving')) return;
    window.clearTimeout(toastTimers.get(node));
    node.classList.add('is-leaving');
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, 240);
  }

  /* ======================================================================
   * File detection / loaders
   * ====================================================================== */

  function classifyFile(file) {
    if (!file) return null;
    var type = String(file.type || '').toLowerCase();
    if (type.indexOf('image/') === 0) return 'image';
    if (type.indexOf('video/') === 0) return 'video';
    if (IMAGE_FILE_RE.test(file.name || '')) return 'image';
    if (VIDEO_FILE_RE.test(file.name || '')) return 'video';
    return null;
  }

  function openFile(file) {
    if (state.recording) {
      toast('录制中，请先停止录制再更换素材。', 'error');
      return;
    }
    if (state.loading) {
      toast('正在处理上一个素材，请稍候…', 'info', 1800);
      return;
    }
    var kind = classifyFile(file);
    if (!kind) {
      toast('不支持这个文件格式。请选择图片或视频文件。', 'error');
      return;
    }
    if (kind === 'image') {
      loadImage({ file: file, name: file.name, sampleId: null });
    } else {
      loadVideo({ file: file, name: file.name, sampleId: null });
    }
  }

  function loadSample(id, options) {
    var sample = SAMPLES.filter(function (item) { return item.id === id; })[0];
    if (!sample) {
      if (!options || !options.silentMissing) {
        toast('没有找到这个示例素材。', 'error');
      }
      return Promise.resolve(false);
    }
    if (state.recording) {
      toast('录制中，请先停止录制再更换素材。', 'error');
      return Promise.resolve(false);
    }
    if (sample.type === 'video') {
      return loadVideo({
        url: sample.src,
        name: sample.displayName,
        sampleId: sample.id
      });
    }
    return loadImage({
      url: sample.src,
      name: sample.displayName,
      sampleId: sample.id
    });
  }

  function loadImage(source) {
    if (state.loading) {
      return Promise.resolve(false);
    }

    state.loading = true;
    state.lastError = null;
    var token = ++state.loadToken;
    var objectUrl = source.file ? URL.createObjectURL(source.file) : null;
    var src = objectUrl || source.url;
    var committed = false;
    var image = new Image();
    image.decoding = 'async';
    image.alt = '原始图片预览';
    image.className = 'peek-image';

    showBusy(source.sampleId ? '正在载入示例图片…' : '正在解码图片…');
    setEngineStatus('busy', '解码中');

    image.src = src;

    return waitForImage(image)
      .then(function () {
        if (token !== state.loadToken) {
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          return false;
        }
        if (!image.naturalWidth || !image.naturalHeight) {
          throw new Error('图片尺寸无效');
        }

        releaseCurrentMedia();
        state.kind = 'image';
        state.imageEl = image;
        state.objectUrl = objectUrl;
        state.file = source.file || null;
        state.fileName = source.name || '未命名图片';
        state.sampleId = source.sampleId || null;
        state.width = image.naturalWidth;
        state.height = image.naturalHeight;
        state.duration = 0;
        committed = true;

        els.peekBody.appendChild(image);
        enterMediaMode('image');
        updateMediaInfo();
        syncSettingsToUi();
        markActiveSample(state.sampleId);
        renderImage();
        updateActionAvailability();
        setEngineStatus('ready', '本地引擎');
        return true;
      })
      .catch(function (error) {
        if (!committed) {
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          if (token !== state.loadToken) return false;
          state.lastError = error && error.message ? error.message : String(error);
          handleLoadError(error, 'image');
        } else {
          console.error('[ASCII Studio] image post-load error', error);
          toast('图片已载入，但后期处理出现了一点问题。', 'error', 4200);
        }
        return false;
      })
      .then(function (result) {
        state.loading = false;
        els.busyOverlay.hidden = true;
        return result;
      });
  }

  function loadVideo(source) {
    if (state.loading) {
      return Promise.resolve(false);
    }

    state.loading = true;
    state.lastError = null;
    var token = ++state.loadToken;
    var objectUrl = source.file ? URL.createObjectURL(source.file) : null;
    var src = objectUrl || source.url;
    var committed = false;
    var video = document.createElement('video');
    video.className = 'peek-video';
    video.playsInline = true;
    video.setAttribute('playsinline', '');
    video.preload = 'auto';
    video.muted = true;
    video.loop = Boolean(settings.loop);
    video.setAttribute('aria-label', '原始视频');
    attachVideoEvents(video);

    if (state.videoEl && !state.videoEl.paused) {
      try { state.videoEl.pause(); } catch (error) { /* ignore */ }
    }

    showBusy(source.sampleId ? '正在载入示例视频…' : '正在读取视频…');
    setEngineStatus('busy', '解码中');
    video.src = src;

    return waitForVideo(video)
      .then(function () {
        if (token !== state.loadToken) {
          cleanupVideoElement(video, objectUrl);
          return false;
        }
        if (!video.videoWidth || !video.videoHeight) {
          throw new Error('视频尺寸无效');
        }

        releaseCurrentMedia();
        state.kind = 'video';
        state.videoEl = video;
        state.objectUrl = objectUrl;
        state.file = source.file || null;
        state.fileName = source.name || '未命名视频';
        state.sampleId = source.sampleId || null;
        state.width = video.videoWidth;
        state.height = video.videoHeight;
        state.duration = Number.isFinite(video.duration) ? video.duration : 0;
        committed = true;

        els.peekBody.appendChild(video);
        enterMediaMode('video');
        updateMediaInfo();
        syncSettingsToUi();
        syncVideoSettingsUi();
        markActiveSample(state.sampleId);
        updatePlaybackUi();
        syncProgress(true);
        renderVideoFrame();
        updateActionAvailability();
        setEngineStatus('ready', '本地引擎');

        var playPromise = video.play();
        if (playPromise && typeof playPromise.catch === 'function') {
          playPromise.catch(function (error) {
            if (error && error.name !== 'NotAllowedError') {
              console.warn('[ASCII Studio] autoplay blocked', error);
            }
            updatePlaybackUi();
          });
        }
        return true;
      })
      .catch(function (error) {
        if (!committed) {
          cleanupVideoElement(video, objectUrl);
          if (token !== state.loadToken) return false;
          state.lastError = error && error.message ? error.message : String(error);
          handleLoadError(error, 'video');
        } else {
          console.error('[ASCII Studio] video post-load error', error);
          toast('视频已载入，但后期处理出现了一点问题。', 'error', 4200);
        }
        return false;
      })
      .then(function (result) {
        state.loading = false;
        els.busyOverlay.hidden = true;
        syncRecordTitle();
        return result;
      });
  }

  function waitForImage(image) {
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = 0;

      function cleanup() {
        settled = true;
        window.clearTimeout(timer);
        image.removeEventListener('load', onLoad);
        image.removeEventListener('error', onError);
      }

      function finish(callback, value) {
        if (settled) return;
        cleanup();
        callback(value);
      }

      function onLoad() {
        finish(resolve);
      }

      function onError() {
        finish(reject, new Error('图片格式无法解码'));
      }

      if (image.complete) {
        if (image.naturalWidth > 0) {
          cleanup();
          resolve();
        } else {
          cleanup();
          reject(new Error('图片格式无法解码'));
        }
        return;
      }

      image.addEventListener('load', onLoad);
      image.addEventListener('error', onError);
      timer = window.setTimeout(function () {
        finish(reject, new Error('图片解码超时'));
      }, 30000);
    });
  }

  function waitForVideo(video) {
    return new Promise(function (resolve, reject) {
      var settled = false;
      var timer = 0;

      function cleanup() {
        settled = true;
        window.clearTimeout(timer);
        video.removeEventListener('loadeddata', checkReady);
        video.removeEventListener('canplay', checkReady);
        video.removeEventListener('error', onError);
      }

      function checkReady() {
        if (settled) return;
        if (video.readyState >= 2 && video.videoWidth > 0) {
          cleanup();
          resolve();
        }
      }

      function onError() {
        if (settled) return;
        cleanup();
        reject(new Error(describeVideoError(video)));
      }

      if (video.readyState >= 2 && video.videoWidth > 0) {
        resolve();
        return;
      }

      video.addEventListener('loadeddata', checkReady);
      video.addEventListener('canplay', checkReady);
      video.addEventListener('error', onError);
      timer = window.setTimeout(function () {
        if (settled) return;
        cleanup();
        reject(new Error('视频载入超时，请换一个文件试试'));
      }, 30000);
    });
  }

  function cleanupVideoElement(video, objectUrl) {
    try {
      video.pause();
      video.removeAttribute('src');
      video.load();
    } catch (error) {
      /* ignore */
    }
    if (video.parentNode) video.parentNode.removeChild(video);
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  }

  function describeVideoError(video) {
    var code = video && video.error ? video.error.code : 0;
    if (code === 4) return '浏览器无法解码这个视频。建议使用 MP4 (H.264) 或 WebM (VP9) 格式。';
    if (code === 3) return '视频解码失败，文件可能已损坏。';
    if (code === 2) return '视频读取中断，请重试。';
    return '无法载入这个视频，请换一个文件试试。';
  }

  /* ======================================================================
   * Media mode / metadata
   * ====================================================================== */

  function enterMediaMode(kind) {
    stopDemo();
    document.body.classList.add('has-media');
    els.emptyState.hidden = true;
    els.stageHead.hidden = false;
    els.playerBar.hidden = kind !== 'video';
    els.kindBadge.classList.toggle('is-video', kind === 'video');
    setIcon(els.kindIcon, kind === 'video' ? 'film' : 'image');
    els.kindText.textContent = kind === 'video' ? 'VIDEO' : 'IMAGE';
    els.livePill.hidden = true;
    els.recPill.hidden = true;
    if (els.footTip) {
      els.footTip.innerHTML = kind === 'video'
        ? '拖拽即可替换素材 <span class="keycap">SPACE</span> 播放 / 暂停'
        : '拖拽即可替换素材 <span class="keycap">P</span> 保存 PNG';
    }
  }

  function updateMediaInfo() {
    var isVideo = state.kind === 'video';
    els.fileName.textContent = state.fileName || '未命名素材';
    els.fileName.title = state.fileName || '未命名素材';
    var parts = [state.width + ' × ' + state.height];
    if (isVideo) {
      state.duration = state.videoEl && Number.isFinite(state.videoEl.duration) ? state.videoEl.duration : state.duration;
      parts.push(formatTime(state.duration));
    }
    if (state.file) parts.push(formatBytes(state.file.size));
    if (state.sampleId) parts.push('内置示例');
    els.fileMeta.textContent = parts.join('  ·  ');
    els.sourceMeta.textContent =
      (isVideo ? '视频素材' : '图片素材') +
      (settings.renderMode === 'pixel' ? ' · 像素' : '');
    document.title = (state.fileName ? state.fileName + ' — ' : '') + 'ASCII Studio';
  }

  function releaseCurrentMedia() {
    stopVideoLoop();

    if (state.videoEl) {
      var video = state.videoEl;
      try {
        video.pause();
        video.removeAttribute('src');
        video.load();
      } catch (error) {
        /* ignore */
      }
      if (video.parentNode) video.parentNode.removeChild(video);
    }

    if (state.imageEl && state.imageEl.parentNode) {
      state.imageEl.parentNode.removeChild(state.imageEl);
    }

    if (state.objectUrl) {
      URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = null;
    }

    els.peekBody.replaceChildren();
    closeSourcePeek();

    state.kind = null;
    state.width = 0;
    state.height = 0;
    state.duration = 0;
    state.file = null;
    state.fileName = '';
    state.sampleId = null;
    state.imageEl = null;
    state.videoEl = null;
    state.grid = null;
    state.result = null;
    state.lastGridKey = '';
    state.videoAutoRange = null;
    state.videoPixelAutoRange = null;
    state.perfMs = 0;
    state.isPlaying = false;
    state.lastError = null;
  }

  function setIcon(svg, name) {
    if (!svg) return;
    var use = svg.querySelector('use');
    if (use) use.setAttribute('href', '#i-' + name);
  }

  /* ======================================================================
   * Rendering
   * ====================================================================== */

  function getWorkContext(cols, rows) {
    if (!state.workCanvas) {
      state.workCanvas = document.createElement('canvas');
      state.workCtx = state.workCanvas.getContext('2d', { willReadFrequently: true });
    }
    if (state.workCanvas.width !== cols || state.workCanvas.height !== rows) {
      state.workCanvas.width = cols;
      state.workCanvas.height = rows;
    }
    var ctx = state.workCtx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    return ctx;
  }

  function scheduleRender() {
    if (!state.kind) return;
    if (state.renderRaf) return;
    state.renderRaf = window.requestAnimationFrame(function () {
      state.renderRaf = 0;
      renderNow();
    });
  }

  function renderNow() {
    if (state.kind === 'image') renderImage();
    else if (state.kind === 'video') renderVideoFrame();
  }

  function renderImage() {
    if (!state.imageEl || state.kind !== 'image') return;
    try {
      var pixelMode = settings.renderMode === 'pixel';
      var grid = core.computeGrid(
        state.width,
        state.height,
        activeColumns(),
        pixelMode ? 1 : settings.cellAspect
      );
      var ctx = getWorkContext(grid.cols, grid.rows);
      ctx.fillStyle = BACKGROUND;
      ctx.fillRect(0, 0, grid.cols, grid.rows);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(state.imageEl, 0, 0, grid.cols, grid.rows);

      var imageData = ctx.getImageData(0, 0, grid.cols, grid.rows);
      var start = performance.now();
      var result = pixelMode
        ? pixelCore.convertPixels(imageData, pixelOptions())
        : core.convert(imageData, coreOptions());
      var elapsed = performance.now() - start;

      state.result = result;
      state.grid = { cols: grid.cols, rows: grid.rows };
      state.lastGridKey = grid.cols + 'x' + grid.rows;
      state.perfMs = elapsed;
      paintPreview();
      updateGridReadouts(true);
      setPerfLabel(elapsed.toFixed(1) + ' ms', true);
      updateActionAvailability();
      setEngineStatus('ready', '本地引擎');
    } catch (error) {
      state.lastError = error && error.message ? error.message : String(error);
      console.error('[ASCII Studio] image render failed', error);
      setEngineStatus('error', '渲染失败');
      toast('字符画渲染失败：' + (error && error.message ? error.message : '未知错误'), 'error', 5200);
    }
  }

  function renderVideoFrame() {
    var video = state.videoEl;
    if (!video || state.kind !== 'video') return;
    if (video.readyState < 2 || !video.videoWidth) return;

    try {
      var pixelMode = settings.renderMode === 'pixel';
      var grid = core.computeGrid(
        state.width,
        state.height,
        activeColumns(),
        pixelMode ? 1 : settings.cellAspect
      );
      var ctx = getWorkContext(grid.cols, grid.rows);
      ctx.fillStyle = '#000000';
      ctx.fillRect(0, 0, grid.cols, grid.rows);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'medium';
      ctx.drawImage(video, 0, 0, grid.cols, grid.rows);

      var imageData = ctx.getImageData(0, 0, grid.cols, grid.rows);
      var start = performance.now();
      // Keep auto-levels stable across video frames to avoid exposure flicker.
      var result;
      if (pixelMode) {
        result = pixelCore.convertPixels(imageData, pixelOptions(state.videoPixelAutoRange));
        if (!state.videoPixelAutoRange && result.autoRange) {
          state.videoPixelAutoRange = result.autoRange;
        }
      } else {
        result = core.convert(imageData, coreOptions(state.videoAutoRange));
        if (!state.videoAutoRange && result.autoRange) {
          state.videoAutoRange = result.autoRange;
        }
      }
      var elapsed = performance.now() - start;
      var hadResult = Boolean(state.result);

      state.result = result;
      state.grid = { cols: grid.cols, rows: grid.rows };
      state.perfMs = state.perfMs > 0 ? state.perfMs * 0.72 + elapsed * 0.28 : elapsed;
      paintPreview();
      var gridKey = grid.cols + 'x' + grid.rows;
      if (state.lastGridKey !== gridKey) {
        state.lastGridKey = gridKey;
        updateGridReadouts(false);
      }
      if (!hadResult) updateActionAvailability();
      setPerfLabel(null, false);
    } catch (error) {
      state.lastError = error && error.message ? error.message : String(error);
      console.error('[ASCII Studio] video render failed', error);
      stopVideoLoop();
      setEngineStatus('error', '渲染失败');
      toast('视频渲染失败：' + (error && error.message ? error.message : '未知错误'), 'error', 5000);
    }
  }

  function paintPreview() {
    if (!state.result) return;
    var boxWidth = els.canvasMount.clientWidth;
    var boxHeight = els.canvasMount.clientHeight;

    if (state.recording && state.lockedBox) {
      boxWidth = state.lockedBox.width;
      boxHeight = state.lockedBox.height;
    }

    if (boxWidth < 4 || boxHeight < 4) return;

    if (settings.renderMode === 'pixel') {
      els.asciiCanvas.style.imageRendering = 'pixelated';
      pixelRenderer.paintPreview(els.asciiCanvas, state.result, {
        boxWidth: boxWidth,
        boxHeight: boxHeight,
        dpr: Math.min(window.devicePixelRatio || 1, 2)
      });
      return;
    }

    els.asciiCanvas.style.imageRendering = 'auto';
    var maxDpr = state.kind === 'video' ? 1.55 : 2;
    var dpr = Math.min(window.devicePixelRatio || 1, maxDpr);

    renderer.paintPreview(els.asciiCanvas, state.result, {
      boxWidth: boxWidth,
      boxHeight: boxHeight,
      cellAspect: settings.cellAspect,
      dpr: dpr,
      colorMode: settings.colorMode,
      accent: settings.accent,
      background: BACKGROUND
    });
  }

  function updateGridReadouts(force) {
    var pixel = settings.renderMode === 'pixel';
    var unit = pixel ? '像素' : '字符';
    els.unitLabel.textContent = unit;
    if (!state.grid) {
      els.gridDims.textContent = '—';
      els.charCount.textContent = '—';
      els.gridCells.textContent = '— ' + unit;
      return;
    }
    var cells = state.grid.cols * state.grid.rows;
    els.gridDims.textContent = state.grid.cols + ' × ' + state.grid.rows;
    els.charCount.textContent = formatNumber(cells);
    if (force || !els.gridCells.textContent || els.gridCells.textContent.indexOf('—') === 0) {
      els.gridCells.textContent = formatNumber(cells) + ' ' + unit;
    }
    els.colsOutput.textContent = activeColumns() + (pixel ? ' px' : ' 列');
    els.asciiCanvas.setAttribute(
      'aria-label',
      pixel
        ? '复古像素画预览，' + state.grid.cols + ' × ' + state.grid.rows + ' 像素'
        : 'ASCII 字符画预览，' + state.grid.cols + ' 列 ' + state.grid.rows + ' 行'
    );
    updateRangeFill(els.colsRange);
  }

  function initResizeObserver() {
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', function () {
        if (state.result) paintPreview();
      });
      return;
    }
    var observer = new ResizeObserver(function () {
      if (state.recording || !state.result) return;
      window.cancelAnimationFrame(state.resizeRaf);
      state.resizeRaf = window.requestAnimationFrame(function () {
        state.resizeRaf = 0;
        if (!state.recording) paintPreview();
      });
    });
    observer.observe(els.canvasMount);
    if (els.stageHead) observer.observe(els.stageHead);
  }

  /* ======================================================================
   * Video playback
   * ====================================================================== */

  function attachVideoEvents(video) {
    function active() {
      return state.videoEl === video;
    }

    video.addEventListener('play', function () {
      if (!active()) return;
      state.isPlaying = true;
      updatePlaybackUi();
      startVideoLoop();
      syncRecordTitle();
    });

    video.addEventListener('playing', function () {
      if (!active()) return;
      state.isPlaying = true;
      updatePlaybackUi();
    });

    video.addEventListener('pause', function () {
      if (!active()) return;
      state.isPlaying = false;
      stopVideoLoop();
      updatePlaybackUi();
      syncProgress(true);
    });

    video.addEventListener('durationchange', function () {
      if (!active()) return;
      state.duration = Number.isFinite(video.duration) ? video.duration : 0;
      updateMediaInfo();
      syncProgress(true);
    });

    video.addEventListener('timeupdate', function () {
      if (!active()) return;
      syncProgress(false);
    });

    video.addEventListener('seeked', function () {
      if (!active()) return;
      syncProgress(true);
      if (video.paused) renderVideoFrame();
    });

    video.addEventListener('ended', function () {
      if (!active()) return;
      state.isPlaying = false;
      stopVideoLoop();
      updatePlaybackUi();
      syncProgress(true);
      if (state.recording) stopRecording('ended');
      setPerfLabel(null, true);
    });

    video.addEventListener('volumechange', function () {
      if (!active()) return;
      syncMuteUi();
      syncRecordTitle();
    });

    video.addEventListener('error', function () {
      if (!active()) return;
      toast(describeVideoError(video), 'error', 5000);
      setEngineStatus('error', '播放失败');
    });
  }

  function syncVideoSettingsUi() {
    els.fpsSelect.value = String(settings.fps);
    els.loopBtn.setAttribute('aria-pressed', String(Boolean(settings.loop)));
    els.loopBtn.classList.toggle('is-active', Boolean(settings.loop));
    syncMuteUi();
    updatePlaybackUi();
    syncProgress(true);
    syncRecordTitle();
  }

  function syncProgress(force) {
    var video = state.videoEl;
    if (!video) return;
    var duration = Number.isFinite(video.duration) ? video.duration : 0;
    var current = Number.isFinite(video.currentTime) ? video.currentTime : 0;
    els.currentTime.textContent = formatTime(current);
    els.durationTime.textContent = formatTime(duration);
    els.seekRange.max = String(Math.max(0.01, duration));
    if (!state.recording || force) {
      els.seekRange.value = String(clamp(current, 0, Math.max(0.01, duration)));
    }
    updateRangeFill(els.seekRange);
  }

  function updatePlaybackUi() {
    var video = state.videoEl;
    var playing = Boolean(video && !video.paused && !video.ended);
    state.isPlaying = playing;
    setIcon(els.playIcon, playing ? 'pause' : 'play');
    els.playBtn.setAttribute('aria-label', playing ? '暂停' : '播放');
    els.playBtn.title = playing ? '暂停' : '播放';
    var showLive = state.kind === 'video' && playing;
    els.livePill.hidden = !showLive;
    if (showLive) {
      els.liveFps.textContent = Math.round(state.fps || settings.fps) + ' FPS';
      state.lastProgressUi = performance.now();
    }
  }

  function syncMuteUi() {
    var video = state.videoEl;
    var muted = video ? video.muted : true;
    setIcon(els.muteIcon, muted ? 'mute' : 'volume');
    els.muteBtn.setAttribute('aria-pressed', String(muted));
    els.muteBtn.setAttribute('aria-label', muted ? '取消静音' : '静音');
    els.muteBtn.title = muted ? '声音：关' : '声音：开';
  }

  function togglePlay() {
    var video = state.videoEl;
    if (!video || state.recording) return;
    if (video.paused || video.ended) {
      if (video.ended) {
        try { video.currentTime = 0; } catch (error) { /* ignore */ }
      }
      var playPromise = video.play();
      if (playPromise && typeof playPromise.catch === 'function') {
        playPromise.catch(function (error) {
          console.warn('[ASCII Studio] play failed', error);
          toast('无法播放这个视频，请尝试其他编码格式。', 'error');
        });
      }
    } else {
      video.pause();
    }
  }

  function startVideoLoop() {
    if (state.videoRaf) return;
    state.fpsFrames = 0;
    state.fpsStamp = performance.now();
    state.lastVideoRender = 0;

    function tick(now) {
      var video = state.videoEl;
      if (!video || state.kind !== 'video' || video.paused || video.ended) {
        state.videoRaf = 0;
        return;
      }
      state.videoRaf = window.requestAnimationFrame(tick);

      var interval = 1000 / Math.max(1, settings.fps);
      if (now - state.lastVideoRender >= interval - 1) {
        state.lastVideoRender = now;
        renderVideoFrame();
        state.fpsFrames++;
      }

      if (now - state.lastProgressUi > 100) {
        state.lastProgressUi = now;
        syncProgress(false);
      }

      if (now - state.fpsStamp >= 600) {
        state.fps = (state.fpsFrames * 1000) / (now - state.fpsStamp);
        state.fpsFrames = 0;
        state.fpsStamp = now;
        if (!els.livePill.hidden) {
          els.liveFps.textContent = Math.round(state.fps) + ' FPS';
        }
        setPerfLabel(null, true);
      }
    }

    state.videoRaf = window.requestAnimationFrame(tick);
  }

  function stopVideoLoop() {
    if (state.videoRaf) {
      window.cancelAnimationFrame(state.videoRaf);
      state.videoRaf = 0;
    }
    state.fps = 0;
    setPerfLabel(null, true);
  }

  function seekVideoToStart(video) {
    return new Promise(function (resolve) {
      var done = false;
      var timer = 0;

      function finish() {
        if (done) return;
        done = true;
        window.clearTimeout(timer);
        video.removeEventListener('seeked', finish);
        resolve();
      }

      if (!Number.isFinite(video.duration) || video.currentTime < 0.015) {
        try { video.currentTime = 0; } catch (error) { /* ignore */ }
        finish();
        return;
      }

      video.addEventListener('seeked', finish);
      timer = window.setTimeout(finish, 1200);
      try {
        video.currentTime = 0;
      } catch (error) {
        finish();
      }
    });
  }

  /* ======================================================================
   * Recording
   * ====================================================================== */

  function initRecordingSupport() {
    var hasCapture = typeof HTMLCanvasElement !== 'undefined' &&
      typeof HTMLCanvasElement.prototype.captureStream === 'function';
    var hasRecorder = typeof window.MediaRecorder === 'function';
    var hasStream = typeof window.MediaStream === 'function';
    state.canRecord = Boolean(hasCapture && hasRecorder && hasStream);
    syncRecordTitle();
  }

  async function startRecording() {
    if (state.recording || state.kind !== 'video' || !state.videoEl) return;
    if (!state.canRecord) {
      toast('当前浏览器不支持字符动画录制，请使用新版 Edge 或 Chrome。', 'error', 5000);
      return;
    }
    if (state.loading) {
      toast('素材仍在载入，请稍候。', 'info');
      return;
    }

    var video = state.videoEl;

    try {
      video.pause();
      video.loop = false;
      await seekVideoToStart(video);
      renderVideoFrame();
      if (!state.result) throw new Error('当前画面还未准备好');

      state.recChunks = [];
      state.stopRequested = false;
      state.lockedBox = {
        width: els.canvasMount.clientWidth,
        height: els.canvasMount.clientHeight
      };

      var canvasStream = els.asciiCanvas.captureStream(settings.fps);
      var audioTracks = [];
      if (!video.muted) {
        audioTracks = captureVideoAudio(video);
      }

      var tracks = canvasStream.getVideoTracks().slice();
      for (var i = 0; i < audioTracks.length; i++) tracks.push(audioTracks[i]);
      var mixedStream = new MediaStream(tracks);
      state.capturedStream = mixedStream;

      var mimeType = chooseRecorderMime(audioTracks.length > 0);
      var recorder;
      if (mimeType) {
        recorder = new MediaRecorder(mixedStream, {
          mimeType: mimeType,
          videoBitsPerSecond: 8000000
        });
      } else {
        recorder = new MediaRecorder(mixedStream);
      }

      state.recorder = recorder;
      state.recording = true;
      state.recordStartedAt = performance.now();
      state.recorder.onstop = finalizeRecording;
      state.recorder.ondataavailable = function (event) {
        if (event.data && event.data.size > 0) state.recChunks.push(event.data);
      };
      state.recorder.onerror = function (event) {
        console.error('[ASCII Studio] recorder error', event);
        toast('录制过程中发生错误，已停止。', 'error', 4500);
        stopRecording('error');
      };

      setRecordingUi(true);
      recorder.start(250);
      startRecordClock();

      try {
        await video.play();
      } catch (error) {
        console.warn('[ASCII Studio] recording play failed', error);
        toast('无法开始播放，录制已取消。', 'error');
        stopRecording('play-failed');
      }
    } catch (error) {
      console.error('[ASCII Studio] start recording failed', error);
      cleanupRecordingState();
      setRecordingUi(false);
      toast('无法开始录制：' + (error && error.message ? error.message : '未知错误'), 'error', 5000);
    }
  }

  function captureVideoAudio(video) {
    try {
      var stream = typeof video.captureStream === 'function'
        ? video.captureStream()
        : (typeof video.mozCaptureStream === 'function' ? video.mozCaptureStream() : null);
      return stream ? stream.getAudioTracks() : [];
    } catch (error) {
      console.warn('[ASCII Studio] audio capture unavailable', error);
      return [];
    }
  }

  function chooseRecorderMime(hasAudio) {
    if (typeof window.MediaRecorder === 'undefined' || !window.MediaRecorder.isTypeSupported) {
      return '';
    }
    var candidates = hasAudio
      ? [
          'video/webm;codecs=vp9,opus',
          'video/webm;codecs=vp8,opus',
          'video/webm;codecs=vp9',
          'video/webm;codecs=vp8',
          'video/webm',
          'video/mp4'
        ]
      : [
          'video/webm;codecs=vp9',
          'video/webm;codecs=vp8',
          'video/webm',
          'video/mp4'
        ];
    for (var i = 0; i < candidates.length; i++) {
      if (window.MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
    }
    return '';
  }

  function stopRecording(reason) {
    if (!state.recording || state.stopRequested) return;
    state.stopRequested = true;
    window.clearInterval(state.recordTimer);
    state.recordTimer = 0;

    if (state.videoEl && !state.videoEl.paused) {
      try { state.videoEl.pause(); } catch (error) { /* ignore */ }
    }

    var recorder = state.recorder;
    if (recorder && recorder.state !== 'inactive') {
      try {
        recorder.stop();
        return;
      } catch (error) {
        console.warn('[ASCII Studio] recorder stop failed', error);
      }
    }
    finalizeRecording(reason);
  }

  function finalizeRecording() {
    window.clearInterval(state.recordTimer);
    state.recordTimer = 0;

    var chunks = state.recChunks.slice();
    var recorder = state.recorder;
    var mimeType = (recorder && recorder.mimeType) || (chunks[0] && chunks[0].type) || 'video/webm';

    state.recChunks = [];
    state.recorder = null;
    state.recording = false;
    state.stopRequested = false;
    state.lockedBox = null;

    if (state.capturedStream) {
      try {
        state.capturedStream.getTracks().forEach(function (track) { track.stop(); });
      } catch (error) {
        /* ignore */
      }
      state.capturedStream = null;
    }

    if (state.videoEl) {
      state.videoEl.loop = Boolean(settings.loop);
    }

    setRecordingUi(false);
    updateActionAvailability();

    if (!chunks.length) {
      toast('录制没有产生可保存的画面，请重试。', 'error', 4500);
      return;
    }

    var blob = new Blob(chunks, { type: mimeType });
    if (!blob.size) {
      toast('录制文件为空，请重试。', 'error');
      return;
    }
    var extension = mimeType.indexOf('mp4') >= 0 ? 'mp4' : 'webm';
    downloadBlob(
      blob,
      safeBaseName(state.fileName) + '-' + (settings.renderMode === 'pixel' ? 'pixel' : 'ascii') + '.' + extension
    );
    toast(modeWord() + '动画已录制并保存（' + formatBytes(blob.size) + '）', 'success', 4600);
  }

  function cleanupRecordingState() {
    window.clearInterval(state.recordTimer);
    state.recordTimer = 0;
    var recorder = state.recorder;
    if (recorder) {
      recorder.onstop = null;
      recorder.ondataavailable = null;
      recorder.onerror = null;
      if (recorder.state !== 'inactive') {
        try { recorder.stop(); } catch (error) { /* ignore */ }
      }
    }
    if (state.capturedStream) {
      try {
        state.capturedStream.getTracks().forEach(function (track) { track.stop(); });
      } catch (error) {
        /* ignore */
      }
    }
    state.recorder = null;
    state.capturedStream = null;
    state.recChunks = [];
    state.recording = false;
    state.stopRequested = false;
    state.lockedBox = null;
    if (state.videoEl) state.videoEl.loop = Boolean(settings.loop);
  }

  function setRecordingUi(active) {
    document.body.classList.toggle('is-recording', active);
    els.recordBtn.classList.toggle('is-recording', active);
    els.recordLabel.textContent = active ? '停止' : '录制';
    els.recordBtn.setAttribute('aria-label', active ? '停止录制并保存' : '录制' + modeWord() + '动画');
    els.recPill.hidden = !active;

    if (active) {
      els.recTime.textContent = '00:00';
    }

    try {
      els.controlsPanel.inert = active;
      els.stageActions.inert = active;
    } catch (error) {
      /* 兼容旧浏览器 */
    }

    [els.playBtn, els.seekRange, els.muteBtn, els.loopBtn, els.fpsSelect].forEach(function (node) {
      if (node) node.disabled = active;
    });

    if (!active) syncRecordTitle();
    updatePlaybackUi();
  }

  function startRecordClock() {
    window.clearInterval(state.recordTimer);
    state.recordTimer = window.setInterval(function () {
      if (!state.recording) return;
      var elapsed = (performance.now() - state.recordStartedAt) / 1000;
      els.recTime.textContent = formatTime(elapsed);
      if (elapsed >= MAX_RECORD_SECONDS) {
        toast('已达到 3 分钟录制上限，正在保存。', 'info', 3500);
        stopRecording('time-limit');
      }
    }, 250);
  }

  /* ======================================================================
   * Source peek
   * ====================================================================== */

  function openSourcePeek() {
    if (!state.kind) return;
    els.sourcePeek.classList.add('is-visible');
    els.sourcePeek.setAttribute('aria-hidden', 'false');
    if ('inert' in els.sourcePeek) els.sourcePeek.inert = false;
    els.peekBtn.setAttribute('aria-pressed', 'true');
  }

  function closeSourcePeek() {
    els.sourcePeek.classList.remove('is-visible');
    els.sourcePeek.setAttribute('aria-hidden', 'true');
    if ('inert' in els.sourcePeek) els.sourcePeek.inert = true;
    if (els.peekBtn) els.peekBtn.setAttribute('aria-pressed', 'false');
  }

  /* ======================================================================
   * Exports
   * ====================================================================== */

  function copyAscii() {
    if (!state.result || settings.renderMode !== 'ascii' || !state.result.lines) return;
    var text = state.result.lines.join('\n');
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        toast('字符画已复制到剪贴板', 'success');
      }).catch(function () {
        fallbackCopy(text);
      });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '0';
    area.style.left = '-9999px';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    document.body.removeChild(area);
    if (ok) toast('字符画已复制到剪贴板', 'success');
    else toast('复制失败，请改用 TXT 导出。', 'error');
  }

  function exportTxt() {
    if (!state.result || settings.renderMode !== 'ascii' || !state.result.lines) return;
    var text = '\uFEFF' + state.result.lines.join('\r\n') + '\r\n';
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    downloadBlob(blob, safeBaseName(state.fileName) + '-ascii-' + state.result.cols + 'x' + state.result.rows + '.txt');
    toast('TXT 已导出', 'success');
  }

  function exportPng() {
    if (!state.result) return;
    try {
      var pixelMode = settings.renderMode === 'pixel';
      var exportCanvas = pixelMode
        ? pixelRenderer.renderExportCanvas(state.result, { targetWidth: 1600 })
        : renderer.renderExportCanvas(state.result, {
            cellAspect: settings.cellAspect,
            colorMode: settings.colorMode,
            accent: settings.accent,
            background: BACKGROUND
          });

      exportCanvas.toBlob(function (blob) {
        if (!blob) {
          toast('PNG 编码失败，请重试。', 'error');
          return;
        }
        var tag = pixelMode ? 'pixel' : 'ascii';
        downloadBlob(
          blob,
          safeBaseName(state.fileName) + '-' + tag + '-' + state.result.cols + 'x' + state.result.rows + '.png'
        );
        toast('PNG 已导出' + (state.kind === 'video' ? '（当前帧）' : ''), 'success');
      }, 'image/png');
    } catch (error) {
      console.error('[ASCII Studio] export failed', error);
      var message = error && error.message ? error.message : '未知错误';
      if (/tainted|security/i.test(message)) {
        message = '画布安全限制导致无法导出，请通过 start.cmd 以本地服务打开页面。';
      }
      toast('PNG 导出失败：' + message, 'error', 5200);
    }
  }

  function downloadBlob(blob, filename) {
    var url = URL.createObjectURL(blob);
    var anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    anchor.rel = 'noopener';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
  }

  /* ======================================================================
   * Demo animation
   * ====================================================================== */

  function initDemo() {
    if (!els.demoCanvas || !els.demoFrame) return;
    demo.ctx = els.demoCanvas.getContext('2d');
    if (!demo.ctx) return;
    demo.reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    demo.start = performance.now();

    if (typeof ResizeObserver !== 'undefined') {
      demo.observer = new ResizeObserver(function () {
        resizeDemo();
        if (demo.reduced) drawDemo(performance.now());
      });
      demo.observer.observe(els.demoFrame);
    } else {
      window.addEventListener('resize', resizeDemo);
    }

    resizeDemo();
    if (demo.reduced) {
      drawDemo(performance.now());
    } else {
      startDemo();
    }
  }

  function resizeDemo() {
    if (!els.demoFrame || !els.demoCanvas || !demo.ctx) return;
    var rect = els.demoFrame.getBoundingClientRect();
    if (rect.width < 20 || rect.height < 20) return;

    var cols = clamp(Math.round(rect.width / 6.5), 42, 108);
    var rows = Math.max(12, Math.round(cols * (rect.height / rect.width) * 0.58));
    var layout = renderer.fitSize(rect.width, rect.height, cols, rows, 0.58);
    var dpr = Math.min(window.devicePixelRatio || 1, 1.6);

    els.demoCanvas.width = Math.max(1, Math.round(layout.width * dpr));
    els.demoCanvas.height = Math.max(1, Math.round(layout.height * dpr));
    els.demoCanvas.style.width = layout.width + 'px';
    els.demoCanvas.style.height = layout.height + 'px';

    demo.width = layout.width;
    demo.height = layout.height;
    demo.cols = cols;
    demo.rows = rows;
    demo.cellW = layout.width / cols;
    demo.cellH = layout.height / rows;
    demo.dpr = dpr;
  }

  function startDemo() {
    if (demo.running || demo.reduced) return;
    demo.running = true;
    demo.lastDraw = 0;
    demo.raf = window.requestAnimationFrame(demoTick);
  }

  function stopDemo() {
    demo.running = false;
    if (demo.raf) {
      window.cancelAnimationFrame(demo.raf);
      demo.raf = 0;
    }
  }

  function demoTick(now) {
    if (!demo.running) return;
    if (now - demo.lastDraw > 1000 / 20) {
      drawDemo(now);
      demo.lastDraw = now;
    }
    demo.raf = window.requestAnimationFrame(demoTick);
  }

  function drawDemo(now) {
    if (!demo.ctx || !demo.width || !demo.height) return;

    var ctx = demo.ctx;
    var width = demo.width;
    var height = demo.height;
    var cols = demo.cols;
    var rows = demo.rows;
    var cellW = demo.cellW;
    var cellH = demo.cellH;
    var dpr = demo.dpr;
    var t = demo.reduced ? 2.7 : (now - demo.start) / 1000;
    var radius = Math.min(width, height) * 0.355;
    var cx = width * 0.5;
    var cy = height * 0.5;
    var chars = demo.chars || Array.from(core.CHARSETS.classic.chars);
    var accent = '#d7ff64';

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = '400 ' + Math.max(5, Math.min(cellH * 0.96, cellW / 0.6)) + 'px ' + renderer.FONT_STACK;
    ctx.fillStyle = accent;

    var tilt = -0.42;
    var cosTilt = Math.cos(tilt);
    var sinTilt = Math.sin(tilt);
    var lightX = -0.42;
    var lightY = -0.58;
    var lightZ = 0.7;
    var lightLen = Math.sqrt(lightX * lightX + lightY * lightY + lightZ * lightZ);
    lightX /= lightLen;
    lightY /= lightLen;
    lightZ /= lightLen;

    for (var gy = 0; gy < rows; gy++) {
      for (var gx = 0; gx < cols; gx++) {
        var px = (gx + 0.5) * cellW;
        var py = (gy + 0.5) * cellH;
        var nx = (px - cx) / radius;
        var ny = (py - cy) / radius;
        var distanceSq = nx * nx + ny * ny;
        var ch = null;
        var alpha = 1;

        if (distanceSq <= 1) {
          var nz = Math.sqrt(Math.max(0, 1 - distanceSq));
          var diffuse = Math.max(0, nx * lightX + ny * lightY + nz * lightZ);
          var rim = Math.pow(distanceSq, 7) * 0.48;
          var stripes = Math.sin(Math.atan2(ny, nx) * 7 + nz * 9.5 - t * 1.35) * 0.095;
          var scanLine = Math.abs(ny - Math.sin(t * 0.55) * 0.64) < 0.032 ? 0.13 : 0;
          var lum = clamp(0.035 + diffuse * 0.92 + stripes - rim + scanLine, 0, 1);
          var index = Math.round(lum * (chars.length - 1));
          ch = chars[index];
          if (ch === ' ') ch = null;
          alpha = 0.32 + lum * 0.68;
        } else {
          var u = nx * cosTilt - ny * sinTilt;
          var v = nx * sinTilt + ny * cosTilt;
          var ring = Math.sqrt(
            (u / 1.48) * (u / 1.48) +
            (v / 0.365) * (v / 0.365)
          );
          if (Math.abs(ring - 1) < 0.038 && distanceSq > 1.01) {
            ch = ((gx + gy) % 4 === 0) ? '+' : '.';
            alpha = 0.55;
          } else {
            var hash = hash2(gx, gy);
            if (hash % 173 === 0) {
              ch = hash % 3 === 0 ? '+' : '.';
              alpha = 0.12 + 0.22 * (0.5 + 0.5 * Math.sin(t * 1.4 + (hash % 17)));
            }
          }
        }

        if (ch) {
          ctx.globalAlpha = alpha;
          ctx.fillText(ch, px, py);
        }
      }
    }

    ctx.globalAlpha = 1;

    if (!demo.reduced && now - demo.lastCoord > 420 && els.demoCoord) {
      demo.lastCoord = now;
      var orbit = t * 0.6;
      var ox = Math.round(cx + Math.cos(orbit) * radius * 1.48);
      var oy = Math.round(cy + Math.sin(orbit) * radius * 0.365);
      els.demoCoord.textContent = 'x:' + pad2(ox) + ' y:' + pad2(oy);
    }
  }

  function hash2(x, y) {
    var h = (x * 374761393 + y * 668265263) | 0;
    h = (h ^ (h >>> 13)) * 1274126177;
    return (h ^ (h >>> 16)) >>> 0;
  }

  /* ======================================================================
   * Helpers
   * ====================================================================== */

  function updateRangeFill(input) {
    if (!input) return;
    var min = Number(input.min);
    var max = Number(input.max);
    var value = Number(input.value);
    var ratio = max > min ? (value - min) / (max - min) : 0;
    input.style.setProperty('--fill', clamp(ratio * 100, 0, 100).toFixed(2) + '%');
  }

  function setEngineStatus(status, label) {
    if (!els.engineStatus) return;
    window.clearTimeout(statusTimer);
    els.engineStatus.classList.toggle('is-busy', status === 'busy');
    els.engineStatus.classList.toggle('is-error', status === 'error');
    var text = els.engineStatus.querySelector('span');
    if (text) text.textContent = label;
    if (status === 'error') {
      statusTimer = window.setTimeout(function () {
        if (!state.loading) setEngineStatus('ready', '本地引擎');
      }, 4200);
    }
  }

  function showBusy(message) {
    if (!els.busyOverlay) return;
    if (message && els.busyText) els.busyText.textContent = message;
    els.busyOverlay.hidden = false;
  }

  function hideBusy() {
    if (els.busyOverlay) els.busyOverlay.hidden = true;
  }

  function describeLoadError(error, kind) {
    var message = error && error.message ? error.message : String(error || '');
    if (kind === 'video') {
      if (/超时/.test(message)) return message;
      if (/decode|解码|无法/.test(message)) return message;
      return '无法载入这个视频，请确认编码为 MP4 (H.264) 或 WebM。';
    }
    if (/taint|security/i.test(message)) {
      return '图片安全限制导致读取失败，请通过 start.cmd 启动本地服务后重试。';
    }
    if (/超时|尺寸/.test(message)) return message;
    return '无法载入这个图片，请换一个文件试试。';
  }

  function handleLoadError(error, kind) {
    state.lastError = error && error.message ? error.message : String(error);
    console.error('[ASCII Studio] load failed', error);
    setEngineStatus('error', '载入失败');
    toast(describeLoadError(error, kind), 'error', 5200);
    hideBusy();
  }

  function setPerfLabel(override, force) {
    var now = performance.now();
    if (!force && now - state.lastPerfUi < 420) return;
    state.lastPerfUi = now;

    if (override != null) {
      els.perfInfo.textContent = String(override);
      return;
    }
    if (state.kind === 'image') {
      els.perfInfo.textContent = state.perfMs ? state.perfMs.toFixed(1) + ' ms' : '—';
    } else if (state.kind === 'video') {
      if (state.isPlaying) {
        els.perfInfo.textContent = Math.round(state.fps || 0) + ' FPS · ' + state.perfMs.toFixed(1) + ' ms';
      } else {
        els.perfInfo.textContent = state.perfMs ? state.perfMs.toFixed(1) + ' ms' : '已暂停';
      }
    } else {
      els.perfInfo.textContent = '就绪';
    }
  }

  function formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '--:--';
    var total = Math.floor(seconds);
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var secs = total % 60;
    if (hours > 0) return hours + ':' + pad2(minutes) + ':' + pad2(secs);
    return minutes + ':' + pad2(secs);
  }

  function formatBytes(bytes) {
    var number = Number(bytes) || 0;
    if (number < 1024) return number + ' B';
    var units = ['KB', 'MB', 'GB'];
    var index = Math.min(units.length - 1, Math.floor(Math.log(number) / Math.log(1024)) - 1);
    var value = number / Math.pow(1024, index + 1);
    return (value >= 10 ? value.toFixed(1) : value.toFixed(2)) + ' ' + units[index];
  }

  function formatNumber(number) {
    return Number(number || 0).toLocaleString('en-US');
  }

  function formatSigned(number) {
    var value = Math.round(Number(number) || 0);
    return value > 0 ? '+' + value : String(value);
  }

  function pad2(number) {
    return String(number).padStart(2, '0');
  }

  function clamp(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return value < min ? min : value > max ? max : value;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function safeBaseName(name) {
    var value = String(name || 'ascii-art').replace(/\.[^.\\/]+$/, '');
    value = value.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').replace(/\s+/g, ' ').trim();
    return (value || 'ascii-art').slice(0, 72);
  }

  /* ======================================================================
   * Debug API (also used by automated browser tests)
   * ====================================================================== */

  function getSnapshot() {
    return {
      version: VERSION,
      ready: true,
      renderMode: settings.renderMode,
      kind: state.kind,
      fileName: state.fileName,
      width: state.width,
      height: state.height,
      duration: state.duration,
      currentTime: state.videoEl && Number.isFinite(state.videoEl.currentTime) ? state.videoEl.currentTime : 0,
      cols: state.grid ? state.grid.cols : null,
      rows: state.grid ? state.grid.rows : null,
      levels: state.result && state.result.levels != null ? state.result.levels : null,
      inked: state.result && state.result.inked != null ? state.result.inked : null,
      lineCount: state.result
        ? (state.result.lines ? state.result.lines.length : state.result.rows || 0)
        : 0,
      playing: Boolean(state.videoEl && !state.videoEl.paused && !state.videoEl.ended),
      recording: Boolean(state.recording),
      loading: Boolean(state.loading),
      canvas: { width: els.asciiCanvas.width, height: els.asciiCanvas.height },
      emptyVisible: els.emptyState ? !els.emptyState.hidden : null,
      recordSupported: Boolean(state.canRecord),
      error: state.lastError,
      settings: JSON.parse(JSON.stringify(settings)),
      pixel: settings.renderMode === 'pixel' && state.result
        ? {
            palette: state.result.palette ? state.result.palette.id : null,
            colors: state.result.palette ? state.result.palette.colors.length : null,
            outlined: state.result.outlined
          }
        : null,
      samples: SAMPLES.map(function (sample) { return sample.id; })
    };
  }

  function exposeDebugApi() {
    try {
      window.ASCII_STUDIO = Object.freeze({
        version: VERSION,
        loadSample: loadSample,
        getSnapshot: getSnapshot,
        openHelp: openHelp
      });
    } catch (error) {
      console.warn('[ASCII Studio] debug API unavailable', error);
    }
  }
})();
