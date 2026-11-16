/*!
 * ASCII Studio — pure conversion engine
 * 无 DOM 依赖，既可在浏览器中以 window.AsciiCore 使用，也可在 Node.js 中 require。
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.AsciiCore = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.0';

  /**
   * 字符集均按「从疏到密」排列：索引 0 对应最暗，末尾对应最亮。
   * 输入亮度越高，选中的字符越“重”。
   */
  var CHARSETS = Object.freeze({
    classic: Object.freeze({
      id: 'classic',
      label: '经典',
      hint: '10 级 · 通用',
      chars: ' .:-=+*#%@'
    }),
    fine: Object.freeze({
      id: 'fine',
      label: '精细',
      hint: '70 级 · 细腻',
      chars: ' .\'`^",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$'
    }),
    blocks: Object.freeze({
      id: 'blocks',
      label: '方块',
      hint: '5 级 · 厚重',
      chars: ' ░▒▓█'
    }),
    dots: Object.freeze({
      id: 'dots',
      label: '点阵',
      hint: '9 级 · 呼吸感',
      chars: ' ⠁⠉⠙⠋⠛⠟⠿⣿'
    }),
    binary: Object.freeze({
      id: 'binary',
      label: '二进制',
      hint: '3 级 · 数字',
      chars: ' 01'
    })
  });

  var CHARSET_LIST = Object.freeze(
    Object.keys(CHARSETS).map(function (key) {
      return CHARSETS[key];
    })
  );

  var DEFAULT_CHARSET = CHARSETS.classic.chars;
  var MAX_CHARSET_LEVELS = 96;
  var MAX_ROWS = 500;

  // Bayer 8×8 有序抖动矩阵（值 0–63）
  var BAYER_8 = Object.freeze([
    0, 32, 8, 40, 2, 34, 10, 42,
    48, 16, 56, 24, 50, 18, 58, 26,
    12, 44, 4, 36, 14, 46, 6, 38,
    60, 28, 52, 20, 62, 30, 54, 22,
    3, 35, 11, 43, 1, 33, 9, 41,
    51, 19, 59, 27, 49, 17, 57, 25,
    15, 47, 7, 39, 13, 45, 5, 37,
    63, 31, 55, 23, 61, 29, 53, 21
  ]);

  function clamp(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return value < min ? min : value > max ? max : value;
  }

  /**
   * 把任意字符集整理为去重后的「逐级字符表」。
   * 会移除换行/制表等控制字符，最多保留 96 级。
   * @param {string|string[]|null|undefined} input
   * @returns {string[]}
   */
  function normalizeCharset(input) {
    var source;
    if (Array.isArray(input)) {
      source = input.join('');
    } else if (input == null) {
      source = DEFAULT_CHARSET;
    } else {
      source = String(input);
    }

    var seen = Object.create(null);
    var chars = [];
    var iterator = source[Symbol.iterator]();
    var step;
    while (!(step = iterator.next()).done) {
      var ch = step.value;
      if (ch === '\n' || ch === '\r' || ch === '\t' || ch === '\u0000') continue;
      if (seen[ch]) continue;
      seen[ch] = true;
      chars.push(ch);
      if (chars.length >= MAX_CHARSET_LEVELS) break;
    }

    if (chars.length < 2) return Array.from(DEFAULT_CHARSET);
    return chars;
  }

  /**
   * 从字符集 id 或自定义字符中取出可渲染的字符表。
   * @param {string} id
   * @param {string} [custom]
   * @returns {string[]}
   */
  function resolveCharset(id, custom) {
    if (id === 'custom') return normalizeCharset(custom);
    var preset = CHARSETS[id];
    if (!preset) return normalizeCharset(DEFAULT_CHARSET);
    return normalizeCharset(preset.chars);
  }

  /**
   * 按图片宽高与字符单元宽高比计算网格。
   * 令 cellAspect = 单字宽 / 单字高，则：
   *   rows = cols × (sourceHeight / sourceWidth) × cellAspect
   * 这样字符画的整体宽高比与源素材一致，不会被纵向拉伸。
   *
   * @param {number} sourceWidth
   * @param {number} sourceHeight
   * @param {number} columns  期望列数
   * @param {number} [cellAspect=0.58] 单字宽高比
   * @param {number} [maxRows=500]
   * @returns {{cols:number, rows:number}}
   */
  function computeGrid(sourceWidth, sourceHeight, columns, cellAspect, maxRows) {
    var width = Math.max(1, Number(sourceWidth) || 1);
    var height = Math.max(1, Number(sourceHeight) || 1);
    var aspect = clamp(Number(cellAspect) || 0.58, 0.2, 1.6);
    var cols = Math.round(clamp(Number(columns) || 100, 8, 500));
    var rowLimit = Math.max(1, Math.round(Number(maxRows) || MAX_ROWS));
    var rows = Math.round(cols * (height / width) * aspect);
    rows = Math.max(1, Math.min(rowLimit, rows));
    return { cols: cols, rows: rows };
  }

  /**
   * 将像素数据转换为字符网格。
   *
   * 所有参数均可省略，默认输出经典字符集的单色结果。
   *
   * @param {{data: Uint8ClampedArray|Uint8Array, width:number, height:number}} imageData
   * @param {object} [options]
   * @param {string|string[]} [options.charset=' .:-=+*#%@']
   * @param {boolean} [options.color=false] 是否保留原始颜色
   * @param {boolean} [options.invert=false] 明暗反转
   * @param {number} [options.brightness=0] 亮度偏移，-1 ~ 1
   * @param {number} [options.contrast=1] 对比度系数，建议 0.25 ~ 3
   * @param {boolean} [options.autoLevels=false] 自动把明暗层次拉伸到完整范围
   * @param {number} [options.autoClip=0.015] 自动增强时两端裁掉的极值比例
   * @param {number} [options.autoGamma=1] 自动增强后的中间调 gamma（>1 压暗中间调）
   * @param {{low:number,high:number}} [options.autoRange] 复用之前算好的色阶，避免视频逐帧闪烁
   * @param {'off'|'ordered'|'fs'} [options.dither='off'] 抖动方式
   * @param {number} [options.ditherStrength=0.9] 有序抖动强度，0 ~ 1
   * @returns {{
   *   width:number, height:number, cols:number, rows:number,
   *   lines:string[], plain:string, charTable:string[], levels:number,
   *   rgb: Uint8ClampedArray|null, colorMode:'mono'|'color',
   *   inked:number, autoRange:{low:number,high:number}|null
   * }}
   */
  function convert(imageData, options) {
    if (!imageData) throw new Error('convert: imageData is required');

    var data = imageData.data;
    var width = Math.max(1, Math.floor(Number(imageData.width) || 0));
    var height = Math.max(1, Math.floor(Number(imageData.height) || 0));
    var pixelCount = width * height;

    if (!data || typeof data.length !== 'number' || data.length < pixelCount * 4) {
      throw new Error('convert: imageData must contain width × height × 4 bytes');
    }

    var opts = options || {};
    var chars = normalizeCharset(opts.charset);
    var levels = chars.length;
    var maxIndex = levels - 1;

    var color = Boolean(opts.color);
    var invert = Boolean(opts.invert);
    var brightness = clamp(Number(opts.brightness) || 0, -1, 1);
    var contrast = Math.max(0.05, Number(opts.contrast) || 1);
    var autoLevels = Boolean(opts.autoLevels);
    var autoClip = clamp(opts.autoClip == null ? 0.015 : Number(opts.autoClip), 0, 0.2);
    var autoGamma = clamp(opts.autoGamma == null ? 1 : Number(opts.autoGamma), 0.4, 2.4);
    var suppliedRange = opts.autoRange &&
      Number.isFinite(Number(opts.autoRange.low)) &&
      Number.isFinite(Number(opts.autoRange.high))
      ? {
          low: clamp(Number(opts.autoRange.low), 0, 1),
          high: clamp(Number(opts.autoRange.high), 0, 1)
        }
      : null;
    if (suppliedRange && suppliedRange.high <= suppliedRange.low + 0.02) {
      suppliedRange = null;
    }
    var dither = opts.dither === 'ordered' || opts.dither === 'fs' ? opts.dither : 'off';
    var ditherStrength = clamp(
      opts.ditherStrength == null ? 0.9 : Number(opts.ditherStrength),
      0,
      1
    );

    var rawLuminance = new Float32Array(pixelCount);
    var rgb = color ? new Uint8ClampedArray(pixelCount * 3) : null;
    var histogram = autoLevels && !suppliedRange ? new Uint32Array(256) : null;

    // 1) 记录原始感知亮度，同时收集直方图
    var i;
    var p = 0;
    for (i = 0; i < pixelCount; i++, p += 4) {
      var r = data[p];
      var g = data[p + 1];
      var b = data[p + 2];
      var rawLum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
      rawLuminance[i] = rawLum;
      if (histogram) {
        histogram[Math.round(rawLum * 255)]++;
      }

      if (rgb) {
        var c = i * 3;
        rgb[c] = r;
        rgb[c + 1] = g;
        rgb[c + 2] = b;
      }
    }

    // 2) 自动色阶：用低/高百分位把可用明暗范围拉满
    var autoLow = suppliedRange ? suppliedRange.low : 0;
    var autoHigh = suppliedRange ? suppliedRange.high : 1;
    if (histogram) {
      var lowTarget = pixelCount * autoClip;
      var highTarget = pixelCount * (1 - autoClip);
      var accumulated = 0;
      var lowBin = 0;
      var highBin = 255;
      var bin;
      for (bin = 0; bin < 256; bin++) {
        accumulated += histogram[bin];
        if (accumulated >= lowTarget) {
          lowBin = bin;
          break;
        }
      }
      accumulated = 0;
      for (bin = 0; bin < 256; bin++) {
        accumulated += histogram[bin];
        if (accumulated >= highTarget) {
          highBin = bin;
          break;
        }
      }
      autoLow = lowBin / 255;
      autoHigh = highBin / 255;
      if (autoHigh <= autoLow + 0.02) {
        autoLow = 0;
        autoHigh = 1;
      }
    }

    // 3) 应用自动色阶、手动亮度/对比度、反相
    var luminance = new Float32Array(pixelCount);
    var levelScale = autoLevels ? 1 / (autoHigh - autoLow) : 1;
    for (i = 0; i < pixelCount; i++) {
      var lum = rawLuminance[i];
      if (autoLevels) {
        lum = (lum - autoLow) * levelScale;
        lum = lum < 0 ? 0 : lum > 1 ? 1 : lum;
        if (autoGamma !== 1) lum = Math.pow(lum, autoGamma);
      }
      lum = (lum - 0.5) * contrast + 0.5 + brightness;
      lum = lum < 0 ? 0 : lum > 1 ? 1 : lum;
      if (invert) lum = 1 - lum;
      luminance[i] = lum;
    }

    // 2) 量化到字符层级（可抖动）
    var indices = new Uint8Array(pixelCount);
    var x;
    var y;
    var index;
    var value;

    if (dither === 'fs' && maxIndex > 0) {
      // Floyd–Steinberg 误差扩散，让渐变更平滑
      var work = Float32Array.from(luminance);
      for (y = 0; y < height; y++) {
        var row = y * width;
        for (x = 0; x < width; x++) {
          i = row + x;
          value = clamp(work[i], 0, 1);
          index = Math.round(value * maxIndex);
          indices[i] = index;
          var err = value - index / maxIndex;
          if (x + 1 < width) work[i + 1] += (err * 7) / 16;
          if (y + 1 < height) {
            if (x > 0) work[i + width - 1] += (err * 3) / 16;
            work[i + width] += (err * 5) / 16;
            if (x + 1 < width) work[i + width + 1] += (err * 1) / 16;
          }
        }
      }
    } else if (dither === 'ordered' && maxIndex > 0) {
      var unit = ditherStrength / maxIndex;
      for (y = 0; y < height; y++) {
        var matrixRow = (y & 7) * 8;
        for (x = 0; x < width; x++) {
          i = y * width + x;
          var threshold = (BAYER_8[matrixRow + (x & 7)] + 0.5) / 64 - 0.5;
          value = clamp(luminance[i] + threshold * unit, 0, 1);
          indices[i] = Math.round(value * maxIndex);
        }
      }
    } else {
      for (i = 0; i < pixelCount; i++) {
        indices[i] = Math.round(luminance[i] * maxIndex);
      }
    }

    // 3) 拼装文本；若要彩色，同步保留逐像素 RGB
    var spaceish = chars.map(function (ch) {
      return /^\s$/u.test(ch);
    });
    var lines = new Array(height);
    var inked = 0;
    for (y = 0; y < height; y++) {
      var line = '';
      var offset = y * width;
      for (x = 0; x < width; x++) {
        index = indices[offset + x];
        line += chars[index];
        if (!spaceish[index]) inked++;
      }
      lines[y] = line;
    }

    return {
      width: width,
      height: height,
      cols: width,
      rows: height,
      lines: lines,
      plain: lines.join('\n'),
      charTable: chars,
      levels: levels,
      rgb: rgb,
      colorMode: color ? 'color' : 'mono',
      inked: inked,
      autoRange: autoLevels ? { low: autoLow, high: autoHigh } : null
    };
  }

  return Object.freeze({
    VERSION: VERSION,
    CHARSETS: CHARSETS,
    CHARSET_LIST: CHARSET_LIST,
    DEFAULT_CHARSET: DEFAULT_CHARSET,
    normalizeCharset: normalizeCharset,
    resolveCharset: resolveCharset,
    computeGrid: computeGrid,
    convert: convert,
    clamp: clamp
  });
});
