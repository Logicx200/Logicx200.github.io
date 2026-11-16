/*!
 * ASCII Studio — pixel canvas renderer
 * 负责把限制色板后的像素网格以整数倍、无平滑的方式绘制到画布。
 */
(function (root) {
  'use strict';

  var MAX_EXPORT_EDGE = 4096;

  function clamp(value, min, max) {
    if (!Number.isFinite(value)) return min;
    return value < min ? min : value > max ? max : value;
  }

  function getSource(canvas) {
    var source = canvas.__pixelSource;
    if (!source) {
      var sourceCanvas = document.createElement('canvas');
      source = {
        canvas: sourceCanvas,
        ctx: sourceCanvas.getContext('2d')
      };
      canvas.__pixelSource = source;
    }
    return source;
  }

  function drawPixelSource(ctx, result, x, y, width, height) {
    var source = getSource(ctx.canvas);
    var sourceCanvas = source.canvas;
    if (sourceCanvas.width !== result.cols || sourceCanvas.height !== result.rows) {
      sourceCanvas.width = result.cols;
      sourceCanvas.height = result.rows;
    }
    source.ctx.setTransform(1, 0, 0, 1, 0, 0);
    source.ctx.imageSmoothingEnabled = false;
    var imageData = new ImageData(result.pixels, result.cols, result.rows);
    source.ctx.putImageData(imageData, 0, 0);

    ctx.imageSmoothingEnabled = false;
    if ('mozImageSmoothingEnabled' in ctx) ctx.mozImageSmoothingEnabled = false;
    ctx.drawImage(sourceCanvas, x, y, width, height);
  }

  /**
   * 自适应预览：用设备像素的整数倍放大，保证每个逻辑像素边界清晰。
   * @param {HTMLCanvasElement} canvas
   * @param {object} result PixelCore.convertPixels() 返回值
   * @param {object} options
   * @param {number} options.boxWidth CSS 可用宽度
   * @param {number} options.boxHeight CSS 可用高度
   * @param {number} [options.dpr=1]
   * @returns {{width:number,height:number,scale:number,dpr:number}|null}
   */
  function paintPreview(canvas, result, options) {
    if (!canvas || !result || !result.pixels) return null;
    var opts = options || {};
    var boxWidth = Math.max(1, Number(opts.boxWidth) || 1);
    var boxHeight = Math.max(1, Number(opts.boxHeight) || 1);
    var dpr = clamp(Number(opts.dpr) || 1, 0.75, 3);

    var maxScale = Math.min(
      (boxWidth * dpr) / result.cols,
      (boxHeight * dpr) / result.rows
    );
    var scale = Math.max(1, Math.floor(maxScale));
    var pixelWidth = result.cols * scale;
    var pixelHeight = result.rows * scale;

    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }

    var cssWidth = Math.round((pixelWidth / dpr) * 100) / 100 + 'px';
    var cssHeight = Math.round((pixelHeight / dpr) * 100) / 100 + 'px';
    if (canvas.style.width !== cssWidth) canvas.style.width = cssWidth;
    if (canvas.style.height !== cssHeight) canvas.style.height = cssHeight;
    canvas.style.imageRendering = 'pixelated';

    var ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, pixelWidth, pixelHeight);
    drawPixelSource(ctx, result, 0, 0, pixelWidth, pixelHeight);

    return {
      width: pixelWidth / dpr,
      height: pixelHeight / dpr,
      scale: scale,
      dpr: dpr
    };
  }

  /**
   * 导出高清 PNG：每个逻辑像素放大为整数倍，保持硬边缘。
   * @param {object} result PixelCore.convertPixels() 返回值
   * @param {object} [options]
   * @param {number} [options.scale] 强制每格倍数
   * @returns {HTMLCanvasElement}
   */
  function renderExportCanvas(result, options) {
    var opts = options || {};
    var desiredWidth = opts.targetWidth || 1600;
    var scale = Number(opts.scale) || Math.max(2, Math.floor(desiredWidth / result.cols));
    scale = Math.max(1, Math.min(48, scale));
    scale = Math.min(
      scale,
      Math.max(1, Math.floor(MAX_EXPORT_EDGE / result.cols)),
      Math.max(1, Math.floor(MAX_EXPORT_EDGE / result.rows))
    );

    var canvas = document.createElement('canvas');
    canvas.width = result.cols * scale;
    canvas.height = result.rows * scale;
    var ctx = canvas.getContext('2d');
    ctx.imageSmoothingEnabled = false;
    drawPixelSource(ctx, result, 0, 0, canvas.width, canvas.height);
    return canvas;
  }

  root.PixelRenderer = Object.freeze({
    paintPreview: paintPreview,
    renderExportCanvas: renderExportCanvas
  });
})(typeof globalThis !== 'undefined' ? globalThis : this);
