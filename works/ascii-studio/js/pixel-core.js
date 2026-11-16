/*!
 * ASCII Studio — retro pixel engine
 * 把降采样后的画面压进有限色板，并可选描边，做出古早平面像素游戏的味道。
 * 纯函数、无 DOM 依赖，可在 Node.js 中单测。
 */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.PixelCore = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var VERSION = '1.0.0';
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

  var PALETTES = Object.freeze({
    pico8: Object.freeze({
      id: 'pico8',
      label: 'PICO-8',
      hint: '16 色 · 鲜艳复古',
      colors: Object.freeze([
        '#000000', '#1d2b53', '#7e2553', '#008751',
        '#ab5236', '#5f574f', '#c2c3c7', '#fff1e8',
        '#ff004d', '#ffa300', '#ffec27', '#00e436',
        '#29adff', '#83769c', '#ff77a8', '#ffccaa'
      ])
    }),
    gameboy: Object.freeze({
      id: 'gameboy',
      label: 'Game Boy',
      hint: '4 色 · 掌机绿',
      colors: Object.freeze(['#0f380f', '#306230', '#8bac0f', '#9bbc0f'])
    }),
    arcade: Object.freeze({
      id: 'arcade',
      label: '街机 16',
      hint: '16 色 · 高饱和',
      colors: Object.freeze([
        '#000000', '#1a1c2c', '#5d275d', '#b13e53',
        '#ef7d57', '#ffcd75', '#a7f070', '#38b764',
        '#257179', '#29366f', '#3b5dc9', '#41a6f6',
        '#73eff7', '#f4f4f4', '#94b0c2', '#566c86'
      ])
    }),
    cga: Object.freeze({
      id: 'cga',
      label: 'CGA',
      hint: '16 色 · 80 年代 PC',
      colors: Object.freeze([
        '#000000', '#0000aa', '#00aa00', '#00aaaa',
        '#aa0000', '#aa00aa', '#aa5500', '#aaaaaa',
        '#555555', '#5555ff', '#55ff55', '#55ffff',
        '#ff5555', '#ff55ff', '#ffff55', '#ffffff'
      ])
    }),
    gray: Object.freeze({
      id: 'gray',
      label: '灰阶 6',
      hint: '6 色 · 掌上终端',
      colors: Object.freeze(['#070906', '#242824', '#4b514a', '#7b8278', '#b3b9ac', '#ecebdc'])
    }),
    duo: Object.freeze({
      id: 'duo',
      label: '双色',
      hint: '2 色 · 1-bit 游戏',
      colors: Object.freeze(['#070906', '#f3f0da'])
    })
  });

  var PALETTE_LIST = Object.freeze(
    Object.keys(PALETTES).map(function (key) {
      return PALETTES[key];
    })
  );

  function clamp(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return value < min ? min : value > max ? max : value;
  }

  function parseHex(value) {
    var match = /^#?([0-9a-f]{6})$/i.exec(String(value || '').trim());
    if (!match) return null;
    var number = parseInt(match[1], 16);
    return {
      r: (number >> 16) & 255,
      g: (number >> 8) & 255,
      b: number & 255,
      hex: '#' + match[1].toLowerCase()
    };
  }

  /**
   * 解析色板 id 或颜色数组，返回可用于最近色匹配的颜色表。
   * @param {string|string[]} palette
   * @returns {{id:string,label:string,hint:string,colors:Array<{r:number,g:number,b:number,hex:string,lum:number}>}}
   */
  function resolvePalette(palette) {
    var preset = null;
    var rawColors = null;

    if (Array.isArray(palette)) {
      rawColors = palette;
    } else if (typeof palette === 'string' && PALETTES[palette]) {
      preset = PALETTES[palette];
      rawColors = preset.colors;
    } else {
      preset = PALETTES.pico8;
      rawColors = preset.colors;
    }

    var colors = [];
    for (var i = 0; i < rawColors.length; i++) {
      var parsed = parseHex(rawColors[i]);
      if (!parsed) continue;
      parsed.lum = (0.2126 * parsed.r + 0.7152 * parsed.g + 0.0722 * parsed.b) / 255;
      colors.push(parsed);
      if (colors.length >= 64) break;
    }

    if (colors.length < 2) {
      return resolvePalette('pico8');
    }

    return {
      id: preset ? preset.id : 'custom',
      label: preset ? preset.label : '自定义色板',
      hint: preset ? preset.hint : colors.length + ' 色',
      colors: colors
    };
  }

  /** 找出色板中最暗的颜色，用于描边。 */
  function darkestColorIndex(colors) {
    var best = 0;
    for (var i = 1; i < colors.length; i++) {
      if (colors[i].lum < colors[best].lum) best = i;
    }
    return best;
  }

  /**
   * 将降采样后的像素压缩到限制色板，形成像素画。
   * 输入通常是已经缩放到 cols × rows 的 ImageData。
   *
   * @param {{data: Uint8ClampedArray|Uint8Array, width:number, height:number}} imageData
   * @param {object} [options]
   * @param {string|string[]} [options.palette='pico8']
   * @param {boolean} [options.autoLevels=false]
   * @param {number} [options.autoClip=0.015]
   * @param {number} [options.toneGamma=1] 自动色阶后的中间调 gamma
   * @param {{low:number,high:number}} [options.autoRange] 视频逐帧复用的稳定色阶
   * @param {number} [options.brightness=0] -1 ~ 1 的亮度偏移
   * @param {number} [options.contrast=1] 对比度系数
   * @param {'off'|'ordered'|'fs'} [options.dither='off']
   * @param {number} [options.ditherStrength=0.9]
   * @param {boolean} [options.outline=false]
   * @param {number} [options.outlineThreshold=0.18]
   * @returns {{
   *   mode:'pixel', cols:number, rows:number,
   *   pixels:Uint8ClampedArray,
   *   palette:{id:string,label:string,hint:string,colors:Array<object>},
   *   autoRange:{low:number,high:number}|null,
   *   outlined:boolean
   * }}
   */
  function convertPixels(imageData, options) {
    if (!imageData) throw new Error('convertPixels: imageData is required');
    var data = imageData.data;
    var width = Math.max(1, Math.floor(Number(imageData.width) || 0));
    var height = Math.max(1, Math.floor(Number(imageData.height) || 0));
    var pixelCount = width * height;
    if (!data || typeof data.length !== 'number' || data.length < pixelCount * 4) {
      throw new Error('convertPixels: imageData must contain width × height × 4 bytes');
    }

    var opts = options || {};
    var palette = resolvePalette(opts.palette);
    var colors = palette.colors;
    var outline = Boolean(opts.outline);
    var outlineThreshold = clamp(
      opts.outlineThreshold == null ? 0.18 : Number(opts.outlineThreshold),
      0.02,
      1
    );
    var autoLevels = Boolean(opts.autoLevels);
    var autoClip = clamp(opts.autoClip == null ? 0.015 : Number(opts.autoClip), 0, 0.2);
    var toneGamma = clamp(opts.toneGamma == null ? 1 : Number(opts.toneGamma), 0.4, 2.4);
    var brightness = clamp(Number(opts.brightness) || 0, -1, 1);
    var contrast = Math.max(0.05, Number(opts.contrast) || 1);
    var dither = opts.dither === 'ordered' || opts.dither === 'fs' ? opts.dither : 'off';
    var ditherStrength = clamp(
      opts.ditherStrength == null ? 0.9 : Number(opts.ditherStrength),
      0,
      1
    );

    // 复用一帧已经算好的色阶，避免视频曝光逐帧跳动。
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

    var rawLuminance = new Float32Array(pixelCount);
    var histogram = autoLevels && !suppliedRange ? new Uint32Array(256) : null;
    var i;
    var p = 0;
    for (i = 0; i < pixelCount; i++, p += 4) {
      var rawLum = (0.2126 * data[p] + 0.7152 * data[p + 1] + 0.0722 * data[p + 2]) / 255;
      rawLuminance[i] = rawLum;
      if (histogram) histogram[Math.round(rawLum * 255)]++;
    }

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

    var levelScale = autoLevels ? 1 / (autoHigh - autoLow) : 1;
    var adjusted = new Float32Array(pixelCount * 3);
    var luminance = new Float32Array(pixelCount);
    var gains = new Float32Array(256);
    for (var level = 0; level < 256; level++) {
      var normalized = level / 255;
      if (autoLevels) {
        normalized = clamp((normalized - autoLow) * levelScale, 0, 1);
        if (toneGamma !== 1) normalized = Math.pow(normalized, toneGamma);
      }
      normalized = (normalized - 0.5) * contrast + 0.5 + brightness;
      normalized = clamp(normalized, 0, 1);
      gains[level] = normalized * 255;
    }

    p = 0;
    for (i = 0; i < pixelCount; i++, p += 4) {
      var r = gains[data[p]];
      var g = gains[data[p + 1]];
      var b = gains[data[p + 2]];
      var o = i * 3;
      adjusted[o] = r;
      adjusted[o + 1] = g;
      adjusted[o + 2] = b;
      luminance[i] = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    }

    var indices = new Uint8Array(pixelCount);
    var colorCount = colors.length;

    function nearestIndex(r, g, b) {
      var best = 0;
      var bestDistance = Infinity;
      for (var ci = 0; ci < colorCount; ci++) {
        var color = colors[ci];
        var dr = r - color.r;
        var dg = g - color.g;
        var db = b - color.b;
        var distance = dr * dr + dg * dg + db * db;
        if (distance < bestDistance) {
          bestDistance = distance;
          best = ci;
          if (distance === 0) break;
        }
      }
      return best;
    }

    if (dither === 'fs') {
      var work = Float32Array.from(adjusted);
      var maxDist = ditherStrength;
      for (var y = 0; y < height; y++) {
        var rowOffset = y * width;
        for (var x = 0; x < width; x++) {
          var index = rowOffset + x;
          var offset = index * 3;
          var chosen = nearestIndex(work[offset], work[offset + 1], work[offset + 2]);
          indices[index] = chosen;
          var target = colors[chosen];
          var er = (work[offset] - target.r) * maxDist;
          var eg = (work[offset + 1] - target.g) * maxDist;
          var eb = (work[offset + 2] - target.b) * maxDist;

          if (x + 1 < width) {
            var right = offset + 3;
            work[right] += (er * 7) / 16;
            work[right + 1] += (eg * 7) / 16;
            work[right + 2] += (eb * 7) / 16;
          }
          if (y + 1 < height) {
            if (x > 0) {
              var downLeft = (index + width - 1) * 3;
              work[downLeft] += (er * 3) / 16;
              work[downLeft + 1] += (eg * 3) / 16;
              work[downLeft + 2] += (eb * 3) / 16;
            }
            var down = (index + width) * 3;
            work[down] += (er * 5) / 16;
            work[down + 1] += (eg * 5) / 16;
            work[down + 2] += (eb * 5) / 16;
            if (x + 1 < width) {
              var downRight = (index + width + 1) * 3;
              work[downRight] += (er * 1) / 16;
              work[downRight + 1] += (eg * 1) / 16;
              work[downRight + 2] += (eb * 1) / 16;
            }
          }
        }
      }
    } else {
      var orderedAmount = 30 * ditherStrength;
      for (var oy = 0; oy < height; oy++) {
        var rowBase = oy * width;
        var matrixRow = (oy & 7) * 8;
        for (var ox = 0; ox < width; ox++) {
          var pixelIndex = rowBase + ox;
          var pos = pixelIndex * 3;
          var pr = adjusted[pos];
          var pg = adjusted[pos + 1];
          var pb = adjusted[pos + 2];
          if (dither === 'ordered') {
            var threshold = (BAYER_8[matrixRow + (ox & 7)] + 0.5) / 64 - 0.5;
            pr = clamp(pr + threshold * orderedAmount, 0, 255);
            pg = clamp(pg + threshold * orderedAmount, 0, 255);
            pb = clamp(pb + threshold * orderedAmount, 0, 255);
          }
          indices[pixelIndex] = nearestIndex(pr, pg, pb);
        }
      }
    }

    var outlined = false;
    if (outline) {
      var outlineIndex = darkestColorIndex(colors);
      for (var ey = 1; ey < height - 1; ey++) {
        var edgeRow = ey * width;
        for (var ex = 1; ex < width - 1; ex++) {
          var edgeIndex = edgeRow + ex;
          var gx = luminance[edgeIndex + 1] - luminance[edgeIndex - 1];
          var gy = luminance[edgeIndex + width] - luminance[edgeIndex - width];
          if (Math.sqrt(gx * gx + gy * gy) > outlineThreshold) {
            indices[edgeIndex] = outlineIndex;
            outlined = true;
          }
        }
      }
    }

    var pixels = new Uint8ClampedArray(pixelCount * 4);
    for (i = 0; i < pixelCount; i++) {
      var color = colors[indices[i]];
      var targetOffset = i * 4;
      pixels[targetOffset] = color.r;
      pixels[targetOffset + 1] = color.g;
      pixels[targetOffset + 2] = color.b;
      pixels[targetOffset + 3] = 255;
    }

    return {
      mode: 'pixel',
      width: width,
      height: height,
      cols: width,
      rows: height,
      pixels: pixels,
      palette: palette,
      autoRange: autoLevels ? { low: autoLow, high: autoHigh } : null,
      outlined: outlined
    };
  }

  return Object.freeze({
    VERSION: VERSION,
    PALETTES: PALETTES,
    PALETTE_LIST: PALETTE_LIST,
    resolvePalette: resolvePalette,
    convertPixels: convertPixels
  });
});
