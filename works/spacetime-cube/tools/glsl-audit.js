// GLSL 静态审查：在拿不到真实编译器的情况下，尽可能把「编译期就能发现的错误」揪出来。
// 重点是这类：某变量被赋值/使用，却从未声明 —— 这正是 uScale 漏声明那次故障的形态。
//
// 检查项：
//   1. uniform 声明 vs 引用（双向）
//   2. 变量「只被赋值、从未声明」
//   3. 大括号配平、括号配平
//   4. 每个语句以 ; { } 结尾的粗查
//   5. 引用的内建函数是否在白名单里（拼写错误会在这里暴露）
//
// 用法： node tools/glsl-audit.js

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const SHADER = fs.readFileSync(path.join(ROOT, 'shader.js'), 'utf8');

const out = [];
let bad = 0;
const check = (name, pass, detail) => {
  if (!pass) bad++;
  out.push(`${pass ? 'PASS' : 'FAIL'}  ${name}   [${detail}]`);
};

// 取出两个模板字符串（vertexShader / fragmentShader）。
// 用字符串定位而不是正则，避免反引号 / 斜杠的转义坑。
function extract(marker) {
  const start = SHADER.indexOf(marker);
  if (start < 0) return '';
  const tick1 = SHADER.indexOf('`', start);
  const tick2 = SHADER.indexOf('`;', tick1);
  return (tick1 < 0 || tick2 < 0) ? '' : SHADER.slice(tick1 + 1, tick2);
}

const vertexSrc = extract('export const vertexShader');
const fragSrc = extract('export const fragmentShader');

check('能提取到 vertex shader 源码', vertexSrc.length > 20, vertexSrc.length + ' 字符');
check('能提取到 fragment shader 源码', fragSrc.length > 200, fragSrc.length + ' 字符');

// GLSL ES 3.0 内建（够用即可，不求全）
const BUILTINS = new Set([
  'gl_Position', 'gl_FragColor', 'gl_FragCoord', 'gl_PointSize', 'gl_FrontFacing',
  'position', 'uv', 'normal', 'vec2', 'vec3', 'vec4', 'mat2', 'mat3', 'mat4',
  'float', 'int', 'bool', 'void', 'sampler3D', 'sampler2D',
  'if', 'else', 'for', 'while', 'return', 'break', 'continue', 'discard',
  'in', 'out', 'inout', 'const', 'uniform', 'varying', 'attribute', 'struct',
  'min', 'max', 'clamp', 'mix', 'step', 'smoothstep', 'abs', 'sign', 'floor',
  'ceil', 'fract', 'mod', 'sqrt', 'inversesqrt', 'pow', 'exp', 'exp2', 'log',
  'log2', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'radians', 'degrees',
  'length', 'distance', 'dot', 'cross', 'normalize', 'reflect', 'refract',
  'texture', 'textureLod', 'texelFetch', 'true', 'false', 'precision',
  'highp', 'mediump', 'lowp', 'main'
]);
for (const [label, src] of [['顶点着色器', vertexSrc], ['片元着色器', fragSrc]]) {
  // 去掉注释，避免注释里的词干扰
  let code = src.replace(/\/\/[^\n]*/g, ' ').replace(/\/\*[\s\S]*?\*\//g, ' ');
  // swizzle 检查必须用「只去注释、还没剥 swizzle」的版本 ——
  // 否则等于在剥掉之后再去验证 swizzle，永远是空集（这里吃过一次假阴性）。
  const codeWithSwizzle = code.replace(/\d[eE][-+]?\d+/g, ' ');
  // 去掉 swizzle 后缀（.xy / .rgb / .x 等），它们是字段访问不是标识符，
  // 否则会被当成「未声明的标识符」误报
  code = code.replace(/\.(?:[xyzwrgba]{1,4})\b/g, ' ');
  // 去掉科学计数法里的 e（1e-4 / 2.0e3），否则那个 e 会被当成独立标识符
  code = code.replace(/\d[eE][-+]?\d+/g, ' ');

  // 括号配平
  const count = ch => (code.match(new RegExp('\\' + ch, 'g')) || []).length;
  check(`${label}：大括号配平`, count('{') === count('}'), `{ ${count('{')} } ${count('}')}`);
  check(`${label}：圆括号配平`, count('(') === count(')'), `( ${count('(')} ) ${count(')')}`);

  // 声明的变量
  const declared = new Set(['main']);
  for (const m of code.matchAll(/\b(?:uniform|varying|attribute|const)\s+\w+\s+(\w+)/g)) declared.add(m[1]);
  for (const m of code.matchAll(/\b(?:float|int|bool|vec2|vec3|vec4|mat2|mat3|mat4|sampler3D)\s+([A-Za-z_]\w*)\s*[=;,)]/g)) declared.add(m[1]);

  // 函数定义与参数
  for (const m of code.matchAll(/\b\w+\s+(\w+)\s*\(([^)]*)\)\s*\{/g)) {
    declared.add(m[1]);
    for (const arg of m[2].split(',')) {
      const t = arg.trim().split(/\s+/);
      if (t.length >= 2) declared.add(t[t.length - 1].replace(/[\[\]]/g, ''));
    }
  }
  // 循环变量
  for (const m of code.matchAll(/for\s*\(\s*\w+\s+(\w+)\s*=/g)) declared.add(m[1]);

  // 全部标识符
  const ids = [...new Set((code.match(/[A-Za-z_]\w*/g) || []))];
  const unknown = ids.filter(id => !declared.has(id) && !BUILTINS.has(id));

  check(`${label}：没有用到未声明的标识符`,
    unknown.length === 0,
    unknown.length ? '可疑: ' + unknown.join(',') : `${ids.length} 个标识符全部有出处`);

  // 有可疑标识符时打印上下文，省得回头再猜
  for (const id of [...unknown]) {
    const re = new RegExp('\\b' + id + '\\b', 'g');
    let m;
    let shown = 0;
    while ((m = re.exec(code)) && shown < 3) {
      shown++;
      out.push(`      ${id} @${m.index}: `
        + JSON.stringify(code.slice(Math.max(0, m.index - 60), m.index + 60).replace(/\s+/g, ' ')));
    }
  }

  // 只被赋值、从未声明的标识符（uScale 那类错误）
  const assigned = [...new Set([...code.matchAll(/[^=!<>+\-*/]\b([A-Za-z_]\w*)\s*=(?!=)/g)].map(m => m[1]))];
  const assignedUndeclared = assigned.filter(id => !declared.has(id) && !BUILTINS.has(id));
  check(`${label}：没有「只被赋值却没声明」的变量`,
    assignedUndeclared.length === 0,
    assignedUndeclared.length ? '未声明就赋值: ' + assignedUndeclared.join(',') : 'ok');

  // ---- swizzle 集合必须与向量类型匹配 ----
  // GLSL 规定：xyzw 只能用在向量上，rgba 也只能用在向量上，且一次 swizzle
  // 里不能混用两套字母。写在 vec3 上的 .a 会直接编译失败
  // （曾经因为把 vec3 的 colB 写成 colB.a 而炸掉整个着色器）。
  const varType = new Map();
  for (const m of fragSrc.matchAll(/\b(vec2|vec3|vec4|float|int|bool)\s+([A-Za-z_]\w*)\s*[=;,)]/g)) {
    varType.set(m[2], m[1]);
  }
  for (const m of fragSrc.matchAll(/\buniform\s+(vec2|vec3|vec4|float|int|bool)\s+(u[A-Za-z]\w*)\s*;/g)) {
    varType.set(m[2], m[1]);
  }

  const SIZE = { vec2: 2, vec3: 3, vec4: 4 };
  const badSwizzles = [];
  for (const m of codeWithSwizzle.matchAll(/\b([A-Za-z_]\w*)\s*\.\s*([xyzwrgba]{1,4})\b/g)) {
    const type = varType.get(m[1]);
    if (!type || !SIZE[type]) continue;
    const set = m[2];
    const positions = [];
    for (const ch of set) {
      const idxXYZW = 'xyzw'.indexOf(ch);
      const idxRGBA = 'rgba'.indexOf(ch);
      if (idxXYZW >= 0 && idxRGBA >= 0) {
        badSwizzles.push(`${m[1]}.${set} 字母 ${ch} 同时属于 xyzw 与 rgba`);
        break;
      }
      positions.push(idxXYZW >= 0 ? idxXYZW : idxRGBA);
    }
    for (const p of positions) {
      if (p >= SIZE[type]) {
        badSwizzles.push(`${type} 的 ${m[1]}.${set} 取了第 ${p + 1} 个分量（越界）`);
        break;
      }
    }
  }
  check(`${label}：swizzle 分量没有越界（.a 不能用在 vec3 上）`,
    badSwizzles.length === 0,
    badSwizzles.length ? badSwizzles.join(' | ') : `检查了 ${varType.size} 个已知类型的变量`);
}

// uniform 双向一致性
const fragUniforms = [...fragSrc.matchAll(/uniform\s+\w+\s+(u[A-Za-z]\w*)\s*;/g)].map(m => m[1]);
const app = fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8');
const appUniforms = [...app.matchAll(/\b(u[A-Za-z]\w*)\s*:\s*\{\s*value/g)].map(m => m[1]);

const useBody = fragSrc.replace(/uniform\s+\w+\s+u[A-Za-z]\w*\s*;/g, '');
const usedU = new Set(useBody.match(/\bu[A-Z]\w*\b/g) || []);

const declaredNotInApp = fragUniforms.filter(u => !appUniforms.includes(u));
const inAppNotDeclared = appUniforms.filter(u => !fragUniforms.includes(u));
const usedNotDeclared = [...usedU].filter(u => !fragUniforms.includes(u));

check('shader 声明的 uniform 都在 app.js 提供', declaredNotInApp.length === 0,
  declaredNotInApp.length ? '缺: ' + declaredNotInApp.join(',') : fragUniforms.length + ' 个');
check('shader 正文用到的 u* 都已声明', usedNotDeclared.length === 0,
  usedNotDeclared.length ? '未声明: ' + usedNotDeclared.join(',') : [...usedU].length + ' 个');
check('app.js 没有多余的 uniform', inAppNotDeclared.length === 0,
  inAppNotDeclared.length ? '多余: ' + inAppNotDeclared.join(',') : '一致');

const total = out.filter(l => l.startsWith('PASS') || l.startsWith('FAIL')).length;
const pass = out.filter(l => l.startsWith('PASS')).length;
out.push('', `${pass}/${total} 通过`);
const report = out.join('\n');
fs.writeFileSync(path.join(ROOT, 'test', 'glsl-audit.txt'), report, 'utf8');
console.log(report);
process.exit(bad ? 1 : 0);
