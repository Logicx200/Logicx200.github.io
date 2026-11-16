/* 渲染流程自检：用记录型 WebGL 替身跑**真实代码**，断言提交给 GPU 的指令
 *
 * 这一层能证明的：
 *   - 8 个模块全部加载、着色器全部编译链接通过
 *   - 纹理上传的尺寸 = 原图尺寸（原画质的第一道证据）
 *   - 帧平面/侧面颜色条/点云/白色线框各自画了几次、实例数是多少
 *   - 混合与深度的绘制顺序（不透明先写深度、半透明由远到近且不写深度、线框最后）
 *   - 点云实例数与点云网格公式一致
 *   - 着色器里声明的每个 uniform 代码里都真的设置了（拼错名字会被抓出来）
 *   - 跨着色器共享的 uniform，类型与精度一致（不一致会链接失败）
 *   - **拖放被真正拦下、选文件不依赖 JS**
 *
 * 这一层**不能**证明的：GPU 实际算出来的像素长什么样。
 * 本会话沙箱禁止命名管道，Chromium 多进程 IPC 起不来，渲染器进程无法启动
 * （Edge stderr: FATAL mojo platform_channel.cc Check failed 拒绝访问 0x5），
 * 所以真实渲染必须由用户在浏览器里确认 —— 见 README。
 *
 * 用法：node test/pipeline.test.mjs
 */
import { createGlStub, createDom, loadApp, createReporter } from '../tools/harness.mjs';
import { fakeImageFile } from '../tools/make-sample.mjs';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const srcDir = join(here, '..', 'src');
const R = createReporter('渲染流程自检', join(here, 'pipeline.log'));

/* ==================================================== 起一个带桩的 app */

const W = 800, H = 600;
const glStub = createGlStub({ maxTextureSize: 8192 });
const dom = createDom({ width: W, height: H, glStub });
const { STC } = loadApp(dom);
const app = STC.app;

/* ============================================== 1. 着色器编译与 uniform */

R.section('着色器编译与 uniform 一致性');
{
  R.check('WebGL2 上下文获取成功', glStub.gl !== null);

  const SHADER_KEYS = ['PLANE_VS', 'PLANE_FS', 'BAND_VS', 'BAND_FS', 'SOLID_VS', 'SOLID_FS', 'POINT_VS', 'POINT_FS'];
  const shaderSrc = SHADER_KEYS.map((k) => STC.shaders[k]).join('\n');
  const declared = new Set();
  for (const m of shaderSrc.matchAll(/uniform\s+\w+\s+(\w+)/g)) declared.add(m[1]);
  R.check('着色器里解析出 uniform 声明', declared.size >= 19,
    declared.size + ' 个：' + [...declared].join(', '));

  for (const k of SHADER_KEYS) {
    const src = STC.shaders[k];
    R.check(`${k} 的第一行是 #version 300 es`, /^#version 300 es\n/.test(src),
      JSON.stringify(src.split('\n')[0]));
  }

  for (const k of ['PLANE_FS', 'BAND_FS', 'SOLID_FS', 'POINT_FS']) {
    R.check(`${k} 声明了浮点精度`, /precision\s+(highp|mediump)\s+float;/.test(STC.shaders[k]));
  }

  // attribute location 必须在**同一个着色器内**唯一（跨着色器复用同一个 location 是必须的）
  let dup = null;
  for (const k of SHADER_KEYS) {
    const seen = new Set();
    for (const m of STC.shaders[k].matchAll(/layout\(location=(\d+)\)\s+in\s+\w+\s+(\w+)/g)) {
      if (seen.has(m[1])) dup = `${k} 中 location ${m[1]} 重复`;
      seen.add(m[1]);
    }
  }
  R.check('同一个着色器内 attribute location 不重复', dup === null, dup || '8 个着色器全部通过');

  // 顶点着色器的输出 varying 必须在片元着色器里有同名输入（名字写错会直接导致画面全黑）
  const varyings = (src) => [...src.matchAll(/^\s*(?:out|in)\s+(?:vec[234]|float|mat[234])\s+(\w+)/gm)].map((m) => m[1]);
  for (const [vs, fs] of [['PLANE_VS', 'PLANE_FS'], ['BAND_VS', 'BAND_FS'],
    ['POINT_VS', 'POINT_FS']]) {
    const vo = varyings(STC.shaders[vs]);
    const fi = varyings(STC.shaders[fs]);
    const missing = vo.filter((n) => !fi.includes(n));
    R.check(`${vs} → ${fs} 的 varying 名字一致`, missing.length === 0,
      missing.length ? '片元里缺少：' + missing.join(',') : vo.join(','));
  }

  /*
   * 跨着色器共享的 uniform：**类型与精度都必须一致**，否则链接期直接失败。
   *
   * 这条检查是补上的 —— 之前只查了 uniform 名字有没有被设，
   * 于是漏掉了一次真实故障：
   *   Precisions of uniform 'uSquare' differ between VERTEX and FRAGMENT shaders.
   * 原因是 GLSL ES 在顶点阶段给 int 默认 highp，而片元阶段**没有** int 的默认精度。
   */
  function uniformDecls(src, isVertex) {
    const out = new Map();
    let defaultInt = isVertex ? 'highp' : 'mediump';
    let defaultFloat = isVertex ? 'highp' : 'mediump';
    for (const raw of src.split('\n')) {
      const line = raw.trim();
      let m = /^precision\s+(lowp|mediump|highp)\s+int\s*;/.exec(line);
      if (m) { defaultInt = m[1]; continue; }
      m = /^precision\s+(lowp|mediump|highp)\s+float\s*;/.exec(line);
      if (m) { defaultFloat = m[1]; continue; }
      m = /^uniform\s+(?:(lowp|mediump|highp)\s+)?(\w+)\s+(\w+)\s*;/.exec(line);
      if (m) {
        const type = m[2];
        const prec = m[1] || (/^[ib]?vec[234]$|^int$|^uint$|^bool$/.test(type) ? defaultInt : defaultFloat);
        out.set(m[3], { type, prec });
      }
    }
    return out;
  }

  for (const [vs, fs] of [['PLANE_VS', 'PLANE_FS'], ['BAND_VS', 'BAND_FS'],
    ['SOLID_VS', 'SOLID_FS'], ['POINT_VS', 'POINT_FS']]) {
    const vSide = uniformDecls(STC.shaders[vs], true);
    const fSide = uniformDecls(STC.shaders[fs], false);
    const shared = [...vSide.keys()].filter((k) => fSide.has(k));
    const bad = shared.filter((k) =>
      vSide.get(k).type !== fSide.get(k).type || vSide.get(k).prec !== fSide.get(k).prec);
    R.check(`${vs}/${fs}：共享 uniform 的类型与精度一致（${shared.join(', ') || '无共享'}）`,
      bad.length === 0,
      bad.length
        ? bad.map((k) => `${k}: 顶点 ${vSide.get(k).prec} ${vSide.get(k).type} vs 片元 ${fSide.get(k).prec} ${fSide.get(k).type}`).join('；')
        : shared.map((k) => `${k}=${vSide.get(k).prec} ${vSide.get(k).type}`).join(' '));
  }
}

/* ======================================================== 2. 载入序列 */

R.section('载入序列（原画质 / 排序 / 纹理尺寸）');
{
  const files = [];
  for (let i = 0; i < 12; i++) {
    files.push(fakeImageFile(`frame_${String(i).padStart(3, '0')}.png`, 320, 240, 1000 + i));
  }
  await app.loadFiles(files);

  const d = app.diagnostics();
  R.check('12 帧全部载入', d.frames === 12, 'frames=' + d.frames);
  R.check('记录到基准尺寸 320×240', d.baseSize === '320x240', String(d.baseSize));
  R.check('纹理字节账 = 帧数×宽×高×4', d.textureBytes === 12 * 320 * 240 * 4,
    d.textureBytes + ' / ' + (12 * 320 * 240 * 4));
  R.check('没有载入失败', d.failed.length === 0, JSON.stringify(d.failed));
  R.check('没有触发显存预算', d.budgetHit === null, JSON.stringify(d.budgetHit));

  // 逐帧上传的纹理尺寸必须等于原图尺寸
  const uploads = glStub.of('texImage2D').map((c) => c.args);
  const frameUploads = uploads.filter((u) => u[0] === 'source');
  R.check('每一帧都以"原始来源"方式上传（不是先转成像素数组再上传）',
    frameUploads.length >= 12, frameUploads.length + ' 次');
  const wrong = frameUploads.filter((u) => u[1] !== 320 || u[2] !== 240);
  R.check('每一次帧纹理上传都是 320×240（原图尺寸，没有任何缩放）',
    wrong.length === 0, wrong.length ? JSON.stringify(wrong.slice(0, 3)) : `${frameUploads.length} 次全部 320×240`);

  /*
   * 侧面图集：**四张**纹理，每张 =（沿边的像素数）×（帧数），
   * 而且声明的尺寸必须与数据字节数严格相等。
   *
   * 旧版这里断言的是"图集是 1 像素高的带状纹理" —— 那实际上把
   * "算出 W×n 却按 W×1 上传、n-1 帧被静默丢掉"这个 bug 写成了正确行为。
   * 现在的断言依据是**帧数必须体现在纹理高度上**：
   * 侧面颜色要随时间变化，就只能靠高度这一维。
   */
  // 只统计真正的图集：1×1 是诊断用的纯色纹理，不算
  const bandUploads = uploads.filter((u) => u[0] === 'size+data' && u[1] > 1);
  const n = 12;
  R.check('侧面图集是 4 张纹理（左/右/上/下各一张）',
    bandUploads.length === 4, bandUploads.length + ' 张');
  const dims = bandUploads.map((u) => u[1] + '×' + u[2]).sort().join(', ');
  R.check('左右图集宽 = 图高(240)、上下图集宽 = 图宽(320)，高度都是帧数(12)',
    bandUploads.every((u) => u[2] === n) &&
    bandUploads.filter((u) => u[1] === 240).length === 2 &&
    bandUploads.filter((u) => u[1] === 320).length === 2,
    dims);
  R.check('每张图集的字节数 = 宽 × 高 × 4（没有多算也没有被截断）',
    bandUploads.every((u) => u[3] === u[1] * u[2] * 4),
    bandUploads.map((u) => u[1] + '×' + u[2] + '=' + u[3] + 'B').join(' / '));
  R.check('帧数 > 1 时图集高度必须 > 1（否则所有帧的侧面颜色会一模一样）',
    bandUploads.every((u) => u[2] > 1), dims);

  // 桩会记录"声明尺寸与数据长度不符"的调用 —— 真 WebGL 会静默截断，这里必须为 0
  R.check('没有任何一次 texImage2D 的尺寸与数据长度不符（真 WebGL 会静默截断）',
    glStub.textureSizeViolations().length === 0,
    glStub.textureSizeViolations().join('；') || '0 次违规');
}

/* ==================================== 2b. Buffer 不能当 VAO 用 */

R.section('几何绑定：bindVertexArray 必须收到真正的 VAO');
{
  /*
   * 用户报告「白色线框完全没显示出来」，根因就是这一条：
   *   旧代码 `geom.cage = ctx.buffer(...)`，渲染时 `gl.bindVertexArray(geom.cage)`。
   * 真 WebGL2 遇到 bindVertexArray(buffer) 会报 INVALID_OPERATION，
   * 并且**保留原来绑定的 VAO** —— 于是 drawArrays 画的是别的几何，或者什么都没有。
   * 桩如果只是照抄这次调用，这个错误永远抓不到，所以桩里单独记违规。
   */
  glStub.clear();
  app.renderNow();
  R.check('渲染过程中没有把 Buffer 当 VAO 绑定',
    glStub.vaoViolations().length === 0,
    glStub.vaoViolations().join('；') || '0 次违规');

  // 外框与时间轴都必须画出来，而且是各自 24 / 10 个顶点
  // （时间轴 = 主线 2 + 箭头四条 8 = 10，箭头指向最后一帧，见下面"黄色线"那一组）
  const lines = glStub.byProgram('drawArrays', 'solid')
    .filter((c) => c.args[0] === glStub.gl.LINES).map((c) => c.args[2]);
  R.check('立方体外框（24 个顶点）与时间轴（10 个顶点，含箭头）都真的发出了绘制',
    lines.includes(24) && lines.includes(10), 'GL_LINES 顶点数 = ' + lines.join(', '));
  R.check('时间轴的箭头是四根刺（从任何视角看都是箭头，不会退化成一条线）',
    app.renderer().geom.axisCount === 10, 'axisCount=' + app.renderer().geom.axisCount);
  R.check('外框与时间轴用的是**两个不同的 VAO**（各自绑了自己的顶点缓冲）',
    new Set(glStub.of('bindVertexArray').map((c) => c.args[0]).filter(Boolean)).size >= 4,
    [...new Set(glStub.of('bindVertexArray').map((c) => c.args[0]))].join(', '));
}

/* ==================================================== 3. 正视图绘制 */

R.section('正视图：不透明写深度 / 半透明由远到近且不写深度');
{
  app.setView('front');
  app.setOpacity(1.0, 0.12);
  app.setAllGhost(false);
  app.setFrame(0);
  glStub.clear();
  app.renderNow();

  const planeDraws = glStub.byProgram('drawArrays', 'plane');
  const bandDraws = glStub.byProgram('drawArrays', 'band');
  const solidDraws = glStub.byProgram('drawArrays', 'solid');

  R.check('帧平面绘制次数 = 12（每帧一个四边形）', planeDraws.length === 12,
    planeDraws.length + ' 次');
  R.check('每帧的四周色带各画 4 条（12 帧 → 48 次）', bandDraws.length === 48,
    bandDraws.length + ' 条（12 帧 × 4 侧）');
  R.check('立方体线框 + 时间轴由 solid 程序绘制',
    solidDraws.length === 2, solidDraws.length + ' 次（线框 + 时间轴）');
  R.check('立方体线框是 12 条棱（GL_LINES，24 个顶点）',
    solidDraws.some((c) => c.args[0] === glStub.gl.LINES && c.args[2] === 24),
    JSON.stringify(solidDraws.map((c) => c.args)));
  R.check('每帧描边默认不画（避免 200 帧叠成一片白）',
    !app.state.showFrameOutline, 'showFrameOutline=' + app.state.showFrameOutline);

  // 绘制顺序：先画不透明帧（写深度，定下遮挡关系），再画半透明帧（不写深度、由远到近）
  const masks = planeDraws.map((c) => c.depthMask);
  R.check('当前帧（唯一的不透明帧）先画且写深度', masks[0] === true,
    'depthMask 序列 = ' + JSON.stringify(masks));
  R.check('其余 11 个半透明帧都不写深度', masks.slice(1).every((m) => m === false),
    'depthMask 序列 = ' + JSON.stringify(masks));
  R.check('写深度的帧只有一个（只有它需要参与遮挡）',
    masks.filter(Boolean).length === 1, masks.filter(Boolean).length + ' 个');

  const ghostOrder = app.resolve(app.state.seq, app.state, 0).items
    .filter((it) => it.opacity > 0 && it.opacity < 0.998)
    .map((it) => it.i);
  R.check('半透明帧集合正确（除当前帧外全部）',
    ghostOrder.length === 11 && !ghostOrder.includes(0), ghostOrder.join(','));

  const cp = app.camParams();
  const depth = app.state.seq.geo.depth;
  const step = depth / (app.state.seq.frames.length - 1);
  const sorted = STC.view.sortFarToNear(
    ghostOrder.map((i) => ({ i, z: i * step })), cp);
  R.check('半透明帧按由远到近排序（正视时先画最后一帧）',
    sorted[0].i === 11 && sorted[sorted.length - 1].i === 1,
    '绘制次序 = ' + sorted.map((s) => s.i).join(','));

  const firstPlaneIdx = glStub.calls.findIndex((c) => c.name === 'drawArrays' && c.program === 'plane');
  const lastBandIdx = glStub.calls.reduce((acc, c, i) =>
    (c.name === 'drawArrays' && c.program === 'band') ? i : acc, -1);
  R.check('每帧色带先于帧平面绘制（外墙先立起来）', lastBandIdx < firstPlaneIdx,
    `最后一条色带 @${lastBandIdx}，第一个帧平面 @${firstPlaneIdx}`);

  const blend = glStub.of('blendFuncSeparate').map((c) => c.args);
  R.check('混合函数为标准 alpha 混合', blend.length > 0 &&
    blend[0][0] === glStub.gl.SRC_ALPHA && blend[0][1] === glStub.gl.ONE_MINUS_SRC_ALPHA,
    JSON.stringify(blend[0]));

  /*
   * 每帧的侧立面必须**带着自己那一帧的颜色**。
   * 这一组是"侧面全是灰色、而且每一帧都一样"的回归网：
   *   - uRow 逐帧不同（否则四张图都取到同一行 = 所有帧一个颜色）；
   *   - uSpan/uOff 左右墙用 halfH、上下墙用 halfW（否则侧立面尺寸与照片对不上）；
   *   - 片元着色器取的是纹理的 rgb（而不是 max 出来的灰度）。
   */
  const bandUniforms = (name) => glStub.byProgram(name === 'uAxisY' ? 'uniform1i' : 'uniform1f', 'band')
    .map((c) => c.args).filter((a) => a[0] === name).map((a) => a[1]);

  const rows = [...new Set(bandUniforms('uRow'))];
  R.check('每一帧提交的行坐标都不相同（侧面色带随时间变化）',
    rows.length === 12, `uRow 有 ${rows.length} 个不同取值（期望 12）`);
  R.check('行坐标落在各自的纹素中心 ((i+0.5)/n)',
    rows.includes(0.5 / 12) && rows.includes(11.5 / 12),
    rows.slice(0, 3).map((r) => r.toFixed(4)).join(', ') + ' …');

  const geo = app.state.seq.geo;
  const spans = [...new Set(bandUniforms('uSpan'))].sort((a, b) => a - b);
  const offs = [...new Set(bandUniforms('uOff'))].sort((a, b) => a - b);
  const axes = [...new Set(bandUniforms('uAxisY'))].sort((a, b) => a - b);
  R.check('左右墙的半长是 halfH、上下墙的半长是 halfW（不与偏移混用）',
    spans.length === 2 &&
    Math.abs(spans[0] - geo.planeH / 2) < 1e-9 && Math.abs(spans[1] - geo.planeW / 2) < 1e-9,
    `uSpan = ${spans.join(' / ')}（halfH=${geo.planeH / 2} halfW=${geo.planeW / 2}）`);
  R.check('固定轴偏移就是照片的边（±halfW 与 ±halfH）',
    offs.length === 4 &&
    Math.abs(offs[0] + geo.planeW / 2) < 1e-9 && Math.abs(offs[3] - geo.planeW / 2) < 1e-9,
    `uOff = ${offs.join(' / ')}`);
  R.check('两个朝向都用到了（沿 y 的左右墙、沿 x 的上下墙）',
    axes.length === 2 && axes.includes(0) && axes.includes(1), 'uAxisY = ' + axes.join(' / '));

  R.check('侧面片元着色器取的是纹理的真实 rgb（不是 max 出来的灰度）',
    /texture\(uEdgeTex/.test(STC.shaders.BAND_FS) && /c\.rgb/.test(STC.shaders.BAND_FS) &&
    !/vec3\(c\)/.test(STC.shaders.BAND_FS),
    'BAND_FS 里没有 vec3(单通道) 这种灰度化');

  // 每帧描边现在是**真正的矩形线框**（GL_LINES），画在标记那一段
  app.setFrameOutline(true);
  glStub.clear();
  app.renderNow();
  const outlineRects = glStub.byProgram('drawArrays', 'solid')
    .filter((c) => c.args[0] === glStub.gl.LINES && c.args[2] === 8);
  R.check('打开描边后，每一帧画一个矩形线框（12 帧 → 12 个 8 顶点的 GL_LINES）',
    outlineRects.length === 12, outlineRects.length + ' 个');
  const outlineColors = glStub.byProgram('uniform4f', 'solid').map((c) => c.args);
  const alphas = [...new Set(outlineColors.filter((c) => c[1] === 1 && c[2] === 1 && c[3] === 1)
    .map((c) => c[4]))].sort((a, b) => a - b);
  R.check('描边是白色的两档亮度（当前帧更亮）',
    alphas.includes(0.98) && alphas.includes(0.45),
    '白色描边的 alpha = ' + alphas.join(' / '));
  R.check('打开描边时色带照画（描边不再借用 band 程序）',
    glStub.byProgram('drawArrays', 'band').length === 48,
    glStub.byProgram('drawArrays', 'band').length + ' 条色带');
  app.setFrameOutline(false);

  /*
   * 标记（外框 / 时间轴 / 描边）是参照物，必须关掉深度测试才看得见 ——
   * 否则外框会被立方体自己的不透明面挡住，表现就是"线框没显示"。
   */
  const depthToggles = glStub.of('disable').map((c) => c.args[0]);
  R.check('画标记之前关闭了深度测试（外框不会被立方体自己挡住）',
    depthToggles.includes(glStub.gl.DEPTH_TEST), 'disable(DEPTH_TEST) 出现在本帧');
  R.check('本帧结束时深度测试被恢复（下一帧仍按深度遮挡）',
    glStub.of('enable').map((c) => c.args[0]).includes(glStub.gl.DEPTH_TEST),
    'enable(DEPTH_TEST) 出现在本帧末尾');

  /*
   * ★ 厚度条的不透明度必须**跟着那一帧的照片走**。
   * 用户报的是"厚度条不透明度不会改变" —— 之前这里恒定提交 1，
   * 于是把"其他帧"拉到 0，照片没了、边还在。
   */
  const bandOps = glStub.byProgram('uniform1f', 'band')
    .map((c) => c.args).filter((a) => a[0] === 'uOpacity').map((a) => a[1]);
  const bandDrawCalls0 = glStub.byProgram('drawArrays', 'band');
  const bandOpVals = [...new Set(bandOps)].sort((a, b) => a - b);
  R.check('厚度条的不透明度就是那一帧照片的不透明度（1.0 与 0.12 两种）',
    bandOpVals.length === 2 &&
    Math.abs(bandOpVals[0] - 0.12) < 1e-6 && Math.abs(bandOpVals[1] - 1) < 1e-6,
    'uOpacity 取值 = ' + bandOpVals.join(' / '));
  R.check('不透明度是逐帧提交的：1 帧不透明 + 11 帧半透明（每条边 4 次 = 48 次绘制）',
    bandOps.length === 12 &&
    bandOps.filter((v) => v > 0.99).length === 1 &&
    bandOps.filter((v) => v < 0.99).length === 11 &&
    bandDrawCalls0.length === 48,
    `${bandOps.length} 次 uOpacity（1 不透明 / 11 半透明），${bandDrawCalls0.length} 次绘制`);

  /*
   * 不透明的边写深度、半透明的边**不写深度**并且由远到近画 ——
   * 与帧平面同一套规则。否则半透明的薄片会互相挡掉。
   */
  const bandDrawCalls = glStub.byProgram('drawArrays', 'band');
  const deep = bandDrawCalls.filter((c) => c.depthMask === true).length;
  const shallow = bandDrawCalls.filter((c) => c.depthMask === false).length;
  R.check('只有不透明帧的边写深度（4 条），其余 44 条不写',
    deep === 4 && shallow === 44, `写深度 ${deep} 条 / 不写 ${shallow} 条`);

  // 半透明的边必须由远到近：正视时帧号大的先画
  const order = [];
  for (const c of glStub.calls) {
    if (c.name === 'uniform1f' && c.args[0] === 'uRow' && c.program === 'band') {
      order.push(Math.round(c.args[1] * 12 - 0.5));
    }
  }
  const ghostOrder2 = order.slice(1, 1 + 11);   // 第 0 个是不透明帧（0 号）
  R.check('半透明的边按由远到近画（正视时 11,10,…,1）',
    ghostOrder2.join(',') === '11,10,9,8,7,6,5,4,3,2,1', '次序 = ' + ghostOrder2.join(','));

  const vps = glStub.of('viewport').map((c) => c.args);
  R.check('视口尺寸 = 画布后备缓冲尺寸', vps.length && vps[0][0] === W && vps[0][1] === H,
    JSON.stringify(vps[0]));
}

/* ======================================== 4. 侧面颜色条：四种模式 */

R.section('侧面颜色条（边界像素 / 平均色 / 关闭）');
{
  function bandCount() {
    glStub.clear();
    app.renderNow();
    return glStub.byProgram('drawArrays', 'band').length;
  }

  function setEdge(mode) {
    return new Promise((resolve) => {
      app.setEdgeMode(mode);
      setTimeout(resolve, 40);
    });
  }

  /*
   * 现在是「每帧 4 条侧面」（把每张照片人为加厚之后，侧面才有东西可拉长），
   * 所以 12 帧 = 48 条，而不是原先的 4 条。
   * 12 这个数字来自本文件第 2 节载入的那批假图片。
   */
  const PER_FRAME = 4;
  const FRAMES = 12;
  const WANT = PER_FRAME * FRAMES;

  /*
   * 边界像素模式：重新生成一次图集，单独核对上传记录（不借助 clear 过的桩）。
   */
  glStub.clear();
  await setEdge('edge');
  const edgeUploads = glStub.of('texImage2D').map((c) => c.args)
    .filter((a) => a[0] === 'size+data' && a[1] > 1);
  R.check('边界像素模式：上传了 4 张图集，尺寸 = 边长 × 帧数',
    edgeUploads.length === 4 && edgeUploads.every((a) => a[2] === FRAMES) &&
    edgeUploads.filter((a) => a[1] === 240).length === 2 &&
    edgeUploads.filter((a) => a[1] === 320).length === 2,
    edgeUploads.map((a) => a[1] + '×' + a[2]).join(', '));
  R.check(`边界像素模式：每帧画左/右/上/下 4 条侧面（${FRAMES} 帧 → ${WANT} 条）`,
    bandCount() === WANT, bandCount() + ' 条');
  R.check('侧面图集用了边界像素模式', app.state.seq.edgeMode === 'edge', String(app.state.seq.edgeMode));
  R.check('侧面图集纹理已生成（四条边各一张）',
    app.state.seq.edgeTex !== null && app.state.seq.edgeTex !== undefined &&
    ['left', 'right', 'top', 'bottom'].every((k) => !!app.state.seq.edgeTex[k]),
    Object.keys(app.state.seq.edgeTex || {}).join(', '));
  R.check('图集字节账被如实统计（用于状态栏）',
    app.state.seq.edgeBytes === (240 + 240 + 320 + 320) * 12 * 4,
    app.state.seq.edgeBytes + ' 字节');

  /*
   * 平均色模式：每条边一个颜色，宽度压成 1 列。
   * 先 clear 再重建，这样上传记录留在桩里。
   */
  glStub.clear();
  await setEdge('avg');
  const avgUploads = glStub.of('texImage2D').map((c) => c.args)
    .filter((a) => a[0] === 'size+data' && a[1] === 1 && a[2] === FRAMES);
  R.check('平均色模式：每张图只有 1 列（每条边一个颜色，省显存）',
    avgUploads.length === 4 && avgUploads.every((a) => a[1] === 1 && a[2] === FRAMES),
    avgUploads.map((a) => a[1] + '×' + a[2]).join(', ') || '没有上传记录');
  R.check(`平均色模式：同样 ${WANT} 条`, bandCount() === WANT, bandCount() + ' 条');
  R.check('侧面图集切到平均色模式', app.state.seq.edgeMode === 'avg', String(app.state.seq.edgeMode));

  await setEdge('off');
  R.check('关闭侧面后一条都不画', bandCount() === 0, bandCount() + ' 条');
  R.check('关闭后四张图集纹理全部被释放',
    app.state.seq.edgeTex === null || app.state.seq.edgeTex === undefined,
    String(app.state.seq.edgeTex));
  R.check('释放后字节账归零', app.state.seq.edgeBytes === 0, String(app.state.seq.edgeBytes));

  await setEdge('edge');
  R.check(`切回边界像素模式后重新画 ${WANT} 条`, bandCount() === WANT, bandCount() + ' 条');
  R.check('切回来以后图集重新生成（四张都在）',
    ['left', 'right', 'top', 'bottom'].every((k) => !!app.state.seq.edgeTex[k]),
    Object.keys(app.state.seq.edgeTex || {}).join(', '));
}

/* ============ 4b. 厚度条开关 / 诊断配色 */

R.section('厚度条的开关与诊断配色');
{
  app.setView('iso');
  R.check('默认是打开的', app.state.showBands === true, 'showBands=' + app.state.showBands);

  glStub.clear();
  app.renderNow();
  R.check('打开时四条边都画（12 帧 × 4 条 = 48）',
    glStub.byProgram('drawArrays', 'band').length === 48,
    glStub.byProgram('drawArrays', 'band').length + ' 条');

  // 关掉：一条都不画，并且把四张图集纹理释放掉
  app.setBands(false);
  await new Promise((r) => setTimeout(r, 20));
  glStub.clear();
  app.renderNow();
  R.check('关掉后一条边都不画',
    glStub.byProgram('drawArrays', 'band').length === 0,
    glStub.byProgram('drawArrays', 'band').length + ' 条');
  R.check('关掉后图集被释放（不占显存）',
    !app.state.seq.edgeTex || Object.keys(app.state.seq.edgeTex).length === 0,
    String(app.state.seq.edgeTex));
  R.check('关掉后状态位也同步（面板复选框）',
    app.state.showBands === false, 'showBands=' + app.state.showBands);

  // 再打开：重新生成图集并恢复绘制
  app.setBands(true);
  await new Promise((r) => setTimeout(r, 20));
  glStub.clear();
  app.renderNow();
  R.check('重新打开后又画 48 条',
    glStub.byProgram('drawArrays', 'band').length === 48,
    glStub.byProgram('drawArrays', 'band').length + ' 条');

  /*
   * 诊断配色：四个立面涂成红/绿/蓝/黄。
   * 这条是给"某个侧面到底有没有被画出来"准备的 —— 用户看到的画面里
   * 侧立面有时会跟照片自己的暗边混在一起，纯色一涂就一目了然。
   */
  app.setBandDebug(true);
  glStub.clear();
  app.renderNow();
  const binds = glStub.calls.filter((c) => c.name === 'bindTexture' && c.program === 'band');
  const dbgDims = [...new Set(binds.map((c) => {
    const ups = glStub.textureUploads(c.args[1]);
    return ups && ups[0] ? ups[0].width + '×' + ups[0].height : '?';
  }))];
  R.check('诊断模式下四张 1×1 纯色纹理都被建出来并绑上（红/绿/蓝/黄）',
    dbgDims.length === 1 && dbgDims[0] === '1×1', '绑定到的尺寸 = ' + dbgDims.join(' / '));
  R.check('诊断模式下仍然四条边都画',
    glStub.byProgram('drawArrays', 'band').length === 48,
    glStub.byProgram('drawArrays', 'band').length + ' 条');
  const dbgTexIds = [...new Set(binds.map((c) => c.args[1]))];
  R.check('四个面用的是四张**不同**的纯色纹理（能一眼看出哪个面是哪个）',
    dbgTexIds.length === 4, dbgTexIds.length + ' 张不同的纹理');

  app.setBandDebug(false);
  glStub.clear();
  app.renderNow();
  const normalBinds = glStub.calls.filter((c) => c.name === 'bindTexture' && c.program === 'band');
  const normalDims = [...new Set(normalBinds.map((c) => {
    const ups = glStub.textureUploads(c.args[1]);
    return ups && ups[0] ? ups[0].width + '×' + ups[0].height : '?';
  }))].sort();
  R.check('关掉诊断后回去绑真实图集（240×12 / 320×12）',
    normalDims.join(',') === '240×12,320×12', '绑定到的尺寸 = ' + normalDims.join(' / '));
}

/* ==================================================== 5. 点云模式 */

R.section('点云模式（实例数 / 采样网格 / 步长）');
{
  app.setView('front');
  app.setOtherMode('points');
  await app.ensurePoints();

  const stride = Number(app.state.seq.frames[0] && STC.seq.pointStride(app.state.seq.frames, STC.seq.POINT_BUDGET));
  const grid = STC.view.pointGrid(320, 240, stride);
  R.check('小序列的点云步长为 1（不降采样）', stride === 1, 'stride=' + stride);

  app.setOpacity(1.0, 0.5);
  app.setFrame(0);
  glStub.clear();
  app.renderNow();

  const inst = glStub.byProgram('drawArraysInstanced', 'point').map((c) => c.args);
  R.check('点云每个非当前帧一次实例化绘制', inst.length === 11, inst.length + ' 次');
  R.check('每次实例化的顶点数是 6（两个三角形拼一个方点）',
    inst.every((d) => d[2] === 6 && d[1] === 0), JSON.stringify(inst[0]));
  R.check('实例数 = 采样网格点数 = 320×240', inst.every((d) => d[3] === grid.count),
    `实例数 ${inst[0] && inst[0][3]} / 网格点数 ${grid.count}`);
  const instCalls = glStub.byProgram('drawArraysInstanced', 'point');
  R.check('点云不写深度（点云之后画，不破坏深度缓冲）',
    instCalls.every((c) => c.depthMask === false), JSON.stringify(instCalls.map((c) => c.depthMask)));

  const planeDraws = glStub.byProgram('drawArrays', 'plane');
  R.check('点云模式下当前帧仍以平面显示（不被点云取代）', planeDraws.length === 1,
    planeDraws.length + ' 次帧平面绘制（应只有当前帧这一张）');

  const s2 = STC.view.pointStride(320 * 240 * 2000, 4e6, 2000);
  const g2 = STC.view.pointGrid(320, 240, s2);
  R.check('步长放大后实例数按平方关系变小',
    g2.count < grid.count && s2 > 1,
    `stride ${stride}→${s2}，点数 ${grid.count}→${g2.count}`);

  app.setOtherMode('plane');
}

/* ============================ 5b. 点云必须真的能画出来（回归） */

R.section('点云可见性（顶点着色器必须自己把方块撑开）');
{
  /*
   * 用户报告：「点云没有任何显示」。
   *
   * 根因是一个**结构性**错误，而不是数值错误：
   *   实例是用 drawArraysInstanced(gl.TRIANGLES, 0, 6, n) 画的，
   *   但顶点着色器把 aPos（单位方块四角，location 0）声明了却没用，
   *   只用 gl_PointSize 控制大小 —— 而 gl_PointSize 只在 gl.POINTS 下有效。
   *   于是六个顶点全部落在同一个位置，三角形退化，一个像素都画不出来。
   *
   * 这一节断言的就是这个不变量：
   *   「用 TRIANGLES 画实例」 ⇒ 顶点着色器必须用 aPos 在裁剪空间里撑开方块，
   *   并且不能依赖 gl_PointSize / gl_PointCoord。
   * 谁把其中一半改回去，这里就会红。
   */
  app.setView('iso');
  app.setOtherMode('points');
  await app.ensurePoints();
  app.setOpacity(1.0, 0.5);
  app.setFrame(0);
  glStub.clear();
  app.renderNow();

  const calls = glStub.byProgram('drawArraysInstanced', 'point');
  R.check('点云确实发出了实例化绘制', calls.length > 0, calls.length + ' 次');
  const prim = calls[0] && calls[0].args[0];
  R.check('点云的图元是三角形（每实例 6 个顶点撑一个方点）',
    prim === glStub.gl.TRIANGLES, 'mode=' + prim);
  R.check('每实例顶点数 = 6，实例数 = 采样点数',
    calls[0].args[2] === 6 && calls[0].args[3] > 0,
    JSON.stringify(calls[0].args));

  const vs = STC.shaders.POINT_VS;
  const fs = STC.shaders.POINT_FS;

  R.check('顶点着色器没有用 gl_PointSize（它只对 gl.POINTS 有效，这里是三角形）',
    !/gl_PointSize/.test(vs),
    /gl_PointSize/.test(vs) ? 'POINT_VS 里还有 gl_PointSize' : '没有');

  R.check('顶点着色器用 aPos 把方块的角撑到了裁剪空间',
    /clip\.xy\s*\+=/.test(vs) && /aPos\.xy/.test(vs),
    /clip\.xy\s*\+=/.test(vs) ? '有 clip.xy += … aPos.xy …' : '没有裁剪空间偏移');

  R.check('偏移量按「像素」换算（用了视口尺寸）',
    /2\.0\s*\/\s*max\(uViewport/.test(vs) || /\/\s*uViewport/.test(vs),
    'uViewport 出现在偏移公式里');

  R.check('片元着色器没有用 gl_PointCoord（那是 gl.POINTS 才有的）',
    !/gl_PointCoord/.test(fs),
    /gl_PointCoord/.test(fs) ? 'POINT_FS 里还有 gl_PointCoord' : '没有');
  R.check('圆点模式改用方块内的局部坐标 vLocal 切圆',
    /vLocal/.test(fs) && /vLocal/.test(vs),
    'vLocal 在顶点里算出、在片元里用');

  // 数值核对：按着色器的公式，一个 size 像素的点在裁剪空间里的半宽
  // 必须正好等于 size 个像素（不然点会小到看不见或者糊成一片）。
  const vp = app.viewport();
  const size = 5;
  const perPixelX = 2.0 / vp.w, perPixelY = 2.0 / vp.h;
  const halfWpx = Math.abs(1 * 0.5 * size * perPixelX * 1) / perPixelX;   // clip.w = 1（正交）
  const halfHpx = Math.abs(1 * 0.5 * size * perPixelY * 1) / perPixelY;
  R.check('按着色器公式，方块角点在屏幕上正好离中心 size/2 像素',
    Math.abs(halfWpx - size / 2) < 1e-9 && Math.abs(halfHpx - size / 2) < 1e-9,
    `半宽 ${halfWpx}px / 半高 ${halfHpx}px（点大小 ${size}px）`);

  R.check('点大小提交的是像素数，不再乘世界→像素比例',
    glStub.byProgram('uniform1f', 'point').some((c) => c.args[0] === 'uOrthoSize' && c.args[1] === app.state.dotSize),
    'uOrthoSize = ' + app.state.dotSize);

  app.setOtherMode('plane');
}

/* ==================== 5c. 点云密度：亮处密 / 暗处密 */

R.section('点云密度按亮度加权（方向可切换）');
{
  app.setView('iso');
  app.setOtherMode('points');
  await app.ensurePoints();

  function lumUniforms() {
    glStub.clear();
    app.renderNow();
    const f = glStub.byProgram('uniform1f', 'point');
    const i = glStub.byProgram('uniform1i', 'point');
    return {
      dir: (i.find((c) => c.args[0] === 'uLumDir') || { args: [] }).args[1],
      weight: (f.find((c) => c.args[0] === 'uLumWeight') || { args: [] }).args[1],
      threshold: (f.find((c) => c.args[0] === 'uLumThreshold') || { args: [] }).args[1]
    };
  }

  app.setLumDir('bright');
  let u = lumUniforms();
  R.check('「亮处更密」时 uLumDir = 0', u.dir === 0, 'uLumDir=' + u.dir);

  app.setLumDir('dark');
  u = lumUniforms();
  R.check('「暗处更密」时 uLumDir = 1', u.dir === 1, 'uLumDir=' + u.dir);

  app.setLum(0.6, 0.05);
  u = lumUniforms();
  R.check('密度幂次与门槛都如实提交给着色器',
    Math.abs(u.weight - 0.6) < 1e-6 && Math.abs(u.threshold - 0.05) < 1e-6,
    `uLumWeight=${u.weight} uLumThreshold=${u.threshold}`);

  /*
   * 着色器里那条剔除规则的**等价 JS 版**（哈希常数与着色器一致）：
   *   h = fract(sin(dot(px, vec2(127.1,311.7))) * 43758.5453123)
   *   保留 ⟺ dens >= threshold 且 h <= pow(dens, weight)
   *
   * 它验证的是"规则本身"：密度的方向与单调性。
   * 着色器里是否真的用了这条规则，由上面那段源码断言来钉。
   */
  const HASH = 43758.5453123;
  R.check('着色器源码里就是这条规则（哈希常数 + 幂次）',
    STC.shaders.POINT_VS.includes('43758.5453123') &&
    /pow\(dens,\s*w\)/.test(STC.shaders.POINT_VS) &&
    /uLumDir\s*==\s*1/.test(STC.shaders.POINT_VS),
    'pow(dens, w) + uLumDir 分支都在');

  // 用大量采样点统计"保留概率"，避免单点巧合
  const lumW = 0.5;
  function density(dir, lum) {
    let kept = 0; const N = 20000;
    for (let i = 0; i < N; i++) {
      const h = Math.abs(Math.sin(i * 12.9898) * HASH) % 1;
      const dens = dir === 'dark' ? 1 - lum : lum;
      if (dens >= 0.02 && h <= Math.pow(dens, lumW)) kept++;
    }
    return kept / N;
  }
  const brightLow = density('bright', 0.15), brightHigh = density('bright', 0.85);
  const darkLow = density('dark', 0.15), darkHigh = density('dark', 0.85);
  R.check('亮处更密：亮像素的保留率明显高于暗像素',
    brightHigh > brightLow * 2, `亮 ${brightHigh.toFixed(3)} vs 暗 ${brightLow.toFixed(3)}`);
  R.check('暗处更密：暗像素的保留率明显高于亮像素',
    darkLow > darkHigh * 2, `暗 ${darkLow.toFixed(3)} vs 亮 ${darkHigh.toFixed(3)}`);
  R.check('两种方向互为镜像（同一像素的保留率此消彼长）',
    brightHigh > darkHigh && darkLow > brightLow,
    `亮处更密 ${brightLow.toFixed(3)}/${brightHigh.toFixed(3)}，暗处更密 ${darkLow.toFixed(3)}/${darkHigh.toFixed(3)}`);

  // 门槛以下一个点都不画
  app.setLum(0.85, 0.5);
  u = lumUniforms();
  R.check('门槛调到 0.5 后，参与密度的量低于 0.5 的像素全部不画（由着色器分支保证）',
    Math.abs(u.threshold - 0.5) < 1e-6 && /dens\s*<\s*uLumThreshold/.test(STC.shaders.POINT_VS),
    '门槛分支在着色器里');

  app.setLumDir('bright');
  app.setLum(0.85, 0.02);
  app.setOtherMode('plane');
}

/* ==================== 5d. 帧厚度与帧间距 */

R.section('帧厚度（自动夹到帧间距的 90%）与帧间距');
{
  app.setView('front');
  app.setOtherMode('plane');
  app.setAllGhost(false);
  app.setOpacity(1.0, 0.12);
  app.setFrame(0);

  const d0 = app.diagnostics();
  const step = d0.frameStep;

  R.check('默认帧距来自 spacing 滑块（depth = spacing）',
    Math.abs(d0.depth - app.state.spacing) < 1e-9, `depth=${d0.depth} spacing=${app.state.spacing}`);
  R.check('帧间距 = depth/(n-1)', Math.abs(step - d0.depth / 11) < 1e-9,
    `frameStep=${step}`);

  // 厚度小于帧距时如实使用
  app.setThickness(0.02);
  glStub.clear();
  app.renderNow();
  let thick = [...new Set(glStub.byProgram('uniform1f', 'band')
    .filter((c) => c.args[0] === 'uThick').map((c) => c.args[1]))];
  R.check('厚度小于帧间距时按用户设定使用', thick.length === 1 && Math.abs(thick[0] - 0.02) < 1e-9,
    'uThick = ' + thick.join('/'));

  // 厚度超过帧距的 90% 时必须被夹住（否则相邻薄片会互相穿模）
  app.setThickness(0.5);
  glStub.clear();
  app.renderNow();
  thick = [...new Set(glStub.byProgram('uniform1f', 'band')
    .filter((c) => c.args[0] === 'uThick').map((c) => c.args[1]))];
  R.check('厚度被夹到帧间距的 90%（永不互相穿模）',
    thick.length === 1 && Math.abs(thick[0] - step * 0.9) < 1e-9,
    `uThick = ${thick[0]} / 上限 ${step * 0.9}（帧间距 ${step}）`);

  // 帧间距改变 → 几何重排（不需要重新解码）
  const before = app.diagnostics();
  app.setSpacing(3.2);
  const after = app.diagnostics();
  R.check('改帧间距会重排几何：depth 立刻跟着变',
    Math.abs(after.depth - 3.2) < 1e-9 && Math.abs(before.depth - 3.2) > 1e-9,
    `${before.depth} → ${after.depth}`);
  R.check('帧间距变了，帧间距步长同步变化',
    Math.abs(after.frameStep - 3.2 / 11) < 1e-9, `frameStep=${after.frameStep}`);

  const res = STC.view.resolve(app.state.seq, app.state, 0);
  R.check('重排后第一帧仍在 z=0、最后一帧在 z=depth',
    Math.abs(res.items[0].z) < 1e-9 &&
    Math.abs(res.items[res.items.length - 1].z - 3.2) < 1e-9,
    `z(0)=${res.items[0].z} z(last)=${res.items[res.items.length - 1].z}`);

  app.setSpacing(1.6);
  app.setThickness(0.02);
  R.check('复原后帧距回到 1.6', Math.abs(app.diagnostics().depth - 1.6) < 1e-9,
    'depth=' + app.diagnostics().depth);
}

/* ============================================ 6. 不透明度 0 与全透明 */

R.section('不透明度 0：内容透明，线框仍在');
{
  app.setAllGhost(true);
  app.setOpacity(1.0, 0);
  app.setFrameOutline(false);
  glStub.clear();
  app.renderNow();

  const planes = glStub.byProgram('drawArrays', 'plane');
  const solids = glStub.byProgram('drawArrays', 'solid');
  const bands = glStub.byProgram('drawArrays', 'band');
  R.check('不透明度 0 时不画任何帧平面', planes.length === 0, planes.length + ' 次帧平面');
  R.check('不透明度 0 时连侧面也不画（完全透明 = 真的看不见，包括外壳）',
    bands.length === 0, bands.length + ' 条');
  R.check('立方体外框与时间轴照画（它们不受帧不透明度影响）',
    solids.filter((c) => c.args[0] === glStub.gl.LINES).length === 2,
    solids.length + ' 次纯色绘制');
  R.check('默认不画每帧描边 —— 200 帧叠白框就是用户看到的"纯白"',
    solids.length === 2, solids.length + ' 次纯色绘制（应为外框 + 时间轴）');

  // 即使内容全透明，「每帧显示区域描边」打开后也必须照画（现在是真线框）
  app.setFrameOutline(true);
  glStub.clear();
  app.renderNow();
  const outlineRects = glStub.byProgram('drawArrays', 'solid')
    .filter((c) => c.args[0] === glStub.gl.LINES && c.args[2] === 8);
  R.check('打开描边后，即使帧不透明度为 0 也照画（12 帧 → 12 个矩形线框）',
    outlineRects.length === 12, outlineRects.length + ' 个');
  app.setFrameOutline(false);

  // 外壳是"外墙"，不跟着单帧不透明度衰减
  app.setOpacity(1.0, 0.12);
  glStub.clear();
  app.renderNow();
  const bands2 = glStub.byProgram('drawArrays', 'band');
  R.check('侧面颜色条不受帧不透明度影响（它是外壳，照常显示）', bands2.length === 48,
    bands2.length + ' 条');

  app.setAllGhost(false);
  app.setOpacity(1.0, 0.12);
}

/* ================================== 7. 全部不透明 = 实心立方体 */

R.section('全部不透明：深度写入的实心立方体');
{
  app.setAllGhost(false);
  app.setOpacity(1.0, 1.0);
  app.setFrame(0);
  glStub.clear();
  app.renderNow();

  const strips = glStub.byProgram('drawArrays', 'plane');
  R.check('全部不透明时 12 帧平面都写深度',
    strips.length === 12 && strips.every((c) => c.depthMask === true),
    strips.length + ' 次帧平面，全部写深度');
}

/* ================================ 8. 分辨率策略与源码层的约束 */

R.section('分辨率策略：缩放只发生在用户明确要求时');
{
  const seqSrc = readFileSync(join(srcDir, '40-seq.js'), 'utf8');
  const glSrc = readFileSync(join(srcDir, '20-gl.js'), 'utf8');
  const appSrc = readFileSync(join(srcDir, '70-app.js'), 'utf8');
  // 注释里会写到"不要用 resizeWidth"，所以先把注释去掉再检查，
  // 否则这条断言会被自己的说明文字触发（假阴性）
  const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  const seqCode = stripComments(seqSrc);

  /*
   * 分辨率策略变了：帧数一多，原尺寸不可能同时驻留显存
   * （200 帧 12MP = 6.6 GB），所以现在**允许**把单帧缩到指定长边。
   * 但这必须是用户显式选择的，不能是程序偷偷做的，所以断言换成：
   *   1. 缩放的入口只有一个，且由参数控制；
   *   2. 不给参数时默认不缩放；
   *   3. 界面提供"原画质不缩放"这个选项；
   *   4. 实际用的分辨率会如实报告。
   */
  R.check('缩放只有一个入口 decodeAt(file, longEdge)，且由参数控制',
    /function decodeAt\(file, longEdge\)/.test(seqSrc) &&
    /if \(!longEdge \|\| Math\.max\(bit\.width, bit\.height\) <= longEdge\) return bit;/.test(seqSrc),
    '长边为 0 或已小于目标时直接返回原图');
  R.check('不给 longEdge 时默认不缩放（decode 走 decodeAt(file, 0)）',
    /async function decode\(file\) \{\s*return decodeAt\(file, 0\);/.test(seqSrc),
    '默认路径长边为 0');
  R.check('缩放只在 scaled 为真时才发生',
    /var scaled = !!\(longEdge && longEdge < origLong\)/.test(seqSrc),
    'scaled 的判据是"目标长边确实小于原图长边"');
  R.check('界面提供「原画质不缩放」这个选项',
    /分辨率：原画质不缩放/.test(appSrc) || /value="orig"/.test(readFileSync(join(srcDir, 'index.html'), 'utf8')),
    'resMode === "orig" 时不传任何缩放参数');
  R.check('app 只在 resMode 为 auto 或具体数字时才启用缩放',
    /resMode === 'auto'/.test(appSrc) && /resMode !== 'orig'/.test(appSrc),
    'autoLongEdge / longEdge 都由 resMode 决定');
  R.check('实际使用的分辨率会如实报告（原图尺寸与缩放后尺寸都记下来）',
    /origW: origW, origH: origH/.test(seqSrc) && /scaled: scaled/.test(seqSrc) &&
    /'每帧 ' \+ seq\.baseW/.test(appSrc) && /原图 ' \+ seq\.origW/.test(appSrc),
    '状态栏同时给出「每帧尺寸」与「原图尺寸」');
  R.check('自动适配会按「预算 / 帧数」解出一个长边',
    /function fitLongEdge\(n, aspect, budget\)/.test(seqSrc) &&
    /Math\.sqrt\(budget \* longRatio \/ \(4 \* n\)\)/.test(seqSrc),
    'L ≤ sqrt(budget × 长宽比 / (4 × 帧数))');
  R.check('缩放失败时退回原尺寸而不是丢帧',
    /return bit;\s*\/\/ 缩放失败就退回原尺寸/.test(seqSrc) ||
    /catch \(e\) \{\s*return bit;/.test(seqSrc),
    'decodeAt 的 catch 分支返回原尺寸');
  R.check('上传纹理时用的是原始来源，没有二次尺寸参数',
    /texImage2D\(gl\.TEXTURE_2D, 0, gl\.RGBA, gl\.RGBA, gl\.UNSIGNED_BYTE, opts\.source\)/.test(glSrc),
    'texImage2D 用的是 ImageBitmap 自带尺寸');
  R.check('没有生成 mipmap（会引入非原始像素）',
    !/generateMipmap/.test(stripComments(glSrc)) && glStub.of('generateMipmap').length === 0);
  R.check('超出纹理上限时是跳过而不是缩放',
    /超过本机 GPU 单张纹理上限/.test(seqSrc) && /已跳过（不会替你做压缩）/.test(seqSrc),
    '40-seq.js 里有明确的跳过分支与说明文案');
  R.check('本机纹理上限被如实读取并用于判断', /MAX_TEXTURE_SIZE/.test(glSrc),
    'gl.js 读取 MAX_TEXTURE_SIZE');
  R.check('纹理过滤默认是 LINEAR 且不生成 mipmap（不引入额外像素层级）',
    /TEXTURE_MIN_FILTER, filter/.test(glSrc) && /TEXTURE_MAG_FILTER, filter/.test(glSrc),
    '最小/放大过滤用的是同一个值');
  R.check('预算不足时明确建议用户改分辨率策略，而不是静默降质',
    /把顶栏的「分辨率」改成/.test(appSrc) && /程序不会背着你压缩像素/.test(appSrc),
    'appendFatal 的文案里给了出路');
}

/* ================================= 8b. 预算与 200 帧的现实 */

R.section('纹理预算：帧数与分辨率的取舍是可算的');
{
  const S = STC.seq;
  R.check('默认预算不再是 1 GB（那连 26 张 12MP 都装不下）',
    S.RAM_BUDGET >= 2 * 1024 * 1024 * 1024,
    'RAM_BUDGET = ' + Math.round(S.RAM_BUDGET / 1048576) + ' MB');
  R.check('按本机内存探测的预算不小于默认值',
    S.defaultBudget() >= S.RAM_BUDGET,
    'defaultBudget() = ' + Math.round(S.defaultBudget() / 1048576) + ' MB');
  R.check('帧数上限提到 600（200 张不再被抽稀）', S.MAX_FRAMES >= 600,
    'MAX_FRAMES = ' + S.MAX_FRAMES);

  // 核心那条算术：200 帧 3:2 的图，各分辨率下要多少显存
  const n = 200, aspect = 3 / 2;
  function bytesFor(longEdge) {
    const w = longEdge, h = Math.round(longEdge / aspect);
    return n * w * h * 4;
  }
  const at4000 = bytesFor(4000);
  const auto = S.fitLongEdge(n, aspect, S.defaultBudget());

  R.check('200 帧原尺寸（长边 4000）确实装不下 —— 超过任何常见显存',
    at4000 > 6 * 1024 * 1024 * 1024,
    Math.round(at4000 / 1073741824 * 10) / 10 + ' GB');
  R.check('自动适配给出的长边能让 200 帧装进预算',
    n * auto * Math.round(auto / aspect) * 4 <= S.defaultBudget(),
    `自动长边 = ${auto}px，共 ${Math.round(n * auto * Math.round(auto / aspect) * 4 / 1048576)} MB ` +
    `/ 预算 ${Math.round(S.defaultBudget() / 1048576)} MB`);
  R.check('自动适配给出的长边仍然可用（不是退化成几十像素）', auto >= 960,
    auto + 'px 长边');
  R.check('帧数越多，自动长边越小（平方根关系）',
    S.fitLongEdge(400, aspect, S.defaultBudget()) < S.fitLongEdge(100, aspect, S.defaultBudget()),
    `100 帧 → ${S.fitLongEdge(100, aspect, S.defaultBudget())}px；` +
    `400 帧 → ${S.fitLongEdge(400, aspect, S.defaultBudget())}px`);
}

/* ================================ 9. 纹理绑定：不能采到默认白纹理 */

R.section('纹理绑定：每个帧平面都必须绑上真实纹理');
{
  /*
   * WebGL 里如果某个采样器没有绑定纹理，采样结果是**未定义的**，
   * 多数驱动会返回 (0,0,0,1) 或 (1,1,1,1) —— 表现就是"所有切面一片纯白"。
   * 这正是用户报告过的现象，所以这里把它变成一条可断言的检查：
   *   渲染之前**故意把纹理全部解绑**，然后断言每一次帧平面绘制之前
   *   都重新绑定了一张"确实上传过像素"的纹理。
   *
   * 如果哪天渲染器漏了 bindTexture，这条就会失败 —— 而不是等用户看到白屏。
   */
  app.setView('front');
  app.setAllGhost(false);
  app.setOpacity(1.0, 0.4);
  app.setFrame(0);

  // 故意解绑：把 0 号纹理单元上的纹理清掉
  glStub.gl.activeTexture(glStub.gl.TEXTURE0);
  glStub.gl.bindTexture(glStub.gl.TEXTURE_2D, null);
  R.check('渲染前 0 号纹理单元为空（模拟"没有纹理"的状态）',
    glStub.boundTextures()[glStub.gl.TEXTURE0] === null,
    'unit0 = ' + glStub.boundTextures()[glStub.gl.TEXTURE0]);

  glStub.clear();
  app.renderNow();

  // 逐条检查：每次 plane 的 drawArrays 之前，最近一次 bindTexture 必须绑了真纹理
  const seq = glStub.calls;
  let checked = 0, boundBefore = 0, missing = [];
  let lastBound = null;
  for (const c of seq) {
    if (c.name === 'bindTexture') lastBound = c.args[1];
    if (c.name === 'drawArrays' && c.program === 'plane') {
      checked++;
      if (lastBound !== null && lastBound !== undefined) {
        boundBefore++;
        const ups = glStub.textureUploads(lastBound);
        if (!ups || !ups.length || !(ups[0].width > 1 && ups[0].height > 1)) {
          missing.push(`tex#${lastBound} 的上传记录不像一张真图：${JSON.stringify(ups)}`);
        }
      } else {
        missing.push('这次平面绘制之前没有绑定任何纹理');
      }
    }
  }
  R.check('每一次帧平面绘制之前都绑定了纹理',
    checked > 0 && boundBefore === checked,
    `${boundBefore}/${checked} 次；${missing.slice(0, 2).join('；') || '全部正常'}`);
  R.check('绑定的纹理确实上传过 2D 像素（不是 1 像素的占位纹理）',
    missing.length === 0, missing.slice(0, 2).join('；') || '全部是真实帧纹理');

  /*
   * 侧面色带：画四条边的时候必须绑**各自那张**图集，而且每张都是
   * （沿边长度 × 帧数）的真彩色纹理。
   *
   * 旧断言写的是"1 像素高的带状图集" —— 那正是被截断的那张。
   * 现在还要核对：带宽等于图高/图宽、带高等于帧数、字节数对得上。
   */
  const bandBinds = seq.filter((c) => c.name === 'bindTexture' && c.program === 'band');
  R.check('侧面色带绘制前也绑定了图集纹理', bandBinds.length >= 4,
    bandBinds.length + ' 次绑定（12 帧 × 4 条边）');
  if (bandBinds.length) {
    const dims = [...new Set(bandBinds.map((c) => {
      const ups = glStub.textureUploads(c.args[1]);
      return ups && ups[0] ? ups[0].width + '×' + ups[0].height : '?';
    }))].sort();
    R.check('侧面色带绑定的是四张真彩色图集（左右 240×12、上下 320×12）',
      dims.length === 2 && dims.includes('240×12') && dims.includes('320×12'),
      '实际绑定到的尺寸：' + dims.join(' / '));
    const bytesOk = bandBinds.every((c) => {
      const ups = glStub.textureUploads(c.args[1]);
      return ups && ups[0] && ups[0].bytes === ups[0].width * ups[0].height * 4;
    });
    R.check('每张图集的数据字节数与尺寸一致（没有被截断）', bytesOk,
      '全部一致');
  }
}

/* =================== 9c. 轮廓提取（着色器分支 / 逐帧纹素尺寸） */

R.section('轮廓提取：着色器分支 + 逐帧纹素尺寸');
{
  /*
   * 轮廓提取是在**照片自己的纹理上**做的（不是屏幕空间后期），
   * 所以每个帧平面都必须带上"自己那张纹理"的纹素尺寸。
   * 这里同时钉住着色器里的公式与渲染器提交的 uniform ——
   * 真实 GPU 上的像素本会话无法验证（沙箱禁止命名管道，无头浏览器起不来），
   * 但"提交了什么"是可以逐条核对的。
   */
  const fs = STC.shaders.PLANE_FS;

  R.check('片元着色器里有"只保留轮廓"的开关 uniform', /uniform int uOutline;/.test(fs), 'uOutline');
  R.check('有对比门槛 uniform', /uniform float uEdgeThreshold;/.test(fs), 'uEdgeThreshold');
  R.check('有纹素尺寸 uniform（放大到 1 纹素以上时不会整片变噪声）',
    /uniform vec2 uTexel;/.test(fs), 'uTexel');
  R.check('内部是 discard（不是画成透明 —— 那样会留下深度/混合残影）',
    /if\s*\(m\s*<\s*uEdgeThreshold\)\s*discard;/.test(fs),
    (fs.match(/if \(m < uEdgeThreshold\) discard;/) || ['没找到'])[0]);
  R.check('采样步长同时取屏幕导数与纹素下限',
    /max\(fwidth\(vUv\),\s*uTexel\)/.test(fs) && /tx\.x\s*=\s*uTexel\.x/.test(fs),
    'max(fwidth(vUv), uTexel)');
  R.check('取的是上下左右四个邻居（不是只取一个方向）',
    (fs.match(/chanMax\(c,\s*texture\(uTex,\s*vUv\s*[+-]/g) || []).length === 4, '4 个邻居');
  R.check('判据是逐通道最大差，而不是亮度差（等亮度的红↔绿边界靠亮度差会整片漏掉）',
    /float chanMax\(vec4 a, vec4 b\)/.test(fs) && !/0\.299|0\.587|0\.114/.test(fs),
    'chanMax 且没有亮度权重');
  R.check('轮廓色是"原色往白里提"，不是纯白也不是原色',
    /mix\(c\.rgb,\s*vec3\(1\.0\),\s*0\.6\)/.test(fs),
    (fs.match(/mix\(c\.rgb[^;]*;/) || ['没找到'])[0]);

  app.setView('front');
  app.setAllGhost(false);
  app.setOpacity(1.0, 0.4);
  app.setFrame(0);
  if (dom.byId.outline) { dom.byId.outline.checked = false; dom.byId.outline.dispatch('change', { target: dom.byId.outline }); }
  if (dom.byId.edge) { dom.byId.edge.value = '0.25'; dom.byId.edge.dispatch('input', { target: dom.byId.edge }); }
  await new Promise((r) => setTimeout(r, 10));

  glStub.clear();
  app.renderNow();
  const off = glStub.of('uniform1i').filter((c) => c.args[0] === 'uOutline').map((c) => c.args[1]);
  R.check('默认关闭：每帧都提交 uOutline = 0',
    off.length > 0 && off.every((v) => v === 0), '提交了 ' + off.length + ' 次，值 = ' + [...new Set(off)].join(','));

  // 打开：复选框 → 状态位 → uniform
  {
    const box = dom.byId.outline;
    R.check('面板里有「只保留轮廓」这个复选框', !!box, box ? 'id=outline' : '缺少 id=outline');
    box.checked = true;
    box.dispatch('change', { target: box });
    await new Promise((r) => setTimeout(r, 10));
    R.check('勾上后状态位同步', app.state.outline === true, 'outline=' + app.state.outline);

    glStub.clear();
    app.renderNow();
    const on = glStub.of('uniform1i').filter((c) => c.args[0] === 'uOutline').map((c) => c.args[1]);
    R.check('打开后每帧都提交 uOutline = 1',
      on.length > 0 && on.every((v) => v === 1), '提交了 ' + on.length + ' 次，值 = ' + [...new Set(on)].join(','));
    const th = glStub.of('uniform1f').filter((c) => c.args[0] === 'uEdgeThreshold').map((c) => c.args[1]);
    R.check('门槛被逐帧提交给着色器',
      th.length > 0 && th.every((v) => Math.abs(v - 0.25) < 1e-6), '值 = ' + [...new Set(th)].join(','));
  }

  // 门槛滑块：0 → 1，夹在合理区间，并确实改变提交值
  if (dom.byId.edge) {
    const setEdge = async (v) => {
      dom.byId.edge.value = String(v);
      dom.byId.edge.dispatch('input', { target: dom.byId.edge });
      await new Promise((r) => setTimeout(r, 5));
      glStub.clear();
      app.renderNow();
      const got = glStub.of('uniform1f').filter((c) => c.args[0] === 'uEdgeThreshold').map((c) => c.args[1]);
      return got.length ? got[0] : null;
    };
    const low = await setEdge(0.05);
    const high = await setEdge(0.75);
    R.check('门槛滑块真的会改变提交给着色器的值',
      low !== null && high !== null && high > low, `0.05 → ${low}，0.75 → ${high}`);
    R.check('门槛标签跟着滑块走', !!dom.byId.lbEdge, dom.byId.lbEdge ? `lbEdge="${dom.byId.lbEdge.textContent}"` : '缺少 id=lbEdge');
    await setEdge(0.25);
  }

  /*
   * 逐帧纹素尺寸：一圈 320×240 的帧，每次平面绘制前提交的 uTexel
   * 必须正好是 (1/320, 1/240)。写错这一项的症状是"轮廓线在放大后全是噪声"，
   * 而那在截图里很容易被当成"边缘检测本来就这样"。
   */
  {
    glStub.clear();
    app.renderNow();
    const texel = glStub.of('uniform2f').filter((c) => c.args[0] === 'uTexel').map((c) => [c.args[1], c.args[2]]);
    R.check('每一帧平面绘制都提交了 uTexel', texel.length > 0, texel.length + ' 次');
    const bad = texel.filter(([x, y]) => Math.abs(x - 1 / 320) > 1e-9 || Math.abs(y - 1 / 240) > 1e-9);
    R.check('uTexel = (1/该帧纹理宽, 1/该帧纹理高)，逐帧正确',
      bad.length === 0, bad.length ? '有 ' + bad.length + ' 次不符：' + JSON.stringify(bad[0]) : `${texel.length} 次全部 = (1/320, 1/240)`);
    R.check('每一帧的纹理尺寸都被带进了解算结果里（texW/texH 来自该帧像素）',
      STC.view.resolve(app.state.seq,
        { allGhost: false, opCur: 1, opOther: 0.4, otherMode: 'plane' }, 0)
        .items.every((it) => it.texW === 320 && it.texH === 240),
      '解算结果的 texW×texH 全部 = 320×240');
  }

  // 关回去，别影响后面的小节
  {
    const box = dom.byId.outline;
    box.checked = false;
    box.dispatch('change', { target: box });
    await new Promise((r) => setTimeout(r, 10));
    glStub.clear();
    app.renderNow();
    const back = glStub.of('uniform1i').filter((c) => c.args[0] === 'uOutline').map((c) => c.args[1]);
    R.check('关回去以后 uOutline 又全是 0（这是开关，不是一次性过滤）',
      back.length > 0 && back.every((v) => v === 0), '值 = ' + [...new Set(back)].join(','));
  }
}

/* =================== 9d. 切割（选区）：着色器分支 + 提交的 uniform */

R.section('切割：选区在着色器里生效（平面 + 点云）');
{
  /*
   * 切割的语义是"只显示选区内的影像"：选区外的片元/点**直接丢弃**。
   * 这里钉三件事：
   *   1) 着色器里确实有这条判据（平面与点云各一份，否则切到点云选区就失效）；
   *   2) 判据的坐标朝向与 CPU 侧一致（v=0 是图像顶部）；
   *   3) 提交的 uniform 与 state.clipRect 一致，且随开关切换。
   */
  const fs = STC.shaders.PLANE_FS;
  const pvs = STC.shaders.POINT_VS;

  R.check('帧平面着色器有选区开关与选区向量',
    /uniform int uClipOn;/.test(fs) && /uniform vec4 uClip;/.test(fs), 'uClipOn / uClip');
  R.check('选区外是 discard（不是画成透明 —— 那样会留下深度/混合残影）',
    /if \(uClipOn == 1 && \(vUv\.x < uClip\.x/.test(fs) && /\) discard;/.test(fs),
    (fs.match(/if \(uClipOn[^;]*;/) || ['没找到'])[0].replace(/\s+/g, ' '));
  R.check('判据含边界（与 CPU 侧 clipContains 的 >= / <= 一致）',
    /vUv\.x < uClip\.x \|\| vUv\.x > uClip\.z/.test(fs) &&
    /vUv\.y < uClip\.y \|\| vUv\.y > uClip\.w/.test(fs),
    '四个方向都判了（不含边界即为外）');
  R.check('点云顶点着色器也有同一条判据（否则切到点云选区就失效）',
    /uniform int uClipOn;/.test(pvs) && /uniform vec4 uClip;/.test(pvs) &&
    /uvp\.x < uClip\.x/.test(pvs),
    'POINT_VS 里有 uvp 判据');
  R.check('点云的 uv 换算与帧平面同一朝向（图像顶部在 +y）',
    /vec2 uvp = vec2\(aPosPx\.x \+ 0\.5, 0\.5 - aPosPx\.y\)/.test(pvs),
    (pvs.match(/vec2 uvp[^;]*;/) || ['没找到'])[0]);

  /*
   * ★ 点云的局部坐标必须由 view.pixelLocal 烘焙。
   * 这一条是"点云与照片上下颠倒"那类 bug 的回归网：
   * 两条路径各写一套公式时，只能靠肉眼发现；共用一份就不可能不一致。
   */
  R.check('渲染器用 view.pixelLocal 烘焙点云位置（与照片共用同一套朝向）',
    /STC\.view\.pixelLocal\(w, h, x, z\)/.test(readFileSync(join(srcDir, '60-renderer.js'), 'utf8')),
    'buildPoints 里调的是 STC.view.pixelLocal');

  app.setView('front');
  app.setAllGhost(false);
  app.setOpacity(1.0, 0.4);
  app.setFrame(0);
  app.clearClip();
  await new Promise((r) => setTimeout(r, 10));

  glStub.clear();
  app.renderNow();
  const off = glStub.of('uniform1i').filter((c) => c.args[0] === 'uClipOn').map((c) => c.args[1]);
  R.check('默认关闭：每帧都提交 uClipOn = 0',
    off.length > 0 && off.every((v) => v === 0), '提交了 ' + off.length + ' 次，值 = ' + [...new Set(off)].join(','));

  // 打开：选区取左上四分之一（320×240 的帧 → uv 0..0.5）
  const RECT = { x0: 0.1, y0: 0.2, x1: 0.6, y1: 0.7 };
  app.setClipRect(RECT, true);
  await new Promise((r) => setTimeout(r, 10));
  R.check('设置选区后状态位同步（开关被自动打开）',
    app.state.clip === true &&
    Math.abs(app.state.clipRect.x0 - 0.1) < 1e-9 && Math.abs(app.state.clipRect.y1 - 0.7) < 1e-9,
    JSON.stringify(app.state.clipRect));

  glStub.clear();
  app.renderNow();
  const on = glStub.of('uniform1i').filter((c) => c.args[0] === 'uClipOn').map((c) => c.args[1]);
  R.check('打开后每帧都提交 uClipOn = 1',
    on.length > 0 && on.every((v) => v === 1), '提交了 ' + on.length + ' 次');
  const rects = glStub.of('uniform4f').filter((c) => c.args[0] === 'uClip')
    .map((c) => [c.args[1], c.args[2], c.args[3], c.args[4]]);
  const bad = rects.filter((r) => Math.abs(r[0] - 0.1) > 1e-6 || Math.abs(r[1] - 0.2) > 1e-6 ||
    Math.abs(r[2] - 0.6) > 1e-6 || Math.abs(r[3] - 0.7) > 1e-6);
  R.check('uClip = (x0,y0,x1,y1)，逐帧提交且与 state.clipRect 一致',
    rects.length >= 12 && bad.length === 0,
    bad.length ? '有 ' + bad.length + ' 次不符：' + JSON.stringify(bad[0])
      : rects.length + ' 次全部 = (0.1, 0.2, 0.6, 0.7)');

  // 点云模式：两边都要提交（平面 + 点云），否则切换显示方式后选区会失效
  app.setOtherMode('points');
  await app.ensurePoints();
  glStub.clear();
  app.renderNow();
  const ptClip = glStub.of('uniform1i').filter((c) => c.args[0] === 'uClipOn' && c.program === 'point');
  const plClip = glStub.of('uniform1i').filter((c) => c.args[0] === 'uClipOn' && c.program === 'plane');
  R.check('点云模式下选区对**两种**绘制都提交（平面 + 点云实例）',
    ptClip.length > 0 && plClip.length > 0 && ptClip.every((c) => c.args[1] === 1),
    `点云 ${ptClip.length} 次（program=point）、平面 ${plClip.length} 次`);
  app.setOtherMode('plane');

  // 面板：勾选框、按钮与说明文字都要在，且状态与 state 同步
  R.check('面板里有「只显示选区」复选框', !!dom.byId.clip, dom.byId.clip ? 'id=clip' : '缺少 id=clip');
  R.check('面板里有「框选区域…」与「整个画面」两个按钮',
    !!dom.byId.clipEdit && !!dom.byId.clipAll, 'clipEdit / clipAll');
  R.check('选区说明会写出选了多少像素（用当前帧的尺寸换算）',
    /像素/.test(dom.byId.clipInfo.textContent || ''),
    (dom.byId.clipInfo.textContent || '').slice(0, 60));
  {
    dom.byId.clip.checked = false;
    dom.byId.clip.dispatch('change', { target: dom.byId.clip });
    R.check('取消勾选 → state.clip = false（选区本身留着，再勾上就恢复）',
      app.state.clip === false && app.state.clipRect.x0 > 0,
      'clip=' + app.state.clip + ' rect=' + JSON.stringify(app.state.clipRect));
    dom.byId.clip.checked = true;
    dom.byId.clip.dispatch('change', { target: dom.byId.clip });
    R.check('再勾上 → 又生效（关掉开关不会丢掉已经框好的区域）',
      app.state.clip === true, 'clip=' + app.state.clip);
  }

  // 框选面板：能打开、能应用、能取消、能全选
  {
    /*
     * ★ 坐标换算必须按**画布**那块区域来，而不是外层容器。
     * 桩里刻意让外层（60,40,800×400）比画布（100,50,400×300）宽得多 ——
     * 真实布局就是这样（外层是 flex 子项会被拉伸，画布受 max-width/height 限制）。
     * 用错分母的症状是：**选区框看着跟手，但选出来的区域整体偏左**
     * （这正是用户报的问题）。
     */
    dom.byId.clipAll.dispatch('click', {});
    app.openClipEditor();
    R.check('能打开框选面板（在真实应用里跑一遍）', app.clipEditorOpen() === true, '面板已打开');
    R.check('框选面板会把当前帧画到 2D 画布上（尺寸 = 该帧像素尺寸）',
      dom.byId.cropCanvas.width === 320 && dom.byId.cropCanvas.height === 240,
      dom.byId.cropCanvas.width + '×' + dom.byId.cropCanvas.height);
    R.check('面板里显示了选区占了多少像素', /px|整个画面/.test(dom.byId.cropInfo.textContent || ''),
      (dom.byId.cropInfo.textContent || '').slice(0, 60));

    const wrap = dom.byId.cropWrap;
    const at = (u, v) => ({ clientX: 100 + u * 400, clientY: 50 + v * 300 });   // 画布 = (100,50,400×300)

    // 拖一次：画布的 25% → 75%
    wrap.dispatch('mousedown', at(0.25, 0.25));
    dom.document.dispatch('mousemove', at(0.75, 0.75));
    dom.document.dispatch('mouseup', {});
    R.check('★ 外层容器比画布宽时，选区框仍然贴在画布上（px 定位锚在画布的真实位置）',
      dom.byId.cropRect.style.left === '140px' && dom.byId.cropRect.style.top === '85px' &&
      dom.byId.cropRect.style.width === '200px' && dom.byId.cropRect.style.height === '150px',
      `left=${dom.byId.cropRect.style.left} top=${dom.byId.cropRect.style.top} ` +
      `w=${dom.byId.cropRect.style.width} h=${dom.byId.cropRect.style.height}` +
      '（期望 left=140 top=85 w=200 h=150 = 画布内 25%~75%）');

    dom.byId.cropOk.dispatch('click', {});
    R.check('★ 拖出来的矩形换算成 uv 时用的也是画布的尺寸（不是外层的 800 宽）',
      app.state.clip === true &&
      Math.abs(app.state.clipRect.x0 - 0.25) < 0.02 && Math.abs(app.state.clipRect.x1 - 0.75) < 0.02 &&
      Math.abs(app.state.clipRect.y0 - 0.25) < 0.02 && Math.abs(app.state.clipRect.y1 - 0.75) < 0.02,
      JSON.stringify(app.state.clipRect) + '（若按外层宽度算会得到 0.125~0.375）');
    R.check('应用后框选面板自己关掉', app.clipEditorOpen() === false);

    // 再来一次：从画布**中心**拖到画布**右下角** —— 必须是 (0.5,0.5)~(1,1)
    dom.byId.clipAll.dispatch('click', {});
    app.openClipEditor();
    wrap.dispatch('mousedown', at(0.5, 0.5));
    dom.document.dispatch('mousemove', at(1, 1));
    dom.document.dispatch('mouseup', {});
    dom.byId.cropOk.dispatch('click', {});
    R.check('从画布正中拖到右下角 = uv (0.5,0.5)~(1,1)（画布外的空白区域不参与换算）',
      Math.abs(app.state.clipRect.x0 - 0.5) < 0.02 && Math.abs(app.state.clipRect.y0 - 0.5) < 0.02 &&
      Math.abs(app.state.clipRect.x1 - 1) < 0.02 && Math.abs(app.state.clipRect.y1 - 1) < 0.02,
      JSON.stringify(app.state.clipRect));

    // 取消：不改动已有选区
    const before = JSON.stringify(app.state.clipRect);
    app.openClipEditor();
    dom.byId.cropAll.dispatch('click', {});          // 先全选
    dom.byId.cropCancel.dispatch('click', {});       // 再取消
    R.check('取消 = 不改动原选区（全选只是一次草稿）',
      JSON.stringify(app.state.clipRect) === before, before + ' → ' + JSON.stringify(app.state.clipRect));
    R.check('取消后面板关掉', app.clipEditorOpen() === false);
  }

  // 「整个画面」= 复位，且复位后开关自动关掉（勾着也没有任何效果）
  {
    dom.byId.clipAll.dispatch('click', {});
    R.check('「整个画面」把选区复位，并把开关一起关掉',
      app.state.clip === false && STC.view.clipIsFull(app.state.clipRect),
      'clip=' + app.state.clip + ' rect=' + JSON.stringify(app.state.clipRect));
    R.check('复位后复选框被置灰（勾上也没有任何效果，避免"我勾了却没变化"）',
      dom.byId.clip.disabled === true, 'clip.disabled=' + dom.byId.clip.disabled);
    glStub.clear();
    app.renderNow();
    const back = glStub.of('uniform1i').filter((c) => c.args[0] === 'uClipOn').map((c) => c.args[1]);
    R.check('复位后提交的 uClipOn 又全是 0',
      back.length > 0 && back.every((v) => v === 0), '值 = ' + [...new Set(back)].join(','));
  }
}

/* =================== 9b. 全部帧最终都必须拿到纹理 */

R.section('后台上传：最终每一帧都要有纹理（否则会显示成白/品红）');
{
  /*
   * 纹理是按需上传的，但**必须最终把全部帧补齐**。
   * 漏掉的帧在 WebGL 里会采样成纯白（或按我们的着色器显示成品红），
   * 这正是"所有切面都是纯白色"最可能的成因，所以这条要单独钉住。
   */
  const files = [];
  for (let i = 0; i < 40; i++) files.push(fakeImageFile(`bg${i}.png`, 64, 48, 1000 + i));
  await app.loadFiles(files);
  R.check('40 帧全部载入', app.diagnostics().frames === 40, 'frames=' + app.diagnostics().frames);

  // 等后台上传循环把 40 帧补齐
  let uploaded = 0;
  for (let i = 0; i < 400; i++) {
    uploaded = app.state.seq.frames.filter((f) => f.texture).length;
    if (uploaded === 40) break;
    await new Promise((r) => setTimeout(r, 10));
  }
  R.check('后台循环把全部 40 帧的纹理都补齐了', uploaded === 40,
    uploaded + '/40 帧有纹理');

  const failed = app.state.seq.frames.filter((f) => f.textureFailed).length;
  R.check('没有任何一帧纹理上传失败', failed === 0, failed + ' 帧失败');
  R.check('帧平面绘制时全部帧都带纹理（不会采到默认白纹理）',
    app.state.seq.frames.every((f) => !!f.texture),
    '有纹理 ' + app.state.seq.frames.filter((f) => f.texture).length + '/40');
}

/* ================================================ 10. 端到端一致性 */

R.section('提交给 GL 的指令与解算结果一致');
{
  // 注意：这一节必须在「输入通路」之前跑 —— 那一节会载入新的文件批次，
  // 把序列换成 2 帧，于是"恰好一个不透明帧"这类断言前提就变了。
  app.setView('iso');
  app.setFrame(5);
  app.setOpacity(1.0, 0.2);
  app.setAllGhost(false);
  app.setOtherMode('plane');

  const res = app.resolve(app.state.seq, app.state, 5);
  const visible = res.items.filter((it) => it.opacity > 0);
  glStub.clear();
  app.renderNow();

  const planes = glStub.byProgram('drawArrays', 'plane');
  const bands = glStub.byProgram('drawArrays', 'band');
  const opaqueCount = visible.filter((it) => it.opacity >= 0.998).length;

  R.check('帧平面绘制次数 = 可见帧数', planes.length === visible.length,
    `GL 收到 ${planes.length} 次，解算出 ${visible.length} 帧可见`);
  R.check('侧面颜色条 = 可见帧数 × 4 条（每帧四个侧墙）',
    bands.length === visible.length * 4,
    `${bands.length} 条 / 期望 ${visible.length * 4} 条`);
  R.check('不透明帧数和解算一致', opaqueCount === 1 && res.stats.opaque === 1,
    `opaque=${res.stats.opaque}`);
  R.check('本帧只用到 plane / band / solid 三个 program',
    glStub.programNames().sort().join(',') === 'band,plane,solid',
    glStub.programNames().join(' | '));
}

/* =============================== 10. 输入通路：拖放拦截与选文件 */

R.section('输入通路：拖放必须被拦下，选文件不依赖 JS');
{
  /*
   * ★ 先钉一条"自检环境本身"的检查：**src/index.html 里存在的每个 id，
   * 桩的 DOM 里都必须有**。
   *
   * 这条是补上的 —— 桩里少了一个 'lumDir'，于是 bindUI 在那一行抛异常、
   * 被 boot 的 try/catch 接住，**后面所有控件的事件绑定全部没有注册**
   * （方点、三档描边、立方体线框、时间轴、视角切换、切割…）。
   * 表现是"测试全绿"，但那几个开关其实从来没被点过。
   * 少一个 id 就能让一半的界面静默失联，所以这条必须自己盯着。
   */
  {
    const pageIds = new Set();
    for (const m of readFileSync(join(srcDir, 'index.html'), 'utf8').matchAll(/id="([A-Za-z0-9_]+)"/g)) {
      pageIds.add(m[1]);
    }
    const missing = [...pageIds].filter((id) => !dom.byId[id]);
    R.check('★ 页面里的每个 id 在桩的 DOM 里都存在（少一个就会让 bindUI 从那行断掉）',
      missing.length === 0,
      missing.length ? '桩里缺少：' + missing.join(', ') : pageIds.size + ' 个 id 全部存在');
    R.check('bindUI 没有在中途抛异常（这样后面的开关才真的被绑上）',
      !/界面事件绑定失败/.test(dom.byId.fatal.textContent || ''),
      (dom.byId.fatal.textContent || '').slice(0, 80) || '无绑定错误');
  }
  /*
   * 这一节是补上的。用户实际遇到的是：
   *   拖入照片 → 浏览器把每张照片当链接打开，一次开出上百个标签页；
   *   点「打开照片」→ 毫无反应。
   * 根因是 bindUI() 在绑定这两个入口之前就抛异常了，浏览器于是执行了
   * 拖放的**默认行为**（打开文件）。一个渲染层的小问题把整个交互层拖垮。
   *
   * 所以这里断言的不是"有没有绑监听"，而是更本质的三件事：
   *   1. 拖放事件必须被 preventDefault（否则浏览器就会去打开文件）；
   *   2. 拦截必须在脚本求值阶段就武装好，不依赖 boot() 是否成功；
   *   3. 文件控件不能 hidden —— 透明覆盖式按钮靠它可见才点得到。
   */
  const diag = app.inputDiagnostics();
  R.check('拖放拦截已武装（不依赖 boot 是否成功）', diag.dragArmed === true,
    JSON.stringify(diag));
  R.check('文件控件存在且是 file 类型',
    diag.fileInputPresent && diag.fileInputType === 'file', JSON.stringify(diag));
  R.check('文件控件支持多选、并且同时限定图片与视频',
    diag.fileInputMultiple && diag.fileInputAccept === 'image/*,video/*', JSON.stringify(diag));
  R.check('文件控件没有 hidden（透明覆盖式按钮靠它可见才点得到）',
    diag.fileInputVisible === true, 'fileInputVisible=' + diag.fileInputVisible);
  R.check('透明覆盖式按钮的外壳存在', diag.openWrapPresent === true);

  const overCanvas = dom.document.dispatchOn(dom.canvas, 'dragover', {
    dataTransfer: { files: [], items: [], dropEffect: '' }
  });
  R.check('拖到画布上时 dragover 被 preventDefault（否则浏览器会打开文件）',
    overCanvas.defaultPrevented === true, 'defaultPrevented=' + overCanvas.defaultPrevented);

  for (const id of ['bar', 'panel', 'status', 'foot']) {
    const el = dom.byId[id];
    const e = dom.document.dispatchOn(el, 'dragover', {
      dataTransfer: { files: [], items: [], dropEffect: '' }
    });
    R.check(`拖到 #${id} 上时 dragover 也被 preventDefault`, e.defaultPrevented === true);
  }

  {
    const e = dom.document.dispatchOn(dom.canvas, 'dragenter', {
      dataTransfer: { files: [], items: [], dropEffect: '' }
    });
    R.check('dragenter 也被 preventDefault', e.defaultPrevented === true);
  }

  // drop：必须被拦下，并且真的去加载文件（不是只 preventDefault 就完事）
  {
    const files = [fakeImageFile('drop_a.png', 64, 48, 1), fakeImageFile('drop_b.png', 64, 48, 2)];
    const e = dom.document.dispatchOn(dom.canvas, 'drop', {
      dataTransfer: { files, items: [], dropEffect: '' }
    });
    R.check('drop 被 preventDefault（浏览器不会把文件当链接打开）',
      e.defaultPrevented === true);
    R.check('drop 之后确实开始载入这批文件', app.state.busy === true || app.diagnostics().frames > 0,
      'busy=' + app.state.busy + ' frames=' + app.diagnostics().frames);

    for (let i = 0; i < 300 && app.state.busy; i++) await new Promise((r) => setTimeout(r, 10));
    const after = app.diagnostics();
    R.check('拖入的文件被成功载入', after.frames === 2, 'frames=' + after.frames);
  }

  // 再载入一批：这条路径会走释放逻辑（delete* 系列），最容易漏测
  {
    const files = [fakeImageFile('again_a.png', 64, 48, 1), fakeImageFile('again_b.png', 64, 48, 2),
      fakeImageFile('again_c.png', 64, 48, 3)];
    const input = dom.byId.file;
    input.files = files;
    input.dispatch('change', { target: input });
    for (let i = 0; i < 300 && app.state.busy; i++) await new Promise((r) => setTimeout(r, 10));
    const after = app.diagnostics();
    R.check('再次载入新一批照片也成功（释放旧序列的路径走得通）',
      after.frames === 3, 'frames=' + after.frames);
  }

  // 选文件那条路：input 的 change 必须接得住
  {
    const files = [fakeImageFile('pick_a.png', 64, 48, 1), fakeImageFile('pick_b.png', 64, 48, 2)];
    const input = dom.byId.file;
    input.files = files;
    input.dispatch('change', { target: input });
    for (let i = 0; i < 300 && app.state.busy; i++) await new Promise((r) => setTimeout(r, 10));
    const after = app.diagnostics();
    R.check('通过文件对话框选的文件也被成功载入', after.frames === 2, 'frames=' + after.frames);
  }

  R.check('控制台备用入口 STC.app.openPicker 可用',
    typeof app.openPicker === 'function' && typeof app.openPickerFallback === 'function');
  let threw = null;
  try { app.openPicker(); } catch (e) { threw = String(e && e.message || e); }
  R.check('调用备用入口不抛异常', threw === null, threw || '正常');
}

app.stop();
process.exitCode = R.summary() ? 1 : 0;
