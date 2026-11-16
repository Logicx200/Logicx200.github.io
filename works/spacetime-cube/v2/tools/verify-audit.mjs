/* 反向验证：把精度声明去掉，确认新加的 uniform 精度审查真的会报错
 *
 * 为什么必须做这件事：README 里自己写过 ——
 *   "这类静态检查的难点是假阴性。新增检查时必须故意把 bug 注回去、确认它真的会报错。"
 * 第一版 swizzle 检查就犯过这个错：把要检查的东西先剥掉再验，等于验了空集，明明有 bug 却报通过。
 *
 * 用法：node tools/verify-audit.mjs
 */
import { createDom, loadApp } from './harness.mjs';

const dom = createDom({ width: 64, height: 64 });
const { STC } = loadApp(dom);

/** 与 test/pipeline.test.mjs 里那份**完全同一套**逻辑（故意重复一遍以便独立调用） */
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

function audit(vsSrc, fsSrc, isVertexPairBroken) {
  const v = uniformDecls(vsSrc, true);
  const f = uniformDecls(fsSrc, false);
  const shared = [...v.keys()].filter((k) => f.has(k));
  const bad = shared.filter((k) => v.get(k).type !== f.get(k).type || v.get(k).prec !== f.get(k).prec);
  return { shared, bad, v, f };
}

let ok = true;
function check(name, cond, detail) {
  console.log(`[${cond ? 'PASS' : 'FAIL'}] ${name}${detail ? '  — ' + detail : ''}`);
  if (!cond) ok = false;
}

const VS = STC.shaders.POINT_VS;
const FS_FIXED = STC.shaders.POINT_FS;
const FS_BROKEN = FS_FIXED.replace(/^\s*precision\s+highp\s+int;\n/m, '');

console.log('POINT_FS 是否已声明 precision highp int：' + /precision\s+highp\s+int;/.test(FS_FIXED));
console.log('构造出的"未修复版"是否已去掉该声明：' + (!/precision\s+highp\s+int;/.test(FS_BROKEN)));
console.log('');

// 1) 未修复版必须被判定为不一致
{
  const r = audit(VS, FS_BROKEN, true);
  check('未修复版被正确判定为精度不一致',
    r.bad.length === 1 && r.bad[0] === 'uSquare',
    r.bad.length
      ? r.bad.map((k) => `${k}: 顶点 ${r.v.get(k).prec} ${r.v.get(k).type} vs 片元 ${r.f.get(k).prec} ${r.f.get(k).type}`).join('；')
      : '（没报出来 —— 说明这条检查是假阴性，等于没查）');
}

// 2) 已修复版必须通过
{
  const r = audit(VS, FS_FIXED, true);
  check('已修复版通过', r.bad.length === 0,
    r.shared.map((k) => `${k}=${r.v.get(k).prec} ${r.v.get(k).type}`).join(' '));
}

// 3) 类型不一致也要能抓到（换成 float）
{
  const fsWrongType = FS_FIXED.replace('uniform int uSquare;', 'uniform float uSquare;');
  const r = audit(VS, fsWrongType, true);
  check('类型不一致（int vs float）也能抓到',
    r.bad.length === 1 && r.bad[0] === 'uSquare',
    r.bad.map((k) => `${k}: 顶点 ${r.v.get(k).type} vs 片元 ${r.f.get(k).type}`).join('；') || '没报出来');
}

// 4) 另外三个 program 也必须是干净的
for (const [vsName, fsName] of [['PLANE_VS', 'PLANE_FS'], ['BAND_VS', 'BAND_FS'], ['SOLID_VS', 'SOLID_FS']]) {
  const r = audit(STC.shaders[vsName], STC.shaders[fsName], true);
  check(`${vsName}/${fsName} 共享 uniform 干净`, r.bad.length === 0,
    r.shared.map((k) => `${k}=${r.v.get(k).prec} ${r.v.get(k).type}`).join(' ') || '无共享 uniform');
}

STC.app.stop();
console.log('');
console.log(ok ? '反向验证通过：这条检查不是假阴性。' : '反向验证失败：检查本身有问题。');
process.exit(ok ? 0 : 1);
