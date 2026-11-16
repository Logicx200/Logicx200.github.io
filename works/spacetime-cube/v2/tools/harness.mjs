/* Node 侧自检环境：把浏览器里那几个必需的东西做成替身
 *
 * 这不是"模拟浏览器"，而是让 src/ 里的**真实代码**在 Node 里跑起来：
 *   - window / document 的最小替身，够 app.js 完成 boot
 *   - 一个**记录型 WebGL2 替身**：所有 draw 调用都被记下来，
 *     于是"画了什么、按什么顺序画、参数对不对"可以被逐条断言
 *   - 假的 createImageBitmap：从 PNG 头部读尺寸，返回定尺寸的替身
 *
 * 为什么不是「启动无头浏览器截图断言」：
 *   本会话沙箱禁止命名管道，Chromium 的多进程 IPC 起不来，渲染器进程无法启动
 *   （Edge stderr: FATAL mojo platform_channel.cc Check failed 拒绝访问 0x5）。
 *   所以真实的 GPU 渲染在本会话内无法验证，只能验证到"提交给 GL 的指令"这一层。
 *   这一层能抓住绝大多数真实 bug：着色器拼写、uniform 名不一致、混合/深度顺序、
 *   纹理尺寸、实例数、绘制顺序 —— 抓不住的是"GPU 实际算出来的像素长什么样"。
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(here, '..', 'src');

/* ==================================================== 记录型 WebGL2 替身 */

const GL_CONSTS = {  VERSION: 0x1F02, VENDOR: 0x1F00, RENDERER: 0x1F01,
  MAX_TEXTURE_SIZE: 0x0D33, MAX_COMBINED_TEXTURE_IMAGE_UNITS: 0x8B4D,
  MAX_RENDERBUFFER_SIZE: 0x84E8, MAX_VIEWPORT_DIMS: 0x0D3A,
  ALIASED_POINT_SIZE_RANGE: 0x846D, MAX_VERTEX_ATTRIBS: 0x8869,
  COMPILE_STATUS: 0x8B81, LINK_STATUS: 0x8B82,
  VERTEX_SHADER: 0x8B31, FRAGMENT_SHADER: 0x8B30,
  ARRAY_BUFFER: 0x8892, ELEMENT_ARRAY_BUFFER: 0x8893,
  STATIC_DRAW: 0x88E4, FLOAT: 0x1406, UNSIGNED_BYTE: 0x1401,
  TEXTURE_2D: 0x0DE1, TEXTURE0: 0x84C0,
  TEXTURE_MIN_FILTER: 0x2801, TEXTURE_MAG_FILTER: 0x2800,
  TEXTURE_WRAP_S: 0x2802, TEXTURE_WRAP_T: 0x2803,
  LINEAR: 0x2601, NEAREST: 0x2600, CLAMP_TO_EDGE: 0x812F,
  RGBA: 0x1908, DEPTH_TEST: 0x0B71, LEQUAL: 0x0203,
  COLOR_BUFFER_BIT: 0x4000, DEPTH_BUFFER_BIT: 0x0100,
  BLEND: 0x0BE2, SRC_ALPHA: 0x0302, ONE_MINUS_SRC_ALPHA: 0x0303, ONE: 1,
  CULL_FACE: 0x0B44, TRIANGLES: 0x0004, TRIANGLE_STRIP: 0x0005, LINES: 0x0001,
  UNPACK_ALIGNMENT: 0x0CF5, UNPACK_FLIP_Y_WEBGL: 0x9240,
  NO_ERROR: 0, INVALID_ENUM: 0x0500, INVALID_VALUE: 0x0501,
  FRAMEBUFFER: 0x8D40
};

/**
 * 从着色器源码认出它属于哪一个 program。
 *
 * 注意：四个顶点着色器长得几乎一样（都只有 aPos + uProj/uView/uModel），
 * 单看顶点着色器认不出来；而 plane/band/solid 各自的**片元**着色器有独有 uniform。
 * 所以这里按「源码里出现了哪个独有 uniform」判断，任一半认出来即可，
 * 阶段本身不参与判断（拼 program 名字时只取第一个认出来的名字）。
 */
function detectShaderKind(src) {
  if (/uBaseSize/.test(src)) return 'point';
  // 注意：这里必须用 uEdgeTex（band 独有），不能用 uEdge ——
  // 轮廓提取给 PLANE_FS 加了 uEdgeThreshold，用 /uEdge/ 会把**帧平面**认成色带。
  if (/uEdgeTex/.test(src)) return 'band';
  if (/uTex/.test(src)) return 'plane';
  if (/uColor/.test(src)) return 'solid';
  return 'unknown';
}

/**
 * @param {object} opts { maxTextureSize, failShaderMatch:RegExp }
 */
export function createGlStub(opts = {}) {
  const calls = [];
  const objects = [];
  const shaderLabels = new Map();
  const state = {
    program: null, vao: null, texUnit: 0, texByUnit: {},
    activeAttributes: {}, depthMask: null,
    shaderSource: {},
    maxTextureSize: opts.maxTextureSize || 8192,
    // 两类"真 WebGL 会报错、但桩如果只是照抄就抓不到"的违规，单独记下来
    vaoViolations: [],
    textureSizeViolations: []
  };

  function rec(name, args) {
    // 每条调用都带上"当时用的是哪个 program / 哪个 VAO"，
    // 断言才能说清"这条 draw 是谁画的"，而不是靠顶点数去猜
    calls.push({
      name,
      args,
      program: state.program ? state.program.__name : null,
      vao: state.vao ? state.vao.__name : null,
      depthMask: state.depthMask
    });
    if (calls.length > 200000) throw new Error('GL 调用过多，疑似死循环');
  }

  function makeShader(type, src) {
    const id = { kind: 'shader', type, src: String(src), __id: objects.length };
    objects.push(id);
    state.shaderSource[id.__id] = id.src;
    // 故意让某个着色器编译失败，用来验证"编译错误会被如实上报"这条路径
    if (opts.failShaderMatch && opts.failShaderMatch.test(id.src)) id.__fail = true;
    return id;
  }

  const gl = Object.assign({}, GL_CONSTS);

  Object.assign(gl, {
    canvas: null,
    getExtension: () => null,
    getParameter(p) {
      if (p === GL_CONSTS.MAX_TEXTURE_SIZE) return state.maxTextureSize;
      if (p === GL_CONSTS.MAX_VIEWPORT_DIMS) return new Int32Array([16384, 16384]);
      if (p === GL_CONSTS.ALIASED_POINT_SIZE_RANGE) return new Float32Array([1, 1024]);
      if (p === GL_CONSTS.MAX_COMBINED_TEXTURE_IMAGE_UNITS) return 32;
      if (p === GL_CONSTS.MAX_VERTEX_ATTRIBS) return 16;
      return 'stub';
    },

    createShader: (t) => {
      const sh = makeShader(t, '');
      sh.__type = t;
      return sh;
    },
    shaderSource: (sh, src) => {
      sh.src = String(src);
      sh.__kind = detectShaderKind(sh.src);
      rec('shaderSource', [sh.__id, sh.src.length]);
    },
    compileShader: (sh) => rec('compileShader', [sh.__id]),
    getShaderParameter: (sh, p) => (p === GL_CONSTS.COMPILE_STATUS ? !sh.__fail : true),
    getShaderInfoLog: (sh) => (sh.__fail ? 'STUB: 故意注入的编译错误' : ''),
    deleteShader: () => {},

    createProgram: () => { const p = { kind: 'program', __id: objects.length }; objects.push(p); return p; },
    attachShader: (p, sh) => {
      // program 的身份：第一个"认得出来"的着色器决定它的名字。
      // 顶点着色器四个长得一样（认不出来），片元着色器各自有独有 uniform。
      if (sh && sh.__kind && sh.__kind !== 'unknown' && !p.__name) {
        p.__name = sh.__kind;
      }
    },
    bindAttribLocation: () => {}, linkProgram: () => {},
    getProgramParameter: () => true,
    getProgramInfoLog: () => '',
    getUniformLocation: (p, name) => ({ kind: 'uniform', name, program: p }),
    getAttribLocation: () => 0,
    useProgram: (p) => { state.program = p; rec('useProgram', [p && p.__id]); },
    deleteProgram: () => {},

    createBuffer: () => { const b = { kind: 'buffer', __id: objects.length }; objects.push(b); return b; },
    bindBuffer: () => {},
    // delete* 系列是 WebGL2 必备方法。桩里必须存在，否则"再载入一批新照片"
    // 这条释放路径根本跑不到 —— 那正是用户会遇到第二次的情况。
    deleteBuffer: () => {},
    bufferData: (target, data) => {
      rec('bufferData', [target, data && data.byteLength !== undefined ? data.byteLength : -1]);
    },

    createVertexArray: () => { const v = { kind: 'vao', __id: objects.length }; objects.push(v); return v; },
    bindVertexArray: (v) => {
      state.vao = v;
      // 同一个 VAO 反复绑定，第一次出现的序号就是它的可读名字（第几组几何）
      if (v && v.__name === undefined) v.__name = 'vao' + v.__id;
      rec('bindVertexArray', [v ? v.__name : null, v ? v.kind : 'null']);
      /*
       * ★ 这里必须能抓住"把 Buffer 当 VAO 绑定"这类错误。
       *
       * 真 WebGL2 遇到 bindVertexArray(buffer) 会报 INVALID_OPERATION 并**保留**
       * 原来绑定的 VAO，于是后面的 drawArrays 画的是别的几何（或者干脆什么都没有）——
       * 用户看到的现象就是"线框完全没显示"。
       * 桩里如果只是原样记一笔，这类错误就永远抓不到，所以这里单独记一条违规。
       */
      if (v && v.kind !== 'vao') {
        state.vaoViolations.push('bindVertexArray 收到了 ' + v.kind + '（id ' + v.__id + '）');
      }
    },
    deleteVertexArray: () => rec('deleteVertexArray', []),
    enableVertexAttribArray: () => {},
    vertexAttribPointer: (loc, size, type, norm, stride, off) => {
      state.activeAttributes[loc] = { size, stride, off };
      rec('vertexAttribPointer', [loc, size, stride, off]);
    },
    vertexAttribDivisor: (loc, d) => rec('vertexAttribDivisor', [loc, d]),

    createTexture: () => { const t = { kind: 'texture', __id: objects.length, uploads: [] }; objects.push(t); return t; },
    deleteTexture: () => rec('deleteTexture', []),
    activeTexture: (u) => { state.texUnit = u; rec('activeTexture', [u]); },
    bindTexture: (target, t) => {
      state.texByUnit[state.texUnit] = t;
      rec('bindTexture', [target, t ? objects.indexOf(t) : null]);
    },
    texParameteri: () => {},
    pixelStorei: (p, v) => rec('pixelStorei', [p, v]),
    texImage2D(...a) {
      // 两种调用形态：6 参（直接来源）和 9 参（显式尺寸 + 像素数据）
      let info;
      if (a.length >= 9) {
        const w = a[3], h = a[4], data = a[8];
        info = { form: 'size+data', width: w, height: h, bytes: data && data.byteLength };
        /*
         * ★ 尺寸与数据长度必须**正好**相等。
         * 真 WebGL 的 texImage2D 只认宽高，多出来的像素会被静默丢掉 ——
         * 侧面图集就是这么丢掉 n-1 帧、又不报任何错的。桩里把它记成违规。
         */
        const need = w * h * 4;
        if (info.bytes !== undefined && info.bytes !== need) {
          state.textureSizeViolations.push(
            `声明 ${w}×${h}（需要 ${need} 字节），实际 ${info.bytes} 字节`);
        }
      } else {
        const src = a[5];
        info = {
          form: 'source',
          width: src && src.width, height: src && src.height,
          bytes: src && src.width && src.height ? src.width * src.height * 4 : undefined
        };
      }
      const t = state.texByUnit[state.texUnit];
      if (t) t.uploads.push(info);
      // 第四个参数是"数据字节数"，便于断言"尺寸与数据是匹配的"
      rec('texImage2D', [info.form, info.width, info.height, info.bytes]);
    },
    generateMipmap: () => rec('generateMipmap', []),
    getError: () => 0,

    viewport: (x, y, w, h) => rec('viewport', [w, h]),
    clearColor: (r, g, b, a) => rec('clearColor', [r, g, b, a]),
    clear: (m) => rec('clear', [m]),
    enable: (c) => rec('enable', [c]),
    disable: (c) => rec('disable', [c]),
    depthFunc: (f) => rec('depthFunc', [f]),
    depthMask: (m) => { state.depthMask = m; rec('depthMask', [m]); },
    blendFuncSeparate: (...a) => rec('blendFuncSeparate', a),

    drawArrays: (mode, first, count) => rec('drawArrays', [mode, first, count, state.depthMask]),
    drawArraysInstanced: (mode, first, count, instances) =>
      rec('drawArraysInstanced', [mode, first, count, instances, state.depthMask]),
    drawElements: () => rec('drawElements', []),

    readPixels: (x, y, w, h, fmt, type, out) => {
      for (let i = 0; i < out.length; i++) out[i] = 0;
      rec('readPixels', [x, y, w, h]);
    },

    // ---- uniform 设置：全部记录，用来核对"着色器里声明的名字代码里都有设" ----
    uniform1i: (l, v) => rec('uniform1i', [l && l.name, v]),
    uniform1f: (l, v) => rec('uniform1f', [l && l.name, v]),
    uniform2f: (l, x, y) => rec('uniform2f', [l && l.name, x, y]),
    uniform4f: (l, x, y, z, w) => rec('uniform4f', [l && l.name, x, y, z, w]),
    uniformMatrix4fv: (l, t, v) => rec('uniformMatrix4fv', [l && l.name, v && v.length])
  });

  return {
    gl, calls, state, objects,
    /** 取某一类调用 */
    of(name) { return calls.filter((c) => c.name === name); },
    /** 取某个 program 发出的某一类调用，例如 byProgram('drawArrays', 'plane') */
    byProgram(name, which) {
      return calls.filter((c) => c.name === name && c.program === which);
    },
    /** 本帧实际用到的 program 名字 */
    programNames() {
      return [...new Set(calls.filter((c) => c.program).map((c) => c.program))];
    },
    /** 某个纹理对象（按 objects 下标）的实际上传记录 */
    textureUploads(idx) {
      const t = objects[idx];
      return t && t.kind === 'texture' ? t.uploads.slice() : null;
    },
    /** 当前每个纹理单元上绑着哪个纹理（null 表示"没有纹理"） */
    boundTextures() {
      const out = {};
      for (const k of Object.keys(state.texByUnit)) {
        const t = state.texByUnit[k];
        out[k] = t ? objects.indexOf(t) : null;
      }
      return out;
    },
    clear() { calls.length = 0; },
    /** 把 Buffer 当 VAO 绑定的次数（真 WebGL 会 INVALID_OPERATION） */
    vaoViolations() { return state.vaoViolations.slice(); },
    /** texImage2D 声明的尺寸与数据字节数不符的次数（真 WebGL 会静默截断） */
    textureSizeViolations() { return state.textureSizeViolations.slice(); },
    /** 每种 uniform 名字被设置过几次 */
    uniformsSet() {
      const s = new Set();
      for (const c of calls) {
        if (c.name.startsWith('uniform')) s.add(c.args[0]);
      }
      return s;
    }
  };
}

/* ============================================================== DOM 替身 */

function makeClassList() {
  const set = new Set();
  return {
    add: (c) => set.add(c),
    remove: (c) => set.delete(c),
    contains: (c) => set.has(c),
    toggle: (c, on) => { if (on === undefined) { set.has(c) ? set.delete(c) : set.add(c); } else if (on) set.add(c); else set.delete(c); },
    // 让断言里的 'class=' + classList 打出可读内容，而不是 [object Object]
    toString: () => [...set].join(' '),
    _set: set
  };
}

function makeElement(id, tag) {
  const el = {
    id, tagName: (tag || 'div').toUpperCase(),
    textContent: '', value: '', max: '', min: '', disabled: false, checked: false,
    style: {}, dataset: {}, classList: makeClassList(),
    children: [], _listeners: {}, _attrs: {},
    addEventListener(t, fn, opts) {
      const capture = !!(opts && (opts === true || opts.capture));
      (this._listeners[t] = this._listeners[t] || []).push({ fn, capture });
    },
    removeEventListener() {},
    setAttribute(k, v) { this._attrs[k] = String(v); },
    getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; },
    hasAttribute(k) { return k in this._attrs; },
    removeAttribute(k) { delete this._attrs[k]; },
    /** 派发事件；preventDefault 会被记录，供"拦截生效了吗"这类断言使用 */
    dispatch(t, ev) {
      const e = ev || {};
      e.type = t;
      if (!e.target) e.target = this;
      e.defaultPrevented = false;
      e._stopped = false;
      e.preventDefault = function () { this.defaultPrevented = true; };
      e.stopPropagation = function () { this._stopped = true; };
      const list = (this._listeners[t] || []).slice();
      for (const l of list) l.fn(e);
      return e;
    },
    querySelectorAll(sel) {
      if (!sel) return this.children;
      if (sel.charAt(0) === '.') {
        return this.children.filter((c) => c.classList && c.classList.contains(sel.slice(1)));
      }
      return this.children;
    },
    querySelector(sel) {
      const all = this.querySelectorAll(sel);
      return all.length ? all[0] : null;
    },
    appendChild(c) {
      this.children.push(c);
      c.parentNode = this;
      return c;
    },
    removeChild(c) {
      const i = this.children.indexOf(c);
      if (i >= 0) this.children.splice(i, 1);
      c.parentNode = null;
      return c;
    },
    click() { this.dispatch('click', { target: this }); },
    setPointerCapture() {}, releasePointerCapture() {},
    getContext(type) { return this._ctx && this._ctx.type === type ? this._ctx.gl : null; }
  };
  return el;
}

/**
 * 造一个可用的 document / window 替身。
 * @param {object} o { width, height, glStub, ids }
 */
export function createDom(o = {}) {
  const W = o.width || 1200, H = o.height || 800;
  const glStub = o.glStub || createGlStub();
  const byId = {};

  const canvas = makeElement('view', 'canvas');
  canvas.clientWidth = W;
  canvas.clientHeight = H;
  canvas.width = W;
  canvas.height = H;
  canvas._ctx = { type: 'webgl2', gl: glStub.gl };
  glStub.gl.canvas = canvas;
  byId.view = canvas;

  // index.html 里出现的所有元素 id —— app.js 会按 id 取
  const IDS = o.ids || [
    'bar', 'file', 'sort', 'res', 'videoStep', 'status', 'panel', 'frame', 'lbFrame', 'allGhost',
    'opCur', 'lbOpCur', 'opOther', 'lbOpOther', 'otherMode', 'dot', 'lbDot',
    'lumW', 'lbLumW', 'lumT', 'lbLumT', 'lumDir', 'thick', 'lbThick', 'spacing', 'lbSpacing',
    'square', 'edgeMode', 'showBands', 'bandDebug', 'showOutline', 'showCube', 'showAxis', 'viewMode',
    'outline', 'edge', 'lbEdge',
    'clip', 'clipEdit', 'clipAll', 'clipInfo',
    'crop', 'cropWrap', 'cropCanvas', 'cropRect', 'cropInfo', 'cropOk', 'cropCancel', 'cropAll',
    'reset', 'shot', 'foot', 'hud', 'veil', 'veilText', 'veilBar', 'veilCancel', 'fatal',
    'openWrap'
  ];
  for (const id of IDS) if (!byId[id]) byId[id] = makeElement(id, 'div');

  /*
   * 滑块的真实契约是**值存在元素上、标签是"格式化后的显示值"**
   * （range 元素的 textContent 永远是空字符串）。
   * 桩必须照这个来，否则 parseFloat('') → NaN 会被当成有效值写进状态，
   * 把整个几何污染成 depth=null —— 这个坑真的踩过一次，
   * 表现是"色带一条都没画"，而真正的原因在一个毫不相干的滑块上。
   * 这里直接从 src/index.html 读真实默认值，避免桩和页面各写一份。
   */
  const RANGES = {
    opCur: 1, opOther: 0.12, dot: 5, lumW: 0.85, lumT: 0.02,
    thick: 0.02, spacing: 1.6, edge: 0.25
  };
  const LABELS = {
    opCur: 'lbOpCur', opOther: 'lbOpOther', dot: 'lbDot',
    lumW: 'lbLumW', lumT: 'lbLumT', thick: 'lbThick', spacing: 'lbSpacing', edge: 'lbEdge'
  };
  for (const key of Object.keys(RANGES)) {
    if (byId[key]) {
      byId[key].tagName = 'INPUT';
      byId[key].type = 'range';
      byId[key].value = String(RANGES[key]);
    }
    if (byId[LABELS[key]]) byId[LABELS[key]].textContent = RANGES[key].toFixed(2);
  }
  byId.frame.tagName = 'INPUT';
  byId.frame.type = 'range';

  // file 是 <input type="file">，file 要挂在 openWrap 里（透明覆盖式按钮的结构）
  byId.file.tagName = 'INPUT';
  byId.file.type = 'file';
  byId.file.multiple = true;
  byId.file.accept = 'image/*,video/*';
  byId.file.value = '';
  byId.openWrap.classList.add('filewrap');
  byId.openWrap.appendChild(byId.file);

  // videoStep 是 <select>：真实契约是"值在 value 上、选项在 children 上"
  byId.videoStep.tagName = 'SELECT';
  byId.videoStep.value = '1';
  byId.videoStep.children = ['1', '2', '3', '5'].map((v) => {
    const op = makeElement('videoStep:' + v, 'option');
    op.value = v;
    return op;
  });

  // 分段按钮：让 segOn 能找到带 data-v 的按钮
  function segButtons(container, values) {
    container.children = values.map((v) => {
      const b = makeElement(container.id + ':' + v, 'button');
      b.dataset.v = v;
      return b;
    });
    return container;
  }
  segButtons(byId.otherMode, ['plane', 'points']);
  segButtons(byId.edgeMode, ['edge', 'avg']);     // index.html 里没有「关闭」了，总开关是 showBands
  segButtons(byId.viewMode, ['front', 'iso', 'top', 'reset']);
  byId.file.files = null;

  /*
   * 切割选区的编辑器：它需要一块 2D 画布（画当前帧）与一个能报尺寸的容器
   * （把鼠标坐标换算成归一化 uv）。
   *
   * ★ 这里刻意让**外层容器比画布宽得多**，因为真实布局就是这样：
   * `#cropWrap` 是 flex 列的子项、会被拉伸到面板宽度，而画布受 max-width/max-height
   * 限制常常窄得多。如果坐标换算用了外层的矩形，选出来的区域就会整体偏左 ——
   * 这正是用户报的那个 bug，所以桩必须复现这个形状，否则测试是假绿的。
   */
  {
    const cv = byId.cropCanvas;
    cv.tagName = 'CANVAS';
    cv.width = W;
    cv.height = H;
    cv.getContext = (type) => (type === '2d' ? make2d(cv) : null);
    // 外框：宽 800、高 400，从 (60,40) 开始
    const WRAP = { left: 60, top: 40, width: 800, height: 400 };
    // 画布：只占左下角一块 400×300，从 (100,50) 开始 —— 与外框**不同**
    const CANVAS = { left: 100, top: 50, width: 400, height: 300 };
    const rectOf = (b) => () => ({
      left: b.left, top: b.top, width: b.width, height: b.height,
      right: b.left + b.width, bottom: b.top + b.height, x: b.left, y: b.top
    });
    cv.getBoundingClientRect = rectOf(CANVAS);
    byId.cropWrap.getBoundingClientRect = rectOf(WRAP);
    byId.cropRect.getBoundingClientRect = rectOf(CANVAS);
    // 手柄：8 个 <i data-h>，与真实 HTML 一致
    byId.cropRect.children = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map((hh) => {
      const i = makeElement('cropRect:' + hh, 'i');
      i.dataset.h = hh;
      i.parentNode = byId.cropRect;
      return i;
    });
  }

  // document 本身要是可派发事件的，才能测"拖放拦截到底有没有生效"
  const docListeners = {};
  const docAttrs = {};
  const documentShim = {
    readyState: 'complete',
    body: makeElement('body', 'body'),
    documentElement: makeElement('html', 'html'),
    getElementById: (id) => byId[id] || null,
    createElement: (tag) => {
      const el = makeElement('', tag);
      if (tag === 'canvas') {
        el.clientWidth = W;
        el.clientHeight = H;
        el.getContext = (type) => (type === '2d' ? make2d(el) : (type === 'webgl2' ? glStub.gl : null));
      }
      if (tag === 'input') el.type = 'file';
      if (tag === 'video') attachVideoStub(el);
      return el;
    },
    addEventListener(t, fn, opts) {
      const capture = !!(opts && (opts === true || opts.capture));
      (docListeners[t] = docListeners[t] || []).push({ fn, capture });
    },
    removeEventListener() {},
    dispatch(t, ev) {
      const e = ev || {};
      e.type = t;
      if (!e.target) e.target = this;
      e.defaultPrevented = false;
      e.preventDefault = function () { this.defaultPrevented = true; };
      e.stopPropagation = function () { this._stopped = true; };
      for (const l of (docListeners[t] || []).slice()) l.fn(e);
      return e;
    },
    /** 模拟"用户把文件拖到某个元素上"：先跑该元素的监听，再冒泡到 document */
    dispatchOn(target, type, ev) {
      const e = ev || {};
      e.type = type;
      e.target = target;
      e.defaultPrevented = false;
      e._stopped = false;
      e.preventDefault = function () { this.defaultPrevented = true; };
      e.stopPropagation = function () { this._stopped = true; };
      // 捕获阶段：document → 目标
      for (const l of (docListeners[type] || []).slice()) {
        if (l.capture) l.fn(e);
        if (e._stopped) return e;
      }
      if (target && target._listeners && target._listeners[type]) {
        for (const l of target._listeners[type].slice()) l.fn(e);
      }
      // 冒泡阶段：目标 → document
      for (const l of (docListeners[type] || []).slice()) {
        if (!l.capture) l.fn(e);
        if (e._stopped) break;
      }
      return e;
    },
    querySelectorAll: () => [],
    querySelector: () => null,
    _listeners: docListeners
  };

  const windowShim = {
    devicePixelRatio: o.dpr || 1,
    innerWidth: W,
    innerHeight: H,
    addEventListener() {},
    removeEventListener() {},
    document: documentShim,
    location: { search: o.search || '', href: 'http://127.0.0.1:8731/index.html' + (o.search || '') },
    requestAnimationFrame: (fn) => setTimeout(() => fn(performance.now()), 0),
    cancelAnimationFrame: (id) => clearTimeout(id),
    URLSearchParams: globalThis.URLSearchParams,
    performance: globalThis.performance,
    URL: globalThis.URL,
    File: globalThis.File,
    Blob: globalThis.Blob,
    fetch: globalThis.fetch,
    console,
    setTimeout, clearTimeout, setInterval, clearInterval
  };

  return { window: windowShim, document: documentShim, canvas, byId, glStub, W, H };
}

/** 2D 上下文替身：只够 buildPoints/buildEdgeAtlas 走完流程 */
function make2d(el) {
  const w = () => el.width || 1;
  const h = () => el.height || 1;
  return {
    clearRect() {}, drawImage() {},
    getImageData(x, y, ww, hh) {
      return { width: ww, height: hh, data: new Uint8ClampedArray(ww * hh * 4) };
    },
    putImageData() {},
    createImageData: (ww, hh) => ({ width: ww, height: hh, data: new Uint8ClampedArray(ww * hh * 4) }),
    set fillStyle(v) {}, get fillStyle() { return '#000'; },
    fillRect() {}, _size: [w(), h()]
  };
}

/* ======================================================== video 替身 */

/**
 * 给 <video> 元素装上"能播"的行为。
 *
 * 关键点：它必须像真浏览器一样**只通过 requestVideoFrameCallback 报帧**，
 * 因为被测代码正是靠这个回调来"每呈现一帧抓一帧"的。桩里把时间轴按
 * 1/fps 递进，每次触发一个回调，直到超过 duration 再发 ended。
 *
 * 而且它还会**记账**（`__dshVideoStats`）：
 *   presented —— 一共呈现了多少帧
 *   **missed** —— 呈现了但没有登记回调的帧（真浏览器里这些帧就抓不到）
 *   pauses   —— 被暂停了几次（背压是否真的生效）
 * 这三项是"抽帧有没有丢帧"的客观依据，比"我觉得抓到了"可靠。
 *
 * 元信息来自文件上的 `_video = {width, height, fps, duration, dropEvery?}`，
 * 也就是测试里 fakeVideoFile() 造出来的那个描述。
 */
export function attachVideoStub(el) {
  const stats = globalThis.__dshVideoStats || (globalThis.__dshVideoStats = {
    presented: 0, missed: 0, pauses: 0, rvfc: 0
  });
  el.videoWidth = 0;
  el.videoHeight = 0;
  el.duration = NaN;
  el.currentTime = 0;
  el.muted = true;
  el.playsInline = true;
  el.preload = 'auto';
  el.error = null;
  el._rvfc = null;
  el._timer = null;
  el._presented = 0;
  el._dropped = 0;
  el._meta = null;
  el._srcObject = null;
  el.paused = true;

  const stopTimer = () => {
    if (el._timer) { clearInterval(el._timer); el._timer = null; }
  };

  Object.defineProperty(el, 'src', {
    get() { return el._srcObject; },
    set(v) {
      el._srcObject = v;
      el._meta = (globalThis.__dshVideoRegistry && globalThis.__dshVideoRegistry.get(v)) || null;
      if (!el._meta) {
        // 找不到对应文件：模拟"这个格式浏览器解不了"
        setTimeout(() => {
          el.error = { code: 4, message: '不支持的视频源' };
          el.dispatch('error', {});
        }, 0);
        return;
      }
      el.videoWidth = el._meta.width;
      el.videoHeight = el._meta.height;
      el.duration = el._meta.duration;
      setTimeout(() => el.dispatch('loadedmetadata', {}), 0);
    }
  });

  el.play = () => {
    const m = el._meta;
    if (!m) return Promise.reject(new Error('没有视频源'));
    const dt = 1 / (m.fps || 30);
    stopTimer();
    el.paused = false;
    el._timer = setInterval(() => {
      // 先报"当前这一帧"，再推进时间轴 —— 真浏览器第一帧的 mediaTime 就是 0
      if (el.currentTime >= m.duration - 1e-9) {
        stopTimer();
        el.dispatch('ended', {});
        return;
      }
      el._presented++;
      stats.presented++;
      if (m.dropEvery) el._dropped++;
      const cb = el._rvfc;
      el._rvfc = null;
      if (!cb) {
        /*
         * ★ 这一帧"呈现了但没有登记回调" —— 真浏览器里这帧就抓不到了。
         * 第一版的实现正是这样：await 完拷贝才登记下一帧回调，
         * 于是大量帧在这一步被漏掉（用户实测丢 233/325）。
         * 桩把它记成 missed，测试断言它必须是 0。
         */
        stats.missed++;
        el._missed = (el._missed || 0) + 1;
        return;
      }
      cb(performance.now(), { mediaTime: el.currentTime, presentedFrames: el._presented });
      el.currentTime += dt;
    }, 0);
    return Promise.resolve();
  };

  el.pause = () => { stopTimer(); el.paused = true; stats.pauses++; };
  el.load = () => { stopTimer(); };
  el.requestVideoFrameCallback = (cb) => { el._rvfc = cb; stats.rvfc++; return 1; };
  el.cancelVideoFrameCallback = () => { el._rvfc = null; };
  el.getVideoPlaybackQuality = () => ({
    totalVideoFrames: el._presented,
    droppedVideoFrames: el._dropped + (el._missed || 0)
  });
  el.removeAttribute = (k) => { if (k === 'src') { el._srcObject = null; el._meta = null; } };
  el.setAttribute = () => {};
}

/* ======================================================== 加载 src 模块 */

const MODULES = [
  '10-math.js', '20-gl.js', '30-exif.js', '40-seq.js', '45-video.js',
  '50-shaders.js', '55-view.js', '60-renderer.js', '70-app.js'
];

/**
 * 把 src/ 里的模块按顺序执行到一个共享的 window.STC 上。
 * 用 vm 在**当前全局**里跑，所以模块里的 window 就是下面传入的那个替身。
 *
 * @param {object} dom createDom 的结果
 * @param {object} extraGlobals 追加的全局
 * @param {string} [inlineSource] 传入时改为执行这段代码（用于检验打包出来的单文件 HTML），
 *                                不再读取 src/ 下的模块
 * @param {string} [inlineName]  traceback 里显示的文件名
 */
export function loadApp(dom, extraGlobals = {}, inlineSource, inlineName) {
  /*
   * 视频替身需要"这个 blob URL 对应哪个文件"。
   * 真浏览器里是 Blob URL 表，这里用一个进程级注册表模拟，
   * 并且把 URL.createObjectURL / revokeObjectURL 也换成会登记的版本。
   */
  const videoRegistry = new Map();
  globalThis.__dshVideoRegistry = videoRegistry;
  globalThis.__dshVideoStats = { presented: 0, missed: 0, pauses: 0, rvfc: 0 };
  let urlSeq = 0;
  const fakeURL = {
    createObjectURL(file) {
      const u = 'blob:harness/' + (++urlSeq);
      videoRegistry.set(u, file && file._video ? file._video : null);
      return u;
    },
    revokeObjectURL(u) { videoRegistry.delete(u); }
  };

  const sandbox = {
    window: dom.window,
    document: dom.document,
    location: dom.window.location,
    console,
    setTimeout, clearTimeout, setInterval, clearInterval,
    performance: globalThis.performance,
    URL: fakeURL,
    URLSearchParams: globalThis.URLSearchParams,
    // app.js 里有用裸 requestAnimationFrame / devicePixelRatio 的地方，
    // 浏览器里它们是全局的，这里必须补上
    requestAnimationFrame: dom.window.requestAnimationFrame,
    cancelAnimationFrame: dom.window.cancelAnimationFrame,
    devicePixelRatio: dom.window.devicePixelRatio,
    File: globalThis.File,
    Blob: globalThis.Blob,
    TextDecoder, TextEncoder,
    Math, JSON, Date, Object, Array, String, Number, Boolean, Error,
    Promise, Map, Set, WeakMap, Float32Array, Uint8Array, Uint8ClampedArray,
    Uint16Array, Uint32Array, Int32Array, DataView, ArrayBuffer, isNaN, isFinite,
    parseInt, parseFloat, queueMicrotask,
    // 假的解码器：从 PNG 头读尺寸；素材是 canvas / video（视频抽帧那条路）时照抄尺寸
    createImageBitmap: async (source, opts) => {
      const buf = source && source._buf;
      if (buf) {
        const dv = new DataView(buf);
        if (dv.getUint32(0) !== 0x89504e47) throw new Error('不是 PNG');
        return {
          width: dv.getUint32(16), height: dv.getUint32(20),
          close() { this.closed = true; }
        };
      }
      /*
       * 视频抽帧：drawImage(video) → createImageBitmap(canvas)，
       * 或者（直连路径）createImageBitmap(video, {resizeWidth…})。
       *
       * 两个可注入的开关，用来覆盖真实世界里的两种情况：
       *   __dshBitmapDelayMs  每帧拷贝故意变慢（复现"搬不动"→ 背压）
       *   __dshIgnoreResize   故意忽略 resize 参数（模拟个别浏览器）→ 必须退回 canvas 路径
       */
      const delay = globalThis.__dshBitmapDelayMs || 0;
      if (delay > 0) await new Promise((r) => setTimeout(r, delay));
      const sw = source && (source.width || source.videoWidth);
      const sh = source && (source.height || source.videoHeight);
      if (sw && sh) {
        const rw = opts && opts.resizeWidth, rh = opts && opts.resizeHeight;
        const honor = rw && rh && !globalThis.__dshIgnoreResize;
        return {
          width: honor ? rw : sw,
          height: honor ? rh : sh,
          close() { this.closed = true; }
        };
      }
      throw new Error('替身 createImageBitmap 不认识这个来源');
    },
    ...extraGlobals
  };
  sandbox.globalThis = sandbox;
  sandbox.window.STC = sandbox.window.STC || {};

  const ctx = vm.createContext(sandbox);
  vm.runInContext('window.STC = window.STC || {};', ctx);

  if (inlineSource) {
    try {
      vm.runInContext(inlineSource, ctx, { filename: inlineName || 'inline.js' });
    } catch (e) {
      throw new Error('执行内联脚本失败：' + e.message);
    }
    return { ctx, STC: sandbox.window.STC, sandbox };
  }

  for (const m of MODULES) {
    const src = readFileSync(join(SRC, m), 'utf8');
    try {
      vm.runInContext(src, ctx, { filename: m });
    } catch (e) {
      throw new Error('加载 ' + m + ' 失败：' + e.message);
    }
  }
  return { ctx, STC: sandbox.window.STC, sandbox };
}

/* ================================================================ 断言 */

export function createReporter(title, logFile) {
  const results = [];
  const lines = [];
  const emit = (s) => { lines.push(s); console.log(s); };
  return {
    results,
    title,
    check(name, ok, detail) {
      results.push({ name, ok: !!ok, detail: detail === undefined ? '' : String(detail) });
      const mark = ok ? 'PASS' : 'FAIL';
      emit(`[${mark}] ${name}${detail !== undefined ? '  — ' + detail : ''}`);
    },
    near(name, actual, expected, tol, extra) {
      const ok = Math.abs(actual - expected) <= (tol === undefined ? 1e-6 : tol);
      this.check(name, ok, `实际 ${fmt(actual)} / 期望 ${fmt(expected)} ±${tol === undefined ? 1e-6 : tol}` +
        (extra ? '  ' + extra : ''));
      return ok;
    },
    section(t) { emit('\n--- ' + t + ' ---'); },
    summary() {
      const failed = results.filter((r) => !r.ok);
      emit('\n========== ' + (title || '') + ' ==========');
      emit(`共 ${results.length} 项，通过 ${results.length - failed.length}，失败 ${failed.length}`);
      for (const f of failed) emit('  FAIL ' + f.name + '：' + f.detail);
      if (logFile) {
        try {
          writeFileSync(logFile, lines.join('\n') + '\n', 'utf8');
        } catch (e) {
          console.error('写日志失败：' + e.message);
        }
      }
      return failed.length;
    }
  };
}

function fmt(v) {
  if (typeof v !== 'number') return String(v);
  return Math.abs(v) >= 1000 ? v.toFixed(1) : v.toFixed(6);
}
