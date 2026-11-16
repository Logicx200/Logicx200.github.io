/* 成品自检：检验 build 出来的那个单文件 index.html 本身
 *
 * 前面的两个测试跑的是 src/ 里的模块；这个脚本跑的是**用户真正会打开的那个文件**，
 * 因为打包过程本身也可能出错（占位符没替换、脚本没内联、意外引入了外部请求）。
 *
 * 用法：node test/html.test.mjs
 */
import { readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createGlStub, createDom, loadApp, createReporter } from '../tools/harness.mjs';
import { fakeImageFile } from '../tools/make-sample.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const R = createReporter('成品 HTML 自检', join(here, 'html.log'));

const htmlPath = join(root, 'index.html');
R.check('index.html 存在', existsSync(htmlPath), htmlPath);
const html = readFileSync(htmlPath, 'utf8');

/* ------------------------------------------------------ 结构完整性 */

R.section('打包结构');
R.check('两个占位符都已被替换',
  !html.includes('__ASSEMBLE_STYLES__') && !html.includes('__ASSEMBLE_SCRIPTS__'),
  '没有残留占位符');
R.check('样式已内联', /<style>[\s\S]*<\/style>/.test(html), '有内联 style');
R.check('脚本已内联', /<script>[\s\S]{1000,}<\/script>/.test(html), '有内联 script');
R.check('九个模块都被合并进来',
  ['10-math.js', '20-gl.js', '30-exif.js', '40-seq.js', '45-video.js', '50-shaders.js',
    '55-view.js', '60-renderer.js', '70-app.js'].every((m) => html.includes(m)),
  '注释里有 9 个模块名');

/* ------------------------------------------------ 零外部依赖 / 零网络 */

R.section('零外部依赖（离线可跑）');
{
  // 只看真正会产生网络请求的属性，不看注释与文案
  const external = [
    /<script[^>]+src=/i,
    /<link[^>]+rel=["']?stylesheet/i,
    /https?:\/\/[^\s"'<>)]+/g
  ];
  R.check('没有外部 script src', !external[0].test(html));
  R.check('没有外部样式表 link', !external[1].test(html));

  const urls = (html.match(external[2]) || [])
    .filter((u) => !/^https?:\/\/(www\.)?w3\.org/.test(u));   // 命名空间不是请求
  R.check('没有指向外部主机 URL（CDN / 字体 / 图片都没有）', urls.length === 0,
    urls.length ? urls.slice(0, 5).join(' , ') : '一个都没有');

  R.check('没有 import / importmap（不依赖模块加载器）',
    !/\bimportmap\b/.test(html) && !/^\s*import\s/m.test(html));
  R.check('没有 fetch 外部资源的调用',
    !/fetch\(\s*['"`]https?:/.test(html), '示例加载只走同源相对路径');
}

/* ------------------------------------------------ 真把它跑起来一遍 */

R.section('把成品 HTML 里的脚本真的执行一遍');
{
  // 从 <script> 里抽出内联代码，用同一个 DOM 桩环境执行
  const m = html.match(/<script>\n([\s\S]*?)\n<\/script>/);
  R.check('能从 HTML 里抽出内联脚本', !!m, m ? m[1].length + ' 字符' : '没找到');

  const glStub = createGlStub({ maxTextureSize: 8192 });
  const dom = createDom({ width: 800, height: 600, glStub });
  const { STC } = loadApp(dom, {}, m ? m[1] : undefined, 'index.html 内联脚本');

  R.check('执行后挂出了 STC 命名空间', !!STC, Object.keys(STC || {}).join(','));
  R.check('九个子模块都就位',
    ['math', 'gl', 'exif', 'seq', 'video', 'shaders', 'view', 'renderer', 'app']
      .every((k) => !!STC[k]),
    Object.keys(STC).join(','));
  R.check('对外接口 STC.app 存在', !!STC.app && typeof STC.app.loadFiles === 'function');

  // 用成品里的代码真的渲染一帧
  const files = [];
  for (let i = 0; i < 8; i++) files.push(fakeImageFile(`f${i}.png`, 160, 120, 1000 + i));
  await STC.app.loadFiles(files);
  const d = STC.app.diagnostics();
  R.check('成品代码可以载入并渲染序列', d.frames === 8, 'frames=' + d.frames);
  R.check('成品代码没有着色器错误', d.shaderErrors.length === 0, d.shaderErrors.join(' | ') || '无');

  glStub.clear();
  STC.app.renderNow();
  /*
   * 8 帧，默认设置（每帧描边默认关闭）：
   *   8 个帧平面 + 8 帧 × 4 条体积色带 + 1 个立方体线框（12 条棱）+ 1 条时间轴
   * 描边默认关闭是有意的 —— 200 帧时每帧一个白框会把画面叠成一片白。
   */
  const expectDraws = 8 + 8 * 4 + 1 + 1;
  R.check('成品代码真的发出了绘制调用',
    glStub.of('drawArrays').length === expectDraws,
    `${glStub.of('drawArrays').length} 次 drawArrays（期望 ${expectDraws}）`);
  R.check('成品代码用的是四个 program 中的三个（无点云）',
    glStub.programNames().sort().join(',') === 'band,plane,solid',
    glStub.programNames().join(' | '));

  // 立方体线框必须是 12 条棱（24 个顶点），不是每帧一个矩形
  const cageDraws = glStub.of('drawArrays').filter((c) => c.program === 'solid' && c.args[0] === glStub.gl.LINES);
  R.check('立方体线框用 GL_LINES 画 12 条棱（24 个顶点）',
    cageDraws.some((c) => c.args[2] === 24), JSON.stringify(cageDraws.map((c) => c.args)));

  STC.app.stop();
}

/* ------------------------------------------------ 关键文案与开关 */

R.section('界面元素齐全');
{
  const ids = ['view', 'bar', 'file', 'sort', 'res', 'videoStep', 'status', 'panel', 'frame', 'lbFrame',
    'allGhost', 'opCur', 'lbOpCur', 'opOther', 'lbOpOther', 'otherMode', 'dot', 'lbDot',
    'lumDir', 'lumW', 'lbLumW', 'lumT', 'lbLumT', 'thick', 'lbThick', 'spacing', 'lbSpacing',
    'square', 'edgeMode', 'showBands', 'bandDebug', 'showOutline', 'showCube', 'showAxis',
    'outline', 'edge', 'lbEdge',
    'clip', 'clipEdit', 'clipAll', 'clipInfo',
    'crop', 'cropWrap', 'cropCanvas', 'cropRect', 'cropInfo', 'cropOk', 'cropCancel', 'cropAll',
    'viewMode', 'shot', 'hud', 'veil', 'veilCancel', 'fatal', 'openWrap'];
  const missing = ids.filter((id) => !html.includes(`id="${id}"`));
  R.check('所有界面元素都在 HTML 里', missing.length === 0,
    missing.length ? '缺少：' + missing.join(',') : ids.length + ' 个 id 全部存在');

  const labels = ['当前帧', '全部半透明', '其他帧', '点云', '边界像素', '平均色',
    '立方体线框', '时间轴', '正视', '等轴', '俯视', '原画质不缩放', '自动适配',
    '帧厚度', '帧间距', '亮处更密', '暗处更密', '点云密度', '显示厚度条', '四色立面',
    '每帧保留', '每 2 帧取 1', '取消', '只保留轮廓', '对比门槛',
    '切割', '只显示选区', '框选区域', '整个画面', '应用这个选区'];
  const noLabel = labels.filter((t) => !html.includes(t));
  R.check('所有中文控制项文案都在', noLabel.length === 0,
    noLabel.length ? '缺少：' + noLabel.join(',') : labels.length + ' 项全部存在');

  R.check('「显示厚度条」默认勾选', /<input id="showBands" type="checkbox" checked>/.test(html));
  R.check('「四色立面」默认不勾选（它只是诊断用）',
    /<input id="bandDebug" type="checkbox">/.test(html) &&
    !/<input id="bandDebug" type="checkbox" checked>/.test(html), '默认关闭');

  /*
   * 轮廓提取：默认关闭（它是一个"另一种看法"，不是默认外观），
   * 门槛滑块带着真实的默认值，而且门槛的文案要能看懂"越大越干净"。
   */
  R.check('「只保留轮廓」复选框在 HTML 里且默认不勾选',
    /<input id="outline" type="checkbox">/.test(html) &&
    !/<input id="outline" type="checkbox" checked>/.test(html),
    (html.match(/<input id="outline"[^>]*>/) || [''])[0]);
  R.check('轮廓门槛是滑块且带默认值 0.25',
    /<input id="edge"[^>]*type="range"[^>]*value="0\.25"/.test(html) ||
    /<input id="edge"[^>]*value="0\.25"[^>]*type="range"/.test(html),
    (html.match(/<input id="edge"[^>]*>/) || [''])[0]);
  R.check('门槛的显示值标签存在（lbEdge）',
    /id="lbEdge"/.test(html), (html.match(/<span id="lbEdge"[^>]*>[^<]*<\/span>/) || [''])[0]);

  /*
   * 切割：开关默认关闭（不改动用户看到的画面），框选面板默认隐藏
   * （它是模态的，绝不能一开始就盖在画面上）。
   */
  R.check('「只显示选区」复选框存在且默认不勾选',
    /<input id="clip" type="checkbox">/.test(html) &&
    !/<input id="clip" type="checkbox" checked>/.test(html),
    (html.match(/<input id="clip"[^>]*>/) || [''])[0]);
  R.check('框选面板默认是隐藏的（hidden 属性在）',
    /<div id="crop" hidden>/.test(html), (html.match(/<div id="crop"[^>]*>/) || [''])[0]);
  R.check('框选面板里有画布 + 八个手柄（四角四边）',
    /<canvas id="cropCanvas">/.test(html) &&
    (html.match(/data-h="/g) || []).length === 8,
    '手柄数量 = ' + (html.match(/data-h="/g) || []).length);
  R.check('框选面板里说明选区是对所有帧生效的（不是只切当前帧）',
    /对所有帧生效|对所有帧/.test(html), '文案里有"对所有帧"');
  R.check('框选面板带一层遮罩（选区外压暗，一眼看出会被丢掉的是哪块）',
    /#cropRect\{[^}]*box-shadow/.test(html) && /#crop\b|#crop\{/.test(html),
    'box-shadow 铺满遮罩 + #crop 定位');
  /*
   * ★ 框选层必须收缩到画布大小。
   * 它是 flex 列的子项、默认会被拉伸到整个面板宽度，而画布受 max-width/max-height
   * 限制常常窄得多 —— 一旦外框比画布宽，"按百分比定位的选区"与"鼠标坐标换算"
   * 就会用错分母：框看着还跟手，选出来的区域却整体偏左（用户报过这个）。
   */
  R.check('★ 框选层收缩到画布大小（width:fit-content，分母才不会用错）',
    /#cropWrap\{[^}]*width:fit-content/.test(html),
    (html.match(/#cropWrap\{[^}]*\}/) || [''])[0].slice(0, 120));

  // 视频：文件框必须同时收图片与视频，且抽帧默认「每帧保留」
  R.check('文件框同时接受图片与视频',
    /<input id="file"[^>]*accept="image\/\*,video\/\*"/.test(html),
    (html.match(/<input id="file"[^>]*>/) || [''])[0]);
  R.check('「视频抽帧」默认是「每帧保留」（value=1 且在最前面）',
    /<option value="1">视频：每帧保留<\/option>/.test(html) &&
    html.indexOf('视频：每帧保留') < html.indexOf('每 2 帧取 1'),
    '默认不抽稀');
  R.check('抽帧时长视频要有「取消」（实时抽帧不能卡死界面）',
    /<button id="veilCancel"/.test(html), 'veil 里有取消按钮');

  // 「每张照片的显示区域描边」必须默认关闭 —— 200 帧时它会把画面叠成一片白
  R.check('「显示区域描边」默认不勾选（避免叠加成纯白）',
    /<input id="showOutline" type="checkbox">/.test(html) &&
    !/<input id="showOutline" type="checkbox" checked>/.test(html),
    'HTML 里该复选框没有 checked 属性');
  R.check('「立方体线框」默认勾选', /<input id="showCube" type="checkbox" checked>/.test(html));

  R.check('声明了 UTF-8 且 charset 在头部', /<meta charset="utf-8">/i.test(html.slice(0, 600)));
  R.check('有 WebGL2 不可用时的提示文案', html.includes('WebGL2'));
}

/* ---------------------------------------------- 警告条会自动渐隐 */

R.section('警告条：3 秒后自己渐隐（不要求用户手动关）');
{
  /*
   * 用户的原话："丢帧必然存在，那就让警告信息在3秒后渐隐消失"。
   * 这里检查的是打包后的成品里确实带着这套行为 —— 时间行为本身在
   * video.test.mjs 里用真时钟断言。
   */
  R.check('提示条有 .on / .out 两个类（显示与淡出分开，不是一个 opacity 数字）',
    /#fatal\.on\s*\{\s*display:block\s*\}/.test(html) && /#fatal\.out\s*\{[^}]*opacity:0/.test(html),
    '#fatal.on / #fatal.out 都在样式里');
  R.check('淡出是过渡而不是瞬间消失（"渐隐"）',
    /#fatal\{[^}]*transition:opacity[^}]*ease/.test(html),
    (html.match(/#fatal\{[^}]*\}/) || [''])[0].slice(0, 120));
  R.check('淡出后不再挡住鼠标（pointer-events 关掉）',
    /#fatal\.out\s*\{[^}]*pointer-events:none/.test(html), 'pointer-events:none');
  R.check('保持时间是 3 秒（FATAL_HOLD_MS = 3000）',
    /FATAL_HOLD_MS\s*=\s*3000/.test(html), (html.match(/FATAL_HOLD_MS\s*=\s*\d+/) || [''])[0]);
  R.check('点一下可以再看一次（淡出可逆）',
    /el\.addEventListener\('click',\s*function\s*\(\)\s*\{\s*showFatal\(\);\s*\}\)/.test(html),
    'armFatalDismiss 里绑了 click → showFatal');
  R.check('换一批照片时旧提示会被清掉（不带着上一批的警告）',
    /function clearFatal\(\)[\s\S]{0,400}classList\.remove\('on'\)/.test(html),
    'clearFatal 里移除了 on/out');
}

process.exitCode = R.summary() ? 1 : 0;
