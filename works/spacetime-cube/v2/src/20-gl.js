/* 时空立方体 · WebGL2 基础设施
 *
 * 这里做四件事：
 *   1. 创建 context 并如实上报它的能力上限（MAX_TEXTURE_SIZE 是「原画质」的硬边界）；
 *   2. 编译着色器，把编译日志完整保留下来 —— 编译失败时画面会全空，
 *      而 JS 那边一切正常，所以这类错误必须显式暴露，不能只丢给控制台；
 *   3. 缓冲/纹理/VAO 的小工具；
 *   4. 记录每一次 draw call 和估算的显存占用，供 HUD 显示。
 */
(function (STC) {
  'use strict';

  var MAX_REPORTED_ERRORS = 12;

  function create(canvas) {
    var gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: true,
      stencil: false,
      premultipliedAlpha: false,
      preserveDrawingBuffer: true,
      powerPreference: 'high-performance',
      desynchronized: false
    });
    if (!gl) {
      throw new Error('这个浏览器没能提供 WebGL2 上下文。\n' +
        '请用较新的 Chrome / Edge / Firefox，并确认没有关闭硬件加速。');
    }

    var errors = [];
    function report(kind, msg) {
      if (errors.length < MAX_REPORTED_ERRORS) {
        errors.push('[' + kind + '] ' + msg);
      } else if (errors.length === MAX_REPORTED_ERRORS) {
        errors.push('… 更多错误已省略');
      }
    }

    var info = {
      version: gl.getParameter(gl.VERSION),
      vendor: gl.getParameter(gl.VENDOR),
      renderer: gl.getParameter(gl.RENDERER),
      maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      maxTexUnits: gl.getParameter(gl.MAX_COMBINED_TEXTURE_IMAGE_UNITS),
      maxRenderbuffer: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
      maxViewport: gl.getParameter(gl.MAX_VIEWPORT_DIMS),
      pointRange: gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE),
      maxVertexAttribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS)
    };

    /* ------------------------------------------------------------ 着色器 */

    function compile(type, src, label) {
      var sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        var log = gl.getShaderInfoLog(sh) || '(无日志)';
        report('shader:' + label, log.trim() + '\n' + numberLines(src));
        gl.deleteShader(sh);
        return null;
      }
      return sh;
    }

    function program(vsSrc, fsSrc, label, attribs) {
      label = label || 'program';
      var vs = compile(gl.VERTEX_SHADER, vsSrc, label + '.vert');
      var fs = compile(gl.FRAGMENT_SHADER, fsSrc, label + '.frag');
      if (!vs || !fs) return null;
      var p = gl.createProgram();
      gl.attachShader(p, vs);
      gl.attachShader(p, fs);
      if (attribs) {
        for (var i = 0; i < attribs.length; i++) {
          gl.bindAttribLocation(p, i, attribs[i]);
        }
      }
      gl.linkProgram(p);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
        report('link:' + label, (gl.getProgramInfoLog(p) || '(无日志)').trim());
        gl.deleteProgram(p);
        return null;
      }
      return wrapProgram(p, label);
    }

    /** 把 program 包装成「缓存 uniform 位置」的对象 */
    function wrapProgram(p, label) {
      var locs = Object.create(null);
      return {
        program: p,
        label: label,
        use: function () { gl.useProgram(p); return this; },
        /** 取 uniform 位置（缓存；不存在时返回 null，调用方自己跳过） */
        u: function (name) {
          if (!(name in locs)) locs[name] = gl.getUniformLocation(p, name);
          return locs[name];
        },
        /** 只在位置存在时设置，省掉一堆 if */
        set: function (name, fn) {
          var l = this.u(name);
          if (l) fn(l);
          return this;
        },
        attrib: function (name) { return gl.getAttribLocation(p, name); }
      };
    }

    /* -------------------------------------------------------------- 缓冲 */

    function buffer(data, target) {
      var b = gl.createBuffer();
      var t = target || gl.ARRAY_BUFFER;
      gl.bindBuffer(t, b);
      gl.bufferData(t, data, gl.STATIC_DRAW);
      gl.bindBuffer(t, null);
      return b;
    }

    /**
     * 建一个 2D 纹理。关键点：
     *   - 一律上传原始尺寸，绝不缩放（原画质的第一道保证）；
     *   - internalFormat 与 format 都用 RGBA/UNSIGNED_BYTE，
     *     不做任何色彩空间转换，像素值原样进显存；
     *   - LINEAR 时也不生成 mipmap，避免引入非原始像素。
     */
    function texture2D(opts) {
      var t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      var filter = opts.filter || gl.LINEAR;
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      if (opts.flipY) gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, opts.source);
      if (opts.flipY) gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.bindTexture(gl.TEXTURE_2D, null);
      var err = gl.getError();
      if (err !== gl.NO_ERROR) {
        report('texture', '上传 ' + (opts.label || '') + ' 失败（GL 错误 0x' + err.toString(16) + '）' +
          '，尺寸 ' + (opts.source.width || '?') + '×' + (opts.source.height || '?'));
        gl.deleteTexture(t);
        return null;
      }
      return t;
    }

    /**
     * 用**显式尺寸 + 像素数据**建一张 2D 纹理（侧面颜色条用）。
     *
     * 这里有一道必须有的闸门：`data` 的字节数必须**正好**等于 width×height×4。
     * texImage2D 的这个重载只认宽高，多出来的数据会被**静默丢弃** ——
     * 早先侧面图集算出了 W×n 的像素却按 W×1 上传，n-1 帧的数据全被丢掉，
     * 而且一个错误都不报。表现就是"侧面颜色每一帧都一样"。
     * 现在长度不对就直接报错、返回 null，宁可没有侧面也不要错的侧面。
     */
    function edgeTexture(width, height, data, filter) {
      var need = width * height * 4;
      if (!data || data.byteLength !== need) {
        report('texture', '侧面图集尺寸与数据不符：声明 ' + width + '×' + height +
          '（需要 ' + need + ' 字节），实际 ' + (data ? data.byteLength : 'null') +
          ' 字节。已放弃这张图集，而不是上传一张被截断的。');
        return null;
      }
      var t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      var f = filter || gl.NEAREST;
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, f);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, f);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      // 行序由 CPU 侧决定（第 0 行就是第 0 帧），显式关掉翻转
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, data);
      gl.bindTexture(gl.TEXTURE_2D, null);
      var err = gl.getError();
      if (err !== gl.NO_ERROR) {
        report('texture', '上传侧面图集失败（GL 错误 0x' + err.toString(16) + '），尺寸 ' +
          width + '×' + height);
        gl.deleteTexture(t);
        return null;
      }
      return t;
    }

    function vao(setup) {
      var v = gl.createVertexArray();
      gl.bindVertexArray(v);
      setup();
      gl.bindVertexArray(null);
      return v;
    }

    /** 把某个 buffer 绑定到固定位置的 attrib 上 */
    function attrib(index, buf, size, type, normalized, stride, offset, divisor) {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.enableVertexAttribArray(index);
      gl.vertexAttribPointer(index, size, type || gl.FLOAT, !!normalized, stride || 0, offset || 0);
      if (divisor) gl.vertexAttribDivisor(index, divisor);
    }

    function textureBytes(w, h, layers) {
      return w * h * 4 * (layers || 1);
    }

    return {
      gl: gl,
      info: info,
      errors: errors,
      report: report,
      program: program,
      buffer: buffer,
      texture2D: texture2D,
      edgeTexture: edgeTexture,
      vao: vao,
      attrib: attrib,
      textureBytes: textureBytes,
      getError: function () { return gl.getError(); }
    };
  }

  function numberLines(src) {
    return src.split('\n').map(function (l, i) {
      return String(i + 1).padStart(4, ' ') + ' | ' + l;
    }).join('\n');
  }

  STC.gl = { create: create };
})(window.STC = window.STC || {});
