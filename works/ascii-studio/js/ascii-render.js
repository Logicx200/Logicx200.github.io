/*!
 * ASCII Studio — canvas renderer
 * 负责把 AsciiCore 生成的字符网格绘制到画布上（预览 / 高清导出）。
 */
(function (root) {
  'use strict';

  var FONT_STACK =
    '"Cascadia Mono", "Cascadia Code", Consolas, "SFMono-Regular", "Courier New", monospace';
  var DEFAULT_BACKGROUND = '#080a07';
  var DEFAULT_ACCENT = '#d7ff64';
  var DEFAULT_COLOR_LIFT = 0.16;
  var MAX_EXPORT_EDGE = 4096;

  var measuredFonts = Object.create(null);

  function clamp(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return value < min ? min : value > max ? max : value;
  }

  /**
   * 计算画布在给定区域内、保持字符网格比例时的 CSS 尺寸。
   * @param {number} boxWidth
   * @param {number} boxHeight
   * @param {number} cols
   * @param {number} rows
   * @param {number} cellAspect 单字宽 / 单字高
   * @returns {{width:number, height:number}}
   */
  function fitSize(boxWidth, boxHeight, cols, rows, cellAspect) {
    var safeCols = Math.max(1, Number(cols) || 1);
    var safeRows = Math.max(1, Number(rows) || 1);
    var aspect = clamp(Number(cellAspect) || 0.58, 0.2, 1.6);
    var gridAspect = (safeCols * aspect) / safeRows;

    var maxWidth = Math.max(1, Number(boxWidth) || 1);
    var maxHeight = Math.max(1, Number(boxHeight) || 1);

    var width = maxWidth;
    var height = width / gridAspect;
    if (height > maxHeight) {
      height = maxHeight;
      width = height * gridAspect;
    }
    return {
      width: Math.max(1, Math.round(width * 100) / 100),
      height: Math.max(1, Math.round(height * 100) / 100)
    };
  }

  /** 测量某个字体栈下等宽字形的宽度 / 字号比例。 */
  function glyphAdvanceRatio(fontWeight) {
    var key = String(fontWeight);
    if (measuredFonts[key]) return measuredFonts[key];
    var ratio = 0.6;
    try {
      var probe = document.createElement('canvas');
      var ctx = probe.getContext('2d');
      if (ctx) {
        ctx.font = fontWeight + ' 120px ' + FONT_STACK;
        var width = ctx.measureText('M').width;
        if (width > 0) ratio = width / 120;
      }
    } catch (error) {
      /* 使用默认比例 */
    }
    measuredFonts[key] = ratio;
    return ratio;
  }

  function colorString(r, g, b) {
    return '#' +
      ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
  }

  /**
   * 将字符串网格绘制到 2D 上下文。
   * @param {CanvasRenderingContext2D} ctx
   * @param {object} result AsciiCore.convert() 返回值
   * @param {number} width CSS 像素宽
   * @param {number} height CSS 像素高
   * @param {object} [options]
   */
  function drawAscii(ctx, result, width, height, options) {
    if (!ctx || !result || !result.lines || !result.lines.length) return;

    var opts = options || {};
    var cols = Math.max(1, result.cols);
    var rows = Math.max(1, result.rows);
    var cellW = width / cols;
    var cellH = height / rows;
    var weight = opts.fontWeight || 400;
    var ratio = glyphAdvanceRatio(weight);
    var fontSize = cellW / ratio;
    var colorMode = opts.colorMode === 'color' && result.rgb;
    var colorCache = colorMode ? new Array(512) : null;
    var accent = opts.accent || DEFAULT_ACCENT;
    var colorLift = clamp(
      opts.colorLift == null ? DEFAULT_COLOR_LIFT : Number(opts.colorLift),
      0,
      0.6
    );
    var liftScale = 1 - colorLift;

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = weight + ' ' + fontSize + 'px ' + FONT_STACK;
    if (!colorMode) ctx.fillStyle = accent;

    var halfCellW = cellW / 2;
    var halfCellH = cellH / 2;
    var rgb = result.rgb;
    var lines = result.lines;

    for (var y = 0; y < rows; y++) {
      var line = lines[y];
      if (line == null) continue;
      var col = 0;
      var centerY = (y + 0.5) * cellH;
      for (var ch of line) {
        if (ch !== ' ' && ch !== '\u00a0') {
          if (colorMode) {
            var pixel = (y * cols + col) * 3;
            // Screen-lift shadows slightly so colored glyphs stay legible
            // on dark backgrounds without losing the source hue.
            var r = 255 - Math.round((255 - rgb[pixel]) * liftScale);
            var g = 255 - Math.round((255 - rgb[pixel + 1]) * liftScale);
            var b = 255 - Math.round((255 - rgb[pixel + 2]) * liftScale);
            var q = ((r >> 5) << 6) | ((g >> 5) << 3) | (b >> 5);
            var color = colorCache[q];
            if (!color) {
              color = colorString((r >> 5) * 32 + 16, (g >> 5) * 32 + 16, (b >> 5) * 32 + 16);
              colorCache[q] = color;
            }
            ctx.fillStyle = color;
          }
          ctx.fillText(ch, col * cellW + halfCellW, centerY + halfCellH * 0.02);
        }
        col++;
      }
    }
  }

  /**
   * 绘制自适应预览。
   * @param {HTMLCanvasElement} canvas
   * @param {object} result
   * @param {object} options
   * @param {number} options.boxWidth 可用宽度 CSS px
   * @param {number} options.boxHeight 可用高度 CSS px
   * @param {number} [options.cellAspect=0.58]
   * @param {number} [options.dpr=1]
   * @param {'mono'|'color'} [options.colorMode='mono']
   * @param {string} [options.accent]
   * @param {string} [options.background]
   * @returns {{width:number,height:number,dpr:number}|null}
   */
  function paintPreview(canvas, result, options) {
    if (!canvas || !result || !result.lines) return null;
    var opts = options || {};
    var cellAspect = opts.cellAspect || 0.58;
    var layout = fitSize(
      opts.boxWidth,
      opts.boxHeight,
      result.cols,
      result.rows,
      cellAspect
    );
    var dpr = clamp(Number(opts.dpr) || 1, 0.75, 3);
    var pixelWidth = Math.max(1, Math.round(layout.width * dpr));
    var pixelHeight = Math.max(1, Math.round(layout.height * dpr));

    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }

    var cssWidth = layout.width + 'px';
    var cssHeight = layout.height + 'px';
    if (canvas.style.width !== cssWidth) canvas.style.width = cssWidth;
    if (canvas.style.height !== cssHeight) canvas.style.height = cssHeight;

    var ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
    var background = opts.background || DEFAULT_BACKGROUND;
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, layout.width, layout.height);

    drawAscii(ctx, result, layout.width, layout.height, {
      colorMode: opts.colorMode,
      accent: opts.accent,
      fontWeight: opts.fontWeight
    });

    return { width: layout.width, height: layout.height, dpr: dpr };
  }

  /**
   * 生成可用于下载的高清 PNG 画布。
   * @param {object} result
   * @param {object} [options]
   * @param {number} [options.cellAspect=0.58]
   * @param {'mono'|'color'} [options.colorMode='mono']
   * @param {string} [options.accent]
   * @param {string} [options.background]
   * @param {number} [options.cellHeight] 每个字符的目标像素高度
   * @param {number} [options.padding] 留白
   * @returns {HTMLCanvasElement}
   */
  function renderExportCanvas(result, options) {
    var opts = options || {};
    var cellAspect = clamp(Number(opts.cellAspect) || 0.58, 0.2, 1.6);
    var cellHeight =
      Number(opts.cellHeight) ||
      (result.cols <= 60 ? 26 : result.cols <= 120 ? 21 : 17);
    var padding =
      opts.padding == null ? Math.max(16, Math.round(cellHeight * 1.15)) : opts.padding;

    var width = result.cols * cellHeight * cellAspect + padding * 2;
    var height = result.rows * cellHeight + padding * 2;
    var scale = Math.min(
      1,
      MAX_EXPORT_EDGE / Math.max(1, width),
      MAX_EXPORT_EDGE / Math.max(1, height)
    );
    if (scale < 1) {
      cellHeight = Math.max(2, cellHeight * scale);
      padding = Math.max(4, padding * scale);
      width = result.cols * cellHeight * cellAspect + padding * 2;
      height = result.rows * cellHeight + padding * 2;
    }

    var canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    var ctx = canvas.getContext('2d');
    var background = opts.background || DEFAULT_BACKGROUND;
    ctx.fillStyle = background;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.translate(padding, padding);

    var contentWidth = result.cols * cellHeight * cellAspect;
    var contentHeight = result.rows * cellHeight;
    drawAscii(ctx, result, contentWidth, contentHeight, {
      colorMode: opts.colorMode,
      accent: opts.accent,
      fontWeight: opts.fontWeight
    });

    return canvas;
  }

  root.AsciiRenderer = Object.freeze({
    FONT_STACK: FONT_STACK,
    DEFAULT_BACKGROUND: DEFAULT_BACKGROUND,
    DEFAULT_ACCENT: DEFAULT_ACCENT,
    fitSize: fitSize,
    drawAscii: drawAscii,
    paintPreview: paintPreview,
    renderExportCanvas: renderExportCanvas
  });
})(typeof globalThis !== 'undefined' ? globalThis : this);
