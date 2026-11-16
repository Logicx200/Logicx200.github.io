/**
 * transit-kernel.js — 凌日/凌月几何内核（零依赖，纯 ES module）
 *
 * 覆盖：
 *   1. 儒略日 / TT-UTC 时标处理
 *   2. 太阳视位置（Meeus《Astronomical Algorithms》ch.25）
 *   3. 月球视位置 + 地面视差（Meeus ch.47 / ch.40）
 *   4. 大气折射（Bennett）
 *   5. 飞机方向与角尺寸（含机身姿态的三维投影）
 *   6. 穿越判定：时间扫描 + 二分求极小值
 *
 * 全部输出单位为「度」（角度）与「米」（长度），除注明外。
 */

const DEG = Math.PI / 180;
export const norm360 = (x) => ((x % 360) + 360) % 360;
export const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);

// ---------------------------------------------------------------------------
// 1. 时间
// ---------------------------------------------------------------------------

/** 公历 UTC -> 儒略日（Meeus ch.7） */
export function jdFromUTC(y, m, d, h = 0, min = 0, s = 0) {
  let Y = y, M = m;
  if (M <= 2) { Y -= 1; M += 12; }
  const A = Math.floor(Y / 100);
  const B = 2 - A + Math.floor(A / 4);
  return (
    Math.floor(365.25 * (Y + 4716)) +
    Math.floor(30.6001 * (M + 1)) +
    d + B - 1524.5 +
    (h + min / 60 + s / 3600) / 24
  );
}

export function jdFromDate(date) {
  return jdFromUTC(
    date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate(),
    date.getUTCHours(), date.getUTCMinutes(), date.getUTCSeconds() + date.getUTCMilliseconds() / 1000
  );
}

export function ttFromUTC(jdUTC) {
  return jdUTC + deltaTSeconds(jdUTC) / 86400;
}

/**
 * ΔT = TT - UTC，秒。
 *
 * 注意：Espenak & Meeus 教科书多项式（62.92 + 0.32217t + 0.005589t²）
 * 是 2006 年做的预测，实测 ΔT 此后持续低于预测（2025 年预测 ~74.5s，
 * 实测 ~69.2s）。这里改用近年实测锚点 + 平滑推进。
 *
 * 对凌日判定的影响：ΔT 差 5 秒使月球位置差约 0.0007°，仅为月面半径的
 * 0.3%，不构成问题；但用准确的 ΔT 没有任何代价。
 */
export function deltaTSeconds(jd) {
  const y = 2000 + (jd - 2451545.0) / 365.25;
  if (y >= 2015 && y <= 2035) {
    // 2020.0 -> 69.36s（实测），2030 预测约 71.5s
    return 69.36 + (y - 2020) * 0.21;
  }
  if (y >= 1986 && y < 2015) {
    const t = y - 2000;
    return 63.86 + 0.3345 * t - 0.060374 * t * t + 0.0017275 * t ** 3
      + 0.000651814 * t ** 4 + 0.00002373599 * t ** 5;
  }
  if (y > 2035 && y <= 2150) {
    return 72.5 + (y - 2035) * 0.35 - 0.5628 * (2150 - y) * 0.02;
  }
  const u = (y - 1820) / 100;
  return -20 + 32 * u * u;
}

/** 格林尼治平恒星时（度），Meeus 12.4 */
function gmstDeg(jdUT) {
  const T = (jdUT - 2451545.0) / 36525;
  let th = 280.46061837 + 360.98564736629 * (jdUT - 2451545.0)
    + 0.000387933 * T * T - (T ** 3) / 38710000;
  return norm360(th);
}

// ---------------------------------------------------------------------------
// 2. 大气折射（Bennett 公式，标准气压 1010mb / 10°C）
//    h 为真高度角（度），返回「视高度 - 真高度」（度），地平附近约 +0.5667°
// ---------------------------------------------------------------------------
export function refractionDeg(h) {
  if (h < -1.0) return 0;
  const R = 1.02 / Math.tan((h + 10.3 / (h + 5.11)) * DEG); // 角分
  return R / 60;
}

// ---------------------------------------------------------------------------
// 3. 太阳
// ---------------------------------------------------------------------------

/**
 * 太阳视位置。均使用 Meeus 低精度公式（1900–2100 内黄经误差 < 0.01°）。
 * @returns {{ra,dec,distAU,apparentLongitude,semidiameterDeg,epsilon}}
 */
export function sunPosition(jdTT) {
  const T = (jdTT - 2451545.0) / 36525;
  const L0 = norm360(280.46646 + 36000.76983 * T + 0.0003032 * T * T);
  const M = norm360(357.52911 + 35999.05029 * T - 0.0001537 * T * T);
  const e = 0.016708634 - 0.000042037 * T - 0.0000001267 * T * T;
  const Mr = M * DEG;

  const C =
    (1.914602 - 0.004817 * T - 0.000014 * T * T) * Math.sin(Mr) +
    (0.019993 - 0.000101 * T) * Math.sin(2 * Mr) +
    0.000289 * Math.sin(3 * Mr);

  const trueLong = L0 + C;
  const v = M + C;
  const R = (1.000001018 * (1 - e * e)) / (1 + e * Math.cos(v * DEG)); // AU
  const Omega = 125.04 - 1934.136 * T;                                 // 度
  const apparentLong = trueLong - 0.00569 - 0.00478 * Math.sin(Omega * DEG);

  const epsilon = obliquityDeg(T);
  const { ra, dec } = eclipticToEquatorial(apparentLong, 0, epsilon);

  // 视半径：太阳平均 959.63" / R(AU)
  const semidiameterDeg = (959.63 / 3600) / R;

  return { ra, dec, distAU: R, apparentLongitude: norm360(apparentLong), semidiameterDeg, epsilon };
}

function obliquityDeg(T) {
  const e0 = 23 + 26 / 60 + 21.448 / 3600
    - (46.8150 * T + 0.00059 * T * T - 0.001813 * T ** 3) / 3600;
  const Omega = 125.04 - 1934.136 * T;
  return e0 + 0.00256 * Math.cos(Omega * DEG);
}

function eclipticToEquatorial(lambdaDeg, betaDeg, epsDeg) {
  const l = lambdaDeg * DEG, b = betaDeg * DEG, e = epsDeg * DEG;
  const ra = Math.atan2(
    Math.sin(l) * Math.cos(e) - Math.tan(b) * Math.sin(e),
    Math.cos(l)
  );
  const dec = Math.asin(
    Math.sin(b) * Math.cos(e) + Math.cos(b) * Math.sin(e) * Math.sin(l)
  );
  return { ra: norm360(ra / DEG), dec: dec / DEG };
}

// ---------------------------------------------------------------------------
// 4. 月球
//    Meeus ch.47 截断级数：黄经误差 ~10"，距离误差 ~10km —— 对凌月判定足够
// ---------------------------------------------------------------------------

// 周期项：D M M' F  sin系数(L)  sin系数(B)  cos系数(R, km)
const MOON_TERMS = [
  [0, 0, 1, 0, 6288774, -20905355],
  [2, 0, -1, 0, 1274027, -3699111],
  [2, 0, 0, 0, 658314, -2955968],
  [0, 0, 2, 0, 213618, -569925],
  [0, 1, 0, 0, -185116, 48888],
  [0, 0, 0, 2, -114332, -3149],
  [2, 0, -2, 0, 58793, 246158],
  [2, -1, -1, 0, 57066, -152138],
  [2, 0, 1, 0, 53322, -170733],
  [2, -1, 0, 0, 45758, -204586],
  [0, 1, -1, 0, -40923, -129620],
  [1, 0, 0, 0, -34720, 108743],
  [0, 1, 1, 0, -30383, 104755],
  [2, 0, 0, -2, 15327, 10321],
  [0, 0, 1, 2, -12528, 0],
  [0, 0, 1, -2, 10980, 79661],
  [4, 0, -1, 0, 10675, -34782],
  [0, 0, 3, 0, 10034, -23210],
  [4, 0, -2, 0, 8548, -21636],
  [2, 1, -1, 0, -7888, 24208],
  [2, 1, 0, 0, -6766, 30824],
  [1, 0, -1, 0, -5163, -8379],
  [1, 1, 0, 0, 4987, -16675],
  [2, -1, 1, 0, 4036, -12831],
  [2, 0, 2, 0, 3994, -10445],
  [4, 0, 0, 0, 3861, -11650],
  [2, 0, -3, 0, 3665, 14403],
  [0, 1, -2, 0, -2689, -7003],
  [2, 0, -1, 2, -2602, 0],
  [2, -1, -2, 0, 2390, 10056],
  [1, 0, 1, 0, -2348, 6322],
  [2, -2, 0, 0, 2236, -9884],
  [0, 1, 2, 0, -2120, 5751],
  [0, 2, 0, 0, -2069, 0],
  [2, -2, -1, 0, 2048, -4950],
  [2, 0, 1, -2, -1773, 4130],
  [2, 0, 0, 2, -1595, 0],
  [4, -1, -1, 0, 1215, -3958],
  [0, 0, 2, 2, -1110, 0],
  [3, 0, -1, 0, -892, 3258],
  [2, 1, 1, 0, -810, 2616],
  [4, -1, -2, 0, 759, -1897],
  [0, 2, -1, 0, -713, -2117],
  [2, 2, -1, 0, -700, 2354],
  [2, 1, -2, 0, 691, 0],
  [2, -1, 0, -2, 596, 0],
  [4, 0, 1, 0, 549, -1423],
  [0, 0, 4, 0, 537, -1117],
  [4, -1, 0, 0, 520, -1571],
  [1, 0, -2, 0, -487, -1739],
  [2, 1, 0, -2, -399, 0],
  [0, 0, 2, -2, -381, -4421],
  [1, 1, 1, 0, 351, 0],
  [3, 0, -2, 0, -340, 0],
  [4, 0, -3, 0, 330, 0],
  [2, -1, 2, 0, 327, 0],
  [0, 2, 1, 0, -323, 1165],
  [1, 1, -1, 0, 299, 0],
  [2, 0, 3, 0, 294, 0],
  [2, 0, -1, -2, 0, 8752],
];

/** 月球黄经黄纬与距离（Meeus ch.47），jdTT 为 TT 儒略日 */
export function moonPosition(jdTT) {
  const T = (jdTT - 2451545.0) / 36525;
  const Lp = norm360(218.3164477 + 481267.88123421 * T - 0.0015786 * T * T
    + T ** 3 / 538841 - T ** 4 / 65194000);
  const D = norm360(297.8501921 + 445267.1114034 * T - 0.0018819 * T * T
    + T ** 3 / 545868 - T ** 4 / 113065000);
  const M = norm360(357.5291092 + 35999.0502909 * T - 0.0001536 * T * T + T ** 3 / 24490000);
  const Mp = norm360(134.9633964 + 477198.8675055 * T + 0.0087414 * T * T
    + T ** 3 / 69699 - T ** 4 / 14712000);
  const F = norm360(93.2720950 + 483202.0175233 * T - 0.0036539 * T * T
    - T ** 3 / 3526000 + T ** 4 / 863310000);

  const A1 = norm360(119.75 + 131.849 * T);
  const A2 = norm360(53.09 + 479264.290 * T);
  const A3 = norm360(313.45 + 481266.484 * T);
  const E = 1 - 0.002516 * T - 0.0000074 * T * T;

  let sumL = 0, sumR = 0;
  for (const [d, m, mp, f, cl, cr] of MOON_TERMS) {
    const arg = (d * D + m * M + mp * Mp + f * F) * DEG;
    let w = 1;
    if (Math.abs(m) === 1) w = E;
    else if (Math.abs(m) === 2) w = E * E;
    sumL += cl * w * Math.sin(arg);
    sumR += cr * w * Math.cos(arg);
  }
  sumL += 3958 * Math.sin(A1 * DEG) + 1962 * Math.sin((Lp - F) * DEG)
    + 318 * Math.sin(A2 * DEG);
  const sumB =
    5128122 * Math.sin(F * DEG) +
    280602 * Math.sin((Mp + F) * DEG) +
    277693 * Math.sin((Mp - F) * DEG) +
    173237 * Math.sin((2 * D - F) * DEG) +
    55413 * Math.sin((2 * D - Mp + F) * DEG) +
    46271 * Math.sin((2 * D - Mp - F) * DEG) +
    32573 * Math.sin((2 * D + F) * DEG) +
    17198 * Math.sin((2 * Mp + F) * DEG) +
    9266 * Math.sin((2 * D + Mp - F) * DEG) +
    8822 * Math.sin((2 * Mp - F) * DEG) +
    8216 * Math.sin((2 * D - F) * DEG) * 0 + // 占位，下面补上完整项
    8216 * Math.sin((2 * D - M - F) * DEG) * 0;

  // 完整 B 级数（前若干主要项已并入 sumB 的手写部分）
  const binB = [
    [0, 0, 0, 1, 5128122], [0, 0, 1, 1, 280602], [0, 0, 1, -1, 277693],
    [2, 0, 0, -1, 173237], [2, 0, -1, 1, 55413], [2, 0, -1, -1, 46271],
    [2, 0, 0, 1, 32573], [0, 0, 2, 1, 17198], [2, 0, 1, -1, 9266],
    [0, 0, 2, -1, 8822], [2, -1, 0, -1, 8216], [2, 0, -2, -1, 4324],
    [2, 0, 1, 1, 4200], [2, 1, 0, -1, -3359], [2, -1, -1, 1, 2463],
    [2, -1, 0, 1, 2211], [2, -1, -1, -1, 2065], [0, -1, -1, -1, -1870],
    [4, 0, -1, -1, 1828], [0, 1, 0, -1, -1794], [0, 0, 0, 3, -1749],
    [0, -1, 1, -1, -1565], [1, 0, 0, 1, -1491], [0, 1, 1, -1, -1475],
    [0, 1, -1, -1, -1410], [0, -1, 0, 1, -1344], [1, 0, -1, 1, -1335],
    [0, 0, 3, 1, 1107], [4, 0, 0, -1, 1021], [4, 0, -1, 1, 833],
    [0, 0, 1, -3, 777], [4, 0, -2, 1, 671], [2, 0, 0, -3, 607],
    [2, 0, 2, -1, 596], [2, -1, 1, -1, 491], [2, 0, -2, 1, -451],
    [0, 0, 3, -1, 439], [2, 0, 2, 1, 422], [2, 0, -3, -1, 421],
    [2, 1, -1, 1, -366], [2, 1, 0, 1, -351], [4, 0, 0, 1, 331],
    [2, -1, 1, 1, 315], [2, -2, 0, -1, 302], [0, 0, 1, 3, -283],
    [2, 1, 1, -1, -229], [1, 1, 0, -1, 223], [1, 1, 0, 1, 223],
    [0, 1, -2, -1, -220], [2, 1, -1, -1, -220], [1, 0, 1, 1, -185],
    [2, -1, -2, -1, 181], [0, 1, 2, 1, -177], [4, 0, -2, -1, 176],
    [4, -1, -1, -1, 166], [1, 0, 1, -1, -164], [4, 0, 1, -1, 132],
    [1, 0, -1, -1, -119], [4, -1, 0, -1, 115], [2, -2, 0, 1, 107],
  ];
  let bSum = 0;
  for (const [d, m, mp, f, c] of binB) {
    const arg = (d * D + m * M + mp * Mp + f * F) * DEG;
    let w = 1;
    if (Math.abs(m) === 1) w = E;
    else if (Math.abs(m) === 2) w = E * E;
    bSum += c * w * Math.sin(arg);
  }
  bSum += -2235 * Math.sin(Lp * DEG) + 382 * Math.sin(A3 * DEG)
    + 175 * Math.sin((A1 - F) * DEG) + 175 * Math.sin((A1 + F) * DEG)
    + 127 * Math.sin((Lp - Mp) * DEG) - 115 * Math.sin((Lp + Mp) * DEG);

  const lambda = norm360(Lp + sumL / 1000000);
  const beta = bSum / 1000000;
  const distKm = 385000.56 + sumR / 1000;

  return { lambda, beta, distKm, D, M, Mp, F };
}

/**
 * 月球地心赤道坐标 + 站心视差修正，得到「站心视位置」。
 * 视差对月亮不可忽略（最大约 1°，远大于月面半径 0.26°）。
 */
export function moonTopocentric(jdTT, jdUT, latDeg, lonDeg, elevM = 0) {
  const T = (jdTT - 2451545.0) / 36525;
  const eps = obliquityDeg(T);
  const m = moonPosition(jdTT);

  // 距离（地球赤道半径为单位）
  const distER = m.distKm / 6378.14;
  const pi = Math.asin(1 / distER); // 赤道地平视差（弧度）

  const { ra, dec } = eclipticToEquatorial(m.lambda, m.beta, eps);

  // Meeus ch.40 -- 站心修正
  const phi = latDeg * DEG;
  const u = Math.atan(0.99664719 * Math.tan(phi));
  const b = 0.99664719;
  const rhoSinPhi = b * Math.sin(u) + (elevM / 6378140) * Math.sin(phi);
  const rhoCosPhi = Math.cos(u) + (elevM / 6378140) * Math.cos(phi);

  const theta = (gmstDeg(jdUT) + lonDeg) * DEG; // 当地恒星时
  const H = theta - ra * DEG;                    // 时角

  const dRa = Math.atan2(
    -rhoCosPhi * Math.sin(pi) * Math.sin(H),
    Math.cos(dec * DEG) - rhoCosPhi * Math.sin(pi) * Math.cos(H)
  );
  const raTop = ra + dRa / DEG;

  const decTop = Math.atan2(
    (Math.sin(dec * DEG) - rhoSinPhi * Math.sin(pi)) * Math.cos(dRa),
    Math.cos(dec * DEG) - rhoCosPhi * Math.sin(pi) * Math.cos(H)
  ) / DEG;

  const semidiameterDeg = Math.asin(1737.4 / m.distKm) / DEG;

  return {
    ra: norm360(raTop), dec: decTop, distKm: m.distKm,
    semidiameterDeg, parallaxDeg: pi / DEG,
    geocentric: { ra, dec },
  };
}

// ---------------------------------------------------------------------------
// 5. 坐标变换
// ---------------------------------------------------------------------------

/** 地平坐标：返回 { alt, az }，az 自北向东计量 */
export function equatorialToHorizontal(raDeg, decDeg, jdUT, latDeg, lonDeg) {
  const H = (gmstDeg(jdUT) + lonDeg - raDeg) * DEG;
  const dec = decDeg * DEG, lat = latDeg * DEG;
  const alt = Math.asin(
    Math.sin(lat) * Math.sin(dec) + Math.cos(lat) * Math.cos(dec) * Math.cos(H)
  );
  const az = Math.atan2(
    -Math.sin(H) * Math.cos(dec),
    Math.sin(dec) * Math.cos(lat) - Math.cos(dec) * Math.sin(lat) * Math.cos(H)
  );
  return { alt: alt / DEG, az: norm360(az / DEG) };
}

/** 单位向量：由方位角/高度角得到 ENU（东、北、天）分量 */
export function altAzToEnu(altDeg, azDeg) {
  const alt = altDeg * DEG, az = azDeg * DEG;
  return {
    e: Math.cos(alt) * Math.sin(az),
    n: Math.cos(alt) * Math.cos(az),
    u: Math.sin(alt),
  };
}

/** 两个地平坐标之间的角距（度） */
export function angularSeparation(alt1, az1, alt2, az2) {
  const a = altAzToEnu(alt1, az1), b = altAzToEnu(alt2, az2);
  const dot = clamp(a.e * b.e + a.n * b.n + a.u * b.u, -1, 1);
  return Math.acos(dot) / DEG;
}

export function observerEcef(latDeg, lonDeg, hM = 0) {
  const a = 6378137.0, f = 1 / 298.257223563;
  const e2 = f * (2 - f);
  const phi = latDeg * DEG, lam = lonDeg * DEG;
  const N = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2);
  return {
    x: (N + hM) * Math.cos(phi) * Math.cos(lam),
    y: (N + hM) * Math.cos(phi) * Math.sin(lam),
    z: (N * (1 - e2) + hM) * Math.sin(phi),
  };
}

/** 飞机（大地坐标）相对于观测点的地平坐标与斜距 */
export function aircraftHorizontal(obs, ac) {
  const o = observerEcef(obs.lat, obs.lon, obs.elevM || 0);
  const p = observerEcef(ac.lat, ac.lon, ac.altM || 0);
  const dx = p.x - o.x, dy = p.y - o.y, dz = p.z - o.z;
  const phi = obs.lat * DEG, lam = obs.lon * DEG;
  const sp = Math.sin(phi), cp = Math.cos(phi);
  const sl = Math.sin(lam), cl = Math.cos(lam);
  // ECEF -> ENU
  const e = -sl * dx + cl * dy;
  const n = -sp * cl * dx - sp * sl * dy + cp * dz;
  const u = cp * cl * dx + cp * sl * dy + sp * dz;
  const range = Math.hypot(e, n, u);
  const alt = Math.asin(u / range) / DEG;
  const az = norm360(Math.atan2(e, n) / DEG);
  return { alt, az, range, enu: { e: e / range, n: n / range, u: u / range } };
}

// ---------------------------------------------------------------------------
// 6. 飞机角尺寸（三维投影，自动处理迎头/侧身）
// ---------------------------------------------------------------------------

const DEFAULT_DIMS = {
  // 翼展 / 机长 / 机高（米）
  narrow: { span: 35.8, len: 37.6, height: 11.8 }, // A320 级别
  wide: { span: 60.9, len: 63.7, height: 17.0 },   // B777 级别
  regional: { span: 26.0, len: 27.2, height: 7.0 },
};

export function aircraftDimensions(cls) {
  return DEFAULT_DIMS[cls] || DEFAULT_DIMS.narrow;
}

/**
 * 计算飞机在天空中的角尺寸。
 *
 * 做法：把机体当作「翼展 × 机长 × 机高」的长方体，取其 8 个顶点，
 * 全部投影到垂直视线的平面上，再求这 8 个点的外接椭圆半轴。
 *
 * 这样迎头/尾随会自然得到「翼展投影 + 机高」的正面轮廓，而不会
 * 错误地保留整条翼展 —— 不需要任何特判分支。
 *
 * @returns {{ majorDeg, minorDeg, projectedAreaDeg2, frontal, range }}
 */
export function aircraftAngularSize(obs, ac, dims) {
  const o = observerEcef(obs.lat, obs.lon, obs.elevM || 0);
  const p = observerEcef(ac.lat, ac.lon, ac.altM || 0);
  const phi = obs.lat * DEG, lam = obs.lon * DEG;
  const sp = Math.sin(phi), cp = Math.cos(phi);
  const sl = Math.sin(lam), cl = Math.cos(lam);
  const toEnu = (v) => ({
    e: -sl * v.x + cl * v.y,
    n: -sp * cl * v.x - sp * sl * v.y + cp * v.z,
    u: cp * cl * v.x + cp * sl * v.y + sp * v.z,
  });
  const d = toEnu({ x: p.x - o.x, y: p.y - o.y, z: p.z - o.z });
  const range = Math.hypot(d.e, d.n, d.u);
  const los = { e: d.e / range, n: d.n / range, u: d.u / range };

  // 机体三轴在 ENU 中（heading 自北向东计量）
  const h = (ac.headingDeg || 0) * DEG;
  const body = {
    span: { e: Math.cos(h), n: -Math.sin(h), u: 0 }, // 翼展方向
    fuse: { e: Math.sin(h), n: Math.cos(h), u: 0 },  // 机头方向
    vert: { e: 0, n: 0, u: 1 },                      // 机背方向
  };
  const half = {
    span: (dims.span || 35.8) / 2,
    fuse: (dims.len || 37.6) / 2,
    vert: (dims.height || 11.8) / 2,
  };

  // 投影到垂直视线的平面：q = v - (v·los) los
  const project = (v) => {
    const dot = v.e * los.e + v.n * los.n + v.u * los.u;
    return { e: v.e - dot * los.e, n: v.n - dot * los.n, u: v.u - dot * los.u };
  };
  const aSpan = project(body.span);
  const aFuse = project(body.fuse);
  const aVert = project(body.vert);

  // 枚举 8 个顶点的平面投影坐标。
  // 注意：u 分量必须照常累加，不能置 0 —— 视线接近水平时，
  // 「机高」方向几乎整个落在视平面内，丢掉 u 会直接让短轴归零。
  const pts = [];
  for (const si of [-1, 1]) {
    for (const fi of [-1, 1]) {
      for (const vi of [-1, 1]) {
        pts.push({
          e: si * half.span * aSpan.e + fi * half.fuse * aFuse.e + vi * half.vert * aVert.e,
          n: si * half.span * aSpan.n + fi * half.fuse * aFuse.n + vi * half.vert * aVert.n,
          u: si * half.span * aSpan.u + fi * half.fuse * aFuse.u + vi * half.vert * aVert.u,
        });
      }
    }
  }

  // --- 求平面内的两个主方向 ---
  //
  // 所有顶点都落在「过原点、垂直于视线」的平面内，所以直接在该平面上
  // 取一组正交基 (e1, e2)，把顶点写成二维坐标，再求 2x2 协方差主方向。
  //
  // 走过的弯路（留作记录）：
  //   1. 只在 (e,n) 分量上做 2x2 协方差 —— 会丢掉天顶分量，
  //      迎头时短轴被算成 0。
  //   2. 用「原点 + 最远点」构造平面基 —— 顶点共线时（侧视）
  //      两个向量线性相关，基退化，短轴被算成 0。
  //   3. 用坐标轴的叉积兜底 —— 会把平面外的方向当成分量轴，同样错误。
  // 正解是用视线向量本身构造平面的正交基。
  const N = pts.length;
  const cross = (a, b) => ({
    e: a.n * b.u - a.u * b.n,
    n: a.u * b.e - a.e * b.u,
    u: a.e * b.n - a.n * b.e,
  });
  const dot3 = (a, b) => a.e * b.e + a.n * b.n + a.u * b.u;
  const normalize = (v) => {
    const m = Math.hypot(v.e, v.n, v.u);
    return { e: v.e / m, n: v.n / m, u: v.u / m };
  };

  // 选一个与视线不平行的参考向量，叉积得到平面内的基。
  // 顺序必须是 cross(ref, los)：若写成 cross(los, ref)，
  // 当视线沿东时 ref=天顶 会算出 e1=天顶方向，水平方向被错当成第二轴。
  const ref = Math.abs(los.u) < 0.9 ? { e: 0, n: 0, u: 1 } : { e: 1, n: 0, u: 0 };
  const e1 = normalize(cross(ref, los));
  const e2 = normalize(cross(los, e1));

  let c11 = 0, c22 = 0, c12 = 0;
  for (const q of pts) {
    const x = dot3(q, e1), y = dot3(q, e2);
    c11 += x * x; c22 += y * y; c12 += x * y;
  }
  c11 /= N; c22 /= N; c12 /= N;

  const tr2 = c11 + c22;
  const det2 = c11 * c22 - c12 * c12;
  const disc2 = Math.sqrt(Math.max(0, (tr2 / 2) ** 2 - det2));
  const l1 = tr2 / 2 + disc2;
  const l2 = Math.max(0, tr2 / 2 - disc2);

  // 主方向。
  // 注意退化情形：侧视时机高方向几乎不投影到平面上，协方差第二特征值≈0。
  // 此时不能拿「谁的方差大」去选方向，否则长短轴会返回同一个方向。
  // 正确规则：对第 1 主方向，取方差最大的坐标轴；对第 2 主方向，
  // 必须取与之垂直的那一个坐标轴。
  const basisDir = (which, lam) => {
    if (Math.abs(c12) > 1e-12) {
      const x = c12, y = lam - c11;
      const m = Math.hypot(x, y);
      return { x: x / m, y: y / m };
    }
    const majorAlongE1 = c11 >= c22;
    if (which === 1) return majorAlongE1 ? { x: 1, y: 0 } : { x: 0, y: 1 };
    return majorAlongE1 ? { x: 0, y: 1 } : { x: 1, y: 0 };
  };
  const d1 = basisDir(1, l1);
  const d2 = basisDir(2, l2);

  // 用支撑函数求该方向上的真实半宽（协方差特征值只是均方展布，不是外接尺寸）
  const support = (d2d) => {
    let mx = 0;
    for (const q of pts) {
      mx = Math.max(mx, Math.abs(dot3(q, e1) * d2d.x + dot3(q, e2) * d2d.y));
    }
    return mx;
  };

  const halfMajorRad = support(d1) / range;
  const halfMinorRad = support(d2) / range;

  const spanRad = (dims.span || 35.8) / range;
  const areaRad2 = (spanRad * (dims.len || 37.6) / range) * 0.25;

  // 迎头判定：机身轴与视线夹角很小
  const fuseDot = Math.abs(
    body.fuse.e * los.e + body.fuse.n * los.n + body.fuse.u * los.u
  );

  return {
    majorDeg: (2 * halfMajorRad) / DEG,
    minorDeg: (2 * halfMinorRad) / DEG,
    projectedAreaDeg2: (areaRad2 * 4) / (DEG * DEG),
    frontal: fuseDot > 0.9,
    range,
  };
}

// ---------------------------------------------------------------------------
// 7. 穿越判定
// ---------------------------------------------------------------------------

/**
 * 求某时刻太阳/月亮的站心视位置（地平坐标）。
 * 注意：几何判定用「真」位置即可 —— 凌日/凌月时光束同时经过两条路径，
 * 折射对二者的影响在共同高度上几乎抵消（差 < 0.1′）。refractionDeg()
 * 用于展示和人眼可读性。
 */
export function bodyHorizontal(kind, jdUTC, obs) {
  const jdTT = ttFromUTC(jdUTC);
  if (kind === 'sun') {
    const s = sunPosition(jdTT);
    const h = equatorialToHorizontal(s.ra, s.dec, jdUTC, obs.lat, obs.lon);
    return { ...h, semidiameterDeg: s.semidiameterDeg, ra: s.ra, dec: s.dec };
  }
  const m = moonTopocentric(jdTT, jdUTC, obs.lat, obs.lon, obs.elevM || 0);
  const h = equatorialToHorizontal(m.ra, m.dec, jdUTC, obs.lat, obs.lon);
  return { ...h, semidiameterDeg: m.semidiameterDeg, ra: m.ra, dec: m.dec };
}

/**
 * 在 [t0, t0+windowSec] 内扫描一架飞机对某天体的穿越。
 *
 * @param {'sun'|'moon'} kind
 * @param {object} obs   { lat, lon, elevM }
 * @param {object} ac    { lat, lon, altM, headingDeg, speedMs, dims }
 *        —— lat/lon/altM 为 t0 时刻状态；speedMs 为地速（米/秒）
 * @param {number} t0Ms  t0 的 Unix 毫秒时间戳
 * @param {number} windowSec 扫描窗口（秒），默认 180
 * @param {number} stepSec   粗扫步长（秒），默认 1
 * @returns {null | object} 穿越详情
 */
export function scanTransit(kind, obs, ac, t0Ms, windowSec = 180, stepSec = 1) {
  const dims = ac.dims || aircraftDimensions('narrow');
  const speed = (ac.speedMs || 0);

  // 等距圆柱近似推进足够（窗口只有几分钟）
  const posAt = (dtSec) => {
    const h = ac.headingDeg * DEG;
    const dNorth = Math.cos(h) * speed * dtSec;
    const dEast = Math.sin(h) * speed * dtSec;
    const dLat = dNorth / 111320;
    const dLon = dEast / (111320 * Math.cos(ac.lat * DEG));
    return { lat: ac.lat + dLat, lon: ac.lon + dLon, altM: ac.altM, headingDeg: ac.headingDeg };
  };

  const sepAt = (dtSec) => {
    const jd = jdFromDate(new Date(t0Ms + dtSec * 1000));
    const b = bodyHorizontal(kind, jd, obs);
    const a = aircraftHorizontal(obs, posAt(dtSec));
    const sep = angularSeparation(a.alt, a.az, b.alt, b.az);
    const size = aircraftAngularSize(obs, posAt(dtSec), dims);
    // 有效判定半径：天体半径 + 机身在该方向上的等效半径（保守取长短半轴均值）
    const acRadius = (size.majorDeg + size.minorDeg) / 4;
    return { sep, threshold: b.semidiameterDeg + acRadius, body: b, ac: a, size };
  };

  // 一天体低于地平就无意义
  const start = sepAt(0);
  if (start.body.alt < -2) return null;

  let prev = start, prevT = 0;
  let best = { dt: 0, ...start };

  for (let t = stepSec; t <= windowSec; t += stepSec) {
    const cur = sepAt(t);
    if (cur.sep < best.sep) best = { dt: t, ...cur };

    // 极小值落在 (prevT, t) 之间：三点抛物线细分
    if (prev.sep < best.sep + 1e-9 || cur.sep > prev.sep) {
      if (prev.sep <= cur.sep && prev.sep <= sepAt(t - stepSec * 0.5).sep) {
        const refined = refineMinimum(sepAt, prevT, t, stepSec);
        if (refined.sep < best.sep) best = refined;
      }
    }
    prev = cur; prevT = t;
  }

  // 收尾：末段极小值
  const refinedEnd = refineMinimum(sepAt, Math.max(0, windowSec - stepSec), windowSec, stepSec);
  if (refinedEnd.sep < best.sep) best = refinedEnd;

  if (best.sep > best.threshold) return null;

  // 求穿越持续时长：sep(t) = threshold 的两个根
  const half = findCrossings(sepAt, best.dt, best.threshold, stepSec);
  const bodyName = kind === 'sun' ? '日面' : '月面';

  return {
    kind,
    body: bodyName,
    peakOffsetSec: best.dt,
    peakTime: new Date(t0Ms + best.dt * 1000),
    separationDeg: best.sep,
    thresholdDeg: best.threshold,
    coverage: best.threshold > 0
      ? clamp(1 - best.sep / best.threshold, 0, 1)
      : 0,
    durationSec: half ? half[1] - half[0] : 0,
    enterOffsetSec: half ? half[0] : best.dt,
    exitOffsetSec: half ? half[1] : best.dt,
    bodyAltDeg: best.body.alt,
    bodyAzDeg: best.body.az,
    bodySemidiameterDeg: best.body.semidiameterDeg,
    aircraftAltDeg: best.ac.alt,
    aircraftAzDeg: best.ac.az,
    rangeM: best.ac.range,
    aircraftMajorDeg: best.size.majorDeg,
    aircraftMinorDeg: best.size.minorDeg,
    frontal: best.size.frontal,
    // 相对天体中心的偏移方向（画面坐标：右=+x，上=+y）
    offsetXArcmin: (best.ac.az - best.body.az) * Math.cos(best.body.alt * DEG) * 60,
    offsetYArcmin: (best.ac.alt - best.body.alt) * 60,
  };
}

/** 三分点抛物线求 sep(t) 的局部极小值 */
function refineMinimum(sepAt, tA, tB, stepSec) {
  let lo = tA, hi = tB;
  for (let i = 0; i < 40; i++) {
    const m1 = lo + (hi - lo) / 3;
    const m2 = hi - (hi - lo) / 3;
    if (sepAt(m1).sep < sepAt(m2).sep) hi = m2; else lo = m1;
    if (hi - lo < 0.001) break;
  }
  const t = (lo + hi) / 2;
  return { dt: t, ...sepAt(t) };
}

/** 在 bestT 两侧找 sep = threshold 的两个根（线性插值） */
function findCrossings(sepAt, bestT, threshold, stepSec) {
  const f = (t) => sepAt(t).sep - threshold;
  if (f(bestT) > 0) return null;

  const left = (dir) => {
    let t = bestT;
    let prevVal = f(t);
    for (let i = 0; i < 400; i++) {
      const nt = t + dir * Math.max(0.02, stepSec / 4);
      const v = f(nt);
      if (v > 0) {
        // 二分收窄
        let a = t, b = nt;
        for (let k = 0; k < 40; k++) {
          const m = (a + b) / 2;
          if (f(m) > 0) b = m; else a = m;
        }
        return (a + b) / 2;
      }
      t = nt; prevVal = v;
      if (Math.abs(t - bestT) > 120) break;
    }
    return null;
  };
  const t1 = left(-1), t2 = left(1);
  if (t1 === null || t2 === null) return null;
  return [t1, t2];
}
