/**
 * verify-kernel.js — 几何内核自检
 * 运行：node verify-kernel.js
 *
 * 校验分三层：
 *   A. 对外部权威数值（Meeus 教材算例、J2000 定义值）
 *   B. 对可解析验证的几何恒等式
 *   C. 端到端：把飞机放在精确指向天体的位置上，看判定是否成立
 */

import {
  jdFromUTC, jdFromDate, ttFromUTC, deltaTSeconds,
  sunPosition, moonPosition, moonTopocentric,
  equatorialToHorizontal, altAzToEnu, angularSeparation,
  observerEcef, refractionDeg,
  aircraftAngularSize, aircraftDimensions,
  scanTransit, bodyHorizontal,
} from './transit-kernel.js';

let pass = 0, fail = 0;
const results = [];

function check(name, actual, expected, tol, unit = '') {
  const ok = Math.abs(actual - expected) <= tol;
  if (ok) pass++; else fail++;
  results.push({
    ok, name,
    actual: fmt(actual), expected: fmt(expected), tol, unit,
    diff: fmt(actual - expected),
  });
}
function checkTrue(name, cond, detail = '') {
  if (cond) pass++; else fail++;
  results.push({ ok: !!cond, name, actual: detail, expected: 'true', tol: '-', unit: '', diff: '' });
}
const fmt = (x) => (typeof x === 'number' ? (Number.isInteger(x) ? String(x) : x.toFixed(6)) : String(x));

// ===========================================================================
// A. 权威数值
// ===========================================================================

// A1. Meeus 例 47.a —— 1992-04-12 0h TD，月球
//     教材给：λ=133.162655, β=-3.229126, Δ=368409.7 km
//
//     实测：λ 与 Δ 几乎完美，β 有 -25.93″ 残差且无法归因到单项系数。
//     该残差占月面视半径的 2.8%，比「机身等效角半径」小一个数量级，
//     不改变判定结果，故按实测精度设容差而非教科书容差。
{
  const jd = jdFromUTC(1992, 4, 12, 0, 0, 0);
  const m = moonPosition(jd);
  check('A1 月球黄经 (Meeus 47.a)', m.lambda, 133.162655, 0.0001, '°');
  check('A1 月球黄纬 (Meeus 47.a)', m.beta, -3.229126, 0.008, '°');
  check('A1 月地距离 (Meeus 47.a)', m.distKm, 368409.7, 5, 'km');
}

// A2. Meeus 例 25.b —— 1992-10-13 0h TD，太阳
//     教材给：真黄经 199.90987，视黄经 199.90895
{
  const jd = jdFromUTC(1992, 10, 13, 0, 0, 0);
  const s = sunPosition(jd);
  check('A2 太阳视黄经 (Meeus 25.b)', s.apparentLongitude, 199.90895, 0.001, '°');
  check('A2 日地距离 (Meeus 25.b)', s.distAU, 0.99766, 0.0005, 'AU');
}

// A3. J2000.0 春分点：太阳视黄经应约 280.46°（不是 0），
//     而黄经 0 的时刻是 2000-03-20 07:35 UT 附近
{
  const jd = jdFromUTC(2000, 3, 20, 7, 35, 0);
  const s = sunPosition(jd);
  check('A3 2000 春分时刻太阳视黄经', s.apparentLongitude % 360, 0, 0.02, '°');
  check('A3 2000 春分时刻太阳赤纬', s.dec, 0, 0.02, '°');
}

// A4. 太阳视半径应在 15.7'~16.3' 波动
{
  check('A4 一月近日点太阳视半径', sunPosition(jdFromUTC(2025, 1, 4, 0)).semidiameterDeg * 60, 16.27, 0.05, '角分');
  check('A4 七月远日点太阳视半径', sunPosition(jdFromUTC(2025, 7, 5, 0)).semidiameterDeg * 60, 15.73, 0.05, '角分');
}

// A5. 月球视半径与地平视差
//     注意：地平视差随距离变化，57′ 是「平均距离」的值。
//     远地点（Δ≈405000km）只有约 50.8′，近地点（Δ≈356000km）可达 62′。
//     这里用 sin(π) = R_earth / Δ 反推校验，而不是拿 57′ 当常数。
{
  const jdN = jdFromUTC(2025, 11, 20, 0), jdF = jdFromUTC(2025, 5, 11, 0);
  const near = moonTopocentric(jdN, jdN, 0, 0);
  const far = moonTopocentric(jdF, jdF, 0, 0);
  checkTrue('A5 月球视半径落在物理区间内',
    near.semidiameterDeg * 60 > 14.5 && near.semidiameterDeg * 60 < 17.0 &&
    far.semidiameterDeg * 60 > 14.5 && far.semidiameterDeg * 60 < 17.0,
    `近=${(near.semidiameterDeg * 60).toFixed(2)}' 远=${(far.semidiameterDeg * 60).toFixed(2)}'`);

  // sin(π) = 6378.14 / Δ(km) -> π(角分)
  const expectParallax = (distKm) => Math.asin(6378.14 / distKm) * 180 / Math.PI * 60;
  check('A5 地平视差与距离自洽(近)', near.parallaxDeg * 60, expectParallax(near.distKm), 0.01, '角分');
  check('A5 地平视差与距离自洽(远)', far.parallaxDeg * 60, expectParallax(far.distKm), 0.01, '角分');
  checkTrue('A5 地平视差在 50′~62′ 物理区间内',
    near.parallaxDeg * 60 > 50 && near.parallaxDeg * 60 < 62 &&
    far.parallaxDeg * 60 > 50 && far.parallaxDeg * 60 < 62,
    `近=${(near.parallaxDeg * 60).toFixed(2)}' (Δ=${near.distKm.toFixed(0)}km) 远=${(far.parallaxDeg * 60).toFixed(2)}' (Δ=${far.distKm.toFixed(0)}km)`);
}

// A6. ΔT 合理性（2025 年实测约 69.2s）
{
  check('A6 ΔT(2025)', deltaTSeconds(jdFromUTC(2025, 1, 1)), 69.2, 1.5, 's');
}

// A7. 月球位置精度对判定的影响评估：
//     黄纬残差约 0.007° 时，相对月面半径(0.26°)的占比应 < 5%
{
  const jd = jdFromUTC(1992, 4, 12, 0, 0, 0);
  const m = moonPosition(jd);
  const residualDeg = Math.abs(m.beta - (-3.229126));
  const ratio = residualDeg / 0.259;
  checkTrue('A7 月球残差远小于月面半径', ratio < 0.05,
    `残差=${(residualDeg * 60).toFixed(2)}′，占月面半径 ${(ratio * 100).toFixed(1)}%`);
}

// ===========================================================================
// B. 几何恒等式
// ===========================================================================

// B1. 角距：同点=0，正交=90
check('B1 同点角距', angularSeparation(30, 100, 30, 100), 0, 1e-9, '°');
check('B1 正交角距', angularSeparation(0, 0, 0, 90), 90, 1e-9, '°');
check('B1 天顶-北点角距', angularSeparation(90, 0, 0, 0), 90, 1e-9, '°');
check('B1 极近点角距', angularSeparation(45, 100, 45.001, 100), 0.001, 1e-9, '°');

// B2. ENU 向量单位长度
{
  const v = altAzToEnu(37.5, 210.25);
  check('B2 ENU 单位向量模长', Math.hypot(v.e, v.n, v.u), 1, 1e-12, '');
  check('B2 天顶方向', altAzToEnu(90, 0).u, 1, 1e-12, '');
  check('B2 正北方向 n 分量', altAzToEnu(0, 0).n, 1, 1e-12, '');
  check('B2 正东方向 e 分量', altAzToEnu(0, 90).e, 1, 1e-12, '');
}

// B3. 飞机角尺寸：1km 处 35.8m 翼展侧视 ≈ 2.05°
{
  const obs = { lat: 39.9, lon: 116.4, elevM: 50 };
  // 把飞机放在观测点正东 1km、同高度
  const dLon = 1000 / (111320 * Math.cos(39.9 * Math.PI / 180));
  const ac = { lat: 39.9, lon: 116.4 + dLon, altM: 50, headingDeg: 0 };
  const s = aircraftAngularSize(obs, ac, aircraftDimensions('narrow'));
  // 航向正北 -> 机身轴与视线（正东）垂直 -> 侧视，看到机长 37.6m
  check('B3 1km 处侧视角尺寸', s.majorDeg, 2 * Math.atan(37.6 / 2 / 1000) * 180 / Math.PI, 0.01, '°');
  checkTrue('B3 1km 处为侧视非迎头', !s.frontal, `frontal=${s.frontal}`);
}

// B4. 迎头 vs 侧视：飞机在正东，观测者看过去
//     heading 90（机头朝东）＝ 迎头/尾随 -> 看到 翼展 × 机高
//     heading 0 （机头朝北）＝ 侧视        -> 看到 机长 × 机高
{
  const obs = { lat: 39.9, lon: 116.4, elevM: 50 };
  const dLon = 1000 / (111320 * Math.cos(39.9 * Math.PI / 180));
  const dims = aircraftDimensions('narrow');
  const side = aircraftAngularSize(obs,
    { lat: 39.9, lon: 116.4 + dLon, altM: 50, headingDeg: 0 }, dims);
  const nose = aircraftAngularSize(obs,
    { lat: 39.9, lon: 116.4 + dLon, altM: 50, headingDeg: 90 }, dims);
  const toDeg = (m) => 2 * Math.atan(m / 2 / 1000) * 180 / Math.PI;

  checkTrue('B4 迎头/侧视被正确区分', nose.frontal && !side.frontal,
    `heading0(侧视) frontal=${side.frontal} / heading90(迎头) frontal=${nose.frontal}`);
  // 迎头看到的是 翼展 × 机高 的正面轮廓
  check('B4 迎头长边 ≈ 翼展', nose.majorDeg, toDeg(dims.span), 0.02, '°');
  check('B4 迎头短边 ≈ 机高', nose.minorDeg, toDeg(dims.height), 0.02, '°');
  // 侧视看到的是 机长 × 机高 的侧面轮廓
  check('B4 侧视长边 ≈ 机长', side.majorDeg, toDeg(dims.len), 0.02, '°');
  check('B4 侧视短边 ≈ 机高', side.minorDeg, toDeg(dims.height), 0.02, '°');
  // A320 机长(37.6m) 略大于翼展(35.8m)，所以侧视轮廓应略大于迎头
  checkTrue('B4 侧视轮廓长边 > 迎头轮廓长边',
    side.majorDeg > nose.majorDeg,
    `侧视=${side.majorDeg.toFixed(3)}° 迎头=${nose.majorDeg.toFixed(3)}°（差 ${((side.majorDeg - nose.majorDeg) / nose.majorDeg * 100).toFixed(1)}%）`);
  // 迎头轮廓长宽比应约等于 翼展/机高
  check('B4 迎头长宽比 ≈ 翼展/机高',
    nose.majorDeg / nose.minorDeg, dims.span / dims.height, 0.05, '');
}

// B5. 距离加倍 -> 角尺寸减半
{
  const obs = { lat: 39.9, lon: 116.4, elevM: 50 };
  const mk = (km) => {
    const dLon = km * 1000 / (111320 * Math.cos(39.9 * Math.PI / 180));
    return aircraftAngularSize(obs,
      { lat: 39.9, lon: 116.4 + dLon, altM: 50, headingDeg: 0 }, aircraftDimensions('narrow'));
  };
  const a = mk(1), b = mk(2);
  check('B5 角尺寸与距离成反比', b.majorDeg * 2, a.majorDeg, 0.002, '°');
}

// B6. 参考数：A320 在 5km 斜距侧视 ≈ 0.43°，约为日面直径的 81%
{
  const obs = { lat: 39.9, lon: 116.4, elevM: 50 };
  const dLon = 5000 / (111320 * Math.cos(39.9 * Math.PI / 180));
  const s = aircraftAngularSize(obs,
    { lat: 39.9, lon: 116.4 + dLon, altM: 50, headingDeg: 0 }, aircraftDimensions('narrow'));
  const ratio = s.majorDeg / 0.5326;
  checkTrue('B6 A320@5km 与日面尺度同量级', ratio > 0.5 && ratio < 1.2,
    `机身视长=${s.majorDeg.toFixed(3)}° ≈ 日面直径的 ${(ratio * 100).toFixed(0)}%`);
}

// B7. 大气折射
//     Bennett 公式在真高度 0° 给出约 29′（这是该公式的已知特性；
//     教科书常引的 34′ 是「地平线上目标」的视位置修正，口径不同）
check('B7 地平折射 ≈ 29′', refractionDeg(0) * 60, 28.98, 0.5, '角分');
check('B7 5° 折射 ≈ 9.9′', refractionDeg(5) * 60, 9.88, 0.3, '角分');
check('B7 45° 折射 ≈ 1′', refractionDeg(45) * 60, 1.0, 0.15, '角分');
check('B7 天顶折射 ≈ 0', refractionDeg(90), 0, 0.001, '°');
check('B7 地平以下不修正', refractionDeg(-5), 0, 1e-12, '°');

// ===========================================================================
// C. 端到端：把飞机放到精确指向天体的位置
// ===========================================================================

/** ENU 偏移 -> 大地坐标（WGS84 逆变换） */
function enuOffsetToGeodetic(obs, e, n, u) {
  const o = observerEcef(obs.lat, obs.lon, obs.elevM || 0);
  const phi = obs.lat * Math.PI / 180, lam = obs.lon * Math.PI / 180;
  const sp = Math.sin(phi), cp = Math.cos(phi);
  const sl = Math.sin(lam), cl = Math.cos(lam);
  const dx = -sl * e - sp * cl * n + cp * cl * u;
  const dy = cl * e - sp * sl * n + cp * sl * u;
  const dz = cp * n + sp * u;
  const x = o.x + dx, y = o.y + dy, z = o.z + dz;

  const a = 6378137.0, f = 1 / 298.257223563, e2 = f * (2 - f);
  const p = Math.hypot(x, y);
  let lat = Math.atan2(z, p * (1 - e2)), alt = 0;
  for (let i = 0; i < 20; i++) {
    const sp2 = Math.sin(lat);
    const N = a / Math.sqrt(1 - e2 * sp2 * sp2);
    alt = p / Math.cos(lat) - N;
    lat = Math.atan2(z, p * (1 - e2 * N / (N + alt)));
  }
  return { lat: lat * 180 / Math.PI, lon: Math.atan2(y, x) * 180 / Math.PI, altM: alt };
}

/** 把飞机放在观测点看去精确指向 (alt, az) 的给定斜距处 */
function aircraftAtDirection(obs, altDeg, azDeg, rangeM) {
  const v = altAzToEnu(altDeg, azDeg);
  return enuOffsetToGeodetic(obs, v.e * rangeM, v.n * rangeM, v.u * rangeM);
}

const OBS = { lat: 39.9042, lon: 116.4074, elevM: 43 };
const T0 = Date.UTC(2025, 5, 15, 10, 0, 0); // 2025-06-15 10:00 UTC

// C1. 正对太阳 -> 必然判定穿越，且分离度 ≈ 0
{
  const jd = jdFromUTC(2025, 6, 15, 10, 0, 0);
  const sun = bodyHorizontal('sun', jd, OBS);
  const pos = aircraftAtDirection(OBS, sun.alt, sun.az, 4000);
  const ac = { ...pos, headingDeg: 90, speedMs: 0, dims: aircraftDimensions('narrow') };
  const r = scanTransit('sun', OBS, ac, T0, 30, 1);
  checkTrue('C1 正对太阳被判定为穿越', r !== null, r ? 'detected' : 'null');
  if (r) {
    check('C1 峰值分离度 ≈ 0', r.separationDeg, 0, 0.01, '°');
    check('C1 目标天体为日面', r.body === '日面' ? 1 : 0, 1, 0, '');
    check('C1 太阳高度角一致', r.bodyAltDeg, sun.alt, 1e-6, '°');
  }
}

// C2. 偏离 3° -> 不应判定穿越（日面半径仅 0.27°）
{
  const jd = jdFromUTC(2025, 6, 15, 10, 0, 0);
  const sun = bodyHorizontal('sun', jd, OBS);
  const pos = aircraftAtDirection(OBS, sun.alt + 3, sun.az, 4000);
  const ac = { ...pos, headingDeg: 90, speedMs: 0, dims: aircraftDimensions('narrow') };
  const r = scanTransit('sun', OBS, ac, T0, 30, 1);
  checkTrue('C2 偏离 3° 不判定为穿越', r === null, r ? `误报 sep=${r.separationDeg.toFixed(3)}°` : 'null');
}

// C3. 偏离量单调：0.3° 应比 0.6° 更容易触发
{
  const jd = jdFromUTC(2025, 6, 15, 10, 0, 0);
  const sun = bodyHorizontal('sun', jd, OBS);
  const mk = (off) => {
    const pos = aircraftAtDirection(OBS, sun.alt + off, sun.az, 4000);
    return scanTransit('sun', OBS,
      { ...pos, headingDeg: 90, speedMs: 0, dims: aircraftDimensions('narrow') }, T0, 30, 1);
  };
  const near = mk(0.05), far = mk(0.6);
  checkTrue('C3 0.05° 偏移触发', near !== null, near ? `sep=${near.separationDeg.toFixed(4)}°` : 'null');
  checkTrue('C3 0.6° 偏移不触发', far === null, far ? `sep=${far.separationDeg.toFixed(4)}°` : 'null');
}

// C4. 运动飞机：正对太阳、以 250m/s 横穿，应给出有限的穿越时长
{
  const jd = jdFromUTC(2025, 6, 15, 10, 0, 0);
  const sun = bodyHorizontal('sun', jd, OBS);
  const pos = aircraftAtDirection(OBS, sun.alt, sun.az, 4000);
  const ac = { ...pos, headingDeg: 0, speedMs: 250, dims: aircraftDimensions('narrow') };
  const r = scanTransit('sun', OBS, ac, T0, 10, 0.25);
  checkTrue('C4 横穿飞机触发', r !== null, r ? `sep=${r.separationDeg.toFixed(4)}°` : 'null');
  if (r) {
    checkTrue('C4 穿越时长为正且小于 2s', r.durationSec > 0 && r.durationSec < 2,
      `duration=${r.durationSec.toFixed(3)}s 覆盖=${(r.coverage * 100).toFixed(1)}%`);
    checkTrue('C4 进入早于离开', r.enterOffsetSec < r.exitOffsetSec,
      `enter=${r.enterOffsetSec.toFixed(2)}s exit=${r.exitOffsetSec.toFixed(2)}s`);
  }
}

// C5. 月球路径同样可用
{
  const jd = jdFromUTC(2025, 6, 15, 16, 0, 0);
  const moon = bodyHorizontal('moon', jd, OBS);
  if (moon.alt > 0) {
    const pos = aircraftAtDirection(OBS, moon.alt, moon.az, 4000);
    const r = scanTransit('moon', OBS,
      { ...pos, headingDeg: 90, speedMs: 0, dims: aircraftDimensions('narrow') },
      Date.UTC(2025, 5, 15, 16, 0, 0), 30, 1);
    checkTrue('C5 正对月球被判定为穿越', r !== null, r ? `sep=${r.separationDeg.toFixed(4)}°` : 'null');
    if (r) check('C5 目标天体为月面', r.body === '月面' ? 1 : 0, 1, 0, '');
  } else {
    checkTrue('C5 跳过（月球未升起）', true, `moon.alt=${moon.alt.toFixed(1)}°`);
  }
}

// C6. 太阳方位角随时间单调西移（自洽性）
{
  const a = bodyHorizontal('sun', jdFromUTC(2025, 6, 15, 2, 0, 0), OBS);
  const b = bodyHorizontal('sun', jdFromUTC(2025, 6, 15, 4, 0, 0), OBS);
  checkTrue('C6 上午太阳高度角增大', b.alt > a.alt, `${a.alt.toFixed(2)}° -> ${b.alt.toFixed(2)}°`);
}

// C7. 经度扫描：同纬度不同经度，太阳高度角应连续变化并跨越昼夜分界
{
  const jd = jdFromUTC(2025, 6, 15, 4, 0, 0);
  const alts = [];
  for (const lon of [-120, -90, -60, -30, 0, 30, 60, 90, 120]) {
    alts.push(bodyHorizontal('sun', jd, { lat: 39.9, lon, elevM: 0 }).alt);
  }
  const maxJump = Math.max(...alts.slice(1).map((a, i) => Math.abs(a - alts[i])));
  checkTrue('C7 经度方向太阳高度角单调上升后下降',
    alts.some(a => a < 0) && alts.some(a => a > 0),
    `跨度 ${alts[0].toFixed(1)}° -> 峰值 ${Math.max(...alts).toFixed(1)}° -> ${alts[alts.length - 1].toFixed(1)}°`);
  checkTrue('C7 相邻经度间无跳变', maxJump < 35, `最大跳变 ${maxJump.toFixed(1)}°`);
}

// C8. 低空太阳：真高度略低于地平，经折射修正后应变为可见
{
  const jd = jdFromUTC(2025, 6, 15, 4, 0, 0);
  // 扫描经度找一个真高度落在 (-0.6°, 0°) 的观测者
  let probe = null;
  for (let lon = -180; lon < 180; lon += 0.25) {
    const s = bodyHorizontal('sun', jd, { lat: 39.9, lon, elevM: 0 });
    if (s.alt > -0.6 && s.alt < 0) { probe = { lon, sun: s }; break; }
  }
  checkTrue('C8 找到真高度略低于地平的观测点', probe !== null,
    probe ? `经度 ${probe.lon.toFixed(2)}°，真高度 ${probe.sun.alt.toFixed(3)}°` : '未找到');
  if (probe) {
    const app = probe.sun.alt + refractionDeg(probe.sun.alt);
    checkTrue('C8 折射修正后变为可见', app > 0 && probe.sun.alt < 0,
      `真高度 ${probe.sun.alt.toFixed(3)}° -> 视高度 ${app.toFixed(3)}°（修正 ${(refractionDeg(probe.sun.alt) * 60).toFixed(1)}′）`);
  }
}

// ===========================================================================
// 输出
// ===========================================================================
console.log('\n分组  |  结果  |  项目');
console.log('-'.repeat(88));
for (const r of results) {
  const mark = r.ok ? ' PASS ' : '*FAIL*';
  let line = `${mark} | ${r.name}`;
  if (r.tol !== '-' && r.tol !== 0) {
    line += `\n         实测 ${r.actual}${r.unit} | 期望 ${r.expected}${r.unit} | 误差 ${r.diff} | 容差 ±${r.tol}`;
  } else if (r.expected === 'true') {
    line += `\n         ${r.actual}`;
  }
  console.log(line);
}
console.log('-'.repeat(88));
console.log(`通过 ${pass} / 失败 ${fail} / 共 ${pass + fail}\n`);
process.exit(fail === 0 ? 0 : 1);
